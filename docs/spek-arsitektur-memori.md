# Spesifikasi Arsitektur Memori — Dashboard Cakti

| | |
|---|---|
| **Status** | DRAFT v0.5.5 — K28: prinsip P11 (Bab 2) + empat rem tier S (9.1, `ingat/rem.py`); tier S boleh disintesis model LOKAL saja, gagal-tertutup, hanya jalur konsolidasi, tidak pernah naik status otomatis. 29 uji baru. v0.5.4 — K27: perbaikan efek samping CLI (pasang tidak lagi membuat Store/data). v0.5.3 — K26: verifikasi dua langkah mandiri (TOTP RFC 6238, tanpa Google), pembatas laju khusus, perintah totp-atur. v0.5.2 — K25: Google Auth (OAuth2 stdlib-only, sesi cookie HMAC, allowlist wajib) + instal-vps.sh + panduan Google Cloud Console. v0.5.1 — K24: pembersihan atribusi (CLAUDE.md->AGENTS.md+stub fungsional, narasi suara-asisten dinetralkan di 6 berkas). v0.5.0 — K23: dashboard visual Papan Bukti (graf force-directed SVG tulisan sendiri, endpoint /dashboard + /dashboard/data). v0.4.9 — K22: suntik otomatis di percakapan baru (browser) — otomatisasi baca kini menyamai Claude Code SessionStart untuk semua platform kecuali toggle connector Claude.ai. v0.4.8 — K21: pengingat relevansi (badge, tidak menyisipkan) + Suntik lagi (cicilan anggaran_token, tanpa perubahan server). v0.4.7 — K20: fitur suntik memori di ekstensi browser (baca-otomatis untuk platform tanpa MCP), jaminan struktural tidak-pernah-submit. v0.4.6 — K19: MCP Streamable HTTP di /mcp — ingat bisa dipasang sebagai Custom Connector claude.ai; bug kebocoran token di log ditemukan dan diperbaiki sebelum dikirim. v0.4.5 — K18: sumber episode ketiga (browser, selain Claude Code dan API langsung); `/episode` kini teruji (8 uji server nyata). v0.4.4 — K17: Gemini ditambah ke konektor; izin berkas SQLite Python diperbaiki (0600/0700); gate.py & penyedia.py yang sebelumnya tanpa uji kini teruji (13 uji). v0.4.3 — K11 tangkap diimplementasikan (`ingat/tangkap.py`, `pasang`); jalur data nyata lengkap: hook → episode → konsolidasi → tanya → jawab → vault → gateway. v0.4.2 — Python selaras kontrak v2 (vektor terpisah, dua koleksi R12, identitas embedder, SQL portabel); port TS terbukti membaca DB Python. v0.4.1 — R8 diimplementasikan. v0.4.0 — v0.3.3 + Lampiran E (landasan kognitif & neurosains dari tiga buku teks terbuka): 9 validasi, 5 revisi (R8–R12), 3 kandidat kontrak v3. Sebelumnya v0.3.3 — v0.3.2 + 7.7 konsolidasi berpandu pertanyaan (K15, `ingat/tanya.py`, 9 uji). Sebelumnya: v0.3.1 + kontrak v2 (K14): kolom `langkah`/`sesi` episode, `tier_maks`/`usulan_perluasan_lingkup`/`sintesis`/`catatan` pelajaran, penghitung eksekusi prosedur, jendela `berlaku_sampai` + kolom konsolidasi norma, tabel `metrik` & `panggilan_ingat`. Python 30 uji hijau, port TS 28 hijau (+2 todo) |
| **Tanggal** | 6 September 2026 |
| **Induk** | `docs/spek-ai-hybrid.md` (Epic E19) — dokumen ini memakai gate klasifikasi data P/I/S yang didefinisikan di sana |
| **Lokasi usulan** | `docs/spek-arsitektur-memori.md` |
| **Pemilik keputusan** | Tuan Muda |

> Catatan kejujuran sumber: klaim tentang produk pihak ketiga (MemPalace, Mem0, TencentDB Agent Memory, TurboVec, Obsidian, Zep/Graphiti, Letta, Karpathy LLM Wiki) berasal dari pencarian web per September 2026 — rujukan di Lampiran B. Klaim tentang literatur kognitif dan paper agent pra-2026 berasal dari referensi umum dan ditandai demikian. Selebihnya adalah penalaran desain dari diskusi, bukan fakta bersumber. Titik yang ditandai **BELUM DIVERIFIKASI** tidak boleh dianggap benar sebelum kodenya dibaca.

### Perubahan dari v0.1

| # | Revisi | Bab |
|---|---|---|
| R1 | Jenis keempat: **Prosedur** (memori prosedural) dipisah dari Pelajaran | 4, 5, 6.5, 7.6 |
| R2 | Koreksi tunggal tidak langsung jadi aturan global — lahir `dipersempit`; generalisasi butuh konfirmasi kedua yang independen | 7.2 |
| R3 | Norma tidak *dipelajari*, tetapi **tampilan konsolidasi** non-otoritatif boleh diturunkan | 4, 6.4 |
| R4 | Kolom `lingkup` wajib untuk Pelajaran dan Prosedur | 2 (P9), 6, 8.1 |
| R5 | Kedaluwarsa tanpa kontra: `berlaku_untuk` + `tinjau_setelah` | 6, 7.5 |
| R6 | Hipotesis boleh dipakai dengan bendera; naik ke aturan hanya oleh manusia; status `usulan` ditambahkan | 2 (P10), 5, 7.3, 8.3 |
| R7 | Bab uji penerimaan (putar-ulang) dengan lima kasus nyata | 12 |
| — | Zep/Graphiti dan Letta masuk peta kandidat; Karpathy LLM Wiki jadi rujukan lapisan kurasi; Lampiran C prior art | 10, C |

---

## 0. Ringkasan satu layar

Sistem memori untuk agent AI di Dashboard Cakti terdiri dari **empat jenis pengetahuan** dengan **empat kebijakan retensi**, disatukan oleh **satu state machine status**, **satu pintu retrieval**, dan **anggaran konteks eksplisit**.

```
JENIS       MEMUDAR?  DIKONSOLIDASI?     DIHAPUS?             VERSI LAMA              DIAMBIL LEWAT
Episode     ya        ya (jadi bahan)    tidak (didinginkan)  bukti                   pointer saja
Pelajaran   tidak     ya (direvisi)      tidak (ditarik)      riwayat + kontra        query + lingkup
Prosedur    tidak     ya (dari pola)     tidak (ditarik)      riwayat                 pencocokan tugas
Norma       tidak     TIDAK PERNAH       TIDAK PERNAH         masih mengikat masanya  tanggal peristiwa
```

Yang masuk ke context window: **peta + pelajaran aktif dalam lingkup + prosedur yang cocok tugas + norma yang berlaku pada tanggal peristiwa.** Episode dan bukti mentah tidak pernah disuntik kecuali ditarik eksplisit lewat pointer. Hipotesis boleh masuk, selalu berbendera.

---

## 1. Masalah yang diselesaikan

1. **Amnesia lintas sesi.** Setiap sesi agent mulai dari nol; keputusan dan koreksi hilang.
2. **Pembengkakan instruksi.** `CLAUDE.md` dan `.claude/rules/*.md` yang terus ditambah adalah pelajaran dan prosedur yang tidak pernah dikonsolidasi dan tidak pernah kedaluwarsa.
3. **Kehilangan penalaran.** Sistem ekstraktif menyimpan kesimpulan dan membuang alasannya; saat kesimpulan salah, tidak ada jalan kembali.
4. **Norma yang tertimpa.** Peraturan lama "diperbarui" oleh yang baru dan hilang — padahal masih mengikat untuk kontrak di masanya.
5. **Kewalahan konteks ("kasus Spalko").** Transfer pengetahuan tanpa mengukur kapasitas penerima menurunkan kualitas jawaban secara diam-diam.
6. **Pelajaran salah kamar.** Aturan dari kerja konten menyala saat konteksnya keuangan, atau sebaliknya.
7. **Overgeneralisasi dari satu kejadian.** Satu koreksi menjadi aturan universal yang salah di konteks lain ("fobia").

---

## 2. Prinsip desain

| # | Prinsip | Konsekuensi |
|---|---|---|
| P1 | **Turunkan derajat, jangan hapus.** | Episode yang sudah dikonsolidasi pindah ke penyimpanan dingin dengan pointer dari pelajaran; tidak pernah `DELETE`. |
| P2 | **Simpan semua; gate di penggunaan, bukan di penyimpanan.** (K10) | Semua episode tersimpan verbatim, termasuk tier S. Hanya nilai kredensial yang diredaksi sebelum tulis. Tier S: tidak ke LLM, tidak keluar mesin, tidak muncul di `ingat()` tanpa `sertakan_S: true`. Arsip berretensi hukum (bukti pajak, payroll) tetap hidup di sistem arsip — memori boleh menyimpan *jejak episodiknya*, bukan menggantikan arsipnya. |
| P3 | **Adopsi pola, bukan produk.** | Pola pihak ketiga (offloading, wing/room, piramida L0–L3, sleep-time agent, bitemporal edge) diimplementasikan sendiri bila lebih murah daripada memikul seluruh stack-nya. |
| P4 | **Satu pintu retrieval.** | Semua pembacaan memori lewat satu gateway. Tidak ada dua sistem memori berjalan sejajar. |
| P5 | **Provenance manusia di atas mesin.** | Catatan yang ditulis/disetujui manusia memenangkan konflik atas hasil mesin. |
| P6 | **Struktur dulu, isi kemudian.** | Startup memuat peta (indeks + daftar item aktif), bukan isi. |
| P7 | **Kapasitas penerima adalah batasan desain.** | Anggaran konteks adalah angka. Lewat batas → kembalikan pointer, bukan isi. |
| P8 | **Simpan tanpa mengikat konteks asal.** | Pelajaran ditulis pada tingkat abstraksi yang bisa ditransfer. Transfer ke kasus baru adalah tugas penalaran, bukan memori. |
| P9 | **Tidak ada pelajaran tanpa lingkup.** | Setiap pelajaran/prosedur punya `lingkup`; yang belum terbukti lintas lingkup tidak boleh menyala di luar lingkupnya. |
| P10 | **Hipotesis boleh dipakai, tidak boleh dipercaya diam-diam.** | Hipotesis masuk konteks hanya dengan bendera "belum ditinjau" yang diteruskan ke jawaban. Naik ke aturan hanya oleh manusia. |
| P11 | **Abstraksi, bukan penyamaran.** (K28) | Apa pun yang lahir dari data tier tinggi harus naik ke tingkat abstraksi yang bisa ditransfer (P8), bukan sekadar ditutupi. Menyalin kalimat sumber lalu menghapus angkanya adalah penyamaran dan ditolak. Ditegakkan pada **keluaran** model, bukan masukannya: model lokal boleh *melihat* tier S (tidak keluar mesin), tetapi yang ia *hasilkan* diperiksa `ingat/rem.py:periksa_abstraksi` — pola tier S, deret ≥8 digit, dan run ≥5 kata berurutan yang sama dengan sumber semuanya menggugurkan hasil. |

