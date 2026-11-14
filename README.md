# Borsa Botu

Onur Naci Öztürkler'in ["Kripto Al-Sat botu yaptım"](https://www.youtube.com/watch?v=xsszspuRYXs)
videosundaki botun **ABD hisse senedi** versiyonu. Senin hesabınla alım satım yapar.

> **Yatırım tavsiyesi değildir.** Videonun da söylediği gibi bu bir deney.
> Aşağıdaki "Dürüst test sonucu" bölümünü okumadan gerçek para koyma.

## Videodaki bot → bu bot

| Videoda (kripto, Binance) | Burada (hisse, Alpaca) |
|---|---|
| 5.000 $ bütçe | `budget_usd: 5000` |
| Düşen coini al, yükselince sat | Bugünkü tepesinden %2+ düşmüş, RSI ≤ 30, yeşil dönüş mumu gelen hisseyi al |
| Kâr al %16, zarar kes %10 (1.6 oranı) | Kâr al %4, zarar kes %2.5. Oran yine 1.6, ama hisseler kriptodan az oynadığı için yüzdeler küçük |
| Tepe kilidi: 1000→1100 görüp düşerse 1050'de sat | `trail_activate_pct: 2`, `trail_keep_ratio: 0.5`: tepedeki kârın yarısını kilitler |
| "En fazla 1000 $ kaybet" | `max_total_loss_usd: 1000`: aşılırsa her şeyi satar ve durur. Ayrıca günlük limit: 300 $ |
| Önce sanal 5000 $ ile test | `mode: sim` (bilgisayarında sanal) ve `mode: paper` (Alpaca sanal hesabı) |
| Her 30 sn'de kontrol | `loop_seconds: 30` |
| 15-60 dk tutulan işlemler en iyisi | `max_hold_minutes: 60` |
| Asıl sorun komisyon (günde ~200 $) | Alpaca'da hisse komisyonu **0 $**. Sadece çok küçük SEC/FINRA ücretleri var |
| Hostinger VPS'te 7/24 | `deploy/borsa-bot.service` |
| Claude: "10 gün test etmemiz lazım" | `python -m borsa_bot test`: son 60 günle geçmiş testi |

Ek güvenlikler:
- Bot sadece **kendi açtığı** pozisyonlara dokunur. Hesabındaki diğer hisseleri satmaz.
- Kapanıştan 10 dk önce her şeyi satar, gece pozisyon taşımaz.
- Canlı mod `.env` dosyasında `BOT_LIVE_CONFIRM=GERCEK_PARA` yazmadan açılmaz.
- ABD'nin PDT kuralına uyar: 25.000 $ altı hesapta 5 iş gününde 3 gün içi işlem sınırı dolunca yeni alım yapmaz.

## Dürüst test sonucu

Bot son 60 işlem gününün 5 dakikalık verisiyle, 25 hisse üzerinde test edildi (`python -m borsa_bot test`):

| | Alpaca (komisyonsuz) | Binance gibi %0.1 komisyon |
|---|---|---|
| İşlem | 260 | 259 |
| Kazanan | %43.5 | %37.1 |
| Ödenen ücret | 6.72 $ | 457.72 $ |
| **Net** | **−247 $ (−%4.9)** | **−690 $ (−%13.8)** |

- Komisyon sorunu çözüldü. Videodaki gibi kârı yiyen şey artık ücret değil.
- Ama strateji bu 60 günde **para kaybetti**. 48 farklı ayar denendi (kâr al, zarar kes, tutma süresi, düşüş eşiği, RSI). Hiçbiri 60 günün iki yarısında da kâr etmedi.
- Videodaki bir gecelik +116 $ da büyük ihtimalle şanstı. Videoda Claude da bunu söylüyor.

Bu yüzden önerilen yol:
1. `sim` modunda birkaç gün çalıştır, `bot_data/islemler_sim.csv` dosyasına bak.
2. Alpaca `paper` hesabında en az birkaç hafta çalıştır.
3. Ancak sonuçlar tutarlı şekilde pozitifse küçük bir tutarla `live` dene.

