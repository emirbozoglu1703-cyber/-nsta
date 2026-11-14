# BIST 100 Borsa Botu

Onur Naci Öztürkler'in ["Kripto Al-Sat botu yaptım"](https://www.youtube.com/watch?v=xsszspuRYXs)
videosundaki botun **Borsa İstanbul (BIST 100)** versiyonu. Senin hesabınla,
Deniz Yatırım'ın AlgoLab API'si üzerinden alım satım yapar.

> **Yatırım tavsiyesi değildir.** Videonun da söylediği gibi bu bir deney.
> Aşağıdaki "Dürüst test sonucu" bölümünü okumadan gerçek para koyma.

## Videodaki bot → bu bot

| Videoda (kripto, Binance) | Burada (BIST 100, Deniz Yatırım) |
|---|---|
| 5.000 $ bütçe | `budget: 50000` TL |
| Düşen coini al, yükselince sat | Bugünkü tepesinden %2+ düşmüş, RSI ≤ 30, yeşil dönüş mumu gelen BIST 100 hissesini al |
| Kâr al %16, zarar kes %10 (1.6 oranı) | Kâr al %4, zarar kes %2.5. Oran yine 1.6, ama hisseler kriptodan az oynadığı için yüzdeler küçük |
| Tepe kilidi: 1000→1100 görüp düşerse 1050'de sat | `trail_activate_pct: 2`, `trail_keep_ratio: 0.5`: tepedeki kârın yarısını kilitler |
| "En fazla 1000 $ kaybet" | `max_total_loss: 10000` TL: aşılırsa her şeyi satar ve durur. Ayrıca günlük limit: 3.000 TL |
| Önce sanal 5000 $ ile test | `mode: sim`: sanal parayla, gerçek borsaya bağlanmadan |
| Her 30 sn'de kontrol | `loop_seconds: 30` |
| 15-60 dk tutulan işlemler en iyisi | `max_hold_minutes: 60` |
| Komisyon kârı yiyor | `commission_pct`: kendi kurum oranını yaz, test her işlemde hesaplar |
| VPS'te 7/24 | `deploy/borsa-bot.service` |
| Claude: "10 gün test etmemiz lazım" | `python -m borsa_bot test`: son 60 günle geçmiş testi |

Ek güvenlikler:
- Bot sadece **kendi aldığı** lotlara dokunur. Hesabındaki diğer hisseleri satmaz, elinde olan hisseyi tekrar almaz.
- Seans kapanışından (18:00) 10 dk önce her şeyi satar, ertesi güne pozisyon taşımaz.
- Açılışın ilk 15 dakikasında işlem açmaz.
- Gerçek para modu, `.env` dosyasında `BOT_LIVE_CONFIRM=GERCEK_PARA` yazmadan açılmaz.

## Dürüst test sonucu

Son 60 işlem günü, BIST 100'ün 100 hissesi, 5 dakikalık mumlar, işlem başı %0.05 komisyon
(`python -m borsa_bot test`):

| | |
|---|---|
| İşlem | 427 |
| Kazanan | %40 |
| Ücret öncesi | −5.956 TL |
| Ödenen komisyon | 4.216 TL |
| **Net** | **−10.172 TL (−%20.3)** |

- Bot 60 günde bütçesinin %20'sini kaybetti. 10.000 TL toplam zarar limitine takılıp kendini durdurdu, yani limit işe yaradı.
- 48 farklı ayar denendi (kâr al, zarar kes, tutma süresi, düşüş eşiği, RSI). **Hiçbiri** 60 günün iki yarısında kâr etmedi.
- Komisyon BİST'te de önemli: zararın yaklaşık %40'ı komisyon.
- Videodaki bir gecelik kâr büyük ihtimalle şanstı. Videoda Claude da bunu söylüyor.

Bu yüzden önerilen yol:
1. Önce `sim` modunda birkaç hafta çalıştır, `bot_data/islemler_sim.csv` dosyasına bak.
2. `config.json` dosyasında ayarlarla oyna, her seferinde `python -m borsa_bot test` ile dene.
3. Ancak tutarlı şekilde pozitif sonuç görürsen, küçük bir tutarla `live` dene.

## Kurulum

Python 3.9+ gerekir.

```bash
git clone <bu repo>
cd <repo>
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
cp config.example.json config.json
```

### 1) Sanal mod (hesap gerekmez)

```bash
python -m borsa_bot test        # son 60 günle geçmiş testi
python -m borsa_bot calistir    # sanal 50.000 TL ile, seans saatinde çalışır
```

Sanal mod Yahoo Finance verisini kullanır. Bu veri gecikmeli olabilir, bu yüzden
sanal sonuçlar gerçek işlemden biraz farklı çıkar.

