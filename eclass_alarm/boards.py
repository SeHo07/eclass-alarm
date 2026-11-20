"""게시판(공지사항/학습자료실) 기반 과제 감지 + 질의응답 게시판 제출 확인.

예: 불교와인간은 과제를 '과목공지'에 안내하고 '질의응답'에 비밀글로 받는다.
- 공지/자료실 새 글 → 과제성 글이면 본문에서 마감 날짜 후보 추출
- 질의응답 게시판에서 내 이름으로 올라간 글 → 제목 키워드/날짜로 제출 여부 판정
"""
from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from .eclass import KST, _cmid_from_url

NOTICE_RE = re.compile(r"공지|announce|notice|자료|file", re.I)
QNA_RE = re.compile(r"질의|q\s*&\s*a|qna|질문|과제\s*제출", re.I)
TASK_RE = re.compile(r"과제|보고서|리포트|레포트|제출|업로드|감상|에세이|인증")

_DOW = r"(?:\s*\(\s*[월화수목금토일]\s*\))?"
_KDATE = r"(\d{1,2})\s*월\s*(\d{1,2})\s*일" + _DOW
_SDATE = r"(?<![\d/.:])(\d{1,2})\s*/\s*(\d{1,2})(?![\d/])" + _DOW
_TIME = r"(?:[\s,]*(?:(오전|오후)\s*)?(\d{1,2})(?:\s*:\s*(\d{2})|\s*시(?:\s*(\d{1,2})\s*분)?))?"
DATE_RE = re.compile(rf"(?:{_KDATE}|{_SDATE}){_TIME}")

DEADLINE_HINT = re.compile(r"기한|마감|제출|일시|기간|due", re.I)
UNTIL_HINT = re.compile(r"까지")
NOT_DEADLINE = re.compile(r"시험|중간고사|기말고사|수업\s*시간|휴강|대독|발표|범위|보강일")
STOP_TOKENS = {"학과", "이름", "성명", "학번", "형식", "제목", "학부", "전공"}


def classify(name: str) -> str | None:
    if QNA_RE.search(name):
        return "qna"
    if NOTICE_RE.search(name):
        return "notice"
    return None


def course_boards(course_html: str) -> list[tuple[str, str, str]]:
    soup = BeautifulSoup(course_html, "html.parser")
    out = []
    for li in soup.select("li.activity.modtype_ubboard"):
        cmid = (li.get("id") or "").replace("module-", "")
        el = li.select_one(".instancename")
        if el:
            hidden = el.select_one(".accesshide")
            if hidden:
                hidden.extract()
        name = el.get_text(" ", strip=True) if el else ""
        kind = classify(name)
        if cmid and kind:
            out.append((cmid, name, kind))
    return out


def parse_board_list(html: str) -> list[dict]:
    """게시판 목록 표 → [{bwid, title, writer, date(YYYY-MM-DD), url}]"""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table")
    if not table:
        return []
    heads = [th.get_text(strip=True) for th in table.select("thead th")]
    def col(*names):
        return next((i for i, h in enumerate(heads) if any(n in h for n in names)), None)
    ti, wi, di = col("제목", "Subject"), col("작성자", "Writer", "Author"), col("작성일", "Date")
    rows = []
    for tr in table.select("tbody tr"):
        tds = tr.find_all("td")
        if ti is None or len(tds) <= max(x for x in (ti, wi, di) if x is not None):
            continue
        a = tds[ti].select_one('a[href*="article.php"]')
        title = tds[ti].get_text(" ", strip=True)
        title = re.sub(r"\s*\[\d+\]\s*$", "", title)  # 댓글 수 제거
        bwid = None
        if a:
            m = re.search(r"bwid=(\d+)", a["href"])
            bwid = m.group(1) if m else None
        rows.append({
            "bwid": bwid,
            "title": title,
            "writer": tds[wi].get_text(strip=True) if wi is not None else "",
            "date": tds[di].get_text(strip=True) if di is not None else "",
            "url": a["href"] if a else None,
        })
    return rows


