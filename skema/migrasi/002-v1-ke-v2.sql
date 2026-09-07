-- SPDX-License-Identifier: Apache-2.0
-- Migrasi kontrak v1 → v2 (2026-09-07). Hanya aditif + satu RENAME COLUMN yang aman (v1 tanpa penulis).
-- Sengaja TANPA CHECK pada kolom yang ditambah lewat ALTER (perilaku SQLite berbeda antar-versi);
-- validasi nilai ditegakkan di kode. Idempotensi diserahkan ke pemanggil (cek meta.versi_kontrak dulu).

ALTER TABLE instrumen RENAME COLUMN titik_buta TO titik_buta_diketahui;

ALTER TABLE episode ADD COLUMN langkah TEXT NOT NULL DEFAULT '[]';
ALTER TABLE episode ADD COLUMN sesi TEXT;
CREATE INDEX IF NOT EXISTS episode_sesi ON episode (sesi);

ALTER TABLE pelajaran ADD COLUMN tier_maks TEXT;
ALTER TABLE pelajaran ADD COLUMN usulan_perluasan_lingkup TEXT NOT NULL DEFAULT '[]';
ALTER TABLE pelajaran ADD COLUMN sintesis TEXT;
ALTER TABLE pelajaran ADD COLUMN catatan TEXT;

ALTER TABLE prosedur ADD COLUMN eksekusi_total INTEGER NOT NULL DEFAULT 0;
ALTER TABLE prosedur ADD COLUMN eksekusi_berhasil INTEGER NOT NULL DEFAULT 0;
ALTER TABLE prosedur ADD COLUMN gagal_beruntun INTEGER NOT NULL DEFAULT 0;
ALTER TABLE prosedur ADD COLUMN tinjau_ulang INTEGER NOT NULL DEFAULT 0;
ALTER TABLE prosedur ADD COLUMN veto_manusia TEXT;
ALTER TABLE prosedur ADD COLUMN dibuat TEXT;
ALTER TABLE prosedur ADD COLUMN tier_maks TEXT;
ALTER TABLE prosedur ADD COLUMN catatan TEXT;

ALTER TABLE norma ADD COLUMN berlaku_sampai TEXT;
ALTER TABLE norma ADD COLUMN disusun_pada TEXT;
ALTER TABLE norma ADD COLUMN disusun_oleh TEXT;
ALTER TABLE norma ADD COLUMN berlaku_untuk_tanggal TEXT;
ALTER TABLE norma ADD COLUMN isi TEXT;
ALTER TABLE norma ADD COLUMN catatan TEXT;
CREATE INDEX IF NOT EXISTS norma_jendela ON norma (berlaku_sejak, berlaku_sampai);

CREATE TABLE IF NOT EXISTS metrik (
  id       INTEGER PRIMARY KEY,
  waktu    TEXT NOT NULL,
  nama     TEXT NOT NULL,
  nilai    REAL NOT NULL,
  konteks  TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS panggilan_ingat (
  id            INTEGER PRIMARY KEY,
  waktu         TEXT NOT NULL,
  sesi          TEXT,
  lingkup       TEXT NOT NULL,
  query         TEXT NOT NULL,
  jumlah_item   INTEGER NOT NULL,
  token_dipakai INTEGER NOT NULL,
  jenis         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS panggilan_sesi ON panggilan_ingat (sesi);

-- Transisi pemulihan (masuk kontrak v1 tanggal 6 Sep; diulang di sini agar DB v1 lama pun mendapatkannya)
INSERT OR IGNORE INTO transisi_status (jenis, dari, ke, oleh) VALUES
  ('pelajaran', 'dipersempit', 'aturan', 'manusia'),
  ('prosedur',  'dipersempit', 'aktif',  'manusia');

UPDATE meta SET nilai = '2' WHERE kunci = 'versi_kontrak';
INSERT OR IGNORE INTO meta (kunci, nilai) VALUES ('kontrak_diperbarui', '2026-09-07');
