import { analiz } from "./analiz.js";

const ORNEKLER = ["THYAO", "ASELS", "GARAN", "EREGL", "TUPRS", "BIMAS", "KCHOL", "SISE", "FROTO", "AAPL", "NVDA"];
const LS = "hisse-analiz-liste";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const yuzde = (x, d = 1) => (x == null || !isFinite(x) ? "–" : `${x > 0 ? "+" : x < 0 ? "−" : ""}%${Math.abs(x * 100).toFixed(d).replace(".", ",")}`);
const oran = (x) => (x == null ? "–" : `%${Math.round(x * 100)}`);
const para = (x, pb) => (x == null ? "–" : x.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + (pb === "TRY" ? " ₺" : pb === "USD" ? " $" : ` ${pb || ""}`));
const tarih = (ms) => new Date(ms).toLocaleDateString("tr-TR", { day: "numeric", month: "short", year: "numeric" });
const renk = (x) => (x > 0 ? "art" : x < 0 ? "eksi" : "");

// ---------- takip listesi ----------
function listeOku() {
  try { return JSON.parse(localStorage.getItem(LS)) || []; } catch { return []; }
}
function listeYaz(l) {
  try { localStorage.setItem(LS, JSON.stringify(l)); } catch { /* özel pencere */ }
}
let liste = listeOku();
const sonuclar = new Map(); // kod -> analiz özeti (tarama tablosu için)

// ---------- veri ----------
const onbellek = new Map();
async function fiyatGetir(kod) {
  if (onbellek.has(kod)) return onbellek.get(kod);
  const r = await fetch(`/api/veri?tur=fiyat&sembol=${encodeURIComponent(kod)}`);
  const j = await r.json();
  if (!r.ok || j.hata) throw new Error(j.hata || "Veri alınamadı.");
  onbellek.set(kod, j);
  return j;
}
async function haberGetir(sembol, ad) {
  try {
    const r = await fetch(`/api/veri?tur=haber&sembol=${encodeURIComponent(sembol)}&ad=${encodeURIComponent(ad)}`);
    const j = await r.json();
    return j.haberler || [];
  } catch { return []; }
}

// ---------- karar metni ----------
function kararBilgi(a) {
  const t = a.tahmin, b = a.basari;
  const benzer = `Bugüne en çok benzeyen ${t.n} geçmiş haftada, 1 hafta sonra yükselme oranı: <b>${oran(t.olasilik)}</b> (ortanca hareket ${yuzde(t.medyan)}).`;
  const kayit = (dedi, tuttu, taban, yon) =>
    `Bu yöntem son ${b.testHaftasi} haftada bu hisse için ${dedi} kez "${yon}" dedi; isabet oranı: <b>${oran(tuttu)}</b>. Her hafta körlemesine "${yon}" demenin isabeti: ${oran(taban)}.`;
  switch (a.karar) {
    case "YUKSELIS":
      return { sinif: "k-yesil", etiket: "Yükseliş eğilimi", ana: "Gelecek hafta: yükseliş eğilimi",
        metin: [benzer, kayit(b.yukselirDedi, b.yukselirTuttu, b.hepYukselirDeseydin, "yükselir"), "Bu fark şansla açıklanamayacak kadar büyük, yani bu hissede sinyal geçmişte işe yaramış. Yine de kesinlik değildir."] };
    case "DUSUS":
      return { sinif: "k-kirmizi", etiket: "Düşüş eğilimi", ana: "Gelecek hafta: düşüş eğilimi",
        metin: [benzer, kayit(b.duserDedi, b.duserTuttu, 1 - b.hepYukselirDeseydin, "düşer"), "Bu fark şansla açıklanamayacak kadar büyük, yani bu hissede sinyal geçmişte işe yaramış. Yine de kesinlik değildir."] };
    case "YUKSELIS_GUVENSIZ":
      return { sinif: "k-sari", etiket: "Yükseliş (güvenilmez)", ana: "Benzer haftalar yükselişi gösteriyor, ama güvenilir değil",
        metin: [benzer, b.yukselirDedi ? kayit(b.yukselirDedi, b.yukselirTuttu, b.hepYukselirDeseydin, "yükselir") : "", "Bu hissede yöntemin geçmiş isabeti körlemesine tahminden anlamlı ölçüde iyi değil. Bu sinyale güvenme."] };
    case "DUSUS_GUVENSIZ":
      return { sinif: "k-sari", etiket: "Düşüş (güvenilmez)", ana: "Benzer haftalar düşüşü gösteriyor, ama güvenilir değil",
        metin: [benzer, b.duserDedi ? kayit(b.duserDedi, b.duserTuttu, 1 - b.hepYukselirDeseydin, "düşer") : "", "Bu hissede yöntemin geçmiş isabeti körlemesine tahminden anlamlı ölçüde iyi değil. Bu sinyale güvenme."] };
    default:
      return { sinif: "k-gri", etiket: "Belirsiz", ana: "Gelecek hafta için net bir yön yok",
        metin: [benzer, "Benzer haftalarda yükselen ve düşen sayısı birbirine yakın. Veri bir yön göstermiyor."] };
  }
}

