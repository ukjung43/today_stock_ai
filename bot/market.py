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


def _chart(symbol: str, range_: str) -> dict:
    resp = requests.get(
        CHART_URL.format(symbol=quote(symbol)),
        params={"range": range_, "interval": "1d"},
        headers=HEADERS,
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["chart"]["result"][0]


def fetch_quote(symbol: str, name: str, kind: str) -> Quote:
    chart = _chart(symbol, "5d")
    meta = chart["meta"]
    last, ts = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
    if not last or not ts:
        raise RuntimeError(f"{symbol}: 시세 데이터가 부족해요")
    tz = ZoneInfo(meta["exchangeTimezoneName"])
    day = datetime.fromtimestamp(ts, tz).date()

    # Yahoo has two "previous close" sources and each one breaks:
    # - the 1d chartPreviousClose can be a day stale (2026-10-29 lunch: KOSDAQ +0.76% when Yonhap's open
    #   print implied about -2.9%), so for stocks/indices the last daily bar before today wins;
    # - that bar's close can be blank (2026-10-29 morning), so fall back then, but never skip to an older bar;
    # - FX (=X) and futures (=F) bars don't follow the exchange day (24h trading, contract rolls) and gave
    #   FX +1.21% / Brent -2.94% when Yahoo's own quote said -0.16% / -0.99%, so those use chartPreviousClose.
    meta_prev = _chart(symbol, "1d")["meta"].get("chartPreviousClose")
    bars = [
        (datetime.fromtimestamp(t, tz).date(), c)
        for t, c in zip(chart.get("timestamp") or [], chart["indicators"]["quote"][0].get("close") or [])
    ]
    before = [c for d, c in bars if d < day]
    bar_prev = before[-1] if before else None
    if symbol.endswith(("=X", "=F")):
        prev = meta_prev
    else:
        prev = bar_prev or meta_prev
        if bar_prev and meta_prev and abs(bar_prev / meta_prev - 1) > 0.003:
            print(f"[market] {symbol}: 전일 종가가 서로 달라요 (일봉 {bar_prev}, 시세 {meta_prev}). 일봉 값을 써요")
    if not prev:
        raise RuntimeError(f"{symbol}: 전일 종가를 찾지 못했어요")
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
        date=day.isoformat(),
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
