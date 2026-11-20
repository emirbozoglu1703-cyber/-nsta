# Hisse Analiz sitesi

Hisse kodunu yaz (THYAO, ASELS, AAPL...). Site:

- **Gerçek fiyat verisini** gösterir (Yahoo Finance, 5 yıllık günlük): fiyat, haftalık/aylık/yıllık değişim, 52 hafta zirve/dip, 50/200 günlük ortalama, RSI, hacim, 1 yıllık grafik.
- **Gelecek hafta için yön tahmini** verir: hissenin son 5 yılında bugüne en çok benzeyen 30 haftayı bulur, onlardan 1 hafta sonra ne olduğuna bakar.
- **Tahminin geçmişte ne kadar tuttuğunu ölçer:** son 130 hafta için, sadece o haftadan önceki veriyle tahmin yapıp gerçekleşenle karşılaştırır. İsabet, "her hafta yükselir" demekten istatistiksel olarak anlamlı ölçüde iyi değilse sonucu **güvenilir değil** diye işaretler.
- **Son 14 günün haber başlıklarını** kaynağıyla gösterir (Google Haberler). Haberleri yorumlamaz, uydurma özet veya "%88 olumlu" gibi sayılar üretmez.
- Takip listesi: hisseleri ekle, "Hepsini tara" ile hepsini tek tabloda sırala. Liste tarayıcında saklanır.

Kimse bir hissenin gelecek hafta ne yapacağını kesin bilemez. Site sadece ölçtüğünü gösterir. Yatırım tavsiyesi değildir.

## Yayınlama (Netlify, ücretsiz)

Bu klasör olduğu gibi Netlify'a yüklenir: `public/` site, `netlify/functions/veri.mjs` veri fonksiyonu (Yahoo ve Google Haberler tarayıcıdan doğrudan çağrılamadığı için araya girer).

1. https://app.netlify.com → "Add new site" → "Import an existing project" → bu GitHub reposunu seç.
2. **Base directory:** `borsa-sitesi`. Diğer ayarlar `netlify.toml`'dan gelir.
3. Deploy. Site `https://<isim>.netlify.app` adresinde açılır.

## Test

```bash
npm test
```

Testler ayrıca analizin geleceğe bakmadığını ve rastgele fiyat serilerinde sahte "güvenilir" sinyal üretmediğini kontrol eder (40 rastgele seride 0).
