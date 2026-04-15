"""직접 테스트: 로그인 → 글쓰기 클릭 → 페이지 구조 덤프"""
import asyncio
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

from modules.browser import new_session
from modules.naver_auth import naver_login

BOARD_URL = "https://cafe.naver.com/f-e/cafes/19025213/menus/40"
ID = "kyqwgdvdfuz"
PW = "plSubx0nbK"
DEBUG_DIR = os.path.join(os.path.dirname(__file__), "test_debug")
os.makedirs(DEBUG_DIR, exist_ok=True)


def log(msg):
    print(f"[{msg}]", flush=True)


async def dump_page_state(page, label):
    """페이지 구조 덤프 + 스크린샷"""
    log(f"===== {label} =====")
    log(f"URL: {page.url}")
    log(f"Frames ({len(page.frames)}):")
    for i, f in enumerate(page.frames):
        try:
            log(f"  [{i}] {f.url[:150]}")
        except Exception:
            pass

    # 각 프레임의 입력 요소
    for i, f in enumerate([page] + list(page.frames)):
        try:
            inputs = await f.evaluate("""
                () => Array.from(document.querySelectorAll('input, textarea, [contenteditable="true"]'))
                    .slice(0, 15)
                    .map(el => ({
                        tag: el.tagName,
                        type: el.type || '',
                        name: el.name || '',
                        placeholder: el.placeholder || el.getAttribute('placeholder') || '',
                        class: (el.className || '').toString().substring(0, 80),
                        id: el.id || ''
                    }))
            """)
            if inputs:
                log(f"  프레임[{i}] 입력요소 {len(inputs)}개:")
                for inp in inputs:
                    log(f"    → {inp}")
        except Exception as e:
            pass

    path = os.path.join(DEBUG_DIR, f"{label}.png")
    await page.screenshot(path=path, full_page=True)
    log(f"스크린샷: {path}")


async def main():
    async with new_session(headless=False) as (ctx, page):
        # alert 자동 처리
        page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))

        log("STEP 1: 로그인")
        ok = await naver_login(page, ID, PW, log_fn=log)
        if not ok:
            log("로그인 실패 — 이미 캡차 걸린듯. 중단")
            return

        log("STEP 2: 게시판 이동")
        await page.goto(BOARD_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        await dump_page_state(page, "1_board")

        log("STEP 3: 글쓰기 버튼 클릭")
        btn_selectors = [
            'a:has-text("글쓰기")',
            'button:has-text("글쓰기")',
            'a[href*="articles/write"]',
            'a[href*="ArticleWrite"]',
        ]
        clicked = False
        for t in [page] + list(page.frames):
            for sel in btn_selectors:
                try:
                    el = await t.query_selector(sel)
                    if el:
                        log(f"  버튼 발견: {sel} (프레임 URL: {t.url[:80] if hasattr(t, 'url') else 'main'})")
                        await el.click()
                        clicked = True
                        break
                except Exception:
                    pass
            if clicked:
                break

        if not clicked:
            log("글쓰기 버튼 못 찾음")
            return

        log("STEP 4: 클릭 후 3초 대기 (즉시)")
        await asyncio.sleep(3)
        await dump_page_state(page, "2_after_click_3s")

        log("STEP 5: 10초 더 대기 (에디터 로딩)")
        await asyncio.sleep(10)
        await dump_page_state(page, "3_after_click_13s")

        log("STEP 6: 20초 더 대기 (여유)")
        await asyncio.sleep(20)
        await dump_page_state(page, "4_after_click_33s")

        log("완료. 브라우저 창 열어두고 10초 대기")
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
