"""Sanal mod verisi (Yahoo) ve botun işlem saatleri."""

from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

import requests

from .strategy import Bar

TZ = ZoneInfo("Europe/Istanbul")
UA = {"User-Agent": "Mozilla/5.0 (borsa-bot)"}


def now_tr():
    return datetime.now(TZ)


def hm(s):
    h, m = s.split(":")
    return dtime(int(h), int(m))


class SessionClock:
    """Botun işlem saatleri: hafta içi session_open-session_close (İstanbul saati),
    forex'in en likit olduğu Londra + New York saatleri. Tatillerde yeni mum
    gelmediği için bot işlem açmaz."""

    def __init__(self, cfg):
        self.open_t, self.close_t = hm(cfg.session_open), hm(cfg.session_close)

    def session(self, now=None):
        now = now or now_tr()
        open_ = now.replace(hour=self.open_t.hour, minute=self.open_t.minute, second=0, microsecond=0)
        close = now.replace(hour=self.close_t.hour, minute=self.close_t.minute, second=0, microsecond=0)
        is_open = now.weekday() < 5 and open_ <= now < close
        return is_open, open_, close

    def in_session(self, t):
        return self.open_t <= t.time() < self.close_t


def closed_only(bars, now, bar_minutes):
    return [b for b in bars if b.t + timedelta(minutes=bar_minutes) <= now]


class YahooData:
    """Ücretsiz, hesap gerektirmez. Sanal mod ve geçmiş testi için.
    Not: Yahoo verisi gecikmeli olabilir; gerçek hesapta MT5'in kendi verisi
    kullanılır."""

    URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"

    def __init__(self, cfg):
        self.cfg = cfg
        self.clock = SessionClock(cfg)
        self.s = requests.Session()
        self.s.headers.update(UA)

    def _chart(self, sym, range_):
        r = self.s.get(self.URL.format(sym=f"{sym}=X"),
                       params={"interval": f"{self.cfg.bar_minutes}m", "range": range_},
                       timeout=20)
        r.raise_for_status()
        res = r.json()["chart"]["result"][0]
        q = res["indicators"]["quote"][0]
        bars = []
        for i, ts in enumerate(res.get("timestamp") or []):
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None in (o, h, l, c):
                continue
            b = Bar(datetime.fromtimestamp(ts, TZ), o, h, l, c, q["volume"][i] or 0)
            if self.clock.in_session(b.t):
                bars.append(b)
        return bars, res["meta"].get("regularMarketPrice")

    def history(self, sym, range_="60d"):
        return self._chart(sym, range_)[0]

    def bars(self, symbols, now):
        out = {}
        for sym in symbols:
            try:
                out[sym] = closed_only(self._chart(sym, "5d")[0], now, self.cfg.bar_minutes)
            except Exception as e:  # tek hisse hatası botu durdurmasın
                print(f"  ! {sym} verisi alınamadı: {e}")
        return out

    def prices(self, symbols):
        out = {}
        for sym in symbols:
            try:
                p = self._chart(sym, "1d")[1]
                if p:
                    out[sym] = float(p)
            except Exception as e:
                print(f"  ! {sym} fiyatı alınamadı: {e}")
        return out
