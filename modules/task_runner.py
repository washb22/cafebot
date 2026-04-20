"""Task orchestration engine - sequences the full workflow (proxy 기반)."""
import asyncio
import random
from playwright.async_api import async_playwright

from modules.browser import new_session, _normalize_proxy, USER_AGENTS, VIEWPORTS
from modules.naver_auth import naver_login, CaptchaDetected
from modules.naver_post import write_post, edit_post
from modules.naver_comment import write_comment, write_reply, count_top_comments
from modules.adb_network import interruptible_sleep, toggle_airplane_mode, is_device_connected, get_current_ip
from modules.proxy_check import verify_proxy_ip, expected_ip_from_proxy
from config import DEFAULT_DELAYS, DEFAULT_IP_MODE


class PersistentMainSession:
    """작성자(메인) 전용 지속 세션 — 시나리오 전체 동안 살아있으면서 모든 작성자 대댓글 처리.
    실패 시 최대 2회 재연결 시도 (Q1.B).

    ip_mode: "proxy" = 계정의 proxy 필드 사용 + 실 IP 검증.
             "adb"   = 프록시 없이 PC 공인 IP(폰 테더링) 로 직접 접속.
    """

    def __init__(self, main_acc, log_fn, ip_mode=DEFAULT_IP_MODE):
        self.main_acc = main_acc
        self.log = log_fn
        self.ip_mode = ip_mode
        self.pw = None
        self.browser = None
        self.ctx = None
        self.page = None
        # ADB 모드에서는 프록시 필드 무시
        if ip_mode == "adb":
            self.proxy_str = ""
            self.expected_ip = None
        else:
            self.proxy_str = (main_acc.get("proxy") or "").strip()
            self.expected_ip = expected_ip_from_proxy(self.proxy_str)

    async def open(self):
        """브라우저 기동 → 프록시 검증(프록시 모드만) → 네이버 로그인."""
        if self.pw is None:
            self.pw = await async_playwright().start()
        proxy_cfg = _normalize_proxy(self.proxy_str)
        launch_kwargs = {
            "headless": False,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-infobars",
            ],
        }
        if proxy_cfg:
            launch_kwargs["proxy"] = proxy_cfg
        self.browser = await self.pw.chromium.launch(**launch_kwargs)
        viewport = random.choice(VIEWPORTS)
        ua = random.choice(USER_AGENTS)
        self.ctx = await self.browser.new_context(
            viewport=viewport, locale="ko-KR", timezone_id="Asia/Seoul",
            user_agent=ua, ignore_https_errors=True, java_script_enabled=True,
        )
        await self.ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        )
        self.page = await self.ctx.new_page()

        # 프록시 IP 검증 (proxy 모드 전용)
        if self.ip_mode == "proxy" and self.expected_ip:
            status, actual = await verify_proxy_ip(self.page, self.expected_ip, self.log)
            if status != "ok":
                raise RuntimeError(f"메인 프록시 검증 실패 ({status}, actual={actual})")

        # 로그인 (캡챠 시 예외 전파)
        ok = await naver_login(self.page, self.main_acc["id"], self.main_acc["pw"], self.log)
        if not ok:
            raise RuntimeError("메인 로그인 실패")

        mode_tag = "ADB" if self.ip_mode == "adb" else "프록시"
        self.log(f"✓ 메인 세션 열림 (지속/{mode_tag}): {self.main_acc.get('label', self.main_acc.get('id', '?'))}")

    async def open_with_captcha_retry(self, retry_limit=2):
        """캡챠 발생 시 브라우저 새로 열어 재시도. open() 외부에서 호출."""
        for attempt in range(retry_limit + 1):
            try:
                await self.open()
                return True
            except CaptchaDetected as e:
                self.log(f"  🔄 메인 캡챠 감지 ({attempt + 1}/{retry_limit + 1}) — 세션 정리 후 재시도")
                await self.close()
                if attempt < retry_limit:
                    await asyncio.sleep(random.uniform(10, 20))
                    continue
                raise RuntimeError(f"메인 캡챠 재시도 한계 초과: {e}")
            except Exception:
                # 캡챠 외 예외는 그대로
                raise
        return False

    async def close(self):
        try:
            if self.ctx:
                await self.ctx.close()
        except Exception:
            pass
        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass
        try:
            if self.pw:
                await self.pw.stop()
        except Exception:
            pass
        self.pw = self.browser = self.ctx = self.page = None

    async def reconnect(self):
        """세션 죽었을 때 재연결 (Q1.B: 2회 시도). 캡챠 감지 시 재시도 로직 포함."""
        self.log("🔄 메인 세션 재연결 시도...")
        await self.close()
        for attempt in range(1, 3):
            try:
                await self.open_with_captcha_retry(retry_limit=1)
                self.log(f"  ✓ 재연결 성공 ({attempt}/2)")
                return True
            except Exception as e:
                self.log(f"  ⚠ 재연결 {attempt}/2 실패: {str(e)[:80]}")
                await asyncio.sleep(5)
        self.log("❌ 메인 세션 재연결 최종 실패")
        return False

    async def goto_post_and_reply(self, post_url, actual_idx, text, delays=None):
        """post_url 로 이동 → 2~3초 대기 → 대댓글 작성. 실패 시 재연결 후 1회 재시도."""
        async def _attempt():
            await self.page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(random.uniform(2, 3))
            return await write_reply(self.page, post_url, actual_idx, text, self.log)

        try:
            if self.page is None:
                raise RuntimeError("메인 페이지 없음")
            ok = await _attempt()
            if ok:
                return True
            self.log("⚠ 작성자 대댓글 실패 → 메인 세션 재연결 후 재시도")
        except Exception as e:
            self.log(f"⚠ 작성자 대댓글 오류: {str(e)[:80]} → 재연결 시도")

        if not await self.reconnect():
            return False
        try:
            return await _attempt()
        except Exception as e:
            self.log(f"❌ 재연결 후에도 실패: {str(e)[:80]}")
            return False

    async def do_write_post(self, cafe_url, title, body, board_name, image_map):
        """신규 글 작성 (로그인 스킵, 이미 로그인된 메인 세션 재사용)."""
        if self.page is None:
            if not await self.reconnect():
                return None
        return await write_post(
            self.page, cafe_url, title, body, board_name, self.log, image_map=image_map
        )

    async def do_edit_post(self, post_url, title, body, image_map):
        """기존 글 수정 (로그인 스킵)."""
        if self.page is None:
            if not await self.reconnect():
                return None
        return await edit_post(
            self.page, post_url, title, body, self.log, image_map=image_map
        )

    async def count_top_comments_at(self, post_url):
        """게시글의 기존 최상위 댓글 수 (base_offset 용)."""
        if self.page is None:
            if not await self.reconnect():
                return 0
        return await count_top_comments(self.page, post_url, self.log)


