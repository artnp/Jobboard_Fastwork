import os
import sys
import json
import base64
import shutil
import threading
import requests
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import cookie_extractor
import updater

CONFIG_FILE = "config.json"
PORTFOLIO_DIR = "portfolio"
ICON_FILE = "icon.ico"

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
        print(f"Error opening path {target_path}: {e}")

def add_text_context_menu(widget, on_change=None):
    """Adds a right-click context menu (Cut, Copy, Paste, Delete, Select All)
    and robust Ctrl+A, Ctrl+C, Ctrl+V, Ctrl+X bindings supporting all keyboard layouts (Thai/EN)."""
    menu = tk.Menu(widget, tearoff=0, font=("Segoe UI", 9), bg="#FFFFFF", fg="#1E293B", activebackground="#0066FF", activeforeground="#FFFFFF")

    def do_cut():
        try:
            widget.event_generate("<<Cut>>")
            if on_change:
                widget.after(10, on_change)
        except Exception:
            pass

    def do_copy():
        try:
            widget.event_generate("<<Copy>>")
        except Exception:
            pass

    def do_paste():
        try:
            widget.event_generate("<<Paste>>")
            if on_change:
                widget.after(10, on_change)
        except Exception:
            pass

    def do_select_all():
        try:
            if isinstance(widget, tk.Text):
                widget.tag_add("sel", "1.0", "end")
                widget.mark_set("insert", "1.0")
            elif isinstance(widget, (tk.Entry, ttk.Entry)):
                widget.select_range(0, "end")
                widget.icursor("end")
        except Exception:
            pass

    def do_delete():
        try:
            if isinstance(widget, tk.Text):
                if widget.tag_ranges("sel"):
                    widget.delete("sel.first", "sel.last")
            elif isinstance(widget, (tk.Entry, ttk.Entry)):
                if widget.selection_present():
                    widget.delete(tk.SEL_FIRST, tk.SEL_LAST)
            if on_change:
                widget.after(10, on_change)
        except Exception:
            pass

    menu.add_command(label="✂️ ตัด (Cut)", accelerator="Ctrl+X", command=do_cut)
    menu.add_command(label="📋 คัดลอก (Copy)", accelerator="Ctrl+C", command=do_copy)
    menu.add_command(label="📥 วาง (Paste)", accelerator="Ctrl+V", command=do_paste)
    menu.add_command(label="🗑️ ลบ (Delete)", command=do_delete)
    menu.add_separator()
    menu.add_command(label="🔘 เลือกทั้งหมด (Select All)", accelerator="Ctrl+A", command=do_select_all)

    def show_popup(event):
        try:
            widget.focus_set()
            has_selection = False
            if isinstance(widget, tk.Text):
                has_selection = bool(widget.tag_ranges("sel"))
            elif isinstance(widget, (tk.Entry, ttk.Entry)):
                has_selection = widget.selection_present()
            
            state_sel = "normal" if has_selection else "disabled"
            menu.entryconfig(0, state=state_sel)  # Cut
            menu.entryconfig(1, state=state_sel)  # Copy
            menu.entryconfig(3, state=state_sel)  # Delete
            
            menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass
        finally:
            menu.grab_release()

    widget.bind("<Button-3>", show_popup)
    widget.bind("<Button-2>", show_popup)

    # Key binding shortcuts (supporting Thai & EN keyboard layouts)
    def handle_select_all(event):
        do_select_all()
        return "break"

    def handle_copy(event):
        do_copy()
        return "break"

    def handle_cut(event):
        do_cut()
        return "break"

    def handle_paste(event):
        do_paste()
        return "break"

    widget.bind("<Control-a>", handle_select_all)
    widget.bind("<Control-A>", handle_select_all)
    widget.bind("<Control-c>", handle_copy)
    widget.bind("<Control-C>", handle_copy)
    widget.bind("<Control-v>", handle_paste)
    widget.bind("<Control-V>", handle_paste)
    widget.bind("<Control-x>", handle_cut)
    widget.bind("<Control-X>", handle_cut)

    def on_keypress_any_lang(event):
        if (event.state & 0x0004):  # Control key is held down
            if event.keycode == 65:    # Key 'A'
                do_select_all()
                return "break"
            elif event.keycode == 67:  # Key 'C'
                do_copy()
                return "break"
            elif event.keycode == 86:  # Key 'V'
                do_paste()
                return "break"
            elif event.keycode == 88:  # Key 'X'
                do_cut()
                return "break"

    widget.bind("<KeyPress>", on_keypress_any_lang, add="+")

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
    return os.path.join(startup_dir, "FastworkBot.lnk")

