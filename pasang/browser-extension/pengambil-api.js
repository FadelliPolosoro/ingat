// SPDX-License-Identifier: Apache-2.0
// Pengambil isi percakapan lewat API internal situs — jalur UTAMA, dicoba content.js sebelum jalur DOM.
//
// Kenapa bukan selektor CSS: (1) selektor patah setiap kali situsnya di-redesain; (2) DOM situs modern
// hanya merender sebagian percakapan panjang (virtualisasi), jadi episode yang tersimpan bisa bolong
// tanpa kelihatan. Endpoint internal memberi percakapan utuh dengan bentuk data yang jauh lebih stabil.
// Pola ini mengikuti exporter sumber-terbuka Claude (github.com/agarwalvishal/claude-chat-exporter).
//
// Modul ini hanya MEMBACA, memakai sesi login yang sudah ada di browser — sama seperti tab yang kamu
// buka sendiri. Tidak menulis ke halaman, tidak mengirim apa pun keluar situs (yang mengirim ke server
// ingat tetap background.js, lewat kontrak /episode yang sama).
//
// Content script satu ekstensi berbagi satu "isolated world" per frame, jadi content.js membacanya
// lewat window.ingatPengambil — bukan lewat import (tidak tersedia di content script klasik).

(() => {
  'use strict';

  const BATAS_MS = 12_000; // jangan menggantung selamanya kalau jaringan/endpoint diam

  const PESAN = {
    bukan_percakapan: '',
    belum_login: 'Kamu belum login di situs ini (atau sesi loginnya sudah kedaluwarsa), jadi ingat tidak bisa menarik percakapan lewat jalur utama.',
    http: 'Situs menolak permintaan jalur utama ingat — kemungkinan alamat API internalnya berubah.',
    format_asing: 'Jawaban situs tidak lagi berbentuk yang dikenali ingat — format API internalnya kemungkinan berubah.',
    tanpa_organisasi: 'ingat tidak menemukan id organisasi Claude.ai (cookie lastActiveOrg tidak ada). Coba muat ulang halaman setelah login.',
    jaringan: 'Jalur utama (API internal situs) tidak bisa dihubungi.',
  };
  const EKOR =
    ' Sementara ini ingat memakai cara cadangan: membaca tampilan layar. Cara cadangan bisa melewatkan ' +
    'bagian percakapan yang panjang, jadi buka Opsi ekstensi → Diagnostik kalau episodenya terasa bolong.';

  function kalimatGalat(kode, detail) {
    if (!kode || kode === 'bukan_percakapan') return '';
    const inti = PESAN[kode] || PESAN.jaringan;
    return (detail ? `${inti} (${detail})` : inti) + EKOR;
  }

  function gagal(kode, detail) {
    return { ok: false, kode, detail: detail || '', pesan: kalimatGalat(kode, detail) };
  }

  async function ambilJson(url) {
    const kendali = new AbortController();
    const jam = setTimeout(() => kendali.abort(), BATAS_MS);
    let res;
    try {
      res = await fetch(url, { credentials: 'include', headers: { Accept: 'application/json' }, signal: kendali.signal });
    } catch (e) {
      return gagal('jaringan', String((e && e.message) || e).slice(0, 80));
    } finally {
      clearTimeout(jam);
    }
    if (res.status === 401 || res.status === 403) return gagal('belum_login');
    if (res.status === 404) return gagal('http', 'HTTP 404');
    if (!res.ok) return gagal('http', `HTTP ${res.status}`);
    try {
      return { ok: true, data: await res.json() };
    } catch (e) {
      return gagal('format_asing', 'jawaban bukan JSON');
    }
  }

  function bacaCookie(nama) {
    for (const bagian of document.cookie.split(';')) {
      const i = bagian.indexOf('=');
      if (i < 0) continue;
      if (decodeURIComponent(bagian.slice(0, i).trim()) === nama) {
        return decodeURIComponent(bagian.slice(i + 1).trim()).replace(/^"|"$/g, '');
      }
    }
    return '';
  }

  function bersihkan(teks) {
    return String(teks == null ? '' : teks).replace(/\r/g, '').replace(/\n{3,}/g, '\n\n').trim();
  }

  // ---- Claude.ai ------------------------------------------------------------
  // GET /api/organizations/{org}/chat_conversations/{id}?tree=true&rendering_mode=messages&render_all_tools=true
  // org diambil dari cookie lastActiveOrg; id dari URL halaman.

  function idPercakapanClaude() {
    const m = /\/chat\/([0-9a-fA-F-]{16,64})/.exec(location.pathname);
    return m ? m[1] : '';
  }

  async function idOrganisasiClaude() {
    const dariCookie = bacaCookie('lastActiveOrg');
    if (dariCookie) return { ok: true, id: dariCookie };
    // Cadangan bila cookie hilang/berganti nama: daftar organisasi punya endpoint sendiri.
    const r = await ambilJson('/api/organizations');
    if (!r.ok) return r;
    const daftar = Array.isArray(r.data) ? r.data : [];
    const org = daftar.find((o) => o && typeof o.uuid === 'string' && o.uuid);
    return org ? { ok: true, id: org.uuid } : gagal('tanpa_organisasi');
  }

  function teksBlokClaude(blok) {
    if (!blok || typeof blok !== 'object') return '';
    if (blok.type === 'text' && typeof blok.text === 'string') return blok.text;
    if (blok.type === 'tool_use') return `[memakai alat: ${blok.name || '?'}]`;
    // 'thinking' dan 'tool_result' sengaja dilewat: bukan isi percakapan, dan tool_result bisa
    // puluhan ribu karakter yang akan menenggelamkan episode.
    return '';
  }

  function normalkanPesanClaude(p) {
    const peran = p && p.sender === 'assistant' ? 'assistant' : 'user';
    let teks = '';
    if (Array.isArray(p && p.content)) teks = p.content.map(teksBlokClaude).filter(Boolean).join('\n\n');
    if (!teks && typeof (p && p.text) === 'string') teks = p.text;
    return { peran, teks: bersihkan(teks), waktu: (p && p.created_at) || new Date().toISOString() };
  }

  async function ambilClaude() {
    const id = idPercakapanClaude();
    if (!id) return gagal('bukan_percakapan'); // halaman beranda/daftar — memang tidak ada yang ditarik
    const org = await idOrganisasiClaude();
    if (!org.ok) return org;
    const alamat =
      `/api/organizations/${encodeURIComponent(org.id)}/chat_conversations/${encodeURIComponent(id)}` +
      '?tree=true&rendering_mode=messages&render_all_tools=true';
    const r = await ambilJson(alamat);
    if (!r.ok) return r;
    const mentah = r.data && Array.isArray(r.data.chat_messages) ? r.data.chat_messages : null;
    if (!mentah) return gagal('format_asing', 'chat_messages tidak ada');
    const pesan = mentah.map(normalkanPesanClaude).filter((p) => p.teks);
    if (!pesan.length) return gagal('format_asing', 'tidak ada pesan berteks');
    return { ok: true, sumber: 'api', judul: bersihkan(r.data.name || ''), pesan };
  }

  // ---- Perplexity -----------------------------------------------------------
  // Tidak ada endpoint publik yang bisa dipastikan seperti Claude. Yang ada: REST internal
  // /rest/thread/<slug> yang dipakai halamannya sendiri — BELUM DIVERIFIKASI di akun Tuan Muda,
  // jadi diperlakukan sebagai PROBE: dicoba sekali per percakapan, hasilnya diingat di sessionStorage.
  // Kalau tidak ada / bentuknya tak dikenali, kita DIAM-DIAM turun ke jalur DOM — tanpa peringatan,
  // karena untuk Perplexity jalur DOM memang jalur yang sah (selektornya sudah diverifikasi 14 Sep 2026).

  function slugPerplexity() {
    const m = /\/(?:search|page)\/([^/?#]+)/.exec(location.pathname);
    return m ? m[1] : '';
  }

  function teksJawabanPerplexity(entri) {
    if (typeof entri.answer_text === 'string' && entri.answer_text.trim()) return entri.answer_text;
    if (typeof entri.answer === 'string' && entri.answer.trim()) return entri.answer;
    if (typeof entri.text === 'string' && entri.text.trim()) {
      // Bentuk lama: field `text` berisi JSON ber-string dengan kunci "answer" di dalamnya.
      try {
        const dalam = JSON.parse(entri.text);
        if (dalam && typeof dalam.answer === 'string') return dalam.answer;
      } catch (e) { /* bukan JSON — pakai apa adanya */ }
      return entri.text;
    }
    if (Array.isArray(entri.blocks)) {
      const md = entri.blocks
        .map((b) => (b && b.markdown_block && typeof b.markdown_block.answer === 'string' ? b.markdown_block.answer : ''))
        .filter(Boolean)
        .join('\n\n');
      if (md) return md;
    }
    return '';
  }

  async function ambilPerplexity() {
    const slug = slugPerplexity();
    if (!slug) return gagal('bukan_percakapan');
    const kunciProbe = `ingat_probe_pplx_${slug}`;
    try {
      if (sessionStorage.getItem(kunciProbe) === 'tidak') return gagal('bukan_percakapan');
    } catch (e) { /* sessionStorage bisa diblokir; probe ulang tidak berbahaya */ }

    const r = await ambilJson(`/rest/thread/${encodeURIComponent(slug)}?with_schematized_response=true`);
    if (!r.ok) {
      try { sessionStorage.setItem(kunciProbe, 'tidak'); } catch (e) {}
      return gagal('bukan_percakapan'); // turun ke DOM tanpa menakut-nakuti pengguna
    }
    const entri = Array.isArray(r.data) ? r.data : Array.isArray(r.data && r.data.entries) ? r.data.entries : null;
    const pesan = [];
    for (const e of entri || []) {
      if (!e || typeof e !== 'object') continue;
      const tanya = typeof e.query_str === 'string' ? e.query_str : typeof e.query === 'string' ? e.query : '';
      const jawab = teksJawabanPerplexity(e);
      const waktu = e.updated_datetime || e.created_datetime || new Date().toISOString();
      if (tanya.trim()) pesan.push({ peran: 'user', teks: bersihkan(tanya), waktu });
      if (jawab.trim()) pesan.push({ peran: 'assistant', teks: bersihkan(jawab), waktu });
    }
    if (!pesan.length) {
      try { sessionStorage.setItem(kunciProbe, 'tidak'); } catch (e) {}
      return gagal('bukan_percakapan');
    }
    try { sessionStorage.setItem(kunciProbe, 'ada'); } catch (e) {}
    return { ok: true, sumber: 'api', judul: '', pesan };
  }

  // ---- daftar situs ---------------------------------------------------------
  // wajibAPI = kegagalan API di situs ini HARUS diberitahukan ke pengguna (jalur DOM cuma cadangan).
  const SITUS = {
    'claude.ai': { ambil: ambilClaude, wajibAPI: true },
    'www.perplexity.ai': { ambil: ambilPerplexity, wajibAPI: false },
    'perplexity.ai': { ambil: ambilPerplexity, wajibAPI: false },
  };

  window.ingatPengambil = {
    punyaJalurAPI(host) {
      return Object.prototype.hasOwnProperty.call(SITUS, host);
    },
    wajibLewatAPI(host) {
      return !!(SITUS[host] && SITUS[host].wajibAPI);
    },
    async ambil(host) {
      const s = SITUS[host];
      if (!s) return gagal('bukan_percakapan');
      try {
        return await s.ambil();
      } catch (e) {
        return gagal('jaringan', String((e && e.message) || e).slice(0, 80));
      }
    },
    _kalimatGalat: kalimatGalat, // dipakai uji manual di Console
  };
})();
