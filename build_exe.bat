@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name MHW_Save_Guard mhw_save_guard.py
echo Build output: dist\MHW_Save_Guard.exe
pause
