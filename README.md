# ingat

Sistem memori untuk agent AI yang bisa **diperiksa manusia**: empat jenis pengetahuan
(episode, pelajaran, prosedur, norma), satu state machine status, satu pintu retrieval dengan
anggaran konteks eksplisit, dan lapisan kurasi berupa berkas markdown biasa (vault catatan Markdown atau
editor apa pun).

Bukan framework. Produknya adalah **kontrak**: `skema/ingat.sql`, format frontmatter, protokol tool
MCP. Repo ini memuat **implementasi rujukan Python** (`ingat/`, stdlib saja) dan **port TypeScript**
(`port/typescript/`, inti + kontrak). Port dalam bahasa lain dipersilakan membaca database dan
berkas yang sama — lihat `SELARAS.md` untuk status kesesuaian skema.

Status: **pra-rilis, privat** (K13). Keputusan terkunci: `KEPUTUSAN.md`. Desain: `docs/spek-arsitektur-memori.md`.

## Prasyarat

- Python ≥ 3.11 (tanpa dependensi; PyYAML opsional untuk frontmatter penuh).
- Ollama + model `ingat-e5-base` yang dibangun sendiri (`model/README.md`) — atau `embedding.jenis = "lokal"` untuk uji.
- Port TS: Node 22.x ≥ 22.13 (`node:sqlite`).

## Menjalankan

```
cp konfigurasi.contoh.json konfigurasi.json     # atur dir_data, vault, embedding, gate
python3 -m unittest discover -s uji -p "uji_*.py" -t .
python3 -m ingat --konfig konfigurasi.json sinkron    # vault → store
python3 -m ingat --konfig konfigurasi.json konsolidasi # job "tidur": kelompokkan episode → hipotesis/usulan
python3 -m ingat --konfig konfigurasi.json tanya       # mesin BERTANYA dari data → pelajaran/_usulan/tanya-<tgl>.md
python3 -m ingat --konfig konfigurasi.json jawab --berkas vault/pelajaran/_usulan/tanya-<tgl>.md
python3 -m ingat --konfig konfigurasi.json mcp        # server MCP stdio untuk Claude Code
docker compose up -d --build                          # VPS: API HTTP + jadwal konsolidasi
cd port/typescript && npm test                        # port TS
```

## Mulai dalam 10 menit (data nyata pertama)

```
pip install -e .                                   # supaya hook bisa `python3 -m ingat.tangkap`
python3 -m ingat pasang                            # cetak rencana; tidak menyentuh berkas
python3 -m ingat pasang --tulis                    # ~/.ingat/konfigurasi.json, hook di ~/.claude/settings.json, /koreksi, MCP
bash model/bangun-gguf.sh && ollama create ingat-e5-base -f model/Modelfile   # atau embedding.jenis = "lokal" untuk uji
```

Lalu buka sesi Claude Code di repo mana pun. Hook mencatat: setiap tool gagal → episode `kegagalan`; tiap sesi → **satu** episode
`sukses` berisi `langkah` (bukan satu per tool — anti-banjir); prompt `/koreksi <apa yang salah>` → episode `koreksi` bobot 5.
Lingkup = `proyek:<nama folder>` (ubah lewat berkas `.ingat-lingkup` atau env `INGAT_LINGKUP`). Hook tidak pernah memblokir Claude.

Setelah seminggu:

```
python3 -m ingat --konfig ~/.ingat/konfigurasi.json metrik        # episode_aktif > 0?
python3 -m ingat --konfig ~/.ingat/konfigurasi.json konsolidasi
python3 -m ingat --konfig ~/.ingat/konfigurasi.json tanya         # mesin bertanya → jawab di vault catatan → `jawab --berkas …`
```

## Tata letak

