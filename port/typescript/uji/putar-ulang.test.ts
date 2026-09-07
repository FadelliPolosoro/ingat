// SPDX-License-Identifier: Apache-2.0
// Harness putar-ulang. Bagian fixture diuji sekarang; bagian gateway adalah tiket irisan 1.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { bacaFrontmatter } from '../src/simpan/frontmatter.ts';
import { lingkupValid, JENIS_KEJADIAN, TIER, BOBOT } from '../src/inti/jenis.ts';

const DIR = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', 'uji', 'putar-ulang'); // fixture dipakai bersama dengan implementasi rujukan
const KUNCI_WAJIB_PELAJARAN = ['id', 'pelajaran', 'pemicu', 'tindakan', 'lingkup', 'status', 'keyakinan', 'bukti', 'kontra', 'dibuat'];

function bacaFixture(u: string) {
  const dasar = join(DIR, u);
  const episode = readFileSync(join(dasar, 'episode.jsonl'), 'utf8')
    .split('\n')
    .filter((b) => b.trim())
    .map((b) => JSON.parse(b) as Record<string, unknown>);
  const pelajaran = readdirSync(join(dasar, 'pelajaran'))
    .filter((f) => f.endsWith('.md'))
    .map((f) => bacaFrontmatter(readFileSync(join(dasar, 'pelajaran', f), 'utf8')).data);
  const skenario = JSON.parse(readFileSync(join(dasar, 'skenario.json'), 'utf8')) as Record<string, unknown>;
  return { episode, pelajaran, skenario };
}

test('U1 fixture: episode valid terhadap kontrak 6.1', () => {
  const { episode } = bacaFixture('U1');
  assert.ok(episode.length >= 2);
  for (const e of episode) {
    assert.ok(TIER.includes(e.tier as never), `tier ${e.tier} tidak dikenal`);
    assert.ok(JENIS_KEJADIAN.includes(e.jenis_kejadian as never), `jenis ${e.jenis_kejadian} tidak dikenal`);
    assert.equal(e.bobot, BOBOT[e.jenis_kejadian as keyof typeof BOBOT], `bobot ${e.id} tidak sesuai 7.2`);
    assert.ok(lingkupValid(e.lingkup as string), `lingkup ${e.lingkup} tidak valid`);
  }
});

test('U1 fixture: pelajaran memuat kunci wajib, bukti menunjuk episode yang ada, lingkup terkunci (7.2)', () => {
  const { episode, pelajaran, skenario } = bacaFixture('U1');
  const idEpisode = new Set(episode.map((e) => e.id as string));
  for (const p of pelajaran) {
    for (const k of KUNCI_WAJIB_PELAJARAN) assert.ok(k in p, `pelajaran ${p.id} tanpa kunci ${k}`);
    for (const b of p.bukti as string[]) assert.ok(idEpisode.has(b), `bukti ${b} tidak ada di episode.jsonl`);
    assert.equal(p.lingkup, skenario.lingkup, 'pelajaran dari koreksi tunggal harus terkunci di lingkup asal');
  }
  for (const h of skenario.harapan as string[]) {
    assert.ok(pelajaran.some((p) => p.id === h), `harapan ${h} tidak ada di fixture`);
  }
});

test.todo('U1: ingat() dengan lingkup proyek:fp-dashboard mengembalikan pl-0001 di L-aturan/L-tarik [irisan 1]');
test.todo('U1 negatif: ingat() dengan lingkup proyek:garnivo TIDAK mengembalikan pl-0001 [irisan 1, P9]');
