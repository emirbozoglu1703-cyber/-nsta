"""Piyasa verisi (Yahoo / AlgoLab) ve BIST seans saatleri."""

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
    """Botun işlem saatleri: hafta içi session_open-session_close (İstanbul saati).
    BIST'te seans, forex'te likit saatler (Londra + New York). Resmi tatilleri
    bilmez; tatilde yeni mum gelmediği için bot işlem açmaz."""

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
    Not: Yahoo verisi gecikmeli olabilir; gerçek para modunda kurumun
    kendi verisi (MT5 / AlgoLab) kullanılır."""

    URL = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}"

    def __init__(self, cfg):
        self.cfg = cfg
        self.clock = SessionClock(cfg)
        self.s = requests.Session()
        self.s.headers.update(UA)

    def _chart(self, sym, range_):
        ysym = f"{sym}=X" if self.cfg.market == "forex" else f"{sym}.IS"
        r = self.s.get(self.URL.format(sym=ysym),
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


class AlgoLabData:
    """Gerçek para modunda veri: AlgoLab mumları ve son fiyat."""

    def __init__(self, cfg, client):
        self.cfg, self.c = cfg, client
        self.clock = SessionClock(cfg)

    def _parse_t(self, s):
        s = s.replace("Z", "+00:00")
        t = datetime.fromisoformat(s)
        return t.replace(tzinfo=TZ) if t.tzinfo is None else t.astimezone(TZ)

    def bars(self, symbols, now):
        from .algolab import num
        out = {}
        for sym in symbols:
            try:
                rows = self.c.candles(sym, self.cfg.bar_minutes)
            except Exception as e:
                print(f"  ! {sym} mumları alınamadı: {e}")
                continue
            bars = []
            for r in rows:
                b = Bar(self._parse_t(r["date"]), num(r["open"]), num(r["high"]),
                        num(r["low"]), num(r["close"]), num(r.get("volume")))
                if self.clock.in_session(b.t):
                    bars.append(b)
            bars.sort(key=lambda b: b.t)
            out[sym] = closed_only(bars, now, self.cfg.bar_minutes)
        return out

    def prices(self, symbols):
        out = {}
        for sym in symbols:
            try:
                p = self.c.last_price(sym)
                if p > 0:
                    out[sym] = p
            except Exception as e:
                print(f"  ! {sym} fiyatı alınamadı: {e}")
        return out
