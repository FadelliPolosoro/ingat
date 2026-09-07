-- SPDX-License-Identifier: Apache-2.0
-- Kontrak penyimpanan `ingat` — versi 2 (2026-09-07).
-- SQL portabel: TEXT untuk waktu (ISO 8601) dan JSON, INTEGER 0/1 untuk boolean, tanpa AUTOINCREMENT,
-- tanpa fungsi khusus SQLite. Pragma SQLite (WAL, foreign_keys) TIDAK di sini — lihat implementasi.
-- Riwayat: v1 (2026-09-06) → v2 (2026-09-07, aditif; migrasi di skema/migrasi/002-v1-ke-v2.sql;
-- v1 diarsipkan di skema/versi/ingat-v1.sql). Satu rename aman di v2: instrumen.titik_buta →
-- titik_buta_diketahui (nama spek 6.6); aman karena v1 tidak pernah punya penulis.

CREATE TABLE IF NOT EXISTS meta (
  kunci TEXT PRIMARY KEY,
  nilai TEXT NOT NULL
);
INSERT OR IGNORE INTO meta (kunci, nilai) VALUES ('versi_kontrak', '2');
INSERT OR IGNORE INTO meta (kunci, nilai) VALUES ('kontrak_diperbarui', '2026-09-07');

-- Instrumen: tool/konektor yang menghasilkan observasi (Bab 6.6, 7.4)
CREATE TABLE IF NOT EXISTS instrumen (
  id                    TEXT PRIMARY KEY,
  nama                  TEXT NOT NULL,
  dipasang_sejak        TEXT,
  cakupan               TEXT,
  titik_buta_diketahui  TEXT               -- JSON array
);

-- Episode: kejadian mentah (Bab 6.1). Semua tersimpan verbatim (K10).
-- `isi` boleh NULL sejak lahir bila `isi_ref` terisi (verbatim langsung ke penyimpanan dingin).
CREATE TABLE IF NOT EXISTS episode (
  id              TEXT PRIMARY KEY,   -- ep-<tanggal>-<urut>
  waktu           TEXT NOT NULL,
  sumber          TEXT NOT NULL,      -- claude-code | chat | dashboard | tool:<nama>
  tier            TEXT NOT NULL CHECK (tier IN ('P','I','S')),
  lingkup         TEXT NOT NULL,      -- global | proyek:<nama> | peran:<nama>
  instrumen       TEXT,               -- JSON array id instrumen
  jenis_kejadian  TEXT NOT NULL CHECK (jenis_kejadian IN ('koreksi','kegagalan','pola','sukses')),
  bobot           INTEGER NOT NULL,
  status          TEXT NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif','didinginkan','diarsipkan')),
  ringkas         TEXT NOT NULL,
  isi             TEXT,
  isi_ref         TEXT,               -- pointer ke penyimpanan dingin
  diredaksi       TEXT NOT NULL DEFAULT '[]',  -- JSON array jenis kredensial yang diredaksi (K10)
  langkah         TEXT NOT NULL DEFAULT '[]',  -- v2: JSON array urutan aksi tool — bahan prosedur (7.6)
  sesi            TEXT                         -- v2: id sesi — dasar "bukti independen" (7.2)
);
CREATE INDEX IF NOT EXISTS episode_status_lingkup ON episode (status, lingkup);
CREATE INDEX IF NOT EXISTS episode_waktu ON episode (waktu);
CREATE INDEX IF NOT EXISTS episode_sesi ON episode (sesi);

-- Pelajaran: aturan tahu-bahwa (Bab 6.2). Sumber kebenaran = berkas markdown di vault;
-- tabel ini indeks turunan yang dibangun ulang dari vault.
CREATE TABLE IF NOT EXISTS pelajaran (
  id                        TEXT PRIMARY KEY,
  pelajaran                 TEXT NOT NULL,
  pemicu                    TEXT NOT NULL,
  tindakan                  TEXT NOT NULL,
  lingkup                   TEXT NOT NULL,
  status                    TEXT NOT NULL CHECK (status IN ('hipotesis','usulan','aturan','dipersempit','ditarik')),
  keyakinan                 REAL NOT NULL DEFAULT 0.5,
  bukti                     TEXT NOT NULL DEFAULT '[]',
  kontra                    TEXT NOT NULL DEFAULT '[]',
  instrumen_saat_dibuat     TEXT NOT NULL DEFAULT '[]',
  berlaku_untuk             TEXT NOT NULL DEFAULT '{}',
  tinjau_setelah            TEXT,
  dibuat                    TEXT NOT NULL,
  terakhir_dikonfirmasi     TEXT,
  tinjau_ulang              INTEGER NOT NULL DEFAULT 0,
  ditinjau_manusia          INTEGER NOT NULL DEFAULT 0,
  veto_manusia              TEXT,
  berkas                    TEXT,                -- path relatif di vault
  tier_maks                 TEXT CHECK (tier_maks IS NULL OR tier_maks IN ('P','I','S')),  -- v2: tier tertinggi bukti (7.3)
  usulan_perluasan_lingkup  TEXT NOT NULL DEFAULT '[]',  -- v2: JSON array lingkup (7.3 langkah 3)
  sintesis                  TEXT,                -- v2: draf tulisan mesin sebelum disetujui (7.3 langkah 4)
  catatan                   TEXT                 -- v2: catatan bebas manusia
);
CREATE INDEX IF NOT EXISTS pelajaran_status_lingkup ON pelajaran (status, lingkup);

