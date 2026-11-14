"""Ayarlar: config.json + ortam değişkenleri (.env)."""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

DEFAULT_SYMBOLS = [
    # Çok işlem gören, makas (spread) dar ABD hisseleri ve ETF'ler.
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AMD",
    "NFLX", "AVGO", "PLTR", "UBER", "COIN", "SHOP", "CRM", "ORCL",
    "INTC", "MU", "BAC", "JPM", "XOM", "DIS", "SOFI", "SPY", "QQQ",
]


@dataclass
class Config:
    # sim   : bilgisayarda sanal para (anahtar gerekmez, Yahoo verisi)
    # paper : Alpaca'nın sanal hesabı (ücretsiz anahtar gerekir)
    # live  : GERÇEK PARA (Alpaca canlı hesap)
    mode: str = "sim"

    budget_usd: float = 5000.0          # botun kullanabileceği en fazla para
    position_size_usd: float = 1000.0   # her alımda harcanacak tutar
    max_positions: int = 4              # aynı anda en fazla kaç hisse

    max_total_loss_usd: float = 1000.0  # toplam bu kadar zarar ederse bot durur
    max_daily_loss_usd: float = 300.0   # bir günde bu kadar zarar ederse o gün durur

    # Videodaki 1.6 oranı: kâr hedefi / zarar kes = 1.6
    # (Kripto için %16 / %10. Hisseler kriptodan çok daha az oynadığı için
    #  aynı oranı daha küçük yüzdelerle kullanıyoruz.)
    take_profit_pct: float = 4.0
    stop_loss_pct: float = 2.5

    # Tepe kilitleme (trailing): fiyat en az %trail_activate_pct yükselip
    # hedefe varmadan geri dönerse, tepedeki kârın trail_keep_ratio kadarını
    # cebe koyup çık. (Videoda: 1000 -> 1100 gördü, 1050'de sat.)
    trail_activate_pct: float = 2.0
    trail_keep_ratio: float = 0.5

    # Videodaki bulgu: 15-60 dk tutulan işlemler en kârlısıydı.
    max_hold_minutes: int = 60
    cooldown_minutes: int = 30          # aynı hisseye tekrar girmeden önce bekle

    # Giriş sinyali: "düşeni al, dönüşü yakala"
    bar_minutes: int = 5
    lookback_bars: int = 24             # son 2 saat (5 dk x 24)
    dip_from_high_pct: float = 2.0      # son 2 saatin tepesinden en az %2 düşmüş
    rsi_period: int = 14
    rsi_buy_below: float = 30.0         # aşırı satılmış
    # dönüş onayı: son kapanan mum yeşil ve öncekinden yüksek kapanmış olmalı

    loop_seconds: int = 30
    no_entry_minutes_after_open: int = 15
    flatten_minutes_before_close: int = 10

    # Komisyon / ücretler. Alpaca'da hisse komisyonu 0 $.
    # Satışlarda düzenleyici ücretler var (SEC + FINRA TAF), çok küçük.
    commission_per_trade_usd: float = 0.0
    commission_pct: float = 0.0         # işlem başı yüzde komisyon (Binance spot ~0.1)
    sec_fee_rate: float = 0.0000278     # satış tutarı x oran
    taf_per_share: float = 0.000166     # satılan hisse başı, en fazla 8.30 $
    slippage_bps: float = 2.0           # sim/backtest'te alış-satış kayması (0.02%)

    # ABD'de 25.000 $ altı marjin hesaplarda 5 iş gününde en fazla 3 gün içi
    # işlem (PDT kuralı). True ise bot bu sınıra gelince yeni işlem açmaz.
    respect_pdt: bool = True

    symbols: list = field(default_factory=lambda: list(DEFAULT_SYMBOLS))
    state_dir: str = "bot_data"

    def validate(self):
        if self.mode not in ("sim", "paper", "live"):
            raise ValueError("mode sim, paper veya live olmalı")
        if self.position_size_usd > self.budget_usd:
            raise ValueError("position_size_usd bütçeden büyük olamaz")
        if self.stop_loss_pct <= 0 or self.take_profit_pct <= 0:
            raise ValueError("kâr al ve zarar kes yüzdeleri pozitif olmalı")
        if not 0 < self.trail_keep_ratio < 1:
            raise ValueError("trail_keep_ratio 0 ile 1 arasında olmalı")
        if self.mode == "live" and os.environ.get("BOT_LIVE_CONFIRM") != "GERCEK_PARA":
            raise ValueError(
                "Canlı modda bot gerçek parayla işlem yapar. Emin isen "
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
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        known = set(cfg.to_dict())
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"config.json içinde bilinmeyen ayar(lar): {sorted(unknown)}")
        for k, v in data.items():
            setattr(cfg, k, v)
    if os.environ.get("BOT_MODE"):
        cfg.mode = os.environ["BOT_MODE"]
    return cfg.validate()
