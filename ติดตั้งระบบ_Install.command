#!/bin/bash
cd "$(dirname "$0")"

echo "======================================================="
echo "   Fastwork Auto-Offer Bot - ระบบติดตั้งสำหรับ macOS"
echo "======================================================="
echo ""
echo "กำลังติดตั้ง Library ที่จำเป็นทั้งหมด..."
echo ""

pip3 install --upgrade pip
pip3 install requests pillow pystray plyer psutil playwright
python3 -m playwright install chromium

echo ""
echo "======================================================="
echo "   ✅ ติดตั้งระบบเรียบร้อยสมบูรณ์แล้ว!"
echo "   สามารถดับเบิลคลิกไฟล์ 'เปิดการตั้งค่า_Settings.command'"
echo "   เพื่อเริ่มต้นใช้งานได้เลย"
echo "======================================================="
echo ""
read -p "กด Enter เพื่อปิดหน้าต่างนี้..."
