"""Geçmiş 5 dakikalık mumlarla stratejiyi dener (Yahoo, son ~60 gün).

Videoda Claude'un dediği gibi: tek bir gecenin kârı şans olabilir, sistemi
günlerce test etmek lazım. Bu modül, botun aynı kurallarını geçmiş veride
mum mum oynatır ve dürüst bir rapor verir.
"""

import math
from collections import defaultdict
from datetime import timedelta, time as dtime

from . import strategy as st
from .market import YahooData

OPEN_T, CLOSE_T = dtime(9, 30), dtime(16, 0)


def fetch(cfg, range_="60d"):
    yd = YahooData(cfg.bar_minutes)
    out = {}
    for sym in cfg.symbols:
        try:
            bars = [b for b in yd.bars(sym, range_) if OPEN_T <= b.t.time() < CLOSE_T]
        except Exception as e:
            print(f"  ! {sym}: {e}")
            continue
        if bars:
            out[sym] = bars
    return out


def run(cfg, data):
    """Portföy seviyesinde simülasyon. data: {sym: [Bar,...]}"""
    step = timedelta(minutes=cfg.bar_minutes)
    slip = cfg.slippage_bps / 10000
    idx = {s: {b.t: i for i, b in enumerate(bars)} for s, bars in data.items()}
    times = sorted({b.t for bars in data.values() for b in bars})

    cash = cfg.budget_usd
    positions = {}       # sym -> dict(qty, entry, peak, t, buy_fee)
    last_exit = {}
    trades = []
    realized = 0.0
    daily = defaultdict(float)
    halted_total = False
    halted_day = None
    equity_curve = []

    def close(sym, px, reason, t_close):
        nonlocal cash, realized
        p = positions.pop(sym)
        fill = px * (1 - slip)
        fee = st.sell_fees(fill, p["qty"], cfg)
        pnl = (fill - p["entry"]) * p["qty"] - fee - p["buy_fee"]
        cash += fill * p["qty"] - fee
        realized += pnl
        daily[t_close.date()] += pnl
        last_exit[sym] = t_close
        trades.append({"sym": sym, "pnl": pnl, "reason": reason,
                       "fees": fee + p["buy_fee"],
                       "mins": (t_close - p["t"]).total_seconds() / 60,
                       "day": t_close.date()})

    for t in times:
        now = t + step                          # bu mum kapandı, şimdiki an
        close_dt = t.replace(hour=16, minute=0)
        open_dt = t.replace(hour=9, minute=30)
        day = t.date()

        # --- çıkışlar (mum içi: önce stop, sonra tepe kilidi, sonra hedef) ---
        for sym in list(positions):
            i = idx[sym].get(t)
            if i is None:
                continue
            b = data[sym][i]
            p = positions[sym]
            stop = st.stop_price(p["entry"], cfg)
            tgt = st.target_price(p["entry"], cfg)
            trail = st.trail_price(p["entry"], p["peak"], cfg)
            if b.l <= stop:
                close(sym, min(b.o, stop), "zarar_kes", now)
                continue
            if trail is not None and b.l <= trail:
                close(sym, min(b.o, trail), "tepe_kilidi", now)
                continue
            if b.h >= tgt:
                close(sym, max(b.o, tgt), "kar_al", now)
                continue
            p["peak"] = max(p["peak"], b.h)
            trail = st.trail_price(p["entry"], p["peak"], cfg)
            if trail is not None and b.c <= trail:
                close(sym, b.c, "tepe_kilidi", now)
                continue
            if (now - p["t"]).total_seconds() / 60 >= cfg.max_hold_minutes:
                close(sym, b.c, "sure_doldu", now)
                continue
            if (close_dt - now) <= timedelta(minutes=cfg.flatten_minutes_before_close):
                close(sym, b.c, "kapanis", now)

        # --- limitler ---
        unreal = 0.0
        for sym, p in positions.items():
            i = idx[sym].get(t)
            if i is not None:
                unreal += (data[sym][i].c - p["entry"]) * p["qty"]
        if not halted_total and realized + unreal <= -cfg.max_total_loss_usd:
            for sym in list(positions):
                i = idx[sym].get(t)
                close(sym, data[sym][i].c if i is not None else positions[sym]["entry"],
                      "toplam_limit", now)
            halted_total = True
        if halted_day != day and daily[day] + unreal <= -cfg.max_daily_loss_usd:
            for sym in list(positions):
                i = idx[sym].get(t)
                close(sym, data[sym][i].c if i is not None else positions[sym]["entry"],
                      "gunluk_limit", now)
            halted_day = day

        equity_curve.append(cash + sum(
            (data[s][idx[s][t]].c if t in idx[s] else p["entry"]) * p["qty"]
            for s, p in positions.items()))

        # --- girişler ---
        if halted_total or halted_day == day:
            continue
        if now < open_dt + timedelta(minutes=cfg.no_entry_minutes_after_open):
            continue
        if (close_dt - now) < timedelta(minutes=cfg.flatten_minutes_before_close + 15):
            continue
        if len(positions) >= cfg.max_positions:
            continue
        budget = cfg.budget_usd + min(0.0, realized)
        invested = sum(p["qty"] * p["entry"] for p in positions.values())
        cands = []
        for sym, bars in data.items():
            if sym in positions:
                continue
            i = idx[sym].get(t)
            if i is None:
                continue
            le = last_exit.get(sym)
            if le and now - le < timedelta(minutes=cfg.cooldown_minutes):
                continue
            hist = bars[max(0, i - 200): i + 1]
            sig = st.entry_signal(hist, cfg)
            if sig:
                cands.append((sig["score"], sym, bars[i].c))
        cands.sort(reverse=True)
        for _, sym, px in cands:
            if len(positions) >= cfg.max_positions:
                break
            if invested + cfg.position_size_usd > budget:
                break
            fill = px * (1 + slip)
            qty = math.floor(cfg.position_size_usd / fill)
            fee = st.buy_fees(fill, qty, cfg)
            if qty < 1 or fill * qty + fee > cash:
                continue
            cash -= fill * qty + fee
            invested += fill * qty
            positions[sym] = {"qty": qty, "entry": fill, "peak": fill, "t": now, "buy_fee": fee}

    # kalanları son fiyattan kapat
    for sym in list(positions):
        close(sym, data[sym][-1].c, "test_sonu", data[sym][-1].t + step)

    return {"trades": trades, "realized": realized, "equity_curve": equity_curve,
            "days": len({t.date() for t in times}), "halted_total": halted_total}


