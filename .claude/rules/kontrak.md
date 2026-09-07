---
paths: ["skema/**", "src/simpan/frontmatter.ts", "src/mcp/**"]
---
# Aturan kontrak

Berkas di jalur ini adalah **kontrak publik** yang dibaca port lain (Python, Rust, Go).
- Setiap perubahan skema SQL, format frontmatter, atau skema tool MCP: catat di
  `docs/spek-arsitektur-memori.md` (bab terkait) + naikkan `versi_kontrak` di `skema/ingat.sql`.
- Perubahan yang memutus kompatibilitas mundur butuh migrasi di `skema/migrasi/` dan
  persetujuan pemilik.
- SQL portabel: TEXT untuk waktu (ISO 8601), TEXT untuk JSON, INTEGER untuk boolean (0/1),
  tanpa AUTOINCREMENT, tanpa fungsi khusus SQLite di DDL.
- Nama tabel/kolom: Bahasa Indonesia, snake_case, tanpa singkatan yang tidak ada di glosarium spek.