async def random_delay(key, delays=None, stop_event=None):
    """Wait for a random duration based on delay config. 중단 가능."""
    d = (delays or DEFAULT_DELAYS).get(key, (2, 5))
    wait = random.uniform(d[0], d[1])
    await interruptible_sleep(wait, stop_event)


async def _open_session_with_proxy(account, log_fn, verify=True):
    """계정의 proxy 를 사용해 브라우저 세션 연다.

    계정 dict 에 'proxy' 필드가 있으면 사용, 없으면 프록시 없이 진행 (경고).
    verify=True 면 실제 IP 가 프록시 IP 와 일치하는지 확인 후 실패 시 None 반환.

    반환: 세션 컨텍스트매니저 (with 구문에서 사용) 또는 None (프록시 실패 시)
    """
    proxy = account.get("proxy")
    if not proxy:
        log_fn(f"⚠ 계정 {account.get('id', '?')[:6]}*** 프록시 미설정 - PC 직접 IP 로 실행")
    return proxy


async def _rotate_adb_ip(log_fn, stop_event, extra_retries=1):
    """ADB 모드 전용: 폰 비행기모드 토글로 PC 공인 IP 변경.

    실패 시 extra_retries 회 추가 재시도 (토글 간 대기 포함).
    최종 실패 시 fatal=True — 같은 IP 로 다음 계정 진행하면 연관성 노출 위험.

    Returns: {"ok": bool, "fatal": bool, "error": str or None, "new_ip": str}
    """
    if not is_device_connected():
        log_fn("❌ ADB 디바이스 미연결 - IP 변경 불가 (USB 테더링 + USB 디버깅 허용 확인)")
        return {"ok": False, "fatal": True, "error": "adb_not_connected", "new_ip": None}

    before_ip = get_current_ip()

    for attempt in range(1, extra_retries + 2):  # 1 = 기본 + extra_retries 회
        if stop_event and stop_event.is_set():
            return {"ok": False, "fatal": False, "error": "stopped", "new_ip": None}
        try:
            new_ip = await toggle_airplane_mode(log_fn, stop_event)
        except Exception as e:
            log_fn(f"❌ ADB 토글 예외: {e}")
            new_ip = None

        if new_ip and new_ip != before_ip:
            return {"ok": True, "fatal": False, "error": None, "new_ip": new_ip}

        if attempt <= extra_retries:
            wait = 20
            log_fn(f"⚠ IP 변경 실패 ({attempt}/{extra_retries + 1}) — {wait}초 후 재시도")
            if await interruptible_sleep(wait, stop_event):
                return {"ok": False, "fatal": False, "error": "stopped", "new_ip": None}

    # 최종 실패: 같은 IP 로 다른 계정 돌리면 밴 위험 → 전체 중단
    log_fn(f"🛑 IP 변경 최종 실패 (before={before_ip}) - 전체 작업 중단")
    log_fn("→ 폰 재부팅 / USB 테더링 재시작 / WiFi 테더링 전환 후 재실행 권장")
    return {"ok": False, "fatal": True, "error": "ip_not_rotated", "new_ip": before_ip}


