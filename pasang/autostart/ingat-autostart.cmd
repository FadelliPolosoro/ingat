@echo off
REM ingat auto-start: nyalakan API (8765, untuk ekstensi browser) + monitor (8790).
REM Dipanggil saat login lewat pintasan di folder Startup Windows (lihat README.md).
REM pythonw = Python tanpa jendela konsol; kedua server berjalan di latar dan tetap
REM hidup setelah skrip ini selesai.
setlocal
set "KONFIG=%USERPROFILE%\.ingat\konfigurasi.json"
if not exist "%KONFIG%" (
  echo [ingat] Konfig tidak ditemukan: %KONFIG%
  exit /b 1
)
REM serve = REST API + /dashboard (dipakai ekstensi browser di 127.0.0.1:8765)
start "" pythonw -m ingat --konfig "%KONFIG%" serve
REM pantau = monitor visual kesehatan store (127.0.0.1:8790), tanpa buka browser otomatis
start "" pythonw -m ingat --konfig "%KONFIG%" pantau --tanpa-buka --port 8790
exit /b 0
