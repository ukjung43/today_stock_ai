# Claude Code가 직접 글을 쓰고 올리는 순서

2026-11-05부터 글은 Claude API 팀 대신 사장님 PC의 Claude Code 예약 작업이 써요. 예약 작업은 슬롯 이름 하나(morning / lunch / afterwork / evening)를 받아서 아래 순서를 그대로 따라요. 저장소 위치는 `C:\Users\jjww3\Documents\today_stock_ai` 예요.

| 슬롯 | 예약 (한국 시간, 월~금) | 늦으면 건너뛰는 시각 |
|---|---|---|
| morning (장 전) | 08:00 | 09:30 |
| lunch (점심 장중) | 12:00 | 13:30 |
| afterwork (퇴근길) | 18:30 | 20:00 |
| evening (밤 미장) | 22:00 | 23:30 |

## 지켜야 할 것
- `.env`, 토큰, API 키를 읽어서 출력하거나 커밋하지 않는다. 명령은 `.env`를 알아서 읽는다.
- 종목 추천, 매수·매도 권유, 오를지 내릴지 단정하는 말은 쓰지 않는다.
- 숫자는 `market_data`의 `price_text`, `change_text`를 글자 그대로, 헤드라인 숫자는 적힌 그대로만 쓴다. 단위를 바꾸거나 계산하지 않는다 (예: "$1.4 billion"을 "14억달러"로 바꾸지 않는다. 필요 없으면 숫자를 뺀다).
- 기사 본문을 열지 않는다. 헤드라인 제목만 근거로 쓴다.
- 확신이 안 서면 올리지 않고 이유를 보고한다. 안 올리는 게 틀린 글을 올리는 것보다 낫다.

## 순서
1. **시간 확인.** 지금 시각이 위 표의 "늦으면 건너뛰는 시각"을 넘었으면 (PC가 꺼져 있다가 늦게 실행된 경우) 아무것도 하지 말고 "늦어서 건너뜀"이라고 보고하고 끝낸다.
2. **최신으로.** `git pull -q --rebase --autostash`
3. **데이터 준비.** `.venv\Scripts\python -m bot.main prepare --slot <슬롯>`
   - "건너뛰어요"가 나오면 (휴장일, 이미 올린 글, 오늘 시세 없음) 그 내용을 보고하고 끝낸다.
   - "준비 완료: drafts/<날짜>-<슬롯>/context.md"가 나오면 그 폴더가 이번 글의 폴더다.
4. **세 역할을 차례로.** `prompts/researcher.md`, `prompts/writer.md`, `prompts/editor.md`와 `context.md`를 읽고,
   1. 리서처: 지침대로 브리핑(issues, term, term_explain, mood)을 만든다.
   2. 작가: 지침대로 post, reply, card_comment, used_headlines를 쓴다. `<recent_first_lines>`의 표현과 문장 틀은 다시 쓰지 않는다.
   3. 편집장: `editor.md`의 1~6번 기준으로 초안을 냉정하게 다시 본다. 특히 헤드라인에 없는 사실, 헤드라인보다 단정적인 표현, 장중 숫자를 "마감"처럼 쓴 곳, 영어 헤드라인 오역을 찾는다. 문제가 있으면 고쳐 쓰고 다시 본다 (최대 3번).
5. **written.json 저장.** 폴더에 아래 모양으로 저장한다.
   ```json
   {"post": "...", "reply": "...", "card_comment": "...", "used_headlines": [1, 2], "attempts": 1,
    "brief": {"issues": [{"topic": "...", "why": "...", "headline_ids": [1], "related": ["..."]}], "term": "...", "term_explain": "...", "mood": "..."}}
   ```
6. **규칙 검사와 카드.** `.venv\Scripts\python -m bot.main finish --draft drafts/<날짜>-<슬롯>`
   - 실패하면 나온 문제를 고쳐서 written.json을 다시 저장하고 다시 실행한다 (최대 3번). 그래도 실패하면 올리지 않고 보고한다.
7. **카드 눈으로 확인.** `card.png`를 열어서 글자가 겹치거나 잘린 곳, 색(상승 빨강, 하락 파랑)이 숫자 부호와 맞는지 본다.
8. **공개용 커밋.**
   ```bash
   git add drafts/<날짜>-<슬롯>
   git -c user.email=ukjung43@users.noreply.github.com commit -q -m "draft: drafts/<날짜>-<슬롯>"
   git push -q
   ```
   `git rev-parse HEAD`로 SHA를 얻고, `https://raw.githubusercontent.com/ukjung43/today_stock_ai/<SHA>/drafts/<날짜>-<슬롯>/card.png`가 200으로 열리는지 확인한다.
9. **게시.** `.venv\Scripts\python -m bot.main publish --draft drafts/<날짜>-<슬롯> --image-base https://raw.githubusercontent.com/ukjung43/today_stock_ai/<SHA>`
10. **월요일 아침 글이면** 게시 뒤에 `.venv\Scripts\python -m bot.main refresh-token --env`로 Threads 토큰을 갱신한다 (60일이면 만료돼요). 출력에 토큰은 안 나온다.
11. **보고.** 게시 링크, 올린 글과 첫 댓글, 편집장 단계에서 고친 것, 걸리는 점을 쉬운 한국어로 짧게.