---

## 3. Dua sumbu yang tidak boleh dicampur

| Sumbu | Pertanyaan | Ditangani oleh |
|---|---|---|
| **Sumbu 1 — perubahan** | Bagaimana pengetahuan itu sendiri berubah? | State machine status (Bab 5) + loop konsolidasi (Bab 7) |
| **Sumbu 2 — pemanfaatan** | Bagaimana pengetahuan lama dipakai di kasus baru? | **Bukan urusan memori.** Ini penalaran LLM. Memori hanya membantu dengan P8 dan P9. |

Contoh pembeda: matriks (abad ke-19) dipakai untuk grafika komputer tanpa berubah sedikit pun — itu sumbu 2. Perpres pengadaan diganti Perpres baru — itu sumbu 1.

---

## 4. Empat jenis pengetahuan

| | **Episode** | **Pelajaran** | **Prosedur** | **Norma** |
|---|---|---|---|---|
| Apa | Kejadian mentah | Aturan *tahu-bahwa* hasil generalisasi | Langkah *tahu-cara*; boleh berupa kode/hook/skill | Ketentuan dari otoritas eksternal |
| Sumber validitas | Terjadi atau tidak | Bukti terakumulasi | **Dijalankan dan berhasil** | Otoritas, per tanggal |
| Keyakinan | — | 0–1, naik-turun | Tingkat keberhasilan eksekusi | Biner per tanggal |
| Ditulis oleh | Sistem | Sistem, disetujui manusia | Sistem (draf) atau manusia; disetujui manusia | Manusia (ingest dokumen resmi) |
| Memudar | Ya | Tidak | Tidak | Tidak |
| Dikonsolidasi | Ya (bahan) | Ya (direvisi) | Ya (dari pola sukses berulang) | **Tidak pernah dipelajari**; tampilan konsolidasi boleh (6.4) |
| Dihapus | Tidak (didinginkan) | Tidak (ditarik) | Tidak (ditarik) | **Tidak pernah** |
| Versi lama | `bukti` | riwayat + `kontra` | riwayat | Masih mengikat untuk masanya |
| Diambil lewat | pointer | query + `lingkup` | **pencocokan tugas** + `lingkup` | **tanggal peristiwa** |
| Divalidasi lewat | — | bukti/kontra | **uji eksekusi** | dokumen resmi |
| Rumah | Store episodik (dingin) | Obsidian `pelajaran/` | `.claude/rules/*.md`, skill, hook; indeks di Obsidian `prosedur/` | Obsidian `norma/`, satu catatan per versi |

**Mengapa Prosedur dipisah dari Pelajaran (R1):** berbeda di tiga sisi — cara diambil (dicocokkan ke *tugas*, bukan ke *query*), cara divalidasi (dengan *dijalankan*, bukan dengan bukti), dan bentuk (bisa kode). Yang sudah ada hari ini — `.claude/rules/*.md`, skill, `jaga.mjs` — adalah memori prosedural yang selama ini hidup di luar model.

**Sub-jenis Norma yang diperlakukan sama:** peraturan perundangan (UU, PP, Perpres, PMK, Kepmen), SOP internal yang diberlakukan pimpinan, ketentuan kontrak/klien.

---

## 5. State machine status

```
(episode)    aktif ──► didinginkan ──► diarsipkan (per retensi)

(pelajaran)  hipotesis ──► usulan ──► aturan ──► dipersempit (tetap aktif, domain dibatasi)
                 │            │          └─────► ditarik (terbukti salah / veto manusia)
                 └────────────┴────────────────► ditarik
             * hipotesis → usulan: otomatis (bobot bukti ≥ ambang, 7.2)
             * usulan → aturan: HANYA manusia (memindahkan dari _usulan/)

(prosedur)   draf ──► teruji ──► aktif ──► dipersempit (lingkungan dibatasi)
                                    └─────► ditarik (gagal berulang / veto manusia)
             * draf → teruji: lulus uji eksekusi
             * teruji → aktif: HANYA manusia

(norma)      berlaku ──► dicabut (oleh otoritas; tetap mengikat untuk masanya)
                └──────► dibatalkan (putusan pengadilan; tidak mengikat)

abadi — hanya ditetapkan manusia untuk definisi/rumus tetap; tidak punya transisi keluar
```

### 5.1 Empat jalur keluar dan mengapa harus dibedakan

| Jalur | Arti | Masih boleh dipakai? | Contoh |
|---|---|---|---|
| **dipersempit** | Masih benar, domainnya dibatasi | Ya, di dalam domain | Mekanika Newton pada v ≪ c |
| **dicabut** | Dulu berlaku, kini tidak untuk peristiwa baru | Ya, untuk peristiwa di masanya | Perpres pengadaan lama |
| **ditarik** | Salah sejak awal | **Tidak, di mana pun** — dan harus diingat *sebagai kesalahan* | Studi yang diretraksi; pelajaran yang terbukti keliru |
| **abadi** | Terbukti, tidak akan keluar | Ya, selamanya | Rumus PPN DPP 11/12 (selama norma yang mendasarinya berlaku) |

Sistem pihak ketiga tidak membedakan ini. Operasi hapus/perbarui di Mem0 memperlakukan tiga jalur pertama sebagai satu. Invalidasi MemPalace hanya mengenal tanggal akhir. Graphiti punya `t_valid`/`t_invalid` tetapi tidak membedakan "invalid karena diganti" dari "invalid karena salah" — yaitu `dicabut` vs `ditarik`. Karena itu `status` **wajib** ada di skema kita, apa pun mesin di bawahnya.

### 5.2 Transisi yang diizinkan per jenis

| Jenis | Diizinkan | Dilarang |
|---|---|---|
| Episode | aktif → didinginkan → diarsipkan | segala hapus di luar retensi hukum |
| Pelajaran | hipotesis → usulan (otomatis); usulan → aturan (manusia); aturan → dipersempit; **dipersempit → aturan (manusia, pemulihan domain — v0.3.1)**; aturan/usulan/hipotesis/dipersempit → ditarik | hipotesis → aturan langsung; → abadi; → dicabut |
| Prosedur | draf → teruji (uji lulus); teruji → aktif (manusia); aktif → dipersempit; **dipersempit → aktif (manusia, pemulihan — v0.3.1)**; aktif/teruji/draf/dipersempit → ditarik | draf → aktif langsung |
| Norma | berlaku → dicabut; berlaku → dibatalkan — **keduanya hanya manusia** | dipersempit; ditarik; konsolidasi apa pun (tampilan konsolidasi bukan transisi — 6.4); pencabutan oleh mesin |

---

## 6. Skema record

> **Kontrak v2 (2026-09-07).** Skema YAML di bab ini adalah bentuk *vault* (frontmatter). Kolom tabel yang otoritatif ada di `skema/ingat.sql`; v2 menambah: episode `langkah`, `sesi`; pelajaran `tier_maks`, `usulan_perluasan_lingkup`, `sintesis`, `catatan`; prosedur `eksekusi_total`, `eksekusi_berhasil`, `gagal_beruntun`, `tinjau_ulang`, `veto_manusia`, `dibuat`, `tier_maks`, `catatan` (`tingkat_berhasil` menjadi cache); norma `berlaku_sampai`, `disusun_pada`, `disusun_oleh`, `berlaku_untuk_tanggal`, `isi`, `catatan`; tabel baru `metrik`, `panggilan_ingat`. Query titik-waktu norma menjadi satu klausa: `berlaku_sejak ≤ t AND (berlaku_sampai IS NULL OR t < berlaku_sampai)`.

### 6.1 Episode

```yaml
id: ep-2026-09-06-0142            # ep-<tanggal>-<urut>
waktu: 2026-09-06T14:20:00+07:00
sumber: claude-code                # claude-code | chat | dashboard | tool:<nama>
tier: I                            # P | I | S — gate spek-ai-hybrid.md
lingkup: proyek:fp-dashboard       # global | proyek:<nama> | peran:<nama>
instrumen: [hostinger-mcp]
jenis_kejadian: koreksi            # koreksi | kegagalan | pola | sukses
bobot: 5                           # lihat 7.2
status: aktif                      # aktif | didinginkan | diarsipkan
isi_ref: cold/2026/09/ep-...tvim   # pointer ke isi verbatim (tidak pernah inline)
ringkas: "Diasumsikan tidak ada beban kerja karena VPS_getProjectListV1 kosong; ternyata deploy manual via SSH tidak terlihat."
```

### 6.2 Pelajaran

```yaml
id: pl-0017
pelajaran: "Ketiadaan hasil dari instrumen ≠ ketiadaan objek; instrumen punya cakupan."
pemicu: "Akan menyimpulkan 'tidak ada X' dari satu tool yang mengembalikan kosong."
tindakan: "Cek cakupan tool dulu; cari jalur observasi kedua sebelum menyimpulkan."
lingkup: proyek:fp-dashboard       # R4 — global hanya setelah konfirmasi lintas lingkup (7.2)
status: usulan                     # hipotesis | usulan | aturan | dipersempit | ditarik
keyakinan: 0.6
bukti: [ep-2026-09-06-0142]
kontra: []
instrumen_saat_dibuat: [hostinger-mcp]
berlaku_untuk: {}                  # R5 — mis. {alpine: "3.x"}; kosong = tidak terikat versi
tinjau_setelah: 2026-12-05         # R5 — default dibuat + 90 hari; digeser tiap konfirmasi
dibuat: 2026-09-06
terakhir_dikonfirmasi: 2026-09-06
tinjau_ulang: false                # true bila instrumen baru dipasang / kedaluwarsa (7.4, 7.5)
ditinjau_manusia: false            # true hanya setelah dipindah dari _usulan/
veto_manusia: null                 # tanggal + alasan bila ditarik oleh Tuan Muda
```

Aturan penulisan `pelajaran` dan `pemicu` (menegakkan P8):
- Tidak menyebut nama tool/orang/proyek spesifik kecuali memang itu domainnya.
- `pemicu` harus berupa kondisi yang bisa dikenali di kasus lain — bukan deskripsi kejadian asal.
- Uji: "Apakah aturan ini bisa dipakai di proyek yang berbeda tanpa diubah?" Jika tidak, `lingkup` tetap sempit.

### 6.3 Norma (versi resmi)

```yaml
id: nr-perpres-46-2025
norma: "Perpres 46/2025"
judul: "<judul resmi lengkap>"
jenis: perpres                     # uu | pp | perpres | pmk | kepmen | sop-internal | kontrak
otoritatif: true
berlaku_sejak: null                # ISI dari dokumen resmi — jangan ditebak
dicabut_oleh: null
dibatalkan_oleh: null
mengganti: []                      # ISI dari Ketentuan Penutup dokumen resmi
alasan: "<kutipan konsiderans 'Menimbang' / Penjelasan Umum>"
peralihan: "<kutipan verbatim pasal Ketentuan Peralihan>"
sumber_dokumen: "<path/URL PDF resmi: JDIH>"
status: berlaku                    # berlaku | dicabut | dibatalkan
```

