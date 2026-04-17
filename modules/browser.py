"""Playwright incognito browser session manager."""
import os
import sys
import random
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright

if getattr(sys, 'frozen', False) and 'PLAYWRIGHT_BROWSERS_PATH' not in os.environ:
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = os.path.join(
        os.path.dirname(sys.executable), 'browsers'
    )

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {"width": 1280, "height": 800},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
]


@asynccontextmanager
async def new_session(pw=None, headless=False):
    """Create a fresh incognito browser session. Yields (context, page).
    Guarantees full cleanup on exit (no cookie/cache leak)."""
    own_pw = False
    if pw is None:
        pw = await async_playwright().start()
        own_pw = True

    browser = await pw.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--disable-infobars",
        ]
    )

    viewport = random.choice(VIEWPORTS)
    ua = random.choice(USER_AGENTS)

    context = await browser.new_context(
        viewport=viewport,
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        user_agent=ua,
        ignore_https_errors=True,
        java_script_enabled=True,
    )

    # Remove automation indicators
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    """)

    page = await context.new_page()

    try:
        yield context, page
    finally:
        await context.close()
        await browser.close()
        if own_pw:
            await pw.stop()
