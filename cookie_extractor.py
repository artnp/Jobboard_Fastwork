import os
import sys
import time
import json
import base64
import sqlite3
import shutil
import ctypes
from ctypes import wintypes
import psutil

# Windows DPAPI structures for CryptUnprotectData (Windows only)
if sys.platform == "win32":
    try:
        from ctypes import wintypes
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ('cbData', wintypes.DWORD),
                ('pbData', ctypes.POINTER(ctypes.c_byte))
            ]
    except Exception:
        pass

def decrypt_dpapi(encrypted_bytes):
    if sys.platform != "win32":
        return None
    try:
        blob_in = DATA_BLOB(len(encrypted_bytes), ctypes.cast(ctypes.create_string_buffer(encrypted_bytes), ctypes.POINTER(ctypes.c_byte)))
        blob_out = DATA_BLOB()
        if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
            buffer = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return buffer
    except Exception:
        pass
    return None

def decrypt_aes_gcm(key, iv, ciphertext, tag):
    # Try pycryptodome first if available
    try:
        from Crypto.Cipher import AES
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        return cipher.decrypt_and_verify(ciphertext, tag)
    except Exception:
        pass

    # Try cryptography library if available
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(iv, ciphertext + tag, None)
    except Exception:
        pass

    # Fallback to pure Windows BCrypt via ctypes
    try:
        BCRYPT_AES_ALGORITHM = ctypes.c_wchar_p("AES")
        BCRYPT_CHAINING_MODE = ctypes.c_wchar_p("ChainingMode")
        BCRYPT_CHAIN_MODE_GCM = ctypes.c_wchar_p("ChainingModeGCM")
        
        hAlg = wintypes.HANDLE()
        status = ctypes.windll.bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(hAlg), BCRYPT_AES_ALGORITHM, None, 0)
        if status != 0:
            return None
        
        status = ctypes.windll.bcrypt.BCryptSetProperty(
            hAlg, BCRYPT_CHAINING_MODE, 
            ctypes.cast(BCRYPT_CHAIN_MODE_GCM, ctypes.c_void_p), 
            len("ChainingModeGCM") * 2 + 2, 0
        )
        
        hKey = wintypes.HANDLE()
        status = ctypes.windll.bcrypt.BCryptGenerateSymmetricKey(hAlg, ctypes.byref(hKey), None, 0, key, len(key), 0)
        if status != 0:
            ctypes.windll.bcrypt.BCryptCloseAlgorithmProvider(hAlg, 0)
            return None

        class BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.ULONG),
                ("dwInfoVersion", wintypes.ULONG),
                ("pbNonce", ctypes.c_void_p),
                ("cbNonce", wintypes.ULONG),
                ("pbAuthData", ctypes.c_void_p),
                ("cbAuthData", wintypes.ULONG),
                ("pbTag", ctypes.c_void_p),
                ("cbTag", wintypes.ULONG),
                ("pbMacContext", ctypes.c_void_p),
                ("cbMacContext", wintypes.ULONG),
                ("cbAAD", wintypes.ULONG),
                ("cbData", ctypes.c_ulonglong),
                ("dwFlags", wintypes.ULONG)
            ]
        
        auth_info = BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO()
        auth_info.cbSize = ctypes.sizeof(BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO)
        auth_info.dwInfoVersion = 1
        auth_info.pbNonce = ctypes.cast(ctypes.create_string_buffer(iv), ctypes.c_void_p)
        auth_info.cbNonce = len(iv)
        auth_info.pbTag = ctypes.cast(ctypes.create_string_buffer(tag), ctypes.c_void_p)
        auth_info.cbTag = len(tag)
        
        cbPlainText = wintypes.ULONG()
        status = ctypes.windll.bcrypt.BCryptDecrypt(
            hKey, ciphertext, len(ciphertext),
            ctypes.byref(auth_info), None, 0,
            None, 0, ctypes.byref(cbPlainText), 0
        )
        
        plainText = ctypes.create_string_buffer(cbPlainText.value)
        status = ctypes.windll.bcrypt.BCryptDecrypt(
            hKey, ciphertext, len(ciphertext),
            ctypes.byref(auth_info), None, 0,
            plainText, cbPlainText.value, ctypes.byref(cbPlainText), 0
        )
        
        ctypes.windll.bcrypt.BCryptDestroyKey(hKey)
        ctypes.windll.bcrypt.BCryptCloseAlgorithmProvider(hAlg, 0)
        
        if status == 0:
            return plainText.raw[:cbPlainText.value]
    except Exception:
        pass
        
    return None