Aturan ingest:
- `alasan`, `peralihan`, `mengganti` **diekstrak dari dokumen resmi**, bukan disimpulkan. "Kenapa ada peraturan baru" sudah tertulis di konsiderans dan Penjelasan Umum peraturan baru itu sendiri.
- Satu catatan per versi. Perubahan (perubahan pertama, kedua) adalah catatan terpisah dengan `mengganti` menunjuk induknya.
- Nilai yang belum dibaca dari dokumen **dibiarkan `null`**, bukan diisi perkiraan.

### 6.4 Norma — tampilan konsolidasi (R3)

Praktik hukum rutin membuat teks konsolidasi (induk + semua perubahan digabung). Ini **diizinkan** dengan tiga syarat: bukan transisi status, ditandai non-otoritatif, dan menunjuk ke semua versi resmi yang menyusunnya.

```yaml
id: nr-konsolidasi-perpres-pengadaan-2026-09
otoritatif: false                  # WAJIB false
disusun_dari: [nr-perpres-16-2018, nr-perpres-12-2021, nr-perpres-46-2025]
disusun_pada: 2026-09-06
disusun_oleh: mesin                # mesin | manusia
berlaku_untuk_tanggal: 2026-09-06  # tampilan ini benar untuk peristiwa pada tanggal ini
catatan: "Bila ada selisih, versi otoritatif yang menang. Untuk peristiwa sebelum berlaku_sejak Perpres 46/2025, jangan pakai tampilan ini."
```

Retrieval mengembalikan tampilan konsolidasi **hanya bersama** daftar `disusun_dari`, dan jawaban wajib menyebut bahwa ini tampilan turunan.

### 6.5 Prosedur (R1)

```yaml
id: pr-0004
prosedur: "Pasang dependensi Node dengan hook pengaman aktif"
tugas_pemicu: "npm ci / npm install di repo yang memakai jaga.mjs"
langkah:
  - "npm ci --ignore-scripts"
  - "npx playwright install chromium   # terpisah, karena --ignore-scripts memblokir postinstall"
bentuk: teks                       # teks | skrip:<path> | hook:<path> | skill:<nama>
lingkup: proyek:fp-dashboard
status: aktif                      # draf | teruji | aktif | dipersempit | ditarik
tingkat_berhasil: 1.0              # eksekusi berhasil / total eksekusi
bukti: [ep-...]
berlaku_untuk: {node: "22", playwright: "1.x"}
tinjau_setelah: 2026-12-05
uji: "npm ci --ignore-scripts && npx playwright install chromium && node -e \"require('playwright')\""
ditinjau_manusia: true
```

Prosedur diambil dengan **pencocokan tugas** (`tugas_pemicu` vs deskripsi tugas sesi), bukan query semantik bebas. Validasi = menjalankan `uji`. Prosedur yang `uji`-nya gagal dua kali berturut-turut → `tinjau_ulang: true`; tiga kali → `ditarik` otomatis dengan catatan.

### 6.6 Instrumen

```yaml
id: hostinger-mcp
nama: "Hostinger MCP Connector"
dipasang_sejak: null               # ISI dari catatan pemasangan
cakupan: "Hanya melihat deploy yang memakai tooling Hostinger; deploy manual via SSH tidak terlihat."
titik_buta_diketahui: ["deploy manual SSH"]
```

---

## 7. Loop konsolidasi

### 7.1 Pemicu (kapan "tidur")

| Pemicu | Jalur | Alasan |
|---|---|---|
| Job berkala 02:00 WIB | Batch penuh | Padanan konsolidasi saat tidur; menggeneralisasi butuh banyak episode |
| Akumulasi ≥ 50 episode baru | Batch penuh | Supaya hari sibuk tidak menunggu malam |
| Akhir sesi, episode `bobot ≥ 3` | Jalur cepat | Koreksi dan kegagalan tidak boleh menunggu |

Konsolidasi **tidak pernah** terjadi saat tulis. Pola ini sudah dibuktikan produk: Letta memisahkan agent utama (tanpa alat edit memori) dari sleep-time agent yang bekerja di latar — lihat Lampiran C.

### 7.2 Pembobotan dan ambang (R2)

| `jenis_kejadian` | Bobot | Cara dikenali |
|---|---|---|
| koreksi | 5 | Manusia mengoreksi ("bukan begitu", "salah", edit langsung) |
| kegagalan | 3 | Tugas gagal / dibatalkan / harus diulang |
| pola | 2 | ≥ 3 episode serupa dalam 30 hari |
| sukses | 1 | Tugas selesai tanpa koreksi |

Ambang dan lingkup:
- **hipotesis → usulan** saat bobot kumulatif bukti ≥ 5. Satu koreksi manusia cukup untuk menjadi usulan — **tetapi `lingkup`-nya dikunci ke lingkup episode asal.**
- **Generalisasi lingkup** (proyek → global, atau peran A → peran B) hanya bila ada bukti kedua yang *independen*: berasal dari lingkup berbeda **atau** sesi berbeda **dan** instrumen berbeda. Satu kejadian, betapa pun menyakitkan, tidak pernah menghasilkan aturan global.
- Alasan: manusia belajar dari satu kali terbakar, tetapi dari satu kali juga manusia bisa takut semua cahaya. Menahan generalisasi sampai konfirmasi kedua adalah harga murah untuk menghindari fobia sistem.

### 7.3 Langkah job (R6)

1. Ambil episode `status: aktif` dengan `tier ∈ {P, I}` (tier S dilewati — Bab 9). Sejak K28, bila keempat rem tier S terpasang (9.1), `tier ∈ {P, I, S}`.
2. Kelompokkan episode serupa (embedding + `instrumen` + `jenis_kejadian` + `lingkup`).
3. Untuk tiap kelompok: cari pelajaran aktif yang `pemicu`-nya cocok **dan** `lingkup`-nya memuat lingkup episode.
   - Cocok & konsisten → tambah ke `bukti`, perbarui `terakhir_dikonfirmasi`, geser `tinjau_setelah`, naikkan `keyakinan`; bila bukti baru dari lingkup berbeda → usulkan perluasan `lingkup`.
   - Cocok & bertentangan → tambah ke `kontra`; jika `kontra` mendominasi → `dipersempit` (tulis domain baru) atau `ditarik`.
   - Tidak cocok → buat `hipotesis` baru (skema 6.2) dengan `lingkup` = lingkup episode.
4. Hipotesis yang mencapai ambang 7.2 → `status: usulan`, ditulis ke Obsidian `pelajaran/_usulan/`.
5. **Hipotesis dan usulan tetap boleh diambil retrieval** dengan `keyakinan ≤ 0.6` dan bendera `belum_ditinjau: true` yang wajib diteruskan ke jawaban agent ("berdasarkan pola yang belum ditinjau: …"). Naik ke `aturan` **hanya** saat Tuan Muda memindahkan berkas dari `_usulan/` ke `pelajaran/` (atau menandai `veto_manusia`).
6. Semua episode yang diproses → `status: didinginkan`, isi dipindah ke penyimpanan dingin, `isi_ref` diperbarui.
7. Catat metrik (Bab 11).

Langkah 2–3 memakai LLM. Karena itu seluruh job **hanya boleh berjalan di endpoint inferensi yang diizinkan untuk tier tertinggi** dari episode yang diproses (gate spek-ai-hybrid.md).

### 7.3b Episode tidak langsung didinginkan (R8)

Konsolidasi sistem bersifat *bertahap secara waktu*: pasien H.M. kehilangan ingatan deklaratif ~2 tahun sebelum operasi, tetapi ingatan lama utuh — jejak baru bergantung pada hipokampus selama berbulan-bulan sebelum menetap di neokorteks (ONI 13.2). Padanan desainnya: episode **tetap `aktif`** setelah konsolidasi pertama, supaya bisa dikelompokkan ulang saat bukti baru datang; pindah ke `didinginkan` hanya bila (a) pelajaran induknya sudah `aturan` (disetujui manusia), **atau** (b) usianya melewati `hari_dingin` (default 30 hari) — mana yang lebih dulu. Diimplementasikan 7 Sep 2026 (`Konsolidator.dinginkan_tertunda`, konfigurasi `hari_dingin`). Konsekuensi yang ikut ditegakkan: karena episode tetap aktif, **hanya episode baru** yang boleh mengubah pelajaran — run ulang tanpa bukti baru tidak menggelembungkan keyakinan dan tidak mengubah bukti lama menjadi kontra.

### 7.4 Aturan instrumen baru

Instrumen baru membuat terlihat apa yang sebelumnya tak terlihat. Saat record instrumen ditambahkan:
- Pelajaran/prosedur yang **seluruh `bukti`-nya lahir sebelum `dipasang_sejak`** dan bersinggungan dengan `cakupan` instrumen → `tinjau_ulang: true`.
- Job berikutnya memprioritaskan item bertanda `tinjau_ulang`.
- Gelombang `kontra` setelah instrumen baru adalah normal, bukan regresi.
- **Instrumen dicabut (R11):** korteks memetakan ulang wilayah yang kehilangan masukan — representasi jari yang diamputasi diambil alih jari tetangga (Merzenich dkk. 1984, dikutip FoN Bab 25). Padanan: saat record instrumen diberi `dicabut_sejak`, pelajaran/prosedur yang `instrumen_saat_dibuat`-nya memuat instrumen itu → `tinjau_ulang: true`, dan prosedur yang `langkah`-nya memanggilnya → `dipersempit` sampai manusia memetakan ulang. Kolom `dicabut_sejak` = kandidat kontrak v3.

### 7.5 Kedaluwarsa tanpa kontra (R5)

Pelajaran bisa usang tanpa satu pun episode kontra — lingkungan bergeser diam-diam (versi pustaka, struktur repo, kebijakan platform). Dua mekanisme:
- **`tinjau_setelah` lewat** dan tidak ada konfirmasi sejak `terakhir_dikonfirmasi` → `tinjau_ulang: true`; retrieval menurunkan `keyakinan` efektif sebesar 0.2 sampai ditinjau.
- **`berlaku_untuk` tidak cocok** dengan lingkungan sesi (mis. pelajaran untuk `alpine: "3.x"`, sesi mendeteksi 4.x) → item tidak disuntik ke L-aturan; hanya muncul di L-tarik dengan bendera "versi berbeda".

Default `tinjau_setelah` = `dibuat` + 90 hari; item yang sering dikonfirmasi otomatis bergeser lebih jauh (maks. 365 hari). Angka ini usulan awal.

### 7.6 Konsolidasi prosedur (R1)