def report(cfg, res):
    tr = res["trades"]
    lines = []
    p = lines.append
    p(f"Test süresi: {res['days']} işlem günü, {len(cfg.symbols)} hisse")
    p(f"Başlangıç bütçesi: {cfg.budget_usd:.0f} $  |  kâr al %{cfg.take_profit_pct}, "
      f"zarar kes %{cfg.stop_loss_pct}, tepe kilidi %{cfg.trail_activate_pct}")
    if not tr:
        p("Hiç işlem olmadı.")
        return "\n".join(lines)
    wins = [t for t in tr if t["pnl"] > 0]
    fees = sum(t["fees"] for t in tr)
    gross = sum(t["pnl"] + t["fees"] for t in tr)
    p(f"İşlem sayısı: {len(tr)}  |  kazanan: %{len(wins) / len(tr) * 100:.1f}")
    p(f"Ücretler öncesi kâr/zarar: {gross:+.2f} $")
    p(f"Ödenen ücret/komisyon:     {fees:.2f} $")
    p(f"NET kâr/zarar:             {res['realized']:+.2f} $  "
      f"(%{res['realized'] / cfg.budget_usd * 100:+.2f})")
    eq = res["equity_curve"]
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = max(mdd, peak - v)
    p(f"En büyük düşüş (drawdown): {mdd:.2f} $")
    if res["halted_total"]:
        p("!! Toplam zarar limitine takıldı, bot durdu.")

    p("\nSüreye göre (videodaki 0-15 / 15-60 dk analizi):")
    for name, lo, hi in (("0-15 dk", 0, 15), ("15-60 dk", 15, 60.01), ("60+ dk", 60.01, 1e9)):
        g = [t for t in tr if lo <= t["mins"] < hi]
        if g:
            p(f"  {name:<9} {len(g):>4} işlem  net {sum(t['pnl'] for t in g):+9.2f} $  "
              f"kazanan %{sum(t['pnl'] > 0 for t in g) / len(g) * 100:.0f}")

    p("\nÇıkış sebebine göre:")
    by = defaultdict(list)
    for t in tr:
        by[t["reason"]].append(t["pnl"])
    for k, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
        p(f"  {k:<13} {len(v):>4} işlem  net {sum(v):+9.2f} $")

    by_sym = defaultdict(float)
    for t in tr:
        by_sym[t["sym"]] += t["pnl"]
    best = max(by_sym.items(), key=lambda kv: kv[1])
    p(f"\nEn çok kazandıran: {best[0]} ({best[1]:+.2f} $). "
      f"Onsuz net: {res['realized'] - best[1]:+.2f} $")
    if res["realized"] > 0 and best[1] > res["realized"] * 0.5:
        p("  Uyarı: kârın yarıdan fazlası tek hisseden. Videodaki gibi bu şans olabilir.")
    return "\n".join(lines)
