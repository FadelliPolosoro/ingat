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
  let modeCadangan = false;       // true = jalur API gagal, kita sedang mengandalkan pembacaan DOM

  // Nilai selektor boleh berisi beberapa kandidat dipisah '||'. Yang dipakai adalah kandidat PERTAMA
  // yang benar-benar mencocokkan sesuatu — bukan gabungan koma, supaya kandidat yang salah tidak ikut
  // menyeret elemen asing masuk ke episode saat kandidat yang benar sudah ketemu.
  function daftarKandidat(nilai) {
    return String(nilai || '').split('||').map((s) => s.trim()).filter(Boolean);
  }

  function pilihSemua(nilai) {
    for (const s of daftarKandidat(nilai)) {
      try {
        const n = document.querySelectorAll(s);
        if (n.length) return n;
      } catch (e) { /* kandidat tidak valid — coba berikutnya */ }
    }
    return [];
  }

  function pilihSatu(nilai) {
    for (const s of daftarKandidat(nilai)) {
      try {
        const el = document.querySelector(s);
        if (el) return el;
      } catch (e) { /* kandidat tidak valid — coba berikutnya */ }
    }
    return null;
  }

  function punyaJalurAPI() {
    return !!(window.ingatPengambil && window.ingatPengambil.punyaJalurAPI(host));
  }

  function kunciSesi() {
    // Sesi = situs + path percakapan; path biasanya berubah per percakapan (mis. /c/<id>)
    return `${host}:${location.pathname}`;
  }

  function reset() {
    // Percakapan sudah berganti saat fungsi ini jalan, jadi sisa buffer HARUS dikirim lewat jalur DOM:
    // memanggil API di sini akan menarik percakapan yang baru, bukan yang barusan ditinggalkan.
    if (buffer.length) kirimDariDom(ambilBuffer(), 'percakapan berganti', sesiId || kunciSesi());
    sesiId = kunciSesi();
    buffer = [];
    modeCadangan = false;
    setTimeout(cekMulaiOtomatis, 900); // beri DOM waktu merender sebelum diperiksa
    setTimeout(periksaKesehatanSelektor, 15_000);
  }

  // ---- suntik otomatis SEKALI di percakapan baru yang benar-benar kosong (8 Sep 2026) ----
  // Bedanya dari 'Suntik memori' manual: ini hanya menembak ke kotak ketik yang KOSONG saat
  // percakapan baru terdeteksi (0 pesan pengguna, 0 pesan AI) — tidak pernah ke draf yang sedang
  // kamu tulis, tidak pernah ke percakapan lama yang sedang kamu buka-baca. Jawaban atas
  // "apakah otomatis di mana pun saya mulai" — ini bagian yang membuatnya YA untuk platform
  // tanpa MCP, sejajar dengan hook SessionStart di Claude Code. Bisa dimatikan di Opsi.
  function percakapanBenarBenarKosong() {
    if (!sel.user || !sel.assistant) return false; // tidak bisa memastikan tanpa selektor pesan
    return pilihSemua(sel.user).length === 0 && pilihSemua(sel.assistant).length === 0;
  }

  async function cekMulaiOtomatis() {
    try {
      const { autoMulai } = await chrome.storage.sync.get('autoMulai');
      if (autoMulai === false) return; // default AKTIF; pengguna bisa matikan di Opsi
      if (!aktif || !sel.compose) return;
      const kunci = 'ingat_auto_' + host + location.pathname;
      if (sessionStorage.getItem(kunci)) return; // sudah pernah, sekali per percakapan per tab
      const el = pilihSatu(sel.compose);
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
    if (!aktif) return;
    if (punyaJalurAPI()) jadwalkanIdle(); // jalur API tidak butuh selektor; cukup tahu "ada aktivitas"
    if (!sel.user || !sel.assistant) return;
    try {
      const usr = pilihSemua(sel.user);
      const ast = pilihSemua(sel.assistant);
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

  function ambilBuffer() {
    // Dikosongkan SEBELUM menunggu jaringan, supaya pesan yang masuk selama penantian tidak ikut
    // terkirim dua kali di flush berikutnya.
    const isi = buffer;
    buffer = [];
    clearTimeout(timerIdle);
    return isi;
  }

  function kirimEpisode(pesan, alasan, sesi, instrumenTambahan, idTetap) {
    if (!aktif || !pesan.length) return;
    const langkah = pesan.slice(-MAKS_TURN).map((b) => `${b.peran === 'user' ? '🧑' : '🤖'} ${b.teks.slice(0, 300)}`);
    const promptPertama = (pesan.find((b) => b.peran === 'user') || {}).teks || '';
    const rendah = promptPertama.trim().toLowerCase();
    const koreksi = PREFIKS_KOREKSI.some((p) => rendah.startsWith(p));
    const isi = `[percakapan ${host}${location.pathname}] ${pesan.length} pesan (${alasan})\n\n` +
      pesan.map((b) => `${String(b.waktu).slice(11, 19)} ${b.peran}: ${b.teks}`).join('\n\n');
    const payload = {
      _host: host,
      isi,
      sumber: `browser:${host}`,
      tier: 'I',
      jenis_kejadian: koreksi ? 'koreksi' : 'sukses',
      ringkas: (koreksi ? promptPertama.replace(/^\/?koreksi:?\s*/i, '') : `Percakapan ${host}: ${pesan.length} pesan`).slice(0, 200),
      instrumen: [`browser:${host}`, ...(instrumenTambahan || [])],
      langkah,
      sesi: sesi || sesiId || kunciSesi(),
    };
    if (idTetap) payload.id = idTetap; // id deterministik -> server meng-upsert, bukan menumpuk salinan
    chrome.runtime.sendMessage({ jenis: 'kirim_episode', payload }).catch(() => {});
  }

  function kirimDariDom(pesan, alasan, sesi) {
    kirimEpisode(pesan, alasan, sesi, punyaJalurAPI() ? ['jalur:dom-cadangan'] : ['jalur:dom']);
  }

  // Jalur API mengembalikan SELURUH percakapan tiap kali dipanggil, sementara satu percakapan bisa
  // di-flush berkali-kali (idle, tab disembunyikan, dibuka lagi besok). Penanda ini menyimpan berapa
  // pesan yang sudah pernah dikirim supaya yang terkirim hanya selisihnya. Disimpan di
  // chrome.storage.local, BUKAN sessionStorage: sessionStorage mati bersama tabnya, sehingga membuka
  // ulang percakapan lama besok akan mengirim ulang seluruh percakapan itu.
  function kunciPenanda() {
    return 'api_' + host + location.pathname;
  }

  async function bacaPenanda() {
    try {
      const kunci = kunciPenanda();
      const d = await chrome.storage.local.get(kunci);
      return d[kunci] && typeof d[kunci].n === 'number' ? d[kunci].n : 0;
    } catch (e) { return 0; }
  }

  async function kirimDariAPI(hasil, alasan, sesi) {
    let sudah = await bacaPenanda();
    if (sudah > hasil.pesan.length) sudah = 0; // percakapan dipotong/dijawab ulang dari cabang lain
    const baru = hasil.pesan.slice(sudah);
    try { await chrome.storage.local.set({ [kunciPenanda()]: { n: hasil.pesan.length, t: Date.now() } }); } catch (e) {}
    // id deterministik: kalau penanda sempat hilang dan potongan yang sama terkirim lagi, server
    // meng-upsert episode yang sama alih-alih menumpuk salinan.
    const id = `browser:${host}${location.pathname}#${sudah}-${hasil.pesan.length}`;
    kirimEpisode(baru, `${alasan} · jalur API`, sesi, ['jalur:api-internal'], id);
  }

  async function flush(alasan) {
    // Penangkapan dimatikan di Opsi = benar-benar mati, termasuk jalur API. flush dipanggil juga dari
    // visibilitychange yang tidak lewat pindaiTurunBaru, jadi penjagaannya harus ada di sini.
    if (!aktif) { ambilBuffer(); return; }
    const sesi = sesiId || kunciSesi();
    const antre = ambilBuffer();
    if (punyaJalurAPI()) {
      const hasil = await window.ingatPengambil.ambil(host);
      if (hasil && hasil.ok) {
        // Hanya bersihkan lencana kalau memang tadi sempat jatuh — supaya titik hijau "ada memori
        // relevan" tidak ikut terhapus setiap kali jalur API berjalan normal.
        if (modeCadangan) { modeCadangan = false; bersihkanPeringatan(); }
        await kirimDariAPI(hasil, alasan, sesi);
        return; // buffer DOM sengaja dibuang: isinya sudah termuat (lebih lengkap) di hasil API
      }
      if (!hasil || hasil.kode !== 'bukan_percakapan') {
        modeCadangan = true;
        if (window.ingatPengambil.wajibLewatAPI(host)) laporkanPeringatan(hasil);
      }
    }
    kirimDariDom(antre, alasan, sesi);
  }

  // ---- jangan pernah gagal diam-diam ----------------------------------------
  // Kegagalan paling berbahaya di sini bukan error yang kelihatan, tapi episode yang tidak pernah
  // tersimpan sementara Tuan Muda mengira memorinya aman. Setiap kali jalur utama jatuh, ekstensi
  // memberi tahu di tiga tempat: lencana ikon, popup, dan satu bisikan kecil di halaman.
  function laporkanPeringatan(hasil) {
    const kode = (hasil && hasil.kode) || 'jaringan';
    const pesan = (hasil && hasil.pesan) || 'Jalur utama ingat gagal; memakai cara cadangan.';
    chrome.runtime.sendMessage({ jenis: 'peringatan_tangkap', kode, host, pesan }).catch(() => {});
    const kunci = `ingat_warn_${host}${location.pathname}:${kode}`;
    try {
      if (sessionStorage.getItem(kunci)) return; // satu bisikan per jenis masalah per percakapan
      sessionStorage.setItem(kunci, '1');
    } catch (e) { /* sessionStorage diblokir — biar muncul lagi, lebih baik berisik daripada diam */ }
    bisikkan(pesan);
  }

  function bersihkanPeringatan() {
    chrome.runtime.sendMessage({ jenis: 'peringatan_beres', host }).catch(() => {});
  }

  function bisikkan(teks) {
    try {
      const kotak = document.createElement('div');
      kotak.style.cssText =
        'position:fixed;right:16px;bottom:16px;z-index:2147483646;max-width:340px;padding:12px 14px;' +
        'border-radius:10px;background:#7a1f1f;color:#fff;font:13px/1.45 -apple-system,system-ui,sans-serif;' +
        'box-shadow:0 6px 24px rgba(0,0,0,.28)';
      const judul = document.createElement('b');
      judul.textContent = 'ingat — perhatian';
      const isi = document.createElement('div');
      isi.style.cssText = 'margin-top:4px';
      isi.textContent = teks;
      const tutup = document.createElement('button');
      tutup.textContent = 'Tutup';
      tutup.style.cssText =
        'margin-top:8px;padding:4px 10px;border-radius:6px;border:1px solid rgba(255,255,255,.5);' +
        'background:transparent;color:#fff;cursor:pointer';
      tutup.addEventListener('click', () => kotak.remove());
      kotak.append(judul, isi, tutup);
      document.body.appendChild(kotak);
      setTimeout(() => kotak.remove(), 20_000);
    } catch (e) { /* halaman aneh — lencana ikon dan popup tetap membawa pesannya */ }
  }

  // Penjaga untuk situs yang memang bergantung pada DOM (Perplexity dkk.): selektor sudah diisi tapi
  // tidak mencocokkan apa pun di halaman yang jelas berisi percakapan = selektornya mati.
  function periksaKesehatanSelektor() {
    try {
      if (!aktif || !sel.user || !sel.assistant) return;
      if (punyaJalurAPI() && !modeCadangan) return; // jalur API yang menanggung, selektor tidak dipakai
      if (pilihSemua(sel.user).length || pilihSemua(sel.assistant).length) return;
      const panjang = (document.body.innerText || '').length;
      if (panjang < 2000) return; // halaman kosong/daftar — wajar tidak ada balon pesan
      laporkanPeringatan({
        kode: 'selektor_mati',
        pesan: `Selektor untuk ${host} tidak lagi mengenali balon pesan mana pun, padahal halaman ini berisi ` +
          'percakapan. Percakapan di situs ini kemungkinan TIDAK tersimpan. Buka Opsi ekstensi → pilih ulang ' +
          '"Pilih balon pengguna" dan "Pilih balon AI".',
      });
    } catch (e) { /* pemeriksaan kesehatan tidak boleh ikut merusak apa pun */ }
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
        const el = sel.compose ? pilihSatu(sel.compose) : null;
        balas({ ok: true, teks: el ? bacaNilaiElemen(el) : '', adaKotak: !!el });
      } catch (e) { balas({ ok: false, pesan: String(e) }); }
      return true; // balasan async
    }
    if (msg.jenis === 'sisipkan_teks') {
      try {
        const el = sel.compose ? pilihSatu(sel.compose) : null;
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
    const el = sel.compose ? pilihSatu(sel.compose) : null;
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

    // beforeunload tidak bisa menunggu jaringan: panggilan API pasti dibatalkan saat halaman mati.
    // Jadi di sini SELALU jalur DOM — apa yang sempat terbaca lebih baik daripada tidak sama sekali;
    // selisihnya akan dilengkapi jalur API saat percakapan yang sama dibuka lagi.
    window.addEventListener('beforeunload', () => kirimDariDom(ambilBuffer(), 'tab ditutup', sesiId || kunciSesi()));
    document.addEventListener('visibilitychange', () => { if (document.hidden) flush('tab disembunyikan'); });
  }).catch(() => {});
})();
