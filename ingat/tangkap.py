# SPDX-License-Identifier: Apache-2.0
"""Hook Claude Code → episode (K11: tangkap otomatis + koreksi ditandai manusia).

Dipanggil Claude Code lewat `settings.json` → `hooks` dengan JSON di stdin. Peristiwa yang ditangani:

  PostToolUse         mencatat langkah tool ke buffer sesi; heuristik kegagalan → episode `kegagalan` (bobot 3)
  PostToolUseFailure  episode `kegagalan`
  Stop                meng-upsert SATU episode `sukses` per sesi (id deterministik) berisi `langkah` seluruh sesi —
                      bahan konsolidasi prosedur (7.6); bukan satu episode per tool (anti-banjir)
  UserPromptSubmit    prompt diawali `/koreksi` atau `koreksi:` → episode `koreksi` (bobot 5) — K11
  SessionStart        MEMBACA memori: muat_startup(lingkup) dirender jadi additionalContext — pelajaran/prosedur
                      aktif otomatis ada di konteks Claude Code SEJAK PESAN PERTAMA, tanpa Claude perlu ingat
                      memanggil tool sendiri. Ini pasangan tulis/baca dari K11 — sebelumnya hanya tulis.
  SessionEnd          buffer sesi ditutup; sesi tanpa langkah dicatat sebagai metrik (encoding failure, Bab 11)

Prinsip: hook TIDAK PERNAH memblokir Claude — selalu exit 0; galat ditulis ke `<dir_data>/tangkap.log`.
Redaksi kredensial dan penanda tier terjadi di `Store.tambah_episode` (satu-satunya jalur tulis).
Konfigurasi: env `INGAT_KONFIG` → `~/.ingat/konfigurasi.json` → `./konfigurasi.json`.
Lingkup: env `INGAT_LINGKUP` → berkas `<cwd>/.ingat-lingkup` → `proyek:<nama folder cwd>`.
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback

from . import skema
from .aplikasi import Aplikasi, muat_konfig

MAKS_LANGKAH = 60
POLA_GAGAL = re.compile(r"\b(error|failed|failure|traceback|exception|not found|denied|refused|cannot|fatal)\b", re.I)
PREFIKS_KOREKSI = ("/koreksi", "koreksi:")


def path_konfig() -> str:
    for p in (os.environ.get("INGAT_KONFIG"), os.path.expanduser("~/.ingat/konfigurasi.json"), "konfigurasi.json"):
        if p and os.path.exists(p):
            return p
    return os.path.expanduser("~/.ingat/konfigurasi.json")


def tentukan_lingkup(cwd: str) -> str:
    env = os.environ.get("INGAT_LINGKUP")
    if env and skema.lingkup_valid(env):
        return env
    berkas = os.path.join(cwd or ".", ".ingat-lingkup")
    if os.path.exists(berkas):
        with open(berkas, encoding="utf-8") as f:
            l = f.read().strip()
        if skema.lingkup_valid(l):
            return l
    nama = os.path.basename(os.path.abspath(cwd or ".")) or "tanpa-nama"
    return f"proyek:{re.sub(r'[^a-z0-9._-]', '-', nama.lower())}"


def ringkas_langkah(tool: str, masukan: dict) -> str:
    if tool == "Bash":
        return str(masukan.get("command", ""))[:200]
    if tool in ("Edit", "Write", "MultiEdit", "Read", "NotebookEdit"):
        return f"{tool} {masukan.get('file_path', '')}"[:200]
    if tool.startswith("mcp__"):
        return f"{tool} {json.dumps(masukan, ensure_ascii=False)[:120]}"
    return f"{tool} {json.dumps(masukan, ensure_ascii=False)[:120]}"


def deteksi_gagal(tool: str, respons) -> tuple[bool, str]:
    """Heuristik kegagalan pada PostToolUse (PostToolUseFailure sudah pasti gagal)."""
    if isinstance(respons, dict):
        if respons.get("success") is False or respons.get("is_error") or respons.get("interrupted"):
            return True, str(respons.get("error") or respons.get("stderr") or respons)[:2000]
        kode = respons.get("exit_code", respons.get("exitCode"))
        if isinstance(kode, int) and kode != 0:
            return True, str(respons.get("stderr") or respons.get("stdout") or "")[:2000]
        stderr = str(respons.get("stderr") or "")
        stdout = str(respons.get("stdout") or "")
        if tool == "Bash" and stderr and POLA_GAGAL.search(stderr) and not stdout.strip():
            return True, stderr[:2000]
        return False, ""
    teks = str(respons or "")
    if tool == "Bash" and POLA_GAGAL.search(teks[:400]) and len(teks) < 2000:
        return True, teks[:2000]
    return False, ""


class Penangkap:
    def __init__(self, app: Aplikasi, dir_data: str):
        self.app = app
        self.dir_sesi = os.path.join(dir_data, "sesi")
        os.makedirs(self.dir_sesi, exist_ok=True)

    # ---- buffer sesi -------------------------------------------------------------
    def _buf(self, sesi: str) -> str:
        return os.path.join(self.dir_sesi, f"{re.sub(r'[^A-Za-z0-9_-]', '_', sesi)}.jsonl")

    def _tulis_buf(self, sesi: str, rekaman: dict):
        with open(self._buf(sesi), "a", encoding="utf-8") as f:
            f.write(json.dumps(rekaman, ensure_ascii=False) + "\n")

    def _baca_buf(self, sesi: str) -> list[dict]:
        p = self._buf(sesi)
        if not os.path.exists(p):
            return []
        with open(p, encoding="utf-8") as f:
            return [json.loads(b) for b in f if b.strip()]

    # ---- peristiwa ----------------------------------------------------------------
    def tangani(self, ev: dict) -> dict:
        nama = ev.get("hook_event_name") or ev.get("event") or ""
        sesi = str(ev.get("session_id") or "tanpa-sesi")
        cwd = str(ev.get("cwd") or os.getcwd())
        lingkup = tentukan_lingkup(cwd)
        if nama == "PostToolUse":
            return self.post_tool(ev, sesi, lingkup, gagal_pasti=False)
        if nama == "PostToolUseFailure":
            return self.post_tool(ev, sesi, lingkup, gagal_pasti=True)
        if nama == "SessionStart":
            return self.session_start(sesi, lingkup)
        if nama == "Stop":
            return self.stop(sesi, lingkup)
        if nama == "UserPromptSubmit":
            return self.prompt(ev, sesi, lingkup)
        if nama == "SessionEnd":
            return self.akhir_sesi(sesi, lingkup)
        return {"diabaikan": nama}

    def post_tool(self, ev: dict, sesi: str, lingkup: str, gagal_pasti: bool) -> dict:
        tool = str(ev.get("tool_name") or "?")
        masukan = ev.get("tool_input") or {}
        respons = ev.get("tool_response", ev.get("error"))
        langkah = ringkas_langkah(tool, masukan if isinstance(masukan, dict) else {})
        gagal, detail = (True, str(respons)[:2000]) if gagal_pasti else deteksi_gagal(tool, respons)
        self._tulis_buf(sesi, {"waktu": skema.sekarang(), "tool": tool, "langkah": langkah, "gagal": gagal})
        hasil = {"langkah": langkah, "gagal": gagal}
        if gagal:
            ep = self.app.store.tambah_episode(
                f"[tool gagal] {tool}\n{langkah}\n\n{detail}", sumber="claude-code", tier="I", lingkup=lingkup,
                jenis_kejadian="kegagalan", ringkas=f"{tool} gagal: {langkah[:120]} — {detail.strip().splitlines()[0][:80] if detail.strip() else 'tanpa pesan'}",
                instrumen=[f"tool:{tool}"], sesi=sesi, langkah=[langkah])
            hasil["episode"] = ep.id
        return hasil

    def stop(self, sesi: str, lingkup: str) -> dict:
        """Satu episode `sukses` per sesi, di-upsert tiap Stop: id deterministik, langkah bertambah."""
        rekaman = self._baca_buf(sesi)
        if not rekaman:
            return {"sesi": sesi, "langkah": 0}
        langkah = [r["langkah"] for r in rekaman][-MAKS_LANGKAH:]
        gagal = sum(1 for r in rekaman if r.get("gagal"))
        tools = sorted({r["tool"] for r in rekaman})
        isi = "\n".join(f"{r['waktu'][11:19]} {'✗' if r.get('gagal') else '✓'} {r['tool']}: {r['langkah']}" for r in rekaman)
        ep = self.app.store.tambah_episode(
            f"[sesi {sesi}] {len(rekaman)} langkah, {gagal} gagal\n{isi}", id=f"ep-sesi-{re.sub(r'[^A-Za-z0-9_-]', '_', sesi)[:40]}",
            sumber="claude-code", tier="I", lingkup=lingkup, jenis_kejadian="sukses",
            ringkas=f"Sesi Claude Code: {len(rekaman)} langkah ({', '.join(tools)[:80]}), {gagal} gagal",
            instrumen=[f"tool:{t}" for t in tools], sesi=sesi, langkah=langkah)
        return {"sesi": sesi, "episode": ep.id, "langkah": len(langkah), "gagal": gagal}

    def prompt(self, ev: dict, sesi: str, lingkup: str) -> dict:
        teks = str(ev.get("prompt") or "").strip()
        rendah = teks.lower()
        for pre in PREFIKS_KOREKSI:
            if rendah.startswith(pre):
                inti = teks[len(pre):].strip(" :—-")
                if not inti:
                    return {"koreksi": "kosong"}
                terakhir = self._baca_buf(sesi)[-5:]
                konteks = "\n".join(f"{r['tool']}: {r['langkah']}" for r in terakhir)
                ep = self.app.store.tambah_episode(
                    f"[koreksi manusia]\n{inti}\n\nLangkah terakhir sebelum koreksi:\n{konteks}", sumber="claude-code", tier="I",
                    lingkup=lingkup, jenis_kejadian="koreksi", ringkas=inti[:200],
                    instrumen=sorted({f"tool:{r['tool']}" for r in terakhir}), sesi=sesi, langkah=[r["langkah"] for r in terakhir])
                self._tulis_buf(sesi, {"waktu": skema.sekarang(), "tool": "koreksi", "langkah": inti[:200], "gagal": False})
                return {"koreksi": ep.id, "pesan": f"ingat: koreksi dicatat sebagai {ep.id} (bobot 5, lingkup {lingkup})"}
        return {"koreksi": None}

    def session_start(self, sesi: str, lingkup: str) -> dict:
        """L-peta + L-aturan otomatis di awal sesi (anti-Spalko: hanya ringkasan/aturan, bukan episode mentah)."""
        try:
            hasil = self.app.gateway.muat_startup(lingkup, sesi=sesi)
        except Exception as e:
            return {"galat": str(e)}
        # muat_startup selalu menyertakan satu baris judul di peta; "kosong" berarti tidak ada
        # apa pun DI LUAR baris judul itu — norma/pelajaran/prosedur/instrumen maupun aturan aktif.
        if len(hasil["peta"]) <= 1 and not hasil["aturan"]:
            return {"kosong": True}
        blok = [f"## Memori (ingat) — lingkup `{lingkup}`", ""]
        blok += hasil["peta"]
        if hasil["aturan"]:
            blok += ["", "### Pelajaran & prosedur aktif", ""] + hasil["aturan"]
        if hasil["pointer"]:
            blok += ["", f"(+{len(hasil['pointer'])} item lain — panggil tool `ingat` bila relevan)"]
        return {"additionalContext": "\n".join(blok), "token": hasil["token"]}

    def akhir_sesi(self, sesi: str, lingkup: str) -> dict:
        rekaman = self._baca_buf(sesi)
        if not rekaman:
            self.app.store.catat_metrik("sesi_tanpa_episode", 1, sesi=sesi, lingkup=lingkup)
            return {"sesi": sesi, "langkah": 0, "metrik": "sesi_tanpa_episode"}
        hasil = self.stop(sesi, lingkup)
        p = self._buf(sesi)
        os.replace(p, p + ".selesai")
        # Pasangan dari sesi_tanpa_episode. Tanpa penanda sisi-sukses ini, "3 sesi berturut"
        # (alarm Bab 11) tidak bisa dihitung — tabel metrik hanya berisi kegagalan, sehingga
        # tiga sesi kosong yang terpisah berbulan-bulan terbaca seperti deret.
        self.app.store.catat_metrik("sesi_dengan_episode", 1, sesi=sesi, lingkup=lingkup)
        return hasil


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        mentah = sys.stdin.read()
        ev = json.loads(mentah) if mentah.strip() else {}
        if argv and not ev.get("hook_event_name"):
            ev["hook_event_name"] = argv[0]
        konfig = muat_konfig(path_konfig())
        app = Aplikasi(konfig)
        hasil = Penangkap(app, konfig["dir_data"]).tangani(ev)
        nama_ev = ev.get("hook_event_name")
        if nama_ev == "UserPromptSubmit" and hasil.get("pesan"):
            print(hasil["pesan"])  # UserPromptSubmit: stdout polos = konteks tambahan untuk Claude
        elif nama_ev == "SessionStart" and hasil.get("additionalContext"):
            print(json.dumps({"continue": True, "hookSpecificOutput": {
                "hookEventName": "SessionStart", "additionalContext": hasil["additionalContext"]}}, ensure_ascii=False))
        return 0
    except Exception:
        try:
            konfig = muat_konfig(path_konfig())
            os.makedirs(konfig["dir_data"], exist_ok=True)
            with open(os.path.join(konfig["dir_data"], "tangkap.log"), "a", encoding="utf-8") as f:
                f.write(f"{skema.sekarang()} {traceback.format_exc()}\n")
        except Exception:
            pass
        return 0  # hook tidak pernah memblokir Claude


if __name__ == "__main__":
    sys.exit(main())
