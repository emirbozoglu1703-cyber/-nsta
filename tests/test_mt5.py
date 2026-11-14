"""MetaTrader 5 bağlantısı, sahte bir MT5 terminaliyle test edilir
(gerçek MetaTrader5 paketi sadece Windows'ta çalışır)."""

import os
import tempfile
import time
import unittest
from collections import namedtuple
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from borsa_bot import bot as botmod
from borsa_bot.config import Config
from borsa_bot.market import TZ
from borsa_bot.mt5 import MT5Broker, MT5Client, MT5Data

Pos = namedtuple("Pos", "ticket identifier symbol magic volume price_open sl tp profit swap type")
Deal = namedtuple("Deal", "position_id entry volume price profit commission swap fee")


class FakeMT5:
    TRADE_ACTION_DEAL, TRADE_ACTION_SLTP = 1, 6
    ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2
    TRADE_RETCODE_DONE = 10009
    DEAL_ENTRY_IN, DEAL_ENTRY_OUT = 0, 1
    ACCOUNT_TRADE_MODE_DEMO = 0
    TIMEFRAME_M5 = 5

    def __init__(self):
        self.bid, self.ask = 1.08000, 1.08010
        self.positions = []
        self.deals = []
        self.requests = []
        self.next = 1000
        self.init_kwargs = None

    # bağlantı
    def initialize(self, **kw):
        self.init_kwargs = kw
        return True

    def last_error(self):
        return (0, "ok")

    def account_info(self):
        return SimpleNamespace(login=123, server="Kurum-Demo", balance=5000.0, equity=5000.0,
                               margin_free=4800.0, currency="USD", trade_allowed=True,
                               trade_mode=0)

    def terminal_info(self):
        return SimpleNamespace(trade_allowed=True)

    def symbol_select(self, sym, on):
        return True

    # piyasa
    def symbol_info(self, sym):
        return SimpleNamespace(digits=5, trade_tick_size=0.00001, trade_tick_value=1.0,
                               volume_min=0.01, volume_max=100.0, volume_step=0.01,
                               filling_mode=2)

    def symbol_info_tick(self, sym):
        return SimpleNamespace(bid=self.bid, ask=self.ask, time=int(time.time()) + 2 * 3600)

    def copy_rates_from_pos(self, sym, tf, start, count):
        return []

    # pozisyonlar
    def positions_get(self, symbol=None):
        return tuple(p for p in self.positions if symbol is None or p.symbol == symbol)

    def history_deals_get(self, position=None):
        return tuple(d for d in self.deals if d.position_id == position)

    def order_send(self, req):
        self.requests.append(req)
        if req["action"] == self.TRADE_ACTION_SLTP:
            self.positions = [p._replace(sl=req["sl"]) if p.ticket == req["position"] else p
                              for p in self.positions]
            return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, comment="", order=0,
                                   volume=0, price=0)
        self.next += 1
        if req["type"] == self.ORDER_TYPE_BUY:
            t = self.next
            self.positions.append(Pos(t, t, req["symbol"], req["magic"], req["volume"],
                                      req["price"], req["sl"], req["tp"], 0.0, 0.0, 0))
            self.deals.append(Deal(t, self.DEAL_ENTRY_IN, req["volume"], req["price"], 0.0, -0.5, 0.0, 0.0))
            return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, comment="", order=t,
                                   volume=req["volume"], price=req["price"])
        p = next(p for p in self.positions if p.ticket == req["position"])
        self.positions.remove(p)
        profit = round((req["price"] - p.price_open) * p.volume * 100000, 2)
        self.deals.append(Deal(p.ticket, self.DEAL_ENTRY_OUT, p.volume, req["price"], profit, -0.5, 0.0, 0.0))
        return SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, comment="", order=self.next,
                               volume=p.volume, price=req["price"])


def fx_cfg(d, **kw):
    c = Config()
    c.mode, c.state_dir, c.symbols = "live", d, ["EURUSD"]
    for k, v in kw.items():
        setattr(c, k, v)
    return c


ENV = {"MT5_LOGIN": "123", "MT5_PASSWORD": "gizli", "MT5_SERVER": "Kurum-Demo",
       "BOT_LIVE_CONFIRM": "GERCEK_PARA"}


def make(d, fake, **kw):
    cfg = fx_cfg(d, **kw)
    client = MT5Client(cfg, mt5=fake)
    with mock.patch.dict(os.environ, ENV):
        client.connect()
    return cfg, client, MT5Broker(cfg, client)


