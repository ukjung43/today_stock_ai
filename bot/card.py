"""Renders the 1080x1350 image card attached to each post."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import ROOT
from .market import Quote

W, H = 1080, 1350
BG = (22, 22, 26)
PANEL = (34, 34, 40)
FG = (240, 240, 236)
MUTED = (150, 150, 158)
UP = (255, 77, 79)      # Korean convention: rising is red
DOWN = (64, 140, 255)   # falling is blue
FLAT = (200, 200, 200)

# (path, ttc index) — first one that exists wins. Linux paths are what the GitHub runner gets from fonts-noto-cjk.
FONT_CANDIDATES = {
    "bold": [
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1),
        ("C:/Windows/Fonts/malgunbd.ttf", 0),
    ],
    "regular": [
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 1),
        ("C:/Windows/Fonts/malgun.ttf", 0),
    ],
}


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    for path, index in FONT_CANDIDATES[weight]:
        if Path(path).exists():
            return ImageFont.truetype(path, size, index=index)
    raise RuntimeError("한글 폰트를 찾지 못했어요 (Noto Sans CJK 또는 맑은 고딕 필요)")


def _color(q: Quote):
    if q.change_pct > 0.005:
        return UP
    if q.change_pct < -0.005:
        return DOWN
    return FLAT


def render_card(out: Path, slot: dict, today: str, quotes: list[Quote], comment: str, handle: str) -> Path:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    pad = 80

    d.text((pad, 90), f"오늘의 국장 · {slot['label']}", font=_font("bold", 44), fill=FG)
    d.text((pad, 150), today, font=_font("regular", 34), fill=MUTED)

    hero, rest = quotes[0], quotes[1:]
    d.text((pad, 270), hero.name, font=_font("bold", 48), fill=FG)
    d.text((pad, 330), hero.fmt_price(), font=_font("bold", 120), fill=FG)
    d.text((pad, 480), hero.fmt_pct(), font=_font("bold", 96), fill=_color(hero))

    top, row_h = 650, 92
    d.rounded_rectangle((pad - 24, top - 24, W - pad + 24, top + row_h * len(rest) + 8), radius=28, fill=PANEL)
    name_font, val_font = _font("regular", 38), _font("bold", 38)
    for i, q in enumerate(rest):
        y = top + i * row_h
        d.text((pad, y), q.name, font=name_font, fill=FG)
        pct = q.fmt_pct()
        pct_w = d.textlength(pct, font=val_font)
        d.text((W - pad - pct_w, y), pct, font=val_font, fill=_color(q))
        price = q.fmt_price()
        d.text((W - pad - pct_w - 40 - d.textlength(price, font=name_font), y), price, font=name_font, fill=MUTED)

    mascot_path = ROOT / "assets" / "mascot.png"
    comment_width = W - 2 * pad
    if mascot_path.exists():
        mascot = Image.open(mascot_path).convert("RGBA")
        mascot.thumbnail((240, 240))
        img.paste(mascot, (W - pad - mascot.width, H - 150 - mascot.height), mascot)
        comment_width -= mascot.width + 20

    size = 48
    while size > 28 and d.textlength(comment, font=_font("bold", size)) > comment_width:
        size -= 2
    d.text((pad, H - 250), comment, font=_font("bold", size), fill=FG)
    d.text((pad, H - 120), f"@{handle} · AI가 정리 · 종목 추천X", font=_font("regular", 30), fill=MUTED)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG", optimize=True)
    return out
