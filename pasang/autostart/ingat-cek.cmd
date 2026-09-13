@echo off
REM Cek apakah server ingat hidup di mesin ini.
echo Memeriksa server ingat...
curl -s -o nul -w "API     (8765 /sehat): HTTP %%{http_code}\n" http://127.0.0.1:8765/sehat
curl -s -o nul -w "Monitor (8790 /)     : HTTP %%{http_code}\n" http://127.0.0.1:8790/
echo.
echo Buka monitor: http://127.0.0.1:8790/
pause
