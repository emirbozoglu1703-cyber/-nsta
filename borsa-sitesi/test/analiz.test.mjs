// node --test test/
import test from "node:test";
import assert from "node:assert/strict";
import { analiz } from "../public/analiz.js";

function rastgele(seed, n = 1260) {
  let s = seed;
  const r = () => ((s = (s * 1103515245 + 12345) % 2147483648) / 2147483648);
  const gauss = () => Math.sqrt(-2 * Math.log(r() + 1e-12)) * Math.cos(2 * Math.PI * r());
  const close = [100];
  for (let i = 1; i < n; i++) close.push(close[i - 1] * (1 + 0.02 * gauss()));
  return {
    t: close.map((_, i) => Date.UTC(2021, 0, 1) + i * 864e5),
    close, high: close.map((c) => c * 1.01), low: close.map((c) => c * 0.99),
    volume: close.map(() => 1e6 * (0.5 + r())),
  };
}

test("rastgele seride 'güvenilir' sinyal nadir olmalı (yanlış alarm ~%5)", () => {
  let guvenilir = 0, toplam = 40;
  for (let k = 1; k <= toplam; k++) {
    const a = analiz(rastgele(k * 7919));
    if (a.karar === "YUKSELIS" || a.karar === "DUSUS") guvenilir++;
  }
  console.log(`rastgele serilerde güvenilir sinyal: ${guvenilir}/${toplam}`);
  assert.ok(guvenilir <= 5, `çok fazla yanlış alarm: ${guvenilir}/${toplam}`);
});

test("geleceğe bakmıyor: son haftayı değiştirmek geçmiş testi değiştirmez", () => {
  const v = rastgele(42);
  const a1 = analiz(v);
  const v2 = structuredClone(v);
  for (let i = v2.close.length - 5; i < v2.close.length; i++) v2.close[i] *= 1.5;
  const a2 = analiz(v2);
  // Son haftanın sonucu sadece en son test haftasını etkileyebilir.
  assert.ok(Math.abs(a1.basari.testHaftasi - a2.basari.testHaftasi) === 0);
  assert.ok(Math.abs(a1.basari.yukselirDedi - a2.basari.yukselirDedi) <= 1);
});

test("az veri: anlaşılır hata", () => {
  const v = rastgele(1, 300);
  assert.match(analiz(v).hata, /yeterli geçmiş veri yok/);
});

test("eksik (null) fiyatlar atlanır", () => {
  const v = rastgele(3);
  v.close[500] = null;
  const a = analiz(v);
  assert.ok(!a.hata && isFinite(a.tahmin.olasilik));
});
