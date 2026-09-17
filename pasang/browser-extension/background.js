// SPDX-License-Identifier: Apache-2.0
// Relay ke server ingat lokal (endpoint /episode yang sudah ada — lihat ingat/api.py).
// Kegagalan jaringan disimpan ke antrean (chrome.storage.local) dan dicoba lagi tiap alarm.

const NAMA_ALARM = 'ingat-coba-ulang';
const UMUR_PENANDA_MS = 90 * 24 * 60 * 60 * 1000; // penanda percakapan lama dibuang setelah 90 hari
const UMUR_PERINGATAN_MS = 30 * 60 * 1000;        // peringatan dianggap basi setelah 30 menit

async function konfig() {
  // 'aktif' ikut dibaca karena cekRelevansi menghormatinya — tanpa ini nilainya selalu undefined
  // dan pengingat relevansi tetap jalan walau penangkapan sudah dimatikan di Opsi.
  return chrome.storage.sync.get(['token', 'host', 'lingkup', 'aktif', 'selektorLingkupPerSitus']);
}

async function kirimKeServer(payload) {
  const k = await konfig();
  if (!k.token || !k.host) throw new Error('token/host belum dikonfigurasi (buka opsi ekstensi)');
  const { _host, ...bersih } = payload;
  const lingkupSitus = (k.selektorLingkupPerSitus || {})[_host];
  const badan = { ...bersih, lingkup: lingkupSitus || k.lingkup || 'peran:asisten-ai' };
  const res = await fetch(`${k.host.replace(/\/$/, '')}/episode`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${k.token}` },
    body: JSON.stringify(badan),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${(await res.text()).slice(0, 200)}`);
  return res.json();
}

async function antre(payload) {
  const { antrean = [] } = await chrome.storage.local.get('antrean');
  antrean.push({ payload, dicoba: 0, waktu: Date.now() });
  await chrome.storage.local.set({ antrean: antrean.slice(-200) }); // batas antrean supaya tidak tumbuh tanpa henti
}

async function prosesAntrean() {
  const { antrean = [] } = await chrome.storage.local.get('antrean');
  if (!antrean.length) return;
  const sisa = [];
  for (const item of antrean) {
    try {
      await kirimKeServer(item.payload);
      await tandaiSukses();
    } catch (e) {
      item.dicoba += 1;
      if (item.dicoba < 20) sisa.push(item); // buang setelah 20x gagal (± beberapa jam) — hindari antrean abadi
    }
  }
  await chrome.storage.local.set({ antrean: sisa });
  chrome.action.setBadgeText({ text: sisa.length ? String(sisa.length) : '' });
}

async function tandaiSukses() {
  const { jumlah = 0 } = await chrome.storage.local.get('jumlah');
  await chrome.storage.local.set({ jumlah: jumlah + 1, terakhir: Date.now() });
}

// Penanda 'api_<host><path>' dibuat satu per percakapan yang pernah ditangkap lewat jalur API.
// Kecil, tapi tanpa pembersihan ia bertambah selamanya.
async function pangkasPenanda() {
  const semua = await chrome.storage.local.get(null);
  const batas = Date.now() - UMUR_PENANDA_MS;
  const buang = Object.keys(semua).filter(
    (k) => k.startsWith('api_') && semua[k] && typeof semua[k].t === 'number' && semua[k].t < batas,
  );
  if (buang.length) await chrome.storage.local.remove(buang);
}

// ---- peringatan "jalur utama gagal" ---------------------------------------
// Kegagalan paling berbahaya bukan yang berteriak, tapi yang diam: Tuan Muda mengira percakapannya
// tersimpan padahal tidak. Karena itu peringatan dipajang di lencana ikon + Opsi → Diagnostik + popup.
async function simpanPeringatan(msg, tabId) {
  await chrome.storage.local.set({
    peringatanTerakhir: { kode: msg.kode, pesan: msg.pesan, host: msg.host, waktu: Date.now() },
  });
  if (tabId != null) {
    chrome.action.setBadgeText({ text: '!', tabId });
    chrome.action.setBadgeBackgroundColor({ color: '#c0392b', tabId });
  }
}

async function adaPeringatanSegar() {
  const { peringatanTerakhir } = await chrome.storage.local.get('peringatanTerakhir');
  return !!(peringatanTerakhir && Date.now() - peringatanTerakhir.waktu < UMUR_PERINGATAN_MS);
}

