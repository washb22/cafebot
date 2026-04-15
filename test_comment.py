"""댓글/대댓글 테스트 — 방금 작성한 글에 댓글 달기"""
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

# test_write3.py 가 저장한 URL 사용, fallback으로 표준 형식
DEBUG_DIR = os.path.join(os.path.dirname(__file__), "test_debug")
URL_FILE = os.path.join(DEBUG_DIR, "post_url.txt")
ID = "kyqwgdvdfuz"
PW = "plSubx0nbK"


def log(msg):
    print(f"[{msg}]", flush=True)


async def dump_comments(page, label):
    log(f"===== {label} =====")
    log(f"URL: {page.url}")
    log(f"Frames ({len(page.frames)}):")
    for i, f in enumerate(page.frames):
        try:
            log(f"  [{i}] {f.url[:150]}")
        except Exception:
            pass
    # 댓글 관련 요소 탐색
    for i, f in enumerate([page] + list(page.frames)):
        try:
            data = await f.evaluate("""
                () => {
                    const results = [];
                    document.querySelectorAll('textarea, [contenteditable="true"]').forEach(el => {
                        const p = el.placeholder || el.getAttribute('placeholder') || '';
                        const r = el.getBoundingClientRect();
                        if (p.includes('댓글') || p.includes('의견') || el.closest('[class*=comment]') || el.closest('[class*=Comment]')) {
                            results.push({
                                tag: el.tagName, placeholder: p,
                                class: (el.className||'').toString().substring(0,80),
                                w: r.width, h: r.height, x: r.x, y: r.y
                            });
                        }
                    });
                    return results;
                }
            """)
            if data:
                log(f"  [{i}] 댓글 관련:")
                for d in data:
                    log(f"    {d}")
        except Exception:
            pass
    path = os.path.join(DEBUG_DIR, f"{label}.png")
    await page.screenshot(path=path, full_page=True)
    log(f"  스크린샷: {path}")


async def main():
    with open(URL_FILE, 'r', encoding='utf-8') as f:
        post_url = f.read().strip()
    log(f"사용할 POST URL: {post_url}")

    async with new_session(headless=False) as (ctx, page):
        page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))

        log("STEP 1: 로그인")
        ok = await naver_login(page, ID, PW, log_fn=log)
        if not ok:
            return

        log("STEP 2: 게시글 이동")
        try:
            await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            log(f"이동 타임아웃: {e}")
        await asyncio.sleep(5)

        # 끝까지 스크롤 (lazy load)
        for _ in range(3):
            try:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                for f in page.frames:
                    try:
                        await f.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    except Exception:
                        pass
            except Exception:
                pass
            await asyncio.sleep(1.5)

        await dump_comments(page, "post_view")

        # 실제 게시글 URL을 표준 형식으로 재구성 시도
        # URL에서 articleid 추출
        import re
        m = re.search(r'articleid[=%]+(\d+)', post_url)
        m2 = re.search(r'clubid[=%]+(\d+)', post_url)
        if m and m2:
            std_url = f"https://cafe.naver.com/ca-fe/cafes/{m2.group(1)}/articles/{m.group(1)}"
            log(f"STEP 3: 표준 URL 시도 {std_url}")
            try:
                await page.goto(std_url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
            await asyncio.sleep(5)
            for _ in range(3):
                try:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass
                await asyncio.sleep(1.5)
            await dump_comments(page, "post_view_std")


if __name__ == "__main__":
    asyncio.run(main())