async def _run_with_account(account, log_fn, stop_event, do_work, ip_mode=DEFAULT_IP_MODE):
    """계정의 IP 설정에 맞춰 세션을 열고 do_work(page) 실행.

    ip_mode:
      "proxy" — 계정의 proxy 필드로 브라우저 실행 + 실 IP 검증.
      "adb"   — 비행기모드 토글로 PC IP 갱신 후 프록시 없이 브라우저 실행.

    do_work: async callable(page) -> any
    Returns: {"ok": bool, "fatal": bool, "error": str or None, "result": any}

    fatal=True 인 경우(배치 전체 중단해야 함):
      - [proxy] 계정에 proxy 미설정
      - [proxy] 프록시 설정됐으나 실제 IP 불일치
      - [adb]   ADB 디바이스 미연결
    """
    acc_tag = f"{account.get('label', account.get('id', '?'))[:10]}"

    if ip_mode == "adb":
        # 1) IP 먼저 바꾸고 브라우저는 프록시 없이
        rot = await _rotate_adb_ip(log_fn, stop_event)
        if not rot["ok"]:
            return {"ok": False, "fatal": rot["fatal"], "error": rot["error"], "result": None}
        if stop_event and stop_event.is_set():
            return {"ok": False, "fatal": False, "error": "stopped", "result": None}
        try:
            async with new_session(proxy=None) as (ctx, page):
                if stop_event and stop_event.is_set():
                    return {"ok": False, "fatal": False, "error": "stopped", "result": None}
                result = await do_work(page)
                return {"ok": True, "fatal": False, "error": None, "result": result}
        except CaptchaDetected:
            log_fn(f"  🔄 {acc_tag} 캡챠 감지 — 새 세션 재시도 요청")
            return {"ok": False, "fatal": False, "error": "captcha_retry", "result": None, "captcha": True}
        except Exception as e:
            log_fn(f"❌ {acc_tag} 세션 오류: {e}")
            return {"ok": False, "fatal": False, "error": str(e), "result": None}

    # ── proxy 모드 (기본) ──
    proxy = (account.get("proxy") or "").strip()
    expected_ip = expected_ip_from_proxy(proxy)

    if not proxy:
        log_fn(f"❌ {acc_tag} 프록시 미설정 - IP 미변경 위험으로 중단")
        return {"ok": False, "fatal": True, "error": "proxy_not_set", "result": None}

    if not expected_ip:
        log_fn(f"❌ {acc_tag} 프록시 형식 오류 (IP 추출 불가): '{proxy}' - 중단")
        return {"ok": False, "fatal": True, "error": "proxy_parse_error", "result": None}

    try:
        async with new_session(proxy=proxy) as (ctx, page):
            status, actual = await verify_proxy_ip(page, expected_ip, log_fn)
            if status == "mismatch":
                log_fn(f"❌ {acc_tag} IP 불일치 (기대={expected_ip}, 실제={actual}) - 중단")
                return {"ok": False, "fatal": True, "error": "proxy_mismatch", "result": None}
            if status == "unreachable":
                log_fn(f"⚠ {acc_tag} 프록시 응답 없음 (기대={expected_ip}) - 이 계정 스킵하고 계속")
                return {"ok": False, "fatal": False, "error": "proxy_unreachable", "result": None}

            if stop_event and stop_event.is_set():
                return {"ok": False, "fatal": False, "error": "stopped", "result": None}

            result = await do_work(page)
            return {"ok": True, "fatal": False, "error": None, "result": result}
    except CaptchaDetected as e:
        log_fn(f"  🔄 {acc_tag} 캡챠 감지 — 새 세션 재시도 요청")
        return {"ok": False, "fatal": False, "error": "captcha_retry", "result": None, "captcha": True}
    except Exception as e:
        log_fn(f"❌ {acc_tag} 세션 오류: {e}")
        return {"ok": False, "fatal": False, "error": str(e), "result": None}