chrome.runtime.onMessage.addListener((msg, sender, balas) => {
  if (msg.jenis === 'auto_mulai' && sender.tab) {
    // Percakapan baru terdeteksi kosong (content.js sudah memverifikasi) -> suntik /startup sekali.
    // Pakai suntikKe yang sama dengan tombol manual: satu jalur kode, satu jaminan tidak-pernah-submit.
    suntikKe(sender.tab, '').catch(() => {}); // gagal diam-diam — ini kenyamanan, bukan aksi yang diminta eksplisit
    return;
  }
  if (msg.jenis === 'minta_suntik') {
    mintaSuntik().then((r) => balas({ ok: true, ...r })).catch((e) => balas({ ok: false, pesan: String(e.message || e) }));
    return true; // balasan async
  }
  if (msg.jenis === 'minta_suntik_lagi') {
    mintaSuntikLagi().then((r) => balas({ ok: true, ...r })).catch((e) => balas({ ok: false, pesan: String(e.message || e) }));
    return true;
  }
  if (msg.jenis === 'cek_relevansi' && sender.tab) {
    cekRelevansi(msg.teks, sender.tab.id);
    return; // fire-and-forget, tidak perlu balasan
  }
  if (msg.jenis === 'bersihkan_lencana' && sender.tab) {
    const tabId = sender.tab.id;
    adaPeringatanSegar().then((ada) => { if (!ada) chrome.action.setBadgeText({ text: '', tabId }); });
    chrome.storage.local.remove(`hint_${tabId}`);
    return;
  }
  if (msg.jenis === 'peringatan_tangkap') {
    simpanPeringatan(msg, sender.tab ? sender.tab.id : null);
    return;
  }
  if (msg.jenis === 'peringatan_beres') {
    // Jalur utama pulih. Lencana dibersihkan, tapi catatan diagnostik sengaja DIBIARKAN supaya
    // Tuan Muda masih bisa melihat bahwa tadi sempat jatuh ke cara cadangan.
    if (sender.tab) chrome.action.setBadgeText({ text: '', tabId: sender.tab.id });
    return;
  }
  if (msg.jenis === 'kirim_episode') {
    kirimKeServer(msg.payload).then(tandaiSukses).catch(() => antre(msg.payload));
  } else if (msg.jenis === 'galat_tangkap') {
    chrome.storage.local.set({ galatTerakhir: { pesan: msg.pesan, host: msg.host, waktu: Date.now() } });
  } else if (msg.jenis === 'elemen_terpilih') {
    (async () => {
      const { selektor: peta = {} } = await chrome.storage.sync.get('selektor');
      peta[msg.host] = { ...(peta[msg.host] || {}), [msg.peran]: msg.selektor, verifikasi: 'dipilih manual' };
      await chrome.storage.sync.set({ selektor: peta });
      chrome.storage.local.set({ pilihTerakhir: { host: msg.host, peran: msg.peran, selektor: msg.selektor, contoh: msg.contoh } });
      const tabs = await chrome.tabs.query({ url: `*://${msg.host}/*` });
      for (const t of tabs) chrome.tabs.sendMessage(t.id, { jenis: 'konfig_berubah' }).catch(() => {});
    })();
  }
  return true;
});

chrome.alarms.create(NAMA_ALARM, { periodInMinutes: 2 });
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name !== NAMA_ALARM) return;
  prosesAntrean();
  pangkasPenanda().catch(() => {});
});


// ---- Suntik memori (Sesi 8 Sep 2026, + cicilan token) ---------------------
// Alur: baca draf di kotak ketik tab aktif -> tarik memori relevan dari server ingat lokal
// (query = draf bila ada, else konteks awal lewat /startup) -> tulis ke kotak ketik SEBAGAI TEKS.
// Tidak pernah menekan kirim/submit — pengguna yang memutuskan kapan mengirim.
//
// "Cicilan" (menyicil anggaran token, bukan cuma sekali tarik semua): /ingat sudah membatasi hasil
// pada anggaran_token (Bab 8 spek). Klik pertama pakai anggaran default server; kalau responsnya masih
// menyisakan `pointer` (item relevan yang terpotong anggaran), tombol "Suntik lagi" di popup menaikkan
// anggaran_token dan menarik LEBIH BANYAK — item yang sudah disisipkan tidak diulang (dilacak per tab).
// Ini bukan model belajar baru; murni memakai mekanisme anggaran yang sudah ada di server, dieskalasi
// bertahap atas permintaan eksplisit pengguna (bukan otomatis, supaya kotak ketik tidak tiba-tiba penuh).
const TANGGA_ANGGARAN = [null, 1200, 2400, 4000]; // null = biarkan server pakai default (anggaran_tarik)
const suntikState = new Map(); // tabId -> { idTerkirim: Set, langkah: 0, query, lingkup, jenis }

async function ambilDariServer(tab, k, teksTerakhir) {
  const host = k.host.replace(/\/$/, '');
  const lingkupSitus = (k.selektorLingkupPerSitus || {})[new URL(tab.url).hostname];
  const lingkup = lingkupSitus || k.lingkup || 'peran:asisten-ai';
  const st = suntikState.get(tab.id) || { idTerkirim: new Set(), langkah: 0 };
  const anggaran = TANGGA_ANGGARAN[Math.min(st.langkah, TANGGA_ANGGARAN.length - 1)];

  let hasil, jenis;
  if (teksTerakhir && teksTerakhir.trim()) {
    const badan = { query: teksTerakhir.trim().slice(0, 500), lingkup };
    if (anggaran) badan.anggaran_token = anggaran;
    const res = await fetch(`${host}/ingat`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${k.token}` }, body: JSON.stringify(badan) });
    if (!res.ok) throw new Error(`HTTP ${res.status} dari /ingat`);
    hasil = await res.json(); jenis = 'ingat';
  } else {
    const res = await fetch(`${host}/startup`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${k.token}` }, body: JSON.stringify({ lingkup }) });
    if (!res.ok) throw new Error(`HTTP ${res.status} dari /startup`);
    hasil = await res.json(); jenis = 'startup';
  }
  st.langkah += 1;
  st.query = teksTerakhir; st.lingkup = lingkup; st.jenis = jenis;
  suntikState.set(tab.id, st);
  return { hasil, jenis, st, host, lingkup };
}

