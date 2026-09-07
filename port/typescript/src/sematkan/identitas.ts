// SPDX-License-Identifier: Apache-2.0
import type { DatabaseSync } from 'node:sqlite';
import type { Penyemat } from './antarmuka.ts';

export class IdentitasEmbedderTidakCocok extends Error {
  constructor(pesan: string) {
    super(pesan);
    this.name = 'IdentitasEmbedderTidakCocok';
  }
}

/**
 * Pastikan koleksi dibangun dengan model yang sama. Pertama kali: catat. Berikutnya: cocokkan.
 * Ketidakcocokan = error keras, bukan peringatan — ganti model diam-diam menurunkan recall tanpa gejala.
 */
export function cekIdentitas(db: DatabaseSync, koleksi: string, p: Penyemat, waktu: string = new Date().toISOString()): void {
  const r = db.prepare('SELECT model, dimensi FROM identitas_embedder WHERE koleksi = ?').get(koleksi) as
    | { model: string; dimensi: number }
    | undefined;
  if (!r) {
    db.prepare('INSERT INTO identitas_embedder (koleksi, model, dimensi, dicatat) VALUES (?, ?, ?, ?)').run(
      koleksi,
      p.model,
      p.dimensi,
      waktu,
    );
    return;
  }
  if (r.dimensi !== p.dimensi) {
    throw new IdentitasEmbedderTidakCocok(
      `koleksi '${koleksi}' dibangun ${r.dimensi}-dim (${r.model}); penyemat sekarang ${p.dimensi}-dim (${p.model}). Bangun ulang koleksi.`,
    );
  }
  if (r.model !== p.model) {
    throw new IdentitasEmbedderTidakCocok(
      `koleksi '${koleksi}' dibangun dengan ${r.model}; penyemat sekarang ${p.model}. Bangun ulang koleksi atau catat ulang identitas secara eksplisit.`,
    );
  }
}
