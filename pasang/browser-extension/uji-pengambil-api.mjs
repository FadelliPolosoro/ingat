// SPDX-License-Identifier: Apache-2.0
// Uji tanpa browser untuk pengambil-api.js — dijalankan dari akar repo:
//   node pasang/browser-extension/uji-pengambil-api.mjs
//
// Kenapa bukan unittest Python seperti modul lain: berkas yang diuji adalah content script browser.
// Yang diuji di sini murni logika yang bisa salah diam-diam — penguraian jawaban API dan pemetaan
// kode galat ke kalimat Indonesia — dengan document/location/fetch dipalsukan lewat vm.

import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const BERKAS = path.join(path.dirname(fileURLToPath(import.meta.url)), 'pengambil-api.js');
const KODE = fs.readFileSync(BERKAS, 'utf8');

let gagal = 0;
let lulus = 0;

// Pesan ke-i, atau objek kosong — supaya satu penguraian yang meleset melaporkan SEMUA periksaan
// yang gagal, bukan menjatuhkan skripnya di periksaan pertama yang mengindeks pesan yang tak ada.
function pesanKe(h, i) {
  return (h && h.ok && h.pesan[i]) || {};
}

function periksa(nama, syarat, catatan) {
  if (syarat) { lulus += 1; return; }
  gagal += 1;
  console.error(`GAGAL: ${nama}${catatan ? ` — ${catatan}` : ''}`);
}

// Membangun dunia palsu: satu pemanggilan = satu konteks bersih.
function pasangDunia({ pathname, cookie = '', jawaban = {} }) {
  const dipanggil = [];
  const gudang = new Map();
  const konteks = {
    window: {},
    document: { cookie },
    location: { pathname },
    sessionStorage: {
      getItem: (k) => (gudang.has(k) ? gudang.get(k) : null),
      setItem: (k, v) => gudang.set(k, String(v)),
    },
    fetch: async (url) => {
      dipanggil.push(url);
      const j = typeof jawaban === 'function' ? jawaban(url) : jawaban[url] || jawaban._bawaan;
      if (!j) return { ok: false, status: 404, json: async () => ({}) };
      return { ok: j.status === undefined || (j.status >= 200 && j.status < 300), status: j.status || 200, json: async () => j.data };
    },
    AbortController,
    setTimeout,
    clearTimeout,
    console,
  };
  vm.createContext(konteks);
  vm.runInContext(KODE, konteks);
  return { ambil: konteks.window.ingatPengambil, dipanggil, gudang };
}

const ID = '01234567-89ab-cdef-0123-456789abcdef';
const ALAMAT_CLAUDE =
  `/api/organizations/org-1/chat_conversations/${ID}` +
  '?tree=true&rendering_mode=messages&render_all_tools=true';

const PERCAKAPAN_CLAUDE = {
  name: 'Uji memori',
  chat_messages: [
    { sender: 'human', created_at: '2026-09-18T03:04:05Z', content: [{ type: 'text', text: 'Halo Claude' }] },
    {
      sender: 'assistant',
      created_at: '2026-09-18T03:04:30Z',
      content: [
        { type: 'thinking', thinking: 'ini tidak boleh ikut' },
        { type: 'tool_use', name: 'bash' },
        { type: 'text', text: 'Halo Tuan Muda' },
        { type: 'tool_result', content: 'keluaran panjang yang tidak boleh ikut' },
      ],
    },
    { sender: 'human', created_at: '2026-09-18T03:05:00Z', text: 'pakai field text lama' },
  ],
};

// 1. Jalur bahagia Claude: org dari cookie, percakapan terurai jadi tiga pesan.
{
  const { ambil, dipanggil } = pasangDunia({
    pathname: `/chat/${ID}`,
    cookie: 'intercom=x; lastActiveOrg=org-1; other=y',
    jawaban: { [ALAMAT_CLAUDE]: { data: PERCAKAPAN_CLAUDE } },
  });
  const h = await ambil.ambil('claude.ai');
  periksa('claude: punyaJalurAPI', ambil.punyaJalurAPI('claude.ai'));
  periksa('claude: wajibLewatAPI', ambil.wajibLewatAPI('claude.ai'));
  periksa('claude: berhasil', h.ok, JSON.stringify(h));
  periksa('claude: alamat endpoint benar', dipanggil[0] === ALAMAT_CLAUDE, dipanggil[0]);
  periksa('claude: tiga pesan', h.ok && h.pesan.length === 3, h.ok && String(h.pesan.length));
  periksa('claude: peran pertama user', pesanKe(h, 0).peran === 'user');
  periksa('claude: peran kedua assistant', pesanKe(h, 1).peran === 'assistant');
  periksa('claude: teks alat ikut', (pesanKe(h, 1).teks || '').includes('[memakai alat: bash]'));
  periksa('claude: thinking dibuang', h.ok && !(pesanKe(h, 1).teks || '').includes('tidak boleh ikut'));
  periksa('claude: tool_result dibuang', h.ok && !(pesanKe(h, 1).teks || '').includes('keluaran panjang'));
  periksa('claude: field text lama terbaca', pesanKe(h, 2).teks === 'pakai field text lama');
  periksa('claude: judul terbaca', h.ok && h.judul === 'Uji memori');
}

