"""CafeBot Configuration"""
import os

FLASK_PORT = 5002
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")

# Delay ranges (seconds) - min, max
DEFAULT_DELAYS = {
    "after_login": (4, 7),
    "before_typing": (1, 3),
    "typing_char_delay": (0.05, 0.15),
    "after_post_submit": (3, 6),
    "after_comment_submit": (3, 5),
    "after_browser_close": (2, 4),
    "airplane_toggle_wait": (10, 18),
    "between_accounts": (8, 15),
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
