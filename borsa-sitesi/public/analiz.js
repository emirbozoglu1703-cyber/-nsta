// Hisse analizi: sadece ölçülebilir veriler ve hissenin kendi geçmişi.
// Tarayıcıda ve Node testlerinde aynı kod çalışır.

export const HAFTA = 5; // 5 işlem günü = 1 hafta

// ---------- temel göstergeler ----------
export function sma(arr, n, i) {
  if (i + 1 < n) return null;
  let s = 0;
  for (let k = i - n + 1; k <= i; k++) s += arr[k];
  return s / n;
}

export function rsi(closes, i, n = 14) {
  if (i < n) return null;
  let g = 0, l = 0;
  for (let k = 1; k <= n; k++) {
    const d = closes[k] - closes[k - 1];
    if (d > 0) g += d; else l -= d;
  }
  g /= n; l /= n;
  for (let k = n + 1; k <= i; k++) {
    const d = closes[k] - closes[k - 1];
    g = (g * (n - 1) + Math.max(d, 0)) / n;
    l = (l * (n - 1) + Math.max(-d, 0)) / n;
  }
  if (l === 0) return 100;
  return 100 - 100 / (1 + g / l);
}

export function rsiSeries(closes, n = 14) {
  const out = new Array(closes.length).fill(null);
  if (closes.length <= n) return out;
  let g = 0, l = 0;
  for (let k = 1; k <= n; k++) {
    const d = closes[k] - closes[k - 1];
    if (d > 0) g += d; else l -= d;
  }
  g /= n; l /= n;
  out[n] = l === 0 ? 100 : 100 - 100 / (1 + g / l);
  for (let k = n + 1; k < closes.length; k++) {
    const d = closes[k] - closes[k - 1];
    g = (g * (n - 1) + Math.max(d, 0)) / n;
    l = (l * (n - 1) + Math.max(-d, 0)) / n;
    out[k] = l === 0 ? 100 : 100 - 100 / (1 + g / l);
  }
  return out;
}

function std(a) {
  const m = a.reduce((s, x) => s + x, 0) / a.length;
  return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / a.length);
}

// ---------- özellikler (bir günün "durumu") ----------
// Her biri o güne kadarki veriden hesaplanır; geleceğe bakmaz.
export const OZELLIKLER = [
  "son1Hafta", "son4Hafta", "son12Hafta", "ort50Fark", "ort200Fark", "rsi", "hacimOrani", "oynaklik",
];

export function ozellikler(d, i, rsis) {
  const c = d.close, v = d.volume;
  if (i < 200) return null;
  const s50 = sma(c, 50, i), s200 = sma(c, 200, i);
  const v5 = sma(v, 5, i), v50 = sma(v, 50, i);
  const rets = [];
  for (let k = i - 19; k <= i; k++) rets.push(c[k] / c[k - 1] - 1);
  return {
    son1Hafta: c[i] / c[i - 5] - 1,
    son4Hafta: c[i] / c[i - 20] - 1,
    son12Hafta: c[i] / c[i - 60] - 1,
    ort50Fark: c[i] / s50 - 1,
    ort200Fark: c[i] / s200 - 1,
    rsi: rsis[i],
    hacimOrani: v50 > 0 && v5 > 0 ? Math.log(v5 / v50) : 0,
    oynaklik: std(rets),
  };
}

// ---------- veri temizliği ----------
export function temizle(raw) {
  const out = { t: [], close: [], high: [], low: [], volume: [] };
  for (let k = 0; k < raw.t.length; k++) {
    const c = raw.close[k];
    if (c == null || !isFinite(c) || c <= 0) continue;
    out.t.push(raw.t[k]);
    out.close.push(c);
    out.high.push(raw.high[k] ?? c);
    out.low.push(raw.low[k] ?? c);
    out.volume.push(raw.volume[k] ?? 0);
  }
  return out;
}

// ---------- benzer haftalar (en yakın komşu) ----------
// Bugünkü durumu, hissenin geçmişteki her haftasıyla karşılaştırır; en çok
// benzeyen K haftadan sonraki 1 haftada ne olduğuna bakar.
function benzerler(ornekler, hedef, K) {
  // Ölçekleme sadece geçmiş örneklerle yapılır (geleceği görmeden).
  const ort = {}, sap = {};
  for (const f of OZELLIKLER) {
    const xs = ornekler.map((o) => o.x[f]);
    ort[f] = xs.reduce((s, x) => s + x, 0) / xs.length;
    sap[f] = std(xs) || 1;
  }
  const uz = ornekler.map((o) => {
    let s = 0;
    for (const f of OZELLIKLER) s += ((o.x[f] - hedef[f]) / sap[f]) ** 2;
    return { o, mesafe: Math.sqrt(s) };
  });
  uz.sort((a, b) => a.mesafe - b.mesafe);
  return uz.slice(0, K).map((u) => u.o);
}

function ozet(komsular) {
  const getiriler = komsular.map((o) => o.y).sort((a, b) => a - b);
  const yukselen = getiriler.filter((g) => g > 0).length;
  return {
    olasilik: yukselen / getiriler.length,
    medyan: getiriler[Math.floor(getiriler.length / 2)],
    kotu: getiriler[Math.floor(getiriler.length * 0.1)],
    iyi: getiriler[Math.floor(getiriler.length * 0.9)],
    n: getiriler.length,
  };
}

