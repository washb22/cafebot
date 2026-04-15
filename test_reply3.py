"""단순화된 대댓글 테스트 — 공유 댓글창 사용"""
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
with open(os.path.join(DEBUG_DIR, "post_url.txt"), 'r', encoding='utf-8') as f:
    POST_URL = f.read().strip()
ID = "kyqwgdvdfuz"; PW = "plSubx0nbK"
REPLY_TEXT = "대댓글 테스트2"


def log(msg):
    print(f"[{msg}]", flush=True)


async def main():
    async with new_session(headless=False) as (ctx, page):
        page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))
        await naver_login(page, ID, PW, log_fn=log)
        await page.goto(POST_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        for _ in range(3):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            for f in page.frames:
                try:
                    await f.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass
            await asyncio.sleep(1.5)

        # 첫 댓글의 답글쓰기 클릭 (index 0 = 첫 번째 댓글)
        target_index = 0
        log(f"댓글 #{target_index+1}의 답글쓰기 클릭")
        for t in [page] + list(page.frames):
            try:
                items = await t.query_selector_all('li.CommentItem')
                if items and len(items) > target_index:
                    btn = await items[target_index].query_selector('a.comment_info_button')
                    if btn:
                        txt = (await btn.text_content() or '').strip()
                        if '답글' in txt:
                            await btn.click()
                            log(f"  클릭 완료: {txt}")
                            break
            except Exception:
                pass
        await asyncio.sleep(2)

        # 공유 댓글창 찾기 (.comment_inbox_text)
        log("댓글창 탐색 (공유)")
        tb = None
        tb_frame = None
        for attempt in range(8):
            for t in [page] + list(page.frames):
                try:
                    el = await t.query_selector('textarea.comment_inbox_text')
                    if el:
                        box = await el.bounding_box()
                        if box and box['width'] > 100:
                            tb = el
                            tb_frame = t
                            log(f"  발견 size={box['width']:.0f}x{box['height']:.0f} at ({box['x']:.0f},{box['y']:.0f})")
                            break
                except Exception:
                    pass
            if tb:
                break
            await asyncio.sleep(1)

        if not tb:
            log("textarea 못 찾음")
            return

        await tb.scroll_into_view_if_needed()
        await tb.click()
        await asyncio.sleep(0.5)
        await page.keyboard.type(REPLY_TEXT, delay=random.randint(30, 80))
        await asyncio.sleep(1)

        # 등록 (btn_register)
        log("등록 탐색")
        pub = None
        for t in [page] + list(page.frames):
            try:
                els = await t.query_selector_all('a.btn_register, button.btn_register, .btn_register')
                for el in els:
                    box = await el.bounding_box()
                    if box and box['width'] > 10:
                        pub = el
                        log(f"  등록 at ({box['x']:.0f},{box['y']:.0f})")
                        break
                if pub:
                    break
            except Exception:
                pass

        if pub:
            await pub.click()
            await asyncio.sleep(5)
            await page.screenshot(path=os.path.join(DEBUG_DIR, "reply_posted_v2.png"), full_page=True)
            log("대댓글 완료")
        else:
            log("등록 못 찾음")


if __name__ == "__main__":
    asyncio.run(main())
