# SPDX-License-Identifier: Apache-2.0
"""ingat — Panel Kendali (K29). Aplikasi desktop Tkinter (stdlib, nol-dependency).

Sikap K29: PANEL KENDALI, bukan tiruan aplikasi catatan. Visual kaya (graf, kartu) didelegasikan ke
dashboard web yang dibuka lewat tombol. Server serve(8765)+pantau(8790) berjalan IN-PROCESS
(daemon thread) sehingga ini satu aplikasi mandiri — tak perlu .cmd/.vbs auto-start lagi.
Prioritas fungsi (K29 §2): 1) konsolidasi+jawab 2) status 3) buka catatan 4) tempel cepat.
Penanda pemakaian tiap tombol (K29 §3) dicatat ke ~/.ingat/pemakaian.jsonl untuk tinjauan 2-mingguan.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
import threading
import webbrowser

RUMAH = os.path.expanduser("~")
DIR_INGAT = os.path.join(RUMAH, ".ingat")


def _alihkan_stdout_bila_perlu():
    """.exe windowed -> sys.stdout None -> print server jatuh. Alihkan ke berkas log."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        os.makedirs(DIR_INGAT, exist_ok=True)
        f = open(os.path.join(DIR_INGAT, "panel.log"), "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = f
        if sys.stderr is None:
            sys.stderr = f
    except Exception:
        import io
        if sys.stdout is None:
            sys.stdout = io.StringIO()
        if sys.stderr is None:
            sys.stderr = io.StringIO()


def catat_pemakaian(tombol: str):
    """K29 §3: rekam tiap pemakaian tombol (lokal) — dasar tinjauan 2-mingguan."""
    try:
        with open(os.path.join(DIR_INGAT, "pemakaian.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"tombol": tombol, "waktu": dt.datetime.now().isoformat(timespec="seconds")},
                               ensure_ascii=False) + "\n")
    except Exception:
        pass


# ---- preferensi otomasi (Fase 2): konsolidasi terjadwal in-app ----------------
# Disimpan terpisah dari konfigurasi.json (itu milik store/embedder) — ini murni
# pilihan UI panel, jadi tinggal di ~/.ingat/panel-prefs.json. Semua helper di
# bawah bebas-Tkinter supaya bisa diuji tanpa layar.
PREFS_DEFAULT = {"auto_konsolidasi": False, "interval_jam": 6, "terakhir_konsolidasi": None}
INTERVAL_PILIHAN = [("Mati", 0), ("Tiap 1 jam", 1), ("Tiap 6 jam", 6), ("Tiap 12 jam", 12), ("Tiap 24 jam", 24)]


def _path_prefs() -> str:
    return os.path.join(DIR_INGAT, "panel-prefs.json")


def muat_prefs() -> dict:
    """Baca panel-prefs.json; toleran berkas hilang/rusak → jatuh ke default, lalu sanitasi."""
    p = dict(PREFS_DEFAULT)
    try:
        with open(_path_prefs(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k in PREFS_DEFAULT:
                if k in data:
                    p[k] = data[k]
    except Exception:
        pass
    if not isinstance(p.get("interval_jam"), (int, float)) or isinstance(p.get("interval_jam"), bool) or p["interval_jam"] < 0:
        p["interval_jam"] = PREFS_DEFAULT["interval_jam"]
    p["auto_konsolidasi"] = bool(p.get("auto_konsolidasi"))
    return p


def simpan_prefs(prefs: dict) -> None:
    try:
        os.makedirs(DIR_INGAT, exist_ok=True)
        with open(_path_prefs(), "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def interval_ms(jam) -> int:
    """Jam → milidetik untuk root.after. ≤0 → 0 (mati). Bila >0 dijaga minimal 60 dtk
    supaya salah-konfig kecil tak jadi lingkaran konsolidasi yang membanjiri."""
    if not jam or jam <= 0:
        return 0
    return max(60_000, int(jam * 3_600_000))


# ---- koneksi AI (Fase 4): pusat kendali klien retail --------------------------
# Penyambungan sesungguhnya terjadi DI LUAR .exe (ekstensi di browser, MCPB di
# Claude Desktop). Panel hanya: (1) tampil status rekam per klien dari store,
# (2) sajikan host+token untuk disalin, (3) uji koneksi, (4) siapkan komponen.
# `sumber` yang ditulis tiap klien (jangan diubah tanpa menyelaraskan ekstensi/MCP):
#   ekstensi web → "browser:<host>" (content.js);  Claude Desktop → "mcp" (mcp_stdio.py).
KLIEN_KONEKSI = [
    ("Claude Desktop", "MCP", ("mcp",)),
    ("Claude.ai", "web", ("browser:claude.ai",)),
    ("ChatGPT", "web", ("browser:chatgpt.com", "browser:chat.openai.com")),
    ("Perplexity", "web", ("browser:www.perplexity.ai", "browser:perplexity.ai")),
    ("Gemini", "web", ("browser:gemini.google.com",)),
]


def token_server() -> str | None:
    """Token Bearer yang dipakai server 8765. Resolusi: env → berkas → config.
    None = koneksi AI mati karena klien tak bisa otentikasi."""
    from .jauh import baca_token
    t = baca_token(None)
    return t or None


def siapkan_allowlist() -> list[str]:
    """Allowlist email login Google. Resolusi: env INGAT_ALLOWED_EMAILS → berkas
    ~/.ingat/allowlist.txt (satu email per baris). Email SENGAJA tak ditanam di source
    supaya tak ikut ke repo publik — berkasnya milik mesin ini saja. Nilai yang ditemukan
    diekspor balik ke env sebelum muat_konfig() dibaca, jadi server 8765 langsung menerimanya
    dan login Google dengan email itu masuk otomatis (cookie sesi -> /dashboard tanpa langkah lagi).
    Kembalikan daftar email; [] berarti fail-closed (login Google menolak semua)."""
    env = os.environ.get("INGAT_ALLOWED_EMAILS", "").strip()
    if env:
        return [e.strip() for e in env.split(",") if e.strip()]
    berkas = os.path.join(DIR_INGAT, "allowlist.txt")
    try:
        with open(berkas, encoding="utf-8-sig") as f:
            emails = [b.strip() for b in f if b.strip() and not b.lstrip().startswith("#")]
        if emails:
            os.environ["INGAT_ALLOWED_EMAILS"] = ",".join(emails)
            return emails
    except OSError:
        pass
    return []


def status_koneksi(store) -> list[dict]:
    """Untuk tiap klien AI: waktu (iso) episode terbaru dari sumbernya, atau None.
    Dibaca dari store — bukti nyata rekam masuk, bukan tebakan."""
    terbaru: dict[str, str] = {}
    for ep in store.episode_semua():
        s = getattr(ep, "sumber", None)
        w = getattr(ep, "waktu", None)
        if s and w and (s not in terbaru or w > terbaru[s]):
            terbaru[s] = w
    hasil = []
    for nama, jalur, sumber_list in KLIEN_KONEKSI:
        w = None
        for s in sumber_list:
            if s in terbaru and (w is None or terbaru[s] > w):
                w = terbaru[s]
        hasil.append({"nama": nama, "jalur": jalur, "terakhir": w})
    return hasil


# Ambang kesehatan koneksi — memberi tahu kalau sebuah platform BERHENTI menulis diam-diam
# (selektor DOM rusak saat situs ganti UI). ChatGPT sempat 0 episode tanpa alarm; ini menutup itu.
KONEKSI_SEGAR_JAM = 48      # < 2 hari → hijau (sehat)
KONEKSI_BASI_HARI = 7       # ≥ 7 hari PADAHAL pernah aktif → merah (curiga capture mati)


def _parse_waktu(iso):
    """ISO → datetime aware (UTC), atau None kalau tak terbaca."""
    if not iso:
        return None
    try:
        t = dt.datetime.fromisoformat(iso)
        return t.replace(tzinfo=dt.timezone.utc) if t.tzinfo is None else t
    except Exception:
        return None


def _usia_relatif(iso) -> str:
    """'3 jam lalu' / '5 hari lalu' / 'belum ada rekam' — dibaca manusia di panel."""
    t = _parse_waktu(iso)
    if t is None:
        return "belum ada rekam" if not iso else str(iso)[:16].replace("T", " ")
    det = max(0.0, (dt.datetime.now(dt.timezone.utc) - t).total_seconds())
    if det < 3600:
        return f"{int(det // 60)} menit lalu"
    if det < KONEKSI_SEGAR_JAM * 3600:
        return f"{int(det // 3600)} jam lalu"
    return f"{int(det // 86400)} hari lalu"


def _kesehatan_koneksi(iso) -> tuple[str, str]:
    """(simbol, tag_warna) dari umur rekam terakhir. Belum-pernah = netral (○, abu), BUKAN alarm —
    alarm hanya untuk platform yang PERNAH aktif lalu terdiam (⚠ merah), gejala capture rusak."""
    t = _parse_waktu(iso)
    if t is None:
        return "○", "abu"
    jam = (dt.datetime.now(dt.timezone.utc) - t).total_seconds() / 3600
    if jam <= KONEKSI_SEGAR_JAM:
        return "●", "hijau"
    if jam >= KONEKSI_BASI_HARI * 24:
        return "⚠", "merah"
    return "●", "kuning"


def hitungan_tinjau(store) -> dict:
    """Hitung item yang butuh tinjauan (tinjau_ulang=True). Untuk badge panel + monitor."""
    pelajaran = [p for p in store.pelajaran_semua() if getattr(p, "tinjau_ulang", False)]
    prosedur = [p for p in store.prosedur_semua() if getattr(p, "tinjau_ulang", False)]
    return {
        "pelajaran": len(pelajaran),
        "prosedur": len(prosedur),
        "total": len(pelajaran) + len(prosedur),
        "daftar": [{"jenis": "pelajaran", "id": p.id, "teks": p.pelajaran[:80]} for p in pelajaran]
                + [{"jenis": "prosedur", "id": p.id, "teks": p.prosedur[:80]} for p in prosedur],
    }


def _basis_sumberdaya() -> str:
    """Root berkas pendukung: _MEIPASS di dalam .exe, atau root repo saat dari source."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def siapkan_ekstensi() -> str:
    """Salin folder ekstensi (dari bundle/repo) ke ~/.ingat/browser-extension supaya
    bisa 'Load unpacked' permanen — _MEIPASS temporer tak berguna untuk itu."""
    asal = os.path.join(_basis_sumberdaya(), "pasang", "browser-extension")
    tujuan = os.path.join(DIR_INGAT, "browser-extension")
    shutil.copytree(asal, tujuan, dirs_exist_ok=True)
    return tujuan


def siapkan_mcpb() -> str:
    """Salin template MCPB (dari bundle/repo) ke ~/.ingat/mcpb untuk dipasang di Claude Desktop."""
    asal = os.path.join(_basis_sumberdaya(), "pasang", "mcpb")
    tujuan = os.path.join(DIR_INGAT, "mcpb")
    shutil.copytree(asal, tujuan, dirs_exist_ok=True)
    return tujuan


def bangun_mcpb() -> str:
    """Bangun `ingat.mcpb` SIAP-PASANG (bukan cuma menyalin folder): ZIP berisi manifest.json +
    server/main.py, dengan path python & konfigurasi mesin ini terisi otomatis. Kembalikan path
    berkas .mcpb — inilah berkas yang di-'Install Extension…' di Claude Desktop."""
    import re as _re
    import zipfile
    from .sambung import python_untuk_mcp
    asal = os.path.join(_basis_sumberdaya(), "pasang", "mcpb")
    with open(os.path.join(asal, "manifest.contoh.json"), "r", encoding="utf-8") as f:
        manifest = json.load(f)
    manifest["server"]["mcp_config"]["command"] = python_untuk_mcp() or "python"
    with open(os.path.join(asal, "server", "main.py"), "r", encoding="utf-8") as f:
        main_py = f.read()
    # arahkan --konfig ke konfigurasi mesin ini (kalau username beda dari template)
    konfig = os.path.join(DIR_INGAT, "konfigurasi.json")
    main_py = _re.sub(r'r"[^"]*\.ingat[\\/]+konfigurasi\.json"', lambda m: 'r"%s"' % konfig, main_py)
    tujuan = os.path.join(DIR_INGAT, "ingat.mcpb")
    with zipfile.ZipFile(tujuan, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr("server/main.py", main_py)
    return tujuan


def bangun_ekstensi_zip() -> str:
    """Bungkus ekstensi web jadi SATU berkas `~/.ingat/ingat-ekstensi.zip` untuk diunduh, dipindah ke
    perangkat/browser lain, atau dibackup. Manifest.json ADA DI ROOT zip supaya sekali unzip langsung
    jadi folder yang bisa 'Load unpacked'. Catatan (dok Chrome resmi): di luar Web Store, Windows/Mac
    HANYA bisa lewat 'Load unpacked' folder — Chrome tak memasang .zip/.crx sekali klik. .zip = transport."""
    import zipfile
    asal = os.path.join(_basis_sumberdaya(), "pasang", "browser-extension")
    tujuan = os.path.join(DIR_INGAT, "ingat-ekstensi.zip")
    with zipfile.ZipFile(tujuan, "w", zipfile.ZIP_DEFLATED) as z:
        for akar, _dirs, berkas in os.walk(asal):
            for b in berkas:
                if b.endswith((".mjs", ".pyc")):  # berkas uji/dev — tak perlu di paket
                    continue
                penuh = os.path.join(akar, b)
                z.write(penuh, os.path.relpath(penuh, asal))  # relatif ke akar → manifest.json di root zip
    return tujuan


def uji_koneksi(host: str, token, timeout: float = 3.0) -> tuple[bool, str]:
    """Uji server 8765 hidup + token valid. Dijalankan live saat tombol diklik."""
    import urllib.error
    import urllib.request
    dasar = (host or "").rstrip("/")
    try:
        with urllib.request.urlopen(dasar + "/sehat", timeout=timeout) as r:
            if not (200 <= r.status < 300):
                return False, f"server balas {r.status} di /sehat"
    except Exception as e:
        return False, f"server {dasar} tak merespons ({type(e).__name__})"
    if not token:
        return False, "server hidup, tapi INGAT_TOKEN kosong — klien tak bisa otentikasi"
    req = urllib.request.Request(dasar + "/metrik", headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if 200 <= r.status < 300:
                return True, "tersambung · server hidup · token valid"
        return False, "respons tak terduga saat uji token"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "server hidup, tapi token DITOLAK (401) — cek INGAT_TOKEN"
        return False, f"server balas {e.code} saat uji token"
    except Exception as e:
        return False, f"gagal uji token ({type(e).__name__})"


# ---- helper bebas-Tkinter untuk tiga modul sambungan (Fase 5) -----------------
# Semua fungsi di bawah murni teks/keputusan supaya bisa diuji tanpa layar. Yang
# menyentuh widget tinggal di dalam bangun_jendela_*.

def _aman(win, fn):
    """Bungkus callback root.after supaya tak menyentuh jendela yang sudah ditutup.

    Worker thread bisa selesai beberapa detik setelah Tuan Muda menutup jendelanya;
    menyentuh widget mati melempar TclError yang muncul sebagai traceback."""
    def bungkus():
        try:
            if not win.winfo_exists():
                return
            fn()
        except Exception:
            pass
    return bungkus


def status_startup_aman() -> dict:
    """`startup.status_startup()` yang tak pernah melempar.

    Dipanggil tiap 5 detik dari segarkan_status(): satu galat tak terduga di sini akan
    menghentikan seluruh pembaruan status panel, bukan cuma centangnya."""
    from . import startup
    try:
        return startup.status_startup()
    except Exception as e:
        return {"aktif": False, "berkas": None, "metode": None, "target": None,
                "lawas": [], "folder": None, "galat": str(e)}


def pesan_lawas_startup(st: dict) -> str | None:
    """Peringatan bahasa awam bila entri auto-start generasi lama masih ada.

    Bukan sekadar info: entri lama menyalakan server 8765/8790 sebagai proses terpisah
    sedangkan panel menjalankan keduanya in-process — bila dua-duanya hidup saat boot,
    port sudah terpakai dan server panel gagal naik tanpa pesan yang jelas. Berkasnya
    sengaja TIDAK dihapus panel: itu buatan pemasangan lain, keputusan Tuan Muda."""
    lawas = (st or {}).get("lawas") or []
    if not lawas:
        return None
    nama = ", ".join(os.path.basename(p) for p in lawas)
    folder = (st or {}).get("folder") or os.path.dirname(lawas[0])
    return ("PERHATIAN: ada program ingat versi lama yang ikut menyala saat komputer dihidupkan ("
            + nama + "). Dia memakai pintu yang sama dengan panel ini, jadi panel bisa gagal "
            "menyala sendiri saat komputer baru hidup. Kalau mau dirapikan, hapus berkas itu lewat "
            "File Explorer di folder: " + str(folder) + " — panel sengaja tidak menghapusnya sendiri.")


def pesan_alih_startup(nyala: bool, hasil: dict) -> str:
    """Kalimat log setelah centang nyala-otomatis diubah."""
    h = hasil or {}
    if nyala:
        return "Nyala otomatis DIHIDUPKAN — pintasan ditaruh di " + str(h.get("folder") or "folder Startup")
    n = len(h.get("dihapus") or [])
    return "Nyala otomatis DIMATIKAN" + (" (" + str(n) + " pintasan dihapus)" if n else "")


WARNA_LAMPU = {"hijau": "#15803d", "kuning": "#b45309", "merah": "#b91c1c"}


def warna_lampu(lampu) -> str:
    return WARNA_LAMPU.get(str(lampu or ""), "#6b7280")


def baris_butir_sambung(butir: dict) -> str:
    b = butir or {}
    return ("✓ " if b.get("ok") else "✗ ") + str(b.get("nama") or "") + " — " + str(b.get("pesan") or "")


def baris_hasil_cari(h: dict) -> str:
    """Satu baris daftar hasil. Skor angka sengaja tidak ditampilkan: 0.61 tidak berarti
    apa-apa bagi pemakainya, dan None (pointer luapan) akan tampil sebagai nol palsu."""
    d = h or {}
    jenis = str(d.get("jenis") or "?")
    ringkas = str(d.get("ringkas") or d.get("kutipan") or "")
    tgl = str(d.get("tanggal") or "")
    return ("[" + jenis + "] " + ringkas + ("  · " + tgl if tgl else "")).strip()


def pesan_sumber_cari(sumber) -> str:
    """Catatan kecil asal hasil. Hanya 'riwayat' yang perlu diberitahukan — sisanya
    adalah pencarian segar dan tak ada gunanya diumumkan."""
    return "dari riwayat (hasil pencarian sebelumnya)" if str(sumber or "") == "riwayat" else ""


def teks_bukti(bukti: dict) -> str:
    """Isi verbatim episode untuk kotak bacaan, tanpa istilah teknis di labelnya."""
    b = bukti or {}
    kepala = []
    w = str(b.get("waktu") or "")
    if w:
        kepala.append("Waktu: " + w[:16].replace("T", " "))
    if b.get("ringkas"):
        kepala.append("Ringkas: " + str(b["ringkas"]))
    return ("\n".join(kepala) + "\n\n" if kepala else "") + str(b.get("isi") or "")


def pesan_galat_bukti(e: BaseException) -> str:
    """Kegagalan buka_bukti() dalam bahasa sehari-hari — tak boleh ada nama kelas Python."""
    if isinstance(e, PermissionError):
        return "Catatan ini ditandai rahasia, jadi isinya tidak dibuka di panel."
    if isinstance(e, KeyError):
        return "Catatan aslinya sudah tidak ada di memori."
    return "Catatan aslinya tidak bisa dibuka sekarang."


def bangun_jendela_koneksi(root, app, tulis_log=None):
    """Jendela 'Koneksi AI' (Toplevel): host+token untuk disalin, status klien dari
    store, uji koneksi, dan pandu-pasang ekstensi/MCPB. Module-level supaya bisa
    di-smoke-test headless. Mengembalikan Toplevel."""
    import tkinter as tk
    from tkinter import messagebox, ttk
    if tulis_log is None:
        tulis_log = lambda *_: None  # noqa: E731

    def _salin(teks, label):
        try:
            root.clipboard_clear()
            root.clipboard_append(teks)
            tulis_log("disalin: " + label)
        except Exception as e:
            tulis_log("gagal salin: " + str(e))

    HOST = "http://127.0.0.1:8765"
    tok = token_server()
    win = tk.Toplevel(root)
    win.title("ingat — Koneksi AI")
    win.geometry("600x880")
    win.minsize(560, 620)

    f1 = ttk.LabelFrame(win, text=" Server (isi ini ke ekstensi & klien) ")
    f1.pack(fill="x", padx=12, pady=(12, 6))
    r1 = ttk.Frame(f1); r1.pack(fill="x", padx=8, pady=(8, 4))
    ttk.Label(r1, text="Host", width=7).pack(side="left")
    eh = ttk.Entry(r1); eh.insert(0, HOST); eh.configure(state="readonly")
    eh.pack(side="left", fill="x", expand=True, padx=4)
    ttk.Button(r1, text="Salin", width=7, command=lambda: _salin(HOST, "host")).pack(side="left")
    r2 = ttk.Frame(f1); r2.pack(fill="x", padx=8, pady=(0, 8))
    ttk.Label(r2, text="Token", width=7).pack(side="left")
    tampil = (tok[:4] + "…" + tok[-4:]) if tok and len(tok) > 8 else (tok or "(kosong)")
    et = ttk.Entry(r2); et.insert(0, tampil); et.configure(state="readonly")
    et.pack(side="left", fill="x", expand=True, padx=4)
    ttk.Button(r2, text="Salin", width=7, state=("normal" if tok else "disabled"),
               command=lambda: _salin(tok or "", "token")).pack(side="left")
    if not tok:
        ttk.Label(f1, text="⚠ INGAT_TOKEN kosong — server 8765 & koneksi AI mati. Set env dulu.",
                  foreground="#b91c1c", font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=(0, 8))

    f2 = ttk.LabelFrame(win, text=" Status klien (kapan terakhir menulis) ")
    f2.pack(fill="both", expand=True, padx=12, pady=6)
    lbl_ringkas = ttk.Label(f2, text="", font=("Segoe UI", 9))
    lbl_ringkas.pack(anchor="w", padx=8, pady=(6, 0))
    box = tk.Text(f2, height=8, font=("Consolas", 9), state="disabled", wrap="none")
    box.pack(fill="both", expand=True, padx=6, pady=(4, 2))
    box.tag_configure("hijau", foreground="#15803d")
    box.tag_configure("kuning", foreground="#b45309")
    box.tag_configure("merah", foreground="#b91c1c")
    box.tag_configure("abu", foreground="#6b7280")

    def muat_status():
        try:
            data = status_koneksi(app.store)
            pesan_e = ""
        except Exception as e:
            data = None
            pesan_e = str(e)
        box.configure(state="normal"); box.delete("1.0", "end")
        if data is None:
            lbl_ringkas.config(text="gagal baca store: " + pesan_e, foreground="#b91c1c")
            box.configure(state="disabled")
            return
        basi = []
        for d in data:
            simbol, tag = _kesehatan_koneksi(d["terakhir"])
            if tag == "merah":
                basi.append(d["nama"])
            baris = "{sm} {nm:<16} [{jl:<3}]  {tt}\n".format(
                sm=simbol, nm=d["nama"], jl=d["jalur"], tt=_usia_relatif(d["terakhir"]))
            box.insert("end", baris, tag)
        box.configure(state="disabled")
        if basi:
            lbl_ringkas.config(
                text="⚠ " + ", ".join(basi) + " diam ≥7 hari — cek ekstensi/selektor platform itu.",
                foreground="#b91c1c")
        else:
            lbl_ringkas.config(text="Semua platform yang pernah aktif masih menulis.", foreground="#15803d")

    muat_status()
    ttk.Button(f2, text="Segarkan", command=muat_status).pack(anchor="e", padx=6, pady=(0, 6))

    f3 = ttk.Frame(win); f3.pack(fill="x", padx=12, pady=4)
    lbl_uji = ttk.Label(f3, text="", font=("Segoe UI", 9))

    def lakukan_uji():
        lbl_uji.config(text="menguji…", foreground="#6b7280")

        def kerja():
            ok, pesan = uji_koneksi(HOST, token_server())
            root.after(0, lambda: lbl_uji.config(
                text=("✓ " if ok else "✗ ") + pesan,
                foreground=("#15803d" if ok else "#b91c1c")))
        threading.Thread(target=kerja, daemon=True).start()

    ttk.Button(f3, text="Uji koneksi", command=lakukan_uji).pack(side="left")
    lbl_uji.pack(side="left", padx=8)

    f4 = ttk.LabelFrame(win, text=" Panduan connector — pakai yang mana untuk apa ")
    f4.pack(fill="x", padx=12, pady=(6, 12))

    _PANDUAN = (
        "AI web (ChatGPT · Gemini · Claude.ai · Perplexity · DeepSeek · Kimi)  →  Ekstensi web (satu pasang)\n"
        "    'Siapkan ekstensi web' → folder ~/.ingat/browser-extension → Load unpacked di chrome://extensions.\n"
        "    'Bangun ekstensi .zip' → satu berkas untuk pindah perangkat/backup (unzip dulu, lalu Load unpacked).\n"
        "\n"
        "Claude Desktop  →  MCPB (cara resmi Claude Desktop 2026)\n"
        "    Tombol di bawah MEMBANGUN berkas siap-pasang:  ~/.ingat/ingat.mcpb\n"
        "    Pasang: Settings → Extensions → Advanced → Install Extension… → pilih ingat.mcpb.\n"
        "\n"
        "Recall otomatis: buka chat baru yang kosong → memori relevan tersuntik ke kotak ketik\n"
        "(Anda tinjau lalu kirim; tak pernah terkirim otomatis). Tanpa kata kunci."
    )
    ttk.Label(f4, text=_PANDUAN, justify="left", font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=(8, 4))

    def pasang_ekstensi():
        try:
            p = siapkan_ekstensi()
            tulis_log("ekstensi disiapkan: " + p)
            try:
                os.startfile(p)
            except Exception:
                pass
            messagebox.showinfo("Ekstensi web siap",
                "Folder ekstensi (upload folder ini):\n" + p +
                "\n\n1. Buka chrome://extensions (atau edge://extensions)\n"
                "2. Nyalakan Developer mode\n"
                "3. Load unpacked → pilih folder di atas\n"
                "4. Buka Opsi ekstensi, isi Host + Token (pakai tombol Salin di jendela ini)\n"
                "5. Claude.ai & Perplexity: isi selektor di Opsi (ChatGPT & Gemini sudah bawaan)")
        except Exception as e:
            messagebox.showerror("Gagal menyiapkan ekstensi", str(e))

    def pasang_mcpb():
        try:
            berkas = bangun_mcpb()
            tulis_log("mcpb dibangun: " + berkas)
            try:
                import subprocess
                subprocess.Popen(["explorer", "/select,", berkas])  # buka folder & sorot berkasnya
            except Exception:
                try:
                    os.startfile(os.path.dirname(berkas))
                except Exception:
                    pass
            messagebox.showinfo("MCPB siap-pasang — Claude Desktop",
                "Berkas yang di-install (ini yang di-'upload'):\n" + berkas +
                "\n\nDi Claude Desktop:\n"
                "1. Settings (roda gigi) → Extensions → Advanced settings\n"
                "2. Extension Developer → Install Extension…\n"
                "3. Pilih berkas ingat.mcpb di atas\n"
                "4. Restart Claude Desktop sekali\n\n"
                "Setelah itu chat Claude Desktop punya tool: ingat, muat_startup, buka_bukti, catat_episode.")
        except Exception as e:
            messagebox.showerror("Gagal membangun MCPB", str(e))

    def bikin_ekstensi_zip():
        try:
            berkas = bangun_ekstensi_zip()
            tulis_log("ekstensi .zip dibangun: " + berkas)
            try:
                import subprocess
                subprocess.Popen(["explorer", "/select,", berkas])
            except Exception:
                try:
                    os.startfile(os.path.dirname(berkas))
                except Exception:
                    pass
            messagebox.showinfo("Ekstensi .zip siap (untuk unduh / pindah perangkat)",
                "Berkas:\n" + berkas +
                "\n\nGunanya: dipindah ke komputer/browser lain atau dibackup.\n"
                "Chrome TIDAK memasang .zip langsung (batas Chrome, di luar Web Store):\n"
                "1. Unzip ke folder tetap (mis. Documents\\ingat-ekstensi)\n"
                "2. chrome://extensions → Developer mode → Load unpacked → pilih folder itu\n"
                "3. Opsi ekstensi: isi Host + Token (tombol Salin di jendela ini)\n\n"
                "Mencakup: ChatGPT, Claude.ai, Gemini, Perplexity, DeepSeek, Kimi.")
        except Exception as e:
            messagebox.showerror("Gagal membangun ekstensi .zip", str(e))

    barisf4 = ttk.Frame(f4); barisf4.pack(fill="x", padx=8, pady=(0, 8))
    ttk.Button(barisf4, text="Siapkan ekstensi web", command=pasang_ekstensi).pack(side="left", padx=(2, 6))
    ttk.Button(barisf4, text="Bangun ekstensi .zip", command=bikin_ekstensi_zip).pack(side="left", padx=(0, 6))
    ttk.Button(barisf4, text="Bangun ingat.mcpb (Claude Desktop)", command=pasang_mcpb).pack(side="left")

    # -- sambungkan otomatis ke Claude Desktop LEWAT mcpServers — LEGACY (Claude Desktop lama).
    #    Claude Desktop 2026 mengabaikan mcpServers dan pakai MCPB (tombol di atas); bagian ini
    #    hanya berguna untuk versi lama, ditandai jelas supaya tak menyesatkan.
    from .sambung import putuskan, sambungkan
    from .sambung import status as status_sambung

    f5 = ttk.LabelFrame(win, text=" Sambungkan otomatis via mcpServers — LEGACY (Claude Desktop lama) ")
    f5.pack(fill="x", padx=12, pady=(0, 12))
    ttk.Label(f5, text="Claude Desktop 2026 memakai MCPB (di atas) — kalau ingat.mcpb sudah terpasang, abaikan bagian ini.",
              foreground="#6b7280", font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(6, 0))
    baris_lampu = ttk.Frame(f5)
    baris_lampu.pack(fill="x", padx=10, pady=(8, 0))
    lampu = tk.Label(baris_lampu, text="●", font=("Segoe UI", 15), fg="#6b7280")
    lampu.pack(side="left")
    lbl_sambung = ttk.Label(baris_lampu, text="memeriksa…", font=("Segoe UI Semibold", 10))
    lbl_sambung.pack(side="left", padx=6)
    rincian = tk.Text(f5, height=3, font=("Segoe UI", 9), wrap="word", state="disabled",
                      relief="flat", highlightthickness=0, background=win.cget("background"))
    rincian.pack(fill="x", padx=12, pady=(2, 4))

    def gambar_sambung(s):
        lampu.config(fg=warna_lampu((s or {}).get("lampu")))
        lbl_sambung.config(text=str((s or {}).get("pesan") or ""))
        rincian.configure(state="normal")
        rincian.delete("1.0", "end")
        for b in (s or {}).get("butir") or []:
            rincian.insert("end", baris_butir_sambung(b) + "\n")
        rincian.configure(state="disabled")

    def periksa_sambungan():
        lbl_sambung.config(text="memeriksa…")

        def kerja():
            # status() menguji server lewat jaringan — di thread UI ini membekukan jendela.
            try:
                s = status_sambung()
            except Exception:
                s = {"lampu": "merah", "pesan": "Keadaan sambungan tidak bisa diperiksa.", "butir": []}
            root.after(0, _aman(win, lambda: gambar_sambung(s)))
        threading.Thread(target=kerja, daemon=True).start()

    def _jalankan_sambung(paksa=False):
        tombol_sambung.config(state="disabled")
        lbl_sambung.config(text="menyambungkan…")

        def kerja():
            try:
                h = sambungkan(paksa=paksa)
            except Exception:
                # Pesan modul sambung sudah berbahasa awam; yang lolos ke sini hanya
                # kegagalan tak terduga, dan str(e)-nya tak berguna bagi pemakainya.
                h = {"berhasil": False, "pesan": "Penyambungan tidak bisa dijalankan sekarang. Coba lagi sebentar."}
            root.after(0, _aman(win, lambda: selesai_sambung(h)))
        threading.Thread(target=kerja, daemon=True).start()

    def selesai_sambung(h):
        tombol_sambung.config(state="normal")
        pesan = str((h or {}).get("pesan") or "")
        tulis_log("sambungkan: " + pesan)
        if (h or {}).get("berhasil"):
            messagebox.showinfo("Sambungkan", pesan, parent=win)
        elif "rusak" in pesan.lower() and messagebox.askyesno(
                "Pengaturan Claude Desktop rusak",
                pesan + "\n\nTulis ulang pengaturannya sekarang? Salinan berkas lama tetap dibuat dulu.",
                parent=win):
            _jalankan_sambung(paksa=True)
            return
        else:
            messagebox.showerror("Sambungkan", pesan, parent=win)
        periksa_sambungan()

    def lakukan_sambung():
        catat_pemakaian("sambungkan")
        _jalankan_sambung(False)

    def lakukan_putus():
        if not messagebox.askyesno("Putuskan", "Cabut ingat dari pengaturan Claude Desktop?", parent=win):
            return
        catat_pemakaian("putuskan")

        def kerja():
            try:
                h = putuskan()
            except Exception:
                h = {"berhasil": False, "pesan": "Pemutusan tidak bisa dijalankan sekarang. Coba lagi sebentar."}
            root.after(0, _aman(win, lambda: selesai_putus(h)))
        threading.Thread(target=kerja, daemon=True).start()

    def selesai_putus(h):
        pesan = str((h or {}).get("pesan") or "")
        tulis_log("putuskan: " + pesan)
        (messagebox.showinfo if (h or {}).get("berhasil") else messagebox.showerror)("Putuskan", pesan, parent=win)
        periksa_sambungan()

    baris_tombol = ttk.Frame(f5)
    baris_tombol.pack(fill="x", padx=10, pady=(0, 8))
    tombol_sambung = ttk.Button(baris_tombol, text="Sambungkan", command=lakukan_sambung)
    tombol_sambung.pack(side="left")
    ttk.Button(baris_tombol, text="Periksa lagi", command=periksa_sambungan).pack(side="left", padx=6)
    ttk.Button(baris_tombol, text="Putuskan", command=lakukan_putus).pack(side="left")
    periksa_sambungan()
    return win


def bangun_jendela_judul(root, app, tulis_log=None):
    """Jendela 'Rapikan nama memori': beri judul bersih & deskriptif ke tiap episode dengan
    mempelajari isinya (heuristik). NON-DESTRUKTIF — judul di tabel sidecar, `sumber`/`ringkas`
    asli tak disentuh; ada Undo. Module-level supaya bisa di-smoke-test headless."""
    import tkinter as tk
    from tkinter import messagebox, ttk
    from . import judul_memori as JM
    if tulis_log is None:
        tulis_log = lambda *_: None  # noqa: E731

    win = tk.Toplevel(root)
    win.title("ingat — Rapikan nama memori")
    win.geometry("720x560")
    win.minsize(600, 460)

    ttk.Label(win, text="Beri judul bersih & deskriptif ke tiap memori (mempelajari isinya).",
              font=("Segoe UI", 10)).pack(anchor="w", padx=12, pady=(12, 0))
    ttk.Label(win, text="Non-destruktif: asal & ringkas asli tak disentuh; bisa di-Undo.",
              foreground="#6b7280", font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=(0, 6))

    lbl = ttk.Label(win, text="", font=("Segoe UI Semibold", 10))
    lbl.pack(anchor="w", padx=12)
    box = tk.Text(win, font=("Consolas", 9), state="disabled", wrap="none")
    box.pack(fill="both", expand=True, padx=12, pady=6)
    sib = {"sibuk": False}

    def _tulis_contoh(contoh):
        box.configure(state="normal"); box.delete("1.0", "end")
        box.insert("end", "{r:<40}    JUDUL rapi\n".format(r="RINGKAS / asal lama"))
        box.insert("end", ("-" * 88) + "\n")
        for c in contoh:
            box.insert("end", "{r:<40} →  {j}\n".format(r=(c["ringkas"] or c["sumber"])[:38], j=c["judul"]))
        box.configure(state="disabled")

    def _jalankan(tulis):
        if sib["sibuk"]:
            return
        sib["sibuk"] = True
        lbl.config(text=("merapikan…" if tulis else "menyusun pratinjau…"), foreground="#6b7280")

        def kerja():
            try:
                hasil, galat = JM.rapikan(app.store, tulis=tulis), ""
            except Exception as e:
                hasil, galat = None, str(e)

            def selesai():
                sib["sibuk"] = False
                if galat:
                    lbl.config(text="gagal: " + galat, foreground="#b91c1c"); return
                kata = "Ditulis" if tulis else "Pratinjau"
                lbl.config(text=f"{kata}: {hasil['diproses']} memori diberi judul.", foreground="#15803d")
                _tulis_contoh(hasil["contoh"])
                if tulis:
                    tulis_log(f"rapikan nama memori: {hasil['ditulis']} judul ditulis")
            root.after(0, selesai)
        threading.Thread(target=kerja, daemon=True).start()

    def _undo():
        if not messagebox.askyesno("Undo", "Hapus semua judul rapi? (memori asli tak tersentuh)", parent=win):
            return
        n = JM.kosongkan(app.store)
        lbl.config(text=f"Undo: {n} judul dihapus.", foreground="#6b7280")
        box.configure(state="normal"); box.delete("1.0", "end"); box.configure(state="disabled")
        tulis_log(f"rapikan nama memori: undo, {n} judul dihapus")

    bar = ttk.Frame(win); bar.pack(fill="x", padx=12, pady=(0, 12))
    ttk.Button(bar, text="Pratinjau", command=lambda: _jalankan(False)).pack(side="left")
    ttk.Button(bar, text="Rapikan sekarang", command=lambda: _jalankan(True)).pack(side="left", padx=6)
    ttk.Button(bar, text="Undo", command=_undo).pack(side="left")
    n0 = JM.berapa_berjudul(app.store)
    lbl.config(text=(f"{n0} memori sudah berjudul." if n0 else "Belum ada yang dirapikan. Klik Pratinjau."))
    _jalankan(False)  # auto-pratinjau saat dibuka
    return win


def bangun_jendela_memori(root, app, tulis_log=None):
    """Jendela 'Kelola memori': daftar semua memori (judul rapi + asal + tanggal + tier), cari/filter,
    lihat isi verbatim, edit judul, hapus, dan ekspor/impor. Rumah bagi judul dari 'Rapikan nama'.
    Module-level supaya bisa di-smoke-test headless. Mengembalikan Toplevel."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from . import judul_memori as JM
    from . import pindah
    from . import tag as TAG
    if tulis_log is None:
        tulis_log = lambda *_: None  # noqa: E731

    win = tk.Toplevel(root)
    win.title("ingat — Kelola memori")
    win.geometry("920x640")
    win.minsize(760, 500)
    d = {"eps": [], "pilih": None}

    # -- bar atas: cari + jumlah
    atas = ttk.Frame(win); atas.pack(fill="x", padx=12, pady=(12, 4))
    ttk.Label(atas, text="Cari:").pack(side="left")
    cari_var = tk.StringVar()
    ttk.Entry(atas, textvariable=cari_var).pack(side="left", fill="x", expand=True, padx=(6, 8), ipady=2)
    tag_filter_var = tk.StringVar(value="Semua tag")
    cmb_tag = ttk.Combobox(atas, textvariable=tag_filter_var, state="readonly", width=16)
    cmb_tag.pack(side="left", padx=(6, 0))
    lbl_jml = ttk.Label(atas, text="", foreground="#6b7280", font=("Segoe UI", 9))
    lbl_jml.pack(side="left", padx=(6, 0))

    # -- badan: kiri daftar, kanan detail
    badan = ttk.Panedwindow(win, orient="horizontal"); badan.pack(fill="both", expand=True, padx=12, pady=4)
    kiri = ttk.Frame(badan); badan.add(kiri, weight=3)
    kolom = ("sumber", "tanggal", "tier", "tag")
    tabel = ttk.Treeview(kiri, columns=kolom, show="tree headings", height=18)
    tabel.heading("#0", text="Judul"); tabel.column("#0", width=300, stretch=True)
    tabel.heading("sumber", text="Asal"); tabel.column("sumber", width=120, anchor="w")
    tabel.heading("tanggal", text="Tanggal"); tabel.column("tanggal", width=90, anchor="center")
    tabel.heading("tier", text="Tier"); tabel.column("tier", width=44, anchor="center")
    tabel.heading("tag", text="Tag"); tabel.column("tag", width=160, anchor="w")
    gulir = ttk.Scrollbar(kiri, orient="vertical", command=tabel.yview)
    tabel.configure(yscrollcommand=gulir.set)
    tabel.pack(side="left", fill="both", expand=True); gulir.pack(side="right", fill="y")

    kanan = ttk.Frame(badan); badan.add(kanan, weight=2)
    ttk.Label(kanan, text="Judul (bisa diedit):", font=("Segoe UI", 9)).pack(anchor="w")
    judul_var = tk.StringVar()
    ent_judul = ttk.Entry(kanan, textvariable=judul_var); ent_judul.pack(fill="x", pady=(0, 4), ipady=2)
    baris_j = ttk.Frame(kanan); baris_j.pack(fill="x")
    btn_simpan = ttk.Button(baris_j, text="Simpan judul", state="disabled")
    btn_simpan.pack(side="left")
    btn_hapus = ttk.Button(baris_j, text="Hapus memori", state="disabled")
    btn_hapus.pack(side="left", padx=6)
    btn_riwayat = ttk.Button(baris_j, text="Riwayat", state="disabled")
    btn_riwayat.pack(side="left", padx=6)
    btn_pin = ttk.Button(baris_j, text="Sematkan", state="disabled")
    btn_pin.pack(side="left", padx=6)
    ttk.Label(kanan, text="Isi memori:", font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))
    isi_box = tk.Text(kanan, font=("Segoe UI", 9), wrap="word", state="disabled")
    isi_box.pack(fill="both", expand=True, pady=(0, 4))

    def _nama_sumber(s):
        return JM._NAMA_SUMBER.get(s, s[8:] if str(s).startswith("browser:") else (s or "—"))

    def _muat():
        d["eps"] = list(reversed(app.store.episode_semua()))  # terbaru dulu
        _isi_tabel()

    def _isi_tabel(*_):
        q = cari_var.get().strip().lower()
        judul_map = JM.semua_judul(app.store)
        tag_map = TAG.semua_tag(app.store)
        tag_fil = tag_filter_var.get()
        tag_unik = sorted({t for ts in tag_map.values() for t in ts})
        cmb_tag["values"] = ["Semua tag"] + tag_unik
        tabel.delete(*tabel.get_children())
        n = 0
        for ep in d["eps"]:
            judul = judul_map.get(ep.id) or (getattr(ep, "ringkas", "") or "")[:60] or ep.id
            sumber = _nama_sumber(getattr(ep, "sumber", ""))
            ep_tags = tag_map.get(ep.id, [])
            if tag_fil and tag_fil != "Semua tag" and tag_fil not in ep_tags:
                continue
            if q and q not in judul.lower() and q not in str(getattr(ep, "sumber", "")).lower() \
                    and q not in (getattr(ep, "ringkas", "") or "").lower():
                continue
            tag_str = ", ".join(ep_tags)
            tabel.insert("", "end", iid=ep.id, text=judul,
                         values=(sumber, str(getattr(ep, "waktu", ""))[:10], getattr(ep, "tier", ""), tag_str))
            n += 1
        lbl_jml.config(text=f"{n} memori")

    def _pilih(*_):
        sel = tabel.selection()
        if not sel:
            return
        ep = next((e for e in d["eps"] if e.id == sel[0]), None)
        if ep is None:
            return
        d["pilih"] = ep
        judul_map = JM.semua_judul(app.store)
        judul_var.set(judul_map.get(ep.id, ""))
        isi = ""
        if getattr(ep, "isi_ref", ""):
            try:
                isi = app.store.buka_dingin(ep.isi_ref).get("isi", "")
            except Exception:
                isi = "(isi tak terbaca)"
        isi_box.configure(state="normal"); isi_box.delete("1.0", "end")
        isi_box.insert("end", isi or "(tanpa isi verbatim)"); isi_box.configure(state="disabled")
        btn_simpan.config(state="normal"); btn_hapus.config(state="normal"); btn_riwayat.config(state="normal")
        if app.store.disematkan(ep.id):
            btn_pin.config(text="Lepas pin", state="normal")
        else:
            btn_pin.config(text="Sematkan", state="normal")

    def _toggle_pin():
        ep = d["pilih"]
        if not ep:
            return
        if app.store.disematkan(ep.id):
            app.store.lepas_sematan(ep.id)
            btn_pin.config(text="Sematkan")
            tulis_log("lepas sematan: " + ep.id)
        else:
            app.store.sematkan("episode", ep.id)
            btn_pin.config(text="Lepas pin")
            tulis_log("disematkan: " + ep.id)
    btn_pin.config(command=_toggle_pin)

    def _simpan_judul():
        ep = d["pilih"]
        if not ep:
            return
        JM.set_judul(app.store, ep.id, judul_var.get(), otak="manusia")
        tabel.item(ep.id, text=judul_var.get().strip() or ep.id)
        tulis_log("judul diedit: " + ep.id)

    def _hapus():
        ep = d["pilih"]
        if not ep:
            return
        if not messagebox.askyesno("Hapus memori",
                "Hapus PERMANEN memori ini? Tak bisa dibatalkan.\n\n" + (judul_var.get() or ep.id),
                parent=win):
            return
        JM.hapus_judul(app.store, ep.id)
        app.store.hapus_episode(ep.id)
        d["eps"] = [e for e in d["eps"] if e.id != ep.id]
        d["pilih"] = None
        tabel.delete(ep.id)
        judul_var.set(""); isi_box.configure(state="normal"); isi_box.delete("1.0", "end"); isi_box.configure(state="disabled")
        btn_simpan.config(state="disabled"); btn_hapus.config(state="disabled"); btn_riwayat.config(state="disabled")
        lbl_jml.config(text=f"{len(tabel.get_children())} memori")
        tulis_log("memori dihapus: " + ep.id)

    def _lihat_riwayat():
        ep = d["pilih"]
        if not ep:
            return
        riwayat = app.store.riwayat_perubahan(ep.id)
        isi_box.configure(state="normal"); isi_box.delete("1.0", "end")
        if not riwayat:
            isi_box.insert("end", "(belum ada perubahan tercatat)")
        else:
            for r in reversed(riwayat):
                isi_box.insert("end", f"[{r['waktu'][:16]}] {r['aksi']} oleh {r['oleh']}\n")
                if r.get('sebelum'):
                    isi_box.insert("end", f"  sebelum: {r['sebelum']}\n")
                if r.get('sesudah'):
                    isi_box.insert("end", f"  sesudah: {r['sesudah']}\n")
                isi_box.insert("end", "\n")
        isi_box.configure(state="disabled")

    def _ekspor():
        path = filedialog.asksaveasfilename(parent=win, defaultextension=".json",
                    filetypes=[("JSON", "*.json")], initialfile="ingat-ekspor.json",
                    title="Ekspor semua memori ke berkas")
        if not path:
            return
        try:
            data = pindah.ekspor(app.store)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            messagebox.showinfo("Ekspor", f"{data['jumlah']} memori diekspor ke:\n{path}", parent=win)
            tulis_log(f"ekspor: {data['jumlah']} memori → {path}")
        except Exception as e:
            messagebox.showerror("Ekspor gagal", str(e), parent=win)

    def _impor():
        path = filedialog.askopenfilename(parent=win, filetypes=[("JSON", "*.json")],
                    title="Impor memori dari berkas ekspor")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            lap = pindah.impor(app.store, data, lewati_ada=True)
            messagebox.showinfo("Impor",
                f"Diimpor {lap['diimpor']}, dilewati (sudah ada) {lap['dilewati_sudah_ada']}.", parent=win)
            tulis_log(f"impor: +{lap['diimpor']} memori dari {path}")
            _muat()
        except Exception as e:
            messagebox.showerror("Impor gagal", str(e), parent=win)

    btn_simpan.config(command=_simpan_judul)
    btn_hapus.config(command=_hapus)
    btn_riwayat.config(command=_lihat_riwayat)
    cari_var.trace_add("write", _isi_tabel)
    cmb_tag.bind("<<ComboboxSelected>>", _isi_tabel)
    tabel.bind("<<TreeviewSelect>>", _pilih)

    bawah = ttk.Frame(win); bawah.pack(fill="x", padx=12, pady=(4, 12))
    ttk.Button(bawah, text="Ekspor semua…", command=_ekspor).pack(side="left")
    ttk.Button(bawah, text="Impor…", command=_impor).pack(side="left", padx=6)
    ttk.Button(bawah, text="Segarkan", command=_muat).pack(side="left")
    ttk.Label(bawah, text="Hapus bersifat permanen (store laptop otoritatif).",
              foreground="#6b7280", font=("Segoe UI", 8)).pack(side="right")

    def buka_recall():
        bangun_jendela_recall(root, app, tulis_log)

    _muat()
    ttk.Button(bawah, text="Pratinjau recall", command=buka_recall).pack(side="left", padx=(12, 0))
    return win


def bangun_jendela_recall(root, app, tulis_log=None):
    """Transparansi recall: tampilkan apa yang ingat SUNTIKKAN saat chat baru dibuka — peta memori
    (judul) + aturan (isi penuh) untuk sebuah lingkup, beserta jumlah token. Module-level, testable."""
    import tkinter as tk
    from tkinter import ttk
    if tulis_log is None:
        tulis_log = lambda *_: None  # noqa: E731

    win = tk.Toplevel(root)
    win.title("ingat — Pratinjau recall")
    win.geometry("740x580"); win.minsize(600, 440)
    atas = ttk.Frame(win); atas.pack(fill="x", padx=12, pady=(12, 4))
    ttk.Label(atas, text="Lingkup:").pack(side="left")
    lk = tk.StringVar(value="global")
    ttk.Entry(atas, textvariable=lk, width=22).pack(side="left", padx=(6, 8))
    lbl = ttk.Label(atas, text="", foreground="#6b7280", font=("Segoe UI", 9)); lbl.pack(side="left")
    ttk.Label(win, text="Inilah yang otomatis masuk ke kotak ketik saat Anda buka chat baru.",
              foreground="#6b7280", font=("Segoe UI", 9)).pack(anchor="w", padx=12)
    box = tk.Text(win, font=("Consolas", 9), wrap="word", state="disabled")
    box.pack(fill="both", expand=True, padx=12, pady=6)

    def muat():
        try:
            hasil = app.gateway.muat_startup(lingkup=lk.get().strip() or "global", sesi="pratinjau-panel")
            galat = ""
        except Exception as e:
            hasil, galat = None, str(e)
        box.configure(state="normal"); box.delete("1.0", "end")
        if galat:
            lbl.config(text=""); box.insert("end", "gagal: " + galat)
        else:
            tok = hasil.get("token", {})
            lbl.config(text=f"{tok.get('total', 0)} token disuntik")
            box.insert("end", "# PETA MEMORI (judul yang muncul di awal chat)\n")
            for b in hasil.get("peta", []):
                box.insert("end", "  " + b + "\n")
            box.insert("end", "\n# ATURAN (isi penuh yang disuntik)\n")
            for a in hasil.get("aturan", []):
                box.insert("end", a + "\n\n")
            if hasil.get("pointer"):
                box.insert("end", f"\n# (+{len(hasil['pointer'])} item tak dimuat penuh — ditarik saat relevan)\n")
            if not hasil.get("peta") and not hasil.get("aturan"):
                box.insert("end", "(belum ada pelajaran/prosedur/norma aktif untuk lingkup ini)")
        box.configure(state="disabled")

    ttk.Button(atas, text="Muat", command=muat).pack(side="right")
    muat()
    return win


def bangun_jendela_cari(root, app, tulis_log=None, gerbang=None, store=None):
    """Jendela 'Cari memori': satu pertanyaan bebas → kutipan memori yang cocok.

    Tanpa model generatif (keputusan Tuan Muda): yang tampil adalah isi memori apa adanya.
    Module-level supaya bisa di-smoke-test headless. Mengembalikan Toplevel."""
    import tkinter as tk
    from tkinter import ttk

    from .cari_memori import cari
    if tulis_log is None:
        tulis_log = lambda *_: None  # noqa: E731

    win = tk.Toplevel(root)
    win.title("ingat — Cari memori")
    win.geometry("660x580")
    win.minsize(540, 480)
    hasil_ref = {"baris": []}

    atas = ttk.Frame(win)
    atas.pack(fill="x", padx=12, pady=(12, 2))
    entri = ttk.Entry(atas, font=("Segoe UI", 11))
    entri.pack(side="left", fill="x", expand=True, ipady=3)
    tombol_cari = ttk.Button(atas, text="Cari", width=8)
    tombol_cari.pack(side="left", padx=(6, 0))
    lbl_info = ttk.Label(win, text="Ketik apa yang ingin dicari, lalu tekan Enter.",
                         foreground="#6b7280", font=("Segoe UI", 9))
    lbl_info.pack(anchor="w", padx=14, pady=(2, 6))

    tengah = ttk.LabelFrame(win, text=" Yang ditemukan ")
    tengah.pack(fill="both", expand=True, padx=12, pady=(0, 6))
    daftar = tk.Listbox(tengah, height=8, font=("Segoe UI", 9), activestyle="none",
                        highlightthickness=0, exportselection=False)
    gulung = ttk.Scrollbar(tengah, orient="vertical", command=daftar.yview)
    daftar.configure(yscrollcommand=gulung.set)
    daftar.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
    gulung.pack(side="left", fill="y", padx=(0, 6), pady=6)

    bawah = ttk.LabelFrame(win, text=" Isi catatan ")
    bawah.pack(fill="both", expand=True, padx=12, pady=(0, 6))
    isi = tk.Text(bawah, height=7, font=("Segoe UI", 10), wrap="word", state="disabled")
    isi.pack(fill="both", expand=True, padx=6, pady=6)

    kaki = ttk.Frame(win)
    kaki.pack(fill="x", padx=12, pady=(0, 12))
    tombol_bukti = ttk.Button(kaki, text="Buka catatan aslinya", state="disabled")
    tombol_bukti.pack(side="left")

    def tulis_isi(teks):
        isi.configure(state="normal")
        isi.delete("1.0", "end")
        isi.insert("end", teks)
        isi.configure(state="disabled")

    def terpilih():
        pilih = daftar.curselection()
        if not pilih:
            return None
        i = int(pilih[0])
        baris = hasil_ref["baris"]
        return baris[i] if 0 <= i < len(baris) else None

    def saat_pilih(*_):
        h = terpilih()
        if h is None:
            tombol_bukti.config(state="disabled")
            return
        tulis_isi(str(h.get("kutipan") or ""))
        # hanya episode yang punya catatan asli untuk dibuka
        tombol_bukti.config(state=("normal" if h.get("id_episode") else "disabled"))
    daftar.bind("<<ListboxSelect>>", saat_pilih)

    def gambar_hasil(jawab):
        tombol_cari.config(state="normal")
        hasil_ref["baris"] = list((jawab or {}).get("hasil") or [])
        daftar.delete(0, "end")
        for h in hasil_ref["baris"]:
            daftar.insert("end", baris_hasil_cari(h))
        catatan = pesan_sumber_cari((jawab or {}).get("sumber"))
        if hasil_ref["baris"]:
            lbl_info.config(text=str(len(hasil_ref["baris"])) + " catatan ditemukan"
                            + (" · " + catatan if catatan else ""), foreground="#6b7280")
            daftar.selection_clear(0, "end")
            daftar.selection_set(0)
            saat_pilih()
        else:
            # pesan dari cari() sudah berbahasa awam; messagebox galat di sini cuma menakuti
            lbl_info.config(text=str((jawab or {}).get("pesan") or "Tidak ada yang cocok."),
                            foreground="#b45309")
            tulis_isi("")
            tombol_bukti.config(state="disabled")
        tulis_log("cari: " + str((jawab or {}).get("pertanyaan") or "") + " → "
                  + str(len(hasil_ref["baris"])) + " hasil")

    def lakukan_cari(*_):
        teks = entri.get().strip()
        catat_pemakaian("cari-memori")
        tombol_cari.config(state="disabled")
        lbl_info.config(text="mencari…", foreground="#6b7280")
        daftar.delete(0, "end")
        hasil_ref["baris"] = []
        tulis_isi("")
        tombol_bukti.config(state="disabled")

        def kerja():
            # penyematan pertanyaan bisa makan 1–2 detik: di thread UI jendela membeku
            # dan Windows menandainya "Not Responding"
            try:
                jawab = cari(teks, gerbang=gerbang, store=store)
            except Exception:
                jawab = {"hasil": [], "pesan": "Pencarian gagal dijalankan. Coba sebentar lagi.",
                         "sumber": "galat", "pertanyaan": teks}
            root.after(0, _aman(win, lambda: gambar_hasil(jawab)))
        threading.Thread(target=kerja, daemon=True).start()

    def lakukan_buka_bukti():
        h = terpilih()
        if not h or not h.get("id_episode"):
            return
        id_episode = str(h["id_episode"])
        catat_pemakaian("buka-bukti")
        tombol_bukti.config(state="disabled")
        lbl_info.config(text="membuka catatan asli…", foreground="#6b7280")

        def kerja():
            try:
                bukti, pesan = app.gateway.buka_bukti(id_episode, sesi="panel"), None
            except Exception as e:
                bukti, pesan = None, pesan_galat_bukti(e)
            root.after(0, _aman(win, lambda: selesai_bukti(bukti, pesan)))
        threading.Thread(target=kerja, daemon=True).start()

    def selesai_bukti(bukti, pesan):
        tombol_bukti.config(state="normal")
        if bukti is None:
            lbl_info.config(text=str(pesan), foreground="#b45309")
            return
        tulis_isi(teks_bukti(bukti))
        lbl_info.config(text="catatan asli ditampilkan di bawah", foreground="#6b7280")

    tombol_cari.config(command=lakukan_cari)
    tombol_bukti.config(command=lakukan_buka_bukti)
    entri.bind("<Return>", lakukan_cari)
    entri.focus_set()
    return win


def jalankan(konfig: str | None = None) -> int:
    _alihkan_stdout_bila_perlu()
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox

    from . import __version__
    from .aplikasi import Aplikasi, muat_konfig

    siapkan_allowlist()  # ekspor INGAT_ALLOWED_EMAILS dari ~/.ingat/allowlist.txt sebelum konfig dibaca
    app = Aplikasi(muat_konfig(konfig))
    penanya_ref = {}  # simpan path tanya terakhir untuk tombol Jawab

    # Gerbang+store dibuka SEKALI di sini, bukan tiap pencarian: membuka SQLite dan memuat
    # vektor per klik membuat kotak cari terasa berat. Objek milik `app` dipakai apa adanya
    # (bukan cari_memori.buka_gerbang) karena itu objek yang sama, sudah hidup untuk server
    # in-process, dan menghormati --konfig yang dipilih Tuan Muda.
    cari_ref = {"gerbang": getattr(app, "gateway", None), "store": getattr(app, "store", None)}
    if cari_ref["gerbang"] is None:
        try:
            from .cari_memori import buka_gerbang
            cari_ref["gerbang"], cari_ref["store"] = buka_gerbang(app.konfig)
        except Exception:
            pass

    # ---- server in-process (daemon: mati saat panel ditutup) -----------------
    def _serve():
        try:
            from .api import jalankan_server
            jalankan_server(app)
        except OSError:
            print("[panel] serve: port 8765 sudah dipakai (mungkin auto-start lama) — pakai yang ada")
        except Exception as e:
            print("[panel] serve gagal:", e)

    def _pantau():
        try:
            from .pantau import layani_pantau
            layani_pantau(app, buka=False)
        except OSError:
            print("[panel] pantau: port 8790 sudah dipakai — pakai yang ada")
        except Exception as e:
            print("[panel] pantau gagal:", e)

    threading.Thread(target=_serve, daemon=True).start()
    threading.Thread(target=_pantau, daemon=True).start()

    # ---- GUI -----------------------------------------------------------------
    root = tk.Tk()
    root.title("ingat — Panel Kendali")
    root.geometry("580x660")
    root.minsize(520, 560)
    AKSEN = "#2563eb"

    kepala = tk.Frame(root, bg=AKSEN)
    kepala.pack(fill="x")
    tk.Label(kepala, text="  ingat", bg=AKSEN, fg="white",
             font=("Segoe UI Semibold", 14)).pack(side="left", pady=9)
    tk.Label(kepala, text="Panel Kendali · v" + __version__ + "   ", bg=AKSEN, fg="#dbe6ff",
             font=("Segoe UI", 9)).pack(side="right", pady=12)

    # -- status
    stat = ttk.LabelFrame(root, text=" Status ")
    stat.pack(fill="x", padx=12, pady=(12, 6))
    lbl_status = ttk.Label(stat, text="menghubungkan…", font=("Segoe UI", 10))
    lbl_status.pack(anchor="w", padx=10, pady=(6, 2))
    lbl_status2 = ttk.Label(stat, text="", foreground="#6b7280", font=("Segoe UI", 9))
    lbl_status2.pack(anchor="w", padx=10, pady=(0, 2))

    lbl_tinjau = ttk.Label(stat, text="", foreground="#b45309", font=("Segoe UI", 9), cursor="hand2")
    lbl_tinjau.pack(anchor="w", padx=10, pady=(0, 6))
    lbl_tinjau.bind("<Button-1>", lambda _: bangun_jendela_memori(root, app, tulis_log))

    def perbarui_tinjau():
        try:
            h = hitungan_tinjau(app.store)
            if h["total"] > 0:
                lbl_tinjau.config(text=f"⚠ {h['total']} memori perlu ditinjau ({h['pelajaran']} pelajaran, {h['prosedur']} prosedur)")
            else:
                lbl_tinjau.config(text="")
        except Exception:
            pass
        root.after(300_000, perbarui_tinjau)

    root.after(2000, perbarui_tinjau)

    # -- log
    def tulis_log(teks: str):
        log.configure(state="normal")
        log.insert("end", "[" + dt.datetime.now().strftime("%H:%M:%S") + "] " + teks + "\n")
        log.see("end")
        log.configure(state="disabled")

    def jalankan_aksi(nama, fn):
        """Jalankan aksi di worker thread; hasil ke log via root.after (aman thread)."""
        catat_pemakaian(nama)
        tulis_log("▶ " + nama + "…")

        def kerja():
            try:
                pesan = fn()
            except Exception as e:
                pesan = "GAGAL: " + str(e)
            root.after(0, lambda: tulis_log("  " + (pesan or "selesai")))
        threading.Thread(target=kerja, daemon=True).start()

    # -- aksi
    def aksi_konsolidasi():
        lap = app.konsolidator.jalankan("batch")
        lap["kedaluwarsa"] = app.konsolidator.kedaluwarsa()
        return "Konsolidasi: " + json.dumps(lap, ensure_ascii=False)

    def aksi_tanya():
        if not app.vault:
            return "vault tidak dikonfigurasi"
        from .tanya import Penanya
        pen = Penanya(app.store, app.vault, {"maks_pertanyaan": 7})
        daftar = pen.susun()
        path = pen.tulis(daftar)
        penanya_ref["path"] = path
        try:
            os.startfile(path)  # buka berkas tanya untuk diisi
        except Exception:
            pass
        return str(len(daftar)) + " pertanyaan → " + path + " (dibuka; isi lalu klik Jawab)"

    def aksi_jawab():
        if not app.vault:
            return "vault tidak dikonfigurasi"
        from .tanya import Penanya
        path = penanya_ref.get("path")
        if not path or not os.path.exists(path):
            return "belum ada berkas tanya — klik Tanya dulu"
        pen = Penanya(app.store, app.vault, {})
        return "Jawab: " + json.dumps(pen.jawab(path), ensure_ascii=False)

    def aksi_catatan():
        v = app.konfig.get("vault")
        if not v or not os.path.isdir(v):
            return "vault tidak ada: " + str(v)
        try:
            os.startfile(v)
            return "membuka folder vault: " + v
        except Exception as e:
            return "gagal buka: " + str(e)

    def buka(url, nama):
        catat_pemakaian(nama)
        webbrowser.open(url)
        tulis_log("↗ buka " + url)

    def aksi_catat():
        isi = kotak.get("1.0", "end").strip()
        if not isi:
            return "kosong — ketik sesuatu dulu"
        ep = app.store.tambah_episode(isi, sumber="panel", tier="I", lingkup="peran:asisten-ai",
                                      jenis_kejadian="sukses", ringkas=isi[:80])
        root.after(0, lambda: kotak.delete("1.0", "end"))
        return "dicatat: " + ep.id

    # -- jendela Koneksi AI (Fase 4): pusat kendali klien retail
    def buka_koneksi():
        catat_pemakaian("koneksi")
        bangun_jendela_koneksi(root, app, tulis_log)

    def buka_cari():
        catat_pemakaian("buka-cari")
        bangun_jendela_cari(root, app, tulis_log, cari_ref["gerbang"], cari_ref["store"])

    def buka_judul():
        catat_pemakaian("rapikan-nama")
        bangun_jendela_judul(root, app, tulis_log)

    def buka_memori():
        catat_pemakaian("kelola-memori")
        bangun_jendela_memori(root, app, tulis_log)

    def _jalankan_tag():
        from . import tag
        tulis_log("Memberi tag otomatis…")
        hasil = tag.tandai(app.store)
        tulis_log(f"Selesai: {hasil['ditulis']} episode ditandai dari {hasil['diproses']} total.")

    def _impor_screenpipe():
        from . import screenpipe
        st = screenpipe.status()
        if not st.get("terhubung"):
            tulis_log(f"Screenpipe: {st.get('pesan', 'tidak ditemukan')}")
            return
        tulis_log(f"Screenpipe terhubung: {st.get('layar', 0)} layar, {st.get('audio', 0)} audio")
        hasil = screenpipe.impor(app.store)
        tulis_log(f"Impor Screenpipe: {hasil['layar']} layar, {hasil['audio']} audio, {hasil['skip']} skip, {hasil['galat']} galat")

    # -- tombol utama (grid 3 kolom)
    tombol = ttk.Frame(root)
    tombol.pack(fill="x", padx=12, pady=6)
    for i in range(3):
        tombol.columnconfigure(i, weight=1)
    daftar_tombol = [
        ("Cari memori", buka_cari),
        ("Konsolidasi", lambda: jalankan_aksi("konsolidasi", aksi_konsolidasi)),
        ("Tanya", lambda: jalankan_aksi("tanya", aksi_tanya)),
        ("Jawab", lambda: jalankan_aksi("jawab", aksi_jawab)),
        ("Monitor", lambda: buka("http://127.0.0.1:8790/", "monitor")),
        ("Graf", lambda: buka("http://127.0.0.1:8790/graf", "graf")),
        ("Timeline", lambda: buka("http://127.0.0.1:8790/timeline", "timeline")),
        ("Digest", lambda: buka("http://127.0.0.1:8790/digest", "digest")),
        ("PWA", lambda: buka("http://127.0.0.1:8765/pwa", "pwa")),
        ("Buka catatan", lambda: jalankan_aksi("catatan", aksi_catatan)),
        ("Koneksi AI", buka_koneksi),
        ("Rapikan nama", buka_judul),
        ("Kelola memori", buka_memori),
        ("Tag otomatis", lambda: _jalankan_tag()),
        ("Screenpipe", lambda: _impor_screenpipe()),
    ]
    for idx, (teks, cmd) in enumerate(daftar_tombol):
        ttk.Button(tombol, text=teks, command=cmd).grid(
            row=idx // 3, column=idx % 3, sticky="ew", padx=4, pady=4, ipady=4)

    # -- tempel cepat
    cepat = ttk.LabelFrame(root, text=" Tempel cepat (catat episode) ")
    cepat.pack(fill="x", padx=12, pady=6)
    kotak = tk.Text(cepat, height=3, font=("Segoe UI", 10), wrap="word")
    kotak.pack(fill="x", padx=8, pady=(8, 4))
    ttk.Button(cepat, text="Catat", command=lambda: jalankan_aksi("catat", aksi_catat)).pack(
        anchor="e", padx=8, pady=(0, 8))

    # -- otomasi: konsolidasi terjadwal (Fase 2)
    prefs = muat_prefs()
    jadwal_ref = {"id": None}
    auto_var = tk.BooleanVar(value=prefs["auto_konsolidasi"])
    interval_var = tk.StringVar()

    def _label_interval(jam):
        for teks, j in INTERVAL_PILIHAN:
            if j == jam:
                return teks
        return "Tiap 6 jam"

    interval_var.set(_label_interval(prefs["interval_jam"]))

    def _jam_terpilih():
        for teks, j in INTERVAL_PILIHAN:
            if teks == interval_var.get():
                return j
        return 0

    def perbarui_label_auto():
        p = muat_prefs()
        t = p.get("terakhir_konsolidasi")
        lbl_auto.config(text="terakhir: " + (t[11:16] if t else "—"))

    def jalankan_auto():
        catat_pemakaian("auto-konsolidasi")
        tulis_log("▶ auto-konsolidasi…")

        def kerja():
            try:
                pesan = aksi_konsolidasi()
            except Exception as e:
                pesan = "GAGAL: " + str(e)
            def selesai():
                tulis_log("  " + pesan)
                p = muat_prefs()
                p["terakhir_konsolidasi"] = dt.datetime.now().isoformat(timespec="seconds")
                simpan_prefs(p)
                perbarui_label_auto()
            root.after(0, selesai)
        threading.Thread(target=kerja, daemon=True).start()
        jadwalkan_auto()  # rantai siklus berikutnya

    def jadwalkan_auto():
        if jadwal_ref["id"] is not None:
            try:
                root.after_cancel(jadwal_ref["id"])
            except Exception:
                pass
            jadwal_ref["id"] = None
        if auto_var.get():
            ms = interval_ms(_jam_terpilih())
            if ms > 0:
                jadwal_ref["id"] = root.after(ms, jalankan_auto)

    def simpan_dan_jadwalkan(*_):
        p = muat_prefs()
        p["auto_konsolidasi"] = bool(auto_var.get())
        p["interval_jam"] = _jam_terpilih()
        simpan_prefs(p)
        jadwalkan_auto()
        aktif = auto_var.get() and _jam_terpilih() > 0
        tulis_log("otomasi: " + (interval_var.get().lower() if aktif else "mati"))

    otom = ttk.LabelFrame(root, text=" Otomasi ")
    otom.pack(fill="x", padx=12, pady=6)
    baris = ttk.Frame(otom)
    baris.pack(fill="x", padx=8, pady=8)
    ttk.Checkbutton(baris, text="Konsolidasi otomatis", variable=auto_var,
                    command=simpan_dan_jadwalkan).pack(side="left")
    cb = ttk.Combobox(baris, textvariable=interval_var, state="readonly", width=12,
                      values=[t for t, _ in INTERVAL_PILIHAN])
    cb.pack(side="left", padx=8)
    cb.bind("<<ComboboxSelected>>", simpan_dan_jadwalkan)
    lbl_auto = ttk.Label(baris, text="terakhir: —", foreground="#6b7280", font=("Segoe UI", 9))
    lbl_auto.pack(side="left", padx=8)

    # -- nyala otomatis saat Windows menyala
    # Keadaan centang dibaca dari DISK (ada/tidaknya pintasan), BUKAN dari panel-prefs.json:
    # kalau Tuan Muda menghapus pintasannya lewat File Explorer, centang harus ikut mati.
    st_startup_awal = status_startup_aman()
    startup_var = tk.BooleanVar(value=bool(st_startup_awal.get("aktif")))
    alih_startup_ref = {"jalan": False}

    def alih_nyala_otomatis():
        nyala = bool(startup_var.get())
        catat_pemakaian("startup")
        alih_startup_ref["jalan"] = True
        tulis_log("▶ nyala otomatis: " + ("menghidupkan" if nyala else "mematikan") + "…")

        def kerja():
            # Jalur .lnk memanggil PowerShell (timeout 30 dtk) — di thread UI panel akan membeku.
            from . import startup
            try:
                pesan = pesan_alih_startup(nyala, startup.alih_startup(nyala))
            except Exception:
                pesan = ("GAGAL mengubah nyala otomatis. Coba sekali lagi, atau atur sendiri lewat "
                         "folder Startup Windows.")
            root.after(0, lambda: selesai_startup(pesan))

        def selesai_startup(pesan):
            # Centang selalu dikembalikan ke keadaan NYATA di disk supaya tak berbohong saat gagal.
            st = status_startup_aman()
            startup_var.set(bool(st.get("aktif")))
            alih_startup_ref["jalan"] = False
            tulis_log("  " + pesan)
            peringat = pesan_lawas_startup(st)
            if peringat:
                tulis_log("  " + peringat)
        threading.Thread(target=kerja, daemon=True).start()

    baris2 = ttk.Frame(otom)
    baris2.pack(fill="x", padx=8, pady=(0, 8))
    ttk.Checkbutton(baris2, text="Nyala otomatis saat Windows menyala", variable=startup_var,
                    command=alih_nyala_otomatis).pack(side="left")

    # -- log
    logf = ttk.LabelFrame(root, text=" Aktivitas ")
    logf.pack(fill="both", expand=True, padx=12, pady=(6, 12))
    log = scrolledtext.ScrolledText(logf, height=6, font=("Consolas", 9), state="disabled", wrap="word")
    log.pack(fill="both", expand=True, padx=6, pady=6)

    # ---- pembaruan status berkala ----
    def segarkan_status():
        try:
            m = app.store.ringkasan_metrik()
            mode = "relay (baca-saja)" if getattr(app, "relay", False) else "otoritatif"
            e = app.konfig.get("embedding", {}) or {}
            alarm = m.get("alarm") or []
            sehat = "⚠ " + str(len(alarm)) + " alarm" if alarm else "✓ sehat"
            lbl_status.config(text="● {epi} episode · {pel} pelajaran · {pro} prosedur   [{sehat}]".format(
                epi=m.get("episode_aktif", 0),
                pel=sum(m.get(k, 0) for k in m if k.startswith("pelajaran_")),
                pro=sum(m.get(k, 0) for k in m if k.startswith("prosedur_")),
                sehat=sehat))
            try:
                from .kesehatan import ringkasan as _ring_kes
                kes = _ring_kes()
                lampu_kes = kes.get("lampu", "hijau")
                ikon_kes = {"hijau": "✓", "kuning": "⚠", "merah": "✗"}.get(lampu_kes, "?")
                teks_kes = f" · kesehatan {ikon_kes}"
            except Exception:
                teks_kes = ""
            lbl_status2.config(text="mode {m} · {j}:{mo} · server 8765/8790 · {t}{kes}".format(
                m=mode, j=e.get("jenis", "?"), mo=e.get("model", "?"),
                t=dt.datetime.now().strftime("%H:%M:%S"), kes=teks_kes))
        except Exception as ex:
            lbl_status.config(text="status gagal: " + str(ex))
        # Centang nyala-otomatis ikut disegarkan: pintasan bisa dihapus dari File Explorer
        # saat panel hidup. Dilewati selagi ada perubahan berjalan supaya tak saling timpa.
        if not alih_startup_ref["jalan"]:
            aktif = bool(status_startup_aman().get("aktif"))
            if aktif != bool(startup_var.get()):
                startup_var.set(aktif)
        root.after(5000, segarkan_status)

    tulis_log("Panel siap. Server serve(8765) + pantau(8790) berjalan in-process.")
    peringat_awal = pesan_lawas_startup(st_startup_awal)
    if peringat_awal:
        tulis_log(peringat_awal)
    perbarui_label_auto()
    jadwalkan_auto()
    if auto_var.get() and _jam_terpilih() > 0:
        tulis_log("otomasi: konsolidasi " + interval_var.get().lower())
    segarkan_status()
    root.mainloop()
    return 0
