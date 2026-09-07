# Uji putar-ulang (spek Bab 12)

Metode: beri sistem semua episode *sebelum* tanggal kesalahan, ajukan situasi pemicu,
lulus bila gateway mengembalikan item yang `pemicu`-nya menyala sebelum tindakan salah diambil.

Suite Python `uji/uji_putar_ulang.py` (28 uji bersama `uji_redaksi.py`, `uji_penyemat_ollama.py`,
`uji_kontrak.py`) berjalan offline tanpa LLM. Fixture berkas di folder ini dipakai bersama port TS.

| Uji | Kasus | Python (rujukan) | Port TS |
|---|---|---|---|
| U1 | Titik buta Hostinger | hijau | fixture valid; gateway `todo` |
| U2 | Berkas dilaporkan selesai tapi tak ada di disk | hijau | — |
| U3 | Prasyarat versi sebelum integrasi (DaisyUI/Tailwind) | hijau | — |
| U4 | `npm ci --ignore-scripts` + Chromium terpisah | hijau | — |
| U5 | `follows` Instagram selalu nol — uji lingkup negatif | hijau | — |
| U6 | Norma bitemporal (norma fiktif `nr-uji-*`) | hijau | — |
| U7 | Anti-Spalko: rasio token ≤ 15 % | sebagian (`rasio_konteks` ada; skenario 1.000 episode belum) | — |
| U8 | Fobia: koreksi tunggal tidak menyeberang lingkup | hijau (U5 + kunci lingkup 7.2) | — |
| U9 | Item ditarik hanya muncul sebagai peringatan | hijau (`peringatan`/`pernah_ditarik`) | — |
| U10 | K10: tier S tersimpan, redaksi, `sertakan_S` | hijau | redaksi/tier hijau |
| U11–U12 | Gate tier, kontra mendominasi → dipersempit | hijau | — |

Struktur fixture berkas: `episode.jsonl` (skema 6.1), `pelajaran/*.md` (frontmatter 6.2), `skenario.json`
(`lingkup`, `situasi`, `harapan`, `tidak_boleh`, `lingkup_negatif`). Kolom `waktu` yang masih perkiraan
ditandai `"waktu_perkiraan": true` sampai dilengkapi dari riwayat chat.
