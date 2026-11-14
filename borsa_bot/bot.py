"""Botun ana döngüsü: her loop_seconds saniyede bir fiyatlara bakar, alır, satar."""

import csv
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import strategy as st
from .broker import AlgoLabBroker, SimBroker
from .market import YahooData, AlgoLabData, now_tr

JOURNAL_FIELDS = ["zaman", "mod", "sembol", "islem", "adet", "fiyat", "ucret",
                  "kar_zarar", "sebep", "sure_dk"]


def algolab_client(cfg):
    from .algolab import AlgoLab
    key = os.environ.get("ALGOLAB_API_KEY")
    if not key:
        raise SystemExit("ALGOLAB_API_KEY .env dosyasında olmalı.")
    return AlgoLab(key, Path(cfg.state_dir) / "algolab_oturum.json")


def make_clients(cfg):
    if cfg.mode == "sim":
        return SimBroker(cfg), YahooData(cfg)
    if cfg.market == "forex":
        from .mt5 import MT5Broker, MT5Client, MT5Data
        client = MT5Client(cfg)
        client.connect()
        return MT5Broker(cfg, client), MT5Data(cfg, client)
    client = algolab_client(cfg)
    client.load_session()
    return AlgoLabBroker(cfg, client), AlgoLabData(cfg, client)


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
        self._bars = {}          # hisse -> kapanmış mumlar (her yeni mumda yenilenir)
        self._bars_key = None

    # ---------- yardımcılar ----------
    def _held_minutes(self, pos, now):
        return (now - datetime.fromisoformat(pos["entry_time"])).total_seconds() / 60

    def _unrealized(self, prices):
        if hasattr(self.broker, "unrealized"):
            return self.broker.unrealized(self.state.d["positions"])
        tot = 0.0
        for sym, p in self.state.d["positions"].items():
            if sym in prices:
                tot += (prices[sym] - p["entry_price"]) * p["qty"] * st.pnl_factor(sym, prices[sym], self.cfg)
        return tot

    def _fmt(self, x):
        return f"{x:.5f}" if self.cfg.market == "forex" and x < 50 else f"{x:.2f}"

    def close_position(self, sym, price, reason, now):
        pos = self.state.d["positions"][sym]
        if "ticket" in pos:
            fill = self.broker.sell(sym, pos["qty"], price, ticket=pos["ticket"])
        else:
            fill = self.broker.sell(sym, pos["qty"], price)
        if fill is None:
            return False
        if getattr(fill, "pnl", None) is not None:   # kurumun hesapladığı net sonuç
            pnl = fill.pnl
        else:
            f = st.pnl_factor(sym, fill.price, self.cfg)
            pnl = ((fill.price - pos["entry_price"]) * fill.qty * f - fill.fee
                   - pos.get("buy_fee", 0) * (fill.qty / pos["qty"]))
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
                        "sembol": sym, "islem": "SAT", "adet": fill.qty,
                        "fiyat": round(fill.price, 4), "ucret": round(fill.fee, 4),
                        "kar_zarar": round(pnl, 2), "sebep": reason, "sure_dk": round(held, 1)})
        sign = "+" if pnl >= 0 else ""
        print(f"  SAT  {sym:<6} {fill.qty:g} @ {self._fmt(fill.price)}  {sign}{pnl:.2f} {self.cfg.currency}  ({reason}, {held:.0f} dk)")
        return True

    def open_position(self, sym, price, sig, now):
        if hasattr(self.broker, "size"):
            qty = self.broker.size(sym, price)
        else:
            qty = st.size_qty(sym, price, self.cfg)
        if qty <= 0:
            return False
        fill = self.broker.buy(sym, qty, price)
        if fill is None:
            return False
        pos = {"qty": fill.qty, "entry_price": fill.price, "peak": fill.price,
               "entry_time": now.isoformat(), "buy_fee": fill.fee}
        if getattr(fill, "ticket", None) is not None:
            pos["ticket"] = fill.ticket
        self.state.d["positions"][sym] = pos
        self.state.d["fees"] += fill.fee
        self.state.save()
        self.state.log({"zaman": now.isoformat(timespec="seconds"), "mod": self.cfg.mode,
                        "sembol": sym, "islem": "AL", "adet": fill.qty,
                        "fiyat": round(fill.price, 4), "ucret": round(fill.fee, 4),
                        "kar_zarar": "", "sebep": f"dip %{sig['dip']} rsi {sig['rsi']}",
                        "sure_dk": ""})
        print(f"  AL   {sym:<6} {fill.qty:g} @ {self._fmt(fill.price)}  "
              f"(düşüş %{sig['dip']}, RSI {sig['rsi']}; hedef {self._fmt(st.target_price(fill.price, self.cfg))}, "
              f"stop {self._fmt(st.stop_price(fill.price, self.cfg))})")
        return True

    def flatten_all(self, prices, reason, now):
        for sym in list(self.state.d["positions"]):
            px = prices.get(sym) or self.state.d["positions"][sym]["entry_price"]
            self.close_position(sym, px, reason, now)

    # ---------- tek tur ----------
    def step(self):
        cfg, d = self.cfg, self.state.d
        now = now_tr()
        is_open, open_, close = self.broker.clock()
        daily = self.state.today(now)
        if not is_open:
            return False
        self.broker.keep_alive()

        # Açık pozisyonların fiyatı her turda, tüm sembollerin mumları ise
        # her yeni 5 dk mum kapanınca bir kez çekilir.
        prices = self.data.prices(list(d["positions"])) if d["positions"] else {}

        # 0) Sunucudaki zarar kes / kâr al ile kapanmış olanları kaydet (MT5)
        if hasattr(self.broker, "is_closed"):
            for sym in list(d["positions"]):
                if self.broker.is_closed(d["positions"][sym]):
                    if not self.close_position(sym, prices.get(sym, 0), "sunucu_sl_tp", now):
                        print(f"  ! {sym} sunucuda kapanmış ama sonucu okunamadı; kayıttan siliniyor")
                        del d["positions"][sym]

        # 1) Açık pozisyonlar: tepe güncelle, çıkış kurallarını uygula
        mins_to_close = (close - now).total_seconds() / 60
        for sym in list(d["positions"]):
            if sym not in prices:
                continue
            pos, px = d["positions"][sym], prices[sym]
            pos["peak"] = max(pos["peak"], px)
            trail = st.trail_price(pos["entry_price"], pos["peak"], cfg)
            if trail is not None and hasattr(self.broker, "update_stop"):
                self.broker.update_stop(sym, pos.get("ticket"), trail)
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
        if d["realized_pnl"] + unreal <= -cfg.max_total_loss and d["halted"] != "toplam_limit":
            print(f"  !!! Toplam zarar limiti ({cfg.max_total_loss:.0f} {cfg.currency}) aşıldı. Her şey satılıyor, bot DURDU.")
            self.flatten_all(prices, "toplam_limit", now)
            d["halted"] = "toplam_limit"
        elif daily["pnl"] + unreal <= -cfg.max_daily_loss and not d["halted"]:
            print(f"  !! Günlük zarar limiti ({cfg.max_daily_loss:.0f} {cfg.currency}) aşıldı. Bugünlük bu kadar.")
            self.flatten_all(prices, "gunluk_limit", now)
            d["halted"] = "gunluk_limit"
        self.state.save()

        # 3) Yeni alımlar
        if self._may_enter(now, open_, close):
            key = (now - open_).total_seconds() // (cfg.bar_minutes * 60)
            if key != self._bars_key:
                self._bars = self.data.bars(cfg.symbols, now)
                self._bars_key = key
                self._enter(self._bars, now)

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

    def _enter(self, bars_by_sym, now):
        cfg, d = self.cfg, self.state.d
        invested = sum(p["qty"] * p["entry_price"] for p in d["positions"].values())
        budget = cfg.budget + min(0.0, d["realized_pnl"])  # zarar ettikçe bütçe küçülür

        cands = []
        for sym, bars in bars_by_sym.items():
            if sym in d["positions"] or not bars:
                continue
            last = d["last_exit"].get(sym)
            if last and now - datetime.fromisoformat(last) < timedelta(minutes=cfg.cooldown_minutes):
                continue
            sig = st.entry_signal(bars, cfg)
            if sig:
                cands.append((sig["score"], sym, sig))
        if not cands:
            return
        cands.sort(reverse=True)
        cash = self.broker.cash()

        for _, sym, sig in cands:
            if len(d["positions"]) >= cfg.max_positions:
                break
            if st.is_leveraged(cfg):
                if cash <= 0:
                    break
            elif invested + cfg.position_size > budget or cfg.position_size > cash:
                break
            # Kullanıcının kendi açtığı işlemlere / elindeki hisselere dokunma.
            if cfg.mode != "sim" and self.broker.user_holds(sym):
                continue
            px = self.data.prices([sym]).get(sym)
            if not px:
                continue
            if self.open_position(sym, px, sig, now) and not st.is_leveraged(cfg):
                cost = d["positions"][sym]["qty"] * d["positions"][sym]["entry_price"]
                invested += cost
                cash -= cost

    def _status(self, prices, now):
        d = self.state.d
        unreal = self._unrealized(prices)
        parts = []
        for sym, p in d["positions"].items():
            if sym in prices:
                g = (prices[sym] / p["entry_price"] - 1) * 100
                parts.append(f"{sym} {g:+.2f}%")
        halted = f"  [DURDU: {d['halted']}]" if d["halted"] else ""
        c = self.cfg.currency
        print(f"[{now:%H:%M:%S}] {self.broker.name} | gerçekleşen {d['realized_pnl']:+.2f} {c} | "
              f"bugün {d['daily']['pnl']:+.2f} {c} | açık {unreal:+.2f} {c} | "
              f"{', '.join(parts) or 'pozisyon yok'}{halted}", flush=True)

    # ---------- döngü ----------
    def run(self):
        cfg = self.cfg
        what = "Forex" if cfg.market == "forex" else "BIST"
        print(f"{what} botu başladı. Mod: {self.broker.name}, bütçe {cfg.budget:.0f} {cfg.currency}, "
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
                stamp = now_tr().strftime("%Y-%m-%d %H")
                if idle_logged != stamp:
                    print(f"[{now_tr():%Y-%m-%d %H:%M}] Borsa kapalı, bekliyorum...", flush=True)
                    idle_logged = stamp
                time.sleep(60)
            else:
                time.sleep(cfg.loop_seconds)
