"""today_stock.ai command line.

  python -m bot.main draft --slot morning|lunch|afterwork|evening [--no-ai] [--force]
  python -m bot.main prepare --slot evening      # then Claude Code writes written.json
  python -m bot.main finish --draft drafts/2026-11-05-evening
  python -m bot.main publish --draft drafts/2026-11-05-afterwork --image-base https://raw.githubusercontent.com/OWNER/REPO/SHA
  python -m bot.main whoami
  python -m bot.main refresh-token --out token.txt
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .card import render_card
from .config import KST, ROOT, load_config
from .market import Quote, fetch_quotes, is_krx_trading_day
from .news import Headline, fetch_headlines
from .threads import ThreadsClient, exchange_for_long_lived_token, refresh_long_lived_token
from .writer import Written, _context, check_written, write_with_claude, write_with_template

WEEKDAYS = "월화수목금토일"


def _github_output(**values: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in values.items():
                f.write(f"{k}={v}\n")


def _github_summary(markdown: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")


def _recent_first_lines(n: int = 12) -> list[str]:
    """First lines of the latest published drafts, so the writer stops reusing the same hook."""
    lines = []
    for path in sorted((ROOT / "drafts").glob("*/post.json"))[-n:]:
        post = json.loads(path.read_text(encoding="utf-8")).get("post", "")
        if post:
            lines.append(post.splitlines()[0])
    return lines


def _gather(args, cfg):
    """Quotes and headlines for a slot, or None when this slot should not post now."""
    slot = cfg["slots"][args.slot]
    now = datetime.now(KST)
    today = f"{now:%Y.%m.%d} ({WEEKDAYS[now.weekday()]})"

    # The weekend preview posts on Sundays, when the market is closed by design.
    if not args.force and args.slot != "weekend" and not is_krx_trading_day(now.date()):
        print(f"{now.date()} 은 국장 휴장일이라 건너뛰어요.")
        _github_output(skip="true")
        _github_summary(f"⏸️ {today} 국장 휴장일이라 건너뜀")
        return None

    # A manual run and a late scheduled run for the same slot must not both post.
    if not args.force and (Path(args.out) / f"{now:%Y-%m-%d}-{args.slot}" / "post.json").exists():
        print(f"{now:%Y-%m-%d} {args.slot} 글은 이미 만들었어요. 건너뛰어요.")
        _github_output(skip="true")
        _github_summary(f"⏸️ {today} {slot['label']} 글은 이미 있어서 건너뜀")
        return None

    quotes = fetch_quotes(slot["symbols"])
    if args.slot in ("lunch", "afterwork") and not args.force and quotes[0].date != now.date().isoformat():
        print(f"{quotes[0].name} 오늘 시세가 아직 없어요 (마지막 거래일 {quotes[0].date}). 건너뛰어요.")
        _github_output(skip="true")
        _github_summary(f"⏸️ {quotes[0].name} 오늘 시세 없음 (마지막 {quotes[0].date})")
        return None

    feeds = cfg["news"]["feeds"] + slot.get("extra_feeds", [])
    headlines = fetch_headlines(feeds, slot["news_hours"], slot.get("max_items", cfg["news"]["max_items"]))
    return slot, now, today, quotes, headlines


def cmd_draft(args, cfg) -> int:
    gathered = _gather(args, cfg)
    if not gathered:
        return 0
    slot, now, today, quotes, headlines = gathered
    write = write_with_template if args.no_ai else write_with_claude
    written = write(cfg, slot, today, quotes, headlines, _recent_first_lines())
    return _save(args.out, args.slot, cfg, now, today, quotes, headlines, written)


def cmd_prepare(args, cfg) -> int:
    """Saves the data for a slot so Claude Code can write the post itself, without the API."""
    gathered = _gather(args, cfg)
    if not gathered:
        return 0
    slot, now, today, quotes, headlines = gathered
    draft_dir = Path(args.out) / f"{now:%Y-%m-%d}-{args.slot}"
    draft_dir.mkdir(parents=True, exist_ok=True)
    recent = _recent_first_lines()
    context = {
        "slot": args.slot,
        "created_at": now.isoformat(),
        "today": today,
        "quotes": [q.to_dict() for q in quotes],
        "headlines": [h.to_dict() for h in headlines],
    }
    (draft_dir / "context.json").write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    (draft_dir / "context.md").write_text(_context(slot, today, quotes, headlines, recent), encoding="utf-8")
    print(f"준비 완료: {draft_dir.as_posix()}/context.md")
    return 0


def cmd_finish(args, cfg) -> int:
    """Checks the post Claude Code wrote into written.json, then renders the card and post.json."""
    draft_dir = Path(args.draft)
    context = json.loads((draft_dir / "context.json").read_text(encoding="utf-8"))
    data = json.loads((draft_dir / "written.json").read_text(encoding="utf-8"))
    quote_fields = set(Quote.__dataclass_fields__)
    quotes = [Quote(**{k: v for k, v in q.items() if k in quote_fields}) for q in context["quotes"]]
    headlines = [Headline(**h) for h in context["headlines"]]
    written = Written(
        post=data["post"], reply=data["reply"], card_comment=data["card_comment"],
        used_headlines=data.get("used_headlines", []), brief=data.get("brief", {}), attempts=data.get("attempts", 1),
    )
    written.problems = check_written(cfg, context["today"], quotes, headlines, written)
    now = datetime.fromisoformat(context["created_at"])
    return _save(draft_dir.parent, context["slot"], cfg, now, context["today"], quotes, headlines, written)


def _save(out, slot_name: str, cfg, now: datetime, today: str, quotes, headlines, written) -> int:
    slot = cfg["slots"][slot_name]
    draft_dir = Path(out) / f"{now:%Y-%m-%d}-{slot_name}"
    render_card(draft_dir / "card.png", slot, today, quotes, written.card_comment, cfg["site"]["handle"])
    site = cfg["site"]
    reply = written.reply
    # The site link only goes on some posts; every reply carries the extra explanation.
    if slot_name in site.get("link_slots", []) and WEEKDAYS[now.weekday()] in site.get("link_weekdays", []):
        reply += f"\n\n'오늘의 국장'에서 더 보기 🐾\n{site['url']}"
    used = [headlines[i - 1] for i in written.used_headlines if 0 < i <= len(headlines)]
    record = {
        "slot": slot_name,
        "created_at": now.isoformat(),
        "post": written.post,
        "reply": reply,
        "card_comment": written.card_comment,
        "problems": written.problems,
        "attempts": written.attempts,
        "brief": written.brief,
        "quotes": [q.to_dict() for q in quotes],
        "sources": [h.to_dict() for h in used],
    }
    (draft_dir / "post.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    rel = draft_dir.resolve().relative_to(ROOT).as_posix() if draft_dir.resolve().is_relative_to(ROOT) else str(draft_dir)
    print(f"\n초안: {draft_dir}\n{'-' * 40}\n{written.post}\n{'-' * 40}\n[첫 댓글]\n{reply}\n")
    sources = "\n".join(f"- [{h.source}] [{h.title}]({h.link})" for h in used) or "- (없음)"
    issues = "\n".join(f"{n}. {i['topic']} — {i['why']}" for n, i in enumerate(written.brief.get("issues", []), 1))
    team = f"**리서처가 고른 이슈** (분위기: {written.brief.get('mood', '-')})\n\n{issues}\n\n" if issues else ""
    if written.attempts:
        team += f"**작가 시도 횟수:** {written.attempts}회 · 편집장 {'통과' if not written.problems else '반려'}\n\n"
    _github_summary(
        f"## {slot['title']} · {today}\n\n```text\n{written.post}\n```\n\n**첫 댓글**\n\n```text\n{reply}\n```\n\n"
        f"{team}**참고한 헤드라인**\n{sources}\n"
    )

    if written.problems:
        print("검사에 걸려서 이 초안은 올리지 않아요:\n- " + "\n- ".join(written.problems))
        _github_summary("### ⛔ 검사 실패, 게시 안 함\n- " + "\n- ".join(written.problems))
        _github_output(skip="true")
        return 1
    _github_output(skip="false", dir=rel)
    return 0


def cmd_publish(args, cfg) -> int:
    draft_dir = Path(args.draft)
    record = json.loads((draft_dir / "post.json").read_text(encoding="utf-8"))
    if record["problems"]:
        print("검사에 걸린 초안이라 올리지 않아요.")
        return 1
    age_h = (datetime.now(KST) - datetime.fromisoformat(record["created_at"])).total_seconds() / 3600
    if age_h > cfg["post"]["max_draft_age_hours"]:
        print(f"초안이 {age_h:.1f}시간 전 것이라 너무 오래됐어요. 올리지 않아요.")
        _github_summary(f"⏰ 승인이 늦어 게시 안 함 (초안 {age_h:.1f}시간 경과)")
        return 0

    client = ThreadsClient(os.environ.get("THREADS_ACCESS_TOKEN", ""))
    user = client.me()
    image_url = f"{args.image_base.rstrip('/')}/{draft_dir.as_posix()}/card.png"
    post_id = client.post_image(user["id"], record["post"], image_url)
    client.reply_text(user["id"], post_id, record["reply"])
    link = client.permalink(post_id)
    print(f"게시 완료: {link or post_id}")
    _github_summary(f"✅ 게시 완료: {link or post_id}")
    return 0


def cmd_whoami(args, cfg) -> int:
    me = ThreadsClient(os.environ.get("THREADS_ACCESS_TOKEN", "")).me()
    print(f"연결된 Threads 계정: @{me['username']} (id {me['id']})")
    return 0


def _write_env_token(token: str) -> None:
    """Replaces the token in .env in place, without printing it."""
    env_path = ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    lines = [f"THREADS_ACCESS_TOKEN={token}" if l.startswith("THREADS_ACCESS_TOKEN=") else l for l in lines]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_exchange_token(args, cfg) -> int:
    result = exchange_for_long_lived_token(os.environ.get("THREADS_ACCESS_TOKEN", ""), os.environ.get("THREADS_APP_SECRET", ""))
    _write_env_token(result["access_token"])
    print(f".env 의 토큰을 장기 토큰으로 바꿨어요 ({int(result.get('expires_in', 0)) // 86400}일 유효)")
    return 0


def cmd_refresh_token(args, cfg) -> int:
    result = refresh_long_lived_token(os.environ.get("THREADS_ACCESS_TOKEN", ""))
    if args.env:
        _write_env_token(result["access_token"])
    else:
        Path(args.out).write_text(result["access_token"], encoding="utf-8")
    print(f"새 토큰을 저장했어요 ({int(result.get('expires_in', 0)) // 86400}일 유효)")
    return 0


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(prog="today_stock.ai")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("draft", help="글과 이미지 초안 만들기")
    p.add_argument("--slot", choices=["morning", "lunch", "afterwork", "evening", "weekend"], required=True)
    p.add_argument("--no-ai", action="store_true", help="Claude 없이 템플릿으로 (미리보기용)")
    p.add_argument("--force", action="store_true", help="휴장일 검사 건너뛰기")
    p.add_argument("--out", default="drafts")
    p.set_defaults(func=cmd_draft)

    p = sub.add_parser("prepare", help="Claude Code가 직접 쓸 수 있게 시세·헤드라인만 준비 (API 없이)")
    p.add_argument("--slot", choices=["morning", "lunch", "afterwork", "evening", "weekend"], required=True)
    p.add_argument("--force", action="store_true", help="휴장일·중복 검사 건너뛰기")
    p.add_argument("--out", default="drafts")
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("finish", help="written.json 을 규칙 검사하고 카드·post.json 만들기")
    p.add_argument("--draft", required=True)
    p.set_defaults(func=cmd_finish)

    p = sub.add_parser("publish", help="초안을 Threads에 올리기")
    p.add_argument("--draft", required=True)
    p.add_argument("--image-base", required=True, help="card.png 를 공개 주소로 받을 수 있는 기본 URL")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("whoami", help="Threads 토큰 확인")
    p.set_defaults(func=cmd_whoami)

    p = sub.add_parser("exchange-token", help=".env 의 단기 토큰을 장기 토큰(60일)으로 교환")
    p.set_defaults(func=cmd_exchange_token)

    p = sub.add_parser("refresh-token", help="Threads 장기 토큰 갱신")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--out", help="새 토큰을 이 파일에 저장 (GitHub Actions용)")
    group.add_argument("--env", action="store_true", help="이 PC의 .env 토큰을 바로 바꾸기")
    p.set_defaults(func=cmd_refresh_token)

    args = parser.parse_args()
    os.chdir(ROOT)
    return args.func(args, load_config())


if __name__ == "__main__":
    sys.exit(main())
