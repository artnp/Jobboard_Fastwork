import os
import sys
import time
import json
import logging
import threading
import subprocess
import re
import random
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
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("FastworkBot")

CONFIG_FILE = "config.json"
SEEN_JOBS_FILE = "seen_jobs.json"
PORTFOLIO_DIR = "portfolio"
API_URL = "https://jobboard-api.fastwork.co/api/jobs"
ICON_FILE = "icon.png"

# Control Events
stop_event = threading.Event()
manual_trigger_event = threading.Event()
last_status_message = "บอทกำลังทำงานใน Background..."

class Notifier:
    def __init__(self, config: dict):
        self.config = config

    def notify(self, title: str, message: str, skip_desktop: bool = False):
        """Send desktop notification if enabled and not skipped."""
        if not skip_desktop and self.config.get("desktop_notification", True):
            self._send_desktop_notification(title, message)

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

def save_config(config_data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving config: {e}")

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

def auto_sync_user_products_if_needed(config):
    """Automatically fetch and update user products from Fastwork API if user_products is empty or token missing."""
    import cookie_extractor
    token = config.get("access_token", "").strip()
    if not token:
        logger.info("🔍 ไม่พบ Access Token ใน config กำลังสแกนหาคุกกี้จากเบราว์เซอร์อัตโนมัติ...")
        ok, tok, msg = cookie_extractor.get_fastwork_token_from_browsers()
        if ok and tok:
            token = tok
            config["access_token"] = token
            save_config(config)
            logger.info(f"✅ {msg}")

    user_products = config.get("user_products", [])
    if not token or user_products:
        return

    logger.info("🔄 กำลังดึงรายการสินค้าจาก Fastwork อัตโนมัติ...")
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get("https://api.fastwork.co/api/v4/user/products", headers=headers, timeout=10)
        if r.status_code == 200:
            raw_products = r.json()
            old_prods_map = {p.get("product_id"): p for p in config.get("user_products", [])}
            products = []
            for p in raw_products:
                pid = p.get("id")
                old_p = old_prods_map.get(pid, {})
                products.append({
                    "product_id": pid,
                    "title": p.get("title", ""),
                    "slug": p.get("slug", ""),
                    "tags": p.get("tags", []),
                    "keywords": old_p.get("keywords", []),
                    "description": old_p.get("description", "")
                })
            config["user_products"] = products
            save_config(config)
            logger.info(f"✅ ซิงค์สินค้าอัตโนมัติสำเร็จ! พบทั้งหมด {len(products)} รายการ")
    except Exception as e:
        logger.warning(f"ไม่สามารถซิงค์สินค้าอัตโนมัติ: {e}")

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

def _is_keyword_in_text(kw: str, text: str) -> bool:
    kw_clean = kw.strip()
    if not kw_clean:
        return False
    # If keyword consists only of ASCII letters/digits/hyphens/spaces (e.g. 'ebook', 'seo', 'pdf', 'font')
    # ensure it's not part of another English word (e.g. 'facebook', 'macbook')
    if re.match(r'^[a-zA-Z0-9\s\-]+$', kw_clean):
        pattern = r'(?<![a-zA-Z0-9])' + re.escape(kw_clean.lower()) + r'(?![a-zA-Z0-9])'
        return bool(re.search(pattern, text, re.IGNORECASE))
    return kw_clean.lower() in text

def match_keywords(job, keywords, exclude_keywords):
    title = job.get("title", "") or ""
    description = job.get("description", "") or ""
    tag_name = (job.get("tag", {}) or {}).get("name", "") or ""
    
    text_content = f"{title} {description} {tag_name}".lower()

    for ex_kw in exclude_keywords:
        if _is_keyword_in_text(ex_kw, text_content):
            return False, []

    matched = []
    for kw in keywords:
        if _is_keyword_in_text(kw, text_content):
            matched.append(kw.strip())

    return len(matched) > 0, matched

def similarity_score(str1: str, str2: str) -> float:
    """Calculate Bigram similarity score matching Thai text patterns."""
    stop_words = ["รับ", "จ้าง", "ทำ", "ตก", "แต่ง", "ตัด", "ต่อ", "แก้ไข", "รูปภาพ", "รูป", "ภาพ", "ให้", "ดู", "งาน", "ฉัน", "หา", "ฟรีแลนซ์", "คน", "มา"]
    s1 = str1.lower()
    s2 = str2.lower()
    for word in stop_words:
        s1 = s1.replace(word, "")
        s2 = s2.replace(word, "")
    s1 = "".join(s1.split())
    s2 = "".join(s2.split())

    if s1 == s2 and len(s1) > 0:
        return 1.0
    if not s1 or not s2:
        return 0.0

    bg1 = [s1[i:i+2] for i in range(len(s1) - 1)]
    bg2 = [s2[i:i+2] for i in range(len(s2) - 1)]
    if not bg1 or not bg2:
        return 0.0

    intersection = 0
    bg2_copy = list(bg2)
    for b1 in bg1:
        if b1 in bg2_copy:
            intersection += 1
            bg2_copy.remove(b1)

    return (2.0 * intersection) / (len(bg1) + len(bg2))

def get_all_monitoring_keywords(config):
    """Combines global keywords with all product-specific keywords."""
    all_kws = []
    seen = set()
    for kw in config.get("keywords", []):
        k = kw.strip()
        if k and k.lower() not in seen:
            seen.add(k.lower())
            all_kws.append(k)
    for prod in config.get("user_products", []):
        for kw in prod.get("keywords", []):
            k = kw.strip()
            if k and k.lower() not in seen:
                seen.add(k.lower())
                all_kws.append(k)
    return all_kws

def get_all_exclude_keywords(config):
    """Combines global exclude keywords with any product-specific exclude keywords."""
    all_ex = []
    seen = set()
    for kw in config.get("exclude_keywords", []):
        k = kw.strip()
        if k and k.lower() not in seen:
            seen.add(k.lower())
            all_ex.append(k)
    for prod in config.get("user_products", []):
        for kw in prod.get("exclude_keywords", []):
            k = kw.strip()
            if k and k.lower() not in seen:
                seen.add(k.lower())
                all_ex.append(k)
    return all_ex

def select_best_product(job, config):
    """Select the best matching user product for a job based on direct product keywords, tags, title, and text similarity."""
    user_products = config.get("user_products", [])
    if not user_products:
        return None

    title = job.get("title", "") or ""
    description = job.get("description", "") or ""
    tag_name = (job.get("tag", {}) or {}).get("name", "") or ""
    job_text = f"{title} {description} {tag_name}".lower()

    best_product = None
    best_score = -1.0

    for prod in user_products:
        score = 0.0
        
        # 1. Direct Product Keywords (Highest Priority - 100+ points per match)
        prod_kws = prod.get("keywords", [])
        for pkw in prod_kws:
            if _is_keyword_in_text(pkw, job_text):
                # Longer keywords have even higher specificity
                score += 100.0 + (len(pkw.strip()) * 2.0)
        
        # 2. Check extra tags
        tags = prod.get("tags", [])
        for tag in tags:
            if tag and tag.lower() in job_text:
                score += 15.0
        
        # 3. Check match alias if defined
        match_title = prod.get("match", "").lower()
        if match_title and match_title in job_text:
            score += 20.0

        # 4. Product title words matching
        prod_title = prod.get("title", "")
        clean_symbols = ["|", "✅", "❌", "⚠️", "🔥", "📌", "✨", "[", "]", "(", ")", "/", "*", "#", "📖", "👆", "🎬", "🤖", "🔧", "🌐"]
        title_for_words = prod_title
        for sym in clean_symbols:
            title_for_words = title_for_words.replace(sym, " ")
        words = [w.strip() for w in title_for_words.split() if len(w.strip()) >= 2]
        for w in words:
            if w.lower() in job_text:
                score += 10.0

        # 5. Bigram similarity score
        sim = similarity_score(job_text, prod_title)
        score += sim * 10.0

        if score > best_score:
            best_score = score
            best_product = prod

    # Fallback to the first product if no specific score achieved
    if (not best_product or best_score <= 0) and user_products:
        best_product = user_products[0]

    return best_product

def ensure_offer_quota(token: str):
    """Checks offer quota on Fastwork and automatically deletes the oldest open offer if full (10/10)."""
    if not token:
        return
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        r_me = requests.get("https://jobboard-api.fastwork.co/api/me", headers=headers, timeout=10)
        if r_me.status_code == 200:
            quota_data = r_me.json().get("freelance_offers_quota", {})
            current_count = quota_data.get("current_freelance_offers_count", 0)
            max_count = quota_data.get("max_freelance_offers_count", 10)
            reached_quota = quota_data.get("reached_quota", False)

            if reached_quota or current_count >= max_count:
                logger.warning(f"⚠️ โควต้านำเสนองานเต็ม ({current_count}/{max_count}) กำลังค้นหาข้อเสนอเก่าสุดเพื่อลบ...")
                r_offers = requests.get(
                    "https://jobboard-api.fastwork.co/api/me/job-freelance-offers",
                    headers=headers,
                    params={"page": 1, "page_size": 20},
                    timeout=10
                )
                if r_offers.status_code == 200:
                    offers = r_offers.json().get("data", [])
                    open_offers = [o for o in offers if (o.get("job") or {}).get("status") == "open"]
                    open_offers.sort(key=lambda x: x.get("inserted_at", ""))

                    if open_offers:
                        oldest = open_offers[0]
                        oldest_id = oldest.get("id")
                        job_title = (oldest.get("job") or {}).get("title", "ไม่ระบุ")
                        del_url = f"https://jobboard-api.fastwork.co/api/job-freelance-offers/{oldest_id}"
                        r_del = requests.delete(del_url, headers=headers, timeout=10)
                        if r_del.status_code in [200, 204]:
                            logger.info(f"🗑️ ลบข้อเสนอเก่าสุดสำเร็จ: \"{job_title}\" (ID: {oldest_id}) เพื่อเปิดทางให้งานใหม่")
                        else:
                            logger.error(f"❌ ลบข้อเสนอเก่าไม่สำเร็จ Status: {r_del.status_code}, Response: {r_del.text}")
                    else:
                        logger.warning("ไม่พบข้อเสนอที่สถานะเปิดรับอยู่เพื่อทำการลบ")
    except Exception as e:
        logger.error(f"Error checking/freeing quota: {e}")

def upload_portfolio_files(token: str, job_id: str):
    """Uploads PDF and image portfolio files located in the portfolio/ folder to Fastwork Storage for brief_files."""
    if not os.path.exists(PORTFOLIO_DIR):
        return []

    valid_exts = ('.pdf', '.jpg', '.jpeg', '.png', '.webp')
    files = [f for f in os.listdir(PORTFOLIO_DIR) if f.lower().endswith(valid_exts)]
    if not files:
        return []

    # Limit to max 10 files (Fastwork maximum)
    files = files[:10]
    brief_files = []

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    for fname in files:
        fpath = os.path.join(PORTFOLIO_DIR, fname)
        try:
            # Check file size (max 25MB)
            if os.path.getsize(fpath) > 25 * 1024 * 1024:
                logger.warning(f"⚠️ ไฟล์ {fname} มีขนาดเกิน 25MB ข้ามการอัปโหลด")
                continue

            with open(fpath, "rb") as f:
                file_bytes = f.read()

            upload_url = f"https://api.fastwork.co/upload/v2/jobboard/brief?file_name={fname}&job_id={job_id}"
            res = requests.post(upload_url, data=file_bytes, headers=headers, timeout=25)
            if res.status_code in [200, 201]:
                res_data = res.json().get("data", {})
                uploaded_id = res_data.get("id")
                uploaded_url = res_data.get("url")
                if uploaded_id and uploaded_url:
                    is_img = fname.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
                    brief_files.append({
                        "id": uploaded_id,
                        "name": fname,
                        "type": "image" if is_img else "file",
                        "url": uploaded_url
                    })
                    logger.info(f"📎 อัปโหลดไฟล์ผลงานสำเร็จ: {fname}")
            else:
                logger.warning(f"⚠️ อัปโหลดไฟล์ {fname} ไม่สำเร็จ Status: {res.status_code}, Response: {res.text}")
        except Exception as e:
            logger.error(f"Error uploading file {fname}: {e}")

    return brief_files

def format_offer_description(template: str, job: dict, best_product: dict = None, budget_val: int = 100, working_days: int = 1, matched_kws: list = None) -> str:
    """
    Formats the offer proposal description by:
    1. Processing Spintax like {สวัสดีครับ|ยินดีให้บริการครับ|สวัสดีครับคุณลูกค้า}
    2. Replacing dynamic variables:
       - {job_title} or {title} -> real job title from client
       - {hashtags} or {keywords} or {matched_keywords} -> hashtags of matched keywords (e.g. #ตัดต่อเลข #แก้ตัวเลข)
       - {keyword} -> single primary matched keyword hashtag
       - {job_desc} or {job_description} -> snippet of client's job description
       - {budget} or {job_budget} -> budget value
       - {product_title} or {service} -> matching product/service title
       - {working_days} or {days} -> delivery days
    3. Ensuring Fastwork's >= 100 characters requirement.
    """
    if not template or not template.strip():
        template = "สวัสดีครับ ยินดีให้บริการครับ พร้อมรับงานและส่งมอบได้ตามต้องการอย่างรวดเร็วและมีคุณภาพครับ"

    text = template

    # 1. Process Spintax: e.g. {สวัสดีครับ|ยินดีให้บริการครับ} (only when contains '|')
    def spintax_replacer(match):
        content = match.group(1)
        if "|" in content:
            options = content.split("|")
            return random.choice(options).strip()
        # Not a spintax choice, keep as is for variable replacement
        return match.group(0)

    max_loops = 5
    while "{" in text and "|" in text and max_loops > 0:
        new_text = re.sub(r'\{([^{}]+?)\}', spintax_replacer, text)
        if new_text == text:
            break
        text = new_text
        max_loops -= 1

    # 2. Dynamic variable replacements
    job_title = (job.get("title") or "").strip()
    raw_desc = (job.get("description") or "").strip()
    job_desc_snippet = (raw_desc[:120] + "...") if len(raw_desc) > 120 else raw_desc
    product_title = (best_product.get("title") or "").strip() if best_product else ""

    # Format hashtags from matched keywords
    raw_tags = []
    if matched_kws:
        raw_tags = [k.strip() for k in matched_kws if k.strip()]
    elif best_product and best_product.get("keywords"):
        raw_tags = [k.strip() for k in best_product.get("keywords", [])[:3] if k.strip()]
    elif (job.get("tag") or {}).get("name"):
        raw_tags = [(job.get("tag") or {}).get("name", "").strip()]

    formatted_hashtags = []
    for t in raw_tags:
        clean_t = t.replace(" ", "")
        if not clean_t.startswith("#"):
            clean_t = f"#{clean_t}"
        if clean_t not in formatted_hashtags:
            formatted_hashtags.append(clean_t)

    hashtags_str = " ".join(formatted_hashtags) if formatted_hashtags else "#Fastwork"
    first_hashtag = formatted_hashtags[0] if formatted_hashtags else "#Fastwork"

    # Avoid duplicate ## if user wrote #{hashtags}
    if "#{hashtags}" in text:
        text = text.replace("#{hashtags}", hashtags_str)
    if "#{matched_keywords}" in text:
        text = text.replace("#{matched_keywords}", hashtags_str)
    if "#{keywords}" in text:
        text = text.replace("#{keywords}", hashtags_str)

    replacements = {
        "{hashtags}": hashtags_str,
        "{tags}": hashtags_str,
        "{keywords}": hashtags_str,
        "{matched_keywords}": hashtags_str,
        "{matched_kws}": hashtags_str,
        "{keyword}": first_hashtag,
        "{matched_keyword}": first_hashtag,
        "{job_title}": job_title,
        "{title}": job_title,
        "{job_desc}": job_desc_snippet,
        "{job_description}": job_desc_snippet,
        "{budget}": f"{budget_val:,}" if isinstance(budget_val, int) else str(budget_val),
        "{job_budget}": f"{budget_val:,}" if isinstance(budget_val, int) else str(budget_val),
        "{product_title}": product_title,
        "{service}": product_title,
        "{working_days}": str(working_days),
        "{days}": str(working_days),
    }

    for placeholder, val in replacements.items():
        if placeholder in text:
            text = text.replace(placeholder, val)

    text = text.strip()

    # 3. Fastwork requires description minimum 100 characters
    if len(text) < 100:
        padding_phrases = [
            " ยินดีเริ่มงานทันทีและส่งมอบผลงานคุณภาพสูงตามที่กำหนดครับ",
            " สามารถพูดคุยสอบถามและปรับแก้รายละเอียดงานได้ตลอดเวลาครับ",
            " ขอบคุณที่ให้ความสนใจและยินดีร่วมงานด้วยความเต็มใจครับ"
        ]
        p_idx = 0
        while len(text) < 100:
            text += padding_phrases[p_idx % len(padding_phrases)]
            p_idx += 1
        text = text.strip()

    return text

def submit_offer(job_id, job, config, matched_kws: list = None):
    token = config.get("access_token", "").strip()
    if not token:
        logger.warning(f"Cannot submit offer for job {job_id}: Missing access_token in config.json")
        return False

    # 1. Ensure quota is available before posting (delete oldest open offer if full)
    ensure_offer_quota(token)

    # 2. Upload any portfolio attachment files (PDF/Images)
    brief_files = upload_portfolio_files(token, job_id)

    url = f"https://jobboard-api.fastwork.co/api/jobs/{job_id}/offers"
    offer_cfg = config.get("auto_offer_config", {})
    
    # Auto-select best matching product based on job description & title
    best_product = select_best_product(job, config)
    product_id = best_product.get("product_id") if best_product else None
    
    # Determine budget (use job budget or configured price/budget, min 1)
    raw_budget = job.get("budget") or job.get("budget_2")
    try:
        budget_val = int(raw_budget) if raw_budget else int(offer_cfg.get("budget", offer_cfg.get("price", 100)))
    except (ValueError, TypeError):
        budget_val = int(offer_cfg.get("budget", offer_cfg.get("price", 100)))
    if budget_val < 1:
        budget_val = 100

    working_days = offer_cfg.get("working_days", offer_cfg.get("deliver_in_days", 1))
    try:
        working_days = max(1, int(working_days))
    except (ValueError, TypeError):
        working_days = 1

    # Check if best_product has a custom offer description
    custom_desc = (best_product.get("description") or "").strip() if best_product else ""
    if custom_desc:
        template = custom_desc
        logger.info(f"📝 ใช้ข้อความเฉพาะสำหรับสินค้า: \"{best_product.get('title', '')[:40]}...\"")
    else:
        template = offer_cfg.get("description", offer_cfg.get("message", "สวัสดีครับ ยินดีให้บริการครับ พร้อมรับงานและส่งมอบได้ตามต้องการอย่างรวดเร็วและมีคุณภาพครับ"))
        logger.info("📝 ใช้ข้อความมาตรฐานเริ่มต้น (Default Description)")

    message = format_offer_description(template, job, best_product, budget_val, working_days, matched_kws=matched_kws)

    raw_brief_url = config.get("default_brief_url", "")
    brief_url = raw_brief_url.strip() if isinstance(raw_brief_url, str) else ""

    offer_data = {
        "description": message,
        "budget": budget_val,
        "working_days": working_days
    }
    
    if brief_files:
        offer_data["brief_files"] = brief_files
    
    if brief_url:
        if not brief_url.startswith("http://") and not brief_url.startswith("https://"):
            brief_url = f"https://{brief_url}"
        offer_data["brief_url"] = brief_url
    
    if product_id:
        offer_data["product_id"] = product_id

    payload = {
        "job_freelance_offer": offer_data
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://jobboard.fastwork.co",
        "Referer": f"https://jobboard.fastwork.co/jobs/{job_id}"
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        prod_name = best_product.get("title") if best_product else "ไม่ได้ระบุ"
        if res.status_code in [200, 201]:
            logger.info(f"✅ ยื่นข้อเสนอสำเร็จ! Job ID: {job_id} | สินค้า: {prod_name} | งบ: ฿{budget_val} | แนบผลงาน: {len(brief_files)} ไฟล์")
            desc_preview = (message[:70] + "...") if len(message) > 70 else message
            logger.info(f"💬 ข้อความที่ส่ง: {desc_preview}")
            return True
        else:
            logger.error(f"❌ Failed to post offer for job {job_id}. Status: {res.status_code}, Response: {res.text}")
            return False
    except Exception as e:
        logger.error(f"Exception while posting offer for job {job_id}: {e}")
        return False

def check_jobs_cycle(config, notifier, seen_jobs):
    global last_status_message
    keywords = get_all_monitoring_keywords(config)
    exclude_keywords = get_all_exclude_keywords(config)
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
            
            best_product = select_best_product(job, config)
            if best_product:
                logger.info(f"📦 แมตช์งานของคุณ: {best_product.get('title')}")
            logger.info("=" * 60)

            # 1. Auto offer mode (Submit API offer FIRST for maximum speed)
            posted = False
            if mode == "auto_offer":
                posted = submit_offer(job_id, job, config, matched_kws=matched_kws)

            # 2. Desktop Notification
            notify_title = f"🎯 เจองาน Fastwork ใหม่! [฿{budget}]"
            notify_msg = f"ชื่องาน: {title}\nคีย์เวิร์ด: {', '.join(matched_kws)}\nรายละเอียด: {desc_snippet}"
            notifier.notify(notify_title, notify_msg, skip_desktop=(mode == "auto_offer"))

            # 3. Auto open browser in Chrome AFTER offer is posted
            if config.get("auto_open_browser", True):
                try:
                    logger.info(f"🌐 Opening job in Chrome: {job_url}")
                    subprocess.Popen(f'start chrome "{job_url}"', shell=True)
                except Exception as e:
                    logger.error(f"Error opening browser: {e}")

    if new_matches_count > 0:
        save_seen_jobs(seen_jobs)

    now_str = datetime.now().strftime("%H:%M:%S")
    last_status_message = f"เช็คล่าสุด {now_str} (เจองานใหม่ {new_matches_count} งาน)"
    return new_matches_count

def background_loop(icon):
    """Worker thread for background job checking."""
    logger.info("Background monitoring thread started.")
    config = load_config()
    auto_sync_user_products_if_needed(config)
    notifier = Notifier(config)
    seen_jobs = load_seen_jobs()

    while not stop_event.is_set():
        config = load_config()
        interval = config.get("check_interval_seconds", 300)
        
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"[{now_str}] Checking Fastwork Jobs...")

        try:
            matches = check_jobs_cycle(config, notifier, seen_jobs)
            logger.info(f"Cycle finished. {matches} new matched jobs found.")
        except Exception as e:
            logger.error(f"Error in check cycle: {e}")

        # Sleep efficiently without CPU wakeups until interval expires or manual check is triggered
        manual_trigger_event.wait(timeout=interval)
        manual_trigger_event.clear()

    logger.info("Background monitoring thread stopped.")

# System Tray Callbacks
def on_check_now(icon, item):
    manual_trigger_event.set()

def on_open_settings_gui(icon, item):
    try:
        if getattr(sys, 'frozen', False):
            subprocess.Popen([sys.executable, "--settings"])
        else:
            subprocess.Popen([sys.executable, "settings_gui.py"])
    except Exception as e:
        logger.error(f"Error opening settings GUI: {e}")

def open_path(target_path):
    """Opens a file or directory in the default system file explorer / viewer cross-platform."""
    try:
        if sys.platform == "win32":
            os.startfile(target_path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target_path])
        else:
            subprocess.Popen(["xdg-open", target_path])
    except Exception as e:
        logger.error(f"Error opening path {target_path}: {e}")

