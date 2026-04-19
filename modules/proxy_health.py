"""프록시 헬스체크 — 모든 계정의 프록시가 살아있는지 빠르게 확인.
네이버 접근 없이 api.ipify.org 만 호출해 응답/일치 여부 체크.
"""
import asyncio
import time
from playwright.async_api import async_playwright

from modules.browser import _normalize_proxy
from modules.proxy_check import expected_ip_from_proxy


CHECK_URL = "https://api.ipify.org"
TIMEOUT_MS = 12000


async def _check_one(pw, account, concurrency_sem):
    """계정 하나의 프록시 테스트. 결과 dict 반환."""
    proxy_str = (account.get("proxy") or "").strip()
    label = account.get("label", account.get("id", ""))
    acc_id = account.get("id", "")
    result = {
        "label": label,
        "id": acc_id,
        "proxy": proxy_str,
        "expected": "",
        "actual": "",
        "latency_ms": None,
        "status": "no_proxy",  # no_proxy / ok / mismatch / unreachable / error
        "error": "",
    }

    if not proxy_str:
        return result

    proxy_cfg = _normalize_proxy(proxy_str)
    if not proxy_cfg:
        result["status"] = "error"
        result["error"] = "형식 파싱 실패"
        return result

    expected = expected_ip_from_proxy(proxy_str) or ""
    result["expected"] = expected

    async with concurrency_sem:
        browser = None
        ctx = None
        try:
            t0 = time.monotonic()
            browser = await pw.chromium.launch(
                headless=True,
                proxy=proxy_cfg,
                args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
            )
            ctx = await browser.new_context(ignore_https_errors=True)
            page = await ctx.new_page()
            await page.goto(CHECK_URL, timeout=TIMEOUT_MS, wait_until="domcontentloaded")
            text = (await page.inner_text("body")).strip().split()[0] if True else ""
            latency = int((time.monotonic() - t0) * 1000)
            result["actual"] = text
            result["latency_ms"] = latency
            if text.count(".") == 3 and all(p.isdigit() for p in text.split(".")):
                if text == expected:
                    result["status"] = "ok"
                else:
                    result["status"] = "mismatch"
            else:
                result["status"] = "unreachable"
                result["error"] = f"이상한 응답: {text[:40]}"
        except Exception as e:
            msg = str(e).split("\n")[0][:120]
            result["status"] = "unreachable"
            result["error"] = msg
        finally:
            try:
                if ctx:
                    await ctx.close()
            except Exception:
                pass
            try:
                if browser:
                    await browser.close()
            except Exception:
                pass

    return result


async def check_all_proxies(accounts, concurrency=5, log_fn=None):
    """전체 계정 프록시 헬스체크.

    accounts: {"mains": [...], "commenters": [...]}
    concurrency: 동시 체크 수 (기본 5)
    """
    def log(msg):
        if log_fn:
            log_fn(msg)

    sem = asyncio.Semaphore(concurrency)
    results_main = []
    results_comm = []

    async with async_playwright() as pw:
        tasks_main = [_check_one(pw, m, sem) for m in accounts.get("mains", [])]
        tasks_comm = [_check_one(pw, c, sem) for c in accounts.get("commenters", [])]

        all_results = await asyncio.gather(*(tasks_main + tasks_comm))
        for i, r in enumerate(all_results):
            if i < len(tasks_main):
                results_main.append(r)
            else:
                results_comm.append(r)

    return {"mains": results_main, "commenters": results_comm}
