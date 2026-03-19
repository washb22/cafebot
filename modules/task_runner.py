"""Task orchestration engine - sequences the full workflow."""
import asyncio
import random
from playwright.async_api import async_playwright

from modules.browser import new_session
from modules.naver_auth import naver_login
from modules.naver_post import write_post, edit_post
from modules.naver_comment import write_comment, write_reply
from modules.adb_network import toggle_airplane_mode, manual_ip_change, is_device_connected
from config import DEFAULT_DELAYS


async def random_delay(key, delays=None):
    """Wait for a random duration based on delay config."""
    d = (delays or DEFAULT_DELAYS).get(key, (2, 5))
    wait = random.uniform(d[0], d[1])
    await asyncio.sleep(wait)


async def change_ip(log_fn, delays=None):
    """Change IP via ADB or manual method."""
    if is_device_connected():
        await toggle_airplane_mode(log_fn)
    else:
        log_fn("⚠ ADB 장치 미연결 - 수동 IP 변경 모드")
        await manual_ip_change(log_fn)
    await random_delay("airplane_toggle_wait", delays)


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

            await random_delay("after_login", delays)

            if task["mode"] == "new":
                post_url = await write_post(
                    page, task["cafe_url"], task["title"], task["body"],
                    task.get("board_name"), log_fn
                )
                if not post_url:
                    log_fn("❌ 글 작성 실패 - 작업 중단")
                    return {"success": False, "error": "글 작성 실패"}
            else:
                post_url = task["post_url"]
                result = await edit_post(page, post_url, task["title"], task["body"], log_fn)
                if not result:
                    log_fn("❌ 글 수정 실패 - 작업 중단")
                    return {"success": False, "error": "글 수정 실패"}

            await random_delay("after_post_submit", delays)

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

            # IP change
            log_fn("IP 변경 중...")
            await change_ip(log_fn, delays)
            await random_delay("between_accounts", delays)

            acc = comment_data["account"]
            async with new_session() as (ctx, page):
                success = await naver_login(page, acc["id"], acc["pw"], log_fn)
                if not success:
                    log_fn(f"⚠ 댓글 계정 {acc['id'][:3]}*** 로그인 실패 - 건너뜀")
                    continue

                await random_delay("after_login", delays)

                await write_comment(page, post_url, comment_data["text"], log_fn)
                await random_delay("after_comment_submit", delays)

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

            # IP change
            log_fn("IP 변경 중...")
            await change_ip(log_fn, delays)
            await random_delay("between_accounts", delays)

            async with new_session() as (ctx, page):
                success = await naver_login(page, main["id"], main["pw"], log_fn)
                if not success:
                    log_fn("⚠ 메인 계정 대댓글 로그인 실패")
                    return {"success": False, "error": "대댓글 로그인 실패"}

                await random_delay("after_login", delays)

                for j, reply_data in enumerate(replies):
                    if should_stop():
                        break
                    log_fn(f"  대댓글 {j + 1}/{len(replies)} 작성 중...")
                    await write_reply(
                        page, post_url, reply_data["to_index"],
                        reply_data["text"], log_fn
                    )
                    await random_delay("after_comment_submit", delays)

        log_fn("━━━━━━━━━━━━━━━━━━━━━━━━")
        log_fn("✅ 작업 완료!")
        log_fn(f"글 URL: {post_url}")
        return {"success": True, "post_url": post_url}

    except Exception as e:
        log_fn(f"❌ 작업 오류: {str(e)}")
        return {"success": False, "error": str(e)}
