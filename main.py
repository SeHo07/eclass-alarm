"""이클래스 마감 알림 봇.

사용법:
  python main.py check    # 10분마다: 미완료 항목 마감 3시간/1시간 전 반복 알림
  python main.py weekly   # 주 1회: 이번 주 일정 정리
  python main.py test     # 연결 테스트: 로그인 + 텔레그램 발송
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path

from eclass_alarm.eclass import KST, EclassClient, Item, LoginError
from eclass_alarm.telegram import Telegram

STATE_PATH = Path(os.environ.get("STATE_PATH", "state/state.json"))
WINDOWS = [(2, 60 * 60, "🚨🚨 마감 1시간 전"), (1, 3 * 60 * 60, "⏰ 마감 3시간 전")]  # (level, 초, 제목)
LOOP_SECONDS = int(os.environ.get("LOOP_SECONDS", "480"))   # 한 번 실행에서 반복 알림을 유지하는 시간
REFRESH_HOURS = float(os.environ.get("REFRESH_HOURS", "3"))  # 마감 없을 때 정기 확인 간격
ALERT_MARGIN = 15 * 60  # 알림 구간 직전부터 미리 확인
RESEND_SECONDS = int(os.environ.get("RESEND_SECONDS", "60"))  # 반복 간격
WEEKDAYS = "월화수목금토일"
ACK_WORDS = {"확인", "ㅇㅋ", "ok", "OK", "/ack"}


# ---------------------------------------------------------------- 상태

def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 오래된 확인 기록 정리 (14일)
    cutoff = time.time() - 14 * 86400
    state["acked"] = {k: v for k, v in state.get("acked", {}).items() if v > cutoff}
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- 포맷

def fmt_dt(ts: int) -> str:
    d = datetime.fromtimestamp(ts, KST)
    return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]}) {d:%H:%M}"


def fmt_left(ts: int, now: float) -> str:
    sec = int(ts - now)
    if sec <= 0:
        return "마감 지남"
    h, m = divmod(sec // 60, 60)
    return f"{h}시간 {m}분" if h else f"{m}분"


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def alert_text(it: Item, title: str, now: float, count: int) -> str:
    rep = f" (알림 {count}회차)" if count > 1 else ""
    return (
        f"<b>{title}</b>{rep}\n"
        f"📚 {esc(it.course)}\n"
        f"📝 [{it.label}] {esc(it.name)}\n"
        f"🕐 {fmt_dt(it.deadline)} · <b>{fmt_left(it.deadline, now)} 남음</b>\n"
        f"<a href=\"{esc(it.url)}\">바로가기</a>"
    )


def list_text(items: list[Item], now: float, days: int = 7, include_done: bool = True, title: str | None = None) -> str:
    end = now + days * 86400
    upcoming = [i for i in items if now < i.deadline <= end and (include_done or not i.done)]
    late = [i for i in items if not i.done and i.deadline <= now and i.late_deadline and now < i.late_deadline]
    lines = [title or f"<b>📅 앞으로 {days}일 일정</b>"]
    if not upcoming:
        lines.append("\n마감 예정 항목 없음 🎉")
    day = None
    for i in upcoming:
        d = datetime.fromtimestamp(i.deadline, KST)
        key = d.date()
        if key != day:
            day = key
            lines.append(f"\n<b>{d.month}/{d.day}({WEEKDAYS[d.weekday()]})</b>")
        mark = "✅" if i.done else "⬜"
        lines.append(f"{mark} {d:%H:%M} [{i.label}] {esc(i.course)} · {esc(i.name)}")
    todo = sum(1 for i in upcoming if not i.done)
    lines.append(f"\n미완료 {todo}개 / 전체 {len(upcoming)}개")
    if late:
        lines.append("\n<b>⚠️ 지각 인정 기간 남은 동영상</b>")
        for i in late:
            lines.append(f"⬜ ~{fmt_dt(i.late_deadline)} {esc(i.course)} · {esc(i.name)}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 텔레그램 입력 처리

def handle_updates(tg: Telegram, state: dict, items: list[Item] | None, pending: dict, wait: int = 0) -> None:
    """버튼 클릭(확인)과 명령어(/list, /week)를 처리한다."""
    ups = tg.updates(state.get("tg_offset"), wait=wait)
    for u in ups:
        state["tg_offset"] = u["update_id"] + 1
        now = time.time()
        cb = u.get("callback_query")
        if cb:
            if str(cb.get("message", {}).get("chat", {}).get("id")) != tg.chat_id:
                continue
            data = cb.get("data", "")
            if data.startswith("ack:"):
                key = data[4:]
                state.setdefault("acked", {})[key] = now
                tg.answer_callback(cb["id"], "확인! 알림 멈출게")
                p = pending.pop(key, None)
                msg_id = p["msg"] if p else cb["message"]["message_id"]
                tg.edit(msg_id, "✅ 확인함 — " + esc(p["item"].name if p else "알림"))
            continue
        msg = u.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != tg.chat_id:
            continue
        text = (msg.get("text") or "").strip()
        if text in ACK_WORDS:
            for key, p in list(pending.items()):
                state.setdefault("acked", {})[key] = now
                tg.edit(p["msg"], "✅ 확인함 — " + esc(p["item"].name))
                pending.pop(key)
            tg.send("✅ 지금 울리는 알림 전부 확인 처리했어")
        elif text.startswith(("/pause", "일시정지")):
            until = parse_pause(text, now)
            state["paused_until"] = until
            when = "다시 켤 때까지(/resume)" if until == float("inf") else fmt_dt(int(until)) + "까지"
            for key in list(pending):
                tg.edit(pending.pop(key)["msg"], "⏸ 일시정지로 알림 중단")
            tg.send(f"⏸ 마감 알림 일시정지: {when}\n주간 정리와 /list는 계속 동작해.")
        elif text in ("/resume", "재개"):
            state.pop("paused_until", None)
            tg.send("▶️ 마감 알림 다시 켬")
        elif text in ("/refresh", "새로고침"):
            state["force_refresh"] = True
            if items is None:
                tg.send("🔄 지금 이클래스 확인할게")
        elif text in ("/list", "목록") and items is not None:
            seen = state.get("fetched_at")
            note = f" · {datetime.fromtimestamp(seen, KST):%m/%d %H:%M} 기준" if seen else ""
            tg.send(list_text(items, now, days=7, include_done=False, title=f"<b>📋 미완료 항목 (7일){note}</b>")
                    + "\n최신 상태가 필요하면 /refresh")
        elif text in ("/week", "주간") and items is not None:
            tg.send(list_text(items, now, days=7))
        elif text in ("/start", "/help"):
            tg.send("과제·동영상·퀴즈 마감 알림 봇이야.\n"
                    "• 마감 3시간·1시간 전에 [확인] 누를 때까지 반복 알림\n"
                    "• /list 미완료 목록 · /week 이번 주 일정\n"
                    "• '확인'이라고 보내면 울리는 알림 전부 정지\n"
                    "• /refresh 지금 바로 이클래스 다시 확인\n"
                    "• /pause 3h · /pause 2d · /pause (무기한) 일시정지, /resume 재개\n"
                    "(10분마다 확인해서 답장이 최대 10분 늦을 수 있어)")


def parse_pause(text: str, now: float) -> float:
    """'/pause' -> 무기한, '/pause 3h' / '3' -> 3시간, '/pause 2d' -> 2일"""
    m = re.search(r"(\d+)\s*([hdm시일분]?)", text)
    if not m:
        return float("inf")
    n, unit = int(m.group(1)), m.group(2)
    sec = {"d": 86400, "일": 86400, "m": 60, "분": 60}.get(unit, 3600)
    return now + n * sec


def is_paused(state: dict, now: float) -> bool:
    until = state.get("paused_until")
    if until is None:
        return False
    if now >= until:
        state.pop("paused_until", None)
        return False
    return True


# ---------------------------------------------------------------- 모드

def collect(state: dict, tg: Telegram) -> list[Item] | None:
    cli = None
    try:
        cli = EclassClient(os.environ["ECLASS_ID"], os.environ["ECLASS_PW"])
        items = cli.collect()
        state["items"] = [asdict(i) for i in items]
        state["fetched_at"] = time.time()
        state.pop("force_refresh", None)
        return items
    except Exception as e:  # 로그인 실패 등은 6시간에 한 번만 알림
        print(f"collect error: {type(e).__name__}: {e}", file=sys.stderr)
        last = state.get("last_error_notice", 0)
        if time.time() - last > 6 * 3600:
            kind = "로그인 실패" if isinstance(e, LoginError) else "수집 오류"
            tg.send(f"⚠️ 이클래스 {kind}: {esc(str(e))[:300]}\n이 상태면 알림이 안 가니까 확인해줘.")
            state["last_error_notice"] = time.time()
        return None
    finally:
        if cli:
            cli.logout()  # 세션을 남겨두지 않는다


def cached_items(state: dict) -> list[Item] | None:
    if "items" not in state:
        return None
    return [Item(**d) for d in state["items"]]


def need_refresh(state: dict, now: float) -> str | None:
    """로그인이 필요한 이유를 반환. None이면 이번 실행은 로그인하지 않는다."""
    if state.get("force_refresh"):
        return "요청"
    items = cached_items(state)
    if items is None:
        return "캐시 없음"
    if now - state.get("fetched_at", 0) >= REFRESH_HOURS * 3600:
        return "정기 확인"
    for it in items:  # 미완료 항목이 알림 구간(3시간 + 여유) 안에 있을 때만 10분 간격 확인
        if not it.done and 0 < it.deadline - now <= WINDOWS[-1][1] + ALERT_MARGIN:
            return "마감 임박"
    return None


def due_alerts(items: list[Item], acked: dict, now: float) -> list[tuple[Item, int, str]]:
    out = []
    for it in items:
        if it.done or it.deadline <= now:
            continue
        left = it.deadline - now
        for level, window, title in WINDOWS:  # 1시간 창을 먼저 검사
            if left <= window:
                if f"{it.cmid}:{level}" not in acked:
                    out.append((it, level, title))
                break
    return out


def run_check(tg: Telegram, state: dict) -> None:
    pending: dict[str, dict] = {}
    handle_updates(tg, state, cached_items(state), pending)  # 명령어는 로그인 없이 캐시로 응답
    start = now = time.time()
    if is_paused(state, now) and not state.get("force_refresh"):
        print("paused")
        return
    reason = need_refresh(state, now)
    if reason is None:
        print("skip: 마감 임박 항목 없음, 로그인 안 함")
        return
    print(f"refresh: {reason}")
    was_forced = state.get("force_refresh")
    items = collect(state, tg)
    if items is None:
        return
    if was_forced:
        tg.send(list_text(items, now, days=7, include_done=False, title="<b>🔄 새로 확인함 · 미완료 (7일)</b>"))
    if is_paused(state, now):
        return
    for it, level, title in due_alerts(items, state.get("acked", {}), now):
        pending[f"{it.cmid}:{level}"] = {"item": it, "title": title, "msg": None, "count": 0, "last": 0}
    print(f"items={len(items)} pending_alerts={len(pending)}")

    while pending and time.time() - start < LOOP_SECONDS:
        now = time.time()
        for key, p in list(pending.items()):
            if p["item"].deadline <= now:
                pending.pop(key)
                continue
            if now - p["last"] >= RESEND_SECONDS:
                if p["msg"]:
                    tg.delete(p["msg"])  # 이전 메시지 지우고 새로 보내서 다시 울리게
                p["count"] += 1
                p["msg"] = tg.send(alert_text(p["item"], p["title"], now, p["count"]),
                                   buttons=[[("✅ 확인 (알림 끄기)", f"ack:{key}")]])
                p["last"] = now
        handle_updates(tg, state, items, pending, wait=10)
        save_state(state)


def run_weekly(tg: Telegram, state: dict) -> None:
    items = collect(state, tg)
    if items is None:
        return
    now = time.time()
    d = datetime.fromtimestamp(now, KST)
    tg.send(list_text(items, now, days=7, title=f"<b>🗓 주간 일정 ({d.month}/{d.day}~)</b>\n투두메이트에 옮겨 적기!"))


def run_test(tg: Telegram, state: dict) -> None:
    tg.send("🔧 연결 테스트 시작")
    items = collect(state, tg)
    if items is None:
        return
    now = time.time()
    todo = [i for i in items if not i.done and i.deadline > now]
    tg.send(f"✅ 이클래스 로그인 성공\n수집 {len(items)}개 · 마감 전 미완료 {len(todo)}개")
    tg.send(list_text(items, now, days=14, title="<b>📅 앞으로 14일 일정 (테스트)</b>"))
    tg.send("🔔 반복 알림 테스트: 아래 버튼 누르면 끝",
            buttons=[[("✅ 확인 (알림 끄기)", "ack:test")]])
    handle_updates(tg, state, items, {}, wait=0)


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    tg = Telegram(os.environ["TG_BOT_TOKEN"], os.environ["TG_CHAT_ID"])
    state = load_state()
    try:
        {"check": run_check, "weekly": run_weekly, "test": run_test}[mode](tg, state)
    finally:
        save_state(state)


if __name__ == "__main__":
    main()
