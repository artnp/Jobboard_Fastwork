#!/bin/bash
cd "$(dirname "$0")"

# รันบอทและเปิดหน้าต่างตั้งค่าสำหรับ macOS
python3 -c "import subprocess, sys; subprocess.Popen([sys.executable, 'settings_gui.py']); subprocess.Popen([sys.executable, 'fastwork_bot.py'])"
