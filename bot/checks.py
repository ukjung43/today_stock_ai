"""Safety checks run on every draft before it can be published."""

import re

from .market import Quote
from .news import Headline

# Numbers that carry real information: anything with a decimal point, a thousands comma or a percent sign.
NUMBER = re.compile(r"[+\-−]?\d[\d,]*(?:\.\d+)?%?")


def _norm(token: str) -> str:
    return token.replace("−", "-").replace(",", "")


def allowed_numbers(quotes: list[Quote], headlines: list[Headline], extra: list[str] = ()) -> set[str]:
    """`extra` holds strings that may always appear, such as today's date or the account's -65% meme."""
    allowed: set[str] = set()
    for text in extra:
        for m in NUMBER.finditer(text):
            allowed.add(_norm(m.group()))
    for q in quotes:
        for text in (q.fmt_price(), q.fmt_pct()):
            for m in NUMBER.finditer(text):
                allowed.add(_norm(m.group()))
        allowed.add(_norm(f"{abs(q.change_pct):.2f}%"))
        allowed.add(_norm(f"{q.change_pct:+.1f}%"))
        allowed.add(_norm(f"{abs(q.change_pct):.1f}%"))
    for h in headlines:
        for m in NUMBER.finditer(h.title):
            allowed.add(_norm(m.group()).lstrip("+-"))
    return allowed


def find_problems(text: str, allowed: set[str], banned: list[str], max_chars: int) -> list[str]:
    problems = []
    if len(text) > max_chars:
        problems.append(f"글이 {len(text)}자예요. {max_chars}자 이하로 줄여주세요.")
    for word in banned:
        if word in text:
            problems.append(f"금지 표현이 있어요: '{word}'")
    for m in NUMBER.finditer(text):
        token = m.group()
        if not any(c in token for c in ".,%"):
            continue
        norm = _norm(token)
        # An unsigned percentage may match either sign; a signed one must match exactly.
        if norm in allowed or (norm[0] not in "+-" and f"+{norm}" in allowed) or (
            norm[0] not in "+-" and f"-{norm}" in allowed
        ):
            continue
        problems.append(f"데이터에 없는 숫자예요: '{token}'")
    return problems
