import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eclass_alarm import boards as B  # noqa: E402
from eclass_alarm.eclass import _parse_kst  # noqa: E402

MIDTERM = """안녕하세요?중간보고서 과제를 다음과 같이 공지합니다. 1. 제목:"나의 아픔"2. 내용: 자신이 평소에 느꼈던 불편함을 에세이의 형식으로 작성합니다. 3. 발표: 동보고서 중 전체 학우들과 공유했으면 좋겠다고 생각되는 보고서는 강사의 선정을 거쳐 12월7일(월) 수업시간에 대독할 예정입니다. 4. 기한: 11월 22일(일) 24:00까지5. 분량: A4지 1000자 혹은 1장 이상의 분량으로 작성해 주세요.6. 작성형식:1) [게시판]-[질의응답]란에 '비밀글'의 형식으로 올려주세요. 3) 작성 시 [질의응답]란의 제목은 '중간보고, 나의 아픔, 학과, 이름'의 형식으로 통일해 주세요. 7. 기말고사와의 연계: 중간보고서에서 다룬 내용을 바탕으로 기말고사를 제출하겠습니다."""
EXAM = """안녕하세요?오는 10월 26일(월)에는 중간고사가 예정되어 있습니다. 장소: 동일한 강의실시간: 13:00-13:30범위: 10월19일(월) 수업 범위까지환절기 건강 조심하시고"""
MAKEUP = """지난 10월5일은 개천절 대체공휴일이었습니다. 이에 본 수업에서는 다음과 같이 과제제출을 통해 보강을 대체하고자 합니다. 2: 제출 위치: [게시판]-[질의응답]란에 올려주세요. 4. 기한: 11월 8일(일) 24:00까지 제출해 주세요. 5. 제목: [질의응답]란에 보고서 제출시 [보강과제-다르마-학과-이름]의 형식으로 제목을 작성해 주세요."""
MUSEUM = """다음과 같이 과제를 공지합니다.1. 국립중앙박물관의 "사유의 방"을 방문하고 인증샷과 200자평을 남김니다.- 일시: 10월 11일(일) 24:00시 까지입니다.- 업로드 형식: 제목에 "국립박물관 인증샷, 학과, 성명" , "국립박물관 200자평, 학과, 성명" 으로 명시합니다. 2. 동영상 감상평 -일시: 10/18(일) 23:59까지"""

P_MID = _parse_kst("2026-10-15 13:07")
P_EXAM = _parse_kst("2026-10-15 12:22")
P_MAKEUP = _parse_kst("2026-10-12 11:37")
P_MUSEUM = _parse_kst("2026-09-21 10:49")


def test_extract_deadlines():
    d = B.extract_deadlines(MIDTERM, P_MID)
    assert [x["deadline"] for x in d] == [_parse_kst("2026-11-22 23:59")]  # 12/7 대독 제외
    assert B.extract_deadlines(EXAM, P_EXAM) == []
    assert not B.is_task_article("중간고사 관련 공지", EXAM)
    assert [x["deadline"] for x in B.extract_deadlines(MAKEUP, P_MAKEUP)] == [_parse_kst("2026-11-08 23:59")]
    assert [x["deadline"] for x in B.extract_deadlines(MUSEUM, P_MUSEUM)] == [
        _parse_kst("2026-10-11 23:59"), _parse_kst("2026-10-18 23:59")]


def test_title_keywords():
    assert B.title_keywords(MIDTERM) == ["중간보고"]
    assert B.title_keywords(MAKEUP) == ["보강과제"]
    assert B.title_keywords(MUSEUM) == ["국립박물관"]


def test_judge_done():
    mine = [
        {"title": "보강과제-다르마-컴퓨터AI학부-이세호", "date": "2026-11-09"},
        {"title": "국립박물관 인증샷 및 200자평, 컴퓨터·AI학부, 이세호", "date": "2026-10-11"},
    ]
    mid = {"posted": P_MID, "deadline": _parse_kst("2026-11-22 23:59"), "keywords": ["중간보고"]}
    mk = {"posted": P_MAKEUP, "deadline": _parse_kst("2026-11-08 23:59"), "keywords": ["보강과제"]}
    B.judge_done([mid, mk], mine)
    assert mid["done"] is False and mk["done"] is True
    mine.append({"title": "중간보고, 나의 아픔, 컴퓨터AI학부, 이세호", "date": "2026-11-21"})
    B.judge_done([mid], mine)
    assert mid["done"] is True
    # 키워드 없는 과제: 기간 내 남는 글로 판정
    nk = {"posted": P_MUSEUM, "deadline": _parse_kst("2026-10-18 23:59"), "keywords": []}
    B.judge_done([nk], [{"title": "감상평", "date": "2026-10-17"}])
    assert nk["done"] is True