```
ingat/                 implementasi rujukan Python: skema, simpan, gateway, konsolidasi, tanya, tangkap (hook), pasang, vault, mcp_stdio, api, cli, redaksi, vektor, gate
pasang/                templat hook Claude Code, ekstensi Chrome (tangkap ChatGPT/Claude/Gemini/dst), .mcp.json
skema/ingat.sql        kontrak penyimpanan (SQL portabel) — target penyelarasan
uji/                   uji_putar_ulang (U1–U12), uji_tanya, uji_redaksi, uji_penyemat_ollama, uji_kontrak, uji_migrasi; fixture putar-ulang/
port/typescript/       port TS: inti (status, anggaran, cosinus), simpan, sematkan, tangkap; 27 uji
model/                 Modelfile + skrip konversi GGUF (K9)
vault-contoh/          contoh struktur vault
docs/                  spesifikasi arsitektur v0.3.1
SELARAS.md             selisih skema Python vs kontrak + tiket penyelarasan
```

## Ringkasan tiga tingkat otomatisasi baca-memori

| Platform | Tulis (tangkap) | Baca (pakai memori) |
|---|---|---|
| Claude Code | otomatis (hook, K11) | **otomatis penuh** (hook `SessionStart`) |
| ChatGPT / Gemini / DeepSeek / Kimi / Perplexity | ekstensi browser (K18) | **otomatis sekali di percakapan baru** (K22); klik/badge untuk sisanya (K20/K21) |
| Claude.ai / Claude Desktop | ekstensi browser (K18) | connector MCP (K19), toggle per-percakapan — **satu-satunya yang masih manual**, dikendalikan Anthropic bukan `ingat` |

## Instalasi di VPS baru (dari nol)

```
scp ingat.zip root@<IP-VPS>:/root/          # dari PowerShell laptop
ssh root@<IP-VPS>
bash instal-vps.sh                          # idempoten, aman dijalankan ulang
```
Lima langkah tersisa yang tidak bisa diotomasi dicetak di akhir skrip: arahkan domain/sslip.io, Caddy,
Google Cloud Console (`pasang/README-google-auth.md`), isi `allowed_emails`, pasang koneksi laptop.

## Masuk ke dashboard: tiga jalur independen

1. **Google Auth** — perlu domain+HTTPS+OAuth Client ID (`pasang/README-google-auth.md`).
2. **Verifikasi dua langkah mandiri (TOTP)** — TIDAK bergantung Google sama sekali; jalur cadangan
   kalau OAuth jadi kendala. Atur sekali: `python3 -m ingat totp-atur --tulis-env`, lalu scan/tempel
   rahasia ke aplikasi authenticator apa pun (Google Authenticator, Authy, Bitwarden, dll. — standar
   terbuka RFC 6238, bukan terikat satu vendor).
3. **Token** — `INGAT_TOKEN`, selalu tersedia sebagai jalur paling sederhana.

Ketiganya independen; matikan yang mana pun tanpa memengaruhi yang lain.



## Dashboard visual — Papan Bukti

`http://<host>/dashboard` — tiga panel: **Registri** (daftar norma/pelajaran/prosedur/instrumen),
**Isi Catatan** (detail item terpilih), **Papan Bukti** (graf force-directed: node bisa diseret kursor,
tautan dihitung dari relasi struktural sungguhan — bukti episode yang sama, norma yang saling
menggantikan, instrumen yang melahirkan pelajaran — bukan wikilink generik). SVG + simulasi gaya
ditulis sendiri, nol dependensi JS. Buka halamannya, masukkan host+token sekali (tersimpan di
localStorage browser itu saja).

## Custom Connector claude.ai (MCP Streamable HTTP)

`ingat` bisa dipasang sebagai connector di claude.ai — sejajar dengan connector lain di menu **Settings →
Connectors → Add connector → Remote**. Endpoint: `https://<domain-kamu>/mcp/<INGAT_TOKEN>`. Langkah
lengkap + cara verifikasi dengan curl sebelum mencoba di claude.ai: `pasang/README-connector.md`.
**Belum ada OAuth** — token statis di URL, diperlakukan seperti kata sandi. Empat tool yang sama dengan
Claude Code (`ingat`, `muat_startup`, `buka_bukti`, `catat_episode`).