-- Prosedur: tahu-cara (Bab 6.5)
CREATE TABLE IF NOT EXISTS prosedur (
  id                TEXT PRIMARY KEY,
  prosedur          TEXT NOT NULL,
  tugas_pemicu      TEXT NOT NULL,
  langkah           TEXT NOT NULL,        -- JSON array string
  bentuk            TEXT NOT NULL,        -- teks | skrip:<path> | hook:<path> | skill:<nama>
  lingkup           TEXT NOT NULL,
  status            TEXT NOT NULL CHECK (status IN ('draf','teruji','aktif','dipersempit','ditarik')),
  tingkat_berhasil  REAL NOT NULL DEFAULT 0,   -- CACHE = eksekusi_berhasil / eksekusi_total; bukan sumber kebenaran
  bukti             TEXT NOT NULL DEFAULT '[]',
  berlaku_untuk     TEXT NOT NULL DEFAULT '{}',
  tinjau_setelah    TEXT,
  uji               TEXT,
  ditinjau_manusia  INTEGER NOT NULL DEFAULT 0,
  berkas            TEXT,
  eksekusi_total    INTEGER NOT NULL DEFAULT 0,   -- v2
  eksekusi_berhasil INTEGER NOT NULL DEFAULT 0,   -- v2
  gagal_beruntun    INTEGER NOT NULL DEFAULT 0,   -- v2: 2× → tinjau_ulang, 3× → ditarik (6.5)
  tinjau_ulang      INTEGER NOT NULL DEFAULT 0,   -- v2 (6.5, 7.4, 7.5)
  veto_manusia      TEXT,                         -- v2
  dibuat            TEXT,                         -- v2
  tier_maks         TEXT CHECK (tier_maks IS NULL OR tier_maks IN ('P','I','S')),  -- v2
  catatan           TEXT                          -- v2
);

-- Norma: ketentuan otoritas, bitemporal (Bab 6.3, 6.4)
CREATE TABLE IF NOT EXISTS norma (
  id                    TEXT PRIMARY KEY,
  norma                 TEXT NOT NULL,
  judul                 TEXT,
  jenis                 TEXT NOT NULL,          -- uu | pp | perpres | pmk | kepmen | sop-internal | kontrak | konsolidasi
  otoritatif            INTEGER NOT NULL DEFAULT 1,
  berlaku_sejak         TEXT,
  dicabut_oleh          TEXT,
  dibatalkan_oleh       TEXT,
  mengganti             TEXT NOT NULL DEFAULT '[]',
  disusun_dari          TEXT NOT NULL DEFAULT '[]',  -- hanya untuk tampilan konsolidasi
  alasan                TEXT,
  peralihan             TEXT,
  sumber_dokumen        TEXT,
  status                TEXT NOT NULL CHECK (status IN ('berlaku','dicabut','dibatalkan')),
  berkas                TEXT,
  berlaku_sampai        TEXT,                    -- v2: = berlaku_sejak pengganti; query titik-waktu satu klausa
  disusun_pada          TEXT,                    -- v2 (6.4)
  disusun_oleh          TEXT CHECK (disusun_oleh IS NULL OR disusun_oleh IN ('mesin','manusia')),  -- v2 (6.4)
  berlaku_untuk_tanggal TEXT,                    -- v2 (6.4)
  isi                   TEXT,                    -- v2: kutipan pasal kunci / ringkasan untuk di-embed, bukan teks lengkap
  catatan               TEXT                     -- v2
);
CREATE INDEX IF NOT EXISTS norma_berlaku ON norma (berlaku_sejak);
CREATE INDEX IF NOT EXISTS norma_jendela ON norma (berlaku_sejak, berlaku_sampai);

