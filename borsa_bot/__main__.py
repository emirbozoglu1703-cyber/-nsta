"""Kullanım:
    python -m borsa_bot calistir           # botu başlat (config.json'daki moda göre)
    python -m borsa_bot test               # son 60 günle geçmiş testi (backtest)
    python -m borsa_bot test --komisyon 0.1  # Binance gibi %0.1 komisyonla dene
    python -m borsa_bot durum              # kâr/zarar ve açık pozisyonlar
    python -m borsa_bot hepsini-sat        # botun açtığı her şeyi şimdi sat
    python -m borsa_bot devam              # zarar limiti yüzünden duran botu tekrar aç
"""

import argparse
import json
import sys

from .config import load_config, load_env


def main(argv=None):
    ap = argparse.ArgumentParser(prog="borsa_bot")
    ap.add_argument("komut", choices=["calistir", "test", "durum", "hepsini-sat", "devam"])
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--gun", default="60d", help="test için geçmiş (en fazla 60d)")
    ap.add_argument("--komisyon", type=float, help="test: işlem başı yüzde komisyon")
    a = ap.parse_args(argv)

    load_env()
    cfg = load_config(a.config)

    if a.komut == "test":
        from . import backtest
        if a.komisyon is not None:
            cfg.commission_pct = a.komisyon
        print(f"{len(cfg.symbols)} hissenin 5 dk mumları indiriliyor...")
        data = backtest.fetch(cfg, a.gun)
        print(backtest.report(cfg, backtest.run(cfg, data)))
        return

    from .bot import Bot, State
    if a.komut == "durum":
        d = State(cfg).d
        print(json.dumps({k: d[k] for k in ("realized_pnl", "fees", "daily", "halted",
                                             "trades", "positions")},
                         indent=2, ensure_ascii=False))
        return
    if a.komut == "devam":
        st = State(cfg)
        st.d["halted"] = None
        st.save()
        print("Durdurma kaldırıldı. Bot bir sonraki turda yeni işlem açabilir.")
        return

    bot = Bot(cfg)
    if a.komut == "hepsini-sat":
        from .market import now_ny
        snap = bot.data.snapshot(list(bot.state.d["positions"]))
        bot.flatten_all({s: v[1] for s, v in snap.items()}, "elle", now_ny())
        return
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\nBot durduruldu. Açık pozisyonlar duruyor; "
              "satmak için: python -m borsa_bot hepsini-sat")
        sys.exit(0)


if __name__ == "__main__":
    main()
