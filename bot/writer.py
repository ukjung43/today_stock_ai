"""The writing team: researcher picks the issues, writer drafts the post, editor reviews it.

Each role is one Claude call with its own prompt in prompts/<role>.md. Rule-based checks
(numbers, banned words, length) run before the editor so it only judges what code can't.
"""

import json
from dataclasses import dataclass, field

import anthropic

from .checks import allowed_numbers, find_problems
from .config import ROOT
from .market import Quote
from .news import Headline

RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "why": {"type": "string"},
                    "headline_ids": {"type": "array", "items": {"type": "integer"}},
                    "related": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["topic", "why", "headline_ids", "related"],
                "additionalProperties": False,
            },
        },
        "term": {"type": "string"},
        "term_explain": {"type": "string"},
        "mood": {"type": "string"},
    },
    "required": ["issues", "term", "term_explain", "mood"],
    "additionalProperties": False,
}

WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "post": {"type": "string"},
        "reply": {"type": "string"},
        "card_comment": {"type": "string"},
        "used_headlines": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["post", "reply", "card_comment", "used_headlines"],
    "additionalProperties": False,
}

EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["approved", "issues"],
    "additionalProperties": False,
}


class WriterError(RuntimeError):
    pass


@dataclass
class Written:
    post: str
    reply: str
    card_comment: str
    used_headlines: list[int] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    brief: dict = field(default_factory=dict)
    attempts: int = 0


def _always_allowed(cfg: dict, today: str) -> list[str]:
    return [today, *cfg["safety"].get("allowed_numbers", [])]


def _context(slot: dict, today: str, quotes: list[Quote], headlines: list[Headline]) -> str:
    data = [q.to_dict() for q in quotes]
    lines = [f"{i}. [{h.source}] {h.title}" for i, h in enumerate(headlines, 1)]
    return (
        f"오늘은 {today}이고, 쓸 글은 '{slot['title']}' ({slot['label']}) 이에요.\n\n"
        f"<market_data>\n{json.dumps(data, ensure_ascii=False, indent=1)}\n</market_data>\n\n"
        "<headlines>\n" + "\n".join(lines) + "\n</headlines>"
    )


class Team:
    def __init__(self, cfg: dict, slot: dict, today: str, quotes: list[Quote], headlines: list[Headline]):
        self.cfg, self.today = cfg, today
        self.quotes, self.headlines = quotes, headlines
        self.context = _context(slot, today, quotes, headlines)
        self.client = anthropic.Anthropic()

    def _ask(self, role: str, messages: list, schema: dict):
        resp = self.client.beta.messages.create(
            model=self.cfg["claude"]["model"],
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={
                "effort": self.cfg["roles"][role]["effort"],
                "format": {"type": "json_schema", "schema": schema},
            },
            system=(ROOT / "prompts" / f"{role}.md").read_text(encoding="utf-8"),
            messages=messages,
        )
        if resp.stop_reason == "refusal":
            raise WriterError(f"{role} 단계에서 Claude가 거절했어요 (request {resp._request_id})")
        if resp.stop_reason == "max_tokens":
            raise WriterError(f"{role} 응답이 너무 길어서 잘렸어요")
        return json.loads(next(b.text for b in resp.content if b.type == "text")), resp

    def research(self) -> dict:
        brief, _ = self._ask("researcher", [{"role": "user", "content": self.context + "\n\n오늘의 빅이슈 브리핑을 만들어주세요."}], RESEARCH_SCHEMA)
        return brief

    def review(self, written: Written, brief: dict) -> list[str]:
        draft = {"post": written.post, "reply": written.reply, "card_comment": written.card_comment}
        content = (
            f"{self.context}\n\n<brief>\n{json.dumps(brief, ensure_ascii=False, indent=1)}\n</brief>\n\n"
            f"<draft>\n{json.dumps(draft, ensure_ascii=False, indent=1)}\n</draft>\n\n초안을 검수해주세요."
        )
        verdict, _ = self._ask("editor", [{"role": "user", "content": content}], EDIT_SCHEMA)
        if verdict["approved"]:
            return []
        return [f"[편집장] {issue}" for issue in verdict["issues"]] or ["[편집장] 승인하지 않았어요"]

    def run(self) -> Written:
        allowed = allowed_numbers(self.quotes, self.headlines, _always_allowed(self.cfg, self.today))
        banned, limits = self.cfg["safety"]["banned"], self.cfg["post"]
        brief = self.research()
        print(f"[리서처] {[i['topic'] for i in brief['issues']]}")

        messages: list = [{
            "role": "user",
            "content": f"{self.context}\n\n<brief>\n{json.dumps(brief, ensure_ascii=False, indent=1)}\n</brief>\n\n브리핑으로 글을 써주세요.",
        }]
        for attempt in range(1, self.cfg["claude"]["max_attempts"] + 1):
            data, resp = self._ask("writer", messages, WRITE_SCHEMA)
            written = Written(**data, brief=brief, attempts=attempt)
            written.problems = find_problems(written.post, allowed, banned, limits["max_chars"])
            written.problems += find_problems(written.reply, allowed, banned, limits["reply_max_chars"])
            written.problems += find_problems(written.card_comment, allowed, banned, limits["card_comment_max_chars"])
            if not written.problems:
                written.problems = self.review(written, brief)
            if not written.problems:
                return written
            print(f"[작가] {attempt}번째 초안 반려: {written.problems}")
            messages += [
                {"role": "assistant", "content": resp.content},
                {"role": "user", "content": "검수에서 반려됐어요. 고쳐서 다시 써주세요:\n- " + "\n- ".join(written.problems)},
            ]
        return written  # still has problems; the caller refuses to publish it


def write_with_claude(cfg: dict, slot: dict, today: str, quotes: list[Quote], headlines: list[Headline]) -> Written:
    return Team(cfg, slot, today, quotes, headlines).run()


def write_with_template(cfg: dict, slot: dict, today: str, quotes: list[Quote], headlines: list[Headline]) -> Written:
    """No-AI fallback used for local previews (`--no-ai`)."""
    hero = quotes[0]
    bullets = [f"• {q.name} — {q.fmt_price()} ({q.fmt_pct()})" for q in quotes[:4]]
    news = [f"• {h.title if len(h.title) <= 40 else h.title[:39] + '…'}" for h in headlines[:2]]
    post = "\n".join(
        [f"{slot['title']} ({today})", f"{hero.name} {hero.fmt_pct()}… 내 계좌는 여전히 -65%에오", "", *bullets, *news, "", "자세한 정리는 댓글 👇"]
    )
    written = Written(post=post, reply="오늘 국장 추가 설명 자리예요 🐾", card_comment="오늘도 공부하는 주린이")
    allowed = allowed_numbers(quotes, headlines, _always_allowed(cfg, today))
    written.problems = find_problems(post, allowed, cfg["safety"]["banned"], cfg["post"]["max_chars"])
    return written