## Tangkap dari browser (ChatGPT, Claude.ai, Gemini, DeepSeek, Kimi, Perplexity)

Ekstensi Chrome di `pasang/browser-extension/` (pasang manual, lihat README di folder itu). Menangkap
percakapanmu jadi episode lewat endpoint `/episode` yang sama dipakai hook Claude Code — satu episode
per percakapan, `/koreksi` bobot 5 lintas platform. **Selektor ChatGPT** pola umum, verifikasi sendiri;
**Claude.ai/Gemini/DeepSeek/Kimi/Perplexity kosong** — isi lewat "Pilih elemen" di halaman nyata (klik balon pesan),
karena DOM situs itu tidak bisa diverifikasi dari lingkungan penulisan kode.

## Konektor penyedia LLM

`ingat/penyedia.py` — dipakai **hanya** untuk satu hal: menyintesis draf pelajaran saat `konsolidasi` (opsional;
default sistem tanpa LLM sama sekali, K6). Bukan chat interface, bukan pengganti Dashboard Cakti/E19.

| Penyedia | Protokol | Env var |
|---|---|---|
| Claude | Anthropic Messages API | `ANTHROPIC_API_KEY` |
| ChatGPT/OpenAI | OpenAI-compatible | `OPENAI_API_KEY` |
| Gemini | Lapisan kompatibilitas OpenAI resmi Google (`/v1beta/openai/`) | `GEMINI_API_KEY` |
| DeepSeek | OpenAI-compatible | `DEEPSEEK_API_KEY` |
| Kimi (Moonshot) | OpenAI-compatible | `MOONSHOT_API_KEY` |
| Perplexity, Grok, GLM, Nemotron, lokal (Ollama/vLLM) | OpenAI-compatible | lihat `.env.contoh` |

Aktifkan di `konfigurasi.json` → `penyedia.<id>.aktif = true` **dan** isi env var-nya — dua syarat, bukan salah satu.
Tanpa keduanya, penyedia dilewati diam-diam (bukan galat) dan konsolidasi jatuh ke heuristik. Gate P/I/S (Bab 9) tetap
menyaring di atas ini: tier S tidak pernah dikirim ke penyedia mana pun, dipaksa di kode (`Gate.izin("S")` selalu `[]`).

## Keamanan dan ukuran (ringkas; detail di `docs/spek-arsitektur-memori.md` Bab 9 dan `KEPUTUSAN.md`)

- Tanpa dependensi runtime (Python stdlib; TS `node:sqlite`) — permukaan serangan rantai pasok minimal.
- Berkas SQLite dan folder penyimpanan dingin dibuat dengan izin `0600`/`0700` (hanya pemilik).
- Kredensial diredaksi sebelum tulis; tier S tersimpan tapi tidak pernah keluar mesin/ke LLM (K10).
- API HTTP (opsional, untuk multi-perangkat): token wajib ≥24 karakter dari env (tanpa default), perbandingan
  timing-safe, rate limit per IP, `X-Forwarded-For` hanya dipercaya di belakang proxy tepercaya, TLS via Caddy.
- Docker: non-root, `read_only`, `cap_drop: ALL`, `no-new-privileges`, bind ke `127.0.0.1` saja.
- **Belum diaudit pihak ketiga.** Rate limiter in-memory per proses (reset saat restart, tidak terdistribusi).
  Vault catatan yang disinkron lewat git: jangan push ke remote publik — episode tier S ada di dalamnya.
- Retrieval brute-force O(n) per query — cepat sampai puluhan ribu item aktif; index (TurboVec-style) = fase 2.

## Lisensi

## Lisensi

Apache-2.0 — © 2026 Fadelli Polosoro dan kontributor. Kontribusi lewat DCO (`git commit -s`): `DCO.md`, `CONTRIBUTING.md`.
