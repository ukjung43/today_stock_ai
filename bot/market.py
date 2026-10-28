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
        params={"range": "10d", "interval": "1d"},
        headers=HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    result = resp.json()["chart"]["result"][0]
    tz = ZoneInfo(result["meta"]["exchangeTimezoneName"])
    closes = [
        (datetime.fromtimestamp(ts, tz).date(), c)
        for ts, c in zip(result["timestamp"], result["indicators"]["quote"][0]["close"])
        if c is not None
    ]
    if len(closes) < 2:
        raise RuntimeError(f"{symbol}: 시세 데이터가 부족해요")
    (last_date, last), (_, prev) = closes[-1], closes[-2]
    return Quote(
        symbol=symbol,
        name=name,
        kind=kind,
        price=last,
        prev_close=prev,
        change_pct=(last / prev - 1) * 100,
        date=last_date.isoformat(),
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
