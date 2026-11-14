"""MetaTrader 5 bağlantısı: senin forex hesabın üzerinden işlem.

Nasıl çalışır:
  - Bilgisayarında (Windows) MetaTrader 5 programı kurulu ve açık olmalı.
  - Bot, MetaQuotes'un resmi `MetaTrader5` Python paketiyle o programa bağlanır,
    .env dosyasındaki hesap no / şifre / sunucu ile hesabına giriş yapar.
  - Şifre hiçbir yere gönderilmez; sadece senin bilgisayarındaki MT5'e verilir.

Güvenlik:
  - Botun her emri `mt5_magic` numarasını taşır. Bot sadece bu numaralı
    pozisyonları yönetir; senin elle açtığın işlemlere dokunmaz ve senin açık
    pozisyonun olan pariteye girmez.
  - Zarar kes (SL) ve kâr al (TP) emirle birlikte sunucuya yazılır. Bot ya da
    bilgisayar kapansa bile korumalar sunucuda çalışır. Tepe kilidi devreye
    girince bot SL'yi yukarı taşır.
"""

import os
import time
from datetime import datetime, timezone

from .market import SessionClock, TZ, now_tr, closed_only
from .strategy import Bar


def load_mt5():
    try:
        import MetaTrader5 as mt5  # sadece Windows'ta kurulabilir
    except ImportError:
        raise SystemExit(
            "MetaTrader5 paketi yok. Windows'ta: pip install MetaTrader5\n"
            "(Paket sadece Windows'ta çalışır; MT5 programı da açık olmalı.)")
    return mt5


class Fill:
    def __init__(self, qty, price, fee, pnl=None, ticket=None):
        self.qty, self.price, self.fee, self.pnl, self.ticket = qty, price, fee, pnl, ticket


class MT5Client:
    def __init__(self, cfg, mt5=None):
        self.cfg = cfg
        self.mt5 = mt5 or load_mt5()
        self._offset = None  # sunucu saati - UTC (saniye)

    def connect(self):
        m = self.mt5
        login = os.environ.get("MT5_LOGIN")
        password = os.environ.get("MT5_PASSWORD")
        server = os.environ.get("MT5_SERVER")
        if not (login and password and server):
            raise SystemExit("MT5_LOGIN, MT5_PASSWORD ve MT5_SERVER .env dosyasında olmalı.")
        kwargs = {"login": int(login), "password": password, "server": server}
        if os.environ.get("MT5_PATH"):
            kwargs["path"] = os.environ["MT5_PATH"]
        if not m.initialize(**kwargs):
            raise SystemExit(f"MT5'e bağlanılamadı: {m.last_error()}")
        acc = m.account_info()
        if acc is None:
            raise SystemExit(f"MT5 hesap bilgisi alınamadı: {m.last_error()}")
        if not acc.trade_allowed:
            raise SystemExit("Bu MT5 hesabında işlem izni yok (yatırımcı şifresiyle mi girdin?). "
                             "Ana (trading) şifre gerekli.")
        ti = m.terminal_info()
        if ti is not None and not ti.trade_allowed:
            raise SystemExit("MT5 programında 'Algo Trading' kapalı. Üst menüden aç.")
        demo = getattr(acc, "trade_mode", None) == getattr(m, "ACCOUNT_TRADE_MODE_DEMO", -1)
        print(f"MT5 hesabı: {acc.login} ({acc.server}) {'DEMO' if demo else 'GERÇEK'}, "
              f"bakiye {acc.balance:.2f} {acc.currency}")
        for sym in self.cfg.symbols:
            if not m.symbol_select(sym, True):
                print(f"  ! {sym} bu kurumda bulunamadı (sembol adı farklı olabilir, örn. EURUSD.m)")
        return acc

    def ensure_connected(self):
        if self.mt5.terminal_info() is None:
            print("  ! MT5 bağlantısı koptu, tekrar bağlanıyorum...")
            self.connect()

    # ---------- saat ----------
    def server_offset(self):
        """MT5 mum saatleri sunucu saatindedir. UTC'ye çevirmek için fark."""
        if self._offset is not None:
            return self._offset
        env = os.environ.get("MT5_SUNUCU_SAAT_FARKI")
        if env:
            self._offset = int(float(env) * 3600)
            return self._offset
        for sym in self.cfg.symbols:
            tick = self.mt5.symbol_info_tick(sym)
            if tick is None:
                continue
            diff = tick.time - time.time()
            hours = round(diff / 3600)
            if abs(diff - hours * 3600) < 600:  # taze tick: tam saat farkı
                self._offset = hours * 3600
                return self._offset
        return 2 * 3600  # çoğu kurum GMT+2/+3; taze tick yoksa tahmin

    def to_tr(self, server_ts):
        return datetime.fromtimestamp(server_ts - self.server_offset(), timezone.utc).astimezone(TZ)


