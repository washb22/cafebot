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
# 프록시 방식은 IP 변경 대기가 없어 전체 속도가 매우 빠르므로
# between_accounts 를 사람 수준으로 늘려 네이버 봇 탐지를 회피한다.
DEFAULT_DELAYS = {
    "after_login": (3, 6),          # 로그인 후 바로 글/댓글 안 쓰고 잠깐 대기
    "before_typing": (0.8, 2.0),    # 커서 놓고 타이핑 시작하기 전
    "typing_char_delay": (0.030, 0.080),  # 글자 입력 간격 (좀 더 사람처럼)
    "after_post_submit": (2, 4),
    "after_comment_submit": (1.5, 3),
    "after_browser_close": (0.5, 1),
    "airplane_toggle_wait": (3, 6),  # 사용 안함 (비행기모드 모드용)
    "between_accounts": (18, 35),    # 계정 전환 간격 (핵심) - 사람 속도로
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