// ---------- ana analiz ----------
export function analiz(raw, { K = 30, minGecmis = 80, esik = 0.6 } = {}) {
  const d = temizle(raw);
  const n = d.close.length;
  if (n < 200 + HAFTA * (minGecmis + 10)) {
    return { hata: "Bu hisse için yeterli geçmiş veri yok (en az ~2.5 yıl gerekiyor)." };
  }
  const rsis = rsiSeries(d.close);

  // Haftalık örnekler: bugünden geriye 5'er gün. Son örnek = bugün.
  const idx = [];
  for (let i = n - 1; i >= 200; i -= HAFTA) idx.unshift(i);
  const ornekler = idx.map((i) => ({
    i,
    t: d.t[i],
    x: ozellikler(d, i, rsis),
    y: i + HAFTA < n ? d.close[i + HAFTA] / d.close[i] - 1 : null,
  }));
  const bugun = ornekler[ornekler.length - 1];
  const gecmis = ornekler.filter((o) => o.y !== null);

  // 1) Geçmişte bu yöntem ne kadar tuttu? (her hafta için sadece o haftadan
  //    ÖNCE bilinen verilerle tahmin yapılır, sonra gerçekle karşılaştırılır)
  const testler = [];
  for (let k = minGecmis; k < gecmis.length; k++) {
    const hedef = gecmis[k];
    // Hedef haftanın getirisi hedef.i'den sonra belli olur; komşular hedeften
    // en az 1 hafta önce bitmiş olmalı.
    const onceki = gecmis.slice(0, k - 1);
    const s = ozet(benzerler(onceki, hedef.x, K));
    testler.push({ t: hedef.t, olasilik: s.olasilik, y: hedef.y });
  }
  const yukDedi = testler.filter((x) => x.olasilik >= esik);
  const dusDedi = testler.filter((x) => x.olasilik <= 1 - esik);
  const tumYukselen = testler.filter((x) => x.y > 0).length / testler.length;
  const basari = {
    testHaftasi: testler.length,
    hepYukselirDeseydin: tumYukselen,
    yukselirDedi: yukDedi.length,
    yukselirTuttu: yukDedi.length ? yukDedi.filter((x) => x.y > 0).length / yukDedi.length : null,
    duserDedi: dusDedi.length,
    duserTuttu: dusDedi.length ? dusDedi.filter((x) => x.y <= 0).length / dusDedi.length : null,
    yukselirOrtGetiri: yukDedi.length ? yukDedi.reduce((s, x) => s + x.y, 0) / yukDedi.length : null,
  };

  // 2) Bugün için tahmin: geçmişin tamamı kullanılır.
  const komsular = benzerler(gecmis.slice(0, gecmis.length), bugun.x, K);
  const tahmin = ozet(komsular);
  tahmin.ornekTarihler = komsular.slice(0, 5).map((o) => ({ t: o.t, y: o.y }));

  // 3) Karar: yöntem bu hissede geçmişte işe yaramadıysa tahmin gösterilmez.
  // "Güvenilir" = geçmişteki isabet, körlemesine tahminden şansla açıklanamayacak
  // kadar iyi (tek yönlü binom testi, z >= 1.65 ~ %95 güven) ve en az 15 sinyal.
  const z = (tuttu, n, taban) => (tuttu - taban) / Math.sqrt((taban * (1 - taban)) / n);
  const minSinyal = 15;
  basari.yukselirZ = basari.yukselirDedi ? z(basari.yukselirTuttu, basari.yukselirDedi, basari.hepYukselirDeseydin) : null;
  basari.duserZ = basari.duserDedi ? z(basari.duserTuttu, basari.duserDedi, 1 - basari.hepYukselirDeseydin) : null;
  const yukGuvenilir = basari.yukselirDedi >= minSinyal && basari.yukselirZ >= 1.65;
  const dusGuvenilir = basari.duserDedi >= minSinyal && basari.duserZ >= 1.65;
  let karar;
  if (tahmin.olasilik >= esik) {
    karar = yukGuvenilir ? "YUKSELIS" : "YUKSELIS_GUVENSIZ";
  } else if (tahmin.olasilik <= 1 - esik) {
    karar = dusGuvenilir ? "DUSUS" : "DUSUS_GUVENSIZ";
  } else {
    karar = "BELIRSIZ";
  }

  return { veri: d, bugun: durum(d, rsis), ozellik: bugun.x, tahmin, basari, karar, esik };
}

// ---------- bugünün durumu: düz rakamlar ----------
export function durum(d, rsis) {
  const n = d.close.length, i = n - 1, c = d.close;
  const yil = Math.max(0, n - 252);
  const zirve = Math.max(...d.high.slice(yil));
  const dip = Math.min(...d.low.slice(yil));
  return {
    fiyat: c[i],
    tarih: d.t[i],
    gunluk: c[i] / c[i - 1] - 1,
    haftalik: c[i] / c[i - 5] - 1,
    aylik: c[i] / c[i - 21] - 1,
    yillik: c[i] / c[yil] - 1,
    zirve52: zirve,
    dip52: dip,
    zirveyeUzaklik: c[i] / zirve - 1,
    ort50: sma(c, 50, i),
    ort200: sma(c, 200, i),
    rsi: rsis[i],
    hacimOrani: sma(d.volume, 5, i) / (sma(d.volume, 50, i) || 1),
  };
}
