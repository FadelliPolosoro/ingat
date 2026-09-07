// SPDX-License-Identifier: Apache-2.0
// Pembaca/penulis frontmatter subset-YAML `ingat` (KEPUTUSAN.md):
//   - blok diapit `---` di awal berkas
//   - satu kunci per baris: `kunci: nilai`
//   - nilai: JSON flow (`["a"]`, `{"x":1}`, `"teks"`, 12, true, null) atau string polos
// Sengaja tanpa pustaka YAML supaya nol dependensi; Obsidian merender bentuk ini normal.

export interface HasilFrontmatter {
  data: Record<string, unknown>;
  badan: string;
}

export class FrontmatterRusak extends Error {
  constructor(pesan: string) {
    super(pesan);
    this.name = 'FrontmatterRusak';
  }
}

function parseNilai(mentah: string): unknown {
  const s = mentah.trim();
  if (s === '') return '';
  const awal = s[0];
  if (awal === '[' || awal === '{' || awal === '"') {
    try {
      return JSON.parse(s);
    } catch (e) {
      throw new FrontmatterRusak(`nilai JSON flow tidak valid: ${s}`);
    }
  }
  if (s === 'null' || s === '~') return null;
  if (s === 'true') return true;
  if (s === 'false') return false;
  if (/^-?\d+(\.\d+)?$/.test(s)) return Number(s);
  return s; // string polos (termasuk tanggal ISO — dibiarkan string)
}

export function bacaFrontmatter(teks: string): HasilFrontmatter {
  if (!teks.startsWith('---\n') && !teks.startsWith('---\r\n')) {
    return { data: {}, badan: teks };
  }
  const baris = teks.split(/\r?\n/);
  let akhir = -1;
  for (let i = 1; i < baris.length; i++) {
    if (baris[i] === '---') {
      akhir = i;
      break;
    }
  }
  if (akhir === -1) throw new FrontmatterRusak('penutup --- tidak ditemukan');
  const data: Record<string, unknown> = {};
  for (let i = 1; i < akhir; i++) {
    const b = baris[i]!;
    if (b.trim() === '' || b.trim().startsWith('#')) continue;
    const titik = b.indexOf(':');
    if (titik <= 0) throw new FrontmatterRusak(`baris ${i + 1} bukan 'kunci: nilai': ${b}`);
    const kunci = b.slice(0, titik).trim();
    if (!/^[a-z0-9_]+$/.test(kunci)) throw new FrontmatterRusak(`kunci tidak valid: ${kunci}`);
    data[kunci] = parseNilai(b.slice(titik + 1));
  }
  return { data, badan: baris.slice(akhir + 1).join('\n') };
}

function tulisNilai(v: unknown): string {
  if (v === null || v === undefined) return 'null';
  if (typeof v === 'string') {
    // string polos aman bila tidak diawali karakter JSON dan tidak mengandung baris baru
    if (/^[\[\{"]/.test(v) || /\r|\n/.test(v) || v === 'true' || v === 'false' || v === 'null' || /^-?\d/.test(v)) {
      return JSON.stringify(v);
    }
    return v;
  }
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  return JSON.stringify(v);
}

export function tulisFrontmatter(data: Record<string, unknown>, badan: string): string {
  const baris = Object.entries(data).map(([k, v]) => `${k}: ${tulisNilai(v)}`);
  return `---\n${baris.join('\n')}\n---\n${badan}`;
}
