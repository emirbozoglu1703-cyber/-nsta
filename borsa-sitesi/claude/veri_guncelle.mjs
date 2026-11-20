// Giriş yapmadan açılan sayfa için veri dosyalarını üretir.
// Borsa İstanbul'daki TÜM hisseler + popüler ABD hisseleri. Her hisse için:
// canlı fiyat, gün içi 5 dk (5 gün), 5 yıllık günlük kapanış, hazır analiz
// sonucu (aynı analiz.js) ve son 7 günün haberleri.
//
//   node borsa-sitesi/claude/veri_guncelle.mjs
//
// Çıktı: borsa-sitesi/claude/veri/p<N>.json (25'er hisselik paketler) ve veri/index.json

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { analiz, temizle, durum, rsiSeries } from "../public/analiz.js";

const KOK = path.dirname(fileURLToPath(import.meta.url));
const CIKTI = path.join(KOK, "veri");
const UA = { "User-Agent": "Mozilla/5.0 (hisse-analiz)" };
const PAKET = 25;
const ABD = [
  { kod: "AAPL", ad: "Apple" }, { kod: "NVDA", ad: "NVIDIA" }, { kod: "MSFT", ad: "Microsoft" },
  { kod: "TSLA", ad: "Tesla" }, { kod: "AMZN", ad: "Amazon" }, { kod: "GOOGL", ad: "Alphabet" }, { kod: "META", ad: "Meta" },
];

const r4 = (x) => (x == null ? null : Math.round(x * 1e4) / 1e4);
const bekle = (ms) => new Promise((ok) => setTimeout(ok, ms));

async function getir(url, opts = {}, deneme = 3) {
  for (let i = 0; i < deneme; i++) {
    try {
      const r = await fetch(url, { headers: UA, ...opts });
      if (r.ok) return await r.text();
      if (r.status === 404) return null;
    } catch {}
    await bekle(1500 * (i + 1));
  }
  return null;
}

// Güncel BIST hisse listesi (TradingView); ulaşılamazsa repodaki kopya.
async function bistListesi() {
  const t = await getir("https://scanner.tradingview.com/turkey/scan", {
    method: "POST", headers: { ...UA, "Content-Type": "application/json" },
    body: JSON.stringify({ columns: ["name", "description"], filter: [{ left: "type", operation: "equal", right: "stock" }], range: [0, 3000], markets: ["turkey"] }),
  });
  try {
    const rows = JSON.parse(t).data.map((x) => ({ kod: x.d[0], ad: x.d[1] }));
    if (rows.length > 400) {
      rows.sort((a, b) => a.kod.localeCompare(b.kod));
      fs.writeFileSync(path.join(KOK, "bist_hisseler.json"), JSON.stringify(rows));
      return rows;
    }
  } catch {}
  return JSON.parse(fs.readFileSync(path.join(KOK, "bist_hisseler.json"), "utf8"));
}

