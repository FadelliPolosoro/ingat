// SPDX-License-Identifier: Apache-2.0
// Pencarian vektor brute-force (pola sqlite_exact). Murni. Index ANN = fase 2, di balik antarmuka ini.

export interface KandidatVektor {
  id: string;
  vektor: Float32Array; // sudah dinormalisasi L2
}

export interface Hit {
  id: string;
  skor: number; // cosine similarity, lebih tinggi = lebih dekat
}

export function normalisasiL2(v: Float32Array): Float32Array {
  let s = 0;
  for (let i = 0; i < v.length; i++) s += v[i]! * v[i]!;
  const n = Math.sqrt(s);
  if (n === 0) return v;
  const out = new Float32Array(v.length);
  for (let i = 0; i < v.length; i++) out[i] = v[i]! / n;
  return out;
}

export function dot(a: Float32Array, b: Float32Array): number {
  if (a.length !== b.length) throw new Error(`dimensi tidak sama: ${a.length} vs ${b.length}`);
  let s = 0;
  for (let i = 0; i < a.length; i++) s += a[i]! * b[i]!;
  return s;
}

/**
 * Cari k terdekat. `allowlist` (opsional) membatasi kandidat — padanan filter `lingkup`/versi;
 * kandidat di luar allowlist tidak diskor sama sekali.
 */
export function cariTerdekat(
  query: Float32Array,
  kandidat: Iterable<KandidatVektor>,
  k: number,
  allowlist?: ReadonlySet<string>,
): Hit[] {
  const hasil: Hit[] = [];
  for (const c of kandidat) {
    if (allowlist && !allowlist.has(c.id)) continue;
    hasil.push({ id: c.id, skor: dot(query, c.vektor) });
  }
  hasil.sort((x, y) => y.skor - x.skor);
  return hasil.slice(0, k);
}

/** Konversi BLOB float32 little-endian ↔ Float32Array (format kolom vektor.vektor). */
export function keBlob(v: Float32Array): Uint8Array {
  return new Uint8Array(v.buffer, v.byteOffset, v.byteLength);
}
export function dariBlob(b: Uint8Array, dimensi: number): Float32Array {
  if (b.byteLength !== dimensi * 4) throw new Error(`blob ${b.byteLength} byte ≠ ${dimensi}×4`);
  const salinan = new Uint8Array(b); // pastikan offset 0 & aligned
  return new Float32Array(salinan.buffer, 0, dimensi);
}
