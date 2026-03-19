"""Naver Cafe post writing and editing."""
import asyncio
import random
from config import SELECTORS


async def human_delay(min_s=0.5, max_s=1.5):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def human_type(page, selector_or_element, text, frame=None):
    """Type text with human-like random delays."""
    target = frame or page
    if isinstance(selector_or_element, str):
        await target.click(selector_or_element)
    else:
        await selector_or_element.click()
    await human_delay(0.3, 0.7)

    for char in text:
        await (frame or page).keyboard.type(char, delay=random.randint(30, 120))
        if random.random() < 0.1:
            await human_delay(0.2, 0.5)


async def write_post(page, cafe_url, title, body, board_name=None, log_fn=None):
    """Write a new post on Naver Cafe.
    Returns the new post URL on success, None on failure."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        # Navigate to write page
        write_url = f"https://cafe.naver.com/{cafe_url}/articles/write"
        log(f"글쓰기 페이지 이동: {write_url}")
        await page.goto(write_url, wait_until="networkidle", timeout=30000)
        await human_delay(2, 4)

        # Select board if specified
        if board_name:
            log(f"게시판 선택: {board_name}")
            try:
                board_btn = await page.query_selector(".select_component, .board_select, button:has-text('게시판')")
                if board_btn:
                    await board_btn.click()
                    await human_delay(0.5, 1)
                    board_option = await page.query_selector(f"text={board_name}")
                    if board_option:
                        await board_option.click()
                        await human_delay(0.5, 1)
            except Exception as e:
                log(f"게시판 선택 실패 (계속 진행): {e}")

        # Fill title
        log("제목 입력 중...")
        title_sel = await page.query_selector(".se-title-input, .title_area textarea, [placeholder*='제목']")
        if title_sel:
            await title_sel.click()
            await human_delay(0.3, 0.7)
            await page.keyboard.type(title, delay=random.randint(30, 100))
        await human_delay(0.5, 1)

        # Fill body - SmartEditor
        log("본문 입력 중...")
        body_sel = await page.query_selector(".se-text-paragraph, .se-component-content .se-text-paragraph-align-, [contenteditable='true']")
        if body_sel:
            await body_sel.click()
            await human_delay(0.5, 1)

            # Type body with paragraph support
            lines = body.split("\n")
            for i, line in enumerate(lines):
                if line.strip():
                    await page.keyboard.type(line, delay=random.randint(20, 80))
                if i < len(lines) - 1:
                    await page.keyboard.press("Enter")
                    await human_delay(0.1, 0.3)
        await human_delay(1, 2)

        # Click publish
        log("발행 중...")
        publish_btn = await page.query_selector("button:has-text('등록'), button:has-text('발행'), button:has-text('완료')")
        if publish_btn:
            await publish_btn.click()
            await human_delay(3, 6)

        # Wait for redirect to new post
        await page.wait_for_load_state("networkidle", timeout=15000)
        post_url = page.url
        log(f"글 작성 완료: {post_url}")
        return post_url

    except Exception as e:
        log(f"글 작성 오류: {str(e)}")
        return None


async def edit_post(page, post_url, title, body, log_fn=None):
    """Edit an existing post."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        log(f"글 수정 페이지 이동: {post_url}")
        await page.goto(post_url, wait_until="networkidle", timeout=30000)
        await human_delay(2, 3)

        # The post content is often in an iframe
        # Try to find and click edit button
        # First check if we need to enter an iframe
        cafe_frame = page.frame("cafe_main")
        target = cafe_frame if cafe_frame else page

        edit_btn = await target.query_selector("a:has-text('수정'), button:has-text('수정'), .article_edit")
        if edit_btn:
            await edit_btn.click()
            await human_delay(2, 4)
            await page.wait_for_load_state("networkidle", timeout=15000)
        else:
            # Try direct edit URL
            edit_url = post_url.replace("/articles/", "/articles/") + "?mode=edit"
            await page.goto(edit_url, wait_until="networkidle", timeout=30000)
            await human_delay(2, 3)

        # Clear and fill title
        log("제목 수정 중...")
        title_sel = await page.query_selector(".se-title-input, [placeholder*='제목']")
        if title_sel:
            await title_sel.click()
            await page.keyboard.press("Control+a")
            await human_delay(0.2, 0.4)
            await page.keyboard.type(title, delay=random.randint(30, 100))
        await human_delay(0.5, 1)

        # Clear and fill body
        log("본문 수정 중...")
        body_sel = await page.query_selector(".se-text-paragraph, [contenteditable='true']")
        if body_sel:
            await body_sel.click()
            await page.keyboard.press("Control+a")
            await human_delay(0.2, 0.4)

            lines = body.split("\n")
            for i, line in enumerate(lines):
                if line.strip():
                    await page.keyboard.type(line, delay=random.randint(20, 80))
                if i < len(lines) - 1:
                    await page.keyboard.press("Enter")
                    await human_delay(0.1, 0.3)
        await human_delay(1, 2)

        # Publish
        log("수정 발행 중...")
        publish_btn = await page.query_selector("button:has-text('등록'), button:has-text('수정'), button:has-text('완료')")
        if publish_btn:
            await publish_btn.click()
            await human_delay(3, 6)

        await page.wait_for_load_state("networkidle", timeout=15000)
        log(f"글 수정 완료: {page.url}")
        return page.url

    except Exception as e:
        log(f"글 수정 오류: {str(e)}")
        return None
