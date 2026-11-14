"""Alım ve satım kuralları. Saf fonksiyonlar: hem canlı bot hem backtest kullanır."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Bar:
    t: datetime   # mumun açılış zamanı (New York saati)
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


def rsi(closes, period=14):
    """Wilder RSI. Yeterli veri yoksa None."""
    if len(closes) < period + 1:
        return None
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    avg_g, avg_l = gains / period, losses / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(d, 0)) / period
        avg_l = (avg_l * (period - 1) + max(-d, 0)) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - 100 / (1 + rs)


def entry_signal(bars, cfg):
    """Kapanmış mumlara bakar. Sinyal varsa {'score':..., 'rsi':..., 'dip':...}, yoksa None.

    Kural (videodaki "düşen coini al" fikrinin hisse hali):
      1. Son lookback_bars mumun tepesinden en az dip_from_high_pct düşmüş.
      2. Son birkaç mumdan birinde RSI aşırı satılmış bölgeye (rsi_buy_below) inmiş.
      3. Dönüş onayı: son mum yeşil ve bir öncekinden yüksek kapanmış.
    """
    need = max(cfg.lookback_bars, cfg.rsi_period + 2) + 1
    if len(bars) < need:
        return None
    last, prev = bars[-1], bars[-2]
    # Tepe sadece bugünün mumlarından: dünkü kapanışa göre gece açılan
    # boşluk (gap) "düşüş" sayılmasın.
    window = [b for b in bars[-cfg.lookback_bars:] if b.t.date() == last.t.date()]
    if len(window) < 4:
        return None
    high = max(b.h for b in window)
    dip = (high - last.c) / high * 100
    if dip < cfg.dip_from_high_pct:
        return None
    closes = [b.c for b in bars]
    recent_rsi = [rsi(closes[: len(closes) - k], cfg.rsi_period) for k in range(0, 3)]
    recent_rsi = [r for r in recent_rsi if r is not None]
    if not recent_rsi or min(recent_rsi) > cfg.rsi_buy_below:
        return None
    if not (last.c > last.o and last.c > prev.c):
        return None
    # Daha çok düşmüş ve daha çok aşırı satılmış olan önce.
    score = dip + (cfg.rsi_buy_below - min(recent_rsi))
    return {"score": round(score, 3), "rsi": round(min(recent_rsi), 1), "dip": round(dip, 2)}


def exit_reason(entry_price, peak_price, price, held_minutes, cfg):
    """Pozisyondan çıkılmalı mı? Çıkış sebebi ya da None.

    Sıra önemli: önce zarar kes, sonra kâr al, sonra tepe kilidi, en son süre.
    """
    eps = 1e-9  # kayan nokta: 1160/1000 tam %16 çıkmayabilir
    gain = (price / entry_price - 1) * 100
    peak_gain = (peak_price / entry_price - 1) * 100
    if gain <= -cfg.stop_loss_pct + eps:
        return "zarar_kes"
    if gain >= cfg.take_profit_pct - eps:
        return "kar_al"
    if peak_gain >= cfg.trail_activate_pct - eps and gain <= peak_gain * cfg.trail_keep_ratio + eps:
        return "tepe_kilidi"
    if held_minutes >= cfg.max_hold_minutes:
        return "sure_doldu"
    return None


def stop_price(entry_price, cfg):
    return entry_price * (1 - cfg.stop_loss_pct / 100)


def target_price(entry_price, cfg):
    return entry_price * (1 + cfg.take_profit_pct / 100)


def trail_price(entry_price, peak_price, cfg):
    """Tepe kilidi devredeyse çıkış fiyatı, değilse None."""
    peak_gain = peak_price / entry_price - 1
    if peak_gain * 100 < cfg.trail_activate_pct:
        return None
    return entry_price * (1 + peak_gain * cfg.trail_keep_ratio)


def commission(price, qty, cfg):
    """Bir alış ya da satışın komisyonu (TL)."""
    if qty <= 0:
        return 0.0
    return max(price * qty * cfg.commission_pct / 100, cfg.commission_min)


def sell_fees(price, qty, cfg):
    return commission(price, qty, cfg)


def buy_fees(price, qty, cfg):
    return commission(price, qty, cfg)
