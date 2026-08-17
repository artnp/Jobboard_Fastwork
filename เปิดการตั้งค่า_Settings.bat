@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM 1. รัน start_bot.vbs เข้า System Tray
start "" "%~dp0start_bot.vbs"

REM 2. เปิดหน้าต่างตั้งค่า Settings (แบบไม่มีหน้าต่างดำ)
start "" pythonw "%~dp0settings_gui.py"

exit