// ---------- grafik ----------
function grafik(d) {
  const n = d.close.length, bas = Math.max(0, n - 260);
  const c = d.close.slice(bas);
  const ort = (k) => d.close.slice(bas).map((_, j) => {
    const i = bas + j; if (i + 1 < k) return null;
    let s = 0; for (let q = i - k + 1; q <= i; q++) s += d.close[q]; return s / k;
  });
  const o50 = ort(50), o200 = ort(200);
  const hepsi = [...c, ...o50.filter(Boolean), ...o200.filter(Boolean)];
  const mn = Math.min(...hepsi), mx = Math.max(...hepsi);
  const W = 800, H = 220, p = 6;
  const x = (j) => p + (j / (c.length - 1)) * (W - 2 * p);
  const y = (v) => p + (1 - (v - mn) / (mx - mn || 1)) * (H - 2 * p);
  const yol = (arr) => arr.map((v, j) => (v == null ? null : `${x(j).toFixed(1)},${y(v).toFixed(1)}`)).filter(Boolean).join(" ");
  return `
    <svg class="grafik" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Son 1 yıl fiyat grafiği">
      <polyline points="${yol(o200)}" fill="none" stroke="#c9862b" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
      <polyline points="${yol(o50)}" fill="none" stroke="#8b5cf6" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
      <polyline points="${yol(c)}" fill="none" stroke="var(--vurgu)" stroke-width="2" vector-effect="non-scaling-stroke"/>
    </svg>
    <div class="lejant"><span><i style="background:var(--vurgu)"></i>Fiyat (son 1 yıl)</span><span><i style="background:#8b5cf6"></i>50 günlük ort.</span><span><i style="background:#c9862b"></i>200 günlük ort.</span></div>`;
}

