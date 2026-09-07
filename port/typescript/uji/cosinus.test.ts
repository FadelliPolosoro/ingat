// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { cariTerdekat, normalisasiL2, keBlob, dariBlob } from '../src/inti/cosinus.ts';
import { potongAnggaran } from '../src/inti/anggaran.ts';
import { PenyematPalsu } from './bantuan/penyemat-palsu.ts';

test('cariTerdekat: allowlist membatasi kandidat, bukan hanya memfilter hasil', () => {
  const q = normalisasiL2(Float32Array.from([1, 0, 0]));
  const kandidat = [
    { id: 'a', vektor: normalisasiL2(Float32Array.from([1, 0, 0])) },
    { id: 'b', vektor: normalisasiL2(Float32Array.from([0.9, 0.1, 0])) },
    { id: 'c', vektor: normalisasiL2(Float32Array.from([0, 1, 0])) },
  ];
  assert.deepEqual(cariTerdekat(q, kandidat, 2).map((h) => h.id), ['a', 'b']);
  assert.deepEqual(cariTerdekat(q, kandidat, 2, new Set(['c'])).map((h) => h.id), ['c']);
});

test('blob float32 bulat-balik', () => {
  const v = Float32Array.from([0.25, -1.5, 3]);
  assert.deepEqual(Array.from(dariBlob(keBlob(v), 3)), Array.from(v));
  assert.throws(() => dariBlob(keBlob(v), 4));
});

test('penyemat palsu deterministik dan ternormalisasi', async () => {
  const p = new PenyematPalsu(32);
  const [a, b] = await p.sematkan(['tool kosong bukan berarti tidak ada', 'tool kosong bukan berarti tidak ada'], 'query');
  assert.deepEqual(Array.from(a!), Array.from(b!));
  let n = 0;
  for (const x of a!) n += x * x;
  assert.ok(Math.abs(n - 1) < 1e-5, 'norma L2 harus 1');
});

test('potongAnggaran: berhenti saat anggaran habis, sisa jadi pointer (8.4)', () => {
  const urut = [
    { id: '1', teks: 'x'.repeat(400), ringkas: 'satu' },
    { id: '2', teks: 'y'.repeat(400), ringkas: 'dua' },
    { id: '3', teks: 'z'.repeat(400), ringkas: 'tiga' },
  ];
  const h = potongAnggaran(urut, 250); // 400 karakter ≈ 100 token per item
  assert.deepEqual(h.item.map((i) => i.id), ['1', '2']);
  assert.deepEqual(h.pointer, [{ id: '3', ringkas: 'tiga' }]);
  assert.equal(h.tokenTerpakai, 200);
});
