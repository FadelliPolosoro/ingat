// SPDX-License-Identifier: Apache-2.0
// State machine status (spek Bab 5). Murni: tanpa I/O.
// Sumber kebenaran ganda disengaja: tabel `transisi_status` di skema untuk port lain,
// dan peta di sini untuk kode TS. Uji `uji/status.test.ts` memastikan keduanya identik.

import type { Aktor, JenisItem } from './jenis.ts';

export type Pelaku = Aktor | 'keduanya';

export interface Transisi {
  jenis: JenisItem;
  dari: string;
  ke: string;
  oleh: Pelaku;
}

export const TRANSISI: readonly Transisi[] = [
  { jenis: 'episode', dari: 'aktif', ke: 'didinginkan', oleh: 'keduanya' },
  { jenis: 'episode', dari: 'didinginkan', ke: 'diarsipkan', oleh: 'keduanya' },
  { jenis: 'pelajaran', dari: 'hipotesis', ke: 'usulan', oleh: 'keduanya' },
  { jenis: 'pelajaran', dari: 'usulan', ke: 'aturan', oleh: 'manusia' },
  { jenis: 'pelajaran', dari: 'aturan', ke: 'dipersempit', oleh: 'keduanya' },
  { jenis: 'pelajaran', dari: 'hipotesis', ke: 'ditarik', oleh: 'keduanya' },
  { jenis: 'pelajaran', dari: 'usulan', ke: 'ditarik', oleh: 'keduanya' },
  { jenis: 'pelajaran', dari: 'aturan', ke: 'ditarik', oleh: 'keduanya' },
  { jenis: 'pelajaran', dari: 'dipersempit', ke: 'ditarik', oleh: 'keduanya' },
  { jenis: 'pelajaran', dari: 'dipersempit', ke: 'aturan', oleh: 'manusia' }, // pemulihan domain
  { jenis: 'prosedur', dari: 'draf', ke: 'teruji', oleh: 'keduanya' },
  { jenis: 'prosedur', dari: 'teruji', ke: 'aktif', oleh: 'manusia' },
  { jenis: 'prosedur', dari: 'aktif', ke: 'dipersempit', oleh: 'keduanya' },
  { jenis: 'prosedur', dari: 'draf', ke: 'ditarik', oleh: 'keduanya' },
  { jenis: 'prosedur', dari: 'teruji', ke: 'ditarik', oleh: 'keduanya' },
  { jenis: 'prosedur', dari: 'aktif', ke: 'ditarik', oleh: 'keduanya' },
  { jenis: 'prosedur', dari: 'dipersempit', ke: 'ditarik', oleh: 'keduanya' },
  { jenis: 'prosedur', dari: 'dipersempit', ke: 'aktif', oleh: 'manusia' }, // pemulihan domain
  { jenis: 'norma', dari: 'berlaku', ke: 'dicabut', oleh: 'manusia' },
  { jenis: 'norma', dari: 'berlaku', ke: 'dibatalkan', oleh: 'manusia' },
] as const;

export class TransisiTerlarang extends Error {
  readonly jenis: JenisItem;
  readonly dari: string;
  readonly ke: string;
  readonly oleh: Aktor;
  constructor(jenis: JenisItem, dari: string, ke: string, oleh: Aktor, sebab: string) {
    super(`transisi ${jenis}: ${dari} → ${ke} oleh ${oleh} terlarang (${sebab})`);
    this.name = 'TransisiTerlarang';
    this.jenis = jenis;
    this.dari = dari;
    this.ke = ke;
    this.oleh = oleh;
  }
}

function cari(jenis: JenisItem, dari: string, ke: string): Transisi | undefined {
  return TRANSISI.find((t) => t.jenis === jenis && t.dari === dari && t.ke === ke);
}

/** Apakah transisi diizinkan untuk aktor ini? */
export function bolehTransisi(jenis: JenisItem, dari: string, ke: string, oleh: Aktor): boolean {
  const t = cari(jenis, dari, ke);
  if (!t) return false;
  return t.oleh === 'keduanya' || t.oleh === oleh;
}

/** Validasi transisi; lempar TransisiTerlarang bila tidak diizinkan. Mengembalikan status baru. */
export function transisi(jenis: JenisItem, dari: string, ke: string, oleh: Aktor): string {
  const t = cari(jenis, dari, ke);
  if (!t) throw new TransisiTerlarang(jenis, dari, ke, oleh, 'tidak ada di tabel transisi');
  if (t.oleh !== 'keduanya' && t.oleh !== oleh) {
    throw new TransisiTerlarang(jenis, dari, ke, oleh, `hanya ${t.oleh}`);
  }
  return ke;
}

/** Status tujuan yang bisa dicapai dari `dari` oleh aktor ini. */
export function statusBerikut(jenis: JenisItem, dari: string, oleh: Aktor): string[] {
  return TRANSISI.filter(
    (t) => t.jenis === jenis && t.dari === dari && (t.oleh === 'keduanya' || t.oleh === oleh),
  ).map((t) => t.ke);
}

/** Jalur keluar (spek 5.1) — status dari mana tidak ada transisi lanjut. */
export const JALUR_KELUAR = ['diarsipkan', 'ditarik', 'dicabut', 'dibatalkan'] as const;