def get_browser_master_key(local_state_path):
    if not os.path.exists(local_state_path):
        return None
    try:
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)
        encrypted_key_b64 = local_state.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key_b64:
            return None
        encrypted_key = base64.b64decode(encrypted_key_b64)
        if encrypted_key.startswith(b'DPAPI'):
            encrypted_key = encrypted_key[5:]
        return decrypt_dpapi(encrypted_key)
    except Exception:
        return None

def extract_token_from_browser_db(browser_name, user_data_path):
    local_state = os.path.join(user_data_path, "Local State")
    master_key = get_browser_master_key(local_state)
    if not master_key:
        return None, "master_key_not_found"

    profiles = ["Default"]
    try:
        for item in os.listdir(user_data_path):
            if item.startswith("Profile "):
                profiles.append(item)
    except Exception:
        pass

    locked_error = False

    for prof in profiles:
        cookie_paths = [
            os.path.join(user_data_path, prof, "Network", "Cookies"),
            os.path.join(user_data_path, prof, "Cookies")
        ]
        for cpath in cookie_paths:
            if not os.path.exists(cpath):
                continue
            
            temp_db = os.path.join(os.environ.get("TEMP", "."), f"cookies_{browser_name}_{prof}_{int(time.time()*1000)}.db")
            try:
                shutil.copy2(cpath, temp_db)
            except Exception:
                locked_error = True
                continue

            try:
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                # STRICT SECURITY: Query ONLY fastwork.co domain cookies and ONLY authentication token names
                cursor.execute("""
                    SELECT name, value, encrypted_value, host_key 
                    FROM cookies 
                    WHERE (host_key = '.fastwork.co' OR host_key = 'fastwork.co' OR host_key = '.jobboard.fastwork.co' OR host_key = 'jobboard.fastwork.co' OR host_key LIKE '%.fastwork.co')
                      AND name IN ('accessToken', 'token', 'jwt', 'access_token')
                """)
                rows = cursor.fetchall()
                for name, value, encrypted_value, host_key in rows:
                    # Double-check domain strictly ends with fastwork.co
                    clean_host = host_key.lstrip('.').lower()
                    if clean_host != "fastwork.co" and not clean_host.endswith(".fastwork.co"):
                        continue

                    cookie_val = value
                    if not cookie_val and encrypted_value:
                        if encrypted_value.startswith(b'v10') or encrypted_value.startswith(b'v11'):
                            iv = encrypted_value[3:15]
                            payload = encrypted_value[15:]
                            ciphertext = payload[:-16]
                            tag = payload[-16:]
                            decrypted = decrypt_aes_gcm(master_key, iv, ciphertext, tag)
                            if decrypted:
                                cookie_val = decrypted.decode('utf-8', errors='ignore')

                    if cookie_val and cookie_val.startswith("eyJ"):
                        conn.close()
                        try:
                            os.remove(temp_db)
                        except Exception:
                            pass
                        return cookie_val, None
                conn.close()
            except Exception:
                pass
            finally:
                if os.path.exists(temp_db):
                    try:
                        os.remove(temp_db)
                    except Exception:
                        pass

    if locked_error:
        return None, "file_locked"
    return None, "not_found"

def close_browser_processes(process_names):
    """Gracefully closes specified browser processes."""
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() in [p.lower() for p in process_names]:
                proc.kill()
        except Exception:
            pass
    time.sleep(0.8)

