import os
import sys
import time
import json
import logging
import threading
import subprocess
import webbrowser
import urllib.request
import urllib.parse
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import pystray
from pystray import MenuItem as item

try:
    from plyer import notification
except ImportError:
    notification = None

try:
    import winsound
except ImportError:
    winsound = None

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("FastworkBot")

CONFIG_FILE = "config.json"
SEEN_JOBS_FILE = "seen_jobs.json"
API_URL = "https://jobboard-api.fastwork.co/api/jobs"
ICON_FILE = "icon.png"

# Control Events
stop_event = threading.Event()
manual_trigger_event = threading.Event()
last_status_message = "บอทกำลังทำงานใน Background..."

class Notifier:
    def __init__(self, config: dict):
        self.config = config

    def notify(self, title: str, message: str, job_url: str = None):
        """Send notifications to all configured channels."""
        # 1. Desktop Notification
        if self.config.get("desktop_notification", True):
            self._send_desktop_notification(title, message)

        # 2. Discord Webhook
        discord_url = self.config.get("discord_webhook_url")
        if discord_url:
            self._send_discord_webhook(discord_url, title, message, job_url)

        # 3. Telegram Bot
        tg_token = self.config.get("telegram_bot_token")
        tg_chat_id = self.config.get("telegram_chat_id")
        if tg_token and tg_chat_id:
            self._send_telegram(tg_token, tg_chat_id, title, message, job_url)

        # 4. LINE Notify
        line_token = self.config.get("line_notify_token")
        if line_token:
            self._send_line_notify(line_token, title, message, job_url)

    def _send_desktop_notification(self, title: str, message: str):
        try:
            if winsound:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            if notification:
                notification.notify(
                    title=title[:60],
                    message=message[:250],
                    app_name="Fastwork Job Monitor",
                    timeout=10
                )
            else:
                logger.warning("plyer module not found for desktop notification.")
        except Exception as e:
            logger.error(f"Desktop notification error: {e}")

    def _send_discord_webhook(self, url: str, title: str, message: str, job_url: str):
        try:
            payload = {
                "embeds": [{
                    "title": f"🚨 {title}",
                    "description": message,
                    "url": job_url if job_url else "https://jobboard.fastwork.co/jobs",
                    "color": 3447003
                }]
            }
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
            urllib.request.urlopen(req, timeout=5)
            logger.info("Sent Discord notification")
        except Exception as e:
            logger.error(f"Discord webhook error: {e}")

    def _send_telegram(self, token: str, chat_id: str, title: str, message: str, job_url: str):
        try:
            text = f"<b>{title}</b>\n\n{message}"
            if job_url:
                text += f"\n\n🔗 <a href='{job_url}'>ดูรายละเอียดงานบน Fastwork</a>"
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
            logger.info("Sent Telegram notification")
        except Exception as e:
            logger.error(f"Telegram notification error: {e}")

    def _send_line_notify(self, token: str, title: str, message: str, job_url: str):
        try:
            full_msg = f"\n{title}\n{message}"
            if job_url:
                full_msg += f"\n{job_url}"
            url = "https://notify-api.line.me/api/notify"
            payload = urllib.parse.urlencode({"message": full_msg}).encode('utf-8')
            req = urllib.request.Request(url, data=payload, headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/x-www-form-urlencoded"
            })
            urllib.request.urlopen(req, timeout=5)
            logger.info("Sent LINE Notify notification")
        except Exception as e:
            logger.error(f"LINE Notify error: {e}")

def create_f_icon():
    """Generates the 'F' logo icon for system tray if missing."""
    if os.path.exists(ICON_FILE):
        try:
            return Image.open(ICON_FILE)
        except Exception:
            pass

    size = (64, 64)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([2, 2, 62, 62], radius=14, fill="#0066FF")
    try:
        font = ImageFont.truetype("arialbd.ttf", 42)
    except Exception:
        font = ImageFont.load_default()
    draw.text((20, 2), "F", fill="white", font=font)
    img.save(ICON_FILE)
    return img

def load_config():
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"Config file '{CONFIG_FILE}' not found.")
        sys.exit(1)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_seen_jobs():
    if os.path.exists(SEEN_JOBS_FILE):
        try:
            with open(SEEN_JOBS_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            logger.warning(f"Error reading {SEEN_JOBS_FILE}: {e}")
    return set()

def save_seen_jobs(seen_jobs):
    with open(SEEN_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_jobs), f, ensure_ascii=False, indent=2)

def fetch_jobs():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        response = requests.get(API_URL, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])
    except Exception as e:
        logger.error(f"Failed to fetch jobs from API: {e}")
        return []

def match_keywords(job, keywords, exclude_keywords):
    title = job.get("title", "") or ""
    description = job.get("description", "") or ""
    tag_name = (job.get("tag", {}) or {}).get("name", "") or ""
    
    text_content = f"{title} {description} {tag_name}".lower()

    # Check exclude keywords
    for ex_kw in exclude_keywords:
        if ex_kw.strip() and ex_kw.lower() in text_content:
            return False, []

    matched = []
    for kw in keywords:
        kw_clean = kw.strip()
        if kw_clean and kw_clean.lower() in text_content:
            matched.append(kw_clean)

    return len(matched) > 0, matched

