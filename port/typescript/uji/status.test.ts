// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { bolehTransisi, transisi, TransisiTerlarang, statusBerikut, TRANSISI } from '../src/inti/status.ts';
import { bukaDb, transisiDariSkema } from '../src/simpan/sqlite.ts';

test('usulan → aturan hanya boleh oleh manusia (P10)', () => {
  assert.equal(bolehTransisi('pelajaran', 'usulan', 'aturan', 'manusia'), true);
  assert.equal(bolehTransisi('pelajaran', 'usulan', 'aturan', 'mesin'), false);
  assert.throws(() => transisi('pelajaran', 'usulan', 'aturan', 'mesin'), TransisiTerlarang);
});

test('hipotesis → aturan langsung terlarang untuk siapa pun (5.2)', () => {
  assert.equal(bolehTransisi('pelajaran', 'hipotesis', 'aturan', 'manusia'), false);
  assert.equal(bolehTransisi('pelajaran', 'hipotesis', 'aturan', 'mesin'), false);
});

test('norma tidak pernah dipersempit atau ditarik; hanya dicabut/dibatalkan oleh manusia', () => {
  assert.deepEqual(statusBerikut('norma', 'berlaku', 'manusia').sort(), ['dibatalkan', 'dicabut']);
  assert.deepEqual(statusBerikut('norma', 'berlaku', 'mesin'), []);
  assert.equal(bolehTransisi('norma', 'berlaku', 'dipersempit', 'manusia'), false);
});

test('pelajaran tidak pernah abadi, tidak pernah dicabut', () => {
  for (const dari of ['hipotesis', 'usulan', 'aturan', 'dipersempit']) {
    assert.equal(bolehTransisi('pelajaran', dari, 'abadi', 'manusia'), false, `${dari} → abadi harus terlarang`);
    assert.equal(bolehTransisi('pelajaran', dari, 'dicabut', 'manusia'), false, `${dari} → dicabut harus terlarang`);
  }
});

test('pemulihan domain: dipersempit → aturan/aktif hanya manusia', () => {
  assert.equal(bolehTransisi('pelajaran', 'dipersempit', 'aturan', 'manusia'), true);
  assert.equal(bolehTransisi('pelajaran', 'dipersempit', 'aturan', 'mesin'), false);
  assert.equal(bolehTransisi('prosedur', 'dipersempit', 'aktif', 'manusia'), true);
  assert.equal(bolehTransisi('prosedur', 'dipersempit', 'aktif', 'mesin'), false);
});

test('prosedur: draf → aktif langsung terlarang; teruji → aktif hanya manusia', () => {
  assert.equal(bolehTransisi('prosedur', 'draf', 'aktif', 'manusia'), false);
  assert.equal(bolehTransisi('prosedur', 'teruji', 'aktif', 'mesin'), false);
  assert.equal(bolehTransisi('prosedur', 'teruji', 'aktif', 'manusia'), true);
});

test('tabel transisi_status di skema identik dengan TRANSISI di TS (kontrak untuk port lain)', () => {
  const db = bukaDb(':memory:');
  const kunci = (t: { jenis: string; dari: string; ke: string }) => `${t.jenis}|${t.dari}|${t.ke}`;
  const urut = <T extends { jenis: string; dari: string; ke: string }>(xs: T[]) =>
    [...xs].sort((a, b) => (kunci(a) < kunci(b) ? -1 : kunci(a) > kunci(b) ? 1 : 0));
  const dariSql = urut(transisiDariSkema(db));
  const dariTs = urut(TRANSISI.map((t) => ({ jenis: t.jenis, dari: t.dari, ke: t.ke, oleh: t.oleh as string })));
  assert.deepEqual(dariSql, dariTs, 'skema SQL dan peta TS harus sama persis');
  db.close();
});
