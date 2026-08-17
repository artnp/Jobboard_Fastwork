#!/bin/bash
cd "$(dirname "$0")"

# รันบอทใน background ผ่าน start_bot.vbs (macOS ใช้ python3 แทน)
python3 fastwork_bot.py &

# เปิดหน้าต่างตั้งค่าบอท
python3 settings_gui.py