def is_start_on_boot_enabled():
    shortcut_path = get_startup_shortcut_path()
    old_vbs = os.path.join(os.path.dirname(shortcut_path), "FastworkBot.vbs")
    return os.path.exists(shortcut_path) or os.path.exists(old_vbs)

def set_start_on_boot(enable: bool):
    shortcut_path = get_startup_shortcut_path()
    old_vbs = os.path.join(os.path.dirname(shortcut_path), "FastworkBot.vbs")
    if os.path.exists(old_vbs):
        try: os.remove(old_vbs)
        except Exception: pass

    if enable:
        current_dir = os.path.abspath(os.getcwd())
        target_vbs = os.path.join(current_dir, "start_bot.vbs")
        icon_path = os.path.join(current_dir, "icon.ico")

        ps_cmd = f'''$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut("{shortcut_path}")
$s.TargetPath = "wscript.exe"
$s.Arguments = '"{target_vbs}"'
$s.WorkingDirectory = "{current_dir}"
$s.Description = "Fastwork Auto-Offer Bot"
if (Test-Path "{icon_path}") {{
    $s.IconLocation = "{icon_path},0"
}}
$s.Save()'''
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True)
        except Exception as e:
            print("Error creating startup shortcut:", e)
    else:
        if os.path.exists(shortcut_path):
            try:
                os.remove(shortcut_path)
            except Exception as e:
                print("Error removing startup shortcut:", e)

