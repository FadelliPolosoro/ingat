@echo off
REM Sinkron memori laptop -> VPS (K30): kirim perubahan vault (pelajaran/prosedur/norma
REM sebagai markdown) ke bare repo VPS. VPS punya cron yang pull + sinkron tiap 15 menit,
REM jadi dashboard/relay di perangkat lain ikut terbarui.
REM Dijalankan berkala oleh Task Scheduler (task: ingat-vault-sync). Episode TIDAK ikut
REM (hanya pointer dingin di laptop) -> tier S tak pernah keluar laptop.
setlocal
cd /d "%USERPROFILE%\.ingat\vault" || exit /b 1
git pull -q --no-edit
git add -A
REM commit hanya bila ada perubahan
git diff --cached --quiet || git -c user.email=laptop@ingat -c user.name=laptop commit -q -m "sinkron vault dari laptop"
git push -q
exit /b 0
