# Forex Botu (MetaTrader 5)

Onur Naci Öztürkler'in ["Kripto Al-Sat botu yaptım"](https://www.youtube.com/watch?v=xsszspuRYXs)
videosundaki botun **forex** versiyonu. Yeni bir hesap ya da ürün değil:
**senin kendi MetaTrader 5 hesabına** bağlanır ve o hesapta alım satım yapar.

> **Yatırım tavsiyesi değildir.** Forex kaldıraçlıdır; yatırdığın paranın tamamını kaybedebilirsin.
> Aşağıdaki "Dürüst test sonucu" bölümünü okumadan gerçek hesapta çalıştırma.

## Şifren nerede durur?

- Şifreni **kimseye, hiçbir sohbete ya da yapay zekâya yazma.**
- Şifre sadece senin bilgisayarındaki `.env` dosyasına yazılır. Bot onu yalnızca kendi bilgisayarındaki MetaTrader 5 programına verir; başka hiçbir yere göndermez.
- `.env` dosyası git'e girmez (`.gitignore`).

## Videodaki bot → bu bot

| Videoda (kripto) | Burada (forex, MT5) |
|---|---|
| 5.000 $ bütçe | Senin MT5 hesabın, işlem başı en fazla `risk_per_trade: 50` $ risk |
| Düşen coini al, yükselince sat | Bugünkü tepesinden %0.2+ düşmüş, RSI ≤ 30, yeşil dönüş mumu gelen pariteyi al |
| Kâr al %16, zarar kes %10 (1.6 oranı) | Kâr al %0.4, zarar kes %0.25. Oran yine 1.6; kurlar kriptodan çok daha az oynar |
| Tepe kilidi: 1000→1100 görüp düşerse 1050'de sat | Tepe kilidi: bot zarar kes seviyesini (SL) yukarı taşır, tepedeki kârın yarısını kilitler |
| "En fazla 1000 $ kaybet" | `max_total_loss: 1000`: aşılırsa her şeyi kapatır ve durur. Günlük limit: 300 $ |
| Önce sanal parayla test | `BOT_MODE=sim`, ya da kurumunun **demo** MT5 hesabı |
| Her 30 sn'de kontrol | `loop_seconds: 30` |
| 15-60 dk tutulan işlemler en iyisi | `max_hold_minutes: 60` |
| Komisyon kârı yiyor | Forex'te maliyet **makas (spread)**: `slippage_bps` ile hesaba katılır |

Lot büyüklüğünü bot hesaplar: zarar kes'e gelirse en fazla `risk_per_trade` (varsayılan 50 $) kaybedecek kadar lot alır.

## Güvenlik

- **Senin işlemlerine dokunmaz.** Botun her emri bir sihirli numara (`mt5_magic`) taşır. Bot sadece o numaralı pozisyonları yönetir. Senin açık işlemin olan pariteye girmez.
- **Zarar kes ve kâr al sunucuya yazılır.** Bot ya da bilgisayar kapansa bile korumalar kurumun sunucusunda çalışır.
- Sadece uzun (alış) pozisyon açar, açığa satış yapmaz.
- 09:00–23:00 (İstanbul) arası işlem yapar, 22:50'de açık pozisyonları kapatır. Geceye pozisyon taşımaz, swap ödemez.
- Gerçek hesap modu `.env` dosyasında `BOT_LIVE_CONFIRM=GERCEK_PARA` yazmadan açılmaz.
- Yatırımcı (salt okunur) şifresiyle girersen bot bunu anlar ve işlem açmaz.

## Dürüst test sonucu

Son 60 gün, 7 ana parite (EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCHF, USDCAD), 5 dakikalık mumlar,
yaklaşık 1.2 pip makas (`python -m borsa_bot test`):

| | |
|---|---|
| İşlem | 280 |
| Kazanan | %54.6 |
| Makas (spread) maliyeti | 661 $ (net sonuca dahil) |
| **Net** | **+73.86 $ (+%1.5)** |
| En büyük düşüş | 361 $ |

Ama:
- Kârın tamamı tek pariteden (USDJPY, +256 $) geliyor. **USDJPY olmadan sonuç −182 $.**
- 108 farklı ayar denendi. Sadece 4'ü 60 günün iki yarısında da kâr etti; bu kadarı şansla da olur.
- Varsayılan ayarlar ilk 30 günde −88 $, son 30 günde +152 $.
- Aynı strateji daha önce denendiğinde BIST'te %20, ABD hisselerinde %5 zarar etti.

Yani bu strateji güvenilir şekilde para kazandırmıyor. Önerilen yol:
1. `sim` modunda birkaç hafta çalıştır.
2. Kurumunun **demo** MT5 hesabında en az 1 ay çalıştır.
3. Ancak demo sonuçları tutarlı şekilde pozitifse, gerçek hesapta küçük `risk_per_trade` ile (örneğin 5–10 $) başla.

