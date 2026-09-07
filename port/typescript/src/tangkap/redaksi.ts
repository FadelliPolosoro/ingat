// SPDX-License-Identifier: Apache-2.0
// Redaksi kredensial SEBELUM tulis (K10). Nilai diganti [REDAKSI:<jenis>]; nilainya tidak pernah disimpan.
// Tambah pola = tambah uji di uji/redaksi.test.ts.

export interface PolaRedaksi {
  jenis: string;
  pola: RegExp;      // harus punya flag g
  ganti?: (m: RegExpExecArray) => string; // default: seluruh match diganti
}

export const POLA_KREDENSIAL: readonly PolaRedaksi[] = [
  { jenis: 'kunci-privat', pola: /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g },
  { jenis: 'kunci-anthropic', pola: /\bsk-ant-[A-Za-z0-9_-]{20,}/g },
  { jenis: 'kunci-openai', pola: /\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}/g },
  { jenis: 'token-github', pola: /\bgh[pousr]_[A-Za-z0-9]{30,}\b/g },
  { jenis: 'kunci-aws', pola: /\bAKIA[0-9A-Z]{16}\b/g },
  { jenis: 'token-slack', pola: /\bxox[baprs]-[A-Za-z0-9-]{10,}/g },
  { jenis: 'jwt', pola: /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g },
  {
    jenis: 'bearer',
    pola: /\bBearer\s+(?!\[REDAKSI:)[A-Za-z0-9._~+/=-]{16,}/g,
  },
  {
    jenis: 'pasangan-rahasia',
    // api_key = "...", password: ..., KUNCI_ENKRIPSI=... — wajib ada pemisah : atau = ; nilai ≥ 8 karakter tanpa spasi.
    // Tanpa pemisah (bare whitespace) sengaja tidak ditangkap: "token dikembalikan" adalah prosa, bukan rahasia.
    pola: /\b(api[_-]?key|secret[_-]?key|secret|passw(?:or)?d|token|kunci_enkripsi|kunci_csrf)\b(\s*[:=]\s*)(['"]?)(?!\[REDAKSI:)([^\s'"]{8,})\3/gi,
    ganti: (m) => `${m[1]}${m[2]}${m[3]}[REDAKSI:pasangan-rahasia]${m[3]}`,
  },
];

export interface HasilRedaksi {
  teks: string;
  jenis: string[];   // jenis yang terpicu, unik, urut ketemu
  jumlah: number;
}

export function redaksi(teks: string, daftar: readonly PolaRedaksi[] = POLA_KREDENSIAL): HasilRedaksi {
  let hasil = teks;
  const jenis: string[] = [];
  let jumlah = 0;
  for (const p of daftar) {
    const re = new RegExp(p.pola.source, p.pola.flags.includes('g') ? p.pola.flags : p.pola.flags + 'g');
    let kena = false;
    hasil = hasil.replace(re, (...args) => {
      kena = true;
      jumlah++;
      if (p.ganti) {
        const m = args.slice(0, -2) as unknown as RegExpExecArray;
        return p.ganti(m);
      }
      return `[REDAKSI:${p.jenis}]`;
    });
    if (kena) jenis.push(p.jenis);
  }
  return { teks: hasil, jenis, jumlah };
}