### 2) Gerçek para (Deniz Yatırım AlgoLab)

1. Deniz Yatırım'da online hesap aç, para yatır.
2. https://www.algolab.com.tr üzerinden API başvurusu yap, **API anahtarını** al.
3. Kurumunun komisyon oranını öğren, `config.json` içindeki `commission_pct` alanına yaz.
   Örnek: binde 0.5 için `0.05`.
4. `.env` dosyasına yaz:
   ```
   BOT_MODE=live
   ALGOLAB_API_KEY=API-....
   BOT_LIVE_CONFIRM=GERCEK_PARA
   ```
5. Giriş yap. TC kimlik no ve şifreni sorar, sonra telefonuna gelen SMS kodunu ister:
   ```bash
   python -m borsa_bot giris
   ```
   Oturum `bot_data/algolab_oturum.json` dosyasına kaydedilir. Bot oturumu 15 dakikada bir yeniler.
   Oturum düşerse bot hata yazar ve işlem açmaz; tekrar `giris` yapman gerekir.
6. `config.json` dosyasında `budget`, `position_size`, `max_total_loss`, `max_daily_loss` değerlerini kendi paranla ayarla.
7. `python -m borsa_bot calistir`

Bilmen gerekenler:
- AlgoLab saniyede yaklaşık 1 isteğe izin veriyor. Bu yüzden bot 100 hissenin mumlarını 5 dakikada bir tarar (yaklaşık 2 dakika sürer). Elindeki hisselerin fiyatına ise her 30 saniyede bakar.
- Emirler **piyasa emri** olarak gider. Emir 30 saniyede dolmazsa kalan kısmı iptal edilir.
- AlgoLab bağlantısı belgelere ve açık kaynak örneklere göre yazıldı ve sahte cevaplarla test edildi. **Gerçek bir AlgoLab hesabıyla henüz denenmedi.** İlk gün küçük bir `position_size` ile (örneğin 1.000 TL) başla, emirleri Deniz Yatırım uygulamasından kontrol et.
- TC kimlik no, şifre ve API anahtarını kimseyle paylaşma, sohbete yapıştırma. `.env` ve `bot_data/` git'e girmez.

## Komutlar

```bash
python -m borsa_bot giris                 # gerçek para: AlgoLab'e SMS ile giriş
python -m borsa_bot calistir              # botu başlat
python -m borsa_bot test                  # son 60 günle test
python -m borsa_bot test --komisyon 0.1   # farklı komisyonla test
python -m borsa_bot durum                 # kâr/zarar, açık pozisyonlar
python -m borsa_bot hepsini-sat           # botun aldığı her şeyi hemen sat
python -m borsa_bot devam                 # zarar limitiyle duran botu tekrar aç
```

Her işlem `bot_data/islemler_<mod>.csv` dosyasına yazılır: zaman, hisse, al/sat, lot, fiyat, komisyon, kâr/zarar, sebep, süre.

## Hisse listesi

`config.json` içindeki `symbols` alanı, Kasım 2026 itibarıyla BIST 100'ün 100 hissesini içerir.
Endeks her çeyrek değişir. Değiştiğinde listeyi güncelle. Daha az hisseyle de çalışabilirsin,
örneğin sadece BIST 30.

## VPS'e kurulum (7/24 çalışsın)

Videodaki gibi bir VPS kirala (en küçük Ubuntu planı yeterli), sonra:

```bash
sudo useradd -r -m -d /opt/borsa-bot borsabot
sudo -u borsabot git clone <bu repo> /opt/borsa-bot
cd /opt/borsa-bot
sudo -u borsabot python3 -m venv .venv
sudo -u borsabot .venv/bin/pip install -r requirements.txt
sudo -u borsabot cp .env.example .env            # anahtarı içine yaz
sudo -u borsabot cp config.example.json config.json
sudo -u borsabot .venv/bin/python -m borsa_bot giris   # SMS kodunu gir
sudo cp deploy/borsa-bot.service /etc/systemd/system/
sudo systemctl enable --now borsa-bot
journalctl -u borsa-bot -f                       # canlı log
```

## Dosyalar

- `borsa_bot/strategy.py`: alım ve çıkış kuralları
- `borsa_bot/bot.py`: 30 sn'lik ana döngü, zarar limitleri, kayıt
- `borsa_bot/broker.py`: sanal hesap ve gerçek hesap (AlgoLab) emirleri
- `borsa_bot/algolab.py`: Deniz Yatırım AlgoLab API istemcisi
- `borsa_bot/market.py`: fiyat verisi (Yahoo / AlgoLab) ve BIST seans saatleri
- `borsa_bot/backtest.py`: geçmiş testi ve rapor
- `tests/`: `python -m unittest discover -s tests`
