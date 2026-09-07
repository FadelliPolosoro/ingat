// SPDX-License-Identifier: Apache-2.0
// Tipe kontrak. Tidak ada I/O di folder inti/.

export const JENIS_ITEM = ['episode', 'pelajaran', 'prosedur', 'norma'] as const;
export type JenisItem = (typeof JENIS_ITEM)[number];

export const TIER = ['P', 'I', 'S'] as const;
export type Tier = (typeof TIER)[number];

export const JENIS_KEJADIAN = ['koreksi', 'kegagalan', 'pola', 'sukses'] as const;
export type JenisKejadian = (typeof JENIS_KEJADIAN)[number];

/** Bobot per jenis kejadian (spek 7.2) */
export const BOBOT: Record<JenisKejadian, number> = {
  koreksi: 5,
  kegagalan: 3,
  pola: 2,
  sukses: 1,
};

/** Ambang bobot kumulatif: hipotesis → usulan (spek 7.2) */
export const AMBANG_USULAN = 5;

export type Aktor = 'mesin' | 'manusia';

export type Lingkup = 'global' | `proyek:${string}` | `peran:${string}`;

export function lingkupValid(s: string): s is Lingkup {
  return s === 'global' || s.startsWith('proyek:') || s.startsWith('peran:');
}

/** Item dengan lingkup L boleh dipakai di sesi berlingkup S bila L global atau L === S. */
export function lingkupMemuat(lingkupItem: string, lingkupSesi: string): boolean {
  return lingkupItem === 'global' || lingkupItem === lingkupSesi;
}

export interface Episode {
  id: string;
  waktu: string;
  sumber: string;
  tier: Tier;
  lingkup: Lingkup;
  instrumen: string[];
  jenis_kejadian: JenisKejadian;
  bobot: number;
  status: 'aktif' | 'didinginkan' | 'diarsipkan';
  ringkas: string;
  isi: string | null;
  isi_ref: string | null;
  diredaksi: string[];
  langkah: string[];        // v2
  sesi: string | null;      // v2
}

export interface Pelajaran {
  id: string;
  pelajaran: string;
  pemicu: string;
  tindakan: string;
  lingkup: Lingkup;
  status: 'hipotesis' | 'usulan' | 'aturan' | 'dipersempit' | 'ditarik';
  keyakinan: number;
  bukti: string[];
  kontra: string[];
  instrumen_saat_dibuat: string[];
  berlaku_untuk: Record<string, string>;
  tinjau_setelah: string | null;
  dibuat: string;
  terakhir_dikonfirmasi: string | null;
  tinjau_ulang: boolean;
  ditinjau_manusia: boolean;
  veto_manusia: string | null;
  berkas: string | null;
  tier_maks: Tier | null;                 // v2
  usulan_perluasan_lingkup: string[];     // v2
  sintesis: string | null;                // v2
  catatan: string | null;                 // v2
}

export interface Prosedur {
  id: string;
  prosedur: string;
  tugas_pemicu: string;
  langkah: string[];
  bentuk: string;
  lingkup: Lingkup;
  status: 'draf' | 'teruji' | 'aktif' | 'dipersempit' | 'ditarik';
  tingkat_berhasil: number;               // cache = eksekusi_berhasil / eksekusi_total
  bukti: string[];
  berlaku_untuk: Record<string, string>;
  tinjau_setelah: string | null;
  uji: string | null;
  ditinjau_manusia: boolean;
  berkas: string | null;
  eksekusi_total: number;                 // v2
  eksekusi_berhasil: number;              // v2
  gagal_beruntun: number;                 // v2
  tinjau_ulang: boolean;                  // v2
  veto_manusia: string | null;            // v2
  dibuat: string | null;                  // v2
  tier_maks: Tier | null;                 // v2
  catatan: string | null;                 // v2
}

export interface Norma {
  id: string;
  norma: string;
  judul: string | null;
  jenis: string;
  otoritatif: boolean;
  berlaku_sejak: string | null;
  dicabut_oleh: string | null;
  dibatalkan_oleh: string | null;
  mengganti: string[];
  disusun_dari: string[];
  alasan: string | null;
  peralihan: string | null;
  sumber_dokumen: string | null;
  status: 'berlaku' | 'dicabut' | 'dibatalkan';
  berkas: string | null;
  berlaku_sampai: string | null;          // v2
  disusun_pada: string | null;            // v2
  disusun_oleh: 'mesin' | 'manusia' | null; // v2
  berlaku_untuk_tanggal: string | null;   // v2
  isi: string | null;                     // v2
  catatan: string | null;                 // v2
}

/** Norma berlaku pada tanggal t (bitemporal, satu klausa — v2). */
export function normaBerlakuPada(n: Pick<Norma, 'berlaku_sejak' | 'berlaku_sampai' | 'status'>, t: string): boolean {
  if (n.status === 'dibatalkan') return false;
  if (!n.berlaku_sejak || n.berlaku_sejak > t) return false;
  return n.berlaku_sampai === null || t < n.berlaku_sampai;
}
