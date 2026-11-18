"""네트워크 없이 파서/알림 로직 검증. 실행: python -m pytest -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
from eclass_alarm.eclass import (_parse_kst, merge, parse_action_events,  # noqa: E402
                                 parse_course_page, parse_courses)

VOD_DONE = """<li class="activity vod modtype_vod " id="module-141477"><div class="activityinstance">
<a href="https://eclass.dongguk.edu/mod/vod/view.php?id=141477"><span class="instancename">1주차 1차시 강의1<span class="accesshide "> 동영상</span></span></a>
<span class="displayoptions"><span class="text-ubstrap">&nbsp;2026-09-01 00:00:00 ~ 2026-09-07 23:59:59 <span class="text-late">(지각 : 2026-09-14 23:59:59)</span></span></span></div>
<span class="actions"><span class="completionstr mr-2">이수완료</span><span class="autocompletion"><img class="icon" src="https://eclass.dongguk.edu/theme/image.php/coursemosv2/core/1/i/completion-auto-y"></span></span></li>"""

VOD_TODO = """<li class="activity vod modtype_vod " id="module-141500"><div class="activityinstance">
<a href="https://eclass.dongguk.edu/mod/vod/view.php?id=141500"><span class="instancename">13주차 1차시 강의1<span class="accesshide "> 동영상</span></span></a>
<span class="displayoptions"><span class="text-ubstrap">&nbsp;2026-11-24 00:00:00 ~ 2026-11-30 23:59:59 <span class="text-late">(지각 : 2026-12-07 23:59:59)</span></span></span></div>
<span class="actions"><span class="completionstr mr-2"></span><span class="autocompletion"><img class="icon" src="https://eclass.dongguk.edu/theme/image.php/coursemosv2/core/1/i/completion-auto-n"></span></span></li>"""

ASSIGN_DONE = """<li class="activity assign modtype_assign " id="module-176179"><a href="https://eclass.dongguk.edu/mod/assign/view.php?id=176179"><span class="instancename">11주차 과제</span></a>
<span class="actions"><span class="completionstr mr-2">이수완료</span><span class="autocompletion"><img src="x/i/completion-auto-y"></span></span></li>"""

MAIN = """<a href="https://eclass.dongguk.edu/course/view.php?id=59725">교과
기업가정신과 리더십 - 2분반 [창업교육센터] (2학기)
이창영</a><a href="https://eclass.dongguk.edu/course/view.php?id=55780">자율강좌
[학생]2026_인권존중교육(한국어)
자율강좌관리자</a>"""


def ev(eid, cmid, name, ts, mod="assign", etype="due", actionable=True):
    return {"id": eid, "name": name, "modulename": mod, "eventtype": etype, "timesort": ts,
            "url": f"https://eclass.dongguk.edu/mod/{mod}/view.php?id={cmid}",
            "course": {"fullname": "공학선형대수학"},
            "action": {"actionable": actionable}}


def test_parse_courses():
    c = parse_courses(MAIN)
    assert c == {"59725": "기업가정신과 리더십", "55780": "[학생]2026_인권존중교육(한국어)"}


def test_parse_course_page():
    items, comp = parse_course_page(f"<ul>{VOD_DONE}{VOD_TODO}{ASSIGN_DONE}</ul>", "기업가정신")
    assert [i.cmid for i in items] == ["141477", "141500"]
    assert items[0].done and not items[1].done
    assert items[1].name == "13주차 1차시 강의1"
    assert items[1].deadline == _parse_kst("2026-11-30 23:59:59")
    assert items[1].late_deadline == _parse_kst("2026-12-07 23:59:59")
    assert comp == {"141477": True, "141500": False, "176179": True}


def test_action_events_and_merge():
    ts = _parse_kst("2026-11-25 23:59")
    api = parse_action_events([
        ev(1, 177322, "12주차 과제 is due", ts),
        ev(2, 176179, "11주차 과제 is due", ts),                      # 페이지에선 완료 → done
        ev(3, 141500, "13주차 : Progress stop", ts, "vod", "stop"),  # 페이지 항목과 중복
        ev(4, 999, "퀴즈 열림", ts, "quiz", "open"),                  # 시작 이벤트 제외
        ev(5, 998, "제출 불가", ts, actionable=False),               # actionable 아님 제외
    ])
    assert [i.cmid for i in api] == ["177322", "176179", "141500"]
    assert api[0].name == "12주차 과제"
    page, comp = parse_course_page(f"<ul>{VOD_TODO}{ASSIGN_DONE}</ul>", "x")
    merged = {i.cmid: i for i in merge(page, api, comp)}
    assert set(merged) == {"177322", "176179", "141500"}
    assert merged["176179"].done and not merged["177322"].done
    assert merged["141500"].course == "x"  # 페이지 정보 우선


def _item(cmid, left_sec, done=False, now=1_800_000_000):
    from eclass_alarm.eclass import Item
    return Item(cmid=cmid, course="c", type="assign", name=f"n{cmid}", deadline=now + left_sec, done=done, url="u")


def test_due_alerts_levels_and_ack():
    now = 1_800_000_000
    items = [_item("a", 2 * 3600, now=now), _item("b", 30 * 60, now=now), _item("c", 5 * 3600, now=now),
             _item("d", 20 * 60, done=True, now=now), _item("e", -60, now=now)]
    got = {(i.cmid, lvl) for i, lvl, _ in main.due_alerts(items, {}, now)}
    assert got == {("a", 1), ("b", 2)}
    # 3시간 알림을 확인해도 1시간 알림은 다시 울려야 함
    got = {(i.cmid, lvl) for i, lvl, _ in main.due_alerts(items, {"a:1": 1, "b:1": 1}, now)}
    assert got == {("a", 1), ("b", 2)} - {("a", 1)}
    got = {(i.cmid, lvl) for i, lvl, _ in main.due_alerts(items, {"b:2": 1}, now)}
    assert got == {("a", 1)}


class FakeTG:
    chat_id = "1"

    def __init__(self, ups):
        self.ups, self.sent, self.edited = ups, [], []

    def updates(self, offset, wait=0):
        u, self.ups = self.ups, []
        return u

    def send(self, text, buttons=None):
        self.sent.append(text)
        return len(self.sent)

    def edit(self, mid, text):
        self.edited.append((mid, text))

    def answer_callback(self, cid, text=""):
        pass


def test_handle_ack_button_and_word():
    now = 1_800_000_000
    it = _item("a", 1800, now=now)
    pending = {"a:2": {"item": it, "msg": 7}, "b:1": {"item": _item("b", 9000, now=now), "msg": 8}}
    state = {}
    tg = FakeTG([{"update_id": 10, "callback_query": {"id": "x", "data": "ack:a:2",
                                                      "message": {"message_id": 7, "chat": {"id": 1}}}}])
    main.handle_updates(tg, state, [it], pending)
    assert "a:2" in state["acked"] and "a:2" not in pending and state["tg_offset"] == 11
    tg.ups = [{"update_id": 11, "message": {"chat": {"id": 1}, "text": "확인"}}]
    main.handle_updates(tg, state, [it], pending)
    assert not pending and "b:1" in state["acked"]
    # 다른 사람이 보낸 메시지는 무시
    tg.ups = [{"update_id": 12, "message": {"chat": {"id": 999}, "text": "/list"}}]
    n = len(tg.sent)
    main.handle_updates(tg, state, [it], {})
    assert len(tg.sent) == n


def test_list_text():
    now = 1_800_000_000
    txt = main.list_text([_item("a", 3600, now=now), _item("b", 7200, done=True, now=now)], now)
    assert "⬜" in txt and "✅" in txt and "미완료 1개 / 전체 2개" in txt


def test_pause_and_resume():
    now = 1_800_000_000
    assert main.parse_pause("/pause", now) == float("inf")
    assert main.parse_pause("/pause 3h", now) == now + 3 * 3600
    assert main.parse_pause("/pause 2d", now) == now + 2 * 86400
    assert main.parse_pause("일시정지 5", now) == now + 5 * 3600
    state = {}
    tg = FakeTG([{"update_id": 1, "message": {"chat": {"id": 1}, "text": "/pause 2h"}}])
    main.handle_updates(tg, state, [], {})
    assert state["paused_until"] > 0
    assert main.is_paused({"paused_until": now + 10}, now)
    st = {"paused_until": now - 1}
    assert not main.is_paused(st, now) and "paused_until" not in st
    tg.ups = [{"update_id": 2, "message": {"chat": {"id": 1}, "text": "/resume"}}]
    main.handle_updates(tg, state, [], {})
    assert "paused_until" not in state
    # 무기한 정지도 JSON 저장/복원 가능
    import json
    assert json.loads(json.dumps({"p": float("inf")}))["p"] == float("inf")
