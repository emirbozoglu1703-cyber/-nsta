"""Ayarlar: config.json + ortam değişkenleri (.env)."""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path

# BIST 100 endeksi (TradingView, Kasım 2026). Endeks her çeyrek güncellenir;
# değişince config.json içindeki "symbols" listesini güncelle.
BIST100 = (
    "AEFES AGHOL AHGAZ AKBNK AKCNS AKFYE AKSA AKSEN ALARK ALBRK ALTNY ANHYT ANSGR "
    "ARCLK ASELS ASTOR AYGAZ BERA BIMAS BINHO BRSAN BRYAT BTCIM CANTE CCOLA CIMSA "
    "CVKMD CWENE DOAS DOHOL ECILC ECZYT EGEEN EGGUB EKGYO ENERY ENJSA ENKAI ENTRA "
    "EREGL EUREN FENER FROTO GARAN GLRMK GLYHO GRSEL GUBRF GWIND HALKB HEKTS ISCTR "
    "ISDMR ISMEN KARSN KATMR KCAER KCHOL KORDS KRDMD LMKDC MAVI MGROS MPARK OBAMS "
    "ODAS OTKAR OYAKC PAHOL PETKM PGSUS RGYAS RYSAS SAHOL SASA SISE SNGYO SOKM "
    "TABGD TAVHL TCELL TCKRC THYAO TKFEN TOASO TRALT TRENJ TRGYO TRMET TSKB TTKOM "
    "TTRAK TUKAS TUPRS TURSG ULKER VAKBN VESTL YKBNK ZOREN"
).split()


@dataclass
class Config:
    # sim  : bilgisayarda sanal para (Yahoo verisi, hesap gerekmez)
    # live : GERÇEK PARA (Deniz Yatırım AlgoLab API)
    mode: str = "sim"

    # Tutarlar Türk lirası.
    budget: float = 50000.0             # botun kullanabileceği en fazla para
    position_size: float = 10000.0      # her alımda harcanacak tutar
    max_positions: int = 4              # aynı anda en fazla kaç hisse

    max_total_loss: float = 10000.0     # toplam bu kadar zarar ederse bot durur
    max_daily_loss: float = 3000.0      # bir günde bu kadar zarar ederse o gün durur

    # Videodaki 1.6 oranı: kâr hedefi / zarar kes = 1.6
    # (Kripto için %16 / %10. Hisseler kriptodan daha az oynadığı için
    #  aynı oranı daha küçük yüzdelerle kullanıyoruz.)
    take_profit_pct: float = 4.0
    stop_loss_pct: float = 2.5

    # Tepe kilitleme: fiyat en az %trail_activate_pct yükselip hedefe varmadan
    # geri dönerse, tepedeki kârın trail_keep_ratio kadarını cebe koyup çık.
    # (Videoda: 1000 -> 1100 gördü, 1050'de sat.)
    trail_activate_pct: float = 2.0
    trail_keep_ratio: float = 0.5

    # Videodaki bulgu: 15-60 dk tutulan işlemler en kârlısıydı.
    max_hold_minutes: int = 60
    cooldown_minutes: int = 30          # aynı hisseye tekrar girmeden önce bekle

    # Giriş sinyali: "düşeni al, dönüşü yakala"
    bar_minutes: int = 5
    lookback_bars: int = 24             # son 2 saat (5 dk x 24)
    dip_from_high_pct: float = 2.0      # bugünkü tepeden en az %2 düşmüş
    rsi_period: int = 14
    rsi_buy_below: float = 30.0         # aşırı satılmış
    # dönüş onayı: son kapanan mum yeşil ve öncekinden yüksek kapanmış olmalı

    loop_seconds: int = 30
    session_open: str = "10:00"         # BIST sürekli işlem seansı (İstanbul saati)
    session_close: str = "18:00"
    no_entry_minutes_after_open: int = 15
    flatten_minutes_before_close: int = 10

    # Komisyon: aracı kurumunun sana verdiği oran (BSMV dahil), işlem başına yüzde.
    # Örnek: binde 0.5 = 0.05. Kendi oranını yaz, sonuçları çok etkiler.
    commission_pct: float = 0.05
    commission_min: float = 0.0         # varsa emir başı en düşük komisyon (TL)
    slippage_bps: float = 5.0           # sim/backtest'te alış-satış kayması (%0.05)

    symbols: list = field(default_factory=lambda: list(BIST100))
    state_dir: str = "bot_data"

    def validate(self):
        if self.mode not in ("sim", "live"):
            raise ValueError("mode sim veya live olmalı")
        if self.position_size > self.budget:
            raise ValueError("position_size bütçeden büyük olamaz")
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
