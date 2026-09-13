@echo off
REM Hentikan server ingat dengan menutup proses yang MENDENGARKAN di port 8765 dan 8790.
REM Presisi: hanya membunuh yang memegang port itu, bukan semua pythonw.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do taskkill /f /pid %%p >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8790" ^| findstr "LISTENING"') do taskkill /f /pid %%p >nul 2>&1
echo Server ingat (8765, 8790) dihentikan.
pause