- ≥ 3 episode `sukses` dengan urutan langkah serupa dalam satu `lingkup` → job menulis `draf` prosedur ke `prosedur/_usulan/` lengkap dengan `uji` yang disintesis dari langkah terakhir yang memverifikasi keberhasilan.
- Episode `kegagalan` yang langkahnya cocok dengan prosedur aktif → `tingkat_berhasil` turun; lihat aturan gagal di 6.5.
- Prosedur **tidak pernah** naik ke `aktif` tanpa manusia, karena prosedur mengeksekusi sesuatu.

---

### 7.7 Konsolidasi berpandu pertanyaan (v0.5 — K15)

Di antara v0 (kelompokkan, manusia tulis) dan v1 (LLM menyintesis draf): **mesin tidak menyimpulkan, mesin bertanya.** Pertanyaan dibangun dari kolom yang sudah ada — tanpa LLM — dan manusia adalah *oracle* (active learning): dari 100 episode, yang disodorkan bukan 100 kelompok, melainkan ≤ 7 pertanyaan paling bernilai.

| Jenis | Pemicu di data | Jawaban sah | Efek |
|---|---|---|---|
| generalisasi | pelajaran `hipotesis`/`usulan` belum ditinjau manusia | `buat`, `setuju-draf`, `tolak`, `premis-salah` | pelajaran ditulis manusia → `aturan`; `premis-salah` = pengelompokan mesin keliru (dicatat sebagai sinyal, pelajaran `ditarik`) |
| perluasan | `usulan_perluasan_lingkup` terisi | `global`, `tetap`, `lingkup:<x>` | `lingkup` diubah, usulan dibersihkan |
| konflik | `kontra` tidak kosong pada aturan aktif | `persempit` (+`berlaku_untuk`/`pemicu`), `tarik`, `tetap` | `dipersempit` / `ditarik` / kontra dicatat ditolak |
| kedaluwarsa | `tinjau_setelah` lewat atau `tinjau_ulang` | `konfirmasi`, `persempit`, `tarik` | `terakhir_dikonfirmasi` + `tinjau_setelah` digeser / dipersempit / ditarik |

**Anti-sugesti (R9).** Urutan di tiap pertanyaan: bukti → fakta → pertanyaan → blok jawab → *baru* saran dan draf mesin. Template jawaban tidak pernah diisi draf mesin. Alasannya empiris: pertanyaan yang mengarahkan mengubah ingatan (efek misinformasi, Loftus & Palmer 1974 — "smashed" vs "hit" mengubah estimasi kecepatan dan memunculkan pecahan kaca yang tidak ada); prosedur *blind lineup* menjadi rekomendasi standar karena itu. Draf mesin adalah "lineup" yang ditumpuk; tampilkan setelah manusia menjawab sendiri. Pelajaran yang ditulis sendiri diberi keyakinan 0.8, `setuju-draf` 0.7 — pemrosesan yang lebih dalam diingat lebih baik (levels of processing, Craik & Lockhart 1972).

**Jadwal tinjau melebar (R10).** Tiap konfirmasi berhasil menggandakan interval tinjau (90 → 180 → 365 hari, dibatasi). Ini distributed practice + kurva lupa Ebbinghaus: retensi turun cepat lalu mendatar, dan pengulangan berjarak menahannya lebih murah daripada pengulangan rapat. Metode kartu indeks di buku teks (pisahkan yang benar dan salah, ulangi yang salah) adalah persis pemilahan `tinjau_setelah`.

Aturan: `lewati` dan `tidak-tahu` selalu sah; pertanyaan yang ditunda ditanya ulang setelah `hari_tunggu` (30 hari), maksimal `maks_diulang` (2×), lalu turun ke ekor prioritas — tidak menumpuk. Pertanyaan yang sudah **diputuskan** tidak ditanya ulang kecuali keadaannya berubah (kuncinya memuat id kontra / bukti / tanggal tinjau). Setiap pertanyaan **menunjukkan buktinya** sebelum bertanya, supaya premis yang salah bisa dikenali. Jawaban diterapkan ke **berkas vault** (P5), bukan ke store; `Vault.sinkron` yang menegakkan state machine. Prioritas: konflik > generalisasi (menurut bobot bukti) > perluasan > kedaluwarsa.

Ini juga yang menyelesaikan bottleneck manusia (Bab 12 analisis kekurangan, butir 6): manusia tidak menulis dari nol dan tidak melabeli semuanya — hanya menjawab yang paling mengurangi ketidakpastian.

---

## 8. Retrieval dan anggaran konteks (anti-Spalko)

### 8.1 Satu pintu

```
ingat(query, jenis?, lingkup, tanggal_peristiwa?, tugas?, anggaran_token)
  → { item[], pointer[], asumsi[], bendera[] }
```

- `lingkup` **wajib** (R4): hasil dibatasi ke item yang `lingkup`-nya `global` atau memuat lingkup sesi.
- `jenis` kosong → semua jenis, urutan prioritas 8.3.
- `tanggal_peristiwa` kosong → default hari ini; `asumsi[]` **wajib** memuat "tanggal peristiwa diasumsikan hari ini".
- `tugas` diisi → prosedur dicocokkan ke `tugas_pemicu`.
- `anggaran_token` habis → sisa hasil dikembalikan sebagai `pointer[]` (id + ringkas ≤ 20 kata).
- `bendera[]` memuat `belum_ditinjau`, `versi_berbeda`, `tampilan_konsolidasi`, `pernah_ditarik` — agent wajib meneruskan bendera yang relevan ke jawaban.
- Dedup: hasil disaring dengan MMR (atau setara) sebelum dipotong anggaran, supaya nyaris-duplikat tidak menggusur item yang berbeda.

### 8.2 Lapisan pemuatan

| Lapisan | Kapan dimuat | Isi | Anggaran usulan (kalibrasi) |
|---|---|---|---|
| **L-peta** | Startup, selalu | Indeks per direktori (wing/room), daftar id+judul pelajaran/prosedur aktif dalam lingkup, daftar norma berlaku hari ini (judul saja) | ≤ 300 token |
| **L-aturan** | Startup, selalu | Isi pelajaran `aturan`/`dipersempit` yang `pemicu` dan `lingkup`-nya cocok; prosedur `aktif` yang `tugas_pemicu`-nya cocok | ≤ 1.500 token |
| **L-tarik** | Hanya saat `ingat()` dipanggil | Pelajaran lain, hipotesis berbendera, norma per tanggal, ringkas episode | ≤ 600 token / panggilan, ≤ 5 item |
| **L-bukti** | Hanya lewat `buka_bukti(id)` | Isi verbatim satu episode dari penyimpanan dingin | ≤ 1 episode / panggilan |
| **Total memori** | — | Semua lapisan | ≤ 15 % context window aktif |

Angka usulan awal, dikalibrasi setelah dua minggu metrik. Pengguna Karpathy LLM Wiki melaporkan pola itu rusak melewati ~200 berkas karena agent tak lagi bisa memegang seluruh graf, dan indeks per direktori adalah perbaikannya — itulah L-peta.

### 8.2b Isyarat sebelum isi (R12)

Recall berisyarat jauh lebih baik daripada recall bebas — kira-kira 75% vs sepertiga pada daftar kata berkategori (ONI 13.2) — dan aktivasi menyebar di jaringan semantik membuat konsep yang terkait ikut terangkat (Collins & Loftus 1975, Psychology 2e 8.1). Dua konsekuensi:

1. **L-peta adalah isyarat.** Daftar judul pelajaran/prosedur/norma per lingkup di startup bukan sekadar indeks hemat token — ia isyarat kategori yang membuat retrieval berikutnya lebih tepat. Ini alasan kognitif di balik indeks per direktori Karpathy.
2. **Dua vektor per pelajaran.** `pemicu` (kondisi — isyarat situasi) dan `pelajaran`+`tindakan` (isi) di-embed **terpisah**: pencocokan situasi sesi terhadap koleksi `pemicu`, pencocokan query terhadap koleksi `isi`. Diimplementasikan 7 Sep 2026: `Store` menulis koleksi `isi` dan `pemicu`; `Gateway` memakai skor maksimum keduanya — pelajaran yang hanya cocok di `pemicu` tetap ditemukan (uji `test_dua_koleksi_dan_pemicu_menemukan_pelajaran`). Dasarnya prinsip spesifisitas pengkodean: isyarat retrieval bekerja bila cocok dengan kondisi saat pengkodean — dan "sel konsep" yang menyala untuk satu konsep lintas modalitas (foto, teks, suara) menunjukkan bahwa yang harus dicocokkan adalah *konsep pemicu*, bukan permukaan kalimatnya (P8).

### 8.3 Arbiter konflik

Bila dua item menjawab query yang sama dan bertentangan:

1. Norma otoritatif yang `berlaku` pada `tanggal_peristiwa`
2. Tampilan konsolidasi norma (hanya bila `berlaku_untuk_tanggal` cocok; selalu berbendera)
3. Catatan kurasi manusia di Obsidian (`ditinjau_manusia: true`)
4. Pelajaran/prosedur mesin `aturan`/`aktif` dengan `keyakinan` tertinggi dalam lingkup
5. `dipersempit` (hanya bila query di dalam domainnya)
6. `usulan`/`hipotesis` — selalu berbendera `belum_ditinjau`
7. Episode — tidak pernah menang sendirian; hanya bukti

Untuk query bertipe *cara* (`tugas` terisi), prosedur `aktif` dalam lingkup diprioritaskan di atas pelajaran deklaratif.

Item `ditarik` tidak pernah dikembalikan sebagai jawaban, tetapi **dikembalikan sebagai peringatan** bila query menyerempet domainnya ("pernah diyakini X, ditarik pada <tanggal> karena <alasan>").

### 8.4 Sinyal "cukup"

Retrieval berhenti saat anggaran habis, **bukan** saat hasil habis. Tidak ada mode "muat semua yang relevan". Bila penalaran butuh lebih, ia memanggil `ingat()` lagi — dan setiap panggilan tercatat.

### 8.5 Larangan

- Tidak ada retrieval terjadwal/otomatis yang menyuntik isi ke tengah sesi tanpa dipanggil.
- Tidak ada dua gateway memori aktif bersamaan.
- Isi episode tidak pernah masuk `L-aturan` atau `L-peta`.
- Tidak ada item tanpa `lingkup` yang lolos gateway.

---

## 9. Kebijakan retensi × gate P/I/S

Tier mengikuti definisi di `docs/spek-ai-hybrid.md`.

| Tier | Episode | Konsolidasi | Pelajaran/prosedur yang lahir darinya | Norma |
|---|---|---|---|---|
| **P** | Normal | Ya, provider apa pun yang lolos gate | Boleh ditulis ke Obsidian | Normal |
| **I** | Normal | Ya, **hanya** endpoint terkendali/privat | Boleh; `ringkas`, `pelajaran`, `langkah` tidak boleh memuat nilai/nama internal spesifik | Normal |
| **S** | **Tersimpan verbatim** (K10), kredensial diredaksi, ditandai `tier: S` otomatis oleh `src/tangkap/tier.ts` bila terdeteksi NIK/NPWP/rekening/kata kunci payroll-pajak | **Default tidak pernah.** Sejak K28: boleh **hanya** ke model lokal, **hanya** di jalur konsolidasi, dan **hanya** bila keempat rem terpasang sekaligus (9.1) | Boleh dari mesin **hanya** bila lolos P11; yang gagal P11 → pelajaran ditulis manusia. Tidak pernah naik status otomatis (rem 4) | Normal — norma bukan data sensitif |

