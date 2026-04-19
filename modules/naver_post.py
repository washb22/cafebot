"""Naver Cafe post writing and editing."""
import asyncio
import random
import re


async def human_delay(min_s=0.5, max_s=1.5):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _cleanup_residual_ui(page, log=None):
    """글 작성/수정 완료 후 SmartEditor 잔재 (이미지 모달, 오버레이, 토스트) 강제 정리.
    Chrome #1 지속 세션에서 특히 필요 (브라우저가 안 닫히므로 모달이 다음 작업까지 남음).
    """
    try:
        # ESC 3회로 모달/드롭다운 닫기
        for _ in range(3):
            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.2)
            except Exception:
                pass
        # se-popup-dim / 이미지 업로드 모달 잔재 DOM 제거
        try:
            await page.evaluate("""
                () => {
                    const sel = '.se-popup-dim, .se-popup-dim-white, .se-photo-modal, [class*="photo-modal"], [class*="image-modal"]';
                    document.querySelectorAll(sel).forEach(el => {
                        try { el.remove(); } catch(e) {}
                    });
                }
            """)
        except Exception:
            pass
        await asyncio.sleep(0.5)
        if log:
            log("  (모달/오버레이 정리 완료)")
    except Exception:
        pass


async def _wait_popup_dim_gone(page, log=None, max_wait=10):
    """SmartEditor 오버레이 (se-popup-dim) 가 사라질 때까지 대기.
    이미지 업로드/카테고리 선택 등 팝업이 pointer events 가로챔 → 등록 클릭 실패 방지.
    ESC 시도 후에도 남아있으면 return (호출자가 force click 으로 폴백).
    """
    for i in range(max_wait):
        try:
            found = False
            for t in [page] + list(page.frames):
                try:
                    el = await t.query_selector('.se-popup-dim, .se-popup-dim-white')
                    if el:
                        box = await el.bounding_box()
                        if box and box['width'] > 50:
                            found = True
                            break
                except Exception:
                    continue
            if not found:
                if i > 0 and log:
                    log(f"  팝업 오버레이 해제 대기 {i}초 후 해제됨")
                return True
            # 오버레이 있으면 ESC 시도
            if i == 2:
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
        except Exception:
            pass
        await asyncio.sleep(1)
    if log:
        log("⚠ 팝업 오버레이가 여전히 남아있음 (force click 폴백 예정)")
    return False


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

    네이티브 파일 피커 차단:
      page.on("filechooser") 리스너를 미리 걸어 두면, Chromium 이 OS 파일 피커를
      띄우려 할 때 Playwright 가 이벤트를 선점해 프로그래매틱으로 파일 세팅함 →
      OS "열기" 창이 화면에 뜨지 않음. 2차 분기(툴바 버튼 클릭)에서 필수.
    """
    def log(msg):
        if log_fn:
            log_fn(msg)

    # 툴바 사진 버튼 후보
    photo_selectors = [
        'button[aria-label*="사진"]',
        'button[data-type="image"]',
        'button.se-image-toolbar-button',
        'button.se-toolbar-item-image',
        'a.se2_photo',
        'button:has(.se-toolbar-icon-image)',
    ]

    # 파일 피커 선점 리스너 등록
    fc_handled = {"done": False}

    async def _fc_handler(fc):
        try:
            await fc.set_files(image_path)
            fc_handled["done"] = True
        except Exception:
            pass

    page.on("filechooser", _fc_handler)

    try:
        # 1차 분기: 페이지에 이미 있는 input[type="file"] 에 직접 파일 세팅
        # (OS 창 안 뜸)
        for t in [page] + list(page.frames):
            try:
                inputs = await t.query_selector_all('input[type="file"]')
                for inp in inputs:
                    try:
                        accept = await inp.get_attribute("accept") or ""
                        if "image" in accept.lower() or accept == "":
                            await inp.set_input_files(image_path)
                            log(f"  이미지 업로드(직접 input): {image_path.rsplit(chr(92), 1)[-1]}")
                            await asyncio.sleep(4)
                            return True
                    except Exception:
                        continue
            except Exception:
                pass

        # 2차 분기: 툴바 버튼 클릭 (filechooser 리스너가 OS 창 선점)
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
        await asyncio.sleep(2)  # filechooser 이벤트 발생 + 리스너 처리 시간

        # filechooser 가 이미 파일 세팅했으면 성공
        if fc_handled["done"]:
            log(f"  이미지 업로드(filechooser 선점): {image_path.rsplit(chr(92), 1)[-1]}")
            await asyncio.sleep(3)
            return True

        # filechooser 가 안 뜬 케이스 — 모달이 열렸을 수 있음. 다시 input 탐색
        for t in [page] + list(page.frames):
            try:
                inputs = await t.query_selector_all('input[type="file"]')
                for inp in inputs:
                    try:
                        await inp.set_input_files(image_path)
                        log(f"  이미지 업로드(재탐색 input): {image_path.rsplit(chr(92), 1)[-1]}")
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
    finally:
        try:
            page.remove_listener("filechooser", _fc_handler)
        except Exception:
            pass


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
        await _wait_popup_dim_gone(page, log)
        try:
            await pub_el.click(timeout=15000)
        except Exception as e:
            log(f"⚠ 일반 클릭 실패 → force 클릭 재시도: {str(e)[:60]}")
            try:
                await pub_el.click(force=True, timeout=10000)
            except Exception as e2:
                log(f"❌ force 클릭도 실패: {str(e2)[:80]}")
                return None

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
        await _cleanup_residual_ui(page, log)
        return post_url

    except Exception as e:
        log(f"글 작성 오류: {str(e)}")
        return None


async def _resolve_edit_url(page, post_url, log_fn=None):
    """post_url 방문 후 cafe_main iframe URL 에서 cafe_id 추출 →
    수정 URL (`/ca-fe/cafes/{cafe_id}/articles/write?articleid={article_id}`) 반환."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        log(f"post_url 이동 타임아웃(무시): {e}")
    await human_delay(3, 5)

    # 단축 URL(naver.me 등) 리다이렉트 후 실제 URL 사용
    resolved_url = page.url
    if resolved_url and resolved_url != post_url:
        log(f"URL 리다이렉트 감지: {post_url} → {resolved_url}")
        post_url = resolved_url

    # article_id: URL 끝에서 추출
    m = re.search(r'/(\d+)(?:\?|$|#)', post_url)
    if not m:
        # oldPath 안에 articleid 가 있을 수도
        m = re.search(r'articleid[=]?(\d+)', post_url)
    if not m:
        log(f"⚠ post_url 에서 article_id 추출 실패: {post_url}")
        return None
    article_id = m.group(1)

    # cafe_id: cafe_main iframe URL 에서 추출
    cafe_id = None
    for _ in range(10):
        for f in page.frames:
            if f.name == "cafe_main":
                mm = re.search(r'/cafes/(\d+)/', f.url or "")
                if mm:
                    cafe_id = mm.group(1)
                    break
        if cafe_id:
            break
        await asyncio.sleep(1)

    if not cafe_id:
        log("⚠ cafe_main iframe 에서 cafe_id 추출 실패")
        return None

    return f"https://cafe.naver.com/ca-fe/cafes/{cafe_id}/articles/{article_id}/modify"