def is_bot_running():
    """Checks if FastworkBot is already running in background system tray."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.2)
        s.connect(('127.0.0.1', 58923))
        s.close()
        return True
    except Exception:
        return False

def ensure_bot_running():
    """Ensures that the Fastwork Bot is running in system tray if not already running."""
    if not is_bot_running():
        try:
            current_dir = os.path.abspath(os.path.dirname(__file__))
            vbs_path = os.path.join(current_dir, "start_bot.vbs")
            if sys.platform == "win32" and os.path.exists(vbs_path):
                subprocess.Popen(["wscript.exe", vbs_path], cwd=current_dir)
            elif sys.platform == "win32":
                subprocess.Popen(["python", "fastwork_bot.py"], cwd=current_dir)
            else:
                subprocess.Popen([sys.executable, "fastwork_bot.py"], cwd=current_dir)
        except Exception as e:
            print(f"Error ensuring bot is running: {e}")

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

class TagInputWidget(tk.Frame):
    """Widget สำหรับจัดการคีย์เวิร์ดแบบ Tag Chips อัจฉริยะ (ใช้ tk.Text window_create เรนเดอร์ลื่นไหลและตัดบรรทัดอัตโนมัติ)"""
    def __init__(self, parent, on_tags_changed=None, bg="#F1F5F9",
                 chip_bg="#EFF6FF", chip_border="#BFDBFE", chip_fg="#1D4ED8", chip_icon="🏷️",
                 del_fg="#93C5FD", del_hover_fg="#EF4444",
                 placeholder_text="ยังไม่มีคีย์เวิร์ดเฉพาะ (พิมพ์ในช่องด้านบนแล้วกด Enter เพื่อเพิ่มแท็ก)",
                 hint_text="💡 พิมพ์คีย์เวิร์ดแล้วกด Enter หรือเครื่องหมายจุลภาค (,) เพื่อเพิ่มแท็ก • คลิก ✖ บนแท็กเพื่อลบ",
                 btn_text="➕ เพิ่มแท็ก", btn_style="Primary.TButton", box_height=3, **kwargs):
        super().__init__(parent, bg=bg, **kwargs)
        self.on_tags_changed = on_tags_changed
        self.tags = []
        self.chip_bg = chip_bg
        self.chip_border = chip_border
        self.chip_fg = chip_fg
        self.chip_icon = chip_icon
        self.del_fg = del_fg
        self.del_hover_fg = del_hover_fg
        self.placeholder_text = placeholder_text

        # 1. Entry Input Row
        entry_row = tk.Frame(self, bg=bg)
        entry_row.pack(fill="x", padx=2, pady=(0, 4))

        self.entry_var = tk.StringVar()
        self.entry = ttk.Entry(entry_row, textvariable=self.entry_var, font=("Segoe UI", 10))
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry.bind("<Return>", self._on_enter_pressed)
        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<BackSpace>", self._on_backspace)
        add_text_context_menu(self.entry, on_change=self._on_entry_paste_check)

        btn_add = ttk.Button(entry_row, text=btn_text, style=btn_style, command=self._add_from_entry)
        btn_add.pack(side="left", padx=(0, 4))

        btn_clear = ttk.Button(entry_row, text="🗑️ ล้างทั้งหมด", style="Secondary.TButton", command=self.clear_all_tags)
        btn_clear.pack(side="left")

        # 2. Tag Chips Box with Scrollbar (Expanded to fill card)
        box_frame = tk.Frame(self, bg="#CBD5E1", padx=1, pady=1)
        box_frame.pack(fill="both", expand=True, padx=2, pady=(0, 2))

        self.tag_text = tk.Text(box_frame, height=box_height, font=("Segoe UI", 10), wrap="word", relief="flat", borderwidth=0, bg="#FFFFFF", padx=6, pady=6, cursor="arrow")
        scroll = ttk.Scrollbar(box_frame, orient="vertical", command=self.tag_text.yview)
        self.tag_text.configure(yscrollcommand=scroll.set)

        self.tag_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tag_text.config(state="disabled")

        hint_lbl = tk.Label(self, text=hint_text, font=("Segoe UI", 8), bg=bg, fg="#64748B")
        hint_lbl.pack(anchor="w", padx=2, pady=(2, 0))

    def flush_entry(self):
        """Forces any typed uncommitted entry to be parsed and added to tags."""
        self._add_from_entry()

    def _on_enter_pressed(self, event):
        self._add_from_entry()
        return "break"

    def _on_backspace(self, event):
        if not self.entry_var.get() and self.tags:
            self.remove_tag(self.tags[-1])

    def _on_key_release(self, event):
        val = self.entry_var.get()
        if "," in val:
            parts = val.split(",")
            for p in parts[:-1]:
                self.add_tag(p.strip())
            self.entry_var.set(parts[-1].lstrip())

    def _on_entry_paste_check(self):
        val = self.entry_var.get()
        if "," in val or "\n" in val:
            self._add_from_entry()

    def _add_from_entry(self):
        val = self.entry_var.get().strip()
        if val:
            for item in val.replace("\n", ",").split(","):
                self.add_tag(item.strip())
            self.entry_var.set("")

    def add_tag(self, tag_text):
        tag_text = tag_text.strip()
        if not tag_text:
            return
        if tag_text not in self.tags:
            self.tags.append(tag_text)
            self._render_chips()
            if self.on_tags_changed:
                self.on_tags_changed(self.tags)

    def remove_tag(self, tag_text):
        if tag_text in self.tags:
            self.tags.remove(tag_text)
            self._render_chips()
            if self.on_tags_changed:
                self.on_tags_changed(self.tags)

    def clear_all_tags(self):
        if self.tags:
            self.tags = []
            self._render_chips()
            if self.on_tags_changed:
                self.on_tags_changed(self.tags)

    def set_tags(self, tag_list):
        self.tags = [t.strip() for t in tag_list if t.strip()]
        self._render_chips()

    def get_tags(self):
        return list(self.tags)

    def _render_chips(self):
        self.tag_text.config(state="normal")
        self.tag_text.delete("1.0", "end")

        if not self.tags:
            empty_lbl = tk.Label(self.tag_text, text=self.placeholder_text, font=("Segoe UI", 9, "italic"), bg="#FFFFFF", fg="#94A3B8")
            self.tag_text.window_create("end", window=empty_lbl)
        else:
            for tag in self.tags:
                chip = tk.Frame(self.tag_text, bg=self.chip_bg, highlightbackground=self.chip_border, highlightthickness=1, padx=6, pady=2)
                icon_prefix = f"{self.chip_icon} " if self.chip_icon else ""
                lbl = tk.Label(chip, text=f"{icon_prefix}{tag}", bg=self.chip_bg, fg=self.chip_fg, font=("Segoe UI", 9, "bold"))
                lbl.pack(side="left", padx=(0, 4))
                
                btn_del = tk.Label(chip, text="✖", bg=self.chip_bg, fg=self.del_fg, font=("Segoe UI", 8, "bold"), cursor="hand2")
                btn_del.pack(side="left")
                
                def make_del(t):
                    return lambda e: self.remove_tag(t)
                btn_del.bind("<Button-1>", make_del(tag))
                btn_del.bind("<Enter>", lambda e, b=btn_del: b.config(fg=self.del_hover_fg))
                btn_del.bind("<Leave>", lambda e, b=btn_del: b.config(fg=self.del_fg))

                self.tag_text.window_create("end", window=chip)
                self.tag_text.insert("end", "  ")

        self.tag_text.config(state="disabled")

class SettingsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fastwork Bot - ระบบตั้งค่าและจัดการบอท")
        self.geometry("860x780")
        self.minsize(760, 660)
        
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
        self.style.configure("Secondary.TButton", font=("Segoe UI", 9), background="#F1F5F9", foreground=self.text_dark, borderwidth=1, padding=[8, 4])
        self.style.map("Secondary.TButton", background=[("active", "#E2E8F0")])

        self.style.configure("Success.TLabel", font=("Segoe UI", 9, "bold"), foreground=self.success_color, background=self.card_bg)
        self.style.configure("Warning.TLabel", font=("Segoe UI", 9, "bold"), foreground=self.danger_color, background=self.card_bg)

    def build_ui(self):
        # Header Banner
        header_frame = tk.Frame(self, bg=self.primary_color, height=60)
        header_frame.pack(fill="x", side="top")

        title_frame = tk.Frame(header_frame, bg=self.primary_color)
        title_frame.pack(side="left", padx=(15, 10), pady=12)

        title_label = tk.Label(title_frame, text="⚡ Fastwork Auto-Offer Bot", font=("Segoe UI", 12, "bold"), bg=self.primary_color, fg="#FFFFFF")
        title_label.pack(side="left")

        subtitle_label = tk.Label(title_frame, text="• Control Panel", font=("Segoe UI", 9), bg=self.primary_color, fg="#E0E7FF")
        subtitle_label.pack(side="left", padx=5)

        # Version, Guide & Update button on right side of header
        local_ver = updater.get_local_version_info().get("version", "1.0.0")
        ver_frame = tk.Frame(header_frame, bg=self.primary_color)
        ver_frame.pack(side="right", padx=15, pady=12)

        self.ver_badge = tk.Label(ver_frame, text=f"v{local_ver}", font=("Segoe UI", 9, "bold"), bg="#1E40AF", fg="#FFFFFF", padx=6, pady=2)
        self.ver_badge.pack(side="left", padx=(0, 6))

        btn_guide = ttk.Button(ver_frame, text="📖 คู่มือการใช้", style="Secondary.TButton", command=self.open_guide)
        btn_guide.pack(side="left", padx=(0, 6))

        btn_update = ttk.Button(ver_frame, text="🔄 เช็คอัปเดต", style="Secondary.TButton", command=self.check_update_action)
        btn_update.pack(side="left")

        # Tab Notebook
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=12)

        # Tabs
        self.tab_token = ttk.Frame(self.notebook)
        self.tab_offer = ttk.Frame(self.notebook)
        self.tab_products = ttk.Frame(self.notebook)
        self.tab_portfolio = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_token, text="🔑 บัญชี & คุกกี้ Token")
        self.notebook.add(self.tab_offer, text="✍️ ใบเสนองาน")
        self.notebook.add(self.tab_products, text="📦 สินค้าของฉัน")
        self.notebook.add(self.tab_portfolio, text="📎 ไฟล์ผลงาน PDF")

        self.build_tab_token()
        self.build_tab_offer()
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
        add_text_context_menu(self.token_entry)

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
        add_text_context_menu(self.brief_url_entry)

        # Check interval & mode
        row_opts = tk.Frame(card2, bg=self.card_bg)
        row_opts.pack(fill="x", pady=4)

        tk.Label(row_opts, text="⏱️ ตรวจสอบงานทุกๆ (วินาที):", font=("Segoe UI", 9, "bold"), bg=self.card_bg).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.interval_entry = ttk.Entry(row_opts, width=10, font=("Segoe UI", 10))
        self.interval_entry.grid(row=0, column=1, sticky="w", padx=(0, 20))
        add_text_context_menu(self.interval_entry)

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
        add_text_context_menu(self.desc_text, on_change=self.update_char_count)

        self.lbl_char_count = tk.Label(card, text="จำนวนตัวอักษร: 0 ตัวอักษร", font=("Segoe UI", 9, "bold"), bg=self.card_bg, fg=self.danger_color)
        self.lbl_char_count.pack(anchor="w", pady=(2, 10))

        # Price and working days
        price_row = tk.Frame(card, bg=self.card_bg)
        price_row.pack(fill="x", pady=5)

        tk.Label(price_row, text="💰 ราคาเริ่มต้น (บาท):", font=("Segoe UI", 9, "bold"), bg=self.card_bg).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.budget_entry = ttk.Entry(price_row, width=12, font=("Segoe UI", 10))
        self.budget_entry.grid(row=0, column=1, sticky="w", padx=(0, 20))
        add_text_context_menu(self.budget_entry)

        tk.Label(price_row, text="⏳ ระยะเวลาทำงาน (วัน):", font=("Segoe UI", 9, "bold"), bg=self.card_bg).grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.days_entry = ttk.Entry(price_row, width=12, font=("Segoe UI", 10))
        self.days_entry.grid(row=0, column=3, sticky="w")
        add_text_context_menu(self.days_entry)

        tk.Label(card, text="* หากผู้ว่าจ้างระบุงบประมาณในโพสต์ บอทจะใช้งบประมาณของผู้ว่าจ้างเป็นหลัก แต่หากไม่ระบุจะใช้ราคาเริ่มต้นนี้", font=("Segoe UI", 8), bg=self.card_bg, fg=self.text_muted).pack(anchor="w", pady=(8, 0))

    def update_char_count(self, event=None):
        text = self.desc_text.get("1.0", "end-1c")
        count = len(text)
        if count >= 100:
            self.lbl_char_count.config(text=f"✅ จำนวนตัวอักษร: {count} ตัวอักษร (ผ่านเกณฑ์)", fg=self.success_color)
        else:
            self.lbl_char_count.config(text=f"⚠️ จำนวนตัวอักษร: {count}/100 ตัวอักษร (ต้องมีอย่างน้อย 100 ตัวอักษร)", fg=self.danger_color)

    # ---------------- TAB 3: PRODUCTS ----------------
    def build_tab_products(self):
        container = tk.Frame(self.tab_products, bg=self.bg_color)
        container.pack(fill="both", expand=True, padx=15, pady=10)

        card = tk.Frame(container, bg=self.card_bg, highlightbackground=self.border_color, highlightthickness=1, padx=14, pady=10)
        card.pack(fill="both", expand=True)

        top_row = tk.Frame(card, bg=self.card_bg)
        top_row.pack(fill="x", pady=(0, 4))

        tk.Label(top_row, text="📦 รายการสินค้า & จัดการคีย์เวิร์ดเฉพาะ Fastwork", font=("Segoe UI", 11, "bold"), bg=self.card_bg, fg=self.text_dark).pack(side="left")
        
        sync_prod_btn = ttk.Button(top_row, text="🔄 ดึงสินค้าล่าสุดจาก Fastwork", style="Primary.TButton", command=self.sync_account_and_products)
        sync_prod_btn.pack(side="right")

        tk.Label(card, text="คลิกเลือกสินค้าในตารางด้านบน แล้วพิมพ์คีย์เวิร์ดเฉพาะในช่องด้านล่าง (เมื่อเจองานที่ตรง บอทจะเลือกส่งสินค้านี้ทันที 100%)", font=("Segoe UI", 9), bg=self.card_bg, fg=self.text_muted).pack(anchor="w", pady=(0, 4))

        # Products Treeview Table
        tree_frame = tk.Frame(card)
        tree_frame.pack(fill="x", pady=(0, 4))

        cols = ("num", "title", "kw_count", "id")
        self.prod_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse", height=4)
        self.prod_tree.heading("num", text="#")
        self.prod_tree.heading("title", text="ชื่องานบริการ (Product Title)")
        self.prod_tree.heading("kw_count", text="คีย์เวิร์ดเฉพาะ")
        self.prod_tree.heading("id", text="Product ID")

        self.prod_tree.column("num", width=35, anchor="center")
        self.prod_tree.column("title", width=440, anchor="w")
        self.prod_tree.column("kw_count", width=120, anchor="center")
        self.prod_tree.column("id", width=170, anchor="center")

        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.prod_tree.yview)
        self.prod_tree.configure(yscrollcommand=scroll.set)

        self.prod_tree.pack(side="left", fill="x", expand=True)
        scroll.pack(side="right", fill="y")
        self.prod_tree.bind("<<TreeviewSelect>>", self.on_prod_tree_selected)

        # Editor Panel for Selected Product Keywords (Tag Chips Mode)
        self.prod_editor_card = tk.Frame(card, bg="#F1F5F9", highlightbackground=self.border_color, highlightthickness=1, padx=12, pady=6)
        self.prod_editor_card.pack(fill="both", expand=True, pady=(4, 4))

        editor_top = tk.Frame(self.prod_editor_card, bg="#F1F5F9")
        editor_top.pack(fill="x", pady=(0, 2))

        self.lbl_selected_prod_title = tk.Label(editor_top, text="🎯 คีย์เวิร์ดเฉพาะสำหรับ: (กรุณาคลิกเลือกสินค้าในตารางด้านบน)", font=("Segoe UI", 9, "bold"), bg="#F1F5F9", fg=self.primary_color)
        self.lbl_selected_prod_title.pack(side="left")

        self.lbl_kw_count = tk.Label(editor_top, text="จำนวน: 0 คำ", font=("Segoe UI", 9, "bold"), bg="#F1F5F9", fg=self.text_dark)
        self.lbl_kw_count.pack(side="right")

        # Tag Input Widget (Auto Wrap Tags + Enter to add)
        self.tag_widget = TagInputWidget(
            self.prod_editor_card,
            on_tags_changed=self.on_prod_tags_changed,
            bg="#F1F5F9",
            chip_bg="#EFF6FF",
            chip_border="#BFDBFE",
            chip_fg="#1D4ED8",
            chip_icon="🏷️",
            del_fg="#93C5FD",
            del_hover_fg="#EF4444",
            placeholder_text="ยังไม่มีคีย์เวิร์ดเฉพาะ (พิมพ์ในช่องด้านบนแล้วกด Enter เพื่อเพิ่มแท็ก)",
            hint_text="💡 พิมพ์คีย์เวิร์ดแล้วกด Enter หรือเครื่องหมายจุลภาค (,) เพื่อเพิ่มแท็ก • คลิก ✖ บนแท็กเพื่อลบ",
            btn_text="➕ เพิ่มแท็ก",
            btn_style="Primary.TButton",
            box_height=2
        )
        self.tag_widget.pack(fill="both", expand=True, pady=(2, 0))

        # Editor Panel for Exclude / Blacklist Keywords (คีย์เวิร์ดที่ห้ามโพสต์)
        self.exclude_editor_card = tk.Frame(card, bg="#FEF2F2", highlightbackground="#FECACA", highlightthickness=1, padx=12, pady=6)
        self.exclude_editor_card.pack(fill="both", expand=True, pady=(2, 0))

        exclude_top = tk.Frame(self.exclude_editor_card, bg="#FEF2F2")
        exclude_top.pack(fill="x", pady=(0, 2))

        lbl_exclude_title = tk.Label(exclude_top, text="🚫 คีย์เวิร์ดที่ห้ามโพสต์ (หากพบคำเหล่านี้ในชื่องานหรือรายละเอียด บอทจะไม่ยื่นข้อเสนอเด็ดขาด):", font=("Segoe UI", 9, "bold"), bg="#FEF2F2", fg="#B91C1C")
        lbl_exclude_title.pack(side="left")

        self.lbl_exclude_kw_count = tk.Label(exclude_top, text="จำนวน: 0 คำ", font=("Segoe UI", 9, "bold"), bg="#FEF2F2", fg="#B91C1C")
        self.lbl_exclude_kw_count.pack(side="right")

        # Tag Input Widget for Exclude Keywords
        self.exclude_tag_widget = TagInputWidget(
            self.exclude_editor_card,
            on_tags_changed=self.on_exclude_tags_changed,
            bg="#FEF2F2",
            chip_bg="#FEE2E2",
            chip_border="#FCA5A5",
            chip_fg="#B91C1C",
            chip_icon="🚫",
            del_fg="#F87171",
            del_hover_fg="#7F1D1D",
            placeholder_text="ยังไม่มีคีย์เวิร์ดที่ห้ามโพสต์ (พิมพ์คำที่ต้องการบล็อก เช่น การพนัน, 3D แล้วกด Enter เพื่อเพิ่มแท็ก)",
            hint_text="🚫 หากพบคำเหล่านี้ในโพสต์งาน บอทจะข้ามและไม่ยื่นข้อเสนอโดยเด็ดขาด • คลิก ✖ บนแท็กเพื่อลบ",
            btn_text="➕ เพิ่มคำห้าม",
            btn_style="Secondary.TButton",
            box_height=2
        )
        self.exclude_tag_widget.pack(fill="both", expand=True, pady=(2, 0))

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
        open_path(os.path.abspath(PORTFOLIO_DIR))

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

    def open_guide(self):
        guide_path = os.path.abspath(os.path.join("how_to_install", "index.html"))
        if os.path.exists(guide_path):
            open_path(guide_path)
        else:
            messagebox.showwarning("แจ้งเตือน", "ไม่พบไฟล์คู่มือ how_to_install/index.html")

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
        self.brief_url_entry.insert(0, cfg.get("default_brief_url", ""))

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

        # Products
        self.populate_products_tree(cfg.get("user_products", []))

        # Exclude Keywords (คีย์เวิร์ดที่ห้ามโพสต์)
        ex_kws = cfg.get("exclude_keywords", [])
        self.exclude_tag_widget.set_tags(ex_kws)
        self.lbl_exclude_kw_count.config(text=f"จำนวน: {len(ex_kws)} คำ")

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

    def on_exclude_tags_changed(self, tags):
        self.config["exclude_keywords"] = list(tags)
        self.lbl_exclude_kw_count.config(text=f"จำนวน: {len(tags)} คำ")

    def on_prod_tree_selected(self, event=None):
        selected = self.prod_tree.selection()
        if not selected:
            return
        idx = self.prod_tree.index(selected[0])
        prods = self.config.get("user_products", [])
        if 0 <= idx < len(prods):
            p = prods[idx]
            title = p.get("title", "ไม่ระบุ")
            short_title = (title[:55] + "...") if len(title) > 55 else title
            self.lbl_selected_prod_title.config(text=f"🎯 คีย์เวิร์ดเฉพาะสำหรับ: #{idx+1} {short_title}")
            kws = p.get("keywords", [])
            self.tag_widget.set_tags(kws)
            self.lbl_kw_count.config(text=f"จำนวน: {len(kws)} คำ")

    def on_prod_tags_changed(self, tags):
        selected = self.prod_tree.selection()
        if not selected:
            return
        idx = self.prod_tree.index(selected[0])
        prods = self.config.get("user_products", [])
        if 0 <= idx < len(prods):
            prods[idx]["keywords"] = list(tags)
            self.lbl_kw_count.config(text=f"จำนวน: {len(tags)} คำ")
            self.refresh_products_tree_display()

    def refresh_products_tree_display(self):
        prods = self.config.get("user_products", [])
        children = self.prod_tree.get_children()
        for idx, item_id in enumerate(children):
            if idx < len(prods):
                p = prods[idx]
                kw_cnt = len(p.get("keywords", []))
                kw_str = f"✅ {kw_cnt} คำ" if kw_cnt > 0 else "0 คำ (ยังไม่ตั้ง)"
                self.prod_tree.item(item_id, values=(idx + 1, p.get("title", ""), kw_str, p.get("product_id", "")))

    def populate_products_tree(self, products):
        self.prod_tree.delete(*self.prod_tree.get_children())
        for idx, p in enumerate(products, 1):
            kw_cnt = len(p.get("keywords", []))
            kw_str = f"✅ {kw_cnt} คำ" if kw_cnt > 0 else "0 คำ (ยังไม่ตั้ง)"
            self.prod_tree.insert("", "end", values=(idx, p.get("title", ""), kw_str, p.get("product_id", "")))

        first_items = self.prod_tree.get_children()
        if first_items:
            self.prod_tree.selection_set(first_items[0])
            self.on_prod_tree_selected()

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
                    # Preserve existing keywords per product by product_id
                    old_prod_kw_map = {p.get("product_id"): p.get("keywords", []) for p in self.config.get("user_products", [])}
                    for p in prods:
                        p_id = p.get("product_id")
                        if p_id in old_prod_kw_map:
                            p["keywords"] = old_prod_kw_map[p_id]
                        elif "keywords" not in p:
                            p["keywords"] = []

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

        # 3. Flush any active edits from Product tag widget and Exclude tag widget
        self.tag_widget.flush_entry()
        self.exclude_tag_widget.flush_entry()

        selected = self.prod_tree.selection()
        if selected:
            sel_idx = self.prod_tree.index(selected[0])
            prods = self.config.get("user_products", [])
            if 0 <= sel_idx < len(prods):
                prods[sel_idx]["keywords"] = self.tag_widget.get_tags()

        exclude_kws = self.exclude_tag_widget.get_tags()

        # 4. Startup Shortcut
        start_boot = self.var_start_boot.get()
        set_start_on_boot(start_boot)

        # Construct new config
        new_config = {
            "keywords": self.config.get("keywords", []),
            "exclude_keywords": exclude_kws,
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
            self.refresh_products_tree_display()
            self.status_label.config(text=f"✅ บันทึกการตั้งค่าเรียบร้อยแล้ว ({datetime.now().strftime('%H:%M:%S')})")
            messagebox.showinfo("บันทึกสำเร็จ", "บันทึกการตั้งค่าทั้งหมดเรียบร้อยแล้ว!\nบอทจะโหลดค่าใหม่ไปใช้งานอัตโนมัติ")

def main():
    app = SettingsApp()
    app.mainloop()

if __name__ == "__main__":
    main()
