// SPDX-License-Identifier: Apache-2.0
const SITUS = ['chatgpt.com', 'chat.openai.com', 'claude.ai', 'gemini.google.com', 'chat.deepseek.com', 'www.kimi.com', 'kimi.moonshot.cn', 'www.perplexity.ai', 'perplexity.ai'];

async function muat() {
  const d = await chrome.storage.sync.get(['host', 'token', 'lingkup', 'aktif', 'autoMulai', 'selektor']);
  document.getElementById('host').value = d.host || '';
  document.getElementById('token').value = d.token || '';
  document.getElementById('lingkup').value = d.lingkup || 'peran:asisten-ai';
  document.getElementById('aktif').checked = d.aktif !== false;
  document.getElementById('autoMulai').checked = d.autoMulai !== false;

  let bawaan = {};
  try { bawaan = await (await fetch(chrome.runtime.getURL('selectors-default.json'))).json(); } catch (e) {}
  const selektor = { ...bawaan, ...(d.selektor || {}) };

  const wadah = document.getElementById('daftarSitus');
  wadah.innerHTML = '';
  for (const host of SITUS) {
    const cfg = selektor[host] || {};
    const div = document.createElement('div');
    div.className = 'situs';
    const tangkapOk = cfg.user && cfg.assistant;
    const suntikOk = !!cfg.compose;
    const status = `${tangkapOk ? '<span class="ok">✓ tangkap</span>' : '<span class="warn">tangkap: belum</span>'} · ${suntikOk ? '<span class="ok">✓ suntik</span>' : '<span class="warn">suntik: belum</span>'} <span style="color:#999">(${cfg.verifikasi || '—'})</span>`;
    div.innerHTML = `
      <b style="min-width:170px">${host}</b>
      ${status}
      <code title="${(cfg.user || '').replace(/"/g, '&quot;')}">user: ${cfg.user || '(kosong)'}</code>
      <code title="${(cfg.assistant || '').replace(/"/g, '&quot;')}">ai: ${cfg.assistant || '(kosong)'}</code>
      <code title="${(cfg.compose || '').replace(/"/g, '&quot;')}">ketik: ${cfg.compose || '(kosong)'}</code>
      <button data-host="${host}" data-peran="user">Pilih balon pengguna</button>
      <button data-host="${host}" data-peran="assistant">Pilih balon AI</button>
      <button data-host="${host}" data-peran="compose">Pilih kotak ketik</button>
    `;
    wadah.appendChild(div);
  }
  wadah.querySelectorAll('button').forEach((b) => b.addEventListener('click', async () => {
    const tabs = await chrome.tabs.query({ url: `*://${b.dataset.host}/*`, active: true, currentWindow: true });
    const tab = tabs[0] || (await chrome.tabs.query({ url: `*://${b.dataset.host}/*` }))[0];
    if (!tab) { alert(`Buka tab ${b.dataset.host} dulu, lalu coba lagi.`); return; }
    await chrome.tabs.update(tab.id, { active: true });
    await chrome.tabs.sendMessage(tab.id, { jenis: 'mulai_pilih_elemen', peran: b.dataset.peran });
    const label = { user: 'BALON PESANMU', assistant: 'BALON JAWABAN AI', compose: 'KOTAK KETIK (tempat kamu mengetik)' }[b.dataset.peran];
    alert(`Di tab ${b.dataset.host}: klik ${label} sekarang.`);
  }));
}

document.getElementById('simpan').addEventListener('click', async () => {
  await chrome.storage.sync.set({
    host: document.getElementById('host').value.trim(),
    token: document.getElementById('token').value.trim(),
    lingkup: document.getElementById('lingkup').value.trim() || 'peran:asisten-ai',
    aktif: document.getElementById('aktif').checked,
    autoMulai: document.getElementById('autoMulai').checked,
  });
  document.getElementById('statusSimpan').textContent = 'Tersimpan.';
  setTimeout(() => (document.getElementById('statusSimpan').textContent = ''), 2000);
});

function lolosHtml(teks) {
  const d = document.createElement('div');
  d.textContent = String(teks == null ? '' : teks);
  return d.innerHTML;
}

async function segarkanDiagnostik() {
  const d = await chrome.storage.local.get(['antrean', 'jumlah', 'terakhir', 'galatTerakhir', 'pilihTerakhir', 'peringatanTerakhir']);
  const el = document.getElementById('diagnostik');
  const t = (ms) => (ms ? new Date(ms).toLocaleString('id-ID') : '—');
  const p = d.peringatanTerakhir;
  el.innerHTML = `
    ${p ? `<div style="margin-bottom:6px;padding:8px;border-radius:6px;background:#fdecea;color:#7a1f1f">
      <b>⚠ Jalur utama pernah gagal</b> (${lolosHtml(p.host)}, kode <code>${lolosHtml(p.kode)}</code>, ${t(p.waktu)})<br>
      ${lolosHtml(p.pesan)}
    </div>` : ''}
    Episode terkirim (sejak dipasang): <b>${d.jumlah || 0}</b> · terakhir: ${t(d.terakhir)}<br>
    Antrean tertunda (server tidak terjangkau): <b>${(d.antrean || []).length}</b><br>
    ${d.galatTerakhir ? `Galat tangkap terakhir (${lolosHtml(d.galatTerakhir.host)}): ${lolosHtml(d.galatTerakhir.pesan)} — ${t(d.galatTerakhir.waktu)}<br>` : ''}
    ${d.pilihTerakhir ? `Selektor terakhir dipilih: ${lolosHtml(d.pilihTerakhir.host)} / ${lolosHtml(d.pilihTerakhir.peran)} → contoh teks: "${lolosHtml(d.pilihTerakhir.contoh)}"` : ''}
  `;
}
document.getElementById('segarkan').addEventListener('click', segarkanDiagnostik);
chrome.storage.onChanged.addListener(() => { muat(); segarkanDiagnostik(); });
muat();
segarkanDiagnostik();