def submit_offer(job_id, config):
    token = config.get("access_token", "").strip()
    if not token:
        logger.warning(f"Cannot submit offer for job {job_id}: Missing access_token in config.json")
        return False

    url = f"https://jobboard-api.fastwork.co/api/jobs/{job_id}/offers"
    offer_cfg = config.get("auto_offer_config", {})
    payload = {
        "price": offer_cfg.get("price", 300),
        "deliver_in_days": offer_cfg.get("deliver_in_days", 1),
        "message": offer_cfg.get("message", "สวัสดีครับ พร้อมรับงานและส่งมอบได้ตามต้องการครับ")
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code in [200, 201]:
            logger.info(f"✅ Successfully posted offer for job ID: {job_id}")
            return True
        else:
            logger.error(f"❌ Failed to post offer for job {job_id}. Status: {res.status_code}, Response: {res.text}")
            return False
    except Exception as e:
        logger.error(f"Exception while posting offer for job {job_id}: {e}")
        return False

def check_jobs_cycle(config, notifier, seen_jobs):
    global last_status_message
    keywords = config.get("keywords", [])
    exclude_keywords = config.get("exclude_keywords", [])
    mode = config.get("mode", "notify")

    jobs = fetch_jobs()
    if not jobs:
        logger.info("No jobs fetched or API request failed.")
        return 0

    new_matches_count = 0

    for job in jobs:
        job_id = job.get("id")
        if not job_id or job_id in seen_jobs:
            continue

        is_match, matched_kws = match_keywords(job, keywords, exclude_keywords)
        if is_match:
            new_matches_count += 1
            seen_jobs.add(job_id)

            title = job.get("title", "ไม่มีหัวข้อ")
            budget = job.get("budget", "ไม่ระบุ")
            desc = job.get("description", "").strip()
            desc_snippet = (desc[:150] + "...") if len(desc) > 150 else desc
            job_url = f"https://jobboard.fastwork.co/jobs/{job_id}"
            
            logger.info("=" * 60)
            logger.info(f"🎯 เจองานตรงคีย์เวิร์ด! ({', '.join(matched_kws)})")
            logger.info(f"📌 ชื่องาน: {title}")
            logger.info(f"💰 งบประมาณ: ฿{budget}")
            logger.info(f"📝 รายละเอียด: {desc_snippet}")
            logger.info(f"🔗 ลิงก์: {job_url}")
            logger.info("=" * 60)

            # Notification
            notify_title = f"🎯 เจองาน Fastwork ใหม่! [฿{budget}]"
            notify_msg = f"ชื่องาน: {title}\nคีย์เวิร์ด: {', '.join(matched_kws)}\nรายละเอียด: {desc_snippet}"
            notifier.notify(notify_title, notify_msg, job_url)

            # Auto open browser (Chrome)
            if config.get("auto_open_browser", True):
                try:
                    logger.info(f"🌐 Opening job in Chrome: {job_url}")
                    subprocess.Popen(f'start chrome "{job_url}"', shell=True)
                except Exception as e:
                    logger.error(f"Error opening browser: {e}")

            # Auto offer mode
            if mode == "auto_offer":
                submit_offer(job_id, config)

    if new_matches_count > 0:
        save_seen_jobs(seen_jobs)

    now_str = datetime.now().strftime("%H:%M:%S")
    last_status_message = f"เช็คล่าสุด {now_str} (เจองานใหม่ {new_matches_count} งาน)"
    return new_matches_count

def background_loop(icon):
    """Worker thread for background job checking."""
    logger.info("Background monitoring thread started.")
    config = load_config()
    notifier = Notifier(config)
    seen_jobs = load_seen_jobs()

    while not stop_event.is_set():
        config = load_config()  # reload in case user modified config.json
        interval = config.get("check_interval_seconds", 300)
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[{now_str}] Checking Fastwork Jobs...")

        try:
            matches = check_jobs_cycle(config, notifier, seen_jobs)
            logger.info(f"Cycle finished. {matches} new matched jobs found.")
        except Exception as e:
            logger.error(f"Error in check cycle: {e}")

        # Wait for interval or manual trigger or stop signal
        manual_trigger_event.clear()
        wait_seconds = 0
        while wait_seconds < interval and not stop_event.is_set():
            if manual_trigger_event.is_set():
                logger.info("Manual check triggered via System Tray.")
                manual_trigger_event.clear()
                break
            time.sleep(1)
            wait_seconds += 1

    logger.info("Background monitoring thread stopped.")

# System Tray Callbacks
def on_check_now(icon, item):
    manual_trigger_event.set()

def on_open_config(icon, item):
    if os.path.exists(CONFIG_FILE):
        os.startfile(CONFIG_FILE)

def on_open_folder(icon, item):
    os.startfile(os.getcwd())

def on_open_log(icon, item):
    if os.path.exists("bot.log"):
        os.startfile("bot.log")

def on_exit(icon, item):
    stop_event.set()
    icon.stop()

def get_status_text(item):
    return f"🟢 Fastwork Bot: {last_status_message}"

def main():
    icon_image = create_f_icon()

    # System Tray Menu
    menu = pystray.Menu(
        item(get_status_text, None, enabled=False),
        pystray.Menu.SEPARATOR,
        item("🔍 ตรวจหางานทันที (Check Now)", on_check_now),
        item("⚙️ แก้ไขไฟล์ตั้งค่า (config.json)", on_open_config),
        item("📄 ดูประวัติ Log (bot.log)", on_open_log),
        item("📁 เปิดโฟลเดอร์โปรแกรม", on_open_folder),
        pystray.Menu.SEPARATOR,
        item("❌ ปิดโปรแกรม (Exit)", on_exit)
    )

    icon = pystray.Icon("FastworkBot", icon_image, "Fastwork Job Monitor", menu)

    # Start background polling thread
    worker_thread = threading.Thread(target=background_loop, args=(icon,), daemon=True)
    worker_thread.start()

    logger.info("System Tray Icon started with 'F' logo.")
    # Run Tray Icon (Blocks until exit)
    icon.run()

if __name__ == "__main__":
    main()
