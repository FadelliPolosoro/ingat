# Auto-start ingat di Windows (laptop otoritatif, K30)

Menyalakan otomatis saat login:
- `ingat serve` di `127.0.0.1:8765` — REST API + `/dashboard`, dipakai **ekstensi browser**.
- `ingat pantau` di `127.0.0.1:8790` — **monitor visual** kesehatan store.

Keduanya berjalan lewat `pythonw` (tanpa jendela konsol) dan tetap hidup setelah launcher selesai.

## Prasyarat
- `pip install -e .` sudah dijalankan (paket `ingat` importable oleh `pythonw`).
- `%USERPROFILE%\.ingat\konfigurasi.json` ada.
- `pythonw` ada di PATH (cek: `where pythonw`).

## Pasang auto-start (sekali)
Buat pintasan yang menjalankan `ingat-autostart.cmd` **tersembunyi** saat login. Cara paling bersih —
sebuah `.vbs` di folder Startup (menjalankan .cmd dengan jendela mode 0 = tersembunyi):

1. Buat berkas `ingat-autostart.vbs` berisi (sesuaikan path bila repo dipindah):
   ```vbs
   Set sh = CreateObject("WScript.Shell")
   sh.Run """<PATH-REPO>\pasang\autostart\ingat-autostart.cmd""", 0, False
   ```
2. Taruh di folder Startup:
   `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`
   (buka cepat: tekan Win+R, ketik `shell:startup`).

Selesai. Login berikutnya, kedua server menyala sendiri.

## Kelola
- **Cek status**: klik dua kali `ingat-cek.cmd` (atau `curl http://127.0.0.1:8765/sehat`).
- **Monitor**: buka `http://127.0.0.1:8790/`.
- **Hentikan**: klik dua kali `ingat-stop.cmd` (membunuh proses pemegang port 8765/8790 saja).
- **Nyalakan manual sekarang**: klik dua kali `ingat-autostart.cmd`.
- **Matikan auto-start**: hapus `ingat-autostart.vbs` dari folder Startup.

## Catatan
- Bila port sudah terpakai (server lain masih jalan), instans baru gagal bind dan berhenti sendiri —
  tidak merusak apa pun. Jalankan `ingat-stop.cmd` dulu bila ingin restart bersih.
- Karena `pythonw` tak punya konsol, log stdout tidak tertangkap. Untuk mendiagnosis, jalankan
  `python -m ingat --konfig %USERPROFILE%\.ingat\konfigurasi.json serve` manual di terminal agar log tampil.
- Berkas `.cmd` di sini sengaja **ASCII murni** (jebakan encoding Windows: berkas skrip non-ASCII
  bisa dibaca sebagai Windows-1252 dan memecah parser).
