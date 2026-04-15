"""Naver Cafe post writing and editing."""
import asyncio
import random


async def human_delay(min_s=0.5, max_s=1.5):
    await asyncio.sleep(random.uniform(min_s, max_s))


def normalize_to_write_url(url):
    """게시판 URL → 글쓰기 URL 변환.
    - 이미 write URL이면 그대로
    - 'f-e' 경로를 'ca-fe' 로 교체
    - 끝에 /articles/write?boardType=L 추가 (없으면)
    """
    if not url:
        return url
    # f-e → ca-fe (네이버 카페 경로 버그 수정)
    if "/f-e/cafes/" in url:
        url = url.replace("/f-e/cafes/", "/ca-fe/cafes/")
    # 이미 write URL이면 그대로
    if "/articles/write" in url or "ArticleWrite" in url:
        return url
    # 카페명만 들어오면 메인 URL로 (이 경우 사용자가 글쓰기 URL 직접 입력하도록 안내)
    if not url.startswith("http"):
        return f"https://cafe.naver.com/{url}"
    # 게시판 URL에 write 경로 추가
    sep = "&" if "?" in url else "?"
    if url.rstrip("/").endswith("/articles"):
        return url.rstrip("/") + "/write?boardType=L"
    return url.rstrip("/") + "/articles/write?boardType=L"


async def _find_visible(frames_list, selectors, min_w=100, min_h=10, max_wait=20):
    """여러 프레임에서 visible한 요소 탐색 (onscreen만)"""
    for attempt in range(max_wait // 2):
        for t in frames_list:
            for sel in selectors:
                try:
                    els = await t.query_selector_all(sel)
                    for el in els:
                        box = await el.bounding_box()
                        if box and box['width'] >= min_w and box['height'] >= min_h and box['x'] > -100 and box['y'] > -100:
                            return el, t
                except Exception:
                    pass
        await asyncio.sleep(2)
    return None, None


async def write_post(page, cafe_url, title, body, board_name=None, log_fn=None):
    """Write a new post on Naver Cafe."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        # 팝업 자동 닫기
        page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))

        # URL 정규화 (게시판 URL → 글쓰기 URL)
        target_url = normalize_to_write_url(cafe_url)
        log(f"글쓰기 URL 이동: {target_url}")

        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            log(f"이동 타임아웃(무시): {e}")
        await human_delay(3, 5)

        frames_list = lambda: [page] + list(page.frames)

        # 제목 textarea 탐색 (TEXTAREA임, placeholder "제목을 입력해 주세요.")
        log("제목 입력창 탐색...")
        title_el, title_frame = await _find_visible(
            frames_list(),
            [
                'textarea[placeholder="제목을 입력해 주세요."]',
                'textarea.textarea_input',
                'textarea[placeholder*="제목"]',
            ],
            min_w=100, min_h=10, max_wait=20,
        )

        if not title_el:
            log("⚠ 제목 입력창을 찾을 수 없음")
            log(f"   페이지 URL: {page.url}")
            log(f"   → URL이 write 페이지인지 확인 (예: /ca-fe/cafes/XXX/menus/YY/articles/write?boardType=L)")
            try:
                import os as _os
                _path = _os.path.join(_os.path.dirname(__file__), "..", "debug_no_title.png")
                await page.screenshot(path=_path, full_page=True)
                log(f"   디버그 스크린샷: {_path}")
            except Exception:
                pass
            return None

        log("제목 입력 중...")
        await title_el.click()
        await human_delay(0.3, 0.7)
        await page.keyboard.type(title, delay=random.randint(30, 100))
        await human_delay(0.5, 1)

        # 본문 탐색 (.se-text-paragraph P 태그)
        log("본문 입력창 탐색...")
        body_el, body_frame = await _find_visible(
            frames_list(),
            [
                '.se-component-content .se-text-paragraph',
                '.se-text-paragraph',
                'p.se-text-paragraph-align-left',
            ],
            min_w=100, min_h=15, max_wait=10,
        )

        if not body_el:
            log("⚠ 본문 입력창을 찾을 수 없음")
            return None

        try:
            await body_el.scroll_into_view_if_needed()
        except Exception:
            pass
        await body_el.click()
        await human_delay(0.5, 1)

        lines = body.split("\n")
        for i, line in enumerate(lines):
            if line.strip():
                await page.keyboard.type(line, delay=random.randint(20, 80))
            if i < len(lines) - 1:
                await page.keyboard.press("Enter")
                await human_delay(0.1, 0.3)
        await human_delay(1, 2)

        # 등록 버튼 (A 태그, text='등록' 정확히 매칭, 임시등록 제외)
        log("등록 버튼 탐색...")
        pub_el = None
        for t in frames_list():
            try:
                els = await t.query_selector_all('a, button')
                for b in els:
                    try:
                        txt = (await b.text_content() or '').strip()
                        if txt == '등록':
                            box = await b.bounding_box()
                            if box and box['width'] > 10 and box['x'] > 0 and box['y'] > 0:
                                pub_el = b
                                break
                    except Exception:
                        pass
                if pub_el:
                    break
            except Exception:
                pass

        if not pub_el:
            log("⚠ 등록 버튼을 찾을 수 없음")
            return None

        log("발행 중...")
        await pub_el.click()

        # URL 이동 확인 (write 페이지에서 벗어나야 함)
        for _ in range(15):
            await asyncio.sleep(1)
            current = page.url
            if "/articles/write" not in current and "ArticleWrite" not in current:
                break

        post_url = page.url
        if "/articles/write" in post_url or "ArticleWrite" in post_url:
            log(f"⚠ 발행 후에도 write URL: {post_url}")
            return None

        log(f"글 작성 완료: {post_url}")
        return post_url

    except Exception as e:
        log(f"글 작성 오류: {str(e)}")
        return None


async def edit_post(page, post_url, title, body, log_fn=None):
    """Edit an existing post — 기존 로직 유지 (거의 미사용)"""
    def log(msg):
        if log_fn:
            log_fn(msg)
    try:
        log(f"글 수정 페이지 이동: {post_url}")
        await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
        await human_delay(2, 3)
        log("⚠ 수정 모드는 아직 업데이트되지 않음")
        return None
    except Exception as e:
        log(f"글 수정 오류: {str(e)}")
        return None
