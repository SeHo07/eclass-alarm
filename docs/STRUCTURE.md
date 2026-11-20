# 이클래스 구조 분석 (2026-11-19)

동국대 이클래스(eclass.dongguk.edu)는 **Moodle + Coursemos(theme coursemosv2)** 기반.

## 로그인
- `POST /login/index.php` 폼: `username`, `password` (hidden 토큰 없음)
- 로그인 후 메인 HTML에 `"sesskey":"..."` → AJAX 호출에 사용

## 데이터 소스
| 무엇 | 어디서 | 비고 |
|---|---|---|
| 수강 강좌 목록 | 메인(`/`)의 `a[href*="course/view.php?id="]` | 교과 + 자율강좌 |
| 동영상(vod) 기간·이수 | `/course/view.php?id=N` 의 `li.activity.modtype_vod` | `.displayoptions` 에 `시작 ~ 마감 (지각 : …)`, 완료 시 `img[src*=completion-auto-y]` / `.completionstr`=이수완료 |
| 미제출 과제·퀴즈 등 마감 | `POST /lib/ajax/service.php?sesskey=..` `core_calendar_get_action_events_by_timesort` | 제출/완료한 항목은 actionable 이벤트에서 빠짐. eventtype: due/close/stop |
| 과제 제출 상태(참고) | `/mod/assign/view.php?id=CMID` `.submissionstatustable` | "제출 완료"/"제출 안 함" |
| 동영상 출석부(참고) | `/report/ubcompletion/user_progress_a2.php?id=N` | 요구시간/학습시간/O▲X |

## 판정 규칙
- 항목 키 = cmid (`module-141500`, `view.php?id=141500`)
- 강의실 페이지 정보 우선, API 항목 중 페이지에서 완료로 표시된 건 done
- 오프라인 출석은 이클래스에 없으므로 대상 아님 (온라인 출석 = 동영상 이수)

## 게시판 과제 (2026-11-20 추가)
일부 과목(예: 불교와인간)은 과제를 **공지 게시판**에 안내하고 **질의응답 게시판**에 비밀글로 제출받음.
- 강의실 `li.activity.modtype_ubboard` 이름으로 분류: 공지/자료(Announcements, Files) → 과제 감지, 질의응답(Q&A) → 제출 확인
- 목록 `/mod/ubboard/view.php?id=CMID&page=N` (table: 번호/제목/작성자/작성일/조회수). 남의 비밀글은 제목이 "비밀글입니다."이고 내 글은 제목이 보임
- 글 `/mod/ubboard/article.php?id=CMID&bwid=N`: `.ubboard_view .subject h3`, `.date`(작성일), `.content .text_to_html`
- 마감 추출: "11월 22일(일) 24:00까지", "11/25 23:59" 등 + 앞뒤 문맥(기한/마감/제출/까지). 시험·대독·범위 문맥은 제외
- 제출 판정: 공지의 제목 형식 템플릿('중간보고, 나의 아픔, 학과, 이름')에서 첫 단어를 키워드로 → 공지 이후 내 글 제목에 포함되면 제출
- 오탐을 막으려고 후보는 텔레그램 [일정 추가]/[무시] 버튼으로 확인받음
