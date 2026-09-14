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


def jalankan(konfig: str | None = None) -> int:
    _alihkan_stdout_bila_perlu()
    import tkinter as tk
    from tkinter import ttk, scrolledtext

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
    root.geometry("580x560")
    root.minsize(520, 480)
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
    segarkan_status()
    root.mainloop()
    return 0
