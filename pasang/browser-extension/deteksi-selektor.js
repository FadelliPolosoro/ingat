// SPDX-License-Identifier: Apache-2.0
// Alat bantu MENEMUKAN selektor untuk ekstensi ingat — dijalankan MANUAL di Console (F12).
//
// Kenapa ada: Opsi ekstensi mengisi selektor lewat "Pilih elemen" (picker) yang mengutamakan
// data-* lalu jatuh ke rantai nth-of-type yang rapuh. Situs seperti Gemini/Perplexity wajib login,
// jadi selektornya hanya bisa dipastikan DI HALAMANMU SENDIRI. Skrip ini mengukur (bukan menebak):
// ia menguji daftar kandidat terhadap DOM nyata yang sedang terbuka, lalu merekomendasikan yang sehat.
//
// CARA PAKAI:
//   1. Buka situsnya (login), buka SATU percakapan berisi >=1 pesanmu + >=1 jawaban AI.
//   2. F12 -> tab Console -> tempel SELURUH isi berkas ini -> Enter.
//   3. Baca tabel hasil + rekomendasi. Lalu salah satu:
//      (a) pakai picker Opsi ekstensi dan klik elemen yang teksnya cocok, ATAU
//      (b) salin perintah chrome.storage yang dicetak, tempel di Console HALAMAN OPSI EKSTENSI
//          (chrome-extension://<id>/options.html) — bukan di console situs ini — lalu Enter.
//
// Skrip ini hanya MEMBACA DOM. Tidak mengirim apa pun, tidak menyentuh percakapan.

(() => {
  const host = location.host.replace(/^www\./, "") === "perplexity.ai" ? "www.perplexity.ai" : location.host;

  // Kandidat per situs, diurutkan dari yang paling tahan-redesain (custom element / data-*) ke umum.
  const KANDIDAT = {
    "gemini.google.com": {
      user: ["user-query .query-text", "user-query", '[data-test-id="user-query"]'],
      assistant: ["model-response .markdown", "model-response message-content", "model-response", ".model-response-text"],
      compose: ["rich-textarea .ql-editor", '.ql-editor[contenteditable="true"]', '[contenteditable="true"][role="textbox"]'],
    },
    "www.perplexity.ai": {
      user: ['[data-testid="query-title"]', ".group\\/query", "h1.group\\/query", '[data-testid="thread-title"]'],
      assistant: ['[data-testid="answer"]', ".prose", '[id^="markdown-content-"]', ".prose.text-pretty"],
      compose: ['[contenteditable="true"][role="textbox"]', "textarea[placeholder]", "textarea"],
    },
    "chatgpt.com": {
      user: ['[data-message-author-role="user"]'],
      assistant: ['[data-message-author-role="assistant"]'],
      compose: ["#prompt-textarea", '[contenteditable="true"]#prompt-textarea'],
    },
    "claude.ai": {
      user: ['[data-testid="user-message"]', ".font-user-message"],
      assistant: [".font-claude-message", ".font-claude-response", "[data-is-streaming]"],
      compose: ["div.ProseMirror", '[contenteditable="true"]'],
    },
  };
  KANDIDAT["chat.openai.com"] = KANDIDAT["chatgpt.com"];
  KANDIDAT["perplexity.ai"] = KANDIDAT["www.perplexity.ai"];

  const set = KANDIDAT[host];
  if (!set) {
    console.warn(`[ingat] Tidak ada daftar kandidat untuk ${host}. Pakai picker Opsi ekstensi.`);
    return;
  }

  const teks = (el) => (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
  const uji = (sel) => {
    try {
      const n = document.querySelectorAll(sel);
      const isi = [...n].map(teks).filter(Boolean);
      return { cocok: n.length, berteks: isi.length, contoh: (isi[0] || "").slice(0, 55) };
    } catch (e) {
      return { cocok: "ERR", berteks: 0, contoh: e.message.slice(0, 40) };
    }
  };
  // Sehat = ada yang cocok, ada teks, dan jumlahnya masuk akal (bukan menyapu seluruh halaman).
  const sehat = (r, compose) =>
    r.cocok !== "ERR" && r.cocok >= 1 && (compose ? true : r.berteks >= 1 && r.cocok <= 60);

  const rekom = {};
  const baris = [];
  for (const peran of ["user", "assistant", "compose"]) {
    for (const sel of set[peran]) {
      const r = uji(sel);
      const ok = sehat(r, peran === "compose");
      baris.push({ peran, selektor: sel, cocok: r.cocok, "berteks": r.berteks, "✓": ok ? "REKOMENDASI" : "", contoh: r.contoh });
      if (ok && !rekom[peran]) rekom[peran] = sel;
    }
  }

  console.log(`%c[ingat] Deteksi selektor untuk ${host}`, "font-weight:bold;font-size:13px");
  console.table(baris);
  const kurang = ["user", "assistant", "compose"].filter((p) => !rekom[p]);
  if (kurang.length) {
    console.warn(`[ingat] Belum ketemu untuk: ${kurang.join(", ")}. `+
      `Pastikan percakapan punya pesanmu + jawaban AI di layar, atau pakai picker Opsi lalu klik elemennya.`);
  }
  console.log("[ingat] Rekomendasi:", rekom);

  // Perintah untuk mengisi langsung (jalankan di Console HALAMAN OPSI EKSTENSI, bukan di sini):
  const cfg = { user: rekom.user || "", assistant: rekom.assistant || "", compose: rekom.compose || "",
    verifikasi: "diisi via deteksi-selektor " + new Date().toISOString().slice(0, 10) };
  const perintah =
    `chrome.storage.sync.get('selektor').then(d=>{const s=d.selektor||{};` +
    `s['${host}']=${JSON.stringify(cfg)};` +
    `chrome.storage.sync.set({selektor:s},()=>console.log('[ingat] selektor ${host} tersimpan'));});`;
  console.log("%c[ingat] Salin baris di bawah, tempel di Console HALAMAN OPSI EKSTENSI:", "font-weight:bold");
  console.log(perintah);
  return rekom;
})();