async def _run_with_account_retry(account, log_fn, stop_event, do_work, captcha_retry_limit=2, ip_mode=DEFAULT_IP_MODE):
    """_run_with_account + 캡챠 자동 재시도 래퍼."""
    for attempt in range(captcha_retry_limit + 1):
        r = await _run_with_account(account, log_fn, stop_event, do_work, ip_mode=ip_mode)
        if not r.get("captcha"):
            return r
        if attempt < captcha_retry_limit:
            wait = random.uniform(8, 15)
            acc_tag = f"{account.get('label', account.get('id', '?'))[:10]}"
            log_fn(f"  🔄 {acc_tag} 캡챠 재시도 {attempt + 1}/{captcha_retry_limit} — {wait:.1f}초 대기")
            await asyncio.sleep(wait)
    log_fn(f"❌ 캡챠 재시도 한계 초과 — 해당 계정 스킵")
    return r


def _halt(stop_event, log_fn, reason):
    """치명적 IP 문제 발생 시 전체 중단 플래그 설정."""
    log_fn(f"🛑 전체 작업 중단: {reason}")
    if stop_event:
        stop_event.set()


async def _compute_base_offset(main_acc, post_url, log_fn, ip_mode=DEFAULT_IP_MODE):
    """게시글의 기존 최상위 댓글 수를 세어 반환.
    이어하기 시 to_index 오프셋 계산용.
    proxy 모드: 메인 계정 프록시 사용 / adb 모드: 프록시 없이 현재 PC IP.
    """
    if not post_url:
        return 0
    proxy = None if ip_mode == "adb" else (main_acc.get("proxy") or "").strip()
    if ip_mode == "proxy" and not proxy:
        return 0
    try:
        async with new_session(proxy=proxy) as (ctx, page):
            return await count_top_comments(page, post_url, log_fn)
    except Exception as e:
        log_fn(f"⚠ base_offset 계산 실패: {e} (0 으로 진행)")
        return 0


