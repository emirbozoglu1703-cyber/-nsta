// Giriş yapmadan açılan sayfa için veri dosyalarını üretir.
// Her hisse için: canlı fiyat, gün içi 5 dk (5 gün), 5 yıllık günlük kapanış,
// hazır analiz sonucu (aynı analiz.js) ve son 7 günün haberleri.
//
//   node borsa-sitesi/claude/veri_guncelle.mjs
//
// Çıktı: borsa-sitesi/claude/veri/<KOD>.json ve veri/index.json

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { analiz } from "../public/analiz.js";

const KOK = path.dirname(fileURLToPath(import.meta.url));
const CIKTI = path.join(KOK, "veri");
const UA = { "User-Agent": "Mozilla/5.0 (hisse-analiz)" };

const BIST100 = (
  "AEFES AGHOL AHGAZ AKBNK AKCNS AKFYE AKSA AKSEN ALARK ALBRK ALTNY ANHYT ANSGR " +
  "ARCLK ASELS ASTOR AYGAZ BERA BIMAS BINHO BRSAN BRYAT BTCIM CANTE CCOLA CIMSA " +
  "CVKMD CWENE DOAS DOHOL ECILC ECZYT EGEEN EGGUB EKGYO ENERY ENJSA ENKAI ENTRA " +
  "EREGL EUREN FENER FROTO GARAN GLRMK GLYHO GRSEL GUBRF GWIND HALKB HEKTS ISCTR " +
  "ISDMR ISMEN KARSN KATMR KCAER KCHOL KORDS KRDMD LMKDC MAVI MGROS MPARK OBAMS " +
  "ODAS OTKAR OYAKC PAHOL PETKM PGSUS RGYAS RYSAS SAHOL SASA SISE SNGYO SOKM " +
  "TABGD TAVHL TCELL TCKRC THYAO TKFEN TOASO TRALT TRENJ TRGYO TRMET TSKB TTKOM " +
  "TTRAK TUKAS TUPRS TURSG ULKER VAKBN VESTL YKBNK ZOREN"
).split(" ");
const ABD = ["AAPL", "NVDA", "MSFT", "TSLA", "AMZN", "GOOGL", "META"];

const r4 = (x) => (x == null ? null : Math.round(x * 1e4) / 1e4);

async function getir(url, deneme = 3) {
  for (let i = 0; i < deneme; i++) {
    try {
      const r = await fetch(url, { headers: UA });
      if (r.ok) return await r.text();
      if (r.status === 404) return null;
    } catch {}
    await new Promise((ok) => setTimeout(ok, 1500 * (i + 1)));
  }
  return null;
}

async function grafik(sembol, aralik, donem) {
  const t = await getir(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sembol)}?interval=${aralik}&range=${donem}&includePrePost=false`);
  if (!t) return null;
  const res = JSON.parse(t)?.chart?.result?.[0];
  if (!res?.timestamp?.length) return null;
  const q = res.indicators.quote[0];
  return { meta: res.meta, t: res.timestamp.map((x) => x * 1000), close: q.close, high: q.high, low: q.low, volume: q.volume };
}

function rss(xml) {
  const al = (s, tag) => {
    const m = s.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`));
    return m ? m[1].replace(/<!\[CDATA\[|\]\]>/g, "").replace(/&amp;/g, "&").replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").trim() : "";
  };
  return xml.split("<item>").slice(1).map((it) => ({
    baslik: al(it, "title"), link: al(it, "link"), tarih: al(it, "pubDate"), kaynak: al(it, "source"),
  })).sort((a, b) => new Date(b.tarih) - new Date(a.tarih)).slice(0, 15);
}