// ---------- detay kartı ----------
async function goster(kod) {
  const kutu = $("#sonuc");
  kutu.innerHTML = `<div class="yukleniyor">${esc(kod)} için 5 yıllık veri indiriliyor ve geçmiş test ediliyor...</div>`;
  let v, a;
  try {
    v = await fiyatGetir(kod);
    a = analiz(v);
  } catch (e) {
    kutu.innerHTML = `<div class="hata">${esc(e.message)}</div>`;
    return;
  }
  if (a.hata) { kutu.innerHTML = `<div class="hata">${esc(a.hata)}</div>`; return; }
  sonuclar.set(kod, { v, a });
  const g = a.bugun, k = kararBilgi(a), pb = v.paraBirimi, b = a.basari;
  const kisa = v.sembol.replace(/\.IS$/, "");
  const listede = liste.includes(kisa);

  kutu.innerHTML = `
    <div class="kart">
      <div class="baslik">
        <div>
          <h2 style="margin:0">${esc(kisa)} <span class="ad">${esc(v.ad)} · ${esc(v.borsa || "")}</span></h2>
          <div class="fiyat">${para(g.fiyat, pb)} <span class="${renk(g.gunluk)}" style="font-size:1rem">${yuzde(g.gunluk, 2)} bugün</span></div>
          <div class="kucuk">Son veri: ${tarih(g.tarih)}</div>
        </div>
        <button class="ikincil" id="ekle">${listede ? "Listede ✓" : "+ Takip listeme ekle"}</button>
      </div>

      <div class="karar ${k.sinif}">
        <div class="ana">${esc(k.ana)}</div>
        ${k.metin.filter(Boolean).map((m) => `<p>${m}</p>`).join("")}
      </div>

      <div class="izgara">
        <div class="kutu"><div class="e">Benzer haftalarda 1 hafta sonra</div><div class="d">${oran(a.tahmin.olasilik)} yükseldi</div><div class="a">ortanca ${yuzde(a.tahmin.medyan)}</div></div>
        <div class="kutu"><div class="e">Benzer haftalarda olası aralık</div><div class="d">${yuzde(a.tahmin.kotu)} / ${yuzde(a.tahmin.iyi)}</div><div class="a">en kötü %10 / en iyi %10</div></div>
        <div class="kutu"><div class="e">Haftalık / aylık</div><div class="d"><span class="${renk(g.haftalik)}">${yuzde(g.haftalik)}</span> / <span class="${renk(g.aylik)}">${yuzde(g.aylik)}</span></div><div class="a">yıllık ${yuzde(g.yillik)}</div></div>
        <div class="kutu"><div class="e">52 hafta zirve / dip</div><div class="d">${para(g.zirve52, pb)}</div><div class="a">zirveye uzaklık ${yuzde(g.zirveyeUzaklik)} · dip ${para(g.dip52, pb)}</div></div>
        <div class="kutu"><div class="e">50 / 200 günlük ortalama</div><div class="d">${g.fiyat > g.ort50 ? "Üstünde" : "Altında"} / ${g.fiyat > g.ort200 ? "Üstünde" : "Altında"}</div><div class="a">${yuzde(g.fiyat / g.ort50 - 1)} / ${yuzde(g.fiyat / g.ort200 - 1)}</div></div>
        <div class="kutu"><div class="e">RSI (14)</div><div class="d">${g.rsi.toFixed(0)}</div><div class="a">${g.rsi >= 70 ? "aşırı alım bölgesi" : g.rsi <= 30 ? "aşırı satım bölgesi" : "normal bölge"}</div></div>
        <div class="kutu"><div class="e">Hacim (son 5 gün)</div><div class="d">${(g.hacimOrani).toFixed(2).replace(".", ",")}×</div><div class="a">50 günlük ortalamaya göre</div></div>
      </div>
      ${grafik(a.veri)}
    </div>

    <div class="kart">
      <h3>Bu tahmin ne kadar güvenilir?</h3>
      <table>
        <tr><th>Son ${b.testHaftasi} haftalık test</th><th class="sayi">Kaç kez</th><th class="sayi">Tuttu</th><th class="sayi">Körlemesine</th></tr>
        <tr><td>"Yükselir" dedi</td><td class="sayi">${b.yukselirDedi}</td><td class="sayi">${oran(b.yukselirTuttu)}</td><td class="sayi">${oran(b.hepYukselirDeseydin)}</td></tr>
        <tr><td>"Düşer" dedi</td><td class="sayi">${b.duserDedi}</td><td class="sayi">${oran(b.duserTuttu)}</td><td class="sayi">${oran(1 - b.hepYukselirDeseydin)}</td></tr>
      </table>
      <p class="kucuk">Her geçmiş hafta için tahmin, sadece o haftadan önce bilinen verilerle yapıldı, sonra gerçekleşenle karşılaştırıldı. "Körlemesine" sütunu, hiç analiz yapmadan her hafta aynı şeyi söyleseydin tutturacağın oran. Yöntem ancak bu sütunu anlamlı ölçüde geçiyorsa güvenilir sayılır.</p>
      <p class="kucuk">Bugüne en çok benzeyen haftalar: ${a.tahmin.ornekTarihler.map((o) => `${tarih(o.t)} (sonraki hafta <span class="${renk(o.y)}">${yuzde(o.y)}</span>)`).join(", ")}</p>
    </div>

    <div class="kart">
      <h3>Son 14 günün haberleri</h3>
      <ul class="haber" id="haberler"><li class="kucuk">Yükleniyor...</li></ul>
      <p class="kucuk">Başlıklar Google Haberler'den, değiştirilmeden gösteriliyor. Site haberleri yorumlamaz ve tahmine katmaz.</p>
    </div>`;

  $("#ekle").onclick = () => {
    if (!liste.includes(kisa)) { liste.push(kisa); listeYaz(liste); }
    $("#ekle").textContent = "Listede ✓";
    tabloCiz();
  };

  const h = await haberGetir(v.sembol, v.ad);
  const ul = $("#haberler");
  if (!ul) return;
  ul.innerHTML = h.length
    ? h.map((x) => `<li><a href="${esc(x.link)}" target="_blank" rel="noopener noreferrer">${esc(x.baslik)}</a><div class="m">${esc(x.kaynak)} · ${esc(x.tarih ? new Date(x.tarih).toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" }) : "")}</div></li>`).join("")
    : `<li class="kucuk">Son 14 günde bu hisse için haber bulunamadı.</li>`;
}

