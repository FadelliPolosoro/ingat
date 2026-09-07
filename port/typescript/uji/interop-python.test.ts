// SPDX-License-Identifier: Apache-2.0
// SELARAS tiket 5 (bagian baca): DB yang ditulis implementasi rujukan Python terbaca oleh port TS lewat kontrak v2.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { bukaDb, versiKontrak, ambilEpisode, transisiDariSkema } from '../src/simpan/sqlite.ts';
import { TRANSISI } from '../src/inti/status.ts';

const AKAR = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

const SKRIP = `
import os, sys
sys.path.insert(0, ${JSON.stringify(AKAR)})
from ingat.simpan import Store
from ingat.vektor import PenyematLokal
d = sys.argv[1]
s = Store(os.path.join(d, 'data'), PenyematLokal())
ep = s.tambah_episode('[verbatim] VPS_getProjectListV1 kosong', sumber='claude-code', tier='I', lingkup='proyek:fp-dashboard',
                      jenis_kejadian='koreksi', ringkas='tool kosong disimpulkan tidak ada objek', instrumen=['hostinger-mcp'], sesi='s1')
print(ep.id)
s.db.close()
`;

test('DB tulisan Python terbaca port TS: versi kontrak, episode, transisi', (t) => {
  const py = spawnSync('python3', ['--version']);
  if (py.status !== 0) {
    t.skip('python3 tidak tersedia — uji interop dilewati');
    return;
  }
  const dir = mkdtempSync(join(tmpdir(), 'ingat-interop-'));
  try {
    const hasil = spawnSync('python3', ['-c', SKRIP, dir], { encoding: 'utf8' });
    assert.equal(hasil.status, 0, hasil.stderr);
    const id = hasil.stdout.trim();
    const db = bukaDb(join(dir, 'data', 'ingat.sqlite'));
    assert.equal(versiKontrak(db), '2', 'Python harus menulis versi_kontrak = 2');
    const ep = ambilEpisode(db, id);
    assert.ok(ep, 'episode Python harus terbaca');
    assert.equal(ep!.lingkup, 'proyek:fp-dashboard');
    assert.equal(ep!.jenis_kejadian, 'koreksi');
    assert.equal(ep!.bobot, 5);
    assert.deepEqual(ep!.instrumen, ['hostinger-mcp']);
    assert.equal(ep!.sesi, 's1');
    assert.equal(ep!.isi, null, 'Python menyimpan verbatim di isi_ref, isi NULL');
    assert.ok(ep!.isi_ref, 'isi_ref harus terisi');
    // state machine yang ditulis Python identik dengan peta TS
    const kunci = (x: { jenis: string; dari: string; ke: string; oleh: string }) => `${x.jenis}|${x.dari}|${x.ke}|${x.oleh}`;
    assert.deepEqual(new Set(transisiDariSkema(db).map(kunci)), new Set(TRANSISI.map(kunci)));
    // vektor tersimpan di tabel kontrak dengan koleksi 'isi'
    const v = db.prepare("SELECT koleksi, dimensi FROM vektor WHERE item_id = ? AND jenis = 'episode'").all(id) as { koleksi: string; dimensi: number }[];
    assert.deepEqual(v.map((x) => x.koleksi), ['isi']);
    assert.equal(v[0]!.dimensi, 512);
    db.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
