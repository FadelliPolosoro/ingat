// SPDX-License-Identifier: Apache-2.0
let tabAktifId = null;

async function segarkan() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  tabAktifId = tab ? tab.id : null;
  const host = tab && tab.url ? new URL(tab.url).hostname : '';
  const { selektor = {}, aktif, token } = await chrome.storage.sync.get(['selektor', 'aktif', 'token']);
  const { jumlah = 0, antrean = [] } = await chrome.storage.local.get(['jumlah', 'antrean']);
  const cfg = selektor[host];
  document.getElementById('situsStatus').textContent = !host ? '—' : cfg && cfg.user && cfg.assistant ? 'terkonfigurasi' : 'belum diatur';
  document.getElementById('jumlah').textContent = jumlah;
  document.getElementById('tertunda').textContent = antrean.length;
  document.getElementById('titik').style.background = !token ? '#999' : aktif === false ? '#c00' : '#0a7a2f';

  if (tabAktifId != null) {
    const kunci = `hint_${tabAktifId}`;
    const d = await chrome.storage.local.get(kunci);
    const hint = d[kunci];
    const segar = hint && Date.now() - hint.waktu < 120_000; // hint kedaluwarsa 2 menit
    document.getElementById('hintRelevansi').style.display = segar ? 'block' : 'none';
  }
}
document.getElementById('opsi').addEventListener('click', () => chrome.runtime.openOptionsPage());

function terapkanHasilSuntik(r) {
  const status = document.getElementById('suntikStatus');
  const lagi = document.getElementById('suntikLagi');
  if (r.jumlah > 0) {
    status.textContent = `Disuntik: ${r.jumlah} item (${r.jenis}). Periksa lalu kirim sendiri.`;
  } else {
    status.textContent = r.sisaPointer > 0 ? 'Sudah disisipkan sebelumnya; tidak ada item baru.' : 'Tidak ada memori relevan untuk disuntik.';
  }
  lagi.style.display = r.sisaPointer > 0 ? 'block' : 'none';
  if (r.sisaPointer > 0) lagi.textContent = `➕ Suntik lagi (+${r.sisaPointer} tersedia)`;
}

document.getElementById('suntik').addEventListener('click', async (ev) => {
  const tombol = ev.currentTarget;
  const status = document.getElementById('suntikStatus');
  tombol.disabled = true;
  status.textContent = 'Menarik memori…';
  try {
    const r = await chrome.runtime.sendMessage({ jenis: 'minta_suntik' });
    if (!r || !r.ok) throw new Error((r && r.pesan) || 'Gagal.');
    terapkanHasilSuntik(r);
  } catch (e) {
    status.textContent = `Gagal: ${e.message || e}`;
  } finally {
    tombol.disabled = false;
    segarkan();
  }
});

document.getElementById('suntikLagi').addEventListener('click', async (ev) => {
  const tombol = ev.currentTarget;
  const status = document.getElementById('suntikStatus');
  tombol.disabled = true;
  status.textContent = 'Menarik cicilan berikutnya…';
  try {
    const r = await chrome.runtime.sendMessage({ jenis: 'minta_suntik_lagi' });
    if (!r || !r.ok) throw new Error((r && r.pesan) || 'Gagal.');
    terapkanHasilSuntik(r);
  } catch (e) {
    status.textContent = `Gagal: ${e.message || e}`;
  } finally {
    tombol.disabled = false;
  }
});
segarkan();