function rangkaiBlok(hasil, jenis, idTerkirim) {
  let baris = [];
  if (jenis === 'startup') {
    if (idTerkirim.has('__startup__')) return { blok: null, sisaPointer: 0 };
    if ((hasil.peta || []).length <= 1 && !(hasil.aturan || []).length) return { blok: null, sisaPointer: 0 };
    idTerkirim.add('__startup__');
    baris = ['[ingat — konteks memori]', ...(hasil.peta || []), ...(hasil.aturan || []), '[/ingat]'];
  } else {
    const baruSaja = (hasil.item || []).filter((i) => !idTerkirim.has(i.id));
    if (!baruSaja.length) return { blok: null, sisaPointer: (hasil.pointer || []).length };
    baruSaja.forEach((i) => idTerkirim.add(i.id));
    baris = ['[ingat — memori relevan]', ...baruSaja.map((i) => `- (${i.jenis}) ${i.teks || i.ringkas || ''}`), '[/ingat]'];
  }
  const MAKS = 4000;
  const teks = baris.join('\n');
  return { blok: teks.length > MAKS ? teks.slice(0, MAKS) + '\n…' : teks, sisaPointer: (hasil.pointer || []).length };
}

async function suntikKe(tab, teksTerakhir) {
  const k = await konfig();
  if (!k.token || !k.host) throw new Error('Token/host belum dikonfigurasi — buka Opsi ekstensi dulu.');
  const { hasil, jenis, st } = await ambilDariServer(tab, k, teksTerakhir);
  const { blok, sisaPointer } = rangkaiBlok(hasil, jenis, st.idTerkirim);
  st.sisaPointer = sisaPointer;
  suntikState.set(tab.id, st);
  if (!blok) return { jumlah: 0, jenis, sisaPointer };
  const r = await chrome.tabs.sendMessage(tab.id, { jenis: 'sisipkan_teks', teks: blok });
  if (!r || !r.ok) throw new Error((r && r.pesan) || 'Gagal menyisipkan ke kotak ketik (compose belum dikonfigurasi?).');
  const jumlah = jenis === 'startup' ? (hasil.aturan || []).length : (hasil.item || []).length;
  return { jumlah, jenis, sisaPointer, token: hasil.token };
}

async function mintaSuntik() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error('Tidak ada tab aktif.');
  suntikState.delete(tab.id); // klik "Suntik memori" (bukan "lagi") selalu mulai cicilan baru
  const draf = await chrome.tabs.sendMessage(tab.id, { jenis: 'baca_draft' }).catch(() => ({ ok: false }));
  return suntikKe(tab, draf && draf.ok ? draf.teks : '');
}

async function mintaSuntikLagi() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error('Tidak ada tab aktif.');
  const st = suntikState.get(tab.id);
  if (!st) throw new Error('Belum ada sesi Suntik memori di tab ini — klik "Suntik memori" dulu.');
  return suntikKe(tab, st.query);
}

// ---- pengingat relevansi: badge ikon, TIDAK menyisipkan apa pun otomatis -----
const AMBANG_BADGE = 0.30; // sama dengan SKOR_PERINGATAN di gateway.py — "cukup relevan untuk diberi tahu"

async function cekRelevansi(teks, tabId) {
  try {
    const k = await konfig();
    if (!k.token || !k.host || k.aktif === false) return;
    const host = k.host.replace(/\/$/, '');
    const res = await fetch(`${host}/ingat`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${k.token}` },
      body: JSON.stringify({ query: teks, lingkup: k.lingkup || 'peran:asisten-ai', anggaran_token: 50 }),
    });
    if (!res.ok) return;
    const hasil = await res.json();
    const skorTertinggi = Math.max(0, ...(hasil.item || []).map((i) => i.skor || 0));
    if (skorTertinggi >= AMBANG_BADGE) {
      if (await adaPeringatanSegar()) return; // peringatan gagal-tangkap lebih penting daripada titik hijau
      chrome.action.setBadgeText({ text: '●', tabId });
      chrome.action.setBadgeBackgroundColor({ color: '#0a7a2f', tabId });
      await chrome.storage.local.set({ [`hint_${tabId}`]: { skor: skorTertinggi, waktu: Date.now() } });
    } else {
      if (!(await adaPeringatanSegar())) chrome.action.setBadgeText({ text: '', tabId });
      await chrome.storage.local.remove(`hint_${tabId}`);
    }
  } catch (e) { /* pengingat tidak boleh pernah mengganggu; diam saja bila gagal */ }
}

chrome.tabs.onRemoved.addListener((tabId) => { suntikState.delete(tabId); chrome.storage.local.remove(`hint_${tabId}`); });
