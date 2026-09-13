# Pasang ingat sebagai extension Claude Desktop (MCPB)

Claude Desktop versi baru (2026, "epitaxy") **tidak lagi** membaca `mcpServers` dari
`claude_desktop_config.json` (ditimpa balik oleh app). Cara resmi sekarang: **MCPB (MCP Bundle)** —
berkas `.mcpb` (sebenarnya ZIP berisi `manifest.json`) yang di-install lewat UI.

## Bikin bundle
`manifest.contoh.json` = template. Sesuaikan path `command` (python.exe) dan `--konfig` untuk mesinmu,
lalu bungkus jadi ZIP bernama `ingat.mcpb`:

```powershell
python -c "import zipfile; z=zipfile.ZipFile(r'C:\Users\Hi\Downloads\ingat.mcpb','w'); z.write(r'manifest.json','manifest.json'); z.close()"
```

## Install di Claude Desktop
1. Buka **Settings** (roda gigi) → **Extensions** → **Advanced settings**.
2. Cari bagian **Extension Developer** → klik **"Install Extension…"**.
3. Pilih `ingat.mcpb`.
4. **Restart Claude Desktop** sekali (app tidak memantau perubahan .mcpb secara live).

Setelah itu, chat Claude Desktop punya 4 tool: `ingat`, `muat_startup`, `buka_bukti`, `catat_episode`.

## Catatan
- Pakai path Windows absolut di `command` (backslash ganda di JSON). `python.exe`, bukan `python3`.
- Bundle hanya membungkus perintah peluncur; store & konfig tetap di `~/.ingat` (lokal).
- Kalau app menolak manifest, cek `manifest_version` & bentuk `server` terhadap spek MCPB terkini
  (github.com/modelcontextprotocol/mcpb).
