"""Task orchestration engine - sequences the full workflow (proxy 기반)."""
import asyncio
import random
from playwright.async_api import async_playwright

from modules.browser import new_session
from modules.naver_auth import naver_login
from modules.naver_post import write_post, edit_post
from modules.naver_comment import write_comment, write_reply, count_top_comments
from modules.adb_network import interruptible_sleep
from modules.proxy_check import verify_proxy_ip, expected_ip_from_proxy
from config import DEFAULT_DELAYS


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


async def _run_with_account(account, log_fn, stop_event, do_work):
    """계정의 프록시로 세션을 열고 do_work(page) 실행. 프록시 검증 포함.

    do_work: async callable(page) -> any
    Returns: {"ok": bool, "fatal": bool, "error": str or None, "result": any}

    fatal=True 인 경우(배치 전체 중단해야 함):
      - 계정에 proxy 미설정 (IP 미변경 상태 → 보호조치 위험)
      - 프록시 설정됐으나 실제 IP 가 프록시 IP 와 불일치 (프록시 연결 실패)
    """
    proxy = (account.get("proxy") or "").strip()
    expected_ip = expected_ip_from_proxy(proxy)
    acc_tag = f"{account.get('label', account.get('id', '?'))[:10]}"

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
                # 실제 IP 가 다르게 찍힘 = PC IP 노출 위험 → 즉시 중단
                log_fn(f"❌ {acc_tag} IP 불일치 (기대={expected_ip}, 실제={actual}) - 중단")
                return {"ok": False, "fatal": True, "error": "proxy_mismatch", "result": None}
            if status == "unreachable":
                # 프록시 서버 응답 없음 = 요청 자체 실패 = PC IP 노출 없음
                # 이 계정만 스킵하고 다음으로
                log_fn(f"⚠ {acc_tag} 프록시 응답 없음 (기대={expected_ip}) - 이 계정 스킵하고 계속")
                return {"ok": False, "fatal": False, "error": "proxy_unreachable", "result": None}

            if stop_event and stop_event.is_set():
                return {"ok": False, "fatal": False, "error": "stopped", "result": None}

            result = await do_work(page)
            return {"ok": True, "fatal": False, "error": None, "result": result}
    except Exception as e:
        log_fn(f"❌ {acc_tag} 세션 오류: {e}")
        return {"ok": False, "fatal": False, "error": str(e), "result": None}


def _halt(stop_event, log_fn, reason):
    """치명적 IP 문제 발생 시 전체 중단 플래그 설정."""
    log_fn(f"🛑 전체 작업 중단: {reason}")
    if stop_event:
        stop_event.set()