def get_fastwork_token_from_browsers(auto_close_browser=False):
    """Scans installed browsers (Chrome, Edge, Brave, Opera, Opera GX) for Fastwork accessToken cookie."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    app_data = os.environ.get("APPDATA", "")

    browser_configs = [
        {"name": "Google Chrome", "exe": "chrome.exe", "path": os.path.join(local_app_data, r"Google\Chrome\User Data")},
        {"name": "Microsoft Edge", "exe": "msedge.exe", "path": os.path.join(local_app_data, r"Microsoft\Edge\User Data")},
        {"name": "Brave", "exe": "brave.exe", "path": os.path.join(local_app_data, r"BraveSoftware\Brave-Browser\User Data")},
        {"name": "Opera", "exe": "opera.exe", "path": os.path.join(app_data, r"Opera Software\Opera Stable")},
        {"name": "Opera GX", "exe": "opera.exe", "path": os.path.join(app_data, r"Opera Software\Opera GX Stable")}
    ]

    if auto_close_browser:
        close_browser_processes(["chrome.exe", "msedge.exe", "brave.exe", "opera.exe"])

    has_locked = []
    
    for b in browser_configs:
        if os.path.exists(b["path"]):
            token, err = extract_token_from_browser_db(b["name"], b["path"])
            if token:
                return True, token, f"ดึง Token สำเร็จจาก {b['name']}!"
            if err == "file_locked":
                has_locked.append(b["name"])

    if has_locked:
        names_str = ", ".join(has_locked)
        return False, None, f"LOCKED:{names_str}"

    return False, None, "ไม่พบคุกกี้ Fastwork ในเบราว์เซอร์ กรุณาตรวจสอบว่าได้เข้าสู่ระบบ fastwork.co ไว้แล้ว"

def launch_interactive_fastwork_login():
    """Opens a visible browser window for the user to log in and intercepts the accessToken."""
    if sys.platform == "win32":
        session_dir = os.path.join(os.environ.get("LOCALAPPDATA", "."), "FastworkBotSession")
    elif sys.platform == "darwin":
        session_dir = os.path.expanduser("~/Library/Application Support/FastworkBotSession")
    else:
        session_dir = os.path.expanduser("~/.fastwork_bot_session")
    
    # Method 1: Playwright with persistent context
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=session_dir,
                    channel="chrome",
                    headless=False,
                    viewport={"width": 1024, "height": 720}
                )
            except Exception:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=session_dir,
                    headless=False,
                    viewport={"width": 1024, "height": 720}
                )

            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://fastwork.co/")

            start_time = time.time()
            token = None
            while time.time() - start_time < 180:
                try:
                    cookies = context.cookies(["https://fastwork.co", "https://jobboard.fastwork.co"])
                    for c in cookies:
                        domain = c.get("domain", "").lstrip('.').lower()
                        if (domain == "fastwork.co" or domain.endswith(".fastwork.co")) and c.get("name") in ["accessToken", "token"] and c.get("value", "").startswith("eyJ"):
                            token = c.get("value")
                            break
                    if token:
                        break
                except Exception:
                    break
                time.sleep(1)

            try:
                context.close()
            except Exception:
                pass

            if token:
                return True, token, "เข้าสู่ระบบและดึง Token สำเร็จ!"
            return False, None, "หมดเวลาหรือผู้ใช้ปิดหน้าต่างก่อนสำเร็จ"
    except ImportError:
        pass

    # Method 2: Selenium
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        opts = Options()
        opts.add_argument(f"user-data-dir={session_dir}")
        opts.add_argument("--start-maximized")
        driver = webdriver.Chrome(options=opts)
        driver.get("https://fastwork.co/")

        start_time = time.time()
        token = None
        while time.time() - start_time < 180:
            try:
                cookies = driver.get_cookies()
                for c in cookies:
                    domain = c.get("domain", "").lstrip('.').lower()
                    if (domain == "fastwork.co" or domain.endswith(".fastwork.co")) and c.get("name") in ["accessToken", "token"] and c.get("value", "").startswith("eyJ"):
                        token = c.get("value")
                        break
                if token:
                    break
            except Exception:
                break
            time.sleep(1)

        try:
            driver.quit()
        except Exception:
            pass

        if token:
            return True, token, "เข้าสู่ระบบและดึง Token สำเร็จ!"
        return False, None, "หมดเวลาหรือผู้ใช้ปิดหน้าต่างก่อนสำเร็จ"
    except Exception as e:
        return False, None, f"เกิดข้อผิดพลาดในการเปิดเบราว์เซอร์: {e}"

def get_bookmarklet_js():
    """Returns a 1-click JavaScript bookmarklet snippet for extracting Fastwork token."""
    return "javascript:(function(){if(!window.location.hostname.endsWith('fastwork.co')){alert('⚠️ กรุณาเปิดใช้งานโค้ดนี้บนเว็บไซต์ Fastwork.co เท่านั้น');return;}let m=document.cookie.match(/accessToken=([^;]+)/);if(m){navigator.clipboard.writeText(m[1]);alert('✅ คัดลอก Fastwork Access Token เรียบร้อยแล้ว!\\nนำไปวางในโปรแกรมได้ทันที')}else{alert('❌ ไม่พบคุกกี้ accessToken\\nกรุณาเข้าสู่ระบบ fastwork.co ก่อน')}})();"