Contoh tier S: bukti pajak, payroll, dokumen klien, apa pun yang memuat NIK/NPWP/rekening. Episodenya boleh tersimpan (K10); dokumen dan kewajiban retensinya tetap urusan sistem arsip, dan pemrosesan data pribadi tunduk pada UU 27/2022 (PDP) — bukan nasihat hukum, verifikasi.

### 9.1 Empat rem tier S (K28) — `ingat/rem.py`

Sebelum K28 tier S ditolak ke penyedia inferensi mana pun, tanpa syarat. K28 melonggarkannya **hanya**
untuk model yang berjalan di mesin sendiri. Yang membuat pelonggaran ini bukan pelemahan adalah bahwa
**keempat rem wajib terpasang sekaligus** — dan sistemnya **gagal-tertutup**: satu rem hilang, tier S
tertutup lagi persis seperti sebelum K28.

| # | Rem | Ditegakkan di | Gagal-tertutup bila |
|---|---|---|---|
| 1 | **Gate P/I/S + lokalitas** | `RemTierS.penyedia_diizinkan` | penyedia tak terdaftar di `rem_tier_s.penyedia`, belum terkonfigurasi, atau `base_url`-nya bukan loopback/privat/label-tunggal |
| 2 | **Abstraksi P11** | `periksa_abstraksi` atas **keluaran** model | keluaran memuat pola tier S, deret ≥8 digit, atau menyalin ≥5 kata berurutan dari sumber |
| 3 | **Anggaran token harian** | `RemTierS.ada_anggaran` (tabel `metrik`, hari UTC) | `anggaran_token_harian` ≤ 0 atau kuota hari itu sudah habis |
| 4 | **Manusia penjaga akhir** | `rem_tier_s.penjaga` + `konsolidasi.jalankan` | `penjaga` kosong; dan pelajaran ber-`tier_maks: S` **tidak pernah** naik status otomatis, berapa pun bobot buktinya |

Dua batas yang sengaja dipertahankan:

- **Ruang lingkup sempit.** Pelonggaran hanya berlaku untuk `jalur="konsolidasi"`. Jalur umum —
  `Aplikasi.tanya` (`/tanya`) dan endpoint `/penyedia` — tetap menolak tier S selamanya. `gate.S` di
  konfigurasi diabaikan supaya tidak jadi pintu belakang.
- **Heuristik tier S tidak menyalin.** Untuk P/I, sintesis yang gagal jatuh ke heuristik "salin `ringkas`".
  Untuk S itu terlarang — vault adalah repo git (K7), jadi menyalin ringkas episode akan membawa data
  tier S keluar mesin. Bila sintesis gagal atau gugur P11, pelajarannya ditulis manusia.

**Klien yang terhubung** (per 13 Sep 2026): Claude, Claude Desktop, ChatGPT, ChatGPT Desktop, Gemini,
Perplexity. Semuanya bermodel cloud — **tidak satu pun boleh menerima tier S**. Rem 1 menutup mereka
lewat uji lokalitas `base_url`, bukan lewat daftar nama, supaya klien baru tidak otomatis lolos.

---

## 10. Lapisan arsitektur dan kandidat komponen

### 10.1 Lima lapisan

| Lapis | Peran | Ditulis oleh | Kandidat |
|---|---|---|---|
| **Kurasi** | Pelajaran/prosedur disetujui + norma | Manusia | Obsidian vault + MCP filesystem (read-only default; tulis hanya ke `_usulan/`). Pola: Karpathy LLM Wiki dengan indeks per direktori |
| **Prosedural** | Rules, skill, hook yang dieksekusi | Manusia (disetujui) | `.claude/rules/*.md`, skill, `jaga.mjs` — sudah ada; hanya perlu indeks + skema 6.5 |
| **Kerja** | Log tool sesi berjalan, dibuang dari konteks | Sistem | Pola *context offloading* + kanvas Mermaid (implementasi sendiri) |
| **Episodik** | Riwayat percakapan verbatim + konsolidasi | Sistem | **Pilih satu** mesin episodik — 10.3 |
| **Indeks** | ANN + (opsional) graf temporal | — | TurboVec (4-bit) untuk dingin; sqlite-vec/Chroma untuk panas; Graphiti bila lapisan norma butuh graf bitemporal |

### 10.2 Pemetaan sistem yang didiskusikan

| Sistem | Peran yang cocok | Peran yang **tidak** cocok | Catatan (per Sep 2026) |
|---|---|---|---|
| **Obsidian** | Kurasi; indeks prosedur; norma | Menampung episode otomatis | Plugin resmi "MCP Server" (beta); beberapa server filesystem tanpa app berjalan |
| **MemPalace** | Episodik verbatim; temporal KG-nya cocok untuk semantik "dicabut" | Konsolidasi (sengaja tidak punya) | ⚠️ Sumber sah hanya GitHub resmi, PyPI, mempalaceofficial.com. **TERVERIFIKASI (kode, commit d9f0590):** backend pluggable lewat kontrak RFC 001 (`BaseBackend`/`BaseCollection`) + entry point `mempalace.backends` + suite konformansi; in-tree: chroma, milvus, pgvector, qdrant, sqlite_exact |
| **Mem0** | Episodik ekstraktif (alternatif) | **Norma** — operasi perbarui/hapus menimpa versi lama | Apache-2.0; Qdrant + Postgres default |
| **TencentDB Agent Memory** | Referensi pola L0–L3, offloading, `node_id` traceback, aset Skill (= prosedur), ACL per Team/User/Agent (= lingkup) | Dipakai utuh bersama sistem episodik lain | MIT; SQLite + sqlite-vec default |
| **TurboVec** | Indeks dingin; allowlist kernel = filter `lingkup` dan versi norma | Indeks utama Mem0 (butuh filter metadata); terdistribusi; **drop-in langsung ke MemPalace** (kontrak `where` wajib) | Repo kanonik tampak `RyanCodrai/turbovec` — verifikasi sebelum `pip install`. **TERVERIFIKASI (kode):** API `IdMapIndex(dim, bit_width)`, `add_with_ids`, `search(q, k, allowlist=)`, `remove(id)`, simpan/muat `.tvim`. Jalur ke MemPalace = backend hibrida (10.4-a) |
| **Zep / Graphiti** | Fakta bitemporal hasil ekstraksi percakapan: edge dengan `t_valid`/`t_invalid` + waktu ingest; invalidasi tanpa buang; query titik-waktu | Membedakan `dicabut` vs `ditarik` (tidak ada — harus lewat atribut `status` kita); **lapisan norma** (graf suksesi peraturan hanya puluhan simpul — Obsidian wikilink + gateway sudah cukup; Graphiti berlebihan) | Paper arXiv 2501.13956. **TERVERIFIKASI (kode, commit b943c9e):** lisensi Apache-2.0; backend Neo4j 5.26 / FalkorDB 1.1.2 / Neptune / Kuzu (deprecated, upstream tak terawat); ada mode embedded `graphiti-core[falkordblite]` (Python ≥3.12, pin `redis<9`); ingest **wajib LLM** dengan structured output (OpenAI/Anthropic/Gemini; model kecil rawan gagal skema). ⚠️ FalkorDB berlisensi **SSPL v1** — lihat 10.4-c |
| **Letta** | Referensi pola: agent utama tanpa alat edit memori + sleep-time agent di latar; memory blocks = L-aturan | Dipakai utuh (satu lagi stack) | Sleep-time compute, April 2025 |
| **Karpathy LLM Wiki** | Referensi pola lapisan kurasi: agent mengompilasi sumber ke markdown saling-tertaut; `agents.md` sebagai kendali perilaku | Menggantikan loop konsolidasi (tidak punya bobot/status/lingkup) | Gist April 2026; rusak > ~200 berkas tanpa indeks per direktori |

### 10.3 Keputusan terbuka — mesin episodik

| Opsi | Kelebihan | Kekurangan | Syarat memilih |
|---|---|---|---|
| **A. MemPalace** | Verbatim, zero API call (aman tier I), temporal KG bawaan, wing/room = allowlist | Tidak ada konsolidasi (harus bangun Bab 7 — sudah rencana) | Bukti tidak pernah hilang, tidak ada data keluar mesin |
| **B. Mem0 (self-host)** | Ekosistem matang, OpenMemory MCP | Ekstraktif (bertentangan P1), butuh LLM saat tulis, berbahaya untuk norma | Integrasi cepat, episodik hanya tier P |
| **C. Bangun sendiri** | Kontrol penuh skema Bab 6 | Semua tahap ditulis sendiri | Bila A tidak bisa ganti backend (10.4-a) |

**Rekomendasi bersyarat (diperbarui setelah 10.4-a/c):** A untuk episodik — 10.4-a terverifikasi, jadi syaratnya terpenuhi. Mulai dengan backend in-tree `sqlite_exact` (tanpa dependensi tambahan, pencarian eksak, cukup untuk skala awal); TurboVec menjadi **optimasi fase 2**, bukan prasyarat. **Lapisan norma tetap di Obsidian** (frontmatter 6.3 + pencarian bitemporal di gateway); Graphiti **ditunda** — nilainya ada pada ekstraksi fakta dari percakapan, bukan pada graf suksesi peraturan yang hanya puluhan simpul, dan ia menambah kewajiban LLM saat ingest serta pertanyaan lisensi SSPL untuk backend embedded-nya.

### 10.4 Titik yang BELUM DIVERIFIKASI

