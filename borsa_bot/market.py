"""Piyasa verisi (Yahoo / Alpaca) ve borsa saatleri."""

import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

from .strategy import Bar

NY = ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0 (borsa-bot)"}


def now_ny():
    return datetime.now(NY)


class SimpleClock:
    """Alpaca'sız saat: hafta içi 09:30-16:00 New York. Resmi tatilleri bilmez."""

    def session(self, now=None):
        now = now or now_ny()
        open_ = now.replace(hour=9, minute=30, second=0, microsecond=0)
        close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        is_open = now.weekday() < 5 and open_ <= now < close
        return is_open, open_, close


class YahooData:
    """Ücretsiz, anahtarsız. Sanal (sim) mod ve backtest için."""

    URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"

    def __init__(self, bar_minutes=5):
        self.interval = f"{bar_minutes}m"
        self.bar_minutes = bar_minutes
        self.s = requests.Session()
        self.s.headers.update(UA)

    def _chart(self, sym, range_):
        r = self.s.get(self.URL.format(sym=sym),
                       params={"interval": self.interval, "range": range_,
                               "includePrePost": "false"}, timeout=20)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        bars = []
        for i, ts in enumerate(res.get("timestamp") or []):
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None in (o, h, l, c):
                continue
            bars.append(Bar(datetime.fromtimestamp(ts, NY), o, h, l, c, q["volume"][i] or 0))
        price = res["meta"].get("regularMarketPrice")
        return bars, price

    def bars(self, sym, range_="5d"):
        bars, _ = self._chart(sym, range_)
        return bars

    def snapshot(self, symbols, now=None):
        """{sym: (kapanmış_mumlar, son_fiyat)}"""
        now = now or now_ny()
        out = {}
        for sym in symbols:
            try:
                bars, price = self._chart(sym, "5d")
            except Exception as e:  # tek hisse hatası botu durdurmasın
                print(f"  ! {sym} verisi alınamadı: {e}")
                continue
            closed = [b for b in bars if b.t + timedelta(minutes=self.bar_minutes) <= now]
            if closed and price:
                out[sym] = (closed, float(price))
        return out


class AlpacaData:
    """Alpaca piyasa verisi (paper/live). Ücretsiz planda IEX verisi."""

    URL = "https://data.alpaca.markets/v2/stocks"

    def __init__(self, key, secret, bar_minutes=5, feed=None):
        self.s = requests.Session()
        self.s.headers.update({"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
        self.bar_minutes = bar_minutes
        self.feed = feed or os.environ.get("ALPACA_DATA_FEED", "iex")

    def snapshot(self, symbols, now=None):
        now = now or now_ny()
        start = (now - timedelta(days=5)).astimezone(timezone.utc).isoformat()
        bars = {s: [] for s in symbols}
        token = None
        while True:
            params = {"symbols": ",".join(symbols), "timeframe": f"{self.bar_minutes}Min",
                      "start": start, "limit": 10000, "feed": self.feed,
                      "adjustment": "raw"}
            if token:
                params["page_token"] = token
            r = self.s.get(f"{self.URL}/bars", params=params, timeout=20)
            r.raise_for_status()
            j = r.json()
            for sym, lst in (j.get("bars") or {}).items():
                for b in lst:
                    t = datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY)
                    bars[sym].append(Bar(t, b["o"], b["h"], b["l"], b["c"], b["v"]))
            token = j.get("next_page_token")
            if not token:
                break
        r = self.s.get(f"{self.URL}/trades/latest",
                       params={"symbols": ",".join(symbols), "feed": self.feed}, timeout=20)
        r.raise_for_status()
        latest = {s: t["p"] for s, t in (r.json().get("trades") or {}).items()}
        out = {}
        for sym in symbols:
            closed = [b for b in bars[sym]
                      if b.t + timedelta(minutes=self.bar_minutes) <= now]
            closed = [b for b in closed if b.t.time() >= datetime.strptime("09:30", "%H:%M").time()
                      and b.t.time() < datetime.strptime("16:00", "%H:%M").time()]
            if closed and sym in latest:
                out[sym] = (closed, float(latest[sym]))
        return out


def retry(fn, tries=3, wait=2):
    for i in range(tries):
        try:
            return fn()
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(wait * (i + 1))
