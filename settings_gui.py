import os
import sys
import json
import base64
import shutil
import threading
import requests
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import cookie_extractor
import updater

CONFIG_FILE = "config.json"
PORTFOLIO_DIR = "portfolio"
ICON_FILE = "icon.ico"

def load_config_data():
    if not os.path.exists(CONFIG_FILE):
        return {
            "keywords": [],
            "exclude_keywords": [],
            "check_interval_seconds": 300,
            "mode": "auto_offer",
            "desktop_notification": True,
            "auto_open_browser": True,
            "default_brief_url": "https://fastwork.co",
            "access_token": "",
            "auto_offer_config": {
                "budget": 100,
                "working_days": 1,
                "description": "สวัสดีครับ ยินดีให้บริการครับ พร้อมรับงานและส่งมอบได้ตามต้องการอย่างรวดเร็วและมีคุณภาพครับ"
            },
            "user_products": []
        }
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        messagebox.showerror("Error", f"ไม่สามารถอ่านไฟล์ config.json ได้: {e}")
        return {}

def save_config_data(data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        messagebox.showerror("Error", f"ไม่สามารถบันทึก config.json: {e}")
        return False

def get_startup_shortcut_path():
    startup_dir = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
    return os.path.join(startup_dir, "FastworkBot.vbs")

def is_start_on_boot_enabled():
    return os.path.exists(get_startup_shortcut_path())

def set_start_on_boot(enable: bool):
    shortcut_path = get_startup_shortcut_path()
    if enable:
        current_dir = os.path.abspath(os.getcwd())
        vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{current_dir}"
WshShell.Run "pythonw fastwork_bot.py", 0, False
'''
        try:
            with open(shortcut_path, "w", encoding="utf-8") as f:
                f.write(vbs_content)
        except Exception as e:
            print("Error creating startup shortcut:", e)
    else:
        if os.path.exists(shortcut_path):
            try:
                os.remove(shortcut_path)
            except Exception as e:
                print("Error removing startup shortcut:", e)

def fetch_fastwork_products(token):
    if not token or not token.strip():
        return False, "กรุณากรอก Access Token ก่อน", []
    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get("https://api.fastwork.co/api/v4/user/products", headers=headers, timeout=10)
        if r.status_code == 200:
            raw_products = r.json()
            products = []
            for p in raw_products:
                products.append({
                    "product_id": p.get("id"),
                    "title": p.get("title", ""),
                    "slug": p.get("slug", ""),
                    "tags": p.get("tags", [])
                })
            return True, f"พบสินค้าทั้งหมด {len(products)} รายการ", products
        elif r.status_code == 401:
            return False, "Access Token ไม่ถูกต้องหรือหมดอายุ (Unauthorized 401)", []
        else:
            return False, f"ดึงข้อมูลไม่สำเร็จ Status Code: {r.status_code}", []
    except Exception as e:
        return False, f"เกิดข้อผิดพลาดในการเชื่อมต่อ: {e}", []

def fetch_fastwork_me(token):
    if not token or not token.strip():
        return None
    headers = {
        "Authorization": f"Bearer {token.strip()}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    info = {"quota": "ไม่สามารถตรวจสอบได้", "user_id": "", "exp": ""}
    try:
        payload = token.strip().split('.')[1]
        payload += '=' * (-len(payload) % 4)
        jwt_data = json.loads(base64.b64decode(payload).decode('utf-8'))
        info["user_id"] = jwt_data.get("user_id", "")
        if "exp" in jwt_data:
            exp_date = datetime.fromtimestamp(jwt_data["exp"]).strftime('%Y-%m-%d %H:%M')
            info["exp"] = exp_date
    except Exception:
        pass

    try:
        r = requests.get("https://jobboard-api.fastwork.co/api/me", headers=headers, timeout=8)
        if r.status_code == 200:
            data = r.json()
            q = data.get("freelance_offers_quota", {})
            cur = q.get("current_freelance_offers_count", 0)
            mx = q.get("max_freelance_offers_count", 10)
            info["quota"] = f"{cur}/{mx} ข้อเสนอ"
    except Exception:
        pass

    return info

class SettingsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fastwork Bot - ระบบตั้งค่าและจัดการบอท")
        self.geometry("820x720")
        self.minsize(740, 640)
        
        # Apply icon if available
        if os.path.exists(ICON_FILE):
            try:
                self.iconbitmap(ICON_FILE)
            except Exception:
                pass

        # Load config
        self.config = load_config_data()
        self.ensure_portfolio_dir()

        self.setup_ui_styles()
        self.build_ui()
        self.load_values_to_ui()

    def ensure_portfolio_dir(self):
        if not os.path.exists(PORTFOLIO_DIR):
            os.makedirs(PORTFOLIO_DIR, exist_ok=True)
            readme_path = os.path.join(PORTFOLIO_DIR, "README.txt")
            if not os.path.exists(readme_path):
                with open(readme_path, "w", encoding="utf-8") as f:
                    f.write("วางไฟล์ผลงานตัวอย่าง เช่น PDF หรือรูปภาพ (JPG, PNG) ไว้ในโฟลเดอร์นี้\nระบบจะอัปโหลดแนบในใบเสนองานให้อัตโนมัติ (ไฟล์ละไม่เกิน 25MB สูงสุด 10 ไฟล์)")

    def setup_ui_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # Color definitions
        self.bg_color = "#F8FAFC"
        self.card_bg = "#FFFFFF"
        self.primary_color = "#0066FF"
        self.primary_hover = "#0052CC"
        self.text_dark = "#1E293B"
        self.text_muted = "#64748B"
        self.border_color = "#E2E8F0"
        self.success_color = "#10B981"
        self.danger_color = "#EF4444"

        self.configure(bg=self.bg_color)

        self.style.configure(".", font=("Segoe UI", 10), background=self.bg_color, foreground=self.text_dark)
        self.style.configure("TNotebook", background=self.bg_color, borderwidth=0)
        self.style.configure("TNotebook.Tab", font=("Segoe UI", 10, "bold"), padding=[16, 8], background="#E2E8F0", foreground=self.text_dark)
        self.style.map("TNotebook.Tab", background=[("selected", self.primary_color)], foreground=[("selected", "#FFFFFF")])

        self.style.configure("Card.TFrame", background=self.card_bg, relief="flat", borderwidth=1)
        self.style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), background=self.primary_color, foreground="#FFFFFF", borderwidth=0, padding=[12, 6])
        self.style.map("Primary.TButton", background=[("active", self.primary_hover)])
        self.style.configure("Secondary.TButton", font=("Segoe UI", 9), background="#F1F5F9", foreground=self.text_dark, borderwidth=1, padding=[10, 5])
        self.style.map("Secondary.TButton", background=[("active", "#E2E8F0")])

        self.style.configure("Success.TLabel", font=("Segoe UI", 9, "bold"), foreground=self.success_color, background=self.card_bg)
        self.style.configure("Warning.TLabel", font=("Segoe UI", 9, "bold"), foreground=self.danger_color, background=self.card_bg)

    def build_ui(self):
        # Header Banner
        header_frame = tk.Frame(self, bg=self.primary_color, height=65)
        header_frame.pack(fill="x", side="top")

        title_label = tk.Label(header_frame, text="⚡ Fastwork Auto-Offer Bot - Control Panel", font=("Segoe UI", 14, "bold"), bg=self.primary_color, fg="#FFFFFF")
        title_label.pack(side="left", padx=20, pady=12)

        subtitle_label = tk.Label(header_frame, text="ระบบจัดการและตั้งค่าบอทอัจฉริยะ", font=("Segoe UI", 9), bg=self.primary_color, fg="#E0E7FF")
        subtitle_label.pack(side="left", padx=5, pady=16)

        # Version & Update button on right side of header
        local_ver = updater.get_local_version_info().get("version", "1.0.0")
        ver_frame = tk.Frame(header_frame, bg=self.primary_color)
        ver_frame.pack(side="right", padx=15, pady=12)

        self.ver_badge = tk.Label(ver_frame, text=f"v{local_ver}", font=("Segoe UI", 9, "bold"), bg="#1E40AF", fg="#FFFFFF", padx=8, pady=3)
        self.ver_badge.pack(side="left", padx=(0, 8))

        btn_update = ttk.Button(ver_frame, text="🔄 ตรวจสอบอัปเดต", style="Secondary.TButton", command=self.check_update_action)
        btn_update.pack(side="left")

        # Tab Notebook
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=12)

        # Tabs
        self.tab_token = ttk.Frame(self.notebook)
        self.tab_offer = ttk.Frame(self.notebook)
        self.tab_keywords = ttk.Frame(self.notebook)
        self.tab_products = ttk.Frame(self.notebook)
        self.tab_portfolio = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_token, text="🔑 บัญชี & คุกกี้ Token")
        self.notebook.add(self.tab_offer, text="✍️ ใบเสนองาน")
        self.notebook.add(self.tab_keywords, text="🎯 คีย์เวิร์ดหางาน")
        self.notebook.add(self.tab_products, text="📦 สินค้าของฉัน")
        self.notebook.add(self.tab_portfolio, text="📎 ไฟล์ผลงาน PDF")

        self.build_tab_token()
        self.build_tab_offer()
        self.build_tab_keywords()
        self.build_tab_products()
        self.build_tab_portfolio()

        # Bottom Bar
        bottom_frame = tk.Frame(self, bg=self.bg_color, height=55)
        bottom_frame.pack(fill="x", side="bottom", padx=15, pady=10)

        self.status_label = tk.Label(bottom_frame, text="พร้อมทำงาน", font=("Segoe UI", 9), bg=self.bg_color, fg=self.text_muted)
        self.status_label.pack(side="left", pady=8)

        save_btn = ttk.Button(bottom_frame, text="💾 บันทึกการตั้งค่าทั้งหมด (Save Settings)", style="Primary.TButton", command=self.save_all_settings)
        save_btn.pack(side="right", padx=5)

    # ---------------- TAB 1: TOKEN & ACCOUNT ----------------
    def build_tab_token(self):
        container = tk.Frame(self.tab_token, bg=self.bg_color)
        container.pack(fill="both", expand=True, padx=15, pady=15)

        card = tk.Frame(container, bg=self.card_bg, highlightbackground=self.border_color, highlightthickness=1, padx=15, pady=15)
        card.pack(fill="x", pady=(0, 10))

        tk.Label(card, text="🔑 Fastwork Access Token & Cookies", font=("Segoe UI", 11, "bold"), bg=self.card_bg, fg=self.text_dark).pack(anchor="w")
        tk.Label(card, text="สามารถกดปุ่มดึงคุกกี้จากเบราว์เซอร์อัตโนมัติ หรือล็อกอินผ่านหน้าต่างเพื่อดึง Token เข้ามาให้อัตโนมัติ", font=("Segoe UI", 9), bg=self.card_bg, fg=self.text_muted).pack(anchor="w", pady=(0, 8))

        token_row = tk.Frame(card, bg=self.card_bg)
        token_row.pack(fill="x", pady=4)

        self.token_entry = ttk.Entry(token_row, font=("Segoe UI", 10), show="*")
        self.token_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.show_token_var = tk.BooleanVar(value=False)
        show_token_cb = ttk.Checkbutton(token_row, text="แสดง", variable=self.show_token_var, command=self.toggle_token_visibility)
        show_token_cb.pack(side="left", padx=(0, 8))

        # Auto Cookie / Token buttons row
        cookie_btn_row = tk.Frame(card, bg=self.card_bg)
        cookie_btn_row.pack(fill="x", pady=(10, 4))

        btn_interactive = ttk.Button(cookie_btn_row, text="🌐 ล็อกอิน Fastwork เพื่อดึง Token อัตโนมัติ", style="Primary.TButton", command=self.interactive_login_popup)
        btn_interactive.pack(side="left", padx=(0, 8))

        btn_paste = ttk.Button(cookie_btn_row, text="📋 วางจาก Clipboard", style="Secondary.TButton", command=self.paste_from_clipboard)
        btn_paste.pack(side="left")

        # Account info card
        self.info_card = tk.Frame(card, bg="#F8FAFC", highlightbackground=self.border_color, highlightthickness=1, padx=12, pady=10)
        self.info_card.pack(fill="x", pady=(12, 0))

        self.lbl_user_id = tk.Label(self.info_card, text="User ID: -", font=("Segoe UI", 9), bg="#F8FAFC", fg=self.text_dark)
        self.lbl_user_id.pack(anchor="w")

        self.lbl_quota = tk.Label(self.info_card, text="โควต้าข้อเสนอคงเหลือ: -", font=("Segoe UI", 9), bg="#F8FAFC", fg=self.text_dark)
        self.lbl_quota.pack(anchor="w")

        self.lbl_token_exp = tk.Label(self.info_card, text="Token หมดอายุ: -", font=("Segoe UI", 9), bg="#F8FAFC", fg=self.text_dark)
        self.lbl_token_exp.pack(anchor="w")

        # General Settings Card
        card2 = tk.Frame(container, bg=self.card_bg, highlightbackground=self.border_color, highlightthickness=1, padx=15, pady=12)
        card2.pack(fill="x", pady=5)

        tk.Label(card2, text="⚙️ การทำงานทั่วไป (General Options)", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.text_dark).pack(anchor="w", pady=(0, 8))

        # Default brief url
        tk.Label(card2, text="🌐 ลิงก์โปรไฟล์ / พอร์ตโฟลิโอ (Default Brief URL):", font=("Segoe UI", 9, "bold"), bg=self.card_bg).pack(anchor="w")
        self.brief_url_entry = ttk.Entry(card2, font=("Segoe UI", 10))
        self.brief_url_entry.pack(fill="x", pady=(2, 8))

        # Check interval & mode
        row_opts = tk.Frame(card2, bg=self.card_bg)
        row_opts.pack(fill="x", pady=4)

        tk.Label(row_opts, text="⏱️ ตรวจสอบงานทุกๆ (วินาที):", font=("Segoe UI", 9, "bold"), bg=self.card_bg).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.interval_entry = ttk.Entry(row_opts, width=10, font=("Segoe UI", 10))
        self.interval_entry.grid(row=0, column=1, sticky="w", padx=(0, 20))

        tk.Label(row_opts, text="🚀 โหมดการทำงาน:", font=("Segoe UI", 9, "bold"), bg=self.card_bg).grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.mode_map = {
            "auto_offer": "โพสต์ตอบกลับทันที",
            "notify": "แจ้งเตือนไม่ต้องโพสต์"
        }
        self.mode_reverse_map = {v: k for k, v in self.mode_map.items()}
        self.mode_combo = ttk.Combobox(row_opts, values=["โพสต์ตอบกลับทันที", "แจ้งเตือนไม่ต้องโพสต์"], state="readonly", width=22)
        self.mode_combo.grid(row=0, column=3, sticky="w")

        # Checkboxes
        chk_row = tk.Frame(card2, bg=self.card_bg)
        chk_row.pack(fill="x", pady=(10, 0))

        self.var_desktop_notify = tk.BooleanVar(value=True)
        ttk.Checkbutton(chk_row, text="🔔 แจ้งเตือน Desktop Notification", variable=self.var_desktop_notify).pack(side="left", padx=(0, 16))

        self.var_auto_open = tk.BooleanVar(value=True)
        ttk.Checkbutton(chk_row, text="🌐 เปิดหน้าเว็บ Chrome อัตโนมัติเมื่อเจองาน", variable=self.var_auto_open).pack(side="left", padx=(0, 16))

        self.var_start_boot = tk.BooleanVar(value=is_start_on_boot_enabled())
        ttk.Checkbutton(chk_row, text="🚀 เริ่มต้นโปรแกรมเมื่อเปิดเครื่อง (Startup)", variable=self.var_start_boot).pack(side="left")

    def toggle_token_visibility(self):
        if self.show_token_var.get():
            self.token_entry.config(show="")
        else:
            self.token_entry.config(show="*")

    # ---------------- TAB 2: AUTO OFFER & DESCRIPTION ----------------
    def build_tab_offer(self):
        container = tk.Frame(self.tab_offer, bg=self.bg_color)
        container.pack(fill="both", expand=True, padx=15, pady=15)

        card = tk.Frame(container, bg=self.card_bg, highlightbackground=self.border_color, highlightthickness=1, padx=15, pady=15)
        card.pack(fill="both", expand=True)

        tk.Label(card, text="📝 ข้อความใบเสนอราคา (Offer Description)", font=("Segoe UI", 11, "bold"), bg=self.card_bg, fg=self.text_dark).pack(anchor="w")
        tk.Label(card, text="ข้อความนี้จะถูกส่งไปยังผู้ว่าจ้างเมื่อบอทยื่นข้อเสนออัตโนมัติ (Fastwork บังคับอย่างน้อย 100 ตัวอักษร)", font=("Segoe UI", 9), bg=self.card_bg, fg=self.text_muted).pack(anchor="w", pady=(0, 8))

        self.desc_text = tk.Text(card, font=("Segoe UI", 10), height=9, wrap="word", relief="solid", borderwidth=1)
        self.desc_text.pack(fill="both", expand=True, pady=5)
        self.desc_text.bind("<KeyRelease>", self.update_char_count)

        self.lbl_char_count = tk.Label(card, text="จำนวนตัวอักษร: 0 ตัวอักษร", font=("Segoe UI", 9, "bold"), bg=self.card_bg, fg=self.danger_color)
        self.lbl_char_count.pack(anchor="w", pady=(2, 10))

        # Price and working days
        price_row = tk.Frame(card, bg=self.card_bg)
        price_row.pack(fill="x", pady=5)

        tk.Label(price_row, text="💰 ราคาเริ่มต้น (บาท):", font=("Segoe UI", 9, "bold"), bg=self.card_bg).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.budget_entry = ttk.Entry(price_row, width=12, font=("Segoe UI", 10))
        self.budget_entry.grid(row=0, column=1, sticky="w", padx=(0, 20))

        tk.Label(price_row, text="⏳ ระยะเวลาทำงาน (วัน):", font=("Segoe UI", 9, "bold"), bg=self.card_bg).grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.days_entry = ttk.Entry(price_row, width=12, font=("Segoe UI", 10))
        self.days_entry.grid(row=0, column=3, sticky="w")

        tk.Label(card, text="* หากผู้ว่าจ้างระบุงบประมาณในโพสต์ บอทจะใช้งบประมาณของผู้ว่าจ้างเป็นหลัก แต่หากไม่ระบุจะใช้ราคาเริ่มต้นนี้", font=("Segoe UI", 8), bg=self.card_bg, fg=self.text_muted).pack(anchor="w", pady=(8, 0))

    def update_char_count(self, event=None):
        text = self.desc_text.get("1.0", "end-1c")
        count = len(text)
        if count >= 100:
            self.lbl_char_count.config(text=f"✅ จำนวนตัวอักษร: {count} ตัวอักษร (ผ่านเกณฑ์)", fg=self.success_color)
        else:
            self.lbl_char_count.config(text=f"⚠️ จำนวนตัวอักษร: {count}/100 ตัวอักษร (ต้องมีอย่างน้อย 100 ตัวอักษร)", fg=self.danger_color)

    # ---------------- TAB 3: KEYWORDS ----------------
    def build_tab_keywords(self):
        container = tk.Frame(self.tab_keywords, bg=self.bg_color)
        container.pack(fill="both", expand=True, padx=15, pady=15)

        # Keywords Box
        card1 = tk.Frame(container, bg=self.card_bg, highlightbackground=self.border_color, highlightthickness=1, padx=15, pady=12)
        card1.pack(fill="both", expand=True, pady=(0, 10))

        tk.Label(card1, text="🎯 คีย์เวิร์ดที่ต้องการตรวจจับ (Keywords)", font=("Segoe UI", 11, "bold"), bg=self.card_bg, fg=self.text_dark).pack(anchor="w")
        tk.Label(card1, text="ใส่คีย์เวิร์ดที่ต้องการ 1 คำต่อ 1 บรรทัด (บอทจะจับงานที่มีคำเหล่านี้)", font=("Segoe UI", 9), bg=self.card_bg, fg=self.text_muted).pack(anchor="w", pady=(0, 6))

        self.kw_text = tk.Text(card1, font=("Segoe UI", 10), height=8, wrap="word", relief="solid", borderwidth=1)
        self.kw_text.pack(fill="both", expand=True, pady=4)

        # Exclude Keywords Box
        card2 = tk.Frame(container, bg=self.card_bg, highlightbackground=self.border_color, highlightthickness=1, padx=15, pady=12)
        card2.pack(fill="x")

        tk.Label(card2, text="🚫 คีย์เวิร์ดยกเว้น (Exclude Keywords - ไม่รับงานที่มีคำเหล่านี้)", font=("Segoe UI", 10, "bold"), bg=self.card_bg, fg=self.text_dark).pack(anchor="w")
        tk.Label(card2, text="ใส่คำที่ไม่ต้องการ 1 คำต่อ 1 บรรทัด หรือคั่นด้วยเครื่องหมายจุลภาค (,)", font=("Segoe UI", 9), bg=self.card_bg, fg=self.text_muted).pack(anchor="w", pady=(0, 6))

        self.ex_kw_text = tk.Text(card2, font=("Segoe UI", 10), height=3, wrap="word", relief="solid", borderwidth=1)
        self.ex_kw_text.pack(fill="x", pady=4)

    # ---------------- TAB 4: PRODUCTS ----------------
    def build_tab_products(self):
        container = tk.Frame(self.tab_products, bg=self.bg_color)
        container.pack(fill="both", expand=True, padx=15, pady=15)

        card = tk.Frame(container, bg=self.card_bg, highlightbackground=self.border_color, highlightthickness=1, padx=15, pady=15)
        card.pack(fill="both", expand=True)

        top_row = tk.Frame(card, bg=self.card_bg)
        top_row.pack(fill="x", pady=(0, 10))

        tk.Label(top_row, text="📦 รายการสินค้า/งานบริการของคุณบน Fastwork", font=("Segoe UI", 11, "bold"), bg=self.card_bg, fg=self.text_dark).pack(side="left")
        
        sync_prod_btn = ttk.Button(top_row, text="🔄 ดึงสินค้าล่าสุดจาก Fastwork", style="Primary.TButton", command=self.sync_account_and_products)
        sync_prod_btn.pack(side="right")

        tk.Label(card, text="บอทจะวิเคราะห์ชื่องานและรายละเอียดของผู้ว่าจ้าง แล้วจับคู่งานบริการที่เหมาะสมที่สุดให้อัตโนมัติ", font=("Segoe UI", 9), bg=self.card_bg, fg=self.text_muted).pack(anchor="w", pady=(0, 10))

        # Products Treeview Table
        tree_frame = tk.Frame(card)
        tree_frame.pack(fill="both", expand=True)

        cols = ("num", "title", "id")
        self.prod_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.prod_tree.heading("num", text="#")
        self.prod_tree.heading("title", text="ชื่องานบริการ (Product Title)")
        self.prod_tree.heading("id", text="Product ID")

        self.prod_tree.column("num", width=40, anchor="center")
        self.prod_tree.column("title", width=420, anchor="w")
        self.prod_tree.column("id", width=220, anchor="center")

        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.prod_tree.yview)
        self.prod_tree.configure(yscrollcommand=scroll.set)

        self.prod_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    # ---------------- TAB 5: PORTFOLIO ----------------
    def build_tab_portfolio(self):
        container = tk.Frame(self.tab_portfolio, bg=self.bg_color)
        container.pack(fill="both", expand=True, padx=15, pady=15)

        card = tk.Frame(container, bg=self.card_bg, highlightbackground=self.border_color, highlightthickness=1, padx=15, pady=15)
        card.pack(fill="both", expand=True)

        top_row = tk.Frame(card, bg=self.card_bg)
        top_row.pack(fill="x", pady=(0, 10))

        tk.Label(top_row, text="📎 ไฟล์ผลงานตัวอย่าง (Auto Portfolio Upload)", font=("Segoe UI", 11, "bold"), bg=self.card_bg, fg=self.text_dark).pack(side="left")

        btn_row = tk.Frame(top_row, bg=self.card_bg)
        btn_row.pack(side="right")

        add_file_btn = ttk.Button(btn_row, text="➕ เพิ่มไฟล์...", style="Primary.TButton", command=self.add_portfolio_file)
        add_file_btn.pack(side="left", padx=4)

        open_folder_btn = ttk.Button(btn_row, text="📁 เปิดโฟลเดอร์", style="Secondary.TButton", command=self.open_portfolio_folder)
        open_folder_btn.pack(side="left", padx=4)

        refresh_btn = ttk.Button(btn_row, text="🔄 รีเฟรช", style="Secondary.TButton", command=self.refresh_portfolio_list)
        refresh_btn.pack(side="left", padx=4)

        tk.Label(card, text="ไฟล์ PDF และรูปภาพที่วางในโฟลเดอร์ 'portfolio/' จะถูกอัปโหลดขึ้นช่อง 'ตัวอย่างผลงาน' ของ Fastwork อัตโนมัติทุกครั้งที่ยื่นงาน (สูงสุด 10 ไฟล์ ไม่เกิน 25MB ต่อไฟล์)", font=("Segoe UI", 9), bg=self.card_bg, fg=self.text_muted, wraplength=650, justify="left").pack(anchor="w", pady=(0, 10))

        # File List Treeview
        tree_frame = tk.Frame(card)
        tree_frame.pack(fill="both", expand=True)

        cols = ("name", "size", "type")
        self.file_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        self.file_tree.heading("name", text="ชื่อไฟล์")
        self.file_tree.heading("size", text="ขนาดไฟล์")
        self.file_tree.heading("type", text="ประเภท")

        self.file_tree.column("name", width=360, anchor="w")
        self.file_tree.column("size", width=120, anchor="center")
        self.file_tree.column("type", width=120, anchor="center")

        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=scroll.set)

        self.file_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        bottom_actions = tk.Frame(card, bg=self.card_bg)
        bottom_actions.pack(fill="x", pady=(10, 0))

        self.lbl_file_count = tk.Label(bottom_actions, text="จำนวนไฟล์: 0/10 ไฟล์", font=("Segoe UI", 9, "bold"), bg=self.card_bg, fg=self.text_dark)
        self.lbl_file_count.pack(side="left")

        del_btn = ttk.Button(bottom_actions, text="🗑️ ลบไฟล์ที่เลือก", style="Secondary.TButton", command=self.delete_selected_portfolio_file)
        del_btn.pack(side="right")

        self.refresh_portfolio_list()

    def open_portfolio_folder(self):
        self.ensure_portfolio_dir()
        os.startfile(os.path.abspath(PORTFOLIO_DIR))

    def add_portfolio_file(self):
        self.ensure_portfolio_dir()
        files = filedialog.askopenfilenames(
            title="เลือกไฟล์ผลงานตัวอย่าง",
            filetypes=[("Portfolio Files", "*.pdf;*.png;*.jpg;*.jpeg;*.webp"), ("PDF files", "*.pdf"), ("Image files", "*.png;*.jpg;*.jpeg;*.webp"), ("All Files", "*.*")]
        )
        if files:
            for f in files:
                try:
                    shutil.copy(f, PORTFOLIO_DIR)
                except Exception as e:
                    messagebox.showerror("Error", f"ไม่สามารถคัดลอกไฟล์ {f}: {e}")
            self.refresh_portfolio_list()

    def delete_selected_portfolio_file(self):
        selected = self.file_tree.selection()
        if not selected:
            messagebox.showinfo("แจ้งเตือน", "กรุณาเลือกไฟล์ที่ต้องการลบในตารางก่อน")
            return
        item = self.file_tree.item(selected[0])
        file_name = item["values"][0]
        file_path = os.path.join(PORTFOLIO_DIR, file_name)
        if os.path.exists(file_path):
            if messagebox.askyesno("ยืนยันการลบ", f"คุณต้องการลบไฟล์ '{file_name}' ออกจากโฟลเดอร์ผลงานหรือไม่?"):
                try:
                    os.remove(file_path)
                    self.refresh_portfolio_list()
                except Exception as e:
                    messagebox.showerror("Error", f"ไม่สามารถลบไฟล์ได้: {e}")

    def refresh_portfolio_list(self):
        self.file_tree.delete(*self.file_tree.get_children())
        if not os.path.exists(PORTFOLIO_DIR):
            return

        valid_exts = ('.pdf', '.jpg', '.jpeg', '.png', '.webp')
        files = [f for f in os.listdir(PORTFOLIO_DIR) if f.lower().endswith(valid_exts)]
        
        for f in files:
            p = os.path.join(PORTFOLIO_DIR, f)
            size_kb = os.path.getsize(p) / 1024
            size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB"
            ext = os.path.splitext(f)[1].upper()
            self.file_tree.insert("", "end", values=(f, size_str, ext))

        self.lbl_file_count.config(text=f"จำนวนไฟล์: {len(files)}/10 ไฟล์ (รองรับสูงสุด 10 ไฟล์)")

    # ---------------- AUTO COOKIE / TOKEN EXTRACTION ----------------
    def auto_extract_cookies_from_browser(self):
        self.status_label.config(text="กำลังสแกนคุกกี้จากเบราว์เซอร์...")
        ok, tok, msg = cookie_extractor.get_fastwork_token_from_browsers()
        
        if ok and tok:
            self.apply_new_token(tok, msg)
            return

        if msg.startswith("LOCKED:"):
            locked_browsers = msg.split("LOCKED:")[1]
            confirm = messagebox.askyesno(
                "เบราว์เซอร์กำลังเปิดอยู่",
                f"พบว่าเบราว์เซอร์ ({locked_browsers}) กำลังเปิดทำงานอยู่ ทำให้ระบบไม่สามารถอ่านไฟล์คุกกี้ได้\n\n"
                "คุณต้องการให้โปรแกรม 'ปิดเบราว์เซอร์ชั่วคราว' แล้วดึงคุกกี้ทันทีหรือไม่?\n"
                "(หรือกด No เพื่อใช้ปุ่ม 'ล็อกอิน Fastwork เพื่อดึง Token' แทน)"
            )
            if confirm:
                ok2, tok2, msg2 = cookie_extractor.get_fastwork_token_from_browsers(auto_close_browser=True)
                if ok2 and tok2:
                    self.apply_new_token(tok2, msg2)
                else:
                    messagebox.showerror("เกิดข้อผิดพลาด", msg2)
            return

        messagebox.showinfo("แจ้งเตือน", msg)

    def check_update_action(self):
        self.status_label.config(text="กำลังตรวจสอบอัปเดตจาก GitHub...")
        def worker():
            has_up, r_info, msg = updater.check_for_updates()
            def on_done():
                if has_up and r_info:
                    confirm = messagebox.askyesno(
                        "พบเวอร์ชันใหม่!",
                        f"{msg}\n\nคุณต้องการดาวน์โหลดและติดตั้งการอัปเดตเดี๋ยวนี้หรือไม่?\n(ไฟล์ตั้งค่าของคุณจะไม่ถูกลบหรือเขียนทับ)"
                    )
                    if confirm:
                        self.status_label.config(text="กำลังดาวน์โหลดไฟล์อัปเดต...")
                        def dl_worker():
                            ok, dl_msg = updater.perform_update(r_info)
                            def on_dl_done():
                                if ok:
                                    messagebox.showinfo("อัปเดตสำเร็จ", f"{dl_msg}\n\nกรุณาปิดและเปิดโปรแกรมใหม่อีกครั้งเพื่อเริ่มใช้งานเวอร์ชันใหม่")
                                    self.destroy()
                                else:
                                    messagebox.showerror("เกิดข้อผิดพลาด", dl_msg)
                            self.after(0, on_dl_done)
                        threading.Thread(target=dl_worker, daemon=True).start()
                else:
                    self.status_label.config(text=msg)
                    messagebox.showinfo("ตรวจสอบอัปเดต", msg)
            self.after(0, on_done)
        threading.Thread(target=worker, daemon=True).start()

    def interactive_login_popup(self):
        self.status_label.config(text="กำลังเปิดหน้าต่างล็อกอิน Fastwork...")
        def worker():
            ok, tok, msg = cookie_extractor.launch_interactive_fastwork_login()
            def on_done():
                if ok and tok:
                    self.apply_new_token(tok, msg)
                else:
                    self.status_label.config(text=msg)
                    messagebox.showwarning("แจ้งเตือน", msg)
            self.after(0, on_done)
        threading.Thread(target=worker, daemon=True).start()

    def paste_from_clipboard(self):
        try:
            content = self.clipboard_get().strip()
            if not content:
                messagebox.showwarning("แจ้งเตือน", "ไม่พบข้อความใน Clipboard")
                return
            # If full JWT
            if content.startswith("eyJ"):
                self.apply_new_token(content, "วาง Token จาก Clipboard สำเร็จ!")
                return
            # If cookie string e.g. accessToken=eyJ...
            if "accessToken=" in content:
                import re
                m = re.search(r'accessToken=([^;\s]+)', content)
                if m:
                    self.apply_new_token(m.group(1), "สกัดและวาง Token จากข้อความคุกกี้สำเร็จ!")
                    return
            # Fallback
            self.apply_new_token(content, "วางข้อความลงในช่อง Token แล้ว")
        except Exception as e:
            messagebox.showwarning("แจ้งเตือน", f"ไม่สามารถอ่าน Clipboard ได้: {e}")

    def apply_new_token(self, token, success_message=""):
        self.token_entry.delete(0, "end")
        self.token_entry.insert(0, token)
        self.config["access_token"] = token
        self.status_label.config(text=f"✅ {success_message}")
        self.sync_account_and_products()

    # ---------------- DATA LOADING & SYNC ----------------
    def load_values_to_ui(self):
        cfg = self.config

        # Token & account
        self.token_entry.delete(0, "end")
        self.token_entry.insert(0, cfg.get("access_token", ""))

        self.brief_url_entry.delete(0, "end")
        self.brief_url_entry.insert(0, cfg.get("default_brief_url", "https://fastwork.co"))

        self.interval_entry.delete(0, "end")
        self.interval_entry.insert(0, str(cfg.get("check_interval_seconds", 300)))

        mode_val = cfg.get("mode", "auto_offer")
        self.mode_combo.set(self.mode_map.get(mode_val, "โพสต์ตอบกลับทันที"))

        self.var_desktop_notify.set(cfg.get("desktop_notification", True))
        self.var_auto_open.set(cfg.get("auto_open_browser", True))
        self.var_start_boot.set(cfg.get("start_on_boot", is_start_on_boot_enabled()))

        # Offer
        offer_cfg = cfg.get("auto_offer_config", {})
        self.desc_text.delete("1.0", "end")
        self.desc_text.insert("1.0", offer_cfg.get("description", ""))
        self.update_char_count()

        self.budget_entry.delete(0, "end")
        self.budget_entry.insert(0, str(offer_cfg.get("budget", 100)))

        self.days_entry.delete(0, "end")
        self.days_entry.insert(0, str(offer_cfg.get("working_days", 1)))

        # Keywords
        kws = cfg.get("keywords", [])
        self.kw_text.delete("1.0", "end")
        self.kw_text.insert("1.0", "\n".join(kws))

        ex_kws = cfg.get("exclude_keywords", [])
        self.ex_kw_text.delete("1.0", "end")
        self.ex_kw_text.insert("1.0", "\n".join(ex_kws))

        # Products
        self.populate_products_tree(cfg.get("user_products", []))

        # Update Account info preview
        self.update_account_info_preview()

    def update_account_info_preview(self):
        token = self.token_entry.get().strip()
        if not token:
            return
        def worker():
            info = fetch_fastwork_me(token)
            if info:
                self.after(0, lambda: self.lbl_user_id.config(text=f"User ID: {info.get('user_id', '-')}") )
                self.after(0, lambda: self.lbl_quota.config(text=f"โควต้าข้อเสนอที่ใช้อยู่: {info.get('quota', '-')}") )
                self.after(0, lambda: self.lbl_token_exp.config(text=f"Token หมดอายุ: {info.get('exp', '-')}") )
        threading.Thread(target=worker, daemon=True).start()

    def populate_products_tree(self, products):
        self.prod_tree.delete(*self.prod_tree.get_children())
        for idx, p in enumerate(products, 1):
            self.prod_tree.insert("", "end", values=(idx, p.get("title", ""), p.get("product_id", "")))

    def sync_account_and_products(self):
        token = self.token_entry.get().strip()
        if not token:
            messagebox.showwarning("แจ้งเตือน", "กรุณากรอก Access Token ก่อนกดซิงค์ข้อมูล")
            return

        self.status_label.config(text="กำลังดึงข้อมูลจาก Fastwork...")
        def worker():
            ok, msg, prods = fetch_fastwork_products(token)
            info = fetch_fastwork_me(token)

            def update_ui():
                if ok:
                    self.config["user_products"] = prods
                    self.config["access_token"] = token
                    self.populate_products_tree(prods)
                    if info:
                        self.lbl_user_id.config(text=f"User ID: {info.get('user_id', '-')}")
                        self.lbl_quota.config(text=f"โควต้าข้อเสนอที่ใช้อยู่: {info.get('quota', '-')}")
                        self.lbl_token_exp.config(text=f"Token หมดอายุ: {info.get('exp', '-')}")
                    save_config_data(self.config)
                    self.status_label.config(text=f"✅ ซิงค์สำเร็จ! {msg}")
                    messagebox.showinfo("สำเร็จ", f"ซิงค์ข้อมูลเรียบร้อย!\n{msg}\nระบบได้บันทึกรายการสินค้าลง config.json แล้ว")
                else:
                    self.status_label.config(text=f"❌ {msg}")
                    messagebox.showerror("เกิดข้อผิดพลาด", msg)
            self.after(0, update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def save_all_settings(self):
        # 1. Token & General
        token = self.token_entry.get().strip()
        brief_url = self.brief_url_entry.get().strip()
        try:
            interval = int(self.interval_entry.get().strip())
        except ValueError:
            interval = 300
        mode = self.mode_reverse_map.get(self.mode_combo.get(), "auto_offer")

        # 2. Offer
        desc = self.desc_text.get("1.0", "end-1c").strip()
        try:
            budget = int(self.budget_entry.get().strip())
        except ValueError:
            budget = 100
        try:
            days = int(self.days_entry.get().strip())
        except ValueError:
            days = 1

        # 3. Keywords
        raw_kw = self.kw_text.get("1.0", "end-1c").strip()
        keywords = [k.strip() for k in raw_kw.splitlines() if k.strip()]

        raw_ex_kw = self.ex_kw_text.get("1.0", "end-1c").strip()
        exclude_keywords = []
        for line in raw_ex_kw.splitlines():
            for item in line.split(","):
                if item.strip():
                    exclude_keywords.append(item.strip())

        # 4. Startup Shortcut
        start_boot = self.var_start_boot.get()
        set_start_on_boot(start_boot)

        # Construct new config
        new_config = {
            "keywords": keywords,
            "exclude_keywords": exclude_keywords,
            "check_interval_seconds": interval,
            "mode": mode,
            "desktop_notification": self.var_desktop_notify.get(),
            "auto_open_browser": self.var_auto_open.get(),
            "start_on_boot": start_boot,
            "default_brief_url": brief_url,
            "access_token": token,
            "auto_offer_config": {
                "budget": budget,
                "working_days": days,
                "description": desc
            },
            "user_products": self.config.get("user_products", [])
        }

        if save_config_data(new_config):
            self.config = new_config
            self.status_label.config(text=f"✅ บันทึกการตั้งค่าเรียบร้อยแล้ว ({datetime.now().strftime('%H:%M:%S')})")
            messagebox.showinfo("บันทึกสำเร็จ", "บันทึกการตั้งค่าทั้งหมดเรียบร้อยแล้ว!\nบอทจะโหลดค่าใหม่ไปใช้งานอัตโนมัติ")

def main():
    app = SettingsApp()
    app.mainloop()

if __name__ == "__main__":
    main()