async def run_task(task, log_fn, stop_event=None):
    """Execute the full posting + commenting workflow.

    task = {
        "mode": "new" / "edit" / "comment_only",
        "cafe_url": "cafeurl",
        "post_url": "..." (for edit/comment_only mode),
        "board_name": "게시판명" (optional),
        "title": "글 제목",
        "body": "글 본문",
        "main_account": {"id": "...", "pw": "...", "proxy": "..."},
        "comments": [{"account": {..., "proxy":...}, "text": "..."}, ...],
        "replies": [{"to_index": 0, "text": "..."}],
        "scenario": [{"action":..., "account":..., "text":..., "to_index":...}],
        "delays": {...} (optional override)
    }
    """
    delays = task.get("delays", DEFAULT_DELAYS)
    main = task["main_account"]
    post_url = task.get("post_url", "")
    ip_mode = (task.get("ip_mode") or DEFAULT_IP_MODE).lower()
    if ip_mode not in ("proxy", "adb"):
        ip_mode = DEFAULT_IP_MODE
    log_fn(f"🔧 IP 모드: {'ADB 테더링' if ip_mode == 'adb' else 'HTTP 프록시'}")
    if ip_mode == "adb" and not is_device_connected():
        log_fn("❌ ADB 디바이스 미연결 상태로 작업 시작 불가")
        return {"success": False, "error": "adb_not_connected"}

    def should_stop():
        return stop_event and stop_event.is_set()

    is_comment_only = task.get("mode") == "comment_only"

    if is_comment_only:
        total_steps = len(task.get("scenario", [])) or (len(task.get("comments", [])) + (1 if task.get("replies") else 0))
    else:
        total_steps = 2 + len(task.get("comments", [])) + (1 if task.get("replies") else 0)
    current_step = 0

    # 메인 지속 세션: 작성자 모든 활동(글 작성/수정, base_offset, 작성자 대댓글)을 여기서 처리
    main_session = PersistentMainSession(main, log_fn, ip_mode=ip_mode)
    try:
        try:
            await main_session.open_with_captcha_retry(retry_limit=2)
        except Exception as e:
            log_fn(f"❌ 메인 세션 초기화 실패: {e}")
            return {"success": False, "error": f"main session init: {e}"}

        # ═══════════════════════════════════════
        # STEP 1: Main - Write/Edit post (Chrome #1 재사용)
        # ═══════════════════════════════════════
        if is_comment_only:
            post_url = task["post_url"]
            log_fn(f"━━━ 댓글 전용 모드 ━━━")
            log_fn(f"대상 글: {post_url}")
        else:
            current_step += 1
            log_fn(f"━━━ [{current_step}/{total_steps}] 글 작성/수정 (메인 세션) ━━━")
            await random_delay("after_login", delays, stop_event)

            if task["mode"] == "new":
                post_url = await main_session.do_write_post(
                    task["cafe_url"], task["title"], task["body"],
                    task.get("board_name"), task.get("image_map"),
                )
                if not post_url:
                    log_fn("❌ 글 작성 실패 - 작업 중단")
                    return {"success": False, "error": "글 작성 실패"}
            else:
                post_url = task["post_url"]
                result = await main_session.do_edit_post(
                    post_url, task["title"], task["body"], task.get("image_map"),
                )
                if not result:
                    log_fn("❌ 글 수정 실패 - 작업 중단")
                    return {"success": False, "error": "글 수정 실패"}

            await random_delay("after_post_submit", delays, stop_event)
            log_fn(f"글 URL: {post_url}")

        if should_stop():
            log_fn("⚠ 작업 중단됨")
            return {"success": False, "error": "사용자 중단"}

        # base_offset (Chrome #1 재사용)
        base_offset = 0
        if post_url and (task.get("replies") or task.get("scenario") or is_comment_only):
            log_fn("기존 댓글 수 집계 중... (메인 세션)")
            base_offset = await main_session.count_top_comments_at(post_url)
            if base_offset > 0:
                log_fn(f"→ to_index 오프셋 {base_offset} 적용 (이어하기/댓글전용)")

        # ═══════════════════════════════════════
        # STEP 2+: Comment accounts (고전 comments 배열)
        # ═══════════════════════════════════════
        comments = task.get("comments", [])
        for i, comment_data in enumerate(comments):
            if should_stop():
                log_fn("⚠ 작업 중단됨")
                return {"success": False, "error": "사용자 중단"}

            current_step += 1
            log_fn(f"━━━ [{current_step}/{total_steps}] 댓글 {i + 1}/{len(comments)} ━━━")

            await random_delay("between_accounts", delays, stop_event)

            acc = comment_data["account"]

            async def _do_comment(page, _acc=acc, _text=comment_data["text"]):
                ok = await naver_login(page, _acc["id"], _acc["pw"], log_fn)
                if not ok:
                    return {"error": "로그인 실패"}
                await random_delay("after_login", delays, stop_event)
                if should_stop():
                    return {"error": "stopped"}
                await write_comment(page, post_url, _text, log_fn)
                await random_delay("after_comment_submit", delays, stop_event)
                return {}

            r = await _run_with_account_retry(acc, log_fn, stop_event, _do_comment, ip_mode=ip_mode)
            if not r["ok"]:
                if r.get("fatal"):
                    _halt(stop_event, log_fn, f"댓글 {i+1} IP 문제 ({r['error']})")
                    return {"success": False, "error": r["error"]}
                log_fn(f"⚠ 댓글 {i+1} 건너뜀: {r['error']}")
                continue

        # ═══════════════════════════════════════
        # STEP FINAL: Main account - Replies (레거시 경로, 메인 세션 재사용)
        # ═══════════════════════════════════════
        replies = task.get("replies", [])
        if replies:
            if should_stop():
                log_fn("⚠ 작업 중단됨")
                return {"success": False, "error": "사용자 중단"}

            current_step += 1
            log_fn(f"━━━ [{current_step}/{total_steps}] 대댓글 작성 (메인 세션 재사용) ━━━")

            for j, reply_data in enumerate(replies):
                if should_stop():
                    break
                actual_idx = reply_data["to_index"] + base_offset
                log_fn(f"  대댓글 {j + 1}/{len(replies)} (txt idx {reply_data['to_index']} + offset {base_offset} → 페이지 #{actual_idx+1})")
                ok = await main_session.goto_post_and_reply(
                    post_url, actual_idx, reply_data["text"], delays
                )
                if not ok:
                    log_fn(f"⚠ 대댓글 {j+1} 실패")
                # 연속 대댓글 간 자연스러운 텀
                await asyncio.sleep(random.uniform(3, 7))

        # ═══════════════════════════════════════
        # SCENARIO: 2-브라우저 구조 (Chrome #1 = 메인 지속, Chrome #2 = 댓글러 새 세션)
        #
        # - 작성자(ㄴ 작성자) 대댓글: Chrome #1 에서 재사용 → 로그인 1회 → 캡챠 회피
        # - 댓글 / 댓글러 대댓글(ㄴ 댓글N): Chrome #2 에서 매번 새 세션 + 새 프록시
        #
        # to_index 매핑:
        #   target_txt_idx 가 실패한 경우 대댓글 스킵
        #   성공한 경우 base_offset + (앞까지 성공한 comment 수) 로 실제 페이지 인덱스 계산
        # ═══════════════════════════════════════
        scenario = task.get("scenario", [])
        if scenario:
            log_fn(f"━━━ 시나리오 실행 (2-브라우저, {len(scenario)}개 액션) ━━━")

            comment_txt_idx_counter = 0
            comment_success = {}

            try:
                for idx, act in enumerate(scenario, 1):
                    if should_stop():
                        log_fn("⚠ 작업 중단됨")
                        break

                    acc = act.get("account")
                    if not acc:
                        log_fn(f"⚠ action #{idx}: 계정 정보 없음 - 건너뜀")
                        if act.get("action") == "comment":
                            comment_success[comment_txt_idx_counter] = False
                            comment_txt_idx_counter += 1
                        continue

                    log_fn(f"━━━ [{idx}/{len(scenario)}] {act.get('action')} ({acc.get('label', acc.get('id', ''))[:10]}) ━━━")

                    # reply 인 경우 target 검증 + 실제 인덱스 계산
                    if act["action"] == "reply":
                        target_txt_idx = act["to_index"]
                        if not comment_success.get(target_txt_idx, False):
                            log_fn(f"⚠ 대상 댓글(txt idx {target_txt_idx}) 실패 → 대댓글 스킵")
                            continue
                        succeeded_before = sum(
                            1 for k, v in comment_success.items()
                            if k < target_txt_idx and v
                        )
                        actual_idx = base_offset + succeeded_before
                    else:
                        actual_idx = None

                    is_main_reply = act["action"] == "reply" and act.get("is_main")

                    # ── Chrome #1: 작성자 대댓글 (지속 세션 재사용) ──
                    if is_main_reply:
                        log_fn(f"  [메인 세션 재사용] txt idx {act['to_index']} → 페이지 #{actual_idx+1}")
                        ok = await main_session.goto_post_and_reply(
                            post_url, actual_idx, act["text"], delays
                        )
                        if not ok:
                            log_fn(f"❌ 작성자 대댓글 최종 실패 - 다음 액션 계속")
                        # 메인 연속 대댓글 사이 짧은 대기 (너무 빠르지 않게)
                        await asyncio.sleep(random.uniform(3, 7))
                        continue

                    # ── Chrome #2: 댓글 or 댓글러 대댓글 (새 세션) ──
                    if act["action"] == "comment":
                        this_comment_txt_idx = comment_txt_idx_counter
                        comment_txt_idx_counter += 1
                    else:
                        this_comment_txt_idx = None

                    await random_delay("between_accounts", delays, stop_event)

                    async def _do_action(page, _acc=acc, _act=act, _aidx=actual_idx):
                        ok = await naver_login(page, _acc["id"], _acc["pw"], log_fn)
                        if not ok:
                            return {"error": "로그인 실패"}
                        await random_delay("after_login", delays, stop_event)
                        if should_stop():
                            return {"error": "stopped"}

                        if _act["action"] == "comment":
                            result = await write_comment(page, post_url, _act["text"], log_fn)
                            if not result:
                                return {"error": "댓글 작성 실패", "comment_ok": False}
                        elif _act["action"] == "reply":
                            log_fn(f"  (txt idx {_act['to_index']} → 페이지 #{_aidx+1})")
                            result = await write_reply(page, post_url, _aidx, _act["text"], log_fn)
                            if not result:
                                return {"error": "대댓글 작성 실패"}

                        await random_delay("after_comment_submit", delays, stop_event)
                        return {"comment_ok": True}

                    r = await _run_with_account_retry(acc, log_fn, stop_event, _do_action, ip_mode=ip_mode)

                    if act["action"] == "comment":
                        succ = bool(r["ok"]) and bool((r.get("result") or {}).get("comment_ok", False))
                        comment_success[this_comment_txt_idx] = succ
                        # Q3: 댓글 성공 시 2~3초 대기 (다음이 작성자 답글일 수 있어 자연스러운 텀)
                        if succ:
                            await asyncio.sleep(random.uniform(2, 3))

                    if not r["ok"]:
                        if r.get("fatal"):
                            _halt(stop_event, log_fn, f"action #{idx} IP 문제 ({r['error']})")
                            break
                        log_fn(f"⚠ action #{idx} 건너뜀: {r['error']}")

                # 요약
                succ_cnt = sum(1 for v in comment_success.values() if v)
                fail_cnt = sum(1 for v in comment_success.values() if not v)
                log_fn(f"시나리오 댓글 결과: 성공 {succ_cnt} / 실패 {fail_cnt} (총 {len(comment_success)})")
            except Exception as e:
                log_fn(f"⚠ 시나리오 실행 중 예외: {e}")

        log_fn("━━━━━━━━━━━━━━━━━━━━━━━━")
        log_fn("✅ 작업 완료!")
        log_fn(f"글 URL: {post_url}")
        return {"success": True, "post_url": post_url}

    except Exception as e:
        log_fn(f"❌ 작업 오류: {str(e)}")
        return {"success": False, "error": str(e)}
    finally:
        # Chrome #1 메인 세션 정리 (작업 끝 or 예외 발생 시 공통)
        try:
            await main_session.close()
            log_fn("메인 세션 종료")
        except Exception:
            pass