def on_check_update(icon, item):
    on_open_settings_gui(icon, item)

def on_open_portfolio(icon, item):
    if not os.path.exists(PORTFOLIO_DIR):
        os.makedirs(PORTFOLIO_DIR, exist_ok=True)
    open_path(os.path.abspath(PORTFOLIO_DIR))

def on_open_config(icon, item):
    if os.path.exists(CONFIG_FILE):
        open_path(os.path.abspath(CONFIG_FILE))

def on_open_guide(icon, item):
    guide_path = os.path.abspath(os.path.join("how_to_install", "index.html"))
    if os.path.exists(guide_path):
        open_path(guide_path)

def on_open_folder(icon, item):
    if getattr(sys, 'frozen', False):
        open_path(os.path.dirname(sys.executable))
    else:
        open_path(os.getcwd())

def on_exit(icon, item):
    stop_event.set()
    manual_trigger_event.set()
    icon.stop()

def get_status_text(item):
    return f"🟢 Fastwork Bot: {last_status_message}"

def create_f_icon():
    """Load or generate the fastwork 'F' icon for system tray."""
    icon_png = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    icon_ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    
    if os.path.exists(icon_png):
        try:
            return Image.open(icon_png)
        except Exception:
            pass
    if os.path.exists(icon_ico):
        try:
            return Image.open(icon_ico)
        except Exception:
            pass

    # Fallback dynamically generated crisp blue F icon
    img = Image.new('RGBA', (64, 64), color=(0, 102, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 12, 24, 52], fill='white')
    draw.rectangle([24, 12, 48, 20], fill='white')
    draw.rectangle([24, 28, 42, 36], fill='white')
    return img

