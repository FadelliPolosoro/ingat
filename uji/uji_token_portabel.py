# SPDX-License-Identifier: Apache-2.0
"""A2 — token portabel: generate, persist, resolve 3-tier, CLI show/set/buat."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
import unittest.mock as mock

from ingat.jauh import baca_token


def _mock_expanduser(tmp_dir):
    _asli = os.path.expanduser
    def _expand(p):
        if "/.ingat/token" in p.replace("\\", "/") or r"\.ingat\token" in p:
            return os.path.join(tmp_dir, "token")
        if "/.ingat" in p.replace("\\", "/") or r"\.ingat" in p:
            return tmp_dir
        return _asli(p)
    return _expand


class ResolusiToken(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ingat-tok-")
        self._env_asli = os.environ.get("INGAT_TOKEN")
        os.environ.pop("INGAT_TOKEN", None)
        self._patcher = mock.patch("os.path.expanduser", side_effect=_mock_expanduser(self.tmp))
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        if self._env_asli is not None:
            os.environ["INGAT_TOKEN"] = self._env_asli
        else:
            os.environ.pop("INGAT_TOKEN", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_env_diutamakan(self):
        os.environ["INGAT_TOKEN"] = "env-token-abcdef1234567890abcdef"
        berkas = os.path.join(self.tmp, "token")
        with open(berkas, "w") as f:
            f.write("file-token-xyz-1234567890abcdef\n")
        self.assertEqual(baca_token(None), "env-token-abcdef1234567890abcdef")

    def test_berkas_fallback(self):
        berkas = os.path.join(self.tmp, "token")
        with open(berkas, "w") as f:
            f.write("file-token-abc123\n")
        self.assertEqual(baca_token(None), "file-token-abc123")

    def test_konfig_fallback(self):
        konfig = {"jauh": {"token": "config-tok-99"}}
        self.assertEqual(baca_token(konfig), "config-tok-99")

    def test_kosong_tanpa_sumber(self):
        self.assertEqual(baca_token(None), "")


class CLIToken(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ingat-cli-tok-")
        self._env_asli = os.environ.get("INGAT_TOKEN")
        os.environ.pop("INGAT_TOKEN", None)
        self._patcher = mock.patch("os.path.expanduser", side_effect=_mock_expanduser(self.tmp))
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        if self._env_asli is not None:
            os.environ["INGAT_TOKEN"] = self._env_asli
        else:
            os.environ.pop("INGAT_TOKEN", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_buat_tulis_berkas(self):
        from ingat.cli import utama
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = utama(["token", "--buat"])
        self.assertEqual(rc, 0)
        self.assertIn("disimpan", buf.getvalue())
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "token")))

    def test_set_tulis_berkas(self):
        from ingat.cli import utama
        import io, contextlib
        val = "my-custom-token-ABCDEFGH12345678"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = utama(["token", "--set", val])
        self.assertEqual(rc, 0)
        with open(os.path.join(self.tmp, "token")) as f:
            self.assertIn(val, f.read())

    def test_set_terlalu_pendek_ditolak(self):
        from ingat.cli import utama
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = utama(["token", "--set", "pendek"])
        self.assertEqual(rc, 1)

    def test_tampil_dari_berkas(self):
        from ingat.cli import utama
        import io, contextlib
        berkas = os.path.join(self.tmp, "token")
        val = "abcdef-1234567890-ghijklmnopqrst"
        with open(berkas, "w") as f:
            f.write(val + "\n")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = utama(["token"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("abcdef", out)
        self.assertIn("qrst", out)
        self.assertIn("~/.ingat/token", out)

    def test_tanpa_token_gagal(self):
        from ingat.cli import utama
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = utama(["token"])
        self.assertEqual(rc, 1)
        self.assertIn("Belum ada", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
