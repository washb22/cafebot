"""댓글 DOM 구조 상세 덤프"""
import asyncio
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

from modules.browser import new_session
from modules.naver_auth import naver_login

DEBUG_DIR = os.path.join(os.path.dirname(__file__), "test_debug")
with open(os.path.join(DEBUG_DIR, "post_url.txt"), 'r', encoding='utf-8') as f:
    POST_URL = f.read().strip()
ID = "kyqwgdvdfuz"; PW = "plSubx0nbK"

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

        # 댓글 컨테이너 찾기
        for i, t in enumerate([page] + list(page.frames)):
            try:
                data = await t.evaluate("""
                    () => {
                        const out = [];
                        document.querySelectorAll('li[class*="comment"], li[class*="Comment"], div.comment_item, div[class*="CommentItem"]').forEach(el => {
                            const text = (el.textContent||'').trim().substring(0, 60);
                            const btns = Array.from(el.querySelectorAll('a, button')).map(b => ({
                                tag: b.tagName, text: (b.textContent||'').trim().substring(0,20),
                                class: (b.className||'').toString().substring(0,60)
                            }));
                            out.push({
                                tag: el.tagName,
                                class: (el.className||'').toString().substring(0,80),
                                text: text,
                                button_count: btns.length,
                                buttons: btns.slice(0, 10)
                            });
                        });
                        return out;
                    }
                """)
                if data:
                    log(f"=== 프레임 [{i}] ===")
                    for d in data[:5]:
                        log(f"  {d['tag']} class={d['class']}")
                        log(f"    text: {d['text'][:40]}")
                        for b in d['buttons'][:6]:
                            log(f"      -> {b}")
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
