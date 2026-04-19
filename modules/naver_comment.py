"""Naver Cafe comment and reply writing.

네이버 카페는 공유 댓글창(textarea.comment_inbox_text)을 사용.
- 일반 댓글: 바로 입력 → 등록
- 대댓글: 대상 댓글의 "답글쓰기" 클릭 → (내부적으로 답글 모드 전환) → 같은 textarea에 입력 → 등록
"""
import asyncio
import random


async def human_delay(min_s=0.5, max_s=1.5):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _find_comment_textarea(page, max_wait=20):
    """공유 댓글창 (textarea.comment_inbox_text) 탐색 — visible한 것"""
    for attempt in range(max_wait // 2):
        for t in [page] + list(page.frames):
            try:
                els = await t.query_selector_all('textarea.comment_inbox_text, textarea[placeholder*="댓글"]')
                for el in els:
                    box = await el.bounding_box()
                    if box and box['width'] > 100:
                        return el, t
            except Exception:
                pass
        await asyncio.sleep(2)
    return None, None


async def _find_register_btn(page):
    """댓글 등록 버튼 (.btn_register) 탐색 — visible"""
    for t in [page] + list(page.frames):
        try:
            els = await t.query_selector_all('a.btn_register, button.btn_register, .btn_register')
            for el in els:
                box = await el.bounding_box()
                if box and box['width'] > 10 and box['y'] > 0:
                    return el
        except Exception:
            pass
    return None


async def _scroll_to_bottom(page):
    """페이지와 모든 iframe을 끝까지 스크롤 (lazy-load 트리거)"""
    try:
        for _ in range(2):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            for f in page.frames:
                try:
                    await f.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass
            await asyncio.sleep(1)
    except Exception:
        pass


async def count_top_comments(page, post_url, log_fn=None):
    """게시글에 이미 있는 **최상위 댓글 개수** 반환.
    이어하기(댓글 전용) 모드에서 to_index 오프셋 계산용.
    """
    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        if post_url not in page.url:
            try:
                await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
            await human_delay(2, 4)
            await _scroll_to_bottom(page)

        total = 0
        for t in [page] + list(page.frames):
            try:
                n = await t.evaluate("""
                    () => {
                        const items = Array.from(document.querySelectorAll('li.CommentItem'));
                        let count = 0;
                        items.forEach(el => {
                            const cls = (el.className || '').toLowerCase();
                            if (!cls.includes('reply') && !cls.includes('answer')) count++;
                        });
                        return count;
                    }
                """)
                if n and n > total:
                    total = n
            except Exception:
                continue
        log(f"기존 최상위 댓글 수: {total}")
        return total
    except Exception as e:
        log(f"댓글 수 집계 오류: {e}")
        return 0


async def write_comment(page, post_url, comment_text, log_fn=None):
    """Write a top-level comment."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))

        log(f"게시글 이동: {post_url[:80]}")
        try:
            await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            log(f"이동 타임아웃(무시): {e}")
        await human_delay(1.5, 3)

        # lazy-load 트리거
        await _scroll_to_bottom(page)

        # 댓글창 탐색
        log("댓글창 탐색...")
        tb, tb_frame = await _find_comment_textarea(page, max_wait=15)
        if not tb:
            log("⚠ 댓글창을 찾을 수 없음")
            try:
                import os as _os
                path = _os.path.join(_os.path.dirname(__file__), "..", "debug_no_comment.png")
                await page.screenshot(path=path, full_page=True)
                log(f"디버그 스크린샷: {path}")
            except Exception:
                pass
            return False

        await tb.scroll_into_view_if_needed()
        await tb.click()
        await human_delay(0.5, 1)

        # 댓글 입력 (여러 줄은 Shift+Enter 로 줄바꿈)
        log("댓글 입력 중...")
        lines = comment_text.split('\n')
        for li, line in enumerate(lines):
            for char in line:
                await page.keyboard.type(char, delay=random.randint(15, 50))
                if random.random() < 0.05:
                    await human_delay(0.1, 0.3)
            if li < len(lines) - 1:
                await page.keyboard.down('Shift')
                await page.keyboard.press('Enter')
                await page.keyboard.up('Shift')
                await human_delay(0.1, 0.25)
        await human_delay(0.3, 0.8)

        # 등록
        pub = await _find_register_btn(page)
        if not pub:
            log("⚠ 등록 버튼 없음")
            return False

        await pub.click()
        await human_delay(1.5, 3)
        log("댓글 작성 완료")
        return True

    except Exception as e:
        log(f"댓글 작성 오류: {str(e)}")
        return False


async def write_reply(page, post_url, comment_index, reply_text, log_fn=None):
    """Reply to comment at given index (0-based)."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))

        if post_url not in page.url:
            try:
                await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                log(f"이동 타임아웃(무시): {e}")
            await human_delay(1.5, 3)
            await _scroll_to_bottom(page)

        # 댓글 목록 탐색 (li.CommentItem 중 최상위 댓글만 — 답글/reply 제외)
        log(f"댓글 목록 탐색 (최상위만)...")

        async def _collect_top_comments():
            res = []
            for t in [page] + list(page.frames):
                try:
                    top_indices = await t.evaluate("""
                        () => {
                            const items = Array.from(document.querySelectorAll('li.CommentItem'));
                            const indices = [];
                            items.forEach((el, i) => {
                                const cls = (el.className || '').toLowerCase();
                                if (!cls.includes('reply') && !cls.includes('answer')) {
                                    indices.push(i);
                                }
                            });
                            return indices;
                        }
                    """)
                    if not top_indices:
                        continue
                    els = await t.query_selector_all('li.CommentItem')
                    for idx in top_indices:
                        if idx < len(els):
                            res.append((els[idx], t))
                except Exception:
                    pass
            return res

        comments = []
        # 1차: 최대 8회 × 2초 = 16초 대기
        for attempt in range(8):
            comments = await _collect_top_comments()
            if comments:
                break
            await asyncio.sleep(2)

        # 1차 실패 시 페이지 reload + 추가 재시도 (캡챠 해결 후 로딩 미완료 케이스 등)
        if not comments:
            log(f"⚠ 댓글 목록 1차 실패 — 페이지 reload 후 재시도")
            try:
                await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                log(f"  reload 타임아웃(무시): {e}")
            await human_delay(2, 4)
            await _scroll_to_bottom(page)
            for attempt in range(6):
                comments = await _collect_top_comments()
                if comments:
                    log(f"  ✓ reload 후 {attempt + 1}회만에 탐지됨")
                    break
                await asyncio.sleep(2)

        if not comments:
            log(f"⚠ 댓글이 없음 (최종 포기)")
            return False

        if comment_index >= len(comments):
            log(f"⚠ 댓글 #{comment_index + 1} 없음 (수집: {len(comments)}개)")
            return False

        target_comment, target_frame = comments[comment_index]
        log(f"댓글 #{comment_index + 1}의 답글쓰기 버튼 클릭...")

        # 답글쓰기 버튼 클릭 (a.comment_info_button with text containing 답글)
        reply_btn = None
        try:
            els = await target_comment.query_selector_all('a.comment_info_button')
            for el in els:
                txt = (await el.text_content() or '').strip()
                if '답글' in txt:
                    reply_btn = el
                    break
        except Exception:
            pass

        if not reply_btn:
            log("⚠ 답글쓰기 버튼을 찾을 수 없음")
            return False

        await reply_btn.click()
        await human_delay(1.5, 2.5)

        # 공유 댓글창 재탐색 (답글 모드로 전환됨)
        tb, tb_frame = await _find_comment_textarea(page, max_wait=10)
        if not tb:
            log("⚠ 답글 입력창을 찾을 수 없음")
            return False

        await tb.scroll_into_view_if_needed()
        await tb.click()
        await human_delay(0.3, 0.7)

        # 대댓글 입력 (여러 줄은 Shift+Enter 로 줄바꿈)
        lines = reply_text.split('\n')
        for li, line in enumerate(lines):
            for char in line:
                await page.keyboard.type(char, delay=random.randint(15, 50))
                if random.random() < 0.05:
                    await human_delay(0.1, 0.3)
            if li < len(lines) - 1:
                await page.keyboard.down('Shift')
                await page.keyboard.press('Enter')
                await page.keyboard.up('Shift')
                await human_delay(0.1, 0.25)
        await human_delay(0.3, 0.8)

        # 등록
        pub = await _find_register_btn(page)
        if not pub:
            log("⚠ 등록 버튼 없음")
            return False

        await pub.click()
        await human_delay(1.5, 3)
        log(f"대댓글 #{comment_index + 1} 작성 완료")
        return True

    except Exception as e:
        log(f"대댓글 작성 오류: {str(e)}")
        return False
