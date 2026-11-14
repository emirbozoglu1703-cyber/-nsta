"""Sanal hesap: videodaki 'sanal para ile test'. Gerçek hesap için bkz. mt5.py."""

import json
from pathlib import Path

from .market import SessionClock, now_tr
from .strategy import buy_fees, sell_fees, pnl_factor


class Fill:
    def __init__(self, qty, price, fee):
        self.qty, self.price, self.fee = qty, price, fee


class SimBroker:
    """Videodaki 'sanal para' testi: gerçek borsaya hiç bağlanmaz."""

    name = "SANAL"

    def __init__(self, cfg):
        self.cfg = cfg
        self.path = Path(cfg.state_dir) / "sim_hesap.json"
        self.clock_ = SessionClock(cfg)
        if self.path.exists():
            self.acct = json.loads(self.path.read_text())
        else:
            self.acct = {"cash": cfg.budget, "positions": {}}
            self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.acct, indent=2))

    def clock(self):
        return self.clock_.session(now_tr())

    def keep_alive(self):
        pass

    def cash(self):
        return self.acct["cash"]

    def held_qty(self, sym):
        p = self.acct["positions"].get(sym)
        return p["qty"] if p else 0

    def user_holds(self, sym):
        return False

    def buy(self, sym, qty, price):
        # Forex'te slippage_bps alış-satış makasının (spread) yarısıdır.
        px = price * (1 + self.cfg.slippage_bps / 10000)
        fee = buy_fees(px, qty, self.cfg)
        # Kaldıraçlı hesap: alımda para bağlanmaz, sadece ücret düşer.
        if fee > self.acct["cash"]:
            return None
        self.acct["cash"] -= fee
        old = self.acct["positions"].get(sym)
        if old:
            q = old["qty"] + qty
            old["entry"] = (old["entry"] * old["qty"] + px * qty) / q
            old["qty"] = q
        else:
            self.acct["positions"][sym] = {"qty": qty, "entry": px}
        self._save()
        return Fill(qty, px, fee)

    def sell(self, sym, qty, price):
        qty = min(qty, self.held_qty(sym))
        if qty <= 0:
            return None
        pos = self.acct["positions"][sym]
        px = price * (1 - self.cfg.slippage_bps / 10000)
        fee = sell_fees(px, qty, self.cfg)
        self.acct["cash"] += (px - pos["entry"]) * qty * pnl_factor(sym, px, self.cfg) - fee
        pos["qty"] -= qty
        if pos["qty"] <= 1e-9:
            del self.acct["positions"][sym]
        self._save()
        return Fill(qty, px, fee)