Ayarlarla oynayıp tekrar test etmek için `config.json` dosyasını değiştirip `python -m borsa_bot test` çalıştır.

## Kurulum (kendi bilgisayarında)

Python 3.9+ gerekir.

```bash
git clone <bu repo>
cd <repo>
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
cp config.example.json config.json
```

### 1) Sanal mod (anahtar gerekmez)

```bash
python -m borsa_bot test        # geçmiş testi
python -m borsa_bot calistir    # sanal 5000 $ ile canlı piyasada çalıştır
```

ABD borsası Türkiye saatiyle 17:30-00:00 arası açık (yaz saatinde 16:30-23:00).
Borsa kapalıyken bot bekler.

### 2) Alpaca sanal hesap (paper)

1. https://alpaca.markets adresinde ücretsiz hesap aç.
2. Panelde **Paper Trading** hesabına geç, **API Keys** bölümünden anahtar üret.
3. `.env` dosyasına yaz:
   ```
   BOT_MODE=paper
   ALPACA_API_KEY=...
   ALPACA_SECRET_KEY=...
   ```
4. `python -m borsa_bot calistir`

### 3) Gerçek para (live)

1. Alpaca'da canlı hesap aç, kimlik doğrulamasını tamamla, para yatır.
2. Canlı hesabın API anahtarlarını `.env` dosyasına yaz.
3. `.env` dosyasında:
   ```
   BOT_MODE=live
   BOT_LIVE_CONFIRM=GERCEK_PARA
   ```
4. `config.json` dosyasında `budget_usd`, `position_size_usd`, `max_total_loss_usd` değerlerini kendi paranla ayarla.
5. `python -m borsa_bot calistir`

Anahtarları kimseyle paylaşma, sohbete yapıştırma. `.env` dosyası git'e girmez.

## Komutlar

```bash
python -m borsa_bot calistir              # botu başlat
python -m borsa_bot test                  # son 60 günle test
python -m borsa_bot test --komisyon 0.1   # komisyonlu test (videodaki Binance durumu)
python -m borsa_bot durum                 # kâr/zarar, açık pozisyonlar
python -m borsa_bot hepsini-sat           # botun açtığı her şeyi hemen sat
python -m borsa_bot devam                 # zarar limitiyle duran botu tekrar aç
```

Her işlem `bot_data/islemler_<mod>.csv` dosyasına yazılır: zaman, hisse, al/sat, fiyat, ücret, kâr/zarar, sebep, süre.

## VPS'e kurulum (7/24 çalışsın)

Videodaki gibi bir VPS kirala (en küçük Ubuntu planı yeterli), sonra:

```bash
sudo useradd -r -m -d /opt/borsa-bot borsabot
sudo -u borsabot git clone <bu repo> /opt/borsa-bot
cd /opt/borsa-bot
sudo -u borsabot python3 -m venv .venv
sudo -u borsabot .venv/bin/pip install -r requirements.txt
sudo -u borsabot cp .env.example .env            # anahtarları içine yaz
sudo -u borsabot cp config.example.json config.json
sudo cp deploy/borsa-bot.service /etc/systemd/system/
sudo systemctl enable --now borsa-bot
journalctl -u borsa-bot -f                       # canlı log
```

## Dosyalar

- `borsa_bot/strategy.py`: alım ve çıkış kuralları
- `borsa_bot/bot.py`: 30 sn'lik ana döngü, zarar limitleri, kayıt
- `borsa_bot/broker.py`: sanal hesap ve Alpaca bağlantısı
- `borsa_bot/market.py`: fiyat verisi (Yahoo / Alpaca) ve borsa saatleri
- `borsa_bot/backtest.py`: geçmiş testi ve rapor
- `tests/`: `python -m unittest discover -s tests`