| # | Klaim | Cara verifikasi | Dampak bila salah |
|---|---|---|---|
| a | Backend MemPalace "pluggable" sehingga ChromaDB bisa diganti TurboVec | Baca kode repo resmi via GitHits | Opsi A kehilangan indeks dingin; jatuh ke C |
| **a — HASIL** | **TERVERIFIKASI, dengan biaya.** Kontrak RFC 001 formal (`mempalace/backends/base.py`): `add/upsert/query/get/delete/count` wajib, `where` metadata (dialek Chroma: `$and/$or`, dll.) **wajib dihormati** — operator yang tak didukung harus melempar `UnsupportedFilterError`, tidak boleh diabaikan diam-diam. Backend pihak ketiga = paket pip dengan entry point `mempalace.backends` (`registry.py`); wajib lolos `tests/_backend_conformance.py`. TurboVec **bukan drop-in** (hanya allowlist ID), tetapi jalurnya jelas: **backend hibrida** = fork `sqlite_exact` (SQLite menyimpan dokumen + metadata, `where` dievaluasi di SQLite/Python → daftar ID) + `IdMapIndex.search(allowlist=...)` TurboVec menggantikan pemeringkatan cosine numpy. Deklarasikan `distance_metric = "ip"` dengan vektor ternormalisasi (kontrak mengizinkan `cosine`/`l2`/`ip`). Perkiraan kerja: satu berkas backend + tes konformansi. Catatan: docstring RFC menyebut sebagian mekanisme (embedder injection, maintenance) masih menyusul di PR lanjutan — antarmuka `spec_version 1.0` bisa bergeser. | — |
| b | Mem0 bisa memakai `TurboVecStore` lewat adapter LangChain | Baca daftar vector store Mem0 | Hanya relevan bila B |
| c | Graphiti bisa jalan self-host dengan beban wajar di VPS KVM 1 (Neo4j/FalkorDB) dan lisensinya kompatibel dengan rencana AGPL | Baca README + docs; ukur memori kontainer | Norma tetap di Obsidian + gateway |
| **c — HASIL** | **TERVERIFIKASI SEBAGIAN — layak dengan tiga syarat.** (1) Lisensi Graphiti **Apache-2.0** → kompatibel untuk dimasukkan ke proyek AGPL. (2) Infra: Neo4j 5.26 adalah server JVM terpisah (GPLv3) — berat untuk KVM 1 yang sudah memikul PostgreSQL 16 + Node + Caddy (angka RAM aktual VPS **belum diukur** di sesi ini; konektor Hostinger tidak termuat). Alternatif ringan: `graphiti-core[falkordblite]` = FalkorDB embedded dalam proses Python (butuh Python ≥3.12 — Ubuntu 24.04 memenuhi; pin `redis<9`). Kuzu deprecated. (3) **FalkorDB berlisensi SSPL v1** (bukan OSI open source): aman untuk pemakaian internal; untuk rilis AGPL publik jangan dibundel — jadikan dependensi opsional yang dipasang pengguna; bila Dashboard Cakti kelak ditawarkan sebagai layanan hosted ke pihak ketiga, kewajiban SSPL §13 perlu tinjauan hukum (saya bukan pengacara). (4) Ingest Graphiti **wajib LLM dengan structured output** dan README memperingatkan model kecil rawan gagal skema → untuk episode tier I hanya boleh lewat endpoint privat yang mendukung structured output dengan baik; model lokal kecil berisiko. **Belum diverifikasi:** apakah tipe entitas/edge kustom Graphiti cukup untuk membawa atribut `status` (`dicabut`/`ditarik`). Ukur memori kontainer tetap PARKIR sampai ada keputusan memakai Graphiti. | Norma tetap di Obsidian + gateway (kini menjadi rekomendasi, bukan fallback) |

---

## 11. Metrik dan alarm

| Metrik | Diukur | Alarm |
|---|---|---|
| Rasio token memori / total konteks per sesi | Setiap sesi | > 15 % |
| Jumlah pelajaran `aturan` per lingkup | Harian | Naik > 20 % seminggu tanpa instrumen baru → curiga abstraksi terlalu rendah (P8) |
| Tingkat `kontra` per pelajaran | Setiap job | `kontra ≥ bukti` → wajib `dipersempit`/`ditarik` |
| Jumlah panggilan `ingat()` per sesi | Setiap sesi | > 10 → L-aturan tidak memuat yang tepat |
| Episode aktif belum dikonsolidasi | Harian | > 200 → job tidak jalan |
| Item di `_usulan/` belum ditinjau | Mingguan | > 20 → manusia bottleneck; tinjau ambang 7.2 |
| Item `tinjau_ulang: true` | Mingguan | > 15 → lingkungan/instrumen berubah cepat; tinjau `tinjau_setelah` |
| Jawaban berbendera `belum_ditinjau` yang kemudian dikoreksi | Setiap koreksi | Rasio > 30 % → hipotesis terlalu mudah masuk retrieval; naikkan ambang keyakinan |
| Prosedur `uji` gagal | Setiap eksekusi | 2× berturut → `tinjau_ulang`; 3× → `ditarik` |
| Sesi tanpa episode (encoding failure — Schacter: absentmindedness) | Setiap akhir sesi | 3 sesi berturut 0 episode → hook tidak jalan / cakupan tangkap bocor |

---

## 12. Uji penerimaan — putar-ulang (R7)

Benchmark publik (LongMemEval, LoCoMo) mengukur *recall*. Yang kita butuhkan: **apakah kesalahan yang sama terulang.** Metode: beri sistem semua episode *sebelum* tanggal kesalahan, lalu ajukan situasi yang memicu kesalahan itu. Lulus bila gateway mengembalikan item (aturan, usulan berbendera, atau prosedur) yang `pemicu`/`tugas_pemicu`-nya menyala **sebelum** tindakan salah diambil.

| # | Kasus nyata (tanggal diisi dari riwayat chat) | Situasi pemicu uji | Kriteria lulus |
|---|---|---|---|
| U1 | Titik buta Hostinger: `VPS_getProjectListV1` kosong disimpulkan sebagai "tidak ada beban kerja" | Sesi baru: satu tool mengembalikan kosong, agent hendak menyimpulkan ketiadaan | Pelajaran "ketiadaan hasil ≠ ketiadaan objek" menyala di L-aturan atau L-tarik |
| U2 | `jelajah.mjs` dilaporkan selesai, ternyata tak pernah sampai ke disk `C:\Users\Hi\Downloads\` | Agent hendak melaporkan "selesai" untuk berkas yang belum diverifikasi ada di disk | Prosedur "verifikasi keberadaan berkas sebelum klaim selesai" cocok tugas |
| U3 | DaisyUI 5 dicoba di halaman yang masih memakai CDN Tailwind v3 | Agent hendak mengintegrasikan pustaka ke halaman | Pelajaran "cek prasyarat versi sebelum integrasi" menyala dengan `berlaku_untuk` yang tepat |
| U4 | `npm ci` di repo dengan `jaga.mjs` memblokir `postinstall` Playwright | Tugas: pasang dependensi di repo fp-dashboard | Prosedur 6.5 (`--ignore-scripts` + install Chromium terpisah) cocok tugas dalam lingkup `proyek:fp-dashboard` |
| U5 | Metrik `follows` Instagram selalu nol via Graph API dianggap sinyal konversi | Analisis metrik akun; agent hendak menafsirkan `follows` | Pelajaran menyala **hanya** dalam lingkup `proyek:garnivo`/`peran:sosmed` — dan **tidak** menyala di lingkup fp-dashboard (uji P9 negatif) |

Uji tambahan:
- **U6 (norma bitemporal):** query "aturan pengadaan yang berlaku untuk kontrak ditandatangani <tanggal sebelum Perpres 46/2025 berlaku>" → mengembalikan versi lama sebagai otoritatif + `peralihan`; query tanpa tanggal → versi terkini + `asumsi[]` menyebut asumsi hari ini.
- **U7 (anti-Spalko):** sesi dengan ≥ 1.000 episode dingin dan 50 pelajaran aktif → rasio token memori ≤ 15 %, tidak ada isi episode di L-aturan.
- **U8 (fobia):** satu koreksi di lingkup `proyek:garnivo` → item muncul sebagai `usulan` di lingkup itu, **tidak** muncul di lingkup lain sebelum bukti kedua independen.
- **U9 (ditarik):** pelajaran yang di-`ditarik` → tidak pernah muncul sebagai jawaban; muncul sebagai peringatan saat query menyerempet domainnya.

Kelima kasus U1–U5 diambil dari riwayat nyata proyek ini. Sebelum implementasi, tanggal dan episode sumbernya dilengkapi dari riwayat chat — bukan direkonstruksi dari ingatan.

---

## 13. Status dan langkah berikut

**PARKIR — yang kurang sebelum implementasi:**
1. ~~Verifikasi 10.4-a dan 10.4-c~~ — **selesai 6 Sep 2026** (hasil di 10.4). Tersisa: 10.4-b hanya bila B; pengukuran RAM VPS hanya bila Graphiti dipakai.
2. Keputusan A/B/C.
3. ~~Pemetaan tier P/I/S untuk episode~~ — **selesai (K10, K11):** default I untuk Claude Code; naik ke S otomatis lewat pola `src/tangkap/tier.ts`; tidak pernah turun ke P otomatis.
4. Melengkapi tanggal dan episode sumber untuk U1–U5 dari riwayat chat.
5. Kalibrasi angka Bab 8.2 dan 7.5 setelah dua minggu metrik.

**LANJUT — urutan implementasi setelah keputusan:**
1. Skema Bab 6 sebagai frontmatter Obsidian + tabel SQLite (episode, instrumen); indeks `prosedur/` untuk rules/skill/hook yang sudah ada.
2. Gateway `ingat()` + `buka_bukti()` sebagai satu MCP server (Bab 8), termasuk filter `lingkup` dan bitemporal norma.
3. Harness uji putar-ulang U1–U9 (Bab 12) — **sebelum** job konsolidasi, supaya job diuji sejak hari pertama.
4. Job konsolidasi (Bab 7) sebagai skrip terjadwal; keluaran ke `_usulan/`.
5. Ingest norma: lima peraturan paling sering dirujuk (Perpres 46/2025, PMK 32/2025, dan tiga lainnya dari `vendor-tender-sp2d`) — kolom diisi dari dokumen JDIH.
6. Metrik Bab 11.

---

### 13b. Jalur data nyata (v0.4.3)

```
Claude Code ──hook──▶ tangkap.py ──▶ Store.tambah_episode (redaksi, tier) ──▶ SQLite
                                                                                │
      02:00 / ≥50 episode ──▶ konsolidasi (kelompokkan; hipotesis→usulan; pendinginan tertunda R8)
                                                                                │
      tanya ──▶ pelajaran/_usulan/tanya-<tgl>.md ──manusia──▶ jawab ──▶ vault ──sinkron──▶ Store
                                                                                │
      sesi berikutnya ──▶ muat_startup (L-peta + L-aturan) ──▶ ingat() (dua koleksi, anggaran) ──▶ konteks
