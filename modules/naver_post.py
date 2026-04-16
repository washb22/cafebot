"""Naver Cafe post writing and editing."""
import asyncio
import random
import re


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


async def _insert_image(page, image_path, log_fn=None):
    """SmartEditor 본문 입력 중 커서 위치에 이미지 삽입.
    가장 불안정한 파트: 네이버 SmartEditor DOM 변경 시 selector 조정 필요.
    여러 selector 후보를 순차 시도.
    """
    def log(msg):
        if log_fn:
            log_fn(msg)

    # 툴바 사진 버튼 후보 (SmartEditor 2 / ONE 공통 추정)
    photo_selectors = [
        'button[aria-label*="사진"]',
        'button[data-type="image"]',
        'button.se-image-toolbar-button',
        'button.se-toolbar-item-image',
        'a.se2_photo',
        'button:has(.se-toolbar-icon-image)',
    ]

    try:
        # 파일 업로드 input 은 툴바 버튼 클릭 없이도 페이지에 존재할 가능성 있음 → 먼저 시도
        for t in [page] + list(page.frames):
            try:
                inputs = await t.query_selector_all('input[type="file"]')
                for inp in inputs:
                    try:
                        accept = await inp.get_attribute("accept") or ""
                        if "image" in accept.lower() or accept == "":
                            await inp.set_input_files(image_path)
                            log(f"  이미지 업로드: {image_path.rsplit(chr(92), 1)[-1]}")
                            await asyncio.sleep(4)
                            return True
                    except Exception:
                        continue
            except Exception:
                pass

        # 툴바 버튼 클릭 → 파일 input 노출 기다리기
        btn = None
        btn_frame = None
        for t in [page] + list(page.frames):
            for sel in photo_selectors:
                try:
                    el = await t.query_selector(sel)
                    if el:
                        box = await el.bounding_box()
                        if box and box["width"] > 5:
                            btn = el
                            btn_frame = t
                            break
                except Exception:
                    continue
            if btn:
                break

        if not btn:
            log("  ⚠ SmartEditor 사진 버튼을 찾을 수 없음 — 이미지 건너뜀")
            return False

        await btn.click()
        await asyncio.sleep(1.5)

        # 파일 input 재탐색
        for t in [page] + list(page.frames):
            try:
                inputs = await t.query_selector_all('input[type="file"]')
                for inp in inputs:
                    try:
                        await inp.set_input_files(image_path)
                        log(f"  이미지 업로드: {image_path.rsplit(chr(92), 1)[-1]}")
                        await asyncio.sleep(4)
                        return True
                    except Exception:
                        continue
            except Exception:
                pass

        log("  ⚠ 파일 업로드 input 을 찾을 수 없음")
        return False
    except Exception as e:
        log(f"  ⚠ 이미지 삽입 오류: {e}")
        return False


async def _type_body_with_images(page, body_el, body, image_map, log_fn=None):
    """본문을 [이미지N] 마커로 분할해 텍스트 + 이미지 순차 입력."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    marker_re = re.compile(r'\[이미지(\d+)\]')
    parts = []  # [("text", "..."), ("img", 1), ("text", "...")] 형태
    pos = 0
    for m in marker_re.finditer(body):
        if m.start() > pos:
            parts.append(("text", body[pos:m.start()]))
        parts.append(("img", int(m.group(1))))
        pos = m.end()
    if pos < len(body):
        parts.append(("text", body[pos:]))

    for kind, val in parts:
        if kind == "text":
            text = val
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if line.strip():
                    await page.keyboard.type(line, delay=random.randint(15, 50))
                if i < len(lines) - 1:
                    await page.keyboard.press("Enter")
                    await human_delay(0.05, 0.15)
        else:
            num = val
            path = (image_map or {}).get(num)
            if not path:
                log(f"  ⚠ [이미지{num}] 마커는 있으나 업로드된 파일 없음 — 텍스트 유지")
                await page.keyboard.type(f"[이미지{num}]", delay=random.randint(15, 50))
                continue
            # 이미지 삽입 전후 개행
            await page.keyboard.press("Enter")
            await human_delay(0.2, 0.4)
            await _insert_image(page, path, log_fn)
            # 이미지 삽입 후 커서를 다음 줄로
            try:
                await body_el.click()
            except Exception:
                pass
            await human_delay(0.3, 0.6)


async def write_post(page, cafe_url, title, body, board_name=None, log_fn=None, image_map=None):
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
        await page.keyboard.type(title, delay=random.randint(15, 50))
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
        await human_delay(0.3, 0.7)

        # 이미지 마커가 있으면 분할 입력, 없으면 기존 방식
        if image_map and re.search(r'\[이미지\d+\]', body):
            log("본문 입력 (이미지 마커 포함)...")
            await _type_body_with_images(page, body_el, body, image_map, log_fn)
        else:
            lines = body.split("\n")
            for i, line in enumerate(lines):
                if line.strip():
                    await page.keyboard.type(line, delay=random.randint(15, 50))
                if i < len(lines) - 1:
                    await page.keyboard.press("Enter")
                    await human_delay(0.05, 0.15)
        await human_delay(0.5, 1.2)

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
