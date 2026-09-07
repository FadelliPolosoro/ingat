// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { bacaFrontmatter, tulisFrontmatter, FrontmatterRusak } from '../src/simpan/frontmatter.ts';

const contoh = `---
id: pl-0001
pelajaran: Ketiadaan hasil dari instrumen ≠ ketiadaan objek; instrumen punya cakupan.
lingkup: proyek:fp-dashboard
status: aturan
keyakinan: 0.9
bukti: ["ep-2026-09-06-0001"]
kontra: []
berlaku_untuk: {}
tinjau_ulang: false
veto_manusia: null
---
Badan catatan.
`;

test('membaca subset YAML: skalar, angka, boolean, null, JSON flow', () => {
  const { data, badan } = bacaFrontmatter(contoh);
  assert.equal(data.id, 'pl-0001');
  assert.equal(data.lingkup, 'proyek:fp-dashboard');
  assert.equal(data.keyakinan, 0.9);
  assert.deepEqual(data.bukti, ['ep-2026-09-06-0001']);
  assert.deepEqual(data.kontra, []);
  assert.deepEqual(data.berlaku_untuk, {});
  assert.equal(data.tinjau_ulang, false);
  assert.equal(data.veto_manusia, null);
  assert.equal(badan.trim(), 'Badan catatan.');
});

test('nilai dengan titik dua di dalam string polos tetap utuh', () => {
  const { data } = bacaFrontmatter('---\npemicu: akan menyimpulkan "tidak ada X": cek dulu\n---\n');
  assert.equal(data.pemicu, 'akan menyimpulkan "tidak ada X": cek dulu');
});

test('bulat-balik tulis → baca', () => {
  const data = { id: 'pl-9', bukti: ['a', 'b'], keyakinan: 0.5, catatan: 'teks: dengan titik dua', kosong: null };
  const { data: kembali } = bacaFrontmatter(tulisFrontmatter(data, 'badan'));
  assert.deepEqual(kembali, data);
});

test('frontmatter rusak dilaporkan, tidak diam-diam diabaikan', () => {
  assert.throws(() => bacaFrontmatter('---\nid: x\n'), FrontmatterRusak);
  assert.throws(() => bacaFrontmatter('---\nbukti: [tidak-json\n---\n'), FrontmatterRusak);
  assert.throws(() => bacaFrontmatter('---\nKunci Besar: x\n---\n'), FrontmatterRusak);
});
