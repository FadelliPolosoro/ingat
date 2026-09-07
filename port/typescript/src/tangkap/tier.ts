// SPDX-License-Identifier: Apache-2.0
// Penanda tier (K10): data pribadi TIDAK diredaksi, tetapi episode ditandai S.
// Default episode Claude Code = I (K10/K11). Naik ke S bila pola di bawah terpicu.
// Turun ke P tidak pernah otomatis.

import type { Tier } from '../inti/jenis.ts';

export interface PolaTier {
  nama: string;
  pola: RegExp;
}

export const POLA_TIER_S: readonly PolaTier[] = [
  { nama: 'nik', pola: /\b\d{16}\b/ },                                        // NIK 16 digit
  { nama: 'npwp', pola: /\b\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}\b/ },         // NPWP format titik-strip
  { nama: 'npwp-16', pola: /\bNPWP\s*[:#]?\s*\d{15,16}\b/i },                 // NPWP 15/16 digit berlabel
  { nama: 'rekening', pola: /\b(?:no\.?\s*)?rek(?:ening)?\s*[:#]?\s*\d{10,16}\b/i },
  { nama: 'kata-kunci-sensitif', pola: /\b(payroll|slip gaji|bukti potong|SPT|faktur pajak|e-faktur)\b/i },
];

export interface HasilTier {
  tier: Tier;
  alasan: string[];
}

export function tandaiTier(teks: string, dasar: Tier = 'I'): HasilTier {
  const alasan = POLA_TIER_S.filter((p) => p.pola.test(teks)).map((p) => p.nama);
  if (alasan.length > 0) return { tier: 'S', alasan };
  return { tier: dasar, alasan: [] };
}