```

Yang belum diverifikasi di sandbox: payload hook dari Claude Code versi terbaru (skema `tool_response` bisa berubah — `deteksi_gagal` bersifat heuristik dan permisif), dan Ollama hidup. Keduanya tugas pertama di mesin pemilik.

### 13c. Tiga jalur masuk MCP (ringkasan)

| Jalur | Transport | Klien | Auth |
|---|---|---|---|
| `ingat mcp` | stdio | Claude Code, Claude Desktop | proses lokal, tanpa token |
| `/mcp` (K19) | Streamable HTTP | claude.ai Custom Connector, klien remote lain | Bearer atau token-di-path |
| `/episode`, `/ingat`, dst. (K18) | REST biasa | ekstensi browser, dashboard, skrip | Bearer |

Ketiganya memanggil `Gateway`/`Store` yang sama — tidak ada logika kedua yang bisa berbeda perilaku.

## 14. Keputusan implementasi (v0.3)

Opsi **C — bangun dari nol** dipilih pada 6 September 2026 dengan tujuan open source dan bebas selamanya. Tiga belas keputusan (lisensi Apache-2.0, hak cipta pribadi + DCO, TypeScript sebagai implementasi rujukan di atas kontrak, SQLite via `node:sqlite`, Ollama + multilingual-e5-base 768-dim dibangun sendiri, konsolidasi v0 tanpa LLM, vault = repo git, simpan semua dengan redaksi kredensial, hook otomatis + koreksi manual, sumber v0 Claude Code, repo privat sampai siap) dicatat di `KEPUTUSAN.md` — sumber kebenaran untuk keputusan, sementara dokumen ini tetap sumber kebenaran untuk desain. Bila keduanya bertentangan, `KEPUTUSAN.md` menang dan dokumen ini yang harus direvisi.

Konsekuensi pada bab lain: 10.3 A/B/C ditutup (C); 10.4-b tidak relevan lagi; TurboVec dan Postgres = fase 2 di balik antarmuka `src/inti/cosinus.ts` dan `src/simpan/`.

---

## Lampiran A — Glosarium

| Istilah | Arti dalam dokumen ini |
|---|---|
| Episode | Kejadian mentah yang ditangkap otomatis |
| Pelajaran | Aturan *tahu-bahwa* hasil generalisasi; punya `pemicu`, `tindakan`, `bukti`, `kontra`, `lingkup` |
| Prosedur | Langkah *tahu-cara*; dicocokkan ke tugas, divalidasi dengan eksekusi |
| Norma | Ketentuan dari otoritas eksternal, berversi, bitemporal |
| Tampilan konsolidasi | Gabungan non-otoritatif dari beberapa versi norma untuk satu tanggal |
| Lingkup | Batas berlakunya pelajaran/prosedur: global, proyek, atau peran |
| Usulan | Hipotesis yang sudah mencapai ambang bukti dan menunggu tinjauan manusia |
| Bitemporal | Setiap fakta punya *kapan berlaku* dan *kapan dicatat* |
| Didinginkan | Episode dipindah ke penyimpanan terkompresi; tetap bisa dibuka lewat pointer |
| Instrumen | Tool/konektor yang menghasilkan observasi; punya cakupan dan titik buta |
| Kasus Spalko | Kewalahan konteks karena transfer tanpa mengukur kapasitas penerima |
| Putar-ulang | Uji penerimaan: episode sebelum kesalahan → apakah sistem mencegah kesalahan itu |
| Gate P/I/S | Klasifikasi data dari `spek-ai-hybrid.md` |

## Lampiran B — Rujukan

Bersumber (pencarian web, per September 2026):
- MemPalace — `github.com/mempalace/mempalace` (peringatan impostor di README)
- Mem0 — `github.com/mem0ai/mem0`; `mem0.ai/blog/introducing-openmemory-mcp`
- TencentDB Agent Memory — `github.com/TencentCloud/TencentDB-Agent-Memory`; MarkTechPost, 23 Mei 2026
- TurboVec — `github.com/RyanCodrai/turbovec`
- Obsidian MCP — `community.obsidian.md/plugins/mcp-server`; `docs.rs/crate/obsidian-mcp`
- Zep/Graphiti — arXiv 2501.13956; `neo4j.com/blog/developer/graphiti-knowledge-graph-memory/` (Juni 2026); `getzep.com/ai-agents/temporal-knowledge-graph/`
- Letta sleep-time compute — `letta.com/blog/sleep-time-compute/` (April 2025); `docs.letta.com/guides/agents/architectures/sleeptime/`; forum Letta, Januari 2026
- Karpathy LLM Wiki — gist April 2026; ulasan pemakaian 3 bulan di `kunalganglani.com/blog/llm-wiki-karpathy-local-knowledge-base`; plugin `github.com/green-dalii/obsidian-llm-wiki`

Dari referensi umum (belum diverifikasi ulang di sesi ini; karya mapan pra-2026):
- McClelland, McNaughton & O'Reilly (1995), *Psychological Review* — Complementary Learning Systems
- Kumaran, Hassabis & McClelland (2016), *Trends in Cognitive Sciences* — revisi CLS
- Laird, Rosenbloom & Newell (1980-an) — Soar, mekanisme *chunking*
- Anderson dkk. — ACT-R, *base-level activation* yang meluruh
- Sumers dkk. (2023) — CoALA, taksonomi memori episodik/semantik/prosedural untuk agent LLM
- Park dkk. (2023) — Generative Agents, *reflection* dan skor *importance*
- Shinn dkk. (2023) — Reflexion; Zhao dkk. (2023) — ExpeL
- Zhong dkk. (2023) — MemoryBank, kurva lupa Ebbinghaus
- Behrouz dkk. (2025) — Titans, metrik *surprise*

Penalaran desain (tidak bersumber): Bab 2, 3, 5, 6, 7, 8, 9, 11, 12 seluruhnya.

## Lampiran C — Prior art: apa yang dipinjam dari mana

| Ide dalam spek ini | Sudah ada di | Yang kita tambahkan |
|---|---|---|
| Episodik / semantik / prosedural sebagai jenis terpisah | Soar, ACT-R; CoALA (2023) | Jenis keempat: **norma** dengan bitemporalitas hukum |
| Episode → aturan (konsolidasi) | Soar *chunking*; Generative Agents *reflection*; Reflexion; ExpeL | Ambang berbobot per `jenis_kejadian`; kunci `lingkup` pada koreksi tunggal |
| Konsolidasi saat "tidur", agent utama tanpa alat edit memori | Letta sleep-time compute (2025) | Keluaran ke `_usulan/` dengan veto manusia; job hanya di endpoint sesuai tier |
| Bobot dari kejutan/kesalahan | Titans (*surprise*); Generative Agents (*importance*) | Koreksi manusia > kegagalan > pola > sukses, dengan angka |
| Memudar / peluruhan | MemoryBank (Ebbinghaus); ACT-R | `tinjau_setelah` + `berlaku_untuk` — kedaluwarsa tanpa kontra |
| Fakta bitemporal, invalidasi tanpa buang, query titik-waktu | Zep/Graphiti | Empat jalur keluar: `dipersempit` / `dicabut` / `ditarik` / `abadi`; `peralihan` sebagai kolom kelas satu; tampilan konsolidasi non-otoritatif |
| Piramida L0–L3, offloading, traceback `node_id`, Skill, ACL | TencentDB Agent Memory (2026) | `lingkup` sebagai atribut item (bukan hanya ACL akses); gate retensi P/I/S |
| Obsidian sebagai rumah yang dikompilasi agent; indeks per direktori | Karpathy LLM Wiki (2026) | Status/bobot/lingkup per catatan; `_usulan/` sebagai antrean tinjau |
| Anggaran konteks eksplisit | Letta memory blocks; TencentDB cap item/karakter/timeout; MemPalace startup 170 token | Lapisan L-peta/L-aturan/L-tarik/L-bukti dengan angka dan sinyal "cukup" |
| Simpan verbatim, jangan ekstraksi | MemPalace (2026) | Dipakai sebagai substrat L0 saja; konsolidasi tetap ada di atasnya |

**Yang tidak ditemukan di pencarian sesi ini:** kombinasi norma bitemporal *dengan ketentuan peralihan* + pembedaan `dicabut`/`ditarik` + gate retensi P/I/S. Absennya di pencarian bukan bukti tidak ada; tetapi ini kandidat kontribusi orisinal, dan ia orisinal *karena* domain pengadaan pemerintah.

## Lampiran E — Landasan kognitif & neurosains (v0.4.0)

Sumber: *Psychology 2e* (OpenStax, CC BY-NC-SA 4.0) Bab 6–8; *Open Neuroscience Initiative* (Lim, DePaul 2021, CC BY-NC 4.0) Bab 13; *Foundations of Neuroscience* (Henley 2021, CC BY-NC-SA 4.0) Bab 20–25. Ketiganya berlisensi non-komersial: dokumen ini **memparafrase dan merujuk**, tidak mengutip teks ke dalam repo Apache-2.0. Tautan Pressbooks Atlantic Canada yang diberikan adalah halaman katalog jaringan, bukan buku — tidak ada isi yang bisa dianalisis darinya.

Satu prinsip yang mengikat semua temuan di bawah: **otak bukan perekam video — ingatan direkonstruksi tiap kali dipanggil, dan setiap rekonstruksi adalah peluang salah** (Psychology 2e 8.2–8.3). `ingat` sengaja *lebih baik* dari otak di satu titik: rekamannya (episode verbatim, K10) tidak pernah dibuang, dan rekonstruksinya (pelajaran) selalu membawa pointer ke rekaman. Tabel ini memetakan temuan ke desain: **V** = memvalidasi yang sudah ada, **R** = merevisi, **K** = kandidat.

| Temuan (sumber) | Padanan di `ingat` | Status |
|---|---|---|
| Tiga fungsi: encode → store → retrieve; pengkodean *effortful* menghasilkan ingatan lebih kuat daripada otomatis (P2e 8.1) | tangkap (otomatis, hook) vs tanya (effortful, manusia) | **V** K11, K15 |
| Levels of processing: pemrosesan semantik > visual/akustik; self-reference effect (Craik & Tulving 1975; Rogers dkk. 1977) | pelajaran ditulis manusia dengan kata sendiri > draf mesin; keyakinan 0.8 vs 0.7 | **R9** (7.7) |
| Kapasitas memori kerja 4 ± 1 chunk (Cowan 2010), bukan 7 ± 2 | `maks_item` 5 per panggilan; L-aturan disusun sebagai chunk per lingkup/jenis | **V** 8.2 |
| Jaringan semantik + aktivasi menyebar; recall berisyarat ≫ bebas (P2e 8.1; ONI 13.2) | L-peta sebagai isyarat; dua vektor per pelajaran (`pemicu` vs isi) | **R12** (8.2b) |
| Episodik = apa/di mana/kapan (Tulving 2002); prosedural bertahan tanpa hipokampus (H.M., serebelum/striatum) | Episode punya `waktu`/`lingkup`/`instrumen`; Prosedur = jenis terpisah | **V** R1, 6.1 |
| Konsolidasi sinaptik (jam) vs sistem (minggu–tahun), terjadi saat tidur; deklaratif di non-REM, prosedural di REM (P2e 8.1; ONI 13.2) | Jalur cepat akhir sesi vs batch 02:00; pelajaran vs prosedur dikonsolidasi terpisah | **V** 7.1, 7.6 |
| Amnesia retrograd bertahap: jejak baru bergantung hipokampus berbulan-bulan (H.M.) | Episode tidak langsung didinginkan | **R8** (7.3b) |
| Retrieval = rekonsolidasi; aspek ditekankan/hilang → ingatan palsu (ONI 13.2) | Pembacaan (`ingat()`) read-only; satu-satunya jendela modifikasi = `jawab` | **V** — dinyatakan eksplisit di 7.7 |
| Efek misinformasi & sugestibilitas; *blind lineup* (Loftus & Palmer 1974; Wells & Quinlivan 2009) | Draf mesin setelah blok jawab; template kosong; `premis-salah` | **R9** (7.7) |
| Flashbulb memory: sangat jelas tetapi tidak lebih akurat (Brown & Kulik 1977; Hirst & Phelps 2016); arousal theory | Bobot koreksi 5 = *prioritas pengkodean*, bukan kebenaran; koreksi tunggal terkunci di lingkup | **V** 7.2, R2 |
| Kurva lupa Ebbinghaus; distributed practice > cramming; metode kartu indeks (P2e 8.3–8.4) | Interval tinjau melebar 2× per konfirmasi, 90..365 hari | **R10** (7.7) |
| Interferensi proaktif (lama menghalangi baru) & retroaktif (baru menimpa lama) (P2e 8.3) | `dipersempit` untuk proaktif; norma berversi untuk retroaktif; MMR untuk nyaris-duplikat | **V** 5, 6.3, 8.1 |
| Tujuh dosa Schacter: transience, absentmindedness, blocking, misattribution, suggestibility, bias, persistence | transience → `tinjau_setelah`; absentmindedness → alarm "0 episode/sesi" (encoding failure); blocking → `pointer[]`; misattribution → `bukti` + `sintesis`; suggestibility → R9; bias hindsight → keyakinan pelajaran manusia dibatasi 0.8 sampai dikonfirmasi episode *berikutnya*; persistence → item `ditarik` hanya muncul sebagai peringatan | **V** + 1 metrik baru (Bab 11) |
| Akuisisi–ekstingsi–pemulihan spontan; generalisasi vs diskriminasi stimulus; Little Albert (P2e 6.2) | `ditarik` = ekstingsi (asosiasi tidak dihapus, hanya dihambat); `global` vs `dipersempit`; fobia = R2 | **V** 5.1, 7.2 · **K** pemulihan `ditarik → hipotesis` (manusia) |
| Latent learning & peta kognitif (Tolman); place cells & grid cells multi-skala (P2e 6.3; ONI 13.2) | Simpan verbatim tanpa kegunaan langsung (K10); `lingkup` sebagai peta; hierarki lingkup multi-skala | **V** K10 · **K** hierarki lingkup |
| Hebb: yang menyala bersama saling menguat, dan kebalikannya; LTP/LTD; reverberasi (ONI 13.3) | `bukti` ↑ keyakinan (LTP); tanpa konfirmasi → keyakinan efektif turun (LTD); job = reverberasi | **V** 7.3, 7.5 |
| Plastisitas kortikal: representasi meluas dengan latihan, dipetakan ulang saat masukan hilang (Merzenich 1984, FoN 25) | Instrumen baru → gelombang tinjau; instrumen dicabut → tinjau_ulang + persempit prosedur | **V** 7.4 · **R11** |
| Inhibisi lateral menajamkan tepi dengan menekan tetangga (FoN 20, 25) | Dedup MMR: kandidat mirip saling menekan supaya yang berbeda muncul | **V** 8.1 |
| Sel konsep ("Jennifer Aniston neuron") menyala lintas modalitas untuk satu konsep (ONI 13.2) | P8: pemicu ditulis sebagai konsep/kondisi, bukan permukaan kalimat | **V** P8, R12 |
| Skema & prototipe menyusun konsep; bias mengarahkan rekonstruksi (P2e 7.1, 8.3) | Pelajaran = prototipe kelompok episode; `premis-salah` menangkap skema yang salah | **V** 7.7 |

**Perubahan yang diadopsi (v0.4.0):** R8 (7.3b), R9 dan R10 (7.7, sudah diimplementasikan di `ingat/tanya.py` dengan uji), R11 (7.4), R12 (8.2b). **Metrik baru** (Bab 11): "sesi tanpa episode" — encoding failure; alarm bila sesi Claude Code berakhir dengan 0 episode selama 3 sesi berturut. **Kandidat kontrak v3:** (1) transisi pemulihan `pelajaran ditarik → hipotesis` oleh manusia (ekstingsi bukan penghapusan); (2) `instrumen.dicabut_sejak`; (3) hierarki lingkup (`proyek:x/peran:y`) sebagai peta multi-skala; (4) tabel `sesi` untuk U7.

**Yang sengaja tidak diadopsi:** mnemonik/akronim, expressive writing, olahraga — teknik manusia yang tidak punya padanan mesin; dan hipertimesia sebagai tujuan — mengingat segalanya tanpa konsolidasi adalah persis "simpan semua, suntik semua" yang ditolak Bab 8.

## Lampiran D — Riwayat versi

| Versi | Tanggal | Perubahan |
|---|---|---|
| 0.1 | 2026-09-06 | Kristalisasi awal: tiga jenis, state machine, skema, loop, anti-Spalko, P/I/S, pemetaan lima sistem |
| 0.2 | 2026-09-06 | R1–R7 hasil analisis kesalahan/kekurangan; Zep/Graphiti, Letta, Karpathy LLM Wiki; uji putar-ulang; Lampiran C |
| 0.2.1 | 2026-09-06 | Verifikasi kode 10.4-a (MemPalace pluggable: ya, jalur backend hibrida) dan 10.4-c (Graphiti Apache-2.0; FalkorDB embedded tersedia tapi SSPL; ingest wajib LLM). Rekomendasi 10.3 diperbarui: `sqlite_exact` dulu, TurboVec fase 2, norma tetap di Obsidian, Graphiti ditunda |
| 0.5.4 | 2026-09-08 | K27: `ingat pasang` dipindah sebelum pembuatan Aplikasi — tidak lagi membuat ./data/ingat.sqlite kosong sebagai efek samping; ditemukan lewat instalasi nyata pengguna |
| 0.5.3 | 2026-09-08 | K26: auth_totp.py (RFC 6238, diverifikasi vektor resmi), rute /auth/totp/masuk + pembatas laju ketat, CLI totp-atur, opsi dashboard ketiga; 13 uji |
| 0.5.2 | 2026-09-08 | K25: auth_google.py, rute /auth/*, dashboard.html dua jalur (cookie/token), instal-vps.sh, README-google-auth.md; 17 uji |
| 0.5.1 | 2026-09-08 | K24: pembersihan atribusi menyeluruh; kepemilikan tunggal Fadelli Polosoro |
| 0.5.0 | 2026-09-08 | K23: dashboard.py (edge terstruktur), static/dashboard.html (registri/konten/papan bukti tiga panel), endpoint /dashboard (publik) + /dashboard/data (token); 9 uji |
| 0.4.9 | 2026-09-08 | K22: auto-mulai (deteksi percakapan kosong, sekali per tab, toggle di Opsi); 2 uji baru |
| 0.4.8 | 2026-09-08 | K21: badge relevansi (ambang 0.30) + tombol Suntik lagi (eskalasi anggaran_token, idTerkirim anti-duplikat); 3 uji baru |
| 0.4.7 | 2026-09-08 | K20: tombol suntik memori (background.js `mintaSuntik`, content.js `tulisKeKotak`), selektor `compose` di 9 situs, 8 uji baru termasuk pemeriksaan sintaks JS dan jaminan anti-submit |
| 0.4.6 | 2026-09-08 | K19: mcp_http.py (Streamable HTTP 2025-06-18, mode JSON, tanpa OAuth — dicatat sebagai batas); refactor tangani_pesan dipakai stdio+HTTP; fix kebocoran token-di-path ke log server (ditemukan sebelum rilis); 8 uji baru |
| 0.4.5 | 2026-09-07 | K18: ekstensi Chrome tangkap percakapan (Jalur B) — content/background script, pemilih elemen untuk situs tanpa selektor terverifikasi, /koreksi lintas platform; 8 uji baru untuk api.py (sebelumnya nol) |
| 0.4.4 | 2026-09-07 | K17: preset Gemini (openai-compat resmi Google); fix izin SQLite Python 0600/0700; 13 uji baru untuk gate.py+penyedia.py (sebelumnya nol uji); README bagian Konektor & Keamanan |
| 0.4.3 | 2026-09-07 | K11: hook Claude Code (`tangkap.py`, 5 peristiwa, anti-banjir satu episode/sesi, `/koreksi`), pemasangan idempoten (`pasang.py`), `tambah_episode` menerima `id` untuk upsert episode sesi; 12 uji |
| 0.4.2 | 2026-09-07 | SELARAS tiket 2–4 selesai: Store Python menulis `versi_kontrak='2'`, tabel `vektor` (koleksi `isi`/`pemicu` — R12 aktif di gateway), `identitas_embedder` ditegakkan, AUTOINCREMENT dilepas, `transisi_status` diisi dari kode; uji migrasi DB lama, subset kontrak, dan interop TS↔Python |
| 0.4.1 | 2026-09-07 | R8 diimplementasikan: pendinginan tertunda, idempotensi run ulang, draf prosedur tanpa duplikat (5 uji) |
| 0.4.0 | 2026-09-07 | Lampiran E landasan kognitif & neurosains (P2e Bab 6–8, ONI Bab 13, FoN Bab 20–25); R8 episode tidak langsung didinginkan; R9 anti-sugesti + keyakinan 0.8/0.7; R10 interval tinjau melebar; R11 instrumen dicabut; R12 isyarat sebelum isi + dua vektor per pelajaran; metrik encoding failure; 4 kandidat kontrak v3 |
| 0.3.3 | 2026-09-07 | Bab 7.7 konsolidasi berpandu pertanyaan (K15): `ingat/tanya.py`, CLI `tanya`/`jawab`, `uji_tanya.py` |
| 0.3.2 | 2026-09-07 | Kontrak v2 (K14) + migrasi 002 + arsip v1 + `uji_migrasi.py`; port TS: tipe `Prosedur`, `Norma`, `normaBerlakuPada` |
| 0.3.1 | 2026-09-06 | K3 direvisi: implementasi Python milik pemilik (gateway, konsolidasi, MCP, API, CLI, vault) menjadi rujukan; TS = port. K10 dipasang di Python (redaksi, tier S tersimpan dengan pagar `sertakan_S`), K5 (`PenyematOllama`). Kontrak v1 mengadopsi transisi pemulihan dari Python; norma dicabut/dibatalkan dikunci ke manusia. `SELARAS.md` mencatat selisih skema + tiket penyelarasan |
| 0.3 | 2026-09-06 | Keputusan bangun dari nol (opsi C, open source Apache-2.0). 13 keputusan implementasi K1–K13 di `KEPUTUSAN.md`. P2 ditulis ulang (K10). Bab 9 tier S direvisi. Kerangka repo `ingat`: skema SQL (kontrak v1), inti (status, anggaran, cosinus), simpan (frontmatter subset-YAML, node:sqlite), sematkan (antarmuka, identitas, Ollama), tangkap (redaksi, tier), fixture U1, 26 uji hijau, 2 todo (gateway irisan 1) |