// ---------- takip listesi tablosu ----------
function tabloCiz() {
  $("#listeKutu").hidden = liste.length === 0;
  if (!liste.length) return;
  const satir = (kod) => {
    const s = sonuclar.get(kod) || sonuclar.get(`${kod}.IS`);
    if (!s) return `<tr class="tikla" data-kod="${esc(kod)}"><td><b>${esc(kod)}</b></td><td colspan="4" class="kucuk">taranmadı</td><td><button class="sil" data-sil="${esc(kod)}" aria-label="Sil">✕</button></td></tr>`;
    const k = kararBilgi(s.a);
    return `<tr class="tikla" data-kod="${esc(kod)}">
      <td><b>${esc(kod)}</b></td>
      <td><span class="etiket ${k.sinif}">${esc(k.etiket)}</span></td>
      <td class="sayi">${oran(s.a.tahmin.olasilik)}</td>
      <td class="sayi gizle-mobil">${s.a.basari.yukselirDedi ? `${oran(s.a.basari.yukselirTuttu)} / ${oran(s.a.basari.hepYukselirDeseydin)}` : "–"}</td>
      <td class="sayi ${renk(s.a.bugun.haftalik)}">${yuzde(s.a.bugun.haftalik)}</td>
      <td><button class="sil" data-sil="${esc(kod)}" aria-label="Sil">✕</button></td></tr>`;
  };
  const sirali = [...liste].sort((x, y) => {
    const a = sonuclar.get(x), b = sonuclar.get(y);
    return (b ? b.a.tahmin.olasilik : -1) - (a ? a.a.tahmin.olasilik : -1);
  });
  $("#tablo").innerHTML = `<div class="tablo-kap"><table>
    <tr><th>Hisse</th><th>Gelecek hafta</th><th class="sayi">Benzer haftalarda yükseliş</th><th class="sayi gizle-mobil">"Yükselir" isabeti / körlemesine</th><th class="sayi">Bu hafta</th><th></th></tr>
    ${sirali.map(satir).join("")}</table></div>`;
}

$("#tablo").addEventListener("click", (e) => {
  const sil = e.target.closest("[data-sil]");
  if (sil) {
    liste = liste.filter((k) => k !== sil.dataset.sil);
    listeYaz(liste); tabloCiz(); e.stopPropagation(); return;
  }
  const tr = e.target.closest("tr[data-kod]");
  if (tr) { goster(tr.dataset.kod); window.scrollTo({ top: $("#sonuc").offsetTop - 10, behavior: "smooth" }); }
});

$("#tara").onclick = async () => {
  const btn = $("#tara");
  btn.disabled = true;
  for (let i = 0; i < liste.length; i++) {
    btn.textContent = `Taranıyor ${i + 1}/${liste.length}...`;
    try {
      const v = await fiyatGetir(liste[i]);
      const a = analiz(v);
      if (!a.hata) sonuclar.set(liste[i], { v, a });
    } catch { /* tek hisse hatası taramayı durdurmasın */ }
    tabloCiz();
  }
  btn.disabled = false;
  btn.textContent = "Hepsini tara";
};
$("#temizle").onclick = () => { liste = []; listeYaz(liste); tabloCiz(); };

$("#form").onsubmit = (e) => {
  e.preventDefault();
  const kod = $("#kod").value.trim().toUpperCase().replace(/\s+/g, "");
  if (!kod) return;
  if (!/^[A-Z0-9][A-Z0-9.\-]{0,14}$/.test(kod)) {
    $("#sonuc").innerHTML = `<div class="hata">Geçersiz kod. Örnek: THYAO, ASELS, AAPL</div>`;
    return;
  }
  goster(kod);
};

$("#ornekler").innerHTML = ORNEKLER.map((k) => `<button class="cip" data-k="${k}">${k}</button>`).join("");
$("#ornekler").onclick = (e) => {
  const b = e.target.closest("[data-k]");
  if (b) { $("#kod").value = b.dataset.k; goster(b.dataset.k); }
};

tabloCiz();