async def edit_post(page, post_url, title, body, log_fn=None, image_map=None):
    """기존 글 수정.

    제목/본문을 새 값으로 덮어씀. 이미지 마커 지원.
    기존 댓글/대댓글은 건드리지 않음 (별도 scenario 단계로 추가).
    """
    def log(msg):
        if log_fn:
            log_fn(msg)

    try:
        page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))

        # post_url 이 이미 /modify 형태면 바로 사용, 아니면 변환
        if "/modify" in post_url:
            edit_url = post_url
        else:
            log(f"수정 URL 확인을 위해 post_url 방문: {post_url}")
            edit_url = await _resolve_edit_url(page, post_url, log_fn)
            if not edit_url:
                log("❌ 수정 URL 을 구성할 수 없음")
                return None

        log(f"수정 페이지 이동: {edit_url}")
        try:
            await page.goto(edit_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            log(f"이동 타임아웃(무시): {e}")
        await human_delay(3, 5)

        frames_list = lambda: [page] + list(page.frames)

        # 제목 textarea 로딩 대기 (기존 제목이 채워질 때까지)
        log("제목 textarea 로딩 대기...")
        title_el = None
        title_frame = None
        for _ in range(15):
            for t in frames_list():
                try:
                    tas = await t.query_selector_all(
                        'textarea[placeholder*="제목"], textarea.textarea_input'
                    )
                    for ta in tas:
                        box = await ta.bounding_box()
                        if box and box["width"] > 100:
                            val = await ta.evaluate("e => e.value")
                            if val:  # 기존 제목이 들어왔음
                                title_el = ta
                                title_frame = t
                                break
                    if title_el:
                        break
                except Exception:
                    pass
            if title_el:
                break
            await asyncio.sleep(1)

        if not title_el:
            log("⚠ 제목 textarea 를 찾지 못함 또는 기존 제목 미로드")
            try:
                import os as _os
                _path = _os.path.join(_os.path.dirname(__file__), "..", "debug_edit_no_title.png")
                await page.screenshot(path=_path, full_page=True)
                log(f"   디버그 스크린샷: {_path}")
            except Exception:
                pass
            return None

        log("제목 clear + 새 제목 입력...")
        await title_el.click()
        await human_delay(0.3, 0.6)
        # select all → delete
        await page.keyboard.press("Control+A")
        await human_delay(0.1, 0.3)
        await page.keyboard.press("Delete")
        await human_delay(0.2, 0.4)
        await page.keyboard.type(title, delay=random.randint(15, 50))
        await human_delay(0.3, 0.7)

        # 본문 SmartEditor 로딩 대기 — write_post 와 동일한 탐색 방식
        log("본문 에디터 로딩 대기...")
        body_el, body_frame = await _find_visible(
            frames_list(),
            [
                '.se-component-content .se-text-paragraph',
                '.se-text-paragraph',
                'p.se-text-paragraph-align-left',
            ],
            min_w=100, min_h=15, max_wait=15,
        )

        if not body_el:
            log("⚠ 본문 paragraph 를 찾지 못함")
            return None

        log("본문 clear + 새 본문 입력...")
        await body_el.click()
        await human_delay(0.3, 0.6)
        # 본문 전체 선택 + 삭제
        await page.keyboard.press("Control+A")
        await human_delay(0.1, 0.3)
        await page.keyboard.press("Delete")
        await human_delay(0.3, 0.6)

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

        # 등록 버튼 (write_post 와 동일 — 수정 모드에서도 '등록' 텍스트)
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

        log("수정 발행 중...")
        await _wait_popup_dim_gone(page, log)
        try:
            await pub_el.click(timeout=15000)
        except Exception as e:
            log(f"⚠ 일반 클릭 실패 → force 클릭 재시도: {str(e)[:60]}")
            try:
                await pub_el.click(force=True, timeout=10000)
            except Exception as e2:
                log(f"❌ force 클릭도 실패: {str(e2)[:80]}")
                return None

        # URL 이동 확인 (write/modify 페이지에서 벗어나야 함 — 수정 성공 판정)
        for _ in range(15):
            await asyncio.sleep(1)
            current = page.url
            if ("/articles/write" not in current and "ArticleWrite" not in current
                and "/modify" not in current):
                break

        final_url = page.url
        if "/articles/write" in final_url or "/modify" in final_url:
            log(f"❌ 발행 후에도 편집 페이지에 남아있음: {final_url}")
            log("   → 등록 버튼 클릭이 실제로 제출되지 않음 (팝업/파일형식 오류 의심)")
            return None

        log(f"글 수정 완료: {final_url}")
        await _cleanup_residual_ui(page, log)
        return final_url

    except Exception as e:
        log(f"글 수정 오류: {str(e)}")
        return None
