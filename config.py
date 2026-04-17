"""CafeBot Configuration"""
import os
import sys

# frozen (PyInstaller) 모드에서는 exe 위치 기준, 개발 모드에서는 소스 위치 기준
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FLASK_PORT = 5002
DATA_DIR = os.path.join(BASE_DIR, "data")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")
ADB_PATH = os.path.join(BASE_DIR, "adb", "adb.exe")
if not os.path.exists(ADB_PATH):
    ADB_PATH = "adb"

# Delay ranges (seconds) - min, max
DEFAULT_DELAYS = {
    "after_login": (1, 2),
    "before_typing": (0.3, 1.0),
    "typing_char_delay": (0.010, 0.030),
    "after_post_submit": (1.5, 3),
    "after_comment_submit": (0.8, 1.8),
    "after_browser_close": (0.5, 1),
    "airplane_toggle_wait": (3, 6),
    "between_accounts": (2, 4),
}

# Naver selectors
SELECTORS = {
    # Login
    "login_url": "https://nid.naver.com/nidlogin.login",
    "login_id": "#id",
    "login_pw": "#pw",
    "login_btn": "#log\\.login",
    "login_captcha": "#captcha",

    # Cafe post
    "cafe_main_frame": "iframe#cafe_main",
    "editor_iframe": "iframe[src*='editor']",
    "title_input": ".se-title-input",
    "body_area": ".se-text-paragraph",
    "publish_btn": "button:has-text('등록'), button:has-text('발행')",
    "board_select": ".select_component",

    # Edit
    "edit_btn": "a:has-text('수정')",

    # Comments
    "comment_textarea": "textarea.comment_inbox",
    "comment_submit": "a.btn_register, button.btn_register",
    "reply_btn": "a.comment_info_button:has-text('답글')",
    "reply_textarea": "textarea.comment_inbox",
}

PLAYWRIGHT_HEADLESS = False
