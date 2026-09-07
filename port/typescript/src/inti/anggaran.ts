// SPDX-License-Identifier: Apache-2.0
// Anggaran konteks (spek Bab 8: anti-Spalko). Murni.

export interface Berjatah {
  id: string;
  teks: string;       // isi yang akan disuntik
  ringkas: string;    // ≤ 20 kata, dipakai untuk pointer
}

export interface HasilPotong<T extends Berjatah> {
  item: T[];
  pointer: { id: string; ringkas: string }[];
  tokenTerpakai: number;
}

/** Perkiraan token kasar: ~4 karakter per token. Cukup untuk anggaran, bukan untuk tagihan. */
export function perkiraanToken(teks: string): number {
  return Math.ceil(teks.length / 4);
}

/**
 * Potong daftar (sudah terurut prioritas) pada anggaran token.
 * Retrieval berhenti saat anggaran habis, bukan saat hasil habis (8.4).
 * Sisa dikembalikan sebagai pointer, bukan isi (P7).
 */
export function potongAnggaran<T extends Berjatah>(
  urut: T[],
  anggaranToken: number,
  hitung: (t: string) => number = perkiraanToken,
): HasilPotong<T> {
  const item: T[] = [];
  const pointer: { id: string; ringkas: string }[] = [];
  let terpakai = 0;
  for (const it of urut) {
    const biaya = hitung(it.teks);
    if (terpakai + biaya <= anggaranToken) {
      item.push(it);
      terpakai += biaya;
    } else {
      pointer.push({ id: it.id, ringkas: potongKata(it.ringkas, 20) });
    }
  }
  return { item, pointer, tokenTerpakai: terpakai };
}

export function potongKata(teks: string, maksKata: number): string {
  const kata = teks.trim().split(/\s+/);
  return kata.length <= maksKata ? teks.trim() : kata.slice(0, maksKata).join(' ') + '…';
}

/** Anggaran usulan awal (spek 8.2). Angka kalibrasi, bukan hasil ukur. */
export const ANGGARAN_DEFAULT = {
  peta: 300,
  aturan: 1500,
  tarikPerPanggilan: 600,
  itemPerPanggilan: 5,
  rasioMaksimal: 0.15,
} as const;
