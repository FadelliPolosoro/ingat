# SPDX-License-Identifier: Apache-2.0
"""K11: hook Claude Code → episode. Diuji dengan payload JSON persis seperti yang dikirim Claude Code ke stdin."""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from ingat.aplikasi import Aplikasi, KONFIG_DEFAULT
from ingat.pasang import gabung_hooks, pasang
from ingat.tangkap import Penangkap, deteksi_gagal, tentukan_lingkup, main


class Dasar(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-tangkap-")
        self.cwd = os.path.join(self.dir, "fp-dashboard")
        os.makedirs(self.cwd)
        k = json.loads(json.dumps(KONFIG_DEFAULT))
        k["dir_data"] = os.path.join(self.dir, "data")
        k["vault"] = os.path.join(self.dir, "vault")
        self.app = Aplikasi(k)
        self.pt = Penangkap(self.app, k["dir_data"])

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def ev(self, nama, **isi):
        return {"session_id": "abc123", "transcript_path": "/x/t.jsonl", "cwd": self.cwd, "hook_event_name": nama,
                "permission_mode": "default", **isi}


class Lingkup(Dasar):
    def test_dari_nama_folder_dan_berkas(self):
        self.assertEqual(tentukan_lingkup(self.cwd), "proyek:fp-dashboard")
        with open(os.path.join(self.cwd, ".ingat-lingkup"), "w") as f:
            f.write("peran:sosmed\n")
        self.assertEqual(tentukan_lingkup(self.cwd), "peran:sosmed")
        with mock.patch.dict(os.environ, {"INGAT_LINGKUP": "global"}):
            self.assertEqual(tentukan_lingkup(self.cwd), "global")


class DeteksiGagal(unittest.TestCase):
    def test_heuristik(self):
        self.assertEqual(deteksi_gagal("Bash", {"stdout": "", "stderr": "npm ERR! code ELIFECYCLE\nnpm ERR! failed"})[0], True)
        self.assertEqual(deteksi_gagal("Bash", {"stdout": "ok\n", "stderr": ""})[0], False)
        self.assertEqual(deteksi_gagal("Bash", {"stdout": "warn: error in log line but ok", "stderr": "deprecated"})[0], False)
        self.assertEqual(deteksi_gagal("Bash", {"exit_code": 1, "stderr": "x"})[0], True)
        self.assertEqual(deteksi_gagal("Edit", {"success": False, "error": "file not found"})[0], True)
        self.assertEqual(deteksi_gagal("Edit", {"success": True})[0], False)


class AlurSesi(Dasar):
    def test_post_tool_stop_upsert_satu_episode_per_sesi(self):
        self.pt.tangani(self.ev("PostToolUse", tool_name="Bash", tool_input={"command": "npm ci --ignore-scripts"},
                                tool_response={"stdout": "added 200 packages", "stderr": ""}))
        self.pt.tangani(self.ev("PostToolUse", tool_name="Edit", tool_input={"file_path": "src/a.js", "old_string": "x", "new_string": "y"},
                                tool_response={"success": True}))
        # PostToolUse sukses tidak membuat episode per tool (anti-banjir)
        self.assertEqual(len(self.app.store.episode_semua()), 0)
        h1 = self.pt.tangani(self.ev("Stop"))
        h2 = self.pt.tangani(self.ev("Stop"))
        self.assertEqual(h1["episode"], h2["episode"], "Stop meng-upsert episode sesi yang sama")
        eps = self.app.store.episode_semua()
        self.assertEqual(len(eps), 1)
        e = eps[0]
        self.assertEqual(e.jenis_kejadian, "sukses")
        self.assertEqual(e.lingkup, "proyek:fp-dashboard")
        self.assertEqual(e.sesi, "abc123")
        self.assertEqual(e.langkah, ["npm ci --ignore-scripts", "Edit src/a.js"])
        self.assertEqual(sorted(e.instrumen), ["tool:Bash", "tool:Edit"])
        # langkah ketiga → episode sesi yang sama bertambah
        self.pt.tangani(self.ev("PostToolUse", tool_name="Bash", tool_input={"command": "npm test"}, tool_response={"stdout": "ok", "stderr": ""}))
        self.pt.tangani(self.ev("Stop"))
        self.assertEqual(len(self.app.store.episode_semua()), 1)
        self.assertEqual(len(self.app.store.episode(e.id).langkah), 3)

    def test_kegagalan_langsung_jadi_episode_dan_diredaksi(self):
        h = self.pt.tangani(self.ev("PostToolUse", tool_name="Bash",
                                    tool_input={"command": "curl -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcdefghijklmnop' https://x"},
                                    tool_response={"stdout": "", "stderr": "curl: (7) Failed to connect: Connection refused"}))
        self.assertTrue(h["gagal"])
        e = self.app.store.episode(h["episode"])
        self.assertEqual(e.jenis_kejadian, "kegagalan")
        self.assertEqual(e.bobot, 3)
        self.assertNotIn("eyJhbGci", e.ringkas)
        self.assertNotIn("eyJhbGci", self.app.store.buka_dingin(e.isi_ref)["isi"])
        self.assertTrue({"bearer", "jwt"} & set(e.diredaksi), e.diredaksi)  # pola jwt lebih dulu; keduanya sah

    def test_post_tool_use_failure_pasti_gagal(self):
        h = self.pt.tangani(self.ev("PostToolUseFailure", tool_name="Write", tool_input={"file_path": "/etc/x"}, error="EACCES: permission denied"))
        self.assertEqual(self.app.store.episode(h["episode"]).jenis_kejadian, "kegagalan")

    def test_koreksi_prefiks_bobot_5_dengan_konteks_langkah(self):
        self.pt.tangani(self.ev("PostToolUse", tool_name="Bash", tool_input={"command": "ls /var/www"}, tool_response={"stdout": "", "stderr": ""}))
        h = self.pt.tangani(self.ev("UserPromptSubmit", prompt="/koreksi VPS_getProjectListV1 kosong bukan berarti tidak ada deploy; saya deploy manual via SSH"))
        e = self.app.store.episode(h["koreksi"])
        self.assertEqual(e.jenis_kejadian, "koreksi")
        self.assertEqual(e.bobot, 5)
        self.assertIn("VPS_getProjectListV1", e.ringkas)
        self.assertEqual(e.langkah, ["ls /var/www"])
        self.assertIn("dicatat", h["pesan"])
        self.assertIsNone(self.pt.tangani(self.ev("UserPromptSubmit", prompt="lanjutkan"))["koreksi"])
        self.assertEqual(self.pt.tangani(self.ev("UserPromptSubmit", prompt="koreksi:"))["koreksi"], "kosong")

    def test_session_start_muat_pelajaran_aktif_otomatis(self):
        """K11-lanjut: pasangan BACA dari K11 (yang sebelumnya cuma TULIS). Tanpa Claude memanggil tool apa pun,
        pelajaran aktif dalam lingkup harus sudah ada di additionalContext sejak awal sesi."""
        vault_dir = self.app.konfig["vault"]
        import os as _os
        _os.makedirs(_os.path.join(vault_dir, "pelajaran"), exist_ok=True)
        from ingat import frontmatter as fm
        meta = {"id": "pl-uji-startup", "jenis": "pelajaran",
                "pelajaran": "Ketiadaan hasil satu tool bukan ketiadaan objek",
                "pemicu": "tool kosong", "tindakan": "cek jalur kedua",
                "lingkup": "proyek:fp-dashboard", "status": "aturan", "keyakinan": 0.9,
                "dibuat": "2026-01-01", "ditinjau_manusia": True}
        with open(_os.path.join(vault_dir, "pelajaran", "pl-uji-startup.md"), "w", encoding="utf-8") as f:
            f.write(fm.dump(meta, "badan"))
        self.app.vault.sinkron(self.app.store)
        h = self.pt.tangani(self.ev("SessionStart"))
        self.assertIn("additionalContext", h)
        self.assertIn("Ketiadaan hasil satu tool bukan ketiadaan objek", h["additionalContext"])
        self.assertIn("lingkup `proyek:fp-dashboard`", h["additionalContext"])

    def test_session_start_kosong_bila_belum_ada_memori(self):
        h = self.pt.tangani(self.ev("SessionStart"))
        self.assertTrue(h.get("kosong"))

    def test_main_session_start_mencetak_json_hookspecific(self):
        """Format keluaran harus sesuai skema resmi Claude Code: hookSpecificOutput.additionalContext."""
        vault_dir = self.app.konfig["vault"]
        import os as _os
        _os.makedirs(_os.path.join(vault_dir, "pelajaran"), exist_ok=True)
        from ingat import frontmatter as fm
        meta = {"id": "pl-uji-main", "jenis": "pelajaran", "pelajaran": "Contoh pelajaran untuk uji main()",
                "pemicu": "x", "tindakan": "y", "lingkup": "proyek:fp-dashboard", "status": "aturan",
                "keyakinan": 0.9, "dibuat": "2026-01-01", "ditinjau_manusia": True}
        with open(_os.path.join(vault_dir, "pelajaran", "pl-uji-main.md"), "w", encoding="utf-8") as f:
            f.write(fm.dump(meta, "badan"))
        self.app.vault.sinkron(self.app.store)
        konfig = os.path.join(self.dir, "k2.json")
        with open(konfig, "w") as f:
            json.dump({"dir_data": self.app.konfig["dir_data"], "vault": vault_dir, "embedding": {"jenis": "lokal"}}, f)
        payload = json.dumps(self.ev("SessionStart"))
        keluar = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(payload)), mock.patch.dict(os.environ, {"INGAT_KONFIG": konfig}), redirect_stdout(keluar):
            self.assertEqual(main([]), 0)
        cetak = json.loads(keluar.getvalue())
        self.assertEqual(cetak["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("Contoh pelajaran untuk uji main()", cetak["hookSpecificOutput"]["additionalContext"])
        self.assertTrue(cetak["continue"])

    def test_session_end_tanpa_langkah_mencatat_metrik(self):
        h = self.pt.tangani(self.ev("SessionEnd", session_id="kosong-1"))
        self.assertEqual(h["metrik"], "sesi_tanpa_episode")
        self.assertEqual(len(self.pt.app.store.db.execute("SELECT * FROM metrik WHERE nama='sesi_tanpa_episode'").fetchall()), 1)

    def test_session_end_menutup_buffer(self):
        self.pt.tangani(self.ev("PostToolUse", tool_name="Bash", tool_input={"command": "pwd"}, tool_response={"stdout": "/x", "stderr": ""}))
        self.pt.tangani(self.ev("SessionEnd"))
        self.assertTrue(os.path.exists(os.path.join(self.dir, "data", "sesi", "abc123.jsonl.selesai")))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "data", "sesi", "abc123.jsonl")))

    def test_main_tidak_pernah_memblokir(self):
        """Hook rusak (stdin bukan JSON, konfigurasi tidak ada) tetap exit 0."""
        with mock.patch("sys.stdin", io.StringIO("bukan json")), mock.patch.dict(os.environ, {"INGAT_KONFIG": os.path.join(self.dir, "tidak-ada.json"),
                                                                                              "INGAT_DIR_DATA": os.path.join(self.dir, "data2"),
                                                                                              "INGAT_VAULT": os.path.join(self.dir, "vault2")}):
            self.assertEqual(main(["PostToolUse"]), 0)

    def test_main_end_to_end_lewat_stdin(self):
        konfig = os.path.join(self.dir, "k.json")
        with open(konfig, "w") as f:
            json.dump({"dir_data": os.path.join(self.dir, "data3"), "vault": os.path.join(self.dir, "vault3"), "embedding": {"jenis": "lokal"}}, f)
        payload = json.dumps(self.ev("UserPromptSubmit", prompt="koreksi: jangan asumsikan tidak ada beban kerja dari satu tool"))
        keluar = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(payload)), mock.patch.dict(os.environ, {"INGAT_KONFIG": konfig}), redirect_stdout(keluar):
            self.assertEqual(main([]), 0)
        self.assertIn("ingat: koreksi dicatat", keluar.getvalue())


