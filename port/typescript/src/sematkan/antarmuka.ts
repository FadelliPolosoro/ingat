// SPDX-License-Identifier: Apache-2.0
// Satu-satunya ketergantungan yang tidak bisa dibuat dari nol: model embedding.
// Diisolasi di balik antarmuka ini; identitas model dicatat per koleksi.

export type PeranTeks = 'query' | 'passage';

export interface Penyemat {
  /** Nama model yang stabil, dipakai untuk identitas koleksi (mis. 'ingat-e5-base@sha256:…') */
  readonly model: string;
  readonly dimensi: number;
  /** Mengembalikan vektor yang SUDAH dinormalisasi L2, satu per teks. */
  sematkan(teks: string[], peran: PeranTeks): Promise<Float32Array[]>;
}

/** Jendela e5 = 512 token; batas karakter konservatif sebelum kirim (KEPUTUSAN.md). */
export const MAKS_KARAKTER_SEMAT = 1500;

export function potongUntukSemat(teks: string, maks: number = MAKS_KARAKTER_SEMAT): string {
  return teks.length <= maks ? teks : teks.slice(0, maks);
}
