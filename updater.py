import os
import sys
import json
import time
import shutil
import requests

VERSION_FILE = "version.json"
GITHUB_REPO = "artnp/Jobboard_Fastwork"
GITHUB_BRANCH = "main"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
REMOTE_VERSION_URL = f"{GITHUB_RAW_URL}/version.json"

DEFAULT_LOCAL_VERSION = {
    "version": "1.0.0",
    "release_date": "2026-08-16",
    "changelog": "เวอร์ชันเริ่มต้น - ระบบ Auto-Offer, GUI Control Panel, Portfolio Upload",
    "update_files": [
        "fastwork_bot.py",
        "settings_gui.py",
        "cookie_extractor.py",
        "updater.py"
    ]
}

def get_local_version_info():
    if os.path.exists(VERSION_FILE):
        try:
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_LOCAL_VERSION

def save_local_version_info(data):
    try:
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def parse_version_tuple(v_str):
    """Converts version string like '1.2.3' to tuple (1, 2, 3) for comparison."""
    try:
        clean = v_str.lower().lstrip('v').strip()
        return tuple(int(x) for x in clean.split('.'))
    except Exception:
        return (0, 0, 0)

def check_for_updates():
    """Checks GitHub for new version. Returns (has_update, remote_info, message)."""
    local_info = get_local_version_info()
    local_ver = local_info.get("version", "1.0.0")
    
    # Bypass GitHub raw caching with timestamp query param
    cache_buster = f"?t={int(time.time())}"
    url = f"{REMOTE_VERSION_URL}{cache_buster}"
    
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "FastworkBot-Updater"})
        if r.status_code == 200:
            remote_info = r.json()
            remote_ver = remote_info.get("version", "1.0.0")
            
            local_tuple = parse_version_tuple(local_ver)
            remote_tuple = parse_version_tuple(remote_ver)
            
            if remote_tuple > local_tuple:
                changelog = remote_info.get("changelog", "มีการปรับปรุงประสิทธิภาพและแก้ไขบั๊ก")
                return True, remote_info, f"พบเวอร์ชันใหม่ v{remote_ver} (ปัจจุบัน v{local_ver})\n\nรายละเอียดการอัปเดต:\n{changelog}"
            else:
                return False, remote_info, f"โปรแกรมเป็นเวอร์ชันล่าสุดแล้ว (v{local_ver})"
        elif r.status_code == 404:
            return False, None, "ไม่พบไฟล์ version.json บน GitHub กรุณาตรวจสอบว่าได้อัปโหลดไฟล์ขึ้น GitHub แล้ว"
        else:
            return False, None, f"ไม่สามารถตรวจสอบอัปเดตได้ Status Code: {r.status_code}"
    except Exception as e:
        return False, None, f"เกิดข้อผิดพลาดในการเชื่อมต่อ GitHub: {e}"

def perform_update(remote_info):
    """Downloads and replaces updated files from GitHub repository without touching config.json or user data."""
    if not remote_info:
        return False, "ไม่มีข้อมูลอัปเดต"

    update_files = remote_info.get("update_files", [
        "fastwork_bot.py",
        "settings_gui.py",
        "cookie_extractor.py",
        "updater.py"
    ])

    downloaded = []
    backup_dir = os.path.join(os.environ.get("TEMP", "."), f"fw_bot_bak_{int(time.time())}")
    os.makedirs(backup_dir, exist_ok=True)

    cache_buster = f"?t={int(time.time())}"

    # NEVER overwrite user private configuration files
    PROTECTED_FILES = ["config.json", "seen_jobs.json", "portfolio", "FastworkBotSession"]

    try:
        for fname in update_files:
            if fname in PROTECTED_FILES:
                continue

            file_url = f"{GITHUB_RAW_URL}/{fname}{cache_buster}"
            res = requests.get(file_url, timeout=12, headers={"User-Agent": "FastworkBot-Updater"})
            
            if res.status_code == 200:
                # Backup existing file if present
                if os.path.exists(fname):
                    shutil.copy2(fname, os.path.join(backup_dir, fname))

                # Write new file content
                with open(fname, "wb") as f:
                    f.write(res.content)
                downloaded.append(fname)
            else:
                print(f"Warning: Could not download {fname} (Status: {res.status_code})")

        if downloaded:
            # Update local version info
            save_local_version_info(remote_info)
            file_list_str = ", ".join(downloaded)
            return True, f"อัปเดตเวอร์ชัน v{remote_info.get('version')} สำเร็จ!\nไฟล์ที่ได้รับการอัปเดต: {file_list_str}"
        else:
            return False, "ไม่สามารถดาวน์โหลดไฟล์อัปเดตได้"
    except Exception as e:
        return False, f"เกิดข้อผิดพลาดขณะทำการอัปเดต: {e}"