_bot_socket_lock = None

def acquire_single_instance_lock():
    """Ensure only one instance of fastwork_bot runs in system tray at a time using local socket lock."""
    global _bot_socket_lock
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1', 58923))
        s.listen(5)
        _bot_socket_lock = s
        
        def drain_pings():
            while True:
                try:
                    conn, _ = s.accept()
                    conn.close()
                except Exception:
                    break
        threading.Thread(target=drain_pings, daemon=True).start()
        return True
    except Exception:
        return False

def main():
    if not acquire_single_instance_lock():
        logger.info("⚡ Fastwork Bot กำลังทำงานอยู่ใน System Tray อยู่แล้ว")
        return

    icon_image = create_f_icon()

    menu = pystray.Menu(
        item(get_status_text, None, enabled=False),
        pystray.Menu.SEPARATOR,
        item("🔍 ตรวจหางานทันที (Check Now)", on_check_now),
        item("⚙️ หน้าต่างตั้งค่าบอท (Settings UI)", on_open_settings_gui),
        item("🔄 ตรวจสอบอัปเดต (Check Update)", on_check_update),
        pystray.Menu.SEPARATOR,
        item("❌ ปิดโปรแกรม (Exit)", on_exit)
    )

    icon = pystray.Icon("FastworkBot", icon_image, "Fastwork Job Monitor", menu)

    worker_thread = threading.Thread(target=background_loop, args=(icon,), daemon=True)
    worker_thread.start()

    logger.info("System Tray Icon started with 'F' logo.")
    icon.run()

if __name__ == "__main__":
    if "--settings" in sys.argv:
        import settings_gui
        settings_gui.main()
    else:
        main()
