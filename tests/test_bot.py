import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from borsa_bot import strategy as st
from borsa_bot.config import Config
from borsa_bot.market import TZ
from borsa_bot.strategy import Bar


def cfg(**kw):
    c = Config()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def falling_then_bounce(day=datetime(2026, 11, 10, 10, 0, tzinfo=TZ), n=40):
    """Sürekli düşen, sonda yeşil bir dönüş mumu olan seri."""
    bars, px = [], 100.0
    for i in range(n):
        t = day + timedelta(minutes=5 * i)
        o = px
        px *= 0.996
        bars.append(Bar(t, o, o * 1.001, px * 0.999, px))
    t = day + timedelta(minutes=5 * n)
    bars.append(Bar(t, px, px * 1.006, px * 0.999, px * 1.005))
    return bars


class StrategyTests(unittest.TestCase):
    def test_rsi_bounds(self):
        self.assertEqual(st.rsi([1, 2, 3, 4, 5] * 4, 14) is not None, True)
        self.assertEqual(st.rsi(list(range(1, 30)), 14), 100.0)
        self.assertIsNone(st.rsi([1, 2, 3], 14))

    def test_entry_on_dip_and_bounce(self):
        sig = st.entry_signal(falling_then_bounce(), cfg())
        self.assertIsNotNone(sig)
        self.assertGreaterEqual(sig["dip"], 2.0)

    def test_no_entry_without_bounce(self):
        bars = falling_then_bounce()[:-1]  # dönüş mumu yok
        self.assertIsNone(st.entry_signal(bars, cfg()))

    def test_exit_rules_video_example(self):
        c = cfg(take_profit_pct=16, stop_loss_pct=10, trail_activate_pct=10, trail_keep_ratio=0.5)
        # 1000 -> 1160 kâr al, 1000 -> 900 zarar kes
        self.assertEqual(st.exit_reason(1000, 1160, 1160, 5, c), "kar_al")
        self.assertEqual(st.exit_reason(1000, 1000, 900, 5, c), "zarar_kes")
        # 1100 tepeyi gördü, 1050'ye döndü -> tepe kilidi
        self.assertEqual(st.exit_reason(1000, 1100, 1050, 5, c), "tepe_kilidi")
        self.assertIsNone(st.exit_reason(1000, 1100, 1060, 5, c))
        self.assertEqual(st.exit_reason(1000, 1000, 1010, 60, c), "sure_doldu")

    def test_fees(self):
        c = cfg(commission_pct=0.05)
        self.assertAlmostEqual(st.buy_fees(100, 100, c), 5.0)   # 10.000 TL x binde 0.5
        self.assertAlmostEqual(st.sell_fees(100, 100, c), 5.0)
        c.commission_min = 8
        self.assertAlmostEqual(st.buy_fees(100, 100, c), 8.0)
        self.assertEqual(st.buy_fees(100, 0, c), 0.0)


class ConfigTests(unittest.TestCase):
    def test_live_needs_confirmation(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                cfg(mode="live").validate()
        with mock.patch.dict(os.environ, {"BOT_LIVE_CONFIRM": "GERCEK_PARA"}):
            cfg(mode="live").validate()


def feed(b, bars, price):
    b.data.bars = lambda syms, now: {"AAA": bars}
    b.data.prices = lambda syms: {s: price for s in syms}
    b._bars_key = None  # yeni mum kapanmış gibi tarama yaptır


class BotLoopTests(unittest.TestCase):
    """Sanal modda bir turu sahte saat ve veriyle çalıştırır."""

    def test_buy_then_stop_loss_and_daily_limit(self):
        from borsa_bot import bot as botmod
        with tempfile.TemporaryDirectory() as d:
            c = cfg(state_dir=d, symbols=["AAA"], max_daily_loss=10_000_000)
            bars = falling_then_bounce()
            now = bars[-1].t + timedelta(minutes=5, seconds=10)
            px = bars[-1].c
            b = botmod.Bot(c)
            open_, close = now.replace(hour=10, minute=0), now.replace(hour=18, minute=0)
            b.broker.clock = lambda: (True, open_, close)
            feed(b, bars, px)
            with mock.patch.object(botmod, "now_tr", return_value=now):
                b.step()
            pos = b.state.d["positions"]["AAA"]
            self.assertEqual(pos["qty"], int(c.position_size // (px * (1 + c.slippage_bps / 1e4))))

            later = now + timedelta(minutes=10)
            feed(b, bars, px * 0.97)
            with mock.patch.object(botmod, "now_tr", return_value=later):
                b.step()
            self.assertNotIn("AAA", b.state.d["positions"])
            self.assertLess(b.state.d["realized_pnl"], 0)
            self.assertTrue(os.path.exists(b.state.journal))

    def test_total_loss_limit_halts(self):
        from borsa_bot import bot as botmod
        with tempfile.TemporaryDirectory() as d:
            c = cfg(state_dir=d, symbols=["AAA"], max_total_loss=1.0, stop_loss_pct=50)
            bars = falling_then_bounce()
            now = bars[-1].t + timedelta(minutes=5, seconds=10)
            px = bars[-1].c
            b = botmod.Bot(c)
            b.broker.clock = lambda: (True, now.replace(hour=10, minute=0), now.replace(hour=18))
            feed(b, bars, px)
            with mock.patch.object(botmod, "now_tr", return_value=now):
                b.step()
            feed(b, bars, px * 0.9)
            with mock.patch.object(botmod, "now_tr", return_value=now + timedelta(minutes=1)):
                b.step()
            self.assertEqual(b.state.d["halted"], "toplam_limit")
            self.assertEqual(b.state.d["positions"], {})


if __name__ == "__main__":
    unittest.main()


class ForexSimTests(unittest.TestCase):
    def test_leveraged_sim_pnl_and_sizing(self):
        from borsa_bot.broker import SimBroker
        from borsa_bot.config import FOREX_PRESET
        with tempfile.TemporaryDirectory() as d:
            c = cfg(state_dir=d, market="forex", **{k: v for k, v in FOREX_PRESET.items()
                                                     if k != "symbols"})
            # 50$ risk / (1.08 x %0.25) = 18.518 birim -> 18.000 (0.18 lot)
            self.assertEqual(st.size_qty("EURUSD", 1.08, c), 18000)
            # USDJPY: kâr yen cinsinden, dolara çevrilir
            self.assertAlmostEqual(st.pnl_factor("USDJPY", 150.0, c), 1 / 150)
            b = SimBroker(c)
            c.slippage_bps = 0
            b.buy("EURUSD", 18000, 1.0800)
            self.assertEqual(b.cash(), 5000)          # kaldıraçlı: para bağlanmaz
            b.sell("EURUSD", 18000, 1.0820)
            self.assertAlmostEqual(b.cash(), 5000 + 0.002 * 18000)