async def _compute_base_offset(main_acc, post_url, log_fn):
    """게시글의 기존 최상위 댓글 수를 세어 반환.
    이어하기 시 to_index 오프셋 계산용. 메인 계정의 프록시로 세션 오픈.
    """
    proxy = (main_acc.get("proxy") or "").strip()
    if not proxy or not post_url:
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

    def should_stop():
        return stop_event and stop_event.is_set()

    is_comment_only = task.get("mode") == "comment_only"

    if is_comment_only:
        total_steps = len(task.get("scenario", [])) or (len(task.get("comments", [])) + (1 if task.get("replies") else 0))
    else:
        total_steps = 2 + len(task.get("comments", [])) + (1 if task.get("replies") else 0)
    current_step = 0

    try:
        # ═══════════════════════════════════════
        # STEP 1: Main account - Write/Edit post
        # ═══════════════════════════════════════
        if is_comment_only:
            post_url = task["post_url"]
            log_fn(f"━━━ 댓글 전용 모드 ━━━")
            log_fn(f"대상 글: {post_url}")
        else:
            current_step += 1
            log_fn(f"━━━ [{current_step}/{total_steps}] 글 작성/수정 ━━━")

            async def _do_post(page):
                success = await naver_login(page, main["id"], main["pw"], log_fn)
                if not success:
                    return {"error": "메인 계정 로그인 실패"}

                await random_delay("after_login", delays, stop_event)

                if task["mode"] == "new":
                    url = await write_post(
                        page, task["cafe_url"], task["title"], task["body"],
                        task.get("board_name"), log_fn,
                        image_map=task.get("image_map"),
                    )
                    if not url:
                        return {"error": "글 작성 실패"}
                    return {"post_url": url}
                else:
                    url = task["post_url"]
                    result = await edit_post(
                        page, url, task["title"], task["body"], log_fn,
                        image_map=task.get("image_map"),
                    )
                    if not result:
                        return {"error": "글 수정 실패"}
                    return {"post_url": url}

            r = await _run_with_account(main, log_fn, stop_event, _do_post)
            if not r["ok"]:
                if r.get("fatal"):
                    _halt(stop_event, log_fn, f"메인 계정 IP 문제 ({r['error']})")
                log_fn(f"❌ 메인 세션 실패: {r['error']} - 작업 중단")
                return {"success": False, "error": r["error"]}
            payload = r["result"] or {}
            if payload.get("error"):
                log_fn(f"❌ {payload['error']}")
                return {"success": False, "error": payload["error"]}
            post_url = payload.get("post_url", "")
            await random_delay("after_post_submit", delays, stop_event)
            log_fn(f"글 URL: {post_url}")

        if should_stop():
            log_fn("⚠ 작업 중단됨")
            return {"success": False, "error": "사용자 중단"}

        # 이어하기/댓글전용 모드 대비: 기존 최상위 댓글 수 카운트 (to_index 오프셋)
        base_offset = 0
        if post_url and (task.get("replies") or task.get("scenario") or is_comment_only):
            log_fn("기존 댓글 수 집계 중...")
            base_offset = await _compute_base_offset(main, post_url, log_fn)
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

            r = await _run_with_account(acc, log_fn, stop_event, _do_comment)
            if not r["ok"]:
                if r.get("fatal"):
                    _halt(stop_event, log_fn, f"댓글 {i+1} IP 문제 ({r['error']})")
                    return {"success": False, "error": r["error"]}
                log_fn(f"⚠ 댓글 {i+1} 건너뜀: {r['error']}")
                continue

        # ═══════════════════════════════════════
        # STEP FINAL: Main account - Replies
        # ═══════════════════════════════════════
        replies = task.get("replies", [])
        if replies:
            if should_stop():
                log_fn("⚠ 작업 중단됨")
                return {"success": False, "error": "사용자 중단"}

            current_step += 1
            log_fn(f"━━━ [{current_step}/{total_steps}] 대댓글 작성 ━━━")

            await random_delay("between_accounts", delays, stop_event)

            async def _do_replies(page):
                ok = await naver_login(page, main["id"], main["pw"], log_fn)
                if not ok:
                    return {"error": "대댓글 로그인 실패"}
                await random_delay("after_login", delays, stop_event)

                for j, reply_data in enumerate(replies):
                    if should_stop():
                        break
                    actual_idx = reply_data["to_index"] + base_offset
                    log_fn(f"  대댓글 {j + 1}/{len(replies)} 작성 중 (txt idx {reply_data['to_index']} + offset {base_offset} → 페이지 #{actual_idx+1})...")
                    await write_reply(
                        page, post_url, actual_idx,
                        reply_data["text"], log_fn
                    )
                    await random_delay("after_comment_submit", delays, stop_event)
                return {}

            r = await _run_with_account(main, log_fn, stop_event, _do_replies)
            if not r["ok"]:
                if r.get("fatal"):
                    _halt(stop_event, log_fn, f"대댓글 IP 문제 ({r['error']})")
                    return {"success": False, "error": r["error"]}
                log_fn(f"⚠ 대댓글 작업 실패: {r['error']}")

        # ═══════════════════════════════════════
        # SCENARIO: 시나리오 모드 (txt 파일 기반)
        # ═══════════════════════════════════════
        scenario = task.get("scenario", [])
        if scenario:
            log_fn(f"━━━ 시나리오 실행 ({len(scenario)}개 액션) ━━━")
            for idx, act in enumerate(scenario, 1):
                if should_stop():
                    log_fn("⚠ 작업 중단됨")
                    return {"success": False, "error": "사용자 중단"}

                acc = act.get("account")
                if not acc:
                    log_fn(f"⚠ action #{idx}: 계정 정보 없음 - 건너뜀")
                    continue

                log_fn(f"━━━ [{idx}/{len(scenario)}] {act.get('action')} ({acc.get('label', acc.get('id', ''))[:10]}) ━━━")

                await random_delay("between_accounts", delays, stop_event)

                async def _do_action(page, _acc=acc, _act=act):
                    ok = await naver_login(page, _acc["id"], _acc["pw"], log_fn)
                    if not ok:
                        return {"error": "로그인 실패"}
                    await random_delay("after_login", delays, stop_event)
                    if should_stop():
                        return {"error": "stopped"}

                    if _act["action"] == "comment":
                        await write_comment(page, post_url, _act["text"], log_fn)
                    elif _act["action"] == "reply":
                        actual_idx = _act["to_index"] + base_offset
                        log_fn(f"  (txt idx {_act['to_index']} + offset {base_offset} → 페이지 #{actual_idx+1})")
                        await write_reply(page, post_url, actual_idx, _act["text"], log_fn)
                    else:
                        return {"error": f"알 수 없는 action: {_act['action']}"}

                    await random_delay("after_comment_submit", delays, stop_event)
                    return {}

                r = await _run_with_account(acc, log_fn, stop_event, _do_action)
                if not r["ok"]:
                    if r.get("fatal"):
                        _halt(stop_event, log_fn, f"action #{idx} IP 문제 ({r['error']})")
                        return {"success": False, "error": r["error"]}
                    log_fn(f"⚠ action #{idx} 건너뜀: {r['error']}")

        log_fn("━━━━━━━━━━━━━━━━━━━━━━━━")
        log_fn("✅ 작업 완료!")
        log_fn(f"글 URL: {post_url}")
        return {"success": True, "post_url": post_url}

    except Exception as e:
        log_fn(f"❌ 작업 오류: {str(e)}")
        return {"success": False, "error": str(e)}


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
