-- Skema Store Python sebelum tiket 2/3 SELARAS (vektor inline, AUTOINCREMENT). Dipakai uji migrasi.

CREATE TABLE IF NOT EXISTS episode (
  id TEXT PRIMARY KEY, waktu TEXT, sumber TEXT, tier TEXT, lingkup TEXT,
  jenis_kejadian TEXT, ringkas TEXT, instrumen TEXT, bobot INTEGER, status TEXT,
  isi_ref TEXT, langkah TEXT, sesi TEXT, vektor BLOB, model_embedding TEXT, diredaksi TEXT
);
CREATE INDEX IF NOT EXISTS ix_episode_status ON episode(status, tier);
CREATE TABLE IF NOT EXISTS pelajaran (
  id TEXT PRIMARY KEY, pelajaran TEXT, pemicu TEXT, tindakan TEXT, lingkup TEXT,
  status TEXT, keyakinan REAL, bukti TEXT, kontra TEXT, instrumen_saat_dibuat TEXT,
  berlaku_untuk TEXT, tinjau_setelah TEXT, dibuat TEXT, terakhir_dikonfirmasi TEXT,
  tinjau_ulang INTEGER, ditinjau_manusia INTEGER, veto_manusia TEXT, tier_maks TEXT,
  sintesis TEXT, usulan_perluasan_lingkup TEXT, catatan TEXT, vektor BLOB, model_embedding TEXT
);
CREATE TABLE IF NOT EXISTS prosedur (
  id TEXT PRIMARY KEY, prosedur TEXT, tugas_pemicu TEXT, langkah TEXT, lingkup TEXT,
  bentuk TEXT, status TEXT, eksekusi_total INTEGER, eksekusi_berhasil INTEGER,
  gagal_beruntun INTEGER, bukti TEXT, berlaku_untuk TEXT, tinjau_setelah TEXT, uji TEXT,
  ditinjau_manusia INTEGER, veto_manusia TEXT, tinjau_ulang INTEGER, dibuat TEXT,
  tier_maks TEXT, catatan TEXT, vektor BLOB, model_embedding TEXT
);
CREATE TABLE IF NOT EXISTS norma (
  id TEXT PRIMARY KEY, norma TEXT, judul TEXT, jenis TEXT, otoritatif INTEGER,
  berlaku_sejak TEXT, berlaku_sampai TEXT, dicabut_oleh TEXT, dibatalkan_oleh TEXT,
  mengganti TEXT, alasan TEXT, peralihan TEXT, sumber_dokumen TEXT, status TEXT,
  disusun_dari TEXT, disusun_pada TEXT, disusun_oleh TEXT, berlaku_untuk_tanggal TEXT,
  catatan TEXT, isi TEXT, vektor BLOB, model_embedding TEXT
);
CREATE TABLE IF NOT EXISTS instrumen (
  id TEXT PRIMARY KEY, nama TEXT, dipasang_sejak TEXT, cakupan TEXT, titik_buta_diketahui TEXT
);
CREATE TABLE IF NOT EXISTS riwayat_status (
  n INTEGER PRIMARY KEY AUTOINCREMENT, waktu TEXT, jenis TEXT, item_id TEXT,
  dari TEXT, ke TEXT, oleh TEXT, alasan TEXT
);
CREATE TABLE IF NOT EXISTS metrik (
  n INTEGER PRIMARY KEY AUTOINCREMENT, waktu TEXT, nama TEXT, nilai REAL, konteks TEXT
);
CREATE TABLE IF NOT EXISTS panggilan_ingat (
  n INTEGER PRIMARY KEY AUTOINCREMENT, waktu TEXT, sesi TEXT, lingkup TEXT, query TEXT,
  jumlah_item INTEGER, token_dipakai INTEGER, jenis TEXT
);
