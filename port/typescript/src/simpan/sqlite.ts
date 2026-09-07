// SPDX-License-Identifier: Apache-2.0
// Adapter SQLite via node:sqlite (Node ≥ 22.13). Satu-satunya tempat pragma SQLite boleh muncul.

import { DatabaseSync } from 'node:sqlite';
import { readFileSync, existsSync, chmodSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import type { Episode } from '../inti/jenis.ts';

const DIR = dirname(fileURLToPath(import.meta.url));
export const JALUR_SKEMA = join(DIR, '..', '..', '..', '..', 'skema', 'ingat.sql'); // port/typescript/src/simpan → akar repo

export function bukaDb(jalur: string): DatabaseSync {
  const baru = jalur !== ':memory:' && !existsSync(jalur);
  const db = new DatabaseSync(jalur);
  if (jalur !== ':memory:') {
    db.exec('PRAGMA journal_mode = WAL;');
    if (baru) {
      try {
        chmodSync(jalur, 0o600);
      } catch {
        /* Windows: izin POSIX tidak berlaku; diabaikan */
      }
    }
  }
  db.exec('PRAGMA foreign_keys = ON;');
  db.exec(readFileSync(JALUR_SKEMA, 'utf8'));
  return db;
}

export function versiKontrak(db: DatabaseSync): string {
  const r = db.prepare("SELECT nilai FROM meta WHERE kunci = 'versi_kontrak'").get() as
    | { nilai: string }
    | undefined;
  if (!r) throw new Error('meta.versi_kontrak tidak ada — skema belum diterapkan');
  return r.nilai;
}

export function simpanEpisode(db: DatabaseSync, e: Episode): void {
  db.prepare(
    `INSERT INTO episode (id, waktu, sumber, tier, lingkup, instrumen, jenis_kejadian, bobot, status, ringkas, isi, isi_ref, diredaksi, langkah, sesi)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).run(
    e.id,
    e.waktu,
    e.sumber,
    e.tier,
    e.lingkup,
    JSON.stringify(e.instrumen),
    e.jenis_kejadian,
    e.bobot,
    e.status,
    e.ringkas,
    e.isi,
    e.isi_ref,
    JSON.stringify(e.diredaksi),
    JSON.stringify(e.langkah),
    e.sesi,
  );
}

export function ambilEpisode(db: DatabaseSync, id: string): Episode | null {
  const r = db.prepare('SELECT * FROM episode WHERE id = ?').get(id) as Record<string, unknown> | undefined;
  if (!r) return null;
  return {
    id: r.id as string,
    waktu: r.waktu as string,
    sumber: r.sumber as string,
    tier: r.tier as Episode['tier'],
    lingkup: r.lingkup as Episode['lingkup'],
    instrumen: JSON.parse((r.instrumen as string) ?? '[]') as string[],
    jenis_kejadian: r.jenis_kejadian as Episode['jenis_kejadian'],
    bobot: r.bobot as number,
    status: r.status as Episode['status'],
    ringkas: r.ringkas as string,
    isi: (r.isi as string | null) ?? null,
    isi_ref: (r.isi_ref as string | null) ?? null,
    diredaksi: JSON.parse((r.diredaksi as string) ?? '[]') as string[],
    langkah: JSON.parse((r.langkah as string) ?? '[]') as string[],
    sesi: (r.sesi as string | null) ?? null,
  };
}

/** Transisi yang tercatat di skema — dipakai uji untuk memastikan TS dan SQL identik. */
export function transisiDariSkema(db: DatabaseSync): { jenis: string; dari: string; ke: string; oleh: string }[] {
  // node:sqlite mengembalikan objek berprototipe null; disalin ke objek biasa supaya deepStrictEqual adil.
  return (db.prepare('SELECT jenis, dari, ke, oleh FROM transisi_status ORDER BY jenis, dari, ke').all() as Record<string, unknown>[]).map(
    (r) => ({ jenis: r.jenis as string, dari: r.dari as string, ke: r.ke as string, oleh: r.oleh as string }),
  );
}
