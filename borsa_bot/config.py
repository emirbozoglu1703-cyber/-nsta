"""Ayarlar: config.json + ortam değişkenleri (.env)."""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

FOREX_MAJORS = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDJPY", "USDCHF", "USDCAD"]


@dataclass
class Config:
    # sim  : bilgisayarda sanal para (Yahoo verisi, hesap gerekmez)
    # live : senin MetaTrader 5 hesabın (demo ya da gerçek)
    mode: str = "sim"
    currency: str = "USD"

    budget: float = 5000.0              # sanal modda başlangıç bakiyesi
    risk_per_trade: float = 50.0        # bir işlem zarar kes'e gelirse kaybedilecek en fazla tutar
    max_positions: int = 3              # aynı anda en fazla açık işlem

    max_total_loss: float = 1000.0      # toplam bu kadar zarar ederse bot durur
    max_daily_loss: float = 300.0       # bir günde bu kadar zarar ederse o gün durur

    # Videodaki 1.6 oranı: kâr hedefi / zarar kes = 1.6
    # (Kripto için %16 / %10. Kurlar kriptodan çok daha az oynadığı için
    #  aynı oranı çok daha küçük yüzdelerle kullanıyoruz.)
    take_profit_pct: float = 0.4
    stop_loss_pct: float = 0.25

    # Tepe kilitleme: fiyat en az %trail_activate_pct yükselip hedefe varmadan
    # geri dönerse, tepedeki kârın trail_keep_ratio kadarını cebe koyup çık.
    # (Videoda: 1000 -> 1100 gördü, 1050'de sat.)
    trail_activate_pct: float = 0.2
    trail_keep_ratio: float = 0.5

    # Videodaki bulgu: 15-60 dk tutulan işlemler en kârlısıydı.
    max_hold_minutes: int = 60
    cooldown_minutes: int = 30          # aynı pariteye tekrar girmeden önce bekle

    # Giriş sinyali: "düşeni al, dönüşü yakala"
    bar_minutes: int = 5
    lookback_bars: int = 24             # son 2 saat (5 dk x 24)
    dip_from_high_pct: float = 0.2      # bugünkü tepeden en az %0.2 düşmüş
    rsi_period: int = 14
    rsi_buy_below: float = 30.0         # aşırı satılmış
    # dönüş onayı: son kapanan mum yeşil ve öncekinden yüksek kapanmış olmalı

    loop_seconds: int = 30
    session_open: str = "09:00"         # işlem saatleri, İstanbul (Londra + New York)
    session_close: str = "23:00"
    no_entry_minutes_after_open: int = 15
    flatten_minutes_before_close: int = 10

    # Maliyetler. Çoğu forex hesabında komisyon yok, maliyet makastır (spread).
    commission_pct: float = 0.0         # varsa işlem başı yüzde komisyon
    commission_min: float = 0.0
    slippage_bps: float = 0.6           # sim/backtest: makasın yarısı (0.6 = %0.006)

    symbols: list = field(default_factory=lambda: list(FOREX_MAJORS))
    state_dir: str = "bot_data"

    # MetaTrader 5
    mt5_magic: int = 26111403           # botun emirlerini senin emirlerinden ayıran numara
    mt5_deviation_points: int = 20      # piyasa emrinde kabul edilen en fazla fiyat kayması

    def validate(self):
        if self.mode not in ("sim", "live"):
            raise ValueError("mode sim veya live olmalı")
        if self.stop_loss_pct <= 0 or self.take_profit_pct <= 0:
            raise ValueError("kâr al ve zarar kes yüzdeleri pozitif olmalı")
        if self.risk_per_trade <= 0:
            raise ValueError("risk_per_trade pozitif olmalı")
        if not 0 < self.trail_keep_ratio < 1:
            raise ValueError("trail_keep_ratio 0 ile 1 arasında olmalı")
        if self.mode == "live" and os.environ.get("BOT_LIVE_CONFIRM") != "GERCEK_PARA":
            raise ValueError(
                "Canlı modda bot senin MT5 hesabında işlem yapar. Emin isen "
                ".env dosyasına BOT_LIVE_CONFIRM=GERCEK_PARA ekle."
            )
        return self

    def to_dict(self):
        return asdict(self)


def load_env(path=".env"):
    """Basit .env okuyucu (ek paket gerektirmez). Var olan değişkenleri ezmez."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load_config(path="config.json"):
    cfg = Config()
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    unknown = set(data) - set(cfg.to_dict())
    if unknown:
        raise ValueError(f"config.json içinde bilinmeyen ayar(lar): {sorted(unknown)}")
    for k, v in data.items():
        setattr(cfg, k, v)
    if os.environ.get("BOT_MODE"):
        cfg.mode = os.environ["BOT_MODE"]
    return cfg.validate()
