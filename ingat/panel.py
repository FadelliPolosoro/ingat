# SPDX-License-Identifier: Apache-2.0
"""ingat — Panel Kendali (K29). Aplikasi desktop Tkinter (stdlib, nol-dependency).

Sikap K29: PANEL KENDALI, bukan tiruan Obsidian. Visual kaya (graf, kartu) didelegasikan ke
dashboard web yang dibuka lewat tombol. Server serve(8765)+pantau(8790) berjalan IN-PROCESS
(daemon thread) sehingga ini satu aplikasi mandiri — tak perlu .cmd/.vbs auto-start lagi.
Prioritas fungsi (K29 §2): 1) konsolidasi+jawab 2) status 3) buka Obsidian 4) tempel cepat.
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
    win.geometry("580x600")
    win.minsize(520, 520)

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

    f2 = ttk.LabelFrame(win, text=" Status klien (rekam episode terakhir) ")
    f2.pack(fill="both", expand=True, padx=12, pady=6)
    box = tk.Text(f2, height=7, font=("Consolas", 9), state="disabled", wrap="none")
    box.pack(fill="both", expand=True, padx=6, pady=(6, 2))

    def muat_status():
        try:
            data = status_koneksi(app.store)
            pesan_e = ""
        except Exception as e:
            data = None
            pesan_e = str(e)
        box.configure(state="normal"); box.delete("1.0", "end")
        if data is None:
            box.insert("end", "gagal baca store: " + pesan_e + "\n")
        else:
            for d in data:
                t = d["terakhir"]
                tampil_t = t[:16].replace("T", " ") if t else "belum ada rekam"
                box.insert("end", "{tn} {nm:<16} [{jl:<3}]  {tt}\n".format(
                    tn=("●" if t else "○"), nm=d["nama"], jl=d["jalur"], tt=tampil_t))
        box.configure(state="disabled")

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

    f4 = ttk.LabelFrame(win, text=" Sambungkan (langkah manual di browser / Claude Desktop) ")
    f4.pack(fill="x", padx=12, pady=(6, 12))

    def pasang_ekstensi():
        try:
            p = siapkan_ekstensi()
            tulis_log("ekstensi disiapkan: " + p)
            try:
                os.startfile(p)
            except Exception:
                pass
            messagebox.showinfo("Ekstensi web siap",
                "Folder ekstensi:\n" + p +
                "\n\n1. Buka chrome://extensions (atau edge://extensions)\n"
                "2. Nyalakan Developer mode\n"
                "3. Load unpacked → pilih folder di atas\n"
                "4. Buka Opsi ekstensi, isi Host + Token (pakai tombol Salin di jendela ini)\n"
                "5. Claude.ai & Perplexity: isi selektor di Opsi (ChatGPT sudah bawaan)")
        except Exception as e:
            messagebox.showerror("Gagal menyiapkan ekstensi", str(e))

    def pasang_mcpb():
        try:
            p = siapkan_mcpb()
            tulis_log("mcpb disiapkan: " + p)
            try:
                os.startfile(p)
            except Exception:
                pass
            messagebox.showinfo("MCPB — Claude Desktop",
                "Folder MCPB:\n" + p +
                "\n\nDi Claude Desktop: Settings → Extensions → Advanced →\n"
                "Extension Developer → Install Extension… → pilih berkas .mcpb,\n"
                "lalu restart Claude Desktop. Baca README di folder ini.")
        except Exception as e:
            messagebox.showerror("Gagal menyiapkan MCPB", str(e))

    ttk.Button(f4, text="Siapkan ekstensi web", command=pasang_ekstensi).pack(side="left", padx=8, pady=8)
    ttk.Button(f4, text="Siapkan MCPB (Claude Desktop)", command=pasang_mcpb).pack(side="left", padx=8, pady=8)
    return win


def jalankan(konfig: str | None = None) -> int:
    _alihkan_stdout_bila_perlu()
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox

    from . import __version__
    from .aplikasi import Aplikasi, muat_konfig

    app = Aplikasi(muat_konfig(konfig))
    penanya_ref = {}  # simpan path tanya terakhir untuk tombol Jawab

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
    lbl_status2.pack(anchor="w", padx=10, pady=(0, 8))

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

    def aksi_obsidian():
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

    # -- tombol utama (grid 3 kolom)
    tombol = ttk.Frame(root)
    tombol.pack(fill="x", padx=12, pady=6)
    for i in range(3):
        tombol.columnconfigure(i, weight=1)
    daftar_tombol = [
        ("Konsolidasi", lambda: jalankan_aksi("konsolidasi", aksi_konsolidasi)),
        ("Tanya", lambda: jalankan_aksi("tanya", aksi_tanya)),
        ("Jawab", lambda: jalankan_aksi("jawab", aksi_jawab)),
        ("Monitor", lambda: buka("http://127.0.0.1:8790/", "monitor")),
        ("Graf", lambda: buka("http://127.0.0.1:8790/graf", "graf")),
        ("Buka Obsidian", lambda: jalankan_aksi("obsidian", aksi_obsidian)),
        ("Koneksi AI", buka_koneksi),
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
            lbl_status2.config(text="mode {m} · {j}:{mo} · server 8765/8790 · {t}".format(
                m=mode, j=e.get("jenis", "?"), mo=e.get("model", "?"),
                t=dt.datetime.now().strftime("%H:%M:%S")))
        except Exception as ex:
            lbl_status.config(text="status gagal: " + str(ex))
        root.after(5000, segarkan_status)

    tulis_log("Panel siap. Server serve(8765) + pantau(8790) berjalan in-process.")
    perbarui_label_auto()
    jadwalkan_auto()
    if auto_var.get() and _jam_terpilih() > 0:
        tulis_log("otomasi: konsolidasi " + interval_var.get().lower())
    segarkan_status()
    root.mainloop()
    return 0
