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
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# IP 변경 방식: "proxy" (HTTP 프록시) 또는 "adb" (안드로이드 테더링 비행기모드)
DEFAULT_IP_MODE = "proxy"
ADB_PATH = os.path.join(BASE_DIR, "adb", "adb.exe")
if not os.path.exists(ADB_PATH):
    ADB_PATH = "adb"

# Delay ranges (seconds) - min, max
# 프록시 방식 속도 튜닝: 사람 속도 유지하되 불필요한 여유 제거
DEFAULT_DELAYS = {
    "after_login": (2, 4),
    "before_typing": (0.5, 1.2),
    "typing_char_delay": (0.020, 0.055),
    "after_post_submit": (1.5, 3),
    "after_comment_submit": (1.2, 2.5),
    "after_browser_close": (0.5, 1),
    "airplane_toggle_wait": (3, 6),  # 사용 안함
    "between_accounts": (12, 25),    # 계정 전환 간격 (핵심)
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
