// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { bukaDb, versiKontrak, simpanEpisode, ambilEpisode } from '../src/simpan/sqlite.ts';
import type { Episode } from '../src/inti/jenis.ts';
import { normaBerlakuPada } from '../src/inti/jenis.ts';

const contoh: Episode = {
  id: 'ep-2026-09-06-0001',
  waktu: '2026-09-06T14:20:00+07:00',
  sumber: 'claude-code',
  tier: 'I',
  lingkup: 'proyek:fp-dashboard',
  instrumen: ['hostinger-mcp'],
  jenis_kejadian: 'koreksi',
  bobot: 5,
  status: 'aktif',
  ringkas: 'VPS_getProjectListV1 kosong disimpulkan tidak ada beban kerja; deploy manual SSH tidak terlihat.',
  isi: 'Human: kok dibilang tidak ada workload? Assistant: ...',
  isi_ref: null,
  diredaksi: [],
  langkah: ['VPS_getProjectListV1'],
  sesi: 'sesi-uji-1',
};

test('skema diterapkan dan versi_kontrak terbaca', () => {
  const db = bukaDb(':memory:');
  assert.equal(versiKontrak(db), '2');
  db.close();
});

test('episode: tulis lalu baca kembali identik (verbatim, K10)', () => {
  const db = bukaDb(':memory:');
  simpanEpisode(db, contoh);
  assert.deepEqual(ambilEpisode(db, contoh.id), contoh);
  assert.equal(ambilEpisode(db, 'tidak-ada'), null);
  db.close();
});

test('CHECK constraint menolak tier dan jenis_kejadian di luar kontrak', () => {
  const db = bukaDb(':memory:');
  assert.throws(() => simpanEpisode(db, { ...contoh, id: 'x1', tier: 'X' as Episode['tier'] }), /CHECK|constraint/i);
  assert.throws(
    () => simpanEpisode(db, { ...contoh, id: 'x2', jenis_kejadian: 'entah' as Episode['jenis_kejadian'] }),
    /CHECK|constraint/i,
  );
  db.close();
});

test('normaBerlakuPada: jendela bitemporal satu klausa (v2)', () => {
  const lama = { status: 'dicabut' as const, berlaku_sejak: '2018-03-22', berlaku_sampai: '2025-06-01' };
  const baru = { status: 'berlaku' as const, berlaku_sejak: '2025-06-01', berlaku_sampai: null };
  assert.equal(normaBerlakuPada(lama, '2024-01-15'), true, 'kontrak 2024 tunduk pada norma lama');
  assert.equal(normaBerlakuPada(baru, '2024-01-15'), false);
  assert.equal(normaBerlakuPada(lama, '2025-06-01'), false, 'hari pengganti berlaku: yang lama sudah tidak');
  assert.equal(normaBerlakuPada(baru, '2026-09-07'), true);
  assert.equal(normaBerlakuPada({ ...baru, status: 'dibatalkan' }, '2026-09-07'), false);
});
