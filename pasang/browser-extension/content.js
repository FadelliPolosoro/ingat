// SPDX-License-Identifier: Apache-2.0
// Mesin tangkap generik: MutationObserver + selektor per situs (chrome.storage).
// Pola sama dengan hook Claude Code (K11): satu episode per SESI PERCAKAPAN, bukan per pesan —
// supaya tidak membanjiri store dengan episode kecil-kecil (anti-banjir).
//
// TIDAK PERNAH memblokir situs yang sedang kamu pakai: seluruh logika dibungkus try/catch,
// dan kegagalan tangkap tidak pernah menampilkan error ke halaman.

(() => {
  'use strict';

  const IDLE_FLUSH_MS = 90_000;   // tidak ada aktivitas baru 90 detik -> kirim episode
  const DEBOUNCE_MS = 1200;       // tunggu 1.2s setelah mutasi terakhir sebelum menganggap teks "selesai"
  const MAKS_TURN = 60;
  const PREFIKS_KOREKSI = ['/koreksi', 'koreksi:'];

  const host = location.hostname;
  const sudahDiproses = new WeakSet();
  const MAKS_SUNTIK = 4000;
  let buffer = [];               // {peran:'user'|'assistant', teks, waktu}
  let timerIdle = null;
  let timerDebounce = null;
  let sesiId = null;
  let aktif = false;
  let sel = { user: '', assistant: '' };
  let composeEl = null;
  let timerRelevansi = null;
  let terakhirCekRelevansi = 0;

  function kunciSesi() {
    // Sesi = situs + path percakapan; path biasanya berubah per percakapan (mis. /c/<id>)
    return `${host}:${location.pathname}`;
  }

  function reset() {
    if (buffer.length) flush('percakapan berganti');
    sesiId = kunciSesi();
    buffer = [];
    setTimeout(cekMulaiOtomatis, 900); // beri DOM waktu merender sebelum diperiksa
  }

  // ---- suntik otomatis SEKALI di percakapan baru yang benar-benar kosong (8 Sep 2026) ----
  // Bedanya dari 'Suntik memori' manual: ini hanya menembak ke kotak ketik yang KOSONG saat
  // percakapan baru terdeteksi (0 pesan pengguna, 0 pesan AI) — tidak pernah ke draf yang sedang
  // kamu tulis, tidak pernah ke percakapan lama yang sedang kamu buka-baca. Jawaban atas
  // "apakah otomatis di mana pun saya mulai" — ini bagian yang membuatnya YA untuk platform
  // tanpa MCP, sejajar dengan hook SessionStart di Claude Code. Bisa dimatikan di Opsi.
  function percakapanBenarBenarKosong() {
    if (!sel.user || !sel.assistant) return false; // tidak bisa memastikan tanpa selektor pesan
    return document.querySelectorAll(sel.user).length === 0 && document.querySelectorAll(sel.assistant).length === 0;
  }

  async function cekMulaiOtomatis() {
    try {
      const { autoMulai } = await chrome.storage.sync.get('autoMulai');
      if (autoMulai === false) return; // default AKTIF; pengguna bisa matikan di Opsi
      if (!aktif || !sel.compose) return;
      const kunci = 'ingat_auto_' + host + location.pathname;
      if (sessionStorage.getItem(kunci)) return; // sudah pernah, sekali per percakapan per tab
      const el = document.querySelector(sel.compose);
      if (!el || bacaNilaiElemen(el).trim() !== '') return; // hanya kotak yang benar-benar kosong
      if (!percakapanBenarBenarKosong()) return; // hanya percakapan baru, bukan yang sedang dibaca ulang
      sessionStorage.setItem(kunci, '1');
      chrome.runtime.sendMessage({ jenis: 'auto_mulai' }).catch(() => {});
    } catch (e) { /* diam — ini kenyamanan, bukan hal yang boleh mengganggu halaman */ }
  }

  async function muatKonfig() {
    const d = await chrome.storage.sync.get(['token', 'host', 'lingkup', 'aktif', 'selektor']);
    aktif = d.aktif !== false; // default aktif begitu dipasang & dikonfigurasi tokennya
    const peta = d.selektor && d.selektor[host];
    sel = peta && peta.user && peta.assistant ? peta : { user: '', assistant: '' };
    sel.compose = (peta && peta.compose) || '';
    return d;
  }

  function teksBersih(el) {
    return (el.innerText || el.textContent || '').trim().replace(/\n{3,}/g, '\n\n');
  }

  function tandaiTurunan(root, elemen) {
    // Tandai elemen DAN semua turunannya supaya query berikutnya tidak menghitungnya lagi.
    sudahDiproses.add(elemen);
  }

  function pindaiTurunBaru() {
    if (!aktif || !sel.user || !sel.assistant) return;
    try {
      const usr = document.querySelectorAll(sel.user);
      const ast = document.querySelectorAll(sel.assistant);
      let adaBaru = false;
      for (const el of usr) {
        if (sudahDiproses.has(el)) continue;
        tandaiTurunan(document, el);
        const teks = teksBersih(el);
        if (teks) { buffer.push({ peran: 'user', teks, waktu: new Date().toISOString() }); adaBaru = true; }
      }
      for (const el of ast) {
        if (sudahDiproses.has(el)) continue;
        // Tunggu sampai elemen "diam" (streaming selesai) sebelum dianggap final.
        const snapshot = teksBersih(el);
        setTimeout(() => {
          if (sudahDiproses.has(el)) return;
          const akhir = teksBersih(el);
          if (akhir === snapshot && akhir) {
            tandaiTurunan(document, el);
            buffer.push({ peran: 'assistant', teks: akhir, waktu: new Date().toISOString() });
            jadwalkanIdle();
          }
        }, DEBOUNCE_MS);
      }
      if (adaBaru) jadwalkanIdle();
    } catch (e) {
      // Diam-diam gagal — jangan pernah mengganggu halaman yang sedang dipakai.
      chrome.runtime.sendMessage({ jenis: 'galat_tangkap', pesan: String(e), host }).catch(() => {});
    }
  }

  function jadwalkanIdle() {
    clearTimeout(timerIdle);
    timerIdle = setTimeout(() => flush('idle 90 detik'), IDLE_FLUSH_MS);
  }

  function flush(alasan) {
    if (!buffer.length) return;
    const langkah = buffer.slice(-MAKS_TURN).map((b) => `${b.peran === 'user' ? '🧑' : '🤖'} ${b.teks.slice(0, 300)}`);
    const promptPertama = (buffer.find((b) => b.peran === 'user') || {}).teks || '';
    const rendah = promptPertama.trim().toLowerCase();
    const koreksi = PREFIKS_KOREKSI.some((p) => rendah.startsWith(p));
    const isi = `[percakapan ${host}${location.pathname}] ${buffer.length} pesan (${alasan})\n\n` +
      buffer.map((b) => `${b.waktu.slice(11, 19)} ${b.peran}: ${b.teks}`).join('\n\n');
    const payload = {
      _host: host,
      isi,
      sumber: `browser:${host}`,
      tier: 'I',
      jenis_kejadian: koreksi ? 'koreksi' : 'sukses',
      ringkas: (koreksi ? promptPertama.replace(/^\/?koreksi:?\s*/i, '') : `Percakapan ${host}: ${buffer.length} pesan`).slice(0, 200),
      instrumen: [`browser:${host}`],
      langkah,
      sesi: sesiId || kunciSesi(),
    };
    chrome.runtime.sendMessage({ jenis: 'kirim_episode', payload }).catch(() => {});
    buffer = [];
    clearTimeout(timerIdle);
  }

  // ---- suntik memori: baca & tulis ke kotak ketik (Sesi 8 Sep 2026) -------
  // TIDAK PERNAH mengirim/submit apa pun — hanya menyisipkan teks ke elemen kotak ketik.
  // Pengguna sendiri yang menekan kirim, sama seperti kalau ia menempel dari clipboard.
  function bacaNilaiElemen(el) {
    if (el == null) return '';
    if ('value' in el) return el.value || '';
    return (el.innerText || el.textContent || '').trim();
  }

  function tulisKeKotak(el, awalan) {
    const asli = bacaNilaiElemen(el);
    const gabung = asli ? `${awalan}\n\n${asli}` : awalan;
    if ('value' in el) {
      // React/Vue melacak <textarea>/<input> lewat setter native pada prototipe, bukan properti instance —
      // menimpa el.value langsung tidak memicu re-render; setter prototipe + event 'input' yang benar.
      const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
      if (setter) setter.call(el, gabung); else el.value = gabung;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
      // contenteditable (ProseMirror/Lexical dkk.): execCommand sudah deprecated tapi masih paling luas
      // dipahami editor kaya-teks — memicu mutation yang dikenali state internalnya. Fallback manual bila gagal.
      el.focus();
      const ok = document.execCommand && document.execCommand('selectAll', false, null) &&
                 document.execCommand('insertText', false, gabung);
      if (!ok) {
        el.textContent = gabung;
        el.dispatchEvent(new InputEvent('input', { bubbles: true, data: gabung, inputType: 'insertText' }));
      }
    }
    el.focus();
  }

  // ---- pemilih elemen (dipicu dari popup lewat chrome.runtime) --------------
  let modePilih = null; // 'user' | 'assistant' | null
  let overlay = null;

  function selektorDari(elemen) {
    // Utamakan atribut data-* yang khas (lebih tahan redesign daripada nama kelas CSS yang sering diacak).
    let e = elemen;
    for (let i = 0; i < 6 && e && e !== document.body; i++, e = e.parentElement) {
      for (const atr of e.attributes || []) {
        if (/^data-(testid|message|author|role|qa)/i.test(atr.name) && atr.value) {
          return `[${atr.name}='${CSS.escape(atr.value)}']`;
        }
      }
    }
    // Fallback: rantai tag+nth-of-type pendek dari elemen yang diklik.
    const bagian = [];
    e = elemen;
    for (let i = 0; i < 4 && e && e !== document.body; i++, e = e.parentElement) {
      const induk = e.parentElement;
      const sama = induk ? Array.from(induk.children).filter((c) => c.tagName === e.tagName) : [e];
      const idx = sama.indexOf(e) + 1;
      bagian.unshift(`${e.tagName.toLowerCase()}:nth-of-type(${idx})`);
    }
    return bagian.join(' > ');
  }

  function mulaiPilih(peran) {
    modePilih = peran;
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;outline:3px solid #ff4d4f;border-radius:6px;transition:all 60ms;';
      document.body.appendChild(overlay);
    }
    document.addEventListener('mousemove', gerakPilih, true);
    document.addEventListener('click', klikPilih, true);
  }

  function gerakPilih(ev) {
    if (!modePilih) return;
    const r = ev.target.getBoundingClientRect();
    Object.assign(overlay.style, { left: `${r.left}px`, top: `${r.top}px`, width: `${r.width}px`, height: `${r.height}px`, display: 'block' });
  }

  function klikPilih(ev) {
    if (!modePilih) return;
    ev.preventDefault(); ev.stopPropagation();
    const s = selektorDari(ev.target);
    chrome.runtime.sendMessage({ jenis: 'elemen_terpilih', host, peran: modePilih, selektor: s, contoh: teksBersih(ev.target).slice(0, 150) });
    document.removeEventListener('mousemove', gerakPilih, true);
    document.removeEventListener('click', klikPilih, true);
    overlay.style.display = 'none';
    modePilih = null;
  }

  chrome.runtime.onMessage.addListener((msg, _pengirim, balas) => {
    if (msg.jenis === 'mulai_pilih_elemen') { mulaiPilih(msg.peran); return; }
    if (msg.jenis === 'konfig_berubah') { muatKonfig().then(pasangPelacakDraf); return; }
    if (msg.jenis === 'baca_draft') {
      try {
        const el = sel.compose ? document.querySelector(sel.compose) : null;
        balas({ ok: true, teks: el ? bacaNilaiElemen(el) : '', adaKotak: !!el });
      } catch (e) { balas({ ok: false, pesan: String(e) }); }
      return true; // balasan async
    }
    if (msg.jenis === 'sisipkan_teks') {
      try {
        const el = sel.compose ? document.querySelector(sel.compose) : null;
        if (!el) { balas({ ok: false, pesan: 'Kotak ketik belum dikonfigurasi untuk situs ini — pilih dulu di Opsi.' }); return true; }
        tulisKeKotak(el, (msg.teks || '').slice(0, MAKS_SUNTIK));
        balas({ ok: true });
      } catch (e) { balas({ ok: false, pesan: String(e) }); }
      return true;
    }
  });

  // ---- pengingat relevansi (Sesi 8 Sep 2026) --------------------------------
  // TIDAK menyisipkan apa pun sendiri — hanya memberi tahu (badge ikon + popup) bahwa ada
  // memori relevan, supaya kamu tidak perlu mengingat sendiri kapan harus klik Suntik memori.
  // Sinyal kepintarannya BUKAN model belajar baru; ia menumpang skor relevansi (skor_hibrida)
  // yang sama dipakai /ingat — jadi otomatis membaik seiring pelajaran makin matang lewat
  // siklus tanya/jawab (K15), tanpa kode ekstensi ini perlu diubah lagi.
  const JEDA_CEK_MS = 4000;   // jangan cek lebih sering dari ini — hormati beban server

  function pasangPelacakDraf() {
    const el = sel.compose ? document.querySelector(sel.compose) : null;
    if (!el || el === composeEl) return;
    composeEl = el;
    composeEl.addEventListener('input', () => {
      clearTimeout(timerRelevansi);
      timerRelevansi = setTimeout(() => {
        const kini = Date.now();
        if (kini - terakhirCekRelevansi < JEDA_CEK_MS) return;
        terakhirCekRelevansi = kini;
        const teks = bacaNilaiElemen(composeEl).trim();
        if (teks.length < 15) { chrome.runtime.sendMessage({ jenis: 'bersihkan_lencana' }).catch(() => {}); return; }
        chrome.runtime.sendMessage({ jenis: 'cek_relevansi', teks: teks.slice(0, 300) }).catch(() => {});
      }, 1500);
    }, { passive: true });
  }

  // ---- inisialisasi -----------------------------------------------------------
  muatKonfig().then(() => {
    reset();
    pasangPelacakDraf();
    setInterval(pasangPelacakDraf, 3000); // compose box situs SPA sering muncul belakangan / berganti elemen
    const observer = new MutationObserver(() => {
      clearTimeout(timerDebounce);
      timerDebounce = setTimeout(pindaiTurunBaru, 400);
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });

    let path = location.pathname;
    setInterval(() => { if (location.pathname !== path) { path = location.pathname; reset(); } }, 2000);

    window.addEventListener('beforeunload', () => flush('tab ditutup'));
    document.addEventListener('visibilitychange', () => { if (document.hidden) flush('tab disembunyikan'); });
  }).catch(() => {});
})();