## Kurulum

### 1) Sanal mod (her bilgisayarda, hesap gerekmez)

Python 3.9+ gerekir.

```bash
git clone <bu repo>
cd <repo>
python -m venv .venv
.venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # Mac/Linux: cp .env.example .env
copy config.example.json config.json
python -m borsa_bot test        # son 60 günle geçmiş testi
python -m borsa_bot calistir    # sanal 5.000 $ ile çalışır
```

### 2) Senin MT5 hesabın (Windows)

MetaQuotes'un Python paketi sadece **Windows**'ta çalışır. VPS kullanacaksan Windows VPS al.

1. Kurumunun MetaTrader 5 programını kur, hesabınla giriş yap.
2. MT5'te üst menüden **Algo Trading** düğmesini aç (yeşil olmalı).
3. Market Watch'ta paritelerin adlarına bak. Kurumun `EURUSD.m` gibi farklı adlar kullanıyorsa `config.json` içindeki `symbols` listesini aynı adlarla güncelle.
4. `.env` dosyasını kendi bilgisayarında aç ve doldur:
   ```
   BOT_MODE=live
   MT5_LOGIN=hesap numaran
   MT5_PASSWORD=ana şifren
   MT5_SERVER=Kurum-Sunucu-Adı
   BOT_LIVE_CONFIRM=GERCEK_PARA
   ```
   Sunucu adı MT5'teki giriş penceresinde yazar (örneğin `KurumAdi-Demo`).
5. Önce **demo hesap** bilgileriyle dene. Bot açılışta hesabın DEMO mu GERÇEK mi olduğunu yazar.
6. `python -m borsa_bot calistir`

Bot açıkken MT5 programı da açık kalmalı. İşlemleri MT5'teki "İşlem" sekmesinde görürsün; açıklama alanında `borsa_bot` yazar.

## Komutlar

```bash
python -m borsa_bot calistir              # botu başlat
python -m borsa_bot test                  # son 60 günle test
python -m borsa_bot durum                 # kâr/zarar, açık pozisyonlar
python -m borsa_bot hepsini-sat           # botun açtığı her şeyi hemen kapat
python -m borsa_bot devam                 # zarar limitiyle duran botu tekrar aç
```

Her işlem `bot_data/islemler_<mod>.csv` dosyasına yazılır.

## Ayarlar (`config.json`)

| Ayar | Varsayılan | Anlamı |
|---|---|---|
| `risk_per_trade` | 50 | Bir işlem zarar kes'e gelirse kaybedilecek en fazla tutar ($) |
| `max_positions` | 3 | Aynı anda en fazla açık işlem |
| `max_total_loss` | 1000 | Toplam zarar bunu geçerse bot her şeyi kapatıp durur |
| `max_daily_loss` | 300 | Günlük zarar bunu geçerse o gün durur |
| `take_profit_pct` / `stop_loss_pct` | 0.4 / 0.25 | Kâr al / zarar kes (%) |
| `trail_activate_pct` / `trail_keep_ratio` | 0.2 / 0.5 | Tepe kilidi |
| `session_open` / `session_close` | 09:00 / 23:00 | İşlem saatleri (İstanbul) |
| `slippage_bps` | 0.6 | Testte makasın yarısı (0.6 = %0.006, EURUSD'de ~0.6 pip) |
| `symbols` | 7 ana parite | İşlem yapılacak pariteler |

## 7/24 çalıştırma (Windows)

Bot açık kaldığı sürece çalışır; bilgisayarın ya da Windows VPS'in açık olmalı.
MT5 programını açık bırak, sonra `deploy\baslat.bat` dosyasına çift tıkla. Bot kapanırsa
30 saniye sonra kendini yeniden başlatır, çıktıları `bot_data\log.txt` dosyasına yazar.
Bilgisayar açılınca kendiliğinden başlasın istersen Görev Zamanlayıcı'da
"oturum açıldığında" bu dosyayı çalıştıran bir görev oluştur.

## Dosyalar

- `borsa_bot/strategy.py`: alım, çıkış, lot ve kâr/zarar hesapları
- `deploy/baslat.bat`: Windows'ta botu sürekli çalıştırır
- `borsa_bot/bot.py`: 30 sn'lik ana döngü, zarar limitleri, kayıt
- `borsa_bot/mt5.py`: MetaTrader 5 bağlantısı (senin hesabın)
- `borsa_bot/broker.py`: sanal hesap
- `borsa_bot/market.py`: fiyat verisi ve işlem saatleri
- `borsa_bot/backtest.py`: geçmiş testi ve rapor
- `tests/`: `python -m unittest`
