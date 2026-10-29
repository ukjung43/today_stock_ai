"""Daily quotes from Yahoo Finance's chart endpoint, plus KRX trading-day checks."""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import holidays
import requests

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
HEADERS = {"User-Agent": "Mozilla/5.0 (today_stock.ai bot)"}


@dataclass
class Quote:
    symbol: str
    name: str
    kind: str  # index | krw | usd | fx
    price: float
    prev_close: float
    change_pct: float
    date: str  # trading date of `price`, in the exchange's timezone

    def fmt_price(self) -> str:
        if self.kind == "krw":
            return f"{self.price:,.0f}원"
        if self.kind == "usd":
            return f"${self.price:,.2f}"
        if self.kind == "fx":
            return f"{self.price:,.2f}원"
        return f"{self.price:,.2f}"

    def fmt_pct(self) -> str:
        return f"{self.change_pct:+.2f}%"

    def to_dict(self) -> dict:
        return asdict(self) | {"price_text": self.fmt_price(), "change_text": self.fmt_pct()}


def fetch_quote(symbol: str, name: str, kind: str) -> Quote:
    resp = requests.get(
        CHART_URL.format(symbol=quote(symbol)),
        params={"range": "1d", "interval": "1d"},
        headers=HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    # Use the quote fields, not the daily bars: Yahoo sometimes blanks or revises a past bar's close,
    # which silently shifted "previous close" back a day (e.g. KOSPI +8% instead of +1.35%).
    meta = resp.json()["chart"]["result"][0]["meta"]
    last, prev, ts = meta.get("regularMarketPrice"), meta.get("chartPreviousClose"), meta.get("regularMarketTime")
    if not last or not prev or not ts:
        raise RuntimeError(f"{symbol}: 시세 데이터가 부족해요")
    change_pct = (last / prev - 1) * 100
    if abs(change_pct) > 30:  # beyond KRX's daily limit: treat as bad data rather than post it
        raise RuntimeError(f"{symbol}: 등락률 {change_pct:+.2f}% 는 데이터 오류로 보여요")
    return Quote(
        symbol=symbol,
        name=name,
        kind=kind,
        price=last,
        prev_close=prev,
        change_pct=change_pct,
        date=datetime.fromtimestamp(ts, ZoneInfo(meta["exchangeTimezoneName"])).date().isoformat(),
    )


def fetch_quotes(symbols: list[dict]) -> list[Quote]:
    return [fetch_quote(s["symbol"], s["name"], s["kind"]) for s in symbols]


def is_krx_trading_day(day: date) -> bool:
    """Weekends, Korean public holidays (incl. substitute days) and the year-end closing day are off."""
    if day.weekday() >= 5:
        return False
    if day in holidays.KR(years=day.year):
        return False
    if day.month == 12 and day.day == 31:
        return False
    return True
