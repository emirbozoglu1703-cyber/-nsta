"""Aracı kurum bağlantısı: sanal (SimBroker) veya Alpaca (paper/live)."""

import json
import time
import uuid
from pathlib import Path

import requests

from .market import SimpleClock, now_ny
from .strategy import buy_fees, sell_fees


class Fill:
    def __init__(self, qty, price, fee):
        self.qty, self.price, self.fee = qty, price, fee


class SimBroker:
    """Videodaki 'sanal 5000 dolar' testi: gerçek borsaya hiç bağlanmaz."""

    name = "SANAL"

    def __init__(self, cfg):
        self.cfg = cfg
        self.path = Path(cfg.state_dir) / "sim_hesap.json"
        self.clock_ = SimpleClock()
        if self.path.exists():
            self.acct = json.loads(self.path.read_text())
        else:
            self.acct = {"cash": cfg.budget_usd, "positions": {}}
            self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.acct, indent=2))

    def clock(self):
        return self.clock_.session(now_ny())

    def account(self, prices=None):
        prices = prices or {}
        eq = self.acct["cash"] + sum(q * prices.get(s, 0) for s, q in self.acct["positions"].items())
        return {"cash": self.acct["cash"], "equity": eq, "daytrade_count": 0,
                "pattern_day_trader": False}

    def held_qty(self, sym):
        return self.acct["positions"].get(sym, 0)

    def buy(self, sym, qty, price):
        px = price * (1 + self.cfg.slippage_bps / 10000)
        fee = buy_fees(px, qty, self.cfg)
        cost = px * qty + fee
        if cost > self.acct["cash"]:
            return None
        self.acct["cash"] -= cost
        self.acct["positions"][sym] = self.acct["positions"].get(sym, 0) + qty
        self._save()
        return Fill(qty, px, fee)

    def sell(self, sym, qty, price):
        qty = min(qty, self.held_qty(sym))
        if qty <= 0:
            return None
        px = price * (1 - self.cfg.slippage_bps / 10000)
        fee = sell_fees(px, qty, self.cfg)
        self.acct["cash"] += px * qty - fee
        left = self.acct["positions"][sym] - qty
        if left:
            self.acct["positions"][sym] = left
        else:
            del self.acct["positions"][sym]
        self._save()
        return Fill(qty, px, fee)


class AlpacaBroker:
    """Alpaca Trading API. paper=True sanal hesap, False GERÇEK PARA."""

    def __init__(self, cfg, key, secret, paper=True):
        self.cfg = cfg
        self.paper = paper
        self.name = "ALPACA-SANAL" if paper else "ALPACA-GERÇEK"
        self.base = ("https://paper-api.alpaca.markets" if paper
                     else "https://api.alpaca.markets") + "/v2"
        self.s = requests.Session()
        self.s.headers.update({"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})

    def _get(self, path, **params):
        r = self.s.get(self.base + path, params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    def clock(self):
        from datetime import datetime
        from .market import NY
        c = self._get("/clock")
        ts = lambda s: datetime.fromisoformat(s).astimezone(NY)
        now = now_ny()
        # Gün içindeysek bugünün açılış/kapanışını, değilse sıradakileri döner.
        close = ts(c["next_close"])
        open_ = close.replace(hour=9, minute=30) if c["is_open"] else ts(c["next_open"])
        return c["is_open"], open_, close

    def account(self, prices=None):
        a = self._get("/account")
        if a.get("trading_blocked") or a.get("account_blocked"):
            raise RuntimeError("Alpaca hesabı işlem yapmaya kapalı")
        return {"cash": float(a["cash"]), "equity": float(a["equity"]),
                "buying_power": float(a["buying_power"]),
                "daytrade_count": int(a.get("daytrade_count", 0)),
                "pattern_day_trader": bool(a.get("pattern_day_trader"))}

    def held_qty(self, sym):
        r = self.s.get(f"{self.base}/positions/{sym}", timeout=20)
        if r.status_code == 404:
            return 0
        r.raise_for_status()
        return float(r.json()["qty"])

    def _order(self, sym, qty, side):
        body = {"symbol": sym, "qty": str(qty), "side": side, "type": "market",
                "time_in_force": "day", "client_order_id": f"bot-{uuid.uuid4().hex[:20]}"}
        r = self.s.post(f"{self.base}/orders", json=body, timeout=20)
        if r.status_code >= 400:
            print(f"  ! {side} emri reddedildi ({sym}): {r.status_code} {r.text[:200]}")
            return None
        oid = r.json()["id"]
        o = None
        for _ in range(30):  # en fazla ~30 sn dolmasını bekle
            o = self._get(f"/orders/{oid}")
            if o["status"] in ("filled", "canceled", "expired", "rejected"):
                break
            time.sleep(1)
        if o["status"] not in ("filled", "canceled", "expired", "rejected"):
            self.s.delete(f"{self.base}/orders/{oid}", timeout=20)
            time.sleep(1)
            o = self._get(f"/orders/{oid}")
        filled = float(o.get("filled_qty") or 0)
        if filled <= 0:
            print(f"  ! {side} emri dolmadı ({sym}): {o['status']}")
            return None
        px = float(o["filled_avg_price"])
        fee = sell_fees(px, filled, self.cfg) if side == "sell" else buy_fees(px, filled, self.cfg)
        return Fill(filled, px, fee)

    def buy(self, sym, qty, price):
        return self._order(sym, qty, "buy")

    def sell(self, sym, qty, price):
        qty = min(qty, self.held_qty(sym))
        if qty <= 0:
            return None
        return self._order(sym, qty, "sell")
