"""Deniz Yatırım AlgoLab API istemcisi (BIST pay piyasası).

Hesap: Deniz Yatırım'da online hesap + AlgoLab'den alınan API anahtarı.
Giriş iki adımlı: TC kimlik no + şifre ile token alınır, telefona gelen SMS
koduyla oturum (hash) açılır. Oturum dosyaya kaydedilir; bot onu kullanır ve
15 dakikada bir yeniler. Oturum düşerse tekrar `python -m borsa_bot giris`.

API belgesi: https://www.algolab.com.tr (Algolab API dokümanı).
"""

import base64
import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests

HOST = "https://www.algolab.com.tr"
API = HOST + "/api"
MIN_GAP = 1.1  # AlgoLab: istekler arası en az ~1 sn


def num(s):
    """'2.05', '1.234,56', '' gibi değerleri sayıya çevirir."""
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    if not s or s == "-":
        return 0.0
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    return float(s)


class AlgoLabError(RuntimeError):
    pass


class AlgoLab:
    def __init__(self, api_key, session_file):
        code = api_key.split("-", 1)[1] if api_key.startswith("API-") else api_key
        self.api_code = code
        self.api_key = "API-" + code
        self.session_file = Path(session_file)
        self.hash = ""
        self._last = 0.0
        self._last_refresh = 0.0
        self.s = requests.Session()

    # ---------- düşük seviye ----------
    def _encrypt(self, text):
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        key = base64.b64decode(self.api_code.encode())
        cipher = AES.new(key, AES.MODE_CBC, b"\0" * 16)
        return base64.b64encode(cipher.encrypt(pad(text.encode(), 16))).decode()

    def _checker(self, endpoint, payload):
        body = json.dumps(payload).replace(" ", "") if payload else ""
        return hashlib.sha256((self.api_key + HOST + endpoint + body).encode()).hexdigest()

    def _post(self, endpoint, payload, login=False):
        wait = MIN_GAP - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        headers = {"APIKEY": self.api_key}
        if not login:
            if not self.hash:
                raise AlgoLabError("Oturum yok. Önce: python -m borsa_bot giris")
            headers.update({"Checker": self._checker(endpoint, payload),
                            "Authorization": self.hash})
        try:
            r = self.s.post(API + endpoint, json=payload, headers=headers, timeout=20)
        finally:
            self._last = time.time()
        if r.status_code == 401:
            raise AlgoLabError("Oturum süresi doldu. Tekrar: python -m borsa_bot giris")
        if r.status_code != 200:
            raise AlgoLabError(f"{endpoint}: HTTP {r.status_code} {r.text[:200]}")
        j = r.json()
        if not j.get("success", False):
            raise AlgoLabError(f"{endpoint}: {j.get('message')}")
        return j.get("content")

    # ---------- oturum ----------
    def login_interactive(self, username, password, ask=input):
        content = self._post("/api/LoginUser", {"username": self._encrypt(username),
                                                "password": self._encrypt(password)}, login=True)
        token = content["token"]
        sms = ask("Telefonuna gelen SMS kodunu yaz: ").strip()
        content = self._post("/api/LoginUserControl", {"token": self._encrypt(token),
                                                       "password": self._encrypt(sms)}, login=True)
        self.hash = content["hash"]
        self.save_session()

    def save_session(self):
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(json.dumps({"hash": self.hash,
                                                 "saved": datetime.now().isoformat()}))
        os.chmod(self.session_file, 0o600)

    def load_session(self):
        if not self.session_file.exists():
            raise AlgoLabError("Oturum yok. Önce: python -m borsa_bot giris")
        self.hash = json.loads(self.session_file.read_text())["hash"]

    def keep_alive(self, every=15 * 60):
        if time.time() - self._last_refresh >= every:
            self._post("/api/SessionRefresh", {})
            self._last_refresh = time.time()

    # ---------- veri ----------
    def candles(self, symbol, period_minutes=5):
        rows = self._post("/api/GetCandleData", {"symbol": symbol, "period": str(period_minutes)})
        return rows or []

    def last_price(self, symbol):
        c = self._post("/api/GetEquityInfo", {"symbol": symbol})
        return num(c.get("lst"))

    def positions(self):
        """{hisse_kodu: adet} (nakit satırı hariç)."""
        rows = self._post("/api/InstantPosition", {"Subaccount": ""}) or []
        out = {}
        for r in rows:
            code = r.get("code")
            if code and code != "TRY" and r.get("type") != "CA":
                out[code] = num(r.get("totalstock"))
        return out

    def cash(self):
        """Kullanılabilir nakit (T+0). RiskSimulation yoksa InstantPosition'daki TRY satırı."""
        try:
            rs = self._post("/api/RiskSimulation", {"Subaccount": ""})
            if isinstance(rs, list):
                rs = rs[0] if rs else {}
            if rs and "t0" in rs:
                return num(rs["t0"])
        except AlgoLabError:
            pass
        for r in self._post("/api/InstantPosition", {"Subaccount": ""}) or []:
            if r.get("code") == "TRY":
                return num(r.get("tlamaount"))
        return 0.0

    def todays_transactions(self):
        return self._post("/api/TodaysTransaction", {"Subaccount": ""}) or []

    # ---------- emir ----------
    def send_market_order(self, symbol, side, lot):
        content = self._post("/api/SendOrder", {
            "symbol": symbol, "direction": side, "pricetype": "piyasa", "price": "",
            "lot": str(int(lot)), "sms": False, "email": False, "subAccount": ""})
        # "Referans Numaranız: 001VEV;0000-2923NR-IET - HISSEOK"
        m = re.search(r":\s*([A-Za-z0-9]+)\s*;", str(content))
        if not m:
            raise AlgoLabError(f"Emir referansı okunamadı: {content}")
        return m.group(1)

    def delete_order(self, order_id):
        return self._post("/api/DeleteOrder", {"id": order_id, "subAccount": ""})

    def wait_fill(self, order_id, timeout=30):
        """(dolan_adet, ortalama_fiyat). Süre dolarsa kalanı iptal eder."""
        def find():
            for t in self.todays_transactions():
                if order_id in (t.get("atpref"), t.get("transactionId")):
                    return t
            return None

        deadline = time.time() + timeout
        t = None
        while time.time() < deadline:
            t = find()
            if t and (t.get("equityStatusDescription") in ("DONE", "DELETED")
                      or num(t.get("remainingsize")) == 0 and num(t.get("fillunit")) > 0):
                break
            time.sleep(2)
        else:
            try:
                self.delete_order(order_id)
            except AlgoLabError as e:
                print(f"  ! emir iptal edilemedi ({order_id}): {e}")
            time.sleep(2)
            t = find()
        if not t:
            return 0, 0.0
        return num(t.get("fillunit")), num(t.get("price"))
