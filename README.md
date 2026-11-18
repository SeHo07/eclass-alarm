# eclass-alarm

동국대 이클래스 과제·동영상·퀴즈 마감 알림 텔레그램 봇 (GitHub Actions, 무료)

- 10분마다 확인 → 미완료 항목 **마감 3시간 전 / 1시간 전**에 `[확인]` 누를 때까지 1분 간격 반복 알림
- 매주 월요일 아침 주간 일정 정리
- 봇 명령어: `/list` 미완료 목록, `/week` 이번 주 일정, `확인` 울리는 알림 전부 정지, `/pause 3h`·`/pause 2d`·`/pause` 일시정지, `/resume` 재개

## 설정
Settings → Secrets and variables → Actions: `ECLASS_ID`, `ECLASS_PW`, `TG_BOT_TOKEN`, `TG_CHAT_ID`

테스트: Actions → check → Run workflow (mode: `test`)

구조는 [docs/STRUCTURE.md](docs/STRUCTURE.md) 참고.
