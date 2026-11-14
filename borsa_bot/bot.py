"""Botun ana döngüsü: her loop_seconds saniyede bir fiyatlara bakar, alır, satar."""

import csv
import json
import math
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import strategy as st
from .broker import AlpacaBroker, SimBroker
from .market import AlpacaData, YahooData, now_ny, NY

JOURNAL_FIELDS = ["zaman", "mod", "hisse", "islem", "adet", "fiyat", "ucret",
                  "kar_zarar", "sebep", "sure_dk"]


def make_clients(cfg):
    if cfg.mode == "sim":
        return SimBroker(cfg), YahooData(cfg.bar_minutes)
    key, secret = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("ALPACA_API_KEY ve ALPACA_SECRET_KEY .env dosyasında olmalı.")
    broker = AlpacaBroker(cfg, key, secret, paper=(cfg.mode == "paper"))
    return broker, AlpacaData(key, secret, cfg.bar_minutes)


class State:
    def __init__(self, cfg):
        self.dir = Path(cfg.state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"durum_{cfg.mode}.json"
        self.journal = self.dir / f"islemler_{cfg.mode}.csv"
        if self.path.exists():
            self.d = json.loads(self.path.read_text())
        else:
            self.d = {"realized_pnl": 0.0, "fees": 0.0, "daily": {"date": "", "pnl": 0.0},
                      "halted": None, "positions": {}, "last_exit": {}, "trades": 0}
            self.save()

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.d, indent=2, ensure_ascii=False))
        tmp.replace(self.path)

    def log(self, row):
        new = not self.journal.exists()
        with self.journal.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=JOURNAL_FIELDS)
            if new:
                w.writeheader()
            w.writerow(row)

    def today(self, now):
        day = now.strftime("%Y-%m-%d")
        if self.d["daily"]["date"] != day:
            self.d["daily"] = {"date": day, "pnl": 0.0}
            if self.d["halted"] == "gunluk_limit":
                self.d["halted"] = None
        return self.d["daily"]