class MT5Data:
    def __init__(self, cfg, client):
        self.cfg, self.c = cfg, client
        self.clock = SessionClock(cfg)

    def bars(self, symbols, now):
        m = self.c.mt5
        tf = getattr(m, f"TIMEFRAME_M{self.cfg.bar_minutes}")
        out = {}
        for sym in symbols:
            rates = m.copy_rates_from_pos(sym, tf, 0, 300)
            if rates is None:
                print(f"  ! {sym} mumları alınamadı: {m.last_error()}")
                continue
            bars = []
            for r in rates:
                b = Bar(self.c.to_tr(int(r["time"])), float(r["open"]), float(r["high"]),
                        float(r["low"]), float(r["close"]), float(r["tick_volume"]))
                if self.clock.in_session(b.t):
                    bars.append(b)
            out[sym] = closed_only(bars, now, self.cfg.bar_minutes)
        return out

    def prices(self, symbols):
        """Uzun pozisyon satışta bid'den kapanır; çıkış kararları bid ile verilir."""
        out = {}
        for sym in symbols:
            t = self.c.mt5.symbol_info_tick(sym)
            if t is not None and t.bid > 0:
                out[sym] = float(t.bid)
        return out


class MT5Broker:
    name = "MT5"

    def __init__(self, cfg, client):
        self.cfg, self.c, self.m = cfg, client, client.mt5
        self.clock_ = SessionClock(cfg)
        acc = self.m.account_info()
        demo = getattr(acc, "trade_mode", None) == getattr(self.m, "ACCOUNT_TRADE_MODE_DEMO", -1)
        self.name = "MT5-DEMO" if demo else "MT5-GERÇEK"

    # ---------- genel ----------
    def clock(self):
        return self.clock_.session(now_tr())

    def keep_alive(self):
        self.c.ensure_connected()

    def cash(self):
        acc = self.m.account_info()
        return float(acc.margin_free) if acc else 0.0

    def _ours(self, sym=None):
        ps = self.m.positions_get(symbol=sym) if sym else self.m.positions_get()
        return [p for p in (ps or []) if p.magic == self.cfg.mt5_magic]

    def user_holds(self, sym):
        ps = self.m.positions_get(symbol=sym) or []
        return any(p.magic != self.cfg.mt5_magic for p in ps)

    def unrealized(self, positions):
        return sum(p.profit + p.swap for p in self._ours())

    # ---------- emir yardımcıları ----------
    def _filling(self, info):
        fm = getattr(info, "filling_mode", 0)
        if fm & 1:
            return self.m.ORDER_FILLING_FOK
        if fm & 2:
            return self.m.ORDER_FILLING_IOC
        return self.m.ORDER_FILLING_RETURN

    def size(self, sym, price):
        """Zarar kes'e gelirse en fazla risk_per_trade kaybedecek lot."""
        info = self.m.symbol_info(sym)
        if info is None or info.trade_tick_size <= 0 or info.trade_tick_value <= 0:
            return 0
        sl_dist = price * self.cfg.stop_loss_pct / 100
        loss_per_lot = sl_dist / info.trade_tick_size * info.trade_tick_value
        lots = self.cfg.risk_per_trade / loss_per_lot
        step = info.volume_step or 0.01
        lots = int(lots / step + 1e-9) * step
        lots = min(round(lots, 2), info.volume_max)
        return lots if lots >= info.volume_min else 0

    def _send(self, req):
        r = self.m.order_send(req)
        if r is None:
            print(f"  ! emir gönderilemedi: {self.m.last_error()}")
            return None
        if r.retcode != self.m.TRADE_RETCODE_DONE:
            print(f"  ! emir reddedildi ({req.get('symbol')}): {r.retcode} {r.comment}")
            return None
        return r

    def _deals_result(self, ticket):
        """Bir pozisyonun gerçekleşen net kârı (komisyon ve swap dahil)."""
        deals = self.m.history_deals_get(position=ticket) or []
        pnl = sum(d.profit + d.commission + d.swap + getattr(d, "fee", 0.0) for d in deals)
        fee = -sum(d.commission + d.swap + getattr(d, "fee", 0.0) for d in deals)
        outs = [d for d in deals if d.entry == self.m.DEAL_ENTRY_OUT]
        price = outs[-1].price if outs else 0.0
        vol = sum(d.volume for d in outs)
        return pnl, fee, price, vol

    # ---------- al / sat ----------
    def buy(self, sym, qty, price):
        info = self.m.symbol_info(sym)
        tick = self.m.symbol_info_tick(sym)
        if info is None or tick is None:
            return None
        ask = tick.ask
        d = info.digits
        req = {
            "action": self.m.TRADE_ACTION_DEAL, "symbol": sym, "volume": float(qty),
            "type": self.m.ORDER_TYPE_BUY, "price": ask,
            "sl": round(ask * (1 - self.cfg.stop_loss_pct / 100), d),
            "tp": round(ask * (1 + self.cfg.take_profit_pct / 100), d),
            "deviation": self.cfg.mt5_deviation_points, "magic": self.cfg.mt5_magic,
            "comment": "borsa_bot", "type_time": self.m.ORDER_TIME_GTC,
            "type_filling": self._filling(info),
        }
        r = self._send(req)
        if r is None:
            return None
        ticket = r.order
        fill_price = r.price or ask
        for p in self._ours(sym):  # pozisyon kimliği açılış emrinin numarasıdır
            if p.identifier == r.order or p.ticket == r.order:
                ticket, fill_price = p.ticket, p.price_open
        return Fill(r.volume, fill_price, 0.0, ticket=ticket)

    def is_closed(self, pos):
        """Sunucudaki SL/TP pozisyonu kapattıysa True."""
        t = pos.get("ticket")
        if t is None:
            return False
        return not any(p.ticket == t for p in self._ours())

    def sell(self, sym, qty, price, ticket=None):
        ours = [p for p in self._ours(sym) if ticket is None or p.ticket == ticket]
        if not ours and ticket is not None:
            # Sunucu SL/TP ile zaten kapatmış: sonucu geçmişten oku.
            pnl, fee, px, vol = self._deals_result(ticket)
            return Fill(vol or qty, px or price, fee, pnl=pnl, ticket=ticket) if (px or vol) else None
        total_pnl = total_fee = total_vol = 0.0
        last_px = price
        for p in ours:
            info = self.m.symbol_info(sym)
            tick = self.m.symbol_info_tick(sym)
            req = {
                "action": self.m.TRADE_ACTION_DEAL, "symbol": sym, "volume": p.volume,
                "type": self.m.ORDER_TYPE_SELL, "position": p.ticket, "price": tick.bid,
                "deviation": self.cfg.mt5_deviation_points, "magic": self.cfg.mt5_magic,
                "comment": "borsa_bot cikis", "type_time": self.m.ORDER_TIME_GTC,
                "type_filling": self._filling(info),
            }
            if self._send(req) is None:
                continue
            time.sleep(0.5)
            pnl, fee, px, vol = self._deals_result(p.ticket)
            total_pnl += pnl
            total_fee += fee
            total_vol += vol or p.volume
            last_px = px or tick.bid
        if total_vol == 0:
            return None
        return Fill(total_vol, last_px, total_fee, pnl=total_pnl, ticket=ticket)

    def update_stop(self, sym, ticket, new_sl):
        """Tepe kilidi: SL'yi sadece yukarı taşır."""
        info = self.m.symbol_info(sym)
        for p in self._ours(sym):
            if ticket is not None and p.ticket != ticket:
                continue
            sl = round(new_sl, info.digits)
            if p.sl and sl <= p.sl:
                continue
            self._send({"action": self.m.TRADE_ACTION_SLTP, "symbol": sym,
                        "position": p.ticket, "sl": sl, "tp": p.tp, "magic": self.cfg.mt5_magic})
