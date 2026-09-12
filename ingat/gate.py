# SPDX-License-Identifier: Apache-2.0
"""Gate klasifikasi data P/I/S (Bab 9, merujuk docs/spek-ai-hybrid.md).

Konfigurasi:
  "gate": {"P": ["claude", ...], "I": ["lokal"]}
  "rem_tier_s": {...}   # K28 — lihat ingat/rem.py

Tier S tertutup secara default, dan `gate.S` di konfigurasi diabaikan (bukan pintu belakang).
Satu-satunya jalan membuka tier S adalah K28: keempat rem di `rem_tier_s` terpasang sekaligus,
dan hanya untuk `jalur="konsolidasi"`. Jalur umum (`/tanya`) tetap menolak tier S selamanya.
"""
from __future__ import annotations

from . import skema
from .rem import RemTierS

JALUR_KONSOLIDASI = "konsolidasi"


class GateDitolak(PermissionError):
    pass


class Gate:
    def __init__(self, konfig: dict | None, rem: dict | None = None, penyedia: dict | None = None):
        k = dict(konfig or {})
        self.izin_tier: dict[str, list[str]] = {
            "P": list(k.get("P", [])),
            "I": list(k.get("I", [])),
            "S": [],
        }
        self.rem = RemTierS(rem, penyedia)

    def izin(self, tier: str, jalur: str = "umum") -> list[str]:
        if tier == "S":
            return self.rem.penyedia_diizinkan() if jalur == JALUR_KONSOLIDASI else []
        return list(self.izin_tier.get(tier, []))

    def boleh(self, penyedia_id: str, tier: str, jalur: str = "umum") -> bool:
        return penyedia_id in self.izin(tier, jalur)

    def pilih(self, tier: str, tersedia: dict, jalur: str = "umum") -> str | None:
        """Provider pertama yang diizinkan untuk tier ini dan benar-benar terkonfigurasi."""
        for pid in self.izin(tier, jalur):
            if pid in tersedia:
                return pid
        return None

    def wajib(self, penyedia_id: str, tier: str, jalur: str = "umum"):
        if tier == "S" and jalur != JALUR_KONSOLIDASI:
            raise GateDitolak(
                "tier S tidak pernah boleh dikirim ke penyedia inferensi di jalur umum (Bab 9); "
                "K28 hanya melonggarkan jalur konsolidasi ke model lokal"
            )
        if not self.boleh(penyedia_id, tier, jalur):
            alasan = f"; rem K28 tertutup: {self.rem.alasan_tertutup()}" if tier == "S" else ""
            raise GateDitolak(
                f"penyedia '{penyedia_id}' tidak diizinkan untuk tier {tier}; izin: {self.izin(tier, jalur)}{alasan}"
            )

    @staticmethod
    def tier_tertinggi(daftar: list[str]) -> str:
        return skema.tier_tertinggi(daftar)
