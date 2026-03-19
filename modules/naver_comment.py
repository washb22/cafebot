"""Naver Cafe comment and reply writing."""
import asyncio
import random


async def human_delay(min_s=0.5, max_s=1.5):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def get_cafe_frame(page):
    """Get the cafe_main iframe if it exists, otherwise return page."""
    cafe_frame = page.frame("cafe_main")
    return cafe_frame if cafe_frame else page


async def write_comment(page, post_url, comment_text, log_fn=None):
    """Write a comment on a post."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        log(f"댓글 작성 페이지 이동...")
        await page.goto(post_url, wait_until="networkidle", timeout=30000)
        await human_delay(2, 4)

        target = await get_cafe_frame(page)

        # Find comment textarea
        log("댓글 입력 중...")
        comment_box = await target.query_selector(
            "textarea.comment_inbox, "
            ".comment_box textarea, "
            "textarea[placeholder*='댓글'], "
            ".CommentWriter textarea"
        )

        if not comment_box:
            # Try clicking a "댓글 작성" area first
            write_area = await target.query_selector(
                ".comment_write_area, "
                ".comment_box, "
                "[class*='comment'] [class*='write']"
            )
            if write_area:
                await write_area.click()
                await human_delay(0.5, 1)
                comment_box = await target.query_selector(
                    "textarea.comment_inbox, textarea[placeholder*='댓글']"
                )

        if not comment_box:
            log("⚠ 댓글 입력란을 찾을 수 없음")
            return False

        await comment_box.click()
        await human_delay(0.5, 1)

        # Type comment with human-like speed
        for char in comment_text:
            await target.keyboard.type(char, delay=random.randint(30, 120))
            if random.random() < 0.08:
                await human_delay(0.2, 0.5)

        await human_delay(0.5, 1.5)

        # Click submit
        submit_btn = await target.query_selector(
            "a.btn_register, "
            "button.btn_register, "
            "a:has-text('등록'), "
            "button:has-text('등록')"
        )
        if submit_btn:
            await submit_btn.click()
            await human_delay(2, 4)
            log("댓글 작성 완료")
            return True
        else:
            log("⚠ 댓글 등록 버튼을 찾을 수 없음")
            return False

    except Exception as e:
        log(f"댓글 작성 오류: {str(e)}")
        return False


async def write_reply(page, post_url, comment_index, reply_text, log_fn=None):
    """Write a reply to a specific comment (by index, 0-based)."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        # If we're not already on the post page, navigate
        if post_url not in page.url:
            await page.goto(post_url, wait_until="networkidle", timeout=30000)
            await human_delay(2, 4)

        target = await get_cafe_frame(page)

        # Find all comments
        comment_items = await target.query_selector_all(
            ".comment_item, "
            ".CommentItem, "
            "li[class*='comment'], "
            ".comment_box_inner"
        )

        if comment_index >= len(comment_items):
            log(f"⚠ 댓글 #{comment_index + 1}을 찾을 수 없음 (총 {len(comment_items)}개)")
            return False

        comment_el = comment_items[comment_index]
        log(f"댓글 #{comment_index + 1}에 대댓글 작성 중...")

        # Click reply button on this comment
        reply_btn = await comment_el.query_selector(
            "a:has-text('답글'), "
            "button:has-text('답글'), "
            "a.comment_info_button, "
            "[class*='reply'] button"
        )
        if reply_btn:
            await reply_btn.click()
            await human_delay(0.5, 1.5)
        else:
            log(f"⚠ 답글 버튼을 찾을 수 없음")
            return False

        # Find the reply textarea (should appear after clicking reply)
        reply_box = await target.query_selector(
            ".comment_write_area.reply textarea, "
            ".reply_write textarea, "
            "textarea.comment_inbox"
        )

        if not reply_box:
            # Try broader search
            await human_delay(0.5, 1)
            textareas = await target.query_selector_all("textarea.comment_inbox")
            # The reply textarea is usually the last one or the one that just appeared
            if len(textareas) > 1:
                reply_box = textareas[-1]
            elif textareas:
                reply_box = textareas[0]

        if not reply_box:
            log("⚠ 대댓글 입력란을 찾을 수 없음")
            return False

        await reply_box.click()
        await human_delay(0.3, 0.7)

        # Type reply
        for char in reply_text:
            await target.keyboard.type(char, delay=random.randint(30, 120))
            if random.random() < 0.08:
                await human_delay(0.2, 0.5)

        await human_delay(0.5, 1.5)

        # Submit reply
        submit_btn = await target.query_selector(
            ".comment_write_area.reply a.btn_register, "
            ".reply_write button:has-text('등록'), "
            "a.btn_register, "
            "button.btn_register"
        )
        if not submit_btn:
            # Try all register buttons, pick the last visible one
            btns = await target.query_selector_all("a.btn_register, button:has-text('등록')")
            if btns:
                submit_btn = btns[-1]

        if submit_btn:
            await submit_btn.click()
            await human_delay(2, 4)
            log(f"대댓글 #{comment_index + 1} 작성 완료")
            return True
        else:
            log("⚠ 대댓글 등록 버튼을 찾을 수 없음")
            return False

    except Exception as e:
        log(f"대댓글 작성 오류: {str(e)}")
        return False