class Pasang(unittest.TestCase):
    def test_gabung_hooks_tanpa_duplikat(self):
        lama = {"hooks": {"PostToolUse": [{"matcher": "Write", "hooks": [{"type": "command", "command": "pnpm lint"}]}]}}
        baru = {"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 -m ingat.tangkap PostToolUse"}]}],
                          "Stop": [{"hooks": [{"type": "command", "command": "python3 -m ingat.tangkap Stop"}]}]}}
        hasil, n = gabung_hooks(lama, baru)
        self.assertEqual(n, 2)
        self.assertEqual(len(hasil["hooks"]["PostToolUse"]), 2, "entri lama utuh, entri ingat ditambah")
        hasil2, n2 = gabung_hooks(hasil, baru)
        self.assertEqual(n2, 0, "idempoten")
        self.assertEqual(hasil2, hasil)

    def test_pasang_cetak_dulu_lalu_tulis(self):
        rumah = tempfile.mkdtemp(prefix="ingat-rumah-")
        try:
            lap = pasang(tulis=False, rumah=rumah)
            self.assertFalse(os.path.exists(os.path.join(rumah, ".claude", "settings.json")), "tanpa --tulis tidak menyentuh berkas")
            lap = pasang(tulis=True, rumah=rumah)
            with open(os.path.join(rumah, ".claude", "settings.json")) as f:
                s = json.load(f)
            self.assertIn("Stop", s["hooks"])
            self.assertTrue(os.path.exists(os.path.join(rumah, ".claude", "commands", "koreksi.md")))
            with open(os.path.join(rumah, ".claude", ".mcp.json")) as f:
                m = json.load(f)
            self.assertIn("ingat", m["mcpServers"])
            with open(os.path.join(rumah, ".ingat", "konfigurasi.json")) as f:
                k = json.load(f)
            # isabs, bukan startswith("/"): di Windows hasilnya "C:\\Users\\...".
            # Kekuatan asersi tetap — "~/.ingat" yang belum diperluas tidak absolut di OS mana pun.
            self.assertTrue(os.path.isabs(k["dir_data"]), "~ diperluas")
            lap2 = pasang(tulis=True, rumah=rumah)
            self.assertTrue(any("sudah ada" in l for l in lap2["langkah"]), "idempoten")
        finally:
            shutil.rmtree(rumah, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
