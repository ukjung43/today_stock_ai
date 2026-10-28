# today_stock.ai

Threads 계정 @today_stock.ai 에 국장 빅이슈를 자동으로 올리는 봇. 사용자는 한국어로 소통하고 개발자가 아니므로, 설명은 쉬운 한국어로 하고 명령어는 그대로 실행할 수 있게 준다.

## 구조
- `bot/market.py` 시세 (Yahoo chart API), KRX 휴장일 판단
- `bot/news.py` RSS 헤드라인 (제목·링크만)
- `bot/writer.py` AI 팀: 리서처 → 작가 → (규칙 검사) → 편집장. 반려되면 작가가 최대 `max_attempts`번 다시 씀
- `prompts/researcher.md`, `prompts/writer.md`, `prompts/editor.md` 역할별 지침
- `bot/checks.py` 규칙 검사: 데이터에 없는 숫자, 부호, 금지어, 글자 수
- `bot/card.py` 1080x1350 카드 (상승 빨강, 하락 파랑)
- `bot/threads.py` Threads 공식 API
- `.github/workflows/post.yml` 08:00/16:00 KST 초안 → `threads` 환경 → 게시 (현재 승인 없이 자동. Required reviewers를 다시 넣으면 승인제)
- `config.toml` 시간대별 종목, 피드, 금지어, 역할별 effort

## 지켜야 할 것
- 종목 추천, 매수·매도 권유, 단정적 예측이 나올 수 있는 변경은 하지 않는다. 금지어와 편집장 기준을 약하게 만들지 않는다.
- 글의 숫자는 시세 데이터에서만 나온다. 모델이 숫자를 계산·생성하게 하지 않는다.
- 기사 본문을 가져오거나 저장하지 않는다 (제목과 링크만).
- `.env`, 토큰, API 키를 읽어서 출력하거나 커밋하지 않는다.
- Claude 모델은 `config.toml`의 `[claude] model` 하나만 쓴다.

## 명령
```bash
.venv\Scripts\python -m bot.main draft --slot close --no-ai --force --out out   # Claude 없이 미리보기
.venv\Scripts\python -m bot.main draft --slot morning --force --out out         # 실제 AI 팀 (ANTHROPIC_API_KEY 필요)
.venv\Scripts\python -m bot.main whoami                                         # Threads 토큰 확인
```
미리보기 결과는 `out/` (git 제외). `drafts/`는 GitHub Actions가 카드 이미지를 공개하려고 커밋하는 곳.

## 개발 역할 에이전트 (.claude/agents)
- `tone-editor` 말투·글 구성 담당. `prompts/*.md`만 고친다.
- `pipeline-dev` 코드·워크플로 담당.
- `qa-reviewer` 검수 담당. 고치지 않고 문제만 보고한다.