class Bot:
    def __init__(self, cfg):
        self.cfg = cfg
        self.broker, self.data = make_clients(cfg)
        self.state = State(cfg)

    # ---------- yardımcılar ----------
    def _held_minutes(self, pos, now):
        return (now - datetime.fromisoformat(pos["entry_time"])).total_seconds() / 60

    def _unrealized(self, prices):
        tot = 0.0
        for sym, p in self.state.d["positions"].items():
            if sym in prices:
                tot += (prices[sym] - p["entry_price"]) * p["qty"]
        return tot

    def close_position(self, sym, price, reason, now):
        pos = self.state.d["positions"][sym]
        fill = self.broker.sell(sym, pos["qty"], price)
        if fill is None:
            return False
        pnl = (fill.price - pos["entry_price"]) * fill.qty - fill.fee - pos.get("buy_fee", 0) * (fill.qty / pos["qty"])
        held = self._held_minutes(pos, now)
        d = self.state.d
        d["realized_pnl"] += pnl
        d["fees"] += fill.fee
        self.state.today(now)["pnl"] += pnl
        d["trades"] += 1
        d["last_exit"][sym] = now.isoformat()
        left = pos["qty"] - fill.qty
        if left > 1e-9:
            pos["qty"] = left
        else:
            del d["positions"][sym]
        self.state.save()
        self.state.log({"zaman": now.isoformat(timespec="seconds"), "mod": self.cfg.mode,
                        "hisse": sym, "islem": "SAT", "adet": fill.qty,
                        "fiyat": round(fill.price, 4), "ucret": round(fill.fee, 4),
                        "kar_zarar": round(pnl, 2), "sebep": reason, "sure_dk": round(held, 1)})
        sign = "+" if pnl >= 0 else ""
        print(f"  SAT  {sym:<5} {fill.qty:g} adet @ {fill.price:.2f}  {sign}{pnl:.2f} $  ({reason}, {held:.0f} dk)")
        return True

    def open_position(self, sym, price, sig, now):
        qty = math.floor(self.cfg.position_size_usd / price)
        if qty < 1:
            return False
        fill = self.broker.buy(sym, qty, price)
        if fill is None:
            return False
        self.state.d["positions"][sym] = {
            "qty": fill.qty, "entry_price": fill.price, "peak": fill.price,
            "entry_time": now.isoformat(), "buy_fee": fill.fee}
        self.state.d["fees"] += fill.fee
        self.state.save()
        self.state.log({"zaman": now.isoformat(timespec="seconds"), "mod": self.cfg.mode,
                        "hisse": sym, "islem": "AL", "adet": fill.qty,
                        "fiyat": round(fill.price, 4), "ucret": round(fill.fee, 4),
                        "kar_zarar": "", "sebep": f"dip %{sig['dip']} rsi {sig['rsi']}",
                        "sure_dk": ""})
        print(f"  AL   {sym:<5} {fill.qty:g} adet @ {fill.price:.2f}  "
              f"(düşüş %{sig['dip']}, RSI {sig['rsi']}; hedef {st.target_price(fill.price, self.cfg):.2f}, "
              f"stop {st.stop_price(fill.price, self.cfg):.2f})")
        return True

    def flatten_all(self, prices, reason, now):
        for sym in list(self.state.d["positions"]):
            px = prices.get(sym) or self.state.d["positions"][sym]["entry_price"]
            self.close_position(sym, px, reason, now)

    # ---------- tek tur ----------
    def step(self):
        cfg, d = self.cfg, self.state.d
        now = now_ny()
        is_open, open_, close = self.broker.clock()
        daily = self.state.today(now)
        if not is_open:
            return False

        symbols = sorted(set(cfg.symbols) | set(d["positions"]))
        snap = self.data.snapshot(symbols, now)
        prices = {s: v[1] for s, v in snap.items()}

        # 1) Açık pozisyonlar: tepe güncelle, çıkış kurallarını uygula
        mins_to_close = (close - now).total_seconds() / 60
        for sym in list(d["positions"]):
            if sym not in prices:
                continue
            pos, px = d["positions"][sym], prices[sym]
            pos["peak"] = max(pos["peak"], px)
            if mins_to_close <= cfg.flatten_minutes_before_close:
                reason = "kapanis"
            else:
                reason = st.exit_reason(pos["entry_price"], pos["peak"], px,
                                        self._held_minutes(pos, now), cfg)
            if reason:
                self.close_position(sym, px, reason, now)
        self.state.save()

        # 2) Zarar limitleri
        unreal = self._unrealized(prices)
        if d["realized_pnl"] + unreal <= -cfg.max_total_loss_usd and d["halted"] != "toplam_limit":
            print(f"  !!! Toplam zarar limiti ({cfg.max_total_loss_usd} $) aşıldı. Her şey satılıyor, bot DURDU.")
            self.flatten_all(prices, "toplam_limit", now)
            d["halted"] = "toplam_limit"
        elif daily["pnl"] + unreal <= -cfg.max_daily_loss_usd and not d["halted"]:
            print(f"  !! Günlük zarar limiti ({cfg.max_daily_loss_usd} $) aşıldı. Bugünlük bu kadar.")
            self.flatten_all(prices, "gunluk_limit", now)
            d["halted"] = "gunluk_limit"
        self.state.save()

        # 3) Yeni alımlar
        if self._may_enter(now, open_, close):
            self._enter(snap, prices, now)

        self._status(prices, now)
        return True

    def _may_enter(self, now, open_, close):
        cfg, d = self.cfg, self.state.d
        if d["halted"]:
            return False
        if now < open_ + timedelta(minutes=cfg.no_entry_minutes_after_open):
            return False
        # kapanışa yakın yeni işlem açma (en az 15 dk tutabilecek kadar zaman kalsın)
        if (close - now) < timedelta(minutes=cfg.flatten_minutes_before_close + 15):
            return False
        return len(d["positions"]) < cfg.max_positions

    def _enter(self, snap, prices, now):
        cfg, d = self.cfg, self.state.d
        acct = self.broker.account(prices)
        if cfg.respect_pdt and cfg.mode != "sim" and acct["equity"] < 25000 \
                and acct["daytrade_count"] >= 3:
            print("  (PDT: 5 iş gününde 3 gün içi işlem sınırı dolu, yeni alım yok)")
            return
        invested = sum(p["qty"] * p["entry_price"] for p in d["positions"].values())
        budget = cfg.budget_usd + min(0.0, d["realized_pnl"])  # zarar ettikçe bütçe küçülür
        cash = acct.get("buying_power", acct["cash"]) if cfg.mode != "sim" else acct["cash"]

        cands = []
        for sym, (bars, px) in snap.items():
            if sym in d["positions"]:
                continue
            last = d["last_exit"].get(sym)
            if last and now - datetime.fromisoformat(last) < timedelta(minutes=cfg.cooldown_minutes):
                continue
            # sinyal sadece bugünün mumlarıyla + önceki günlerin geçmişiyle hesaplanır
            sig = st.entry_signal(bars, cfg)
            if sig:
                cands.append((sig["score"], sym, px, sig))
        cands.sort(reverse=True)

        for _, sym, px, sig in cands:
            if len(d["positions"]) >= cfg.max_positions:
                break
            if invested + cfg.position_size_usd > budget or cfg.position_size_usd > cash:
                break
            # Kullanıcının kendi elindeki hisselere dokunma.
            if cfg.mode != "sim" and self.broker.held_qty(sym) > 0:
                continue
            if self.open_position(sym, px, sig, now):
                invested += d["positions"][sym]["qty"] * d["positions"][sym]["entry_price"]
                cash -= d["positions"][sym]["qty"] * d["positions"][sym]["entry_price"]

    def _status(self, prices, now):
        d = self.state.d
        unreal = self._unrealized(prices)
        parts = []
        for sym, p in d["positions"].items():
            if sym in prices:
                g = (prices[sym] / p["entry_price"] - 1) * 100
                parts.append(f"{sym} {g:+.2f}%")
        halted = f"  [DURDU: {d['halted']}]" if d["halted"] else ""
        print(f"[{now:%H:%M:%S}] {self.broker.name} | gerçekleşen {d['realized_pnl']:+.2f} $ | "
              f"bugün {d['daily']['pnl']:+.2f} $ | açık {unreal:+.2f} $ | "
              f"{', '.join(parts) or 'pozisyon yok'}{halted}", flush=True)

    # ---------- döngü ----------
    def run(self):
        cfg = self.cfg
        print(f"Borsa botu başladı. Mod: {self.broker.name}, bütçe {cfg.budget_usd:.0f} $, "
              f"kâr al %{cfg.take_profit_pct}, zarar kes %{cfg.stop_loss_pct}, "
              f"tepe kilidi %{cfg.trail_activate_pct}/{int(cfg.trail_keep_ratio*100)}%")
        if cfg.mode == "live":
            print("*** DİKKAT: GERÇEK PARA İLE İŞLEM YAPILIYOR ***")
        idle_logged = None
        while True:
            try:
                active = self.step()
            except Exception as e:  # ağ hatası vb. botu öldürmesin
                print(f"  ! hata: {e}", flush=True)
                active = True
            if not active:
                stamp = now_ny().strftime("%Y-%m-%d %H")
                if idle_logged != stamp:
                    print(f"[{now_ny():%Y-%m-%d %H:%M}] Borsa kapalı, bekliyorum...", flush=True)
                    idle_logged = stamp
                time.sleep(60)
            else:
                time.sleep(cfg.loop_seconds)
