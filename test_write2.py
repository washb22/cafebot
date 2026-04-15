"""방법 2: 직접 write URL로 이동"""
import asyncio
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

from modules.browser import new_session
from modules.naver_auth import naver_login

# 직접 write URL (board URL + /articles/write)
WRITE_URL = "https://cafe.naver.com/ca-fe/cafes/19025213/menus/40/articles/write?boardType=L"
ID = "kyqwgdvdfuz"
PW = "plSubx0nbK"
DEBUG_DIR = os.path.join(os.path.dirname(__file__), "test_debug")
os.makedirs(DEBUG_DIR, exist_ok=True)


def log(msg):
    print(f"[{msg}]", flush=True)


async def dump(page, label):
    log(f"===== {label} =====")
    log(f"URL: {page.url}")
    log(f"Frames ({len(page.frames)}):")
    for i, f in enumerate(page.frames):
        try:
            log(f"  [{i}] {f.url[:150]}")
        except Exception:
            pass

    for i, f in enumerate([page] + list(page.frames)):
        try:
            # 글쓰기 관련 엘리먼트만 추려서
            data = await f.evaluate("""
                () => {
                    const results = [];
                    // 제목 관련
                    document.querySelectorAll('input, textarea').forEach(el => {
                        const p = el.placeholder || '';
                        if (p.includes('제목') || p.includes('내용')) {
                            results.push({tag: el.tagName, placeholder: p, class: (el.className||'').substring(0,80), id: el.id});
                        }
                    });
                    // contenteditable
                    document.querySelectorAll('[contenteditable="true"]').forEach(el => {
                        results.push({tag: el.tagName, contenteditable: true, class: (el.className||'').substring(0,80), id: el.id});
                    });
                    return results;
                }
            """)
            if data:
                log(f"  [{i}] 글쓰기 관련 요소 {len(data)}개:")
                for d in data:
                    log(f"    → {d}")
        except Exception:
            pass

    path = os.path.join(DEBUG_DIR, f"{label}.png")
    await page.screenshot(path=path, full_page=True)
    log(f"  스크린샷: {path}")


async def main():
    async with new_session(headless=False) as (ctx, page):
        page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))

        log("STEP 1: 로그인")
        ok = await naver_login(page, ID, PW, log_fn=log)
        if not ok:
            log("로그인 실패")
            return

        log("STEP 2: 직접 write URL로 이동")
        log(f"  URL: {WRITE_URL}")
        try:
            await page.goto(WRITE_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            log(f"  이동 타임아웃: {e}")

        log("STEP 3: 5초 대기 후 덤프")
        await asyncio.sleep(5)
        await dump(page, "write_5s")

        log("STEP 4: 10초 더 대기")
        await asyncio.sleep(10)
        await dump(page, "write_15s")

        log("STEP 5: 15초 더 대기")
        await asyncio.sleep(15)
        await dump(page, "write_30s")

        log("완료")
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
