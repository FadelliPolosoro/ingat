# Peluncur MCP ingat untuk Claude Desktop (MCPB).
# PENTING: jalankan IN-PROCESS, jangan os.execv — di Windows exec = spawn+exit,
# proses asli keluar -> host MCP kehilangan pipe stdio -> "Server disconnected".
# Menjalankan utama() di proses ini menjaga stdin/stdout tetap milik host.
import sys

sys.argv = ["ingat", "--konfig", r"C:\Users\Hi\.ingat\konfigurasi.json", "mcp"]
from ingat.cli import utama

raise SystemExit(utama())