-- Vektor: satu baris per (item, jenis, koleksi). BLOB float32 little-endian.
CREATE TABLE IF NOT EXISTS vektor (
  item_id   TEXT NOT NULL,
  jenis     TEXT NOT NULL CHECK (jenis IN ('episode','pelajaran','prosedur','norma')),
  koleksi   TEXT NOT NULL,
  dimensi   INTEGER NOT NULL,
  vektor    BLOB NOT NULL,
  PRIMARY KEY (item_id, jenis, koleksi)
);

-- Identitas embedder per koleksi (ganti model diam-diam = recall turun tanpa gejala)
CREATE TABLE IF NOT EXISTS identitas_embedder (
  koleksi  TEXT PRIMARY KEY,
  model    TEXT NOT NULL,
  dimensi  INTEGER NOT NULL,
  dicatat  TEXT NOT NULL
);

-- State machine (Bab 5). Transisi yang tidak ada di tabel ini = terlarang.
-- oleh: 'mesin' | 'manusia' | 'keduanya'
CREATE TABLE IF NOT EXISTS transisi_status (
  jenis  TEXT NOT NULL,
  dari   TEXT NOT NULL,
  ke     TEXT NOT NULL,
  oleh   TEXT NOT NULL CHECK (oleh IN ('mesin','manusia','keduanya')),
  PRIMARY KEY (jenis, dari, ke)
);
INSERT OR IGNORE INTO transisi_status (jenis, dari, ke, oleh) VALUES
  ('episode',   'aktif',       'didinginkan', 'keduanya'),
  ('episode',   'didinginkan', 'diarsipkan',  'keduanya'),
  ('pelajaran', 'hipotesis',   'usulan',      'keduanya'),
  ('pelajaran', 'usulan',      'aturan',      'manusia'),
  ('pelajaran', 'aturan',      'dipersempit', 'keduanya'),
  ('pelajaran', 'hipotesis',   'ditarik',     'keduanya'),
  ('pelajaran', 'usulan',      'ditarik',     'keduanya'),
  ('pelajaran', 'aturan',      'ditarik',     'keduanya'),
  ('pelajaran', 'dipersempit', 'ditarik',     'keduanya'),
  ('pelajaran', 'dipersempit', 'aturan',      'manusia'),   -- pemulihan domain: hanya manusia
  ('prosedur',  'draf',        'teruji',      'keduanya'),
  ('prosedur',  'teruji',      'aktif',       'manusia'),
  ('prosedur',  'aktif',       'dipersempit', 'keduanya'),
  ('prosedur',  'draf',        'ditarik',     'keduanya'),
  ('prosedur',  'teruji',      'ditarik',     'keduanya'),
  ('prosedur',  'aktif',       'ditarik',     'keduanya'),
  ('prosedur',  'dipersempit', 'ditarik',     'keduanya'),
  ('prosedur',  'dipersempit', 'aktif',       'manusia'),   -- pemulihan domain: hanya manusia
  ('norma',     'berlaku',     'dicabut',     'manusia'),
  ('norma',     'berlaku',     'dibatalkan',  'manusia');

-- Riwayat setiap perubahan status (audit)
CREATE TABLE IF NOT EXISTS riwayat_status (
  id       INTEGER PRIMARY KEY,
  jenis    TEXT NOT NULL,
  item_id  TEXT NOT NULL,
  dari     TEXT NOT NULL,
  ke       TEXT NOT NULL,
  oleh     TEXT NOT NULL,
  waktu    TEXT NOT NULL,
  alasan   TEXT
);

-- v2: Metrik (Bab 11)
CREATE TABLE IF NOT EXISTS metrik (
  id       INTEGER PRIMARY KEY,
  waktu    TEXT NOT NULL,
  nama     TEXT NOT NULL,
  nilai    REAL NOT NULL,
  konteks  TEXT NOT NULL DEFAULT '{}'   -- JSON object
);

-- v2: Setiap panggilan ingat() tercatat (8.4); alarm > 10 per sesi (Bab 11)
CREATE TABLE IF NOT EXISTS panggilan_ingat (
  id            INTEGER PRIMARY KEY,
  waktu         TEXT NOT NULL,
  sesi          TEXT,
  lingkup       TEXT NOT NULL,
  query         TEXT NOT NULL,
  jumlah_item   INTEGER NOT NULL,
  token_dipakai INTEGER NOT NULL,
  jenis         TEXT NOT NULL            -- semua | norma | pelajaran | prosedur | bukti
);
CREATE INDEX IF NOT EXISTS panggilan_sesi ON panggilan_ingat (sesi);
