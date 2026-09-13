# SPDX-License-Identifier: Apache-2.0
"""K30 — pelajaran/prosedur `tier_maks: S` ditahan di laptop, tidak pernah ke relay/dashboard.

Dua lapis (defense in depth):
1. **Penampungan fisik**: item tier_maks:S ditulis ke `*/_tier-s/` — folder yang di-gitignore vault,
   jadi tidak pernah ikut `git push` ke VPS.
2. **Backstop**: `sinkron(lewati_tier_s=True)` (dipakai relay) menolak meng-indeks tier_maks:S dari
   folder MANA PUN — jadi walau sebuah berkas S salah taruh di `pelajaran/` dan terlanjur ter-push,
   store relay tetap bersih. Karena dashboard membaca store, dashboard relay ikut bersih.

Laptop (`lewati_tier_s=False`) meng-indeks semuanya, termasuk `_tier-s/` — laptop memang butuh
pelajaran tier S-nya.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from ingat import frontmatter, skema
from ingat.dashboard import bangun_graf
from ingat.obsidian import Vault
from ingat.simpan import Store
from ingat.vektor import PenyematLokal

FP = "proyek:fp-dashboard"


def _tulis(vault_path: str, folder: str, id_: str, tier_maks: str, status: str = "aturan"):
    meta = {"id": id_, "jenis": "pelajaran", "pelajaran": f"Pelajaran {id_}", "pemicu": "kondisi x",
            "tindakan": "lakukan y", "lingkup": FP, "status": status, "keyakinan": 0.7, "tier_maks": tier_maks}
    os.makedirs(os.path.join(vault_path, folder), exist_ok=True)
    with open(os.path.join(vault_path, folder, f"{id_}.md"), "w", encoding="utf-8") as f:
        f.write(frontmatter.dump(meta, "isi"))


class _Dasar(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ingat-ftier-")
        self.store = Store(os.path.join(self.dir, "data"), PenyematLokal())
        self.vault = Vault(os.path.join(self.dir, "vault"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def ids(self):
        return {p.id for p in self.store.pelajaran_semua()}


class BackstopSinkron(_Dasar):
    def test_relay_melewati_tier_s_dari_folder_mana_pun(self):
        _tulis(self.vault.path, "pelajaran", "pl-pi", "I")
        _tulis(self.vault.path, "pelajaran", "pl-s-salah-taruh", "S")   # S salah taruh di folder induk
        _tulis(self.vault.path, "pelajaran/_tier-s", "pl-s-benar", "S")
        lap = self.vault.sinkron(self.store, lewati_tier_s=True)
        self.assertEqual(self.ids(), {"pl-pi"}, "relay hanya boleh meng-indeks tier P/I")
        self.assertEqual(lap["dilewati_tier_s"], 2)

    def test_laptop_mengindeks_semua_termasuk_tier_s(self):
        _tulis(self.vault.path, "pelajaran", "pl-pi", "I")
        _tulis(self.vault.path, "pelajaran/_tier-s", "pl-s-benar", "S", status="aturan")
        self.vault.sinkron(self.store, lewati_tier_s=False)
        self.assertEqual(self.ids(), {"pl-pi", "pl-s-benar"})

    def test_default_sinkron_tidak_melewati(self):
        _tulis(self.vault.path, "pelajaran/_tier-s", "pl-s", "S")
        self.vault.sinkron(self.store)  # default lewati_tier_s=False (laptop)
        self.assertIn("pl-s", self.ids())

    def test_dashboard_relay_tidak_pernah_menampilkan_tier_s(self):
        _tulis(self.vault.path, "pelajaran", "pl-pi", "I")
        _tulis(self.vault.path, "pelajaran", "pl-s", "S")
        self.vault.sinkron(self.store, lewati_tier_s=True)
        graf = bangun_graf_ids(self.store)
        self.assertIn("pl-pi", graf)
        self.assertNotIn("pl-s", graf)


def bangun_graf_ids(store) -> set[str]:
    app = type("A", (), {"store": store})()
    g = bangun_graf(app)
    return {n.get("id") for n in g.get("node", g.get("nodes", []))}


class PenampunganFisik(_Dasar):
    """tulis_usulan_* mengarahkan tier_maks:S ke `_tier-s/` (laptop-only), sisanya ke `_usulan/`."""

    def _pelajaran(self, id_, tier_maks):
        return skema.Pelajaran(id=id_, pelajaran="p", pemicu="pm", tindakan="t", lingkup=FP,
                               status="usulan", keyakinan=0.6, tier_maks=tier_maks)

    def test_pelajaran_tier_s_ke_folder_tier_s(self):
        path = self.vault.tulis_usulan_pelajaran(self._pelajaran("pl-s", "S"), ["bukti"])
        self.assertIn(os.path.join("pelajaran", "_tier-s"), path)
        self.assertFalse(os.path.exists(os.path.join(self.vault.path, "pelajaran", "_usulan", "pl-s.md")))

    def test_pelajaran_pi_ke_usulan_seperti_biasa(self):
        path = self.vault.tulis_usulan_pelajaran(self._pelajaran("pl-i", "I"), ["bukti"])
        self.assertIn(os.path.join("pelajaran", "_usulan"), path)

    def test_prosedur_tier_s_ke_folder_tier_s(self):
        pr = skema.Prosedur(id="pr-s", prosedur="x", tugas_pemicu="t", langkah=["a"], lingkup=FP, status="teruji", tier_maks="S")
        path = self.vault.tulis_usulan_prosedur(pr, ["bukti"])
        self.assertIn(os.path.join("prosedur", "_tier-s"), path)


class ThreadRelayFlag(unittest.TestCase):
    """Aplikasi.sinkron_vault() meneruskan lewati_tier_s=self.relay — kebijakan terpusat."""

    def setUp(self):
        import json
        from ingat.aplikasi import Aplikasi, KONFIG_DEFAULT
        self.dir = tempfile.mkdtemp(prefix="ingat-ftier-app-")
        self.k = json.loads(json.dumps(KONFIG_DEFAULT))
        self.k["dir_data"] = os.path.join(self.dir, "data")
        self.k["vault"] = os.path.join(self.dir, "vault")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _app(self, relay: bool):
        from ingat.aplikasi import Aplikasi
        self.k["relay"] = {"aktif": relay}
        return Aplikasi(self.k)

    def test_relay_true_melewati_s(self):
        app = self._app(True)
        _tulis(app.vault.path, "pelajaran", "pl-s", "S")
        _tulis(app.vault.path, "pelajaran", "pl-i", "I")
        app.sinkron_vault()
        self.assertEqual({p.id for p in app.store.pelajaran_semua()}, {"pl-i"})

    def test_relay_false_indeks_s(self):
        app = self._app(False)
        _tulis(app.vault.path, "pelajaran/_tier-s", "pl-s", "S")
        app.sinkron_vault()
        self.assertIn("pl-s", {p.id for p in app.store.pelajaran_semua()})


if __name__ == "__main__":
    unittest.main()
