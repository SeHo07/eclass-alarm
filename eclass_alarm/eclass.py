"""동국대 이클래스(Moodle/Coursemos) 수집기.

수집 경로 (docs/STRUCTURE.md 참고):
1. 강의실 페이지(/course/view.php?id=N)의 li.activity
   - 기간이 표시된 활동(동영상 등): 마감 시각 + 이수 여부(completion 아이콘)
2. Moodle AJAX API core_calendar_get_action_events_by_timesort
   - 아직 안 한(actionable) 과제/퀴즈/설문 등의 마감 시각
두 결과를 cmid 기준으로 합치고, 강의실 페이지에서 완료로 표시된 건 제외한다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://eclass.dongguk.edu"
KST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"

# 마감으로 취급할 캘린더 이벤트 종류 (open/start 같은 시작 이벤트는 제외)
DEADLINE_EVENT_TYPES = {"due", "close", "stop", "expectcompletionon"}

TYPE_LABEL = {
    "assign": "과제",
    "vod": "동영상",
    "quiz": "퀴즈",
    "feedback": "설문",
    "forum": "토론",
    "ubboard": "게시판",
}

_DT = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?)"
_RANGE_RE = re.compile(_DT + r"\s*~\s*" + _DT)
_LATE_RE = re.compile(r"지각\s*:\s*" + _DT)


class LoginError(Exception):
    pass


@dataclass
class Item:
    cmid: str
    course: str
    type: str          # modulename (assign, vod, quiz ...)
    name: str
    deadline: int      # unix seconds
    done: bool
    url: str
    late_deadline: int | None = None

    @property
    def label(self) -> str:
        return TYPE_LABEL.get(self.type, self.type)

    @property
    def deadline_dt(self) -> datetime:
        return datetime.fromtimestamp(self.deadline, KST)


def _parse_kst(s: str) -> int:
    fmt = "%Y-%m-%d %H:%M:%S" if s.count(":") == 2 else "%Y-%m-%d %H:%M"
    return int(datetime.strptime(s, fmt).replace(tzinfo=KST).timestamp())


def _cmid_from_url(url: str) -> str | None:
    q = parse_qs(urlparse(url.replace("&amp;", "&")).query)
    return q.get("id", [None])[0]


def _short_course_name(text: str) -> str:
    """'교과\\n기술창조와특허 - 5분반 [..] (2학기)\\n교수' -> '기술창조와특허'"""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for l in lines:
        if " - " in l:
            return l.split(" - ")[0].strip()
    for l in lines:
        if l not in ("교과", "자율강좌", "비교과"):
            return l
    return text.strip()


# ---------------------------------------------------------------- 파서 (네트워크 없음, 테스트 가능)

def parse_courses(main_html: str) -> dict[str, str]:
    soup = BeautifulSoup(main_html, "html.parser")
    courses: dict[str, str] = {}
    for a in soup.select('a[href*="course/view.php?id="]'):
        cid = _cmid_from_url(a["href"])
        name = _short_course_name(a.get_text("\n"))
        if cid and cid not in courses and name:
            courses[cid] = name
    return courses


def parse_course_page(html: str, course: str) -> tuple[list[Item], dict[str, bool]]:
    """강의실 페이지 -> (기간이 있는 활동 목록, cmid별 완료 여부)"""
    soup = BeautifulSoup(html, "html.parser")
    items: list[Item] = []
    completion: dict[str, bool] = {}
    for li in soup.select("li.activity"):
        cmid = (li.get("id") or "").replace("module-", "")
        if not cmid:
            continue
        m = re.search(r"modtype_(\w+)", " ".join(li.get("class", [])))
        mtype = m.group(1) if m else "unknown"

        done_icon = li.select_one('img[src*="completion-auto-y"], img[src*="completion-manual-y"], img[src*="completion-auto-pass"]')
        cstr = li.select_one(".completionstr")
        done = bool(done_icon) or (cstr is not None and "이수완료" in cstr.get_text())
        has_tracking = bool(li.select_one(".autocompletion, .togglecompletion, .completionstr"))
        if has_tracking:
            completion[cmid] = done

        opt = li.select_one(".displayoptions")
        if not opt:
            continue
        text = opt.get_text(" ", strip=True)
        rng = _RANGE_RE.search(text)
        if not rng:
            continue
        name_el = li.select_one(".instancename")
        if name_el:
            hidden = name_el.select_one(".accesshide")
            if hidden:
                hidden.extract()
            name = name_el.get_text(" ", strip=True)
        else:
            name = mtype
        late = _LATE_RE.search(text)
        a = li.select_one("a[href]")
        items.append(Item(
            cmid=cmid, course=course, type=mtype, name=name,
            deadline=_parse_kst(rng.group(2)), done=done,
            url=(a["href"] if a else f"{BASE}/course/view.php"),
            late_deadline=_parse_kst(late.group(1)) if late else None,
        ))
    return items, completion


def parse_action_events(events: list[dict]) -> list[Item]:
    items = []
    for e in events:
        action = e.get("action") or {}
        if not action.get("actionable", True):
            continue
        if e.get("eventtype") not in DEADLINE_EVENT_TYPES:
            continue
        cmid = _cmid_from_url(e.get("url", "")) or f"ev{e.get('id')}"
        name = re.sub(r"\s*(is due|마감|종료|: Progress stop)$", "", e.get("name", "")).strip()
        course = e.get("course") or {}
        items.append(Item(
            cmid=cmid,
            course=_short_course_name(course.get("fullname", "")),
            type=e.get("modulename") or "event",
            name=name,
            deadline=int(e["timesort"]),
            done=False,
            url=e.get("url", BASE),
        ))
    return items


def merge(page_items: list[Item], api_items: list[Item], completion: dict[str, bool]) -> list[Item]:
    by_cmid: dict[str, Item] = {}
    for it in page_items:
        by_cmid[it.cmid] = it
    for it in api_items:
        if it.cmid in by_cmid:
            continue  # 강의실 페이지 정보(이수 여부 포함)가 더 정확
        if completion.get(it.cmid):
            it.done = True
        by_cmid[it.cmid] = it
    return sorted(by_cmid.values(), key=lambda i: i.deadline)


# ---------------------------------------------------------------- 네트워크 클라이언트

class EclassClient:
    def __init__(self, username: str, password: str, timeout: int = 20):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.timeout = timeout
        self.username = username
        self.password = password
        self.sesskey: str | None = None
        self.main_html = ""

    def login(self) -> None:
        self.s.get(f"{BASE}/login/index.php", timeout=self.timeout)
        r = self.s.post(
            f"{BASE}/login/index.php",
            data={"username": self.username, "password": self.password},
            timeout=self.timeout,
        )
        r = self.s.get(f"{BASE}/", timeout=self.timeout)
        m = re.search(r'"sesskey":"(\w+)"', r.text)
        if not m or 'name="password"' in r.text:
            raise LoginError("이클래스 로그인 실패 (아이디/비번 또는 로그인 방식 변경 확인)")
        self.sesskey = m.group(1)
        self.main_html = r.text

    def _ajax(self, method: str, args: dict) -> dict:
        r = self.s.post(
            f"{BASE}/lib/ajax/service.php",
            params={"sesskey": self.sesskey, "info": method},
            data=json.dumps([{"index": 0, "methodname": method, "args": args}]),
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        res = r.json()[0]
        if res.get("error"):
            raise RuntimeError(f"{method} 실패: {res.get('exception')}")
        return res["data"]

    def collect(self) -> list[Item]:
        if not self.sesskey:
            self.login()
        courses = parse_courses(self.main_html)
        page_items: list[Item] = []
        completion: dict[str, bool] = {}
        for cid, cname in courses.items():
            html = self.s.get(f"{BASE}/course/view.php", params={"id": cid}, timeout=self.timeout).text
            its, comp = parse_course_page(html, cname)
            page_items += its
            completion.update(comp)

        now = int(datetime.now(KST).timestamp())
        events: list[dict] = []
        after = None
        for _ in range(5):  # 페이지네이션 (50개씩)
            args = {"timesortfrom": now - 86400, "limitnum": 50}
            if after:
                args["aftereventid"] = after
            data = self._ajax("core_calendar_get_action_events_by_timesort", args)
            batch = data.get("events", [])
            events += batch
            if len(batch) < 50:
                break
            after = batch[-1]["id"]
        return merge(page_items, parse_action_events(events), completion)
