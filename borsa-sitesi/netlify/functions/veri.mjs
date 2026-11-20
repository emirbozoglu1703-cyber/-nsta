// Tarayıcı Yahoo Finance ve Google Haberler'e doğrudan bağlanamaz (CORS).
// Bu fonksiyon araya girer: sadece okur, hiçbir şey kaydetmez.
//
//   /api/veri?tur=fiyat&sembol=THYAO   -> 5 yıllık günlük fiyat (önce .IS denenir)
//   /api/veri?tur=haber&sembol=THYAO.IS&ad=Türk Hava Yolları -> son haber başlıkları

const UA = { "User-Agent": "Mozilla/5.0 (hisse-analiz)" };
const SEMBOL = /^[A-Z0-9][A-Z0-9.\-]{0,14}$/;

function json(body, status = 200, cache = 900) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": `public, max-age=${cache}`,
    },
  });
}

async function yahoo(sembol) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sembol)}?interval=1d&range=5y&includePrePost=false`;
  const r = await fetch(url, { headers: UA });
  if (!r.ok) return null;
  const j = await r.json();
  const res = j?.chart?.result?.[0];
  if (!res?.timestamp?.length) return null;
  const q = res.indicators.quote[0];
  return {
    sembol: res.meta.symbol,
    ad: res.meta.longName || res.meta.shortName || res.meta.symbol,
    borsa: res.meta.fullExchangeName || res.meta.exchangeName,
    paraBirimi: res.meta.currency,
    t: res.timestamp.map((x) => x * 1000),
    close: q.close, high: q.high, low: q.low, volume: q.volume,
  };
}

function rssOku(xml) {
  const out = [];
  const items = xml.split("<item>").slice(1);
  const al = (s, tag) => {
    const m = s.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`));
    if (!m) return "";
    return m[1].replace(/<!\[CDATA\[|\]\]>/g, "")
      .replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;/g, "'")
      .replace(/&lt;/g, "<").replace(/&gt;/g, ">").trim();
  };
  for (const it of items.slice(0, 15)) {
    out.push({ baslik: al(it, "title"), link: al(it, "link"), tarih: al(it, "pubDate"), kaynak: al(it, "source") });
  }
  return out;
}

async function haberler(sembol, ad) {
  const bist = sembol.endsWith(".IS");
  const kod = sembol.replace(/\.IS$/, "");
  const q = bist ? `"${kod}" hisse` : `${kod} stock`;
  const dil = bist ? "hl=tr&gl=TR&ceid=TR:tr" : "hl=en-US&gl=US&ceid=US:en";
  const url = `https://news.google.com/rss/search?q=${encodeURIComponent(q + " when:14d")}&${dil}`;
  const r = await fetch(url, { headers: UA });
  if (!r.ok) return [];
  return rssOku(await r.text());
}

export default async (req) => {
  const u = new URL(req.url);
  const tur = u.searchParams.get("tur");
  const sembol = (u.searchParams.get("sembol") || "").trim().toUpperCase();
  if (!SEMBOL.test(sembol)) return json({ hata: "Geçersiz hisse kodu." }, 400, 0);

  try {
    if (tur === "fiyat") {
      // Nokta yoksa önce Borsa İstanbul (.IS), bulunamazsa ABD borsası denenir.
      const adaylar = sembol.includes(".") ? [sembol] : [`${sembol}.IS`, sembol];
      for (const s of adaylar) {
        const v = await yahoo(s);
        if (v) return json(v);
      }
      return json({ hata: `"${sembol}" bulunamadı. Kodu kontrol et (örn. THYAO, ASELS, AAPL).` }, 404, 60);
    }
    if (tur === "haber") {
      return json({ haberler: await haberler(sembol, u.searchParams.get("ad") || "") }, 200, 600);
    }
    return json({ hata: "tur=fiyat veya tur=haber olmalı." }, 400, 0);
  } catch (e) {
    return json({ hata: "Veri kaynağına ulaşılamadı, biraz sonra tekrar dene." }, 502, 0);
  }
};

export const config = { path: "/api/veri" };
