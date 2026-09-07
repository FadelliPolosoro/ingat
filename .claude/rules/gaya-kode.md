---
paths: ["ingat/**", "port/typescript/src/**"]
---
# Gaya kode

**Python (rujukan)**: 3.11+, stdlib saja; `from __future__ import annotations`; dataclass untuk record;
tipe di tanda tangan fungsi; nama Bahasa Indonesia, kata kerja untuk aksi (`tambah_episode`, `ubah_status`);
error khusus mewarisi `Exception` dengan nama Indonesia (`TransisiTerlarang`, `GateDitolak`);
setiap berkas diawali `# SPDX-License-Identifier: Apache-2.0`.

**TypeScript (port)**: ESM tanpa fitur yang tidak lolos type-stripping Node (tanpa `enum`, parameter
properties, `namespace`); impor relatif dengan ekstensi `.ts`; `// SPDX-License-Identifier: Apache-2.0`.

Keduanya: fungsi kecil; tanpa `any`/`Any` kecuali di batas JSON dan langsung dipersempit.