// 2. Cookie hilang -> jatuh ke /api/organizations, bukan langsung menyerah.
{
  const { ambil, dipanggil } = pasangDunia({
    pathname: `/chat/${ID}`,
    cookie: 'tanpa-org=1',
    jawaban: {
      '/api/organizations': { data: [{ uuid: 'org-1' }] },
      [ALAMAT_CLAUDE]: { data: PERCAKAPAN_CLAUDE },
    },
  });
  const h = await ambil.ambil('claude.ai');
  periksa('claude: cadangan /api/organizations dipanggil', dipanggil[0] === '/api/organizations', dipanggil[0]);
  periksa('claude: tetap berhasil tanpa cookie', h.ok, JSON.stringify(h));
}

// 3. Belum login (401) -> kode belum_login + kalimat Indonesia yang menyebut cara cadangan.
{
  const { ambil } = pasangDunia({
    pathname: `/chat/${ID}`,
    cookie: 'lastActiveOrg=org-1',
    jawaban: { [ALAMAT_CLAUDE]: { status: 401, data: {} } },
  });
  const h = await ambil.ambil('claude.ai');
  periksa('claude 401: kode belum_login', h.kode === 'belum_login', h.kode);
  periksa('claude 401: pesan berbahasa Indonesia', /belum login/i.test(h.pesan), h.pesan);
  periksa('claude 401: pesan menyebut cara cadangan', /cara cadangan/i.test(h.pesan), h.pesan);
  periksa('claude 401: pesan tidak kosong (bukan gagal diam-diam)', h.pesan.length > 60);
}

// 4. Format berubah -> format_asing, bukan mengarang pesan kosong.
{
  const { ambil } = pasangDunia({
    pathname: `/chat/${ID}`,
    cookie: 'lastActiveOrg=org-1',
    jawaban: { [ALAMAT_CLAUDE]: { data: { name: 'x', messages: [] } } },
  });
  const h = await ambil.ambil('claude.ai');
  periksa('claude: format asing terdeteksi', h.kode === 'format_asing', h.kode);
  periksa('claude: format asing memberi pesan', /format API internalnya kemungkinan berubah/.test(h.pesan), h.pesan);
}

// 5. Halaman non-percakapan -> bukan_percakapan, TANPA pesan (tidak boleh menakut-nakuti).
{
  const { ambil, dipanggil } = pasangDunia({ pathname: '/recents', cookie: 'lastActiveOrg=org-1' });
  const h = await ambil.ambil('claude.ai');
  periksa('claude: /recents bukan percakapan', h.kode === 'bukan_percakapan', h.kode);
  periksa('claude: /recents tidak memanggil apa-apa', dipanggil.length === 0);
  periksa('claude: /recents tanpa pesan peringatan', h.pesan === '');
}

// 6. Perplexity: endpoint ada dan bentuknya dikenali.
{
  const alamat = '/rest/thread/apa-itu-ingat-abc?with_schematized_response=true';
  const { ambil } = pasangDunia({
    pathname: '/search/apa-itu-ingat-abc',
    jawaban: {
      [alamat]: {
        data: [
          { query_str: 'apa itu ingat', text: JSON.stringify({ answer: 'sistem memori pribadi' }), created_datetime: '2026-09-18T01:00:00Z' },
          { query_str: 'lanjutkan', blocks: [{ markdown_block: { answer: 'jawaban kedua' } }] },
        ],
      },
    },
  });
  const h = await ambil.ambil('www.perplexity.ai');
  periksa('perplexity: berhasil', h.ok, JSON.stringify(h));
  periksa('perplexity: empat pesan', h.ok && h.pesan.length === 4, h.ok && String(h.pesan.length));
  periksa('perplexity: jawaban dari JSON ber-string', pesanKe(h, 1).teks === 'sistem memori pribadi');
  periksa('perplexity: jawaban dari markdown_block', pesanKe(h, 3).teks === 'jawaban kedua');
  periksa('perplexity: tidak wajib lewat API', !ambil.wajibLewatAPI('www.perplexity.ai'));
}

// 7. Perplexity: endpoint tidak ada -> DIAM, turun ke DOM, dan tidak diprobe lagi.
{
  const { ambil, dipanggil, gudang } = pasangDunia({ pathname: '/search/tidak-ada-xyz' });
  const h1 = await ambil.ambil('www.perplexity.ai');
  periksa('perplexity 404: bukan_percakapan', h1.kode === 'bukan_percakapan', h1.kode);
  periksa('perplexity 404: tanpa peringatan', h1.pesan === '', h1.pesan);
  periksa('perplexity 404: hasil probe diingat', gudang.get('ingat_probe_pplx_tidak-ada-xyz') === 'tidak');
  const h2 = await ambil.ambil('www.perplexity.ai');
  periksa('perplexity 404: tidak diprobe dua kali', dipanggil.length === 1, String(dipanggil.length));
  periksa('perplexity 404: hasil kedua konsisten', h2.kode === 'bukan_percakapan');
}

// 8. Situs tanpa jalur API sama sekali.
{
  const { ambil } = pasangDunia({ pathname: '/c/1' });
  periksa('chatgpt: tidak punya jalur API', !ambil.punyaJalurAPI('chatgpt.com'));
  const h = await ambil.ambil('chatgpt.com');
  periksa('chatgpt: ambil() aman dipanggil', h.kode === 'bukan_percakapan' && h.pesan === '');
}

console.log(`${lulus} periksaan lulus, ${gagal} gagal`);
process.exit(gagal ? 1 : 0);
