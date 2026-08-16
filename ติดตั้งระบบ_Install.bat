@echo off
chcp 65001 >nul
title Fastwork Bot - ติดตั้ง Library เสริม
cd /d "%~dp0"
color 0A

echo =======================================================
echo    Fastwork Auto-Offer Bot - ระบบติดตั้งอัตโนมัติ
echo =======================================================
echo.
echo กำลังตรวจสอบและติดตั้ง Library ที่จำเป็นทั้งหมด...
echo (ขั้นตอนนี้ทำเพียงครั้งแรกครั้งเดียว กรุณารอสักครู่)
echo.

python -m pip install --upgrade pip
python -m pip install requests pillow pystray plyer psutil playwright
python -m playwright install chromium

echo.
echo =======================================================
echo   ✅ ติดตั้งระบบเรียบร้อยสมบูรณ์แล้ว!
echo   คุณสามารถปิดหน้าต่างนี้ แล้วดับเบิลคลิกไฟล์ 
echo   "เปิดการตั้งค่า_Settings.bat" เพื่อเริ่มใช้งานได้เลย
echo =======================================================
echo.
pause
