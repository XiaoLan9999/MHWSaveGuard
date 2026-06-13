@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    python mhw_save_guard.py
    goto :end
)

where py >nul 2>nul
if %errorlevel%==0 (
    py mhw_save_guard.py
    goto :end
)

echo 找不到 Python。
echo 请安装 Python 3，并勾选 Add Python to PATH。
pause

:end
