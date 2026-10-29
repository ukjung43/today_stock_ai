# today_stock.ai

Threads 계정 [@today_stock.ai](https://www.threads.com/@today_stock.ai)에 매일 국장 빅이슈를 자동으로 정리해서 올리는 프로그램이에요.

- **장 전 (월~금 08:00):** 밤사이 미장, 반도체, 환율, 유가 → "오늘 국장 관전 포인트"
- **점심 장중 (월~금 12:00):** 오전장 코스피, 코스닥, 우리형들 → "오전장 한눈에 보기"
- **장 마감 (월~금 16:00):** 코스피, 코스닥, 우리형(삼전·하닉), 환율 → "오늘 국장 3줄 요약"
- 휴장일(주말, 공휴일, 대체공휴일, 12/31)에는 자동으로 쉬어요.

## 동작 순서

1. 시세를 가져와요 (Yahoo Finance) — 숫자는 여기서만 나와요.
2. 뉴스 헤드라인을 모아요 (연합뉴스, 한국경제 RSS) — 제목과 링크만 써요.
3. AI 팀이 글을 써요.
   - **리서처** (`prompts/researcher.md`): 헤드라인에서 오늘의 빅이슈 3~5개와 깨알 상식 용어를 골라요.
   - **작가** (`prompts/writer.md`): 브리핑으로 스레드 글, 첫 댓글, 카드 코멘트를 써요.
4. 검사해요.
   - **검사기** (`bot/checks.py`): 데이터에 없는 숫자, 틀린 부호, 금지어, 글자 수
   - **편집장** (`prompts/editor.md`): 지어낸 사실, 상승·하락 방향, 투자 권유, 말투
   - 걸리면 작가가 고쳐 쓰고, 3번 안에 통과 못 하면 올리지 않아요.
5. 이미지 카드를 그려요 (`drafts/날짜-slot/card.png`).
6. **승인하면** Threads에 이미지와 글을 올리고, 첫 댓글에 사이트 링크를 달아요.

## 내 PC에서 미리보기

```bash
.venv\Scripts\python -m bot.main draft --slot close --no-ai --force --out out
```

`--no-ai`는 Claude 없이 템플릿으로 써요. `.env`에 `ANTHROPIC_API_KEY`를 넣고 `--no-ai`를 빼면 실제 글이 나와요. 결과는 `out/` 폴더에 생겨요.

## 처음 한 번 설정

### 1. Threads API 토큰
1. [Meta for Developers](https://developers.facebook.com/)에 가입하고 **앱 만들기**를 눌러요. 사용 사례는 **Threads API 액세스**를 골라요.
2. 앱 설정의 **역할 → Threads 테스터**에 `today_stock.ai`를 추가해요.
3. Threads 앱에서 **설정 → 계정 → 웹사이트 권한 → 초대**에서 수락해요.
4. 권한 `threads_basic`, `threads_content_publish`, `threads_manage_replies`로 토큰을 만들고, **장기 토큰(60일)**으로 바꿔요.
5. 토큰은 `.env`의 `THREADS_ACCESS_TOKEN=`에 넣고 아래 명령으로 확인해요. `@today_stock.ai`가 나오면 성공이에요.
   ```bash
   .venv\Scripts\python -m bot.main whoami
   ```

### 2. Claude API 키
[console.anthropic.com](https://console.anthropic.com)에서 키를 만들어 `.env`의 `ANTHROPIC_API_KEY=`에 넣어요.

### 3. GitHub 저장소 (자동 실행용)
- 저장소는 **공개(public)**로 만들어요. Threads API가 이미지를 공개 주소로만 받아서, 카드 이미지를 이 저장소에서 바로 가져가요. 키와 토큰은 코드가 아니라 GitHub Secrets에 들어가서 공개되지 않아요.
- **Settings → Secrets and variables → Actions**에 추가할 것:
  - `ANTHROPIC_API_KEY`
  - `THREADS_ACCESS_TOKEN`
  - `GH_PAT` — 토큰 자동 갱신용. Fine-grained token, 이 저장소만, 권한 **Secrets: Read and write**
- **Settings → Environments → New environment → `threads`** → **Required reviewers**에 내 계정을 넣어요. 그러면 매번 승인해야 올라가요. 나중에 이 설정만 끄면 완전 자동이 돼요.

### 4. 승인하는 법
초안이 만들어지면 GitHub에서 메일이나 GitHub 앱 알림이 와요. **Actions** 탭에서 해당 실행을 열면 글과 카드 미리보기가 보이고, **Review deployments → Approve**를 누르면 올라가요. 3시간 안에 승인하지 않으면 그 글은 버려요(`config.toml`의 `max_draft_age_hours`).

## 바꾸고 싶을 때
- **말투, 글 구성:** `prompts/writer.md` (검수 기준은 `prompts/editor.md`, 이슈 고르는 기준은 `prompts/researcher.md`)
- **역할별 생각 깊이:** `config.toml`의 `[roles.*]`
- **시간, 종목, 뉴스 출처, 금지어, 링크 주소:** `config.toml` (시간은 `.github/workflows/post.yml`의 cron, UTC 기준)
- **마스코트:** `assets/mascot.png`에 배경이 투명한 PNG를 넣으면 카드 오른쪽 아래에 들어가요.

## 주의
- 종목 추천은 절대 안 해요. 금지어 필터로 막혀 있어요.
- 기사 본문은 가져오지 않고, 제목을 요약만 해요.
- 시세는 Yahoo Finance의 비공식 데이터라 가끔 늦거나 막힐 수 있어요. 그러면 그 회차는 실패로 끝나고 아무것도 올라가지 않아요.