def parse_article(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    view = soup.select_one(".ubboard_view") or soup
    subject = view.select_one(".subject")
    content = view.select_one(".content")
    date_el = view.select_one(".date")
    posted = None
    if date_el:
        m = re.search(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", date_el.get_text())
        if m:
            posted = int(datetime.strptime(m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=KST).timestamp())
    return {
        "title": subject.get_text(" ", strip=True) if subject else "",
        "body": content.get_text("\n", strip=True) if content else view.get_text("\n", strip=True),
        "posted": posted,
    }


def is_task_article(title: str, body: str) -> bool:
    return bool(TASK_RE.search(title) or TASK_RE.search(body))


def _to_ts(month: int, day: int, hour: int, minute: int, posted: int) -> int | None:
    p = datetime.fromtimestamp(posted, KST)
    year = p.year + (1 if month < p.month - 3 else 0)
    if hour >= 24:
        hour, minute = 23, 59
    try:
        return int(datetime(year, month, day, hour, minute, tzinfo=KST).timestamp())
    except ValueError:
        return None


def extract_deadlines(body: str, posted: int) -> list[dict]:
    """본문에서 마감 날짜 후보. [{deadline, snippet}]"""
    text = re.sub(r"[ \t]+", " ", body)
    found: dict[int, dict] = {}
    for m in DATE_RE.finditer(text):
        g = m.groups()
        month, day = (g[0], g[1]) if g[0] else (g[2], g[3])
        month, day = int(month), int(day)
        if not (1 <= month <= 12 and 1 <= day <= 31):
            continue
        ampm, hh, mm, mm2 = g[4], g[5], g[6], g[7]
        before = text[max(0, m.start() - 25):m.start()]
        after = text[m.end():m.end() + 15]
        if not (UNTIL_HINT.search(after) or DEADLINE_HINT.search(before)):
            continue
        if NOT_DEADLINE.search(after) or (NOT_DEADLINE.search(before) and not DEADLINE_HINT.search(before)):
            continue
        if hh is not None:
            hour = int(hh) + (12 if ampm == "오후" and int(hh) < 12 else 0)
            minute = int(mm or mm2 or 0)
        else:
            hour, minute = 23, 59
        ts = _to_ts(month, day, hour, minute, posted)
        if ts is None or ts < posted - 86400:
            continue
        line_start = text.rfind("\n", 0, m.start()) + 1
        snippet = text[line_start:m.end() + 6].strip().replace("\n", " ")
        found.setdefault(ts, {"deadline": ts, "snippet": snippet[-80:]})
    return sorted(found.values(), key=lambda x: x["deadline"])


def title_keywords(body: str) -> list[str]:
    """공지에 적힌 '제출 글 제목 형식'에서 대표 키워드 추출 (예: '중간보고, 나의 아픔, 학과, 이름' → 중간보고)"""
    keys: list[str] = []
    for m in re.finditer(r"제목", body):
        window = body[m.start():m.start() + 120]
        for q in re.findall(r"['\"“‘\[]([^'\"”’\]]{2,60})['\"”’\]]", window):
            if not re.search(r"학과|이름|성명|학번", q):  # 제목 '형식' 템플릿만 사용
                continue
            toks = [t.strip() for t in re.split(r"[,\s\-·/_]+", q)]
            first = next((t for t in toks if len(t) >= 2 and t not in STOP_TOKENS), None)
            if first and first not in keys:  # 형식마다 첫 토큰만 대표로
                keys.append(first)
    return keys


def my_name(main_html: str, student_id: str) -> str | None:
    text = BeautifulSoup(main_html, "html.parser").get_text(" ")
    m = re.search(r"([가-힣A-Za-z]{2,10})\s*\(\s*" + re.escape(student_id) + r"\s*\)", text)
    return m.group(1) if m else None


def judge_done(tasks: list[dict], my_posts: list[dict]) -> None:
    """tasks[i]['done'] 갱신. 키워드가 제목에 들어간 내 글이 공지 이후에 있으면 제출.
    키워드가 없는 과제는 공지~마감+3일 사이에 올린, 다른 과제에 안 쓰인 내 글로 판정."""
    def day(ts):
        return datetime.fromtimestamp(ts, KST).strftime("%Y-%m-%d")
    used = set()
    for t in sorted(tasks, key=lambda t: not t.get("keywords")):
        start = day(t["posted"])
        end = day(t["deadline"] + 3 * 86400)
        hit = None
        for i, p in enumerate(my_posts):
            if p["date"] < start:
                continue
            if t.get("keywords"):
                if any(k in p["title"] for k in t["keywords"]):
                    hit = i
                    break
            elif i not in used and p["date"] <= end:
                hit = i
                break
        if hit is not None:
            used.add(hit)
        t["done"] = hit is not None
