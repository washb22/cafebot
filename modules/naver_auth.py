"""Naver login/logout logic with anti-detection bypass."""
import asyncio
import random
import pyperclip
from config import SELECTORS


async def human_delay(min_s=0.5, max_s=1.5):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def clipboard_paste(page, selector, text):
    """Paste text using clipboard to bypass Naver's input detection."""
    await page.click(selector)
    await human_delay(0.3, 0.7)

    # Clear existing text
    await page.keyboard.press("Control+a")
    await human_delay(0.1, 0.3)

    # Copy to clipboard and paste
    pyperclip.copy(text)
    await page.keyboard.press("Control+v")
    await human_delay(0.3, 0.6)


async def naver_login(page, account_id, account_pw, log_fn=None):
    """Login to Naver with given credentials.
    Returns True on success, False on failure."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        log(f"네이버 로그인 시도: {account_id[:3]}***")

        # Navigate to login page
        await page.goto(SELECTORS["login_url"], wait_until="networkidle", timeout=30000)
        await human_delay(1, 2)

        # Input ID via clipboard paste
        await clipboard_paste(page, SELECTORS["login_id"], account_id)
        await human_delay(0.5, 1.0)

        # Input PW via clipboard paste
        await clipboard_paste(page, SELECTORS["login_pw"], account_pw)
        await human_delay(0.5, 1.0)

        # Click login button
        await page.click(SELECTORS["login_btn"])
        await human_delay(2, 4)

        # Wait for navigation
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Check for CAPTCHA
        captcha = await page.query_selector(SELECTORS["login_captcha"])
        if captcha:
            log("⚠ 캡차 감지! 수동 해결 필요 - 30초 대기")
            await asyncio.sleep(30)

        # Check login success - should redirect away from login page
        current_url = page.url
        if "nidlogin" in current_url:
            # Still on login page - check for error
            error_el = await page.query_selector(".error_message, #err_common")
            if error_el:
                error_text = await error_el.text_content()
                log(f"로그인 실패: {error_text}")
            else:
                log("⚠ 로그인 페이지에 머물러 있음 - 2차 인증 확인 필요 (20초 대기)")
                await asyncio.sleep(20)

            if "nidlogin" in page.url:
                log("로그인 실패")
                return False

        log(f"로그인 성공: {account_id[:3]}***")
        return True

    except Exception as e:
        log(f"로그인 오류: {str(e)}")
        return False


async def naver_logout(page, log_fn=None):
    """Logout from Naver."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        await page.goto("https://nid.naver.com/nidlogin.logout", timeout=15000)
        await human_delay(1, 2)
        log("로그아웃 완료")
    except Exception as e:
        log(f"로그아웃 오류 (무시): {str(e)}")
