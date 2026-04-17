"""Task orchestration engine - sequences the full workflow."""
import asyncio
import random
from playwright.async_api import async_playwright

from modules.browser import new_session
from modules.naver_auth import naver_login
from modules.naver_post import write_post, edit_post
from modules.naver_comment import write_comment, write_reply
from modules.adb_network import toggle_airplane_mode, manual_ip_change, is_device_connected, interruptible_sleep
from config import DEFAULT_DELAYS


async def random_delay(key, delays=None, stop_event=None):
    """Wait for a random duration based on delay config. 중단 가능."""
    d = (delays or DEFAULT_DELAYS).get(key, (2, 5))
    wait = random.uniform(d[0], d[1])
    await interruptible_sleep(wait, stop_event)


async def change_ip(log_fn, delays=None, stop_event=None):
    """Change IP via ADB or manual method. 중단 가능."""
    if is_device_connected():
        await toggle_airplane_mode(log_fn, stop_event=stop_event)
    else:
        log_fn("⚠ ADB 장치 미연결 - 수동 IP 변경 모드")
        await manual_ip_change(log_fn, stop_event=stop_event)
    await random_delay("airplane_toggle_wait", delays, stop_event)


async def run_task(task, log_fn, stop_event=None):
    """Execute the full posting + commenting workflow.

    task = {
        "mode": "new" or "edit",
        "cafe_url": "cafeurl",
        "post_url": "..." (for edit mode),
        "board_name": "게시판명" (optional),
        "title": "글 제목",
        "body": "글 본문",
        "main_account": {"id": "...", "pw": "..."},
        "comments": [
            {"account": {"id": "...", "pw": "..."}, "text": "댓글 내용"},
            ...
        ],
        "replies": [
            {"to_index": 0, "text": "대댓글 내용"},
            ...
        ],
        "delays": {...} (optional override)
    }
    """
    delays = task.get("delays", DEFAULT_DELAYS)
    main = task["main_account"]
    post_url = task.get("post_url", "")

    def should_stop():
        return stop_event and stop_event.is_set()

    total_steps = 2 + len(task.get("comments", [])) + (1 if task.get("replies") else 0)
    current_step = 0

    try:
        # ═══════════════════════════════════════
        # STEP 1: Main account - Write/Edit post
        # ═══════════════════════════════════════
        current_step += 1
        log_fn(f"━━━ [{current_step}/{total_steps}] 글 작성/수정 ━━━")

        async with new_session() as (ctx, page):
            success = await naver_login(page, main["id"], main["pw"], log_fn)
            if not success:
                log_fn("❌ 메인 계정 로그인 실패 - 작업 중단")
                return {"success": False, "error": "메인 계정 로그인 실패"}

            await random_delay("after_login", delays, stop_event)

            if task["mode"] == "new":
                post_url = await write_post(
                    page, task["cafe_url"], task["title"], task["body"],
                    task.get("board_name"), log_fn,
                    image_map=task.get("image_map"),
                )
                if not post_url:
                    log_fn("❌ 글 작성 실패 - 작업 중단")
                    return {"success": False, "error": "글 작성 실패"}
            else:
                post_url = task["post_url"]
                result = await edit_post(
                    page, post_url, task["title"], task["body"], log_fn,
                    image_map=task.get("image_map"),
                )
                if not result:
                    log_fn("❌ 글 수정 실패 - 작업 중단")
                    return {"success": False, "error": "글 수정 실패"}

            await random_delay("after_post_submit", delays, stop_event)

        log_fn(f"글 URL: {post_url}")

        if should_stop():
            log_fn("⚠ 작업 중단됨")
            return {"success": False, "error": "사용자 중단"}

        # ═══════════════════════════════════════
        # STEP 2+: Comment accounts
        # ═══════════════════════════════════════
        comments = task.get("comments", [])
        for i, comment_data in enumerate(comments):
            if should_stop():
                log_fn("⚠ 작업 중단됨")
                return {"success": False, "error": "사용자 중단"}

            current_step += 1
            log_fn(f"━━━ [{current_step}/{total_steps}] 댓글 {i + 1}/{len(comments)} ━━━")

            log_fn("IP 변경 중...")
            await change_ip(log_fn, delays, stop_event)
            if should_stop():
                log_fn("⚠ 작업 중단됨")
                return {"success": False, "error": "사용자 중단"}
            await random_delay("between_accounts", delays, stop_event)

            acc = comment_data["account"]
            async with new_session() as (ctx, page):
                success = await naver_login(page, acc["id"], acc["pw"], log_fn)
                if not success:
                    log_fn(f"⚠ 댓글 계정 {acc['id'][:3]}*** 로그인 실패 - 건너뜀")
                    continue

                await random_delay("after_login", delays, stop_event)
                if should_stop():
                    log_fn("⚠ 작업 중단됨")
                    return {"success": False, "error": "사용자 중단"}

                await write_comment(page, post_url, comment_data["text"], log_fn)
                await random_delay("after_comment_submit", delays, stop_event)

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

            log_fn("IP 변경 중...")
            await change_ip(log_fn, delays, stop_event)
            if should_stop():
                log_fn("⚠ 작업 중단됨")
                return {"success": False, "error": "사용자 중단"}
            await random_delay("between_accounts", delays, stop_event)

            async with new_session() as (ctx, page):
                success = await naver_login(page, main["id"], main["pw"], log_fn)
                if not success:
                    log_fn("⚠ 메인 계정 대댓글 로그인 실패")
                    return {"success": False, "error": "대댓글 로그인 실패"}

                await random_delay("after_login", delays, stop_event)

                for j, reply_data in enumerate(replies):
                    if should_stop():
                        break
                    log_fn(f"  대댓글 {j + 1}/{len(replies)} 작성 중...")
                    await write_reply(
                        page, post_url, reply_data["to_index"],
                        reply_data["text"], log_fn
                    )
                    await random_delay("after_comment_submit", delays, stop_event)

        # ═══════════════════════════════════════
        # SCENARIO: 시나리오 모드 (txt 파일 기반)
        # actions 리스트를 순서대로 실행 (댓글/대댓글 혼합)
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

                log_fn("IP 변경 중...")
                await change_ip(log_fn, delays, stop_event)
                if should_stop():
                    log_fn("⚠ 작업 중단됨")
                    return {"success": False, "error": "사용자 중단"}
                await random_delay("between_accounts", delays, stop_event)

                try:
                    async with new_session() as (ctx, page):
                        ok = await naver_login(page, acc["id"], acc["pw"], log_fn)
                        if not ok:
                            log_fn(f"⚠ 로그인 실패 - action #{idx} 건너뜀")
                            continue
                        await random_delay("after_login", delays, stop_event)
                        if should_stop():
                            log_fn("⚠ 작업 중단됨")
                            return {"success": False, "error": "사용자 중단"}

                        if act["action"] == "comment":
                            await write_comment(page, post_url, act["text"], log_fn)
                        elif act["action"] == "reply":
                            await write_reply(page, post_url, act["to_index"], act["text"], log_fn)
                        else:
                            log_fn(f"⚠ 알 수 없는 action: {act['action']}")

                        await random_delay("after_comment_submit", delays, stop_event)
                except Exception as e:
                    log_fn(f"⚠ action #{idx} 오류 - 계속 진행: {e}")

        log_fn("━━━━━━━━━━━━━━━━━━━━━━━━")
        log_fn("✅ 작업 완료!")
        log_fn(f"글 URL: {post_url}")
        return {"success": True, "post_url": post_url}

    except Exception as e:
        log_fn(f"❌ 작업 오류: {str(e)}")
        return {"success": False, "error": str(e)}


async def run_batch(tasks, log_fn, stop_event=None):
    """여러 task 를 순차 실행.

    각 task 는 run_task 와 동일한 스키마.
    한 작업 실패해도 다음 작업 계속 진행 (전체 중단은 stop_event 로만).
    """
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
