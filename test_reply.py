"""대댓글 작성 테스트"""
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
REPLY_TEXT = "대댓글 테스트입니다"


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
        for _ in range(3):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            for f in page.frames:
                try:
                    await f.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass
            await asyncio.sleep(1.5)

        # 댓글 목록 탐색 (정확히 CommentItem만, 탭 제외)
        log("댓글 목록 탐색")
        comments = []
        for attempt in range(8):
            comments = []
            for t in [page] + list(page.frames):
                try:
                    els = await t.query_selector_all('li.CommentItem')
                    for e in els:
                        comments.append((e, t))
                except Exception:
                    pass
            if comments:
                break
            await asyncio.sleep(1)

        log(f"찾은 댓글 수: {len(comments)}")
        if not comments:
            log("댓글 없음 — 전체 comment-like 구조 덤프")
            for i, t in enumerate([page] + list(page.frames)):
                try:
                    data = await t.evaluate("""
                        () => Array.from(document.querySelectorAll('[class*="comment"], [class*="Comment"]'))
                            .filter(el => el.tagName !== 'DIV' || el.querySelectorAll('[class*="comment"]').length === 0)
                            .slice(0, 10)
                            .map(el => ({tag: el.tagName, class: (el.className||'').substring(0,80)}))
                    """)
                    if data:
                        log(f"  [{i}]:")
                        for d in data:
                            log(f"    {d}")
                except Exception:
                    pass
            return

        # 첫 댓글 → 답글 버튼 찾기 (text="답글쓰기", class=comment_info_button)
        target_comment, target_frame = comments[0]
        log("첫 댓글에서 답글쓰기 버튼 탐색")
        reply_btn = None
        for sel in [
            'a.comment_info_button',
            'a:has-text("답글쓰기")',
            'button:has-text("답글쓰기")',
            'a:has-text("답글")',
        ]:
            try:
                els = await target_comment.query_selector_all(sel)
                for el in els:
                    txt = (await el.text_content() or '').strip()
                    if '답글' in txt:
                        reply_btn = el
                        log(f"  발견: {sel} text={txt}")
                        break
                if reply_btn:
                    break
            except Exception:
                pass

        if not reply_btn:
            log("답글 버튼 못 찾음 — 댓글 내부 덤프")
            try:
                data = await target_frame.evaluate("""
                    (el) => Array.from(el.querySelectorAll('a, button')).map(e => ({
                        tag: e.tagName, text: (e.textContent||'').trim().substring(0,30),
                        class: (e.className||'').toString().substring(0,80)
                    }))
                """, target_comment)
                for d in data:
                    log(f"  {d}")
            except Exception as e:
                log(f"덤프 실패: {e}")
            return

        # 답글 클릭 전 textarea 개수
        before = 0
        for t in [page] + list(page.frames):
            try:
                els = await t.query_selector_all('textarea')
                before += len(els)
            except Exception:
                pass
        log(f"답글 클릭 전 textarea: {before}개")

        await reply_btn.click()
        await asyncio.sleep(2)

        # 새로 생긴 textarea 탐색
        log("답글 textarea 탐색")
        reply_box = None
        reply_frame = None
        for attempt in range(8):
            for t in [page] + list(page.frames):
                try:
                    els = await t.query_selector_all('textarea[placeholder*="답글"], textarea[placeholder*="댓글"]')
                    # 마지막(새로 생긴) 것 선택
                    for el in reversed(els):
                        box = await el.bounding_box()
                        if box and box['width'] > 100 and box['height'] > 10:
                            # 본 댓글이 아닌 답글용 - 기본 댓글창은 맨 아래, 답글창은 댓글 바로 아래
                            reply_box = el
                            reply_frame = t
                            log(f"  발견: size={box['width']:.0f}x{box['height']:.0f} at ({box['x']:.0f},{box['y']:.0f})")
                            break
                    if reply_box:
                        break
                except Exception:
                    pass
            if reply_box:
                break
            await asyncio.sleep(1)

        if not reply_box:
            log("답글 textarea 못 찾음")
            return

        await reply_box.scroll_into_view_if_needed()
        await reply_box.click()
        await asyncio.sleep(0.5)
        await page.keyboard.type(REPLY_TEXT, delay=random.randint(30, 80))
        await asyncio.sleep(1)

        log("답글 등록 탐색")
        # 답글 등록 버튼 (보통 답글 textarea 근처 btn_register)
        pub_el = None
        # 전체 .btn_register 중 가장 위 위치의 것 (새로 생긴 답글창 근처)
        candidates = []
        for t in [page] + list(page.frames):
            try:
                els = await t.query_selector_all('.btn_register, a.btn_register, button.btn_register')
                for el in els:
                    box = await el.bounding_box()
                    if box and box['width'] > 10:
                        candidates.append((el, box))
            except Exception:
                pass
        # 답글 textarea 근처(y 가까운)인 등록 버튼 선택
        if candidates:
            reply_box_location = await reply_box.bounding_box()
            if reply_box_location:
                candidates.sort(key=lambda c: abs(c[1]['y'] - reply_box_location['y']))
                pub_el = candidates[0][0]
                log(f"  가까운 등록 버튼 at y={candidates[0][1]['y']:.0f} (답글창 y={reply_box_location['y']:.0f})")

        if not pub_el:
            log("등록 버튼 못 찾음")
            return

        await pub_el.click()
        await asyncio.sleep(5)
        await page.screenshot(path=os.path.join(DEBUG_DIR, "reply_posted.png"), full_page=True)
        log("대댓글 완료")


if __name__ == "__main__":
    asyncio.run(main())
