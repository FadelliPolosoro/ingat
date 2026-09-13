# Peluncur: gantikan proses dengan `python -m ingat --konfig <konfig> mcp`.
# ingat terpasang editable di Python312 pengguna; store & konfig di ~/.ingat (lokal).
import os
import sys

os.execv(sys.executable, [
    sys.executable, "-m", "ingat",
    "--konfig", r"C:\Users\Hi\.ingat\konfigurasi.json", "mcp",
])
