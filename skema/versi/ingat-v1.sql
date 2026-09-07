-- SPDX-License-Identifier: Apache-2.0
-- Kontrak penyimpanan `ingat`. SQL portabel: TEXT untuk waktu (ISO 8601) dan JSON,
-- INTEGER 0/1 untuk boolean, tanpa AUTOINCREMENT, tanpa fungsi khusus SQLite.
-- Pragma SQLite (WAL, foreign_keys) TIDAK di sini — lihat src/simpan/sqlite.ts.

CREATE TABLE IF NOT EXISTS meta (
  kunci TEXT PRIMARY KEY,
  nilai TEXT NOT NULL
);
INSERT OR IGNORE INTO meta (kunci, nilai) VALUES ('versi_kontrak', '1');
-- Riwayat kontrak: v1 = 2026-09-06 (termasuk transisi pemulihan dipersempit→aturan/aktif oleh manusia).

-- Instrumen: tool/konektor yang menghasilkan observasi (Bab 6.6, 7.4)
CREATE TABLE IF NOT EXISTS instrumen (
  id              TEXT PRIMARY KEY,
  nama            TEXT NOT NULL,
  dipasang_sejak  TEXT,
  cakupan         TEXT,
  titik_buta      TEXT               -- JSON array
);

-- Episode: kejadian mentah (Bab 6.1). Semua tersimpan verbatim (K10).
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
  isi             TEXT,               -- verbatim, sudah lewat redaksi; NULL bila sudah didinginkan
  isi_ref         TEXT,               -- pointer ke penyimpanan dingin bila isi NULL
  diredaksi       TEXT NOT NULL DEFAULT '[]'  -- JSON array jenis kredensial yang diredaksi
);
CREATE INDEX IF NOT EXISTS episode_status_lingkup ON episode (status, lingkup);
CREATE INDEX IF NOT EXISTS episode_waktu ON episode (waktu);

-- Pelajaran: aturan tahu-bahwa (Bab 6.2). Sumber kebenaran = berkas markdown di vault;
-- tabel ini indeks turunan yang dibangun ulang dari vault.
CREATE TABLE IF NOT EXISTS pelajaran (
  id                    TEXT PRIMARY KEY,
  pelajaran             TEXT NOT NULL,
  pemicu                TEXT NOT NULL,
  tindakan              TEXT NOT NULL,
  lingkup               TEXT NOT NULL,
  status                TEXT NOT NULL CHECK (status IN ('hipotesis','usulan','aturan','dipersempit','ditarik')),
  keyakinan             REAL NOT NULL DEFAULT 0.5,
  bukti                 TEXT NOT NULL DEFAULT '[]',
  kontra                TEXT NOT NULL DEFAULT '[]',
  instrumen_saat_dibuat TEXT NOT NULL DEFAULT '[]',
  berlaku_untuk         TEXT NOT NULL DEFAULT '{}',
  tinjau_setelah        TEXT,
  dibuat                TEXT NOT NULL,
  terakhir_dikonfirmasi TEXT,
  tinjau_ulang          INTEGER NOT NULL DEFAULT 0,
  ditinjau_manusia      INTEGER NOT NULL DEFAULT 0,
  veto_manusia          TEXT,
  berkas                TEXT                -- path relatif di vault
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
  tingkat_berhasil  REAL NOT NULL DEFAULT 0,
  bukti             TEXT NOT NULL DEFAULT '[]',
  berlaku_untuk     TEXT NOT NULL DEFAULT '{}',
  tinjau_setelah    TEXT,
  uji               TEXT,
  ditinjau_manusia  INTEGER NOT NULL DEFAULT 0,
  berkas            TEXT
);

-- Norma: ketentuan otoritas, bitemporal (Bab 6.3, 6.4)
CREATE TABLE IF NOT EXISTS norma (
  id              TEXT PRIMARY KEY,
  norma           TEXT NOT NULL,
  judul           TEXT,
  jenis           TEXT NOT NULL,          -- uu | pp | perpres | pmk | kepmen | sop-internal | kontrak | konsolidasi
  otoritatif      INTEGER NOT NULL DEFAULT 1,
  berlaku_sejak   TEXT,
  dicabut_oleh    TEXT,
  dibatalkan_oleh TEXT,
  mengganti       TEXT NOT NULL DEFAULT '[]',
  disusun_dari    TEXT NOT NULL DEFAULT '[]',  -- hanya untuk tampilan konsolidasi
  alasan          TEXT,
  peralihan       TEXT,
  sumber_dokumen  TEXT,
  status          TEXT NOT NULL CHECK (status IN ('berlaku','dicabut','dibatalkan')),
  berkas          TEXT
);
CREATE INDEX IF NOT EXISTS norma_berlaku ON norma (berlaku_sejak);

-- Vektor: satu baris per (item, jenis). BLOB float32 little-endian.
CREATE TABLE IF NOT EXISTS vektor (
  item_id   TEXT NOT NULL,
  jenis     TEXT NOT NULL CHECK (jenis IN ('episode','pelajaran','prosedur','norma')),
  koleksi   TEXT NOT NULL,                -- nama koleksi embedding (mis. 'utama')
  dimensi   INTEGER NOT NULL,
  vektor    BLOB NOT NULL,
  PRIMARY KEY (item_id, jenis, koleksi)
);

-- Identitas embedder per koleksi (pelajaran dari kontrak MemPalace: ganti model diam-diam = recall turun)
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
