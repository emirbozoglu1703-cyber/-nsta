import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

from borsa_bot import strategy as st
from borsa_bot.config import Config
from borsa_bot.market import NY
from borsa_bot.strategy import Bar


def cfg(**kw):
    c = Config()
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def falling_then_bounce(day=datetime(2026, 11, 10, 9, 30, tzinfo=NY), n=40):
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
        c = cfg()
        self.assertEqual(st.buy_fees(100, 10, c), 0.0)
        self.assertAlmostEqual(st.sell_fees(100, 10, c), 1000 * c.sec_fee_rate + 10 * c.taf_per_share)
        c.commission_pct = 0.1
        self.assertAlmostEqual(st.buy_fees(100, 10, c), 1.0)


class ConfigTests(unittest.TestCase):
    def test_live_needs_confirmation(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                cfg(mode="live").validate()
        with mock.patch.dict(os.environ, {"BOT_LIVE_CONFIRM": "GERCEK_PARA"}):
            cfg(mode="live").validate()


class BotLoopTests(unittest.TestCase):
    """Sanal modda bir turu sahte saat ve veriyle çalıştırır."""

    def test_buy_then_stop_loss_and_daily_limit(self):
        from borsa_bot import bot as botmod
        with tempfile.TemporaryDirectory() as d:
            c = cfg(state_dir=d, symbols=["AAA"], max_daily_loss_usd=10_000)
            bars = falling_then_bounce()
            now = bars[-1].t + timedelta(minutes=5, seconds=10)
            px = bars[-1].c
            b = botmod.Bot(c)
            open_, close = now.replace(hour=9, minute=30), now.replace(hour=16, minute=0)
            b.broker.clock = lambda: (True, open_, close)
            b.data.snapshot = lambda syms, n=None: {"AAA": (bars, px)}
            with mock.patch.object(botmod, "now_ny", return_value=now):
                b.step()
            pos = b.state.d["positions"]["AAA"]
            self.assertEqual(pos["qty"], int(c.position_size_usd // (px * (1 + c.slippage_bps / 1e4))))

            later = now + timedelta(minutes=10)
            b.data.snapshot = lambda syms, n=None: {"AAA": (bars, px * 0.97)}
            with mock.patch.object(botmod, "now_ny", return_value=later):
                b.step()
            self.assertNotIn("AAA", b.state.d["positions"])
            self.assertLess(b.state.d["realized_pnl"], 0)
            self.assertTrue(os.path.exists(b.state.journal))

    def test_total_loss_limit_halts(self):
        from borsa_bot import bot as botmod
        with tempfile.TemporaryDirectory() as d:
            c = cfg(state_dir=d, symbols=["AAA"], max_total_loss_usd=1.0, stop_loss_pct=50)
            bars = falling_then_bounce()
            now = bars[-1].t + timedelta(minutes=5, seconds=10)
            px = bars[-1].c
            b = botmod.Bot(c)
            b.broker.clock = lambda: (True, now.replace(hour=9, minute=30), now.replace(hour=16))
            b.data.snapshot = lambda syms, n=None: {"AAA": (bars, px)}
            with mock.patch.object(botmod, "now_ny", return_value=now):
                b.step()
            b.data.snapshot = lambda syms, n=None: {"AAA": (bars, px * 0.9)}
            with mock.patch.object(botmod, "now_ny", return_value=now + timedelta(minutes=1)):
                b.step()
            self.assertEqual(b.state.d["halted"], "toplam_limit")
            self.assertEqual(b.state.d["positions"], {})


if __name__ == "__main__":
    unittest.main()
