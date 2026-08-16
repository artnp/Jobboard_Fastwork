@echo off
chcp 65001 >nul
title Fastwork Bot
cd /d "%~dp0"

REM เริ่มการทำงานของบอทใน Background
start "" wscript.exe "start_bot.vbs"

REM เปิดหน้าต่างตั้งค่าบอท
start "" pythonw "settings_gui.py"

exit
