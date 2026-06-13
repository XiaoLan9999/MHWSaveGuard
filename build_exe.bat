@echo off
chcp 65001 >nul
cd /d "%~dp0"

python -m pip install -r requirements.txt
python tools\write_icon.py
python -m PyInstaller --noconfirm --onefile --windowed --name MHW_Save_Guard --icon assets\app_icon.ico --add-data "assets\app_icon.ico;assets" mhw_save_guard.py

echo Build output: dist\MHW_Save_Guard.exe
pause
