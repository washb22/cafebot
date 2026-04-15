"""실제 댓글 작성 테스트"""
import asyncio
import os
import sys
import io
import random
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

from modules.browser import new_session
from modules.naver_auth import naver_login

DEBUG_DIR = os.path.join(os.path.dirname(__file__), "test_debug")
URL_FILE = os.path.join(DEBUG_DIR, "post_url.txt")
ID = "kyqwgdvdfuz"
PW = "plSubx0nbK"
COMMENT_TEXT = "테스트 댓글입니다"


def log(msg):
    print(f"[{msg}]", flush=True)


async def main():
    with open(URL_FILE, 'r', encoding='utf-8') as f:
        post_url = f.read().strip()
    log(f"POST URL: {post_url}")

    async with new_session(headless=False) as (ctx, page):
        page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))

        log("로그인")
        ok = await naver_login(page, ID, PW, log_fn=log)
        if not ok:
            return

        log("게시글 이동")
        await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        # 댓글 영역까지 스크롤
        for _ in range(3):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            for f in page.frames:
                try:
                    await f.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass
            await asyncio.sleep(1.5)

        log("댓글 textarea 탐색")
        comment_box = None
        comment_frame = None
        for attempt in range(10):
            for t in [page] + list(page.frames):
                try:
                    el = await t.query_selector('textarea[placeholder*="댓글"]')
                    if el:
                        box = await el.bounding_box()
                        if box and box['width'] > 100:
                            comment_box = el
                            comment_frame = t
                            log(f"  발견: size={box['width']:.0f}x{box['height']:.0f}")
                            break
                except Exception:
                    pass
            if comment_box:
                break
            await asyncio.sleep(1)

        if not comment_box:
            log("댓글창 못 찾음")
            return

        log("댓글 클릭 + 입력")
        await comment_box.scroll_into_view_if_needed()
        await comment_box.click()
        await asyncio.sleep(1)
        await page.keyboard.type(COMMENT_TEXT, delay=random.randint(30, 80))
        await asyncio.sleep(1)

        log("등록 버튼 탐색 (댓글)")
        # 댓글 등록 버튼: 일반적으로 .btn_register 또는 text='등록'
        pub_el = None
        for t in [comment_frame] + [page] + list(page.frames):
            if not t:
                continue
            try:
                # 1) .btn_register 클래스
                el = await t.query_selector('.btn_register, a.btn_register, button.btn_register')
                if el:
                    box = await el.bounding_box()
                    if box and box['width'] > 10:
                        pub_el = el
                        log(f"  btn_register 발견")
                        break
                # 2) text 정확 '등록'
                els = await t.query_selector_all('a, button')
                for b in els:
                    txt = (await b.text_content() or '').strip()
                    if txt == '등록':
                        box = await b.bounding_box()
                        if box and box['width'] > 10 and box['y'] > 400:  # 댓글 영역 (보통 아래쪽)
                            pub_el = b
                            log(f"  등록 텍스트 버튼 발견 at ({box['x']:.0f},{box['y']:.0f})")
                            break
                if pub_el:
                    break
            except Exception:
                pass

        if not pub_el:
            log("등록 버튼 못 찾음 — 덤프")
            for i, t in enumerate([page] + list(page.frames)):
                try:
                    data = await t.evaluate("""
                        () => Array.from(document.querySelectorAll('a, button')).filter(el => {
                            const txt = (el.textContent||'').trim();
                            return txt === '등록' || (el.className||'').toString().includes('register');
                        }).map(el => {
                            const r = el.getBoundingClientRect();
                            return {tag: el.tagName, text: (el.textContent||'').trim(),
                                    class: (el.className||'').toString().substring(0,80),
                                    w: r.width, h: r.height, x: r.x, y: r.y};
                        })
                    """)
                    if data:
                        log(f"  [{i}]:")
                        for d in data:
                            log(f"    {d}")
                except Exception:
                    pass
            return

        log("등록 클릭")
        await pub_el.click()
        await asyncio.sleep(5)
        await page.screenshot(path=os.path.join(DEBUG_DIR, "comment_posted.png"), full_page=True)
        log("댓글 작성 완료 (스크린샷 저장)")


if __name__ == "__main__":
    asyncio.run(main())
