"""전체 플로우 테스트: 로그인 → write URL → 제목/본문 입력 → 등록"""
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

WRITE_URL = "https://cafe.naver.com/ca-fe/cafes/19025213/menus/40/articles/write?boardType=L"
ID = "kyqwgdvdfuz"
PW = "plSubx0nbK"
TEST_TITLE = "테스트 제목입니다 (자동 삭제 예정)"
TEST_BODY = "테스트 본문\n두번째 줄\n세번째 줄"

DEBUG_DIR = os.path.join(os.path.dirname(__file__), "test_debug")
os.makedirs(DEBUG_DIR, exist_ok=True)


def log(msg):
    print(f"[{msg}]", flush=True)


async def main():
    async with new_session(headless=False) as (ctx, page):
        page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))

        log("STEP 1: 로그인")
        ok = await naver_login(page, ID, PW, log_fn=log)
        if not ok:
            return

        log("STEP 2: write URL 이동")
        await page.goto(WRITE_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)

        log("STEP 3: 제목 입력창 탐색")
        title_el = None
        title_frame = None
        for attempt in range(15):
            for t in [page] + list(page.frames):
                try:
                    el = await t.query_selector('textarea[placeholder="제목을 입력해 주세요."]')
                    if el:
                        title_el, title_frame = el, t
                        break
                except Exception:
                    pass
            if title_el:
                break
            await asyncio.sleep(1)

        if not title_el:
            log("제목 입력창 못 찾음 — 중단")
            return
        log("제목 입력창 발견!")

        log("STEP 4: 제목 클릭 + 입력")
        await title_el.click()
        await asyncio.sleep(0.5)
        await page.keyboard.type(TEST_TITLE, delay=random.randint(30, 80))
        log(f"제목 입력 완료: {TEST_TITLE}")
        await asyncio.sleep(1)

        log("STEP 5: 본문 입력창 탐색 (visible만)")
        body_el = None
        body_frame = None
        # 여러 selector를 시도하며 visible한 것 선택
        body_selectors = [
            '.se-component-content .se-text-paragraph',
            '.se-text-paragraph',
            'div.__se_editor__',
            'div[contenteditable="true"]',
            'body[contenteditable="true"]',
        ]
        for attempt in range(10):
            for t in [page] + list(page.frames):
                for sel in body_selectors:
                    try:
                        els = await t.query_selector_all(sel)
                        for el in els:
                            # visible 체크
                            try:
                                box = await el.bounding_box()
                                if box and box['width'] > 100 and box['height'] > 15 and box['x'] > -100:
                                    body_el, body_frame = el, t
                                    log(f"  본문 발견: {sel} size={box['width']:.0f}x{box['height']:.0f}")
                                    break
                            except Exception:
                                pass
                        if body_el:
                            break
                    except Exception:
                        pass
                if body_el:
                    break
            if body_el:
                break
            await asyncio.sleep(1)

        if not body_el:
            log("본문 입력창 못 찾음 — 전체 contenteditable 덤프:")
            for i, t in enumerate([page] + list(page.frames)):
                try:
                    data = await t.evaluate("""
                        () => Array.from(document.querySelectorAll('[contenteditable="true"], .se-text-paragraph'))
                            .map(el => {
                                const r = el.getBoundingClientRect();
                                return {
                                    tag: el.tagName,
                                    class: (el.className||'').toString().substring(0,100),
                                    placeholder: el.getAttribute('placeholder')||'',
                                    w: r.width, h: r.height, x: r.x, y: r.y
                                };
                            })
                    """)
                    if data:
                        log(f"  [{i}]:")
                        for d in data:
                            log(f"    {d}")
                except Exception:
                    pass
            return

        log("STEP 6: 본문 클릭 + 입력")
        try:
            await body_el.scroll_into_view_if_needed()
        except Exception:
            pass
        await body_el.click()
        await asyncio.sleep(0.5)
        lines = TEST_BODY.split('\n')
        for i, line in enumerate(lines):
            if line:
                await page.keyboard.type(line, delay=random.randint(20, 60))
            if i < len(lines) - 1:
                await page.keyboard.press("Enter")
                await asyncio.sleep(0.2)
        log("본문 입력 완료")
        await asyncio.sleep(2)

        await page.screenshot(path=os.path.join(DEBUG_DIR, "filled.png"), full_page=True)
        log(f"채워진 상태 스크린샷: {DEBUG_DIR}/filled.png")

        log("STEP 7: 등록 버튼 탐색")
        pub_el = None
        for t in [page] + list(page.frames):
            try:
                els = await t.query_selector_all('a, button')
                for b in els:
                    try:
                        txt = (await b.text_content() or '').strip()
                        if txt == '등록':  # 정확히 '등록'만 (임시등록 제외)
                            box = await b.bounding_box()
                            if box and box['width'] > 10 and box['x'] > 0:
                                pub_el = b
                                log(f"  등록 버튼 발견: text='{txt}' at ({box['x']:.0f},{box['y']:.0f})")
                                break
                    except Exception:
                        pass
                if pub_el:
                    break
            except Exception:
                pass

        if not pub_el:
            log("등록 버튼 못 찾음 — 전체 button 덤프:")
            for i, t in enumerate([page] + list(page.frames)):
                try:
                    data = await t.evaluate("""
                        () => Array.from(document.querySelectorAll('button, a')).filter(el => {
                            const t = (el.textContent || '').trim();
                            return t.includes('등록') || t.includes('저장') || t.includes('완료');
                        }).map(el => {
                            const r = el.getBoundingClientRect();
                            return {
                                tag: el.tagName,
                                text: (el.textContent || '').trim().substring(0, 40),
                                class: (el.className || '').toString().substring(0, 80),
                                w: r.width, h: r.height, x: r.x, y: r.y
                            };
                        })
                    """)
                    if data:
                        log(f"  [{i}]:")
                        for d in data:
                            log(f"    {d}")
                except Exception:
                    pass
            return

        log("STEP 8: 등록 버튼 클릭")
        await pub_el.click()
        await asyncio.sleep(10)
        final_url = page.url
        log(f"최종 URL: {final_url}")
        await page.screenshot(path=os.path.join(DEBUG_DIR, "published.png"), full_page=True)

        # 게시된 URL 파일에 저장해둠 (댓글 테스트에서 사용)
        with open(os.path.join(DEBUG_DIR, "post_url.txt"), "w", encoding="utf-8") as f:
            f.write(final_url)
        log("post_url.txt에 저장 완료")


if __name__ == "__main__":
    asyncio.run(main())
