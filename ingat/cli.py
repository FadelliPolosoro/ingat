# SPDX-License-Identifier: Apache-2.0
"""CLI: python -m ingat <perintah>"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, __penulis__, skema
from .aplikasi import Aplikasi, muat_konfig


def _paksa_stdout_utf8() -> None:
    """Paksa stdout/stderr ke UTF-8 supaya json.dumps(ensure_ascii=False) tidak
    jatuh di konsol Windows (cp1252) saat keluaran memuat karakter non-cp1252,
    mis. bendera '⚑' dari hasil `ingat ingat`. Berlaku untuk SEMUA perintah
    yang mencetak json.dumps, bukan satu perintah saja.

    Di uji, stdout diganti io.StringIO yang tidak punya .reconfigure -> dilewati.
    """
    for aliran in (sys.stdout, sys.stderr):
        rekonf = getattr(aliran, "reconfigure", None)
        if rekonf is None:
            continue
        try:
            rekonf(encoding="utf-8")
        except (ValueError, OSError):
            pass


def utama(argv: list[str] | None = None) -> int:
    _paksa_stdout_utf8()
    p = argparse.ArgumentParser(prog="ingat", description=f"ingat v{__version__} — sistem memori agent · dibuat oleh {__penulis__}")
    p.add_argument("--konfig", help="path konfigurasi.json (default: env INGAT_KONFIG atau ./konfigurasi.json)")
    sub = p.add_subparsers(dest="perintah", required=True)
    sub.add_parser("serve", help="jalankan REST API")
    sub.add_parser("mcp", help="jalankan MCP server (stdio)")
    ps = sub.add_parser("pasang", help="pasang hook Claude Code, /koreksi, MCP, dan konfigurasi default (cetak dulu; --tulis untuk menulis)")
    ps.add_argument("--tulis", action="store_true")
    t = sub.add_parser("tanya", help="susun pertanyaan konsolidasi dari data (v0.5) -> pelajaran/_usulan/tanya-<tanggal>.md")
    t.add_argument("--maks", type=int, default=7, help="jumlah pertanyaan maksimal per berkas")
    j = sub.add_parser("jawab", help="terapkan jawaban dari berkas tanya ke vault, lalu sinkron")
    j.add_argument("--berkas", required=True, help="path berkas tanya-*.md yang sudah diisi")
    k = sub.add_parser("konsolidasi", help="jalankan job konsolidasi")
    k.add_argument("--cepat", action="store_true", help="jalur cepat: hanya episode bobot >= 3")
    sub.add_parser("sinkron", help="sinkron vault Obsidian -> store")
    sub.add_parser("bangun-ulang-vektor", help="semat ulang semua item dengan penyemat di konfigurasi sekarang "
                                               "(satu-satunya jalan keluar dari IdentitasEmbedderTidakCocok, K8/K9)")
    e = sub.add_parser("ekspor", help="ekspor semua episode + isi verbatim ke JSON portabel (K30, pindah mesin)")
    e.add_argument("--keluar", default="-", help="berkas tujuan; '-' = stdout")
    im = sub.add_parser("impor", help="impor episode dari berkas ekspor ke store ini (K30)")
    im.add_argument("--berkas", required=True)
    im.add_argument("--timpa", action="store_true", help="timpa episode ber-id yang sudah ada (default: dilewati)")
    bk = sub.add_parser("backup", help="bungkus store+vault+konfigurasi jadi tarball portabel + SHA-256 (A1, pindah perangkat)")
    bk.add_argument("--rumah", default=os.path.expanduser("~/.ingat"), help="folder ingat sumber (default ~/.ingat)")
    bk.add_argument("--keluar", default=None, help="tarball tujuan (default <rumah>/backup/ingat-backup-<waktu>.tar.gz)")
    bk.add_argument("--sandi", default=None, help="enkripsi tarball dengan sandi (K28: wajib sebelum upload)")
    bk.add_argument("--vps", action="store_true", help="setelah backup, langsung unggah ke VPS via SCP")
    bk.add_argument("--host", default="ingat-vps", help="alias SSH VPS (default: ingat-vps)")
    bk.add_argument("--dir-tujuan", default="/opt/ingat/backup", help="folder tujuan di VPS")
    rs = sub.add_parser("restore", help="pulihkan tarball backup ke folder ingat perangkat baru (A1)")
    rs.add_argument("--berkas", required=True, help="tarball backup")
    rs.add_argument("--target", default=os.path.expanduser("~/.ingat"), help="folder ingat tujuan (default ~/.ingat)")
    rs.add_argument("--timpa", action="store_true", help="timpa data/vault yang sudah ada di target")
    rs.add_argument("--tanpa-verifikasi", action="store_true", help="lewati verifikasi checksum SHA-256")
    rs.add_argument("--sandi", default=None, help="sandi dekripsi (wajib bila backup terenkripsi)")
    rs.add_argument("--tanpa-konfig", action="store_true",
                    help="jangan timpa konfigurasi.json target (WAJIB saat sinkron data ke mesin lain)")
    rk = sub.add_parser("rekon", help="rekonsiliasi store ↔ vault: deteksi & perbaiki divergensi (C)")
    rk.add_argument("--perbaiki", action="store_true", help="perbaiki (bukan hanya lapor)")
    rk.add_argument("--rumah", default=os.path.expanduser("~/.ingat"), help="folder ingat (default ~/.ingat)")
    ic = sub.add_parser("impor-claude", help="impor 'chat terdahulu' Claude Code dari transkrip lokal ~/.claude/projects (Jalur A, tanpa ekspor)")
    ic.add_argument("--dir", default=None, help="folder transkrip (default: ~/.claude/projects)")
    ic.add_argument("--lingkup", default=None, help="paksa lingkup untuk semua (mis. peran:asisten-ai); default: per-proyek dari cwd transkrip")
    ic.add_argument("--tulis", action="store_true", help="benar-benar tulis (default: kering — cetak rencana saja)")
    ie = sub.add_parser("impor-ekspor", help="impor dari file ekspor resmi Claude.ai / ChatGPT (Jalur A, ZIP atau JSON)")
    ie.add_argument("berkas", help="path ke file ZIP atau conversations.json")
    ie.add_argument("--lingkup", default=None, help="paksa lingkup")
    ie.add_argument("--tulis", action="store_true", help="benar-benar tulis (default: kering)")
    sub.add_parser("kesehatan", help="ringkasan kesehatan koneksi situs AI")
    c = sub.add_parser("catat", help="catat episode dari CLI")
    c.add_argument("--isi", required=True)
    c.add_argument("--ringkas", required=True)
    c.add_argument("--lingkup", required=True)
    c.add_argument("--jenis", default="sukses", choices=skema.JENIS_KEJADIAN)
    c.add_argument("--tier", default="I", choices=["P", "I", "S"])  # K10/K11: default I; S tersimpan dengan pagar
    c.add_argument("--sumber", default="cli")
    c.add_argument("--instrumen", nargs="*", default=[])
    i = sub.add_parser("instrumen", help="daftarkan instrumen baru (7.4)")
    i.add_argument("--id", required=True)
    i.add_argument("--nama", required=True)
    i.add_argument("--cakupan", default="")
    i.add_argument("--dipasang", default=None)
    t = sub.add_parser("ingat", help="uji retrieval dari CLI")
    t.add_argument("--query", required=True)
    t.add_argument("--lingkup", required=True)
    t.add_argument("--tanggal", default=None)
    t.add_argument("--tugas", default=None)
    sub.add_parser("startup", help="tampilkan L-peta + L-aturan").add_argument("--lingkup", required=True)
    sub.add_parser("metrik", help="ringkasan metrik")
    sub.add_parser("panel", help="buka Panel Kendali desktop (GUI Tkinter, K29): status + konsolidasi/tanya/jawab + tempel cepat, server in-process")
    pt = sub.add_parser("pantau", help="monitor visual store di browser (localhost, baca-saja, tanpa auth)")
    pt.add_argument("--host", default="127.0.0.1", help="hanya loopback (127.0.0.1/localhost/::1)")
    pt.add_argument("--port", type=int, default=8790)
    pt.add_argument("--tanpa-buka", action="store_true", help="jangan buka browser otomatis")
    sub.add_parser("uji", help="jalankan uji putar-ulang U1–U9")
    tok = sub.add_parser("token", help="kelola token autentikasi (tampil/buat/set)")
    tok.add_argument("--buat", action="store_true", help="buat token baru, simpan ke ~/.ingat/token")
    tok.add_argument("--set", dest="set_val", metavar="TOKEN", help="simpan token spesifik ke ~/.ingat/token")
    t2 = sub.add_parser("totp-atur", help="atur verifikasi dua langkah mandiri (K26) — tanpa Google")
    t2.add_argument("--tulis-env", action="store_true", help="tulis/perbarui INGAT_TOTP_RAHASIA langsung ke .env")
    j = sub.add_parser("jadwal", help="penjadwal konsolidasi: harian pada jam tertentu + saat episode aktif >= ambang (7.1)")
    j.add_argument("--jam", default="02:00", help="jam lokal HH:MM (default 02:00)")
    j.add_argument("--ambang", type=int, default=50)
    j.add_argument("--interval", type=int, default=600, help="detik antar pemeriksaan (default 600)")
    a = p.parse_args(argv)

    if a.perintah == "token":
        from .jauh import baca_token
        import secrets
        berkas_token = os.path.expanduser("~/.ingat/token")
        if a.set_val:
            val = a.set_val.strip()
            if len(val) < 24:
                print("Token terlalu pendek (minimal 24 karakter).")
                return 1
            os.makedirs(os.path.dirname(berkas_token), exist_ok=True)
            with open(berkas_token, "w", encoding="utf-8") as f:
                f.write(val + "\n")
            print(f"Token disimpan ke {berkas_token}")
            return 0
        if a.buat:
            val = secrets.token_urlsafe(36)
            os.makedirs(os.path.dirname(berkas_token), exist_ok=True)
            with open(berkas_token, "w", encoding="utf-8") as f:
                f.write(val + "\n")
            print(f"Token baru disimpan ke {berkas_token}")
            print(f"Nilai: {val}")
            return 0
        t = os.environ.get("INGAT_TOKEN", "").strip()
        if t:
            print(f"Token aktif: {t[:6]}...{t[-4:]}  (sumber: env INGAT_TOKEN)")
            return 0
        if os.path.isfile(berkas_token):
            with open(berkas_token, encoding="utf-8") as f:
                t = f.read().strip()
            if t:
                print(f"Token aktif: {t[:6]}...{t[-4:]}  (sumber: ~/.ingat/token)")
                return 0
        t = baca_token(None)
        if t:
            print(f"Token aktif: {t[:6]}...{t[-4:]}  (sumber: konfigurasi)")
            return 0
        print("Belum ada token. Jalankan: ingat token --buat")
        return 1
    if a.perintah == "totp-atur":
        from .auth_totp import buat_rahasia, otpauth_url, kode_sekarang
        rahasia = buat_rahasia()
        print("=== Verifikasi dua langkah MANDIRI (K26) — tidak bergantung Google sama sekali ===")
        print()
        print(f"Rahasia (base32): {rahasia}")
        print(f"URI otpauth      : {otpauth_url(rahasia, akun_label='pemilik')}")
        print()
        print("Cara pasang:")
        print("  1. Buka aplikasi authenticator apa pun (Google Authenticator, Authy, Bitwarden, 1Password, dll.)")
        print("     — semuanya memakai standar terbuka yang sama, bukan produk Google tertentu.")
        print("  2. Pilih 'Tambah akun manual' / 'Enter setup key', tempel Rahasia di atas (bukan URI-nya).")
        print("  3. Verifikasi: kode yang tampil di aplikasimu sekarang harus sama dengan ini:")
        print(f"     {kode_sekarang(rahasia)}  (berlaku ~30 detik dari sekarang)")
        print()
        print("PENTING: rahasia ini hanya tampil SEKALI di sini. Simpan aman — siapa pun yang punya rahasia")
        print("ini bisa menghasilkan kode valid selamanya. Jangan tempel ke chat, tiket, atau screenshot.")
        if a.tulis_env:
            import re
            jalur = ".env"
            if os.path.exists(jalur):
                isi = open(jalur, encoding="utf-8").read()
                if "INGAT_TOTP_RAHASIA=" in isi:
                    isi = re.sub(r"^INGAT_TOTP_RAHASIA=.*$", f"INGAT_TOTP_RAHASIA={rahasia}", isi, flags=re.M)
                else:
                    isi = isi.rstrip("\n") + f"\nINGAT_TOTP_RAHASIA={rahasia}\n"
                open(jalur, "w", encoding="utf-8").write(isi)
                print(f"\nDitulis ke {jalur}. Restart server: docker compose restart ingat")
            else:
                print(f"\n{jalur} tidak ditemukan di direktori ini — tempel manual baris ini ke .env:")
                print(f"INGAT_TOTP_RAHASIA={rahasia}")
        else:
            print(f"\nTempel manual ke .env:  INGAT_TOTP_RAHASIA={rahasia}")
        return 0
    if a.perintah == "uji":
        import unittest
        hasil = unittest.main(module="uji.uji_putar_ulang", argv=["uji"], exit=False, verbosity=2).result
        return 0 if hasil.wasSuccessful() else 1
    if a.perintah == "pasang":
        # Tidak butuh Store/Aplikasi sama sekali — pasang.py murni memanipulasi berkas konfigurasi.
        # Dipindah ke atas (sebelum Aplikasi dibuat) supaya TIDAK membuat ./data/ingat.sqlite kosong
        # sebagai efek samping tak sengaja. Bug ini ditemukan 8 Sep 2026: menjalankan `ingat pasang`
        # di folder proyek (tanpa --konfig) meninggalkan data/ kosong yang ikut ter-zip ke distribusi.
        from .pasang import pasang
        print(json.dumps(pasang(tulis=a.tulis), ensure_ascii=False, indent=2))
        return 0
    if a.perintah == "backup":
        from .backup import buat_backup, unggah_ke_vps
        meta = buat_backup(a.rumah, a.keluar, sandi=a.sandi)
        print(json.dumps({k: meta.get(k) for k in ("berkas", "sha256", "ukuran", "waktu", "ingat_versi", "jumlah", "terenkripsi")},
                         ensure_ascii=False, indent=2))
        if a.vps:
            hasil = unggah_ke_vps(meta["berkas"], host=a.host, dir_tujuan=a.dir_tujuan)
            print(json.dumps(hasil, ensure_ascii=False, indent=2))
        return 0
    if a.perintah == "restore":
        # Dijalankan di perangkat BARU: store belum ada, Ollama mungkin belum jalan — maka
        # jangan bangun Aplikasi (yang akan mati membuka Store yang belum ada).
        from .backup import pulihkan_backup
        lap = pulihkan_backup(a.berkas, a.target, timpa=a.timpa,
                              verifikasi=not a.tanpa_verifikasi, sandi=a.sandi,
                              pulihkan_konfig=not a.tanpa_konfig)
        print(json.dumps({k: lap.get(k) for k in ("dipulihkan_ke", "waktu", "ingat_versi", "versi_backup",
                                                  "jumlah", "konfig_dipulihkan")},
                         ensure_ascii=False, indent=2))
        return 0
    if a.perintah == "rekon":
        from .rekonsiliasi import periksa, perbaiki
        from .simpan import Store
        dir_data = os.path.join(a.rumah, "data")
        vault_path = os.path.join(a.rumah, "vault")
        if not os.path.isdir(dir_data):
            print(f"Store tidak ditemukan: {dir_data}")
            return 1
        st = Store.__new__(Store)
        import sqlite3 as _sql
        st.dir_data = dir_data
        st.db = _sql.connect(os.path.join(dir_data, "ingat.sqlite"))
        st.db.row_factory = _sql.Row
        try:
            vp = vault_path if os.path.isdir(vault_path) else None
            if a.perbaiki:
                from .obsidian import Vault
                v = Vault(vault_path) if vp else None
                lap = perbaiki(st, vp, v)
                print(json.dumps(lap, ensure_ascii=False, indent=2))
            else:
                lap = periksa(st, vp)
                print(json.dumps(lap, ensure_ascii=False, indent=2))
        finally:
            st.db.close()
        return 0

    # Bendera dipasang SEBELUM Store dibuka: Aplikasi membuka Store di __init__, jadi tanpa ini
    # perintah pemulihan justru mati oleh galat yang hendak dipulihkannya.
    app = Aplikasi(muat_konfig(a.konfig), bangun_ulang_vektor=(a.perintah == "bangun-ulang-vektor"))
    if a.perintah == "bangun-ulang-vektor":
        n = {j: len(f()) for j, f in (("episode", app.store.episode_semua), ("pelajaran", app.store.pelajaran_semua),
                                      ("prosedur", app.store.prosedur_semua), ("norma", app.store.norma_semua))}
        ident = [dict(r) for r in app.store.db.execute("SELECT koleksi, model, dimensi FROM identitas_embedder")]
        print(json.dumps({"disemat_ulang": n, "identitas_sekarang": ident}, ensure_ascii=False, indent=2))
    elif a.perintah == "serve":
        from .api import jalankan_server
        jalankan_server(app)
    elif a.perintah == "mcp":
        from .mcp_stdio import layani
        layani(app)
    elif a.perintah == "konsolidasi":
        hasil = app.konsolidator.jalankan("cepat" if a.cepat else "batch")
        hasil["kedaluwarsa"] = app.konsolidator.kedaluwarsa()
        print(json.dumps(hasil, ensure_ascii=False, indent=2))
    elif a.perintah in ("tanya", "jawab"):
        if not app.vault:
            print(json.dumps({"galat": "vault tidak dikonfigurasi"}, ensure_ascii=False))
            return 1
        from .tanya import Penanya
        penanya = Penanya(app.store, app.vault, {"maks_pertanyaan": getattr(a, "maks", 7)})
        if a.perintah == "tanya":
            daftar = penanya.susun()
            path = penanya.tulis(daftar)
            print(json.dumps({"jumlah": len(daftar), "berkas": path,
                              "pertanyaan": [{"nomor": q.nomor, "jenis": q.jenis, "id": q.id, "prioritas": q.prioritas} for q in daftar]},
                             ensure_ascii=False, indent=2))
        else:
            print(json.dumps(penanya.jawab(a.berkas), ensure_ascii=False, indent=2))
    elif a.perintah == "sinkron":
        print(json.dumps(app.sinkron_vault(), ensure_ascii=False, indent=2))
    elif a.perintah == "ekspor":
        from . import pindah
        data = pindah.ekspor(app.store)
        if a.keluar == "-":
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            with open(a.keluar, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(json.dumps({"berkas": a.keluar, "jumlah": data["jumlah"], "embedder": data["embedder"]}, ensure_ascii=False))
    elif a.perintah == "impor":
        from . import pindah
        # K30: relay adalah baca-saja — mengimpor episode ke relay melanggar "tier S tak keluar laptop".
        if app.relay:
            print(json.dumps({"galat": "instans ini relay (baca-saja, K30); impor episode hanya ke store otoritatif laptop"}, ensure_ascii=False))
            return 1
        with open(a.berkas, encoding="utf-8") as f:
            data = json.load(f)
        print(json.dumps(pindah.impor(app.store, data, lewati_ada=not a.timpa), ensure_ascii=False, indent=2))
    elif a.perintah == "impor-claude":
        from .impor_claude import impor_histori
        print(json.dumps(impor_histori(app, root=a.dir, tulis=a.tulis, lingkup_paksa=a.lingkup), ensure_ascii=False, indent=2))
    elif a.perintah == "impor-ekspor":
        from .impor_ekspor import impor_ekspor as _impor_ekspor
        print(json.dumps(_impor_ekspor(app, a.berkas, tulis=a.tulis, lingkup_paksa=a.lingkup), ensure_ascii=False, indent=2))
    elif a.perintah == "kesehatan":
        from .kesehatan import ringkasan as _ringkasan_kesehatan
        print(json.dumps(_ringkasan_kesehatan(), ensure_ascii=False, indent=2))
    elif a.perintah == "catat":
        ep = app.store.tambah_episode(a.isi, sumber=a.sumber, tier=a.tier, lingkup=a.lingkup, jenis_kejadian=a.jenis,
                                      ringkas=a.ringkas, instrumen=a.instrumen)
        print(json.dumps({"id": ep.id, "bobot": ep.bobot}, ensure_ascii=False))
    elif a.perintah == "instrumen":
        print(json.dumps(app.konsolidator.instrumen_baru(skema.Instrumen(id=a.id, nama=a.nama, dipasang_sejak=a.dipasang, cakupan=a.cakupan)), ensure_ascii=False, indent=2))
    elif a.perintah == "ingat":
        print(json.dumps(app.gateway.ingat(a.query, a.lingkup, tanggal_peristiwa=a.tanggal, tugas=a.tugas), ensure_ascii=False, indent=2))
    elif a.perintah == "startup":
        print(json.dumps(app.gateway.muat_startup(a.lingkup), ensure_ascii=False, indent=2))
    elif a.perintah == "metrik":
        print(json.dumps(app.store.ringkasan_metrik(), ensure_ascii=False, indent=2))
    elif a.perintah == "pantau":
        from .pantau import layani_pantau
        return layani_pantau(app, a.host, a.port, buka=not a.tanpa_buka)
    elif a.perintah == "panel":
        from .panel import jalankan
        return jalankan(a.konfig)
    elif a.perintah == "jadwal":
        _jadwal(app, a.jam, a.ambang, a.interval)
    return 0


def _jadwal(app: Aplikasi, jam: str, ambang: int, interval: int):
    """Loop sederhana tanpa cron: batch harian pada `jam` + batch saat episode aktif >= ambang."""
    import datetime as dt
    import time
    hh, mm = (int(x) for x in jam.split(":"))
    terakhir_harian = None
    print(f"[ingat jadwal] harian {jam} · ambang {ambang} episode · interval {interval}s")
    while True:
        kini = dt.datetime.now()
        if app.vault:
            try:
                app.sinkron_vault()  # K30: di relay, tier_maks:S dilewati
            except Exception as e:
                print(f"[ingat jadwal] sinkron gagal: {e}")
        aktif = app.store.ringkasan_metrik()["episode_aktif"]
        harian = (kini.hour, kini.minute) >= (hh, mm) and terakhir_harian != kini.date()
        if harian or aktif >= ambang:
            alasan = "harian" if harian else f"ambang ({aktif} episode aktif)"
            try:
                lap = app.konsolidator.jalankan("batch")
                lap["kedaluwarsa"] = app.konsolidator.kedaluwarsa()
                print(f"[ingat jadwal] {kini.isoformat(timespec='seconds')} konsolidasi ({alasan}): {json.dumps(lap, ensure_ascii=False)}")
            except Exception as e:
                print(f"[ingat jadwal] konsolidasi gagal: {e}")
            if harian:
                terakhir_harian = kini.date()
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(utama())