async def run_batch(tasks, log_fn, stop_event=None):
    """여러 task 를 순차 실행."""
    results = []
    total = len(tasks)
    log_fn(f"═════ 배치 시작: 총 {total}개 작업 ═════")

    for i, task in enumerate(tasks, 1):
        if stop_event and stop_event.is_set():
            log_fn("⚠ 배치 중단 요청 — 남은 작업 건너뜀")
            break

        title_preview = (task.get("title") or "")[:30]
        log_fn("")
        log_fn(f"╔═══ [작업 {i}/{total}] {title_preview} ═══╗")

        try:
            result = await run_task(task, log_fn, stop_event)
        except Exception as e:
            log_fn(f"❌ 작업 {i} 예외: {e}")
            result = {"success": False, "error": str(e)}

        results.append({"index": i, "title": title_preview, **result})

        if result.get("success"):
            log_fn(f"✓ 작업 {i}/{total} 완료")
        else:
            log_fn(f"✗ 작업 {i}/{total} 실패: {result.get('error', '')} — 다음 작업 계속")

    ok_count = sum(1 for r in results if r.get("success"))
    log_fn("")
    log_fn(f"═════ 배치 종료: 성공 {ok_count}/{total} ═════")
    return {
        "success": ok_count == total,
        "total": total,
        "succeeded": ok_count,
        "results": results,
    }
