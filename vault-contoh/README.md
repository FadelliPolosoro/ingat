# Contoh vault

Satu vault untuk semua proyek; `lingkup` ada di frontmatter tiap catatan (KEPUTUSAN.md).
Vault ini adalah repo git privat milik pemilik; VPS melakukan `pull` (K7). `ingat` membaca
folder ini dan membangun indeks SQLite yang bisa dibuang kapan saja.

```
pelajaran/            aturan yang sudah disetujui manusia (status: aturan / dipersempit)
pelajaran/_usulan/    keluaran job konsolidasi (status: usulan) — menunggu tinjauan; juga tanya-<tgl>.md (pertanyaan mesin)
pelajaran/_usulan/selesai/  berkas tanya yang sudah dijawab, dengan laporan penerapan
pelajaran/_tier-s/    (K30) pelajaran tier_maks:S — DI-GITIGNORE, tak pernah di-push. Taruh pelajaran turunan tier S di sini, bukan di pelajaran/.
prosedur/             indeks prosedur (tahu-cara); langkah bisa menunjuk skrip/hook/skill
prosedur/_usulan/     draf prosedur dari pola sukses berulang
prosedur/_tier-s/     (K30) prosedur tier_maks:S — DI-GITIGNORE, tak pernah di-push.
norma/                satu berkas per versi peraturan (frontmatter 6.3); konsolidasi = otoritatif: false
episode-dingin/       pointer ke episode yang didinginkan (bukan isi); isi tetap di SQLite/penyimpanan dingin
```

`ingat` hanya MENULIS ke `*/_usulan/` — kecuali saat menerapkan JAWABANMU (`ingat jawab`), yang menyunting berkas di `pelajaran/` atas namamu. Memindahkan berkas keluar dari `_usulan/` = persetujuan manusia
(usulan → aturan). Menambahkan `veto_manusia: 2026-09-06 alasan` = ditarik.
