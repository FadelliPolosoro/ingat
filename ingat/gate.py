# SPDX-License-Identifier: Apache-2.0
"""Gate klasifikasi data P/I/S (Bab 9, merujuk docs/spek-ai-hybrid.md).

Konfigurasi:
  "gate": {"P": ["claude", "openai", ...], "I": ["lokal"], "S": []}
Tier S tidak pernah boleh — apa pun isi konfigurasi.
"""
from __future__ import annotations

from . import skema


class GateDitolak(PermissionError):
    pass


class Gate:
    def __init__(self, konfig: dict | None):
        k = dict(konfig or {})
        self.izin_tier: dict[str, list[str]] = {
            "P": list(k.get("P", [])),
            "I": list(k.get("I", [])),
            "S": [],
        }

    def izin(self, tier: str) -> list[str]:
        if tier == "S":
            return []
        return list(self.izin_tier.get(tier, []))

    def boleh(self, penyedia_id: str, tier: str) -> bool:
        return penyedia_id in self.izin(tier)

    def pilih(self, tier: str, tersedia: dict) -> str | None:
        """Provider pertama yang diizinkan untuk tier ini dan benar-benar terkonfigurasi."""
        for pid in self.izin(tier):
            if pid in tersedia:
                return pid
        return None

    def wajib(self, penyedia_id: str, tier: str):
        if tier == "S":
            raise GateDitolak("tier S tidak pernah boleh dikirim ke penyedia inferensi (Bab 9)")
        if not self.boleh(penyedia_id, tier):
            raise GateDitolak(f"penyedia '{penyedia_id}' tidak diizinkan untuk tier {tier}; izin: {self.izin(tier)}")

    @staticmethod
    def tier_tertinggi(daftar: list[str]) -> str:
        return skema.tier_tertinggi(daftar)
