# eclass-alarm TODO

- [x] 이클래스 구조 분석 (docs/STRUCTURE.md)
- [x] 수집기: 강좌/동영상/과제·퀴즈 마감 + 완료 여부
- [x] 텔레그램 알림: 3시간/1시간 전, [확인] 누를 때까지 1분 간격 반복
- [x] 명령어 /list /week, '확인' 텍스트로 전체 정지
- [x] 주간 요약 (월 07:53 KST)
- [x] GitHub Actions (10분 cron, 상태는 actions cache, keepalive)
- [x] 오프라인 단위 테스트 (pytest)
- [ ] Secrets 등록 후 Actions에서 test 모드 실행 → 실제 로그인/발송 검증
- [x] 로그인 최소화: 미완료 마감 3시간 이내일 때만 10분 간격, 평소엔 3시간마다 + 매번 로그아웃
- [x] /hw /att 명령
- [x] 게시판(공지·자료실) 과제 감지 + 질의응답 제출 확인 (확인 버튼)
- [ ] cron-job.org 외부 트리거 (세호 PAT 필요)
- [ ] 실제 알림 1회 관찰 후 간격 조정

## 리뷰
- 해외(GitHub 러너) IP에서 이클래스 접속이 막히면 → 국내 VM 또는 대안 필요