async function haber(sembol, deneme = 3) {
  const bist = sembol.endsWith(".IS"), kod = sembol.replace(/\.IS$/, "");
  const q = bist ? `"${kod}" hisse when:7d` : `${kod} stock when:7d`;
  const dil = bist ? "hl=tr&gl=TR&ceid=TR:tr" : "hl=en-US&gl=US&ceid=US:en";
  for (let i = 0; i < deneme; i++) {
    const x = await getir(`https://news.google.com/rss/search?q=${encodeURIComponent(q)}&${dil}`);
    if (x && x.includes("<rss")) return rss(x);
    await new Promise((ok) => setTimeout(ok, 3000 * (i + 1)));
  }
  return [];
}

const META = ["symbol", "longName", "shortName", "fullExchangeName", "currency", "regularMarketPrice",
  "regularMarketTime", "previousClose", "chartPreviousClose", "currentTradingPeriod"];
const metaAl = (m) => Object.fromEntries(META.filter((k) => m[k] !== undefined).map((k) => [k, m[k]]));

async function hisse(kod) {
  const sembol = ABD.includes(kod) ? kod : `${kod}.IS`;
  const g = await grafik(sembol, "1d", "5y");
  if (!g) throw new Error("günlük veri yok");
  const a = analiz({ t: g.t, close: g.close, high: g.high, low: g.low, volume: g.volume });
  const gi = await grafik(sembol, "5m", "5d");
  // Grafik ve değişimler için sadece kapanış yeterli; 52 hafta zirve/dip analizde hazır.
  const temiz = g.t.map((t, i) => [t, g.close[i]]).filter(([, c]) => c != null);
  return {
    kod,
    gunluk: { meta: metaAl(g.meta), t: temiz.map((x) => x[0]), close: temiz.map((x) => r4(x[1])) },
    gunIci: gi ? { meta: metaAl(gi.meta), t: gi.t, close: gi.close.map(r4) } : null,
    analiz: a.hata ? { hata: a.hata } : { bugun: a.bugun, ozellik: a.ozellik, tahmin: a.tahmin, basari: a.basari, karar: a.karar, esik: a.esik },
    haberler: [],
    sembol,
  };
}

async function havuz(isler, n, fn) {
  const out = []; let i = 0;
  await Promise.all(Array.from({ length: n }, async () => {
    while (i < isler.length) { const k = i++; out[k] = await fn(isler[k]).catch((e) => ({ hata: e.message, kod: isler[k] })); }
  }));
  return out;
}

const bas = Date.now();
fs.mkdirSync(CIKTI, { recursive: true });
const kodlar = [...BIST100, ...ABD];
const sonuc = await havuz(kodlar, 5, hisse);
// Haberler ayrı ve yavaş: Google çok sık istekte geçici olarak engelliyor.
await havuz(sonuc.filter((s) => s && s.gunluk), 2, async (s) => {
  s.haberler = await haber(s.sembol);
  await new Promise((ok) => setTimeout(ok, 400));
});
const ozet = [];
for (const s of sonuc) {
  if (!s || s.hata && !s.gunluk) { console.error("atlandı:", s?.kod, s?.hata); continue; }
  fs.writeFileSync(path.join(CIKTI, `${s.kod}.json`), JSON.stringify(s));
  const m = s.gunIci?.meta || s.gunluk.meta;
  const n = s.gunluk.close.length;
  ozet.push({
    kod: s.kod, ad: m.longName || m.shortName || s.kod, pb: m.currency,
    fiyat: m.regularMarketPrice,
    bugun: m.previousClose ? m.regularMarketPrice / m.previousClose - 1 : null,
    haftalik: n > 6 ? m.regularMarketPrice / s.gunluk.close[n - 6] - 1 : null,
    karar: s.analiz.karar || null, olasilik: s.analiz.tahmin?.olasilik ?? null,
  });
}
fs.writeFileSync(path.join(CIKTI, "index.json"), JSON.stringify({ guncelleme: Date.now(), hisseler: ozet }));
console.log(`${ozet.length}/${kodlar.length} hisse yazıldı, ${((Date.now() - bas) / 1000).toFixed(0)} sn`);
