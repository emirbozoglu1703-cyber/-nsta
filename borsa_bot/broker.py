"""Aracı kurum: sanal (SimBroker) veya Deniz Yatırım AlgoLab (gerçek para)."""

import json
from pathlib import Path

from .market import SessionClock, now_tr
from .strategy import buy_fees, sell_fees, is_leveraged, pnl_factor


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
        # Hisse: paranın tamamı bağlanır. Forex (kaldıraçlı): sadece ücret düşer.
        cost = fee if is_leveraged(self.cfg) else px * qty + fee
        if cost > self.acct["cash"]:
            return None
        self.acct["cash"] -= cost
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
        if is_leveraged(self.cfg):
            self.acct["cash"] += (px - pos["entry"]) * qty * pnl_factor(sym, px, self.cfg) - fee
        else:
            self.acct["cash"] += px * qty - fee
        pos["qty"] -= qty
        if pos["qty"] <= 1e-9:
            del self.acct["positions"][sym]
        self._save()
        return Fill(qty, px, fee)


class AlgoLabBroker:
    """GERÇEK PARA. Piyasa emri gönderir, dolmasını bekler."""

    name = "DENIZ-ALGOLAB (GERÇEK)"

    def __init__(self, cfg, client):
        self.cfg, self.c = cfg, client
        self.clock_ = SessionClock(cfg)

    def clock(self):
        return self.clock_.session(now_tr())

    def keep_alive(self):
        self.c.keep_alive()

    def cash(self):
        return self.c.cash()

    def held_qty(self, sym):
        return self.c.positions().get(sym, 0)

    def user_holds(self, sym):
        # Bot bu hisseyi şu an tutmuyorsa (çağrılan yerde zaten öyle), hesaptaki lotlar senindir.
        return self.held_qty(sym) > 0

    def _order(self, sym, qty, side):
        try:
            oid = self.c.send_market_order(sym, side, qty)
        except Exception as e:
            print(f"  ! {side} emri gönderilemedi ({sym}): {e}")
            return None
        filled, px = self.c.wait_fill(oid)
        if filled <= 0 or px <= 0:
            print(f"  ! {side} emri dolmadı ({sym}, ref {oid})")
            return None
        fee = sell_fees(px, filled, self.cfg) if side == "SELL" else buy_fees(px, filled, self.cfg)
        return Fill(filled, px, fee)

    def buy(self, sym, qty, price):
        return self._order(sym, qty, "BUY")

    def sell(self, sym, qty, price):
        qty = min(qty, self.held_qty(sym))
        if qty <= 0:
            return None
        return self._order(sym, qty, "SELL")