async function grafik(sembol, aralik, donem) {
  const t = await getir(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sembol)}?interval=${aralik}&range=${donem}&includePrePost=false`);
  if (!t) return null;
  let res; try { res = JSON.parse(t)?.chart?.result?.[0]; } catch { return null; }
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
    await bekle(3000 * (i + 1));
  }
  return null; // null = alınamadı (boş liste = gerçekten haber yok)
}

const META = ["symbol", "longName", "shortName", "fullExchangeName", "currency", "regularMarketPrice",
  "regularMarketTime", "previousClose", "chartPreviousClose", "currentTradingPeriod"];
const metaAl = (m) => Object.fromEntries(META.filter((k) => m[k] !== undefined).map((k) => [k, m[k]]));

// Kısa biçim: zaman damgaları ilk zamana göre gün (günlük) ya da 5 dk (gün içi) adımı.
function sikistir(t, close, adimMs) {
  const ikili = t.map((x, i) => [x, close[i]]).filter(([, c]) => c != null);
  if (!ikili.length) return { t0: 0, d: [], c: [] };
  const t0 = ikili[0][0];
  return { t0, d: ikili.map(([x]) => Math.round((x - t0) / adimMs)), c: ikili.map(([, c]) => r4(c)) };
}

async function hisse({ kod, ad, abd }) {
  const sembol = abd ? kod : `${kod}.IS`;
  const g = await grafik(sembol, "1d", "5y");
  if (!g) throw new Error("günlük veri yok");
  const raw = { t: g.t, close: g.close, high: g.high, low: g.low, volume: g.volume };
  const a = analiz(raw);
  let sonuc;
  if (!a.hata) {
    sonuc = { bugun: a.bugun, tahmin: a.tahmin, basari: a.basari, karar: a.karar, esik: a.esik };
  } else {
    // Tahmin için geçmiş yetmiyor; yine de bugünün rakamları.
    const d = temizle(raw);
    sonuc = { hata: a.hata, bugun: d.close.length >= 22 ? durum(d, rsiSeries(d.close)) : null };
  }
  const gi = await grafik(sembol, "5m", "5d");
  return {
    kod, ad, sembol,
    gunluk: { meta: metaAl(g.meta), ...sikistir(g.t, g.close, 864e5) },
    gunIci: gi ? { meta: metaAl(gi.meta), ...sikistir(gi.t, gi.close, 3e5) } : null,
    analiz: sonuc,
    haberler: [],
  };
}

async function havuz(isler, n, fn) {
  const out = []; let i = 0;
  await Promise.all(Array.from({ length: n }, async () => {
    while (i < isler.length) { const k = i++; out[k] = await fn(isler[k]).catch((e) => ({ hata: e.message, kod: isler[k].kod })); }
  }));
  return out;
}

const bas = Date.now();
const liste = [...(await bistListesi()).map((h) => ({ ...h, abd: false })), ...ABD.map((h) => ({ ...h, abd: true }))];
const sonuc = (await havuz(liste, 6, hisse)).filter((s) => s && s.gunluk);
const atlanan = liste.length - sonuc.length;

// Haberler ayrı ve yavaş: Google çok sık istekte geçici olarak engelliyor.
let haberHata = 0;
await havuz(sonuc, 3, async (s) => {
  const h = await haber(s.sembol);
  if (h === null) haberHata++;
  s.haberler = h || [];
  await bekle(250);
});

fs.rmSync(CIKTI, { recursive: true, force: true });
fs.mkdirSync(CIKTI, { recursive: true });
const ozet = [];
for (let p = 0; p * PAKET < sonuc.length; p++) {
  const parca = sonuc.slice(p * PAKET, (p + 1) * PAKET);
  const paket = {};
  for (const s of parca) {
    paket[s.kod] = s;
    const m = { ...s.gunluk.meta, ...(s.gunIci?.meta || {}) };
    const n = s.gunluk.c.length;
    ozet.push({
      kod: s.kod, ad: s.ad || m.longName || m.shortName || s.kod, pb: m.currency, p,
      fiyat: m.regularMarketPrice,
      bugun: m.previousClose ? m.regularMarketPrice / m.previousClose - 1 : null,
      haftalik: n > 6 ? m.regularMarketPrice / s.gunluk.c[n - 6] - 1 : null,
      karar: s.analiz.karar || null, olasilik: s.analiz.tahmin?.olasilik ?? null,
    });
  }
  fs.writeFileSync(path.join(CIKTI, `p${p}.json`), JSON.stringify(paket));
}
fs.writeFileSync(path.join(CIKTI, "index.json"), JSON.stringify({ guncelleme: Date.now(), hisseler: ozet }));
console.log(`${ozet.length}/${liste.length} hisse yazıldı (${atlanan} atlandı, ${haberHata} hissede haber alınamadı), ${Math.ceil(ozet.length / PAKET)} paket, ${((Date.now() - bas) / 1000).toFixed(0)} sn`);