LIST = """<table><thead><tr><th>번호</th><th>제목</th><th>작성자</th><th>작성일</th><th>조회수</th></tr></thead><tbody>
<tr><td class="tcenter">161</td><td><span class="secret">비밀글입니다.</span></td><td class="tcenter">조윤정</td><td class="tcenter">2026-11-20</td><td class="tcenter">1</td></tr>
<tr><td class="tcenter">145</td><td><a href="https://eclass.dongguk.edu/mod/ubboard/article.php?id=157461&amp;bwid=220001">보강과제-다르마-컴퓨터AI학부-이세호</a> [1]</td><td class="tcenter">이세호</td><td class="tcenter">2026-11-09</td><td class="tcenter">15</td></tr>
</tbody></table>"""

ARTICLE = """<div class="ubboard_view"><div class="well"><div class="subject">중간보고서 관련 공지</div>
<div class="info"><div class="writer">작성자: 권택규</div><div class="date">작성일: 2026-10-15 13:07</div></div></div>
<div class="content"><div class="text_to_html">안녕하세요? 4. 기한: 11월 22일(일) 24:00까지</div></div></div>"""

COURSE = """<ul><li class="activity ubboard modtype_ubboard" id="module-157460"><span class="instancename">Class Announcements<span class="accesshide"> 게시판</span></span></li>
<li class="activity ubboard modtype_ubboard" id="module-157461"><span class="instancename">Class Q&amp;A</span></li>
<li class="activity ubboard modtype_ubboard" id="module-150586"><span class="instancename">학습자료실</span></li>
<li class="activity ubboard modtype_ubboard" id="module-150585"><span class="instancename">질의응답</span></li></ul>"""


def test_html_parsers():
    rows = B.parse_board_list(LIST)
    assert rows[0]["bwid"] is None and rows[0]["writer"] == "조윤정"
    assert rows[1] == {"bwid": "220001", "title": "보강과제-다르마-컴퓨터AI학부-이세호", "writer": "이세호",
                       "date": "2026-11-09", "url": "https://eclass.dongguk.edu/mod/ubboard/article.php?id=157461&bwid=220001"}
    a = B.parse_article(ARTICLE)
    assert a["title"] == "중간보고서 관련 공지" and a["posted"] == P_MID and "11월 22일" in a["body"]
    assert B.course_boards(COURSE) == [("157460", "Class Announcements", "notice"), ("157461", "Class Q&A", "qna"),
                                       ("150586", "학습자료실", "notice"), ("150585", "질의응답", "qna")]
    assert B.my_name("<div>최종 접속IP : 1.2.3.4이세호 ( 2026112503 )</div>", "2026112503") == "이세호"


REAL_ARTICLE = """<div class="ubboard_view"><div class="well"><div class="subject"><h3>과제공지1</h3></div>
<div class="info"><div class="writer"><span class="title">작성자</span>: 권택규</div>
<div class="date"><span class="title">작성일</span>: 2026-09-21 10:49
(수정일: 2026-09-21 10:53)</div></div>
<div class="content"><div class="text_to_html"><p>다음과 같이 과제를 공지합니다.</p><p>-&nbsp; 일시: 10월 11일(일) 24:00시 까지입니다.</p>
<p>- 업로드 형식: 제목에 "국립박물관 인증샷, 학과, 성명" , "국립박물관 200자평, 학과, 성명" 으로 명시합니다.&nbsp;</p>
<p><span>-일시:&nbsp;10월 11일(일) 24:00시 까지입니다.</span></p><p><span>- 업로드 형식:&nbsp; 제목에 "붓다 감상평, 학과 성명"을 명시합니다.&nbsp;</span></p>
<br>4. 기한:&nbsp; 11월 22일(일)&nbsp; 24:00까지<br></div></div></div>"""


def test_real_article_shape():
    a = B.parse_article(REAL_ARTICLE)
    assert a["title"] == "과제공지1" and a["posted"] == _parse_kst("2026-09-21 10:49")
    d = [x["deadline"] for x in B.extract_deadlines(a["body"], a["posted"])]
    assert d == [_parse_kst("2026-10-11 23:59"), _parse_kst("2026-11-22 23:59")]
    assert B.title_keywords(a["body"]) == ["국립박물관", "붓다"]
