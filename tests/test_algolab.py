import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from borsa_bot import algolab
from borsa_bot.algolab import AlgoLab, AlgoLabError, num

KEY = "API-" + base64.b64encode(b"0123456789abcdef").decode()


def client(d):
    c = AlgoLab(KEY, Path(d) / "oturum.json")
    c.hash = "HASH"
    return c


class AlgoLabTests(unittest.TestCase):
    def test_num(self):
        self.assertEqual(num("2.05"), 2.05)
        self.assertEqual(num("1.234,56"), 1234.56)
        self.assertEqual(num(""), 0.0)
        self.assertEqual(num("-"), 0.0)

    def test_checker_matches_docs(self):
        with tempfile.TemporaryDirectory() as d:
            c = client(d)
            payload = {"symbol": "GARAN", "period": "5"}
            body = json.dumps(payload).replace(" ", "")
            want = hashlib.sha256((KEY + "https://www.algolab.com.tr" + "/api/GetCandleData" + body).encode()).hexdigest()
            self.assertEqual(c._checker("/api/GetCandleData", payload), want)

    def test_encrypt_roundtrip(self):
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        with tempfile.TemporaryDirectory() as d:
            enc = client(d)._encrypt("12345678901")
            key = base64.b64decode(KEY[4:])
            dec = unpad(AES.new(key, AES.MODE_CBC, b"\0" * 16).decrypt(base64.b64decode(enc)), 16)
            self.assertEqual(dec.decode(), "12345678901")

    def test_order_reference_and_fill(self):
        with tempfile.TemporaryDirectory() as d:
            c = client(d)
            calls = []

            def fake_post(endpoint, payload, login=False):
                calls.append((endpoint, payload))
                if endpoint == "/api/SendOrder":
                    return "Referans Numaranız: 001VEV;0000-2923NR-IET - HISSEOK"
                if endpoint == "/api/TodaysTransaction":
                    return [{"atpref": "001VEV", "ticker": "THYAO", "fillunit": "40",
                             "remainingsize": "0", "price": "301.25",
                             "equityStatusDescription": "DONE"}]
                raise AssertionError(endpoint)

            c._post = fake_post
            ref = c.send_market_order("THYAO", "BUY", 40)
            self.assertEqual(ref, "001VEV")
            self.assertEqual(calls[0][1]["pricetype"], "piyasa")
            self.assertEqual(calls[0][1]["lot"], "40")
            with mock.patch.object(algolab.time, "sleep"):
                self.assertEqual(c.wait_fill(ref), (40.0, 301.25))

    def test_unfilled_order_is_cancelled(self):
        with tempfile.TemporaryDirectory() as d:
            c = client(d)
            deleted = []

            def fake_post(endpoint, payload, login=False):
                if endpoint == "/api/TodaysTransaction":
                    return [{"atpref": "X1", "fillunit": "0", "remainingsize": "40",
                             "price": "0", "equityStatusDescription": "WAITING"}]
                if endpoint == "/api/DeleteOrder":
                    deleted.append(payload["id"])
                    return {"message": "Success"}
                raise AssertionError(endpoint)

            c._post = fake_post
            with mock.patch.object(algolab.time, "sleep"):
                self.assertEqual(c.wait_fill("X1", timeout=0), (0.0, 0.0))
            self.assertEqual(deleted, ["X1"])

    def test_positions_skip_cash(self):
        with tempfile.TemporaryDirectory() as d:
            c = client(d)
            c._post = lambda e, p, login=False: [
                {"code": "TRY", "type": "CA", "totalstock": "0", "tlamaount": "52.63"},
                {"code": "TSKB", "type": "CH", "totalstock": "1"}]
            self.assertEqual(c.positions(), {"TSKB": 1.0})

    def test_no_session(self):
        with tempfile.TemporaryDirectory() as d:
            c = AlgoLab(KEY, Path(d) / "yok.json")
            with self.assertRaises(AlgoLabError):
                c.load_session()


if __name__ == "__main__":
    unittest.main()