class MT5Tests(unittest.TestCase):
    def test_connect_uses_env_credentials(self):
        with tempfile.TemporaryDirectory() as d:
            fake = FakeMT5()
            make(d, fake)
            self.assertEqual(fake.init_kwargs, {"login": 123, "password": "gizli", "server": "Kurum-Demo"})

    def test_lot_size_from_risk(self):
        with tempfile.TemporaryDirectory() as d:
            _, _, br = make(d, FakeMT5())
            # 1.08 x %0.25 = 0.0027 = 270 tick x 1$ = 270$/lot -> 50$ risk = 0.18 lot
            self.assertAlmostEqual(br.size("EURUSD", 1.08), 0.18)

    def test_buy_sends_server_side_sl_tp_and_magic(self):
        with tempfile.TemporaryDirectory() as d:
            fake = FakeMT5()
            cfg, _, br = make(d, fake)
            f = br.buy("EURUSD", 0.18, 1.08)
            req = fake.requests[-1]
            self.assertEqual(req["magic"], cfg.mt5_magic)
            self.assertAlmostEqual(req["sl"], round(1.0801 * (1 - 0.0025), 5))
            self.assertAlmostEqual(req["tp"], round(1.0801 * (1 + 0.004), 5))
            self.assertEqual(req["type_filling"], fake.ORDER_FILLING_IOC)
            self.assertEqual(f.ticket, fake.positions[0].ticket)

    def test_never_touches_user_positions(self):
        with tempfile.TemporaryDirectory() as d:
            fake = FakeMT5()
            _, _, br = make(d, fake)
            fake.positions.append(Pos(1, 1, "EURUSD", 0, 1.0, 1.07, 0, 0, 10.0, 0, 0))  # kullanıcının
            self.assertTrue(br.user_holds("EURUSD"))
            self.assertIsNone(br.sell("EURUSD", 1.0, 1.08))
            self.assertEqual(len(fake.positions), 1)
            self.assertEqual(br.unrealized({}), 0)

    def test_sell_reports_broker_pnl(self):
        with tempfile.TemporaryDirectory() as d:
            fake = FakeMT5()
            _, _, br = make(d, fake)
            f = br.buy("EURUSD", 0.1, 1.08)
            fake.bid = 1.08210
            with mock.patch("borsa_bot.mt5.time.sleep"):
                out = br.sell("EURUSD", 0.1, fake.bid, ticket=f.ticket)
            self.assertAlmostEqual(out.pnl, (1.0821 - 1.0801) * 0.1 * 100000 - 1.0, places=2)
            self.assertEqual(fake.positions, [])

    def test_trailing_moves_stop_up_only(self):
        with tempfile.TemporaryDirectory() as d:
            fake = FakeMT5()
            _, _, br = make(d, fake)
            f = br.buy("EURUSD", 0.1, 1.08)
            br.update_stop("EURUSD", f.ticket, 1.0810)
            self.assertAlmostEqual(fake.positions[0].sl, 1.081)
            br.update_stop("EURUSD", f.ticket, 1.0790)  # aşağı taşımaz
            self.assertAlmostEqual(fake.positions[0].sl, 1.081)


class MT5BotLoopTests(unittest.TestCase):
    def test_bot_buys_and_records_server_side_close(self):
        from tests.test_bot import falling_then_bounce
        with tempfile.TemporaryDirectory() as d:
            fake = FakeMT5()
            cfg, client, br = make(d, fake)
            bars = falling_then_bounce(day=datetime(2026, 11, 10, 9, 0, tzinfo=TZ))
            now = bars[-1].t + timedelta(minutes=5, seconds=10)
            with mock.patch.dict(os.environ, ENV), \
                    mock.patch.object(botmod, "make_clients", return_value=(br, MT5Data(cfg, client))):
                b = botmod.Bot(cfg)
            b.broker.clock = lambda: (True, now.replace(hour=9, minute=0), now.replace(hour=23))
            b.data.bars = lambda syms, n: {"EURUSD": bars}
            b.data.prices = lambda syms: {s: fake.bid for s in syms}
            with mock.patch.object(botmod, "now_tr", return_value=now):
                b.step()
            pos = b.state.d["positions"]["EURUSD"]
            self.assertIn("ticket", pos)

            # Sunucudaki zarar kes pozisyonu kapattı:
            p = fake.positions.pop()
            fake.deals.append(Deal(p.ticket, fake.DEAL_ENTRY_OUT, p.volume, p.sl, -50.0, -0.5, 0.0, 0.0))
            with mock.patch.object(botmod, "now_tr", return_value=now + timedelta(minutes=3)):
                b.step()
            self.assertEqual(b.state.d["positions"], {})
            self.assertAlmostEqual(b.state.d["realized_pnl"], -51.0)


if __name__ == "__main__":
    unittest.main()
