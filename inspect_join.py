"""카페 가입 폼 필드 검사용 일회성 스크립트"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from modules.browser import new_session
from modules.naver_auth import naver_login

CAFE_URL = "https://cafe.naver.com/o2note"
ID = "kyqwgdvdfuz"
PW = "plSubx0nbK"
SCREENSHOT = os.path.join(os.path.dirname(__file__), "join_form.png")


def log(msg):
    print(msg)


async def main():
    async with new_session(headless=False) as (ctx, page):
        ok = await naver_login(page, ID, PW, log_fn=log)
        if not ok:
            print("로그인 실패, 종료")
            return

        log("카페 이동")
        await page.goto(CAFE_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        # 가입신청/가입 버튼 탐색
        candidates = [
            'a:has-text("가입신청")',
            'a:has-text("가입하기")',
            'button:has-text("가입신청")',
            'button:has-text("가입하기")',
            'a[href*="CafeJoinForm"]',
            'a[href*="join"]',
        ]
        join_btn = None
        for sel in candidates:
            try:
                el = await page.query_selector(sel)
                if el:
                    join_btn = (sel, el)
                    break
            except Exception:
                pass

        # iframe 내부에도 있을 수 있음
        if not join_btn:
            for frame in page.frames:
                for sel in candidates:
                    try:
                        el = await frame.query_selector(sel)
                        if el:
                            join_btn = (sel, el, frame)
                            break
                    except Exception:
                        pass
                if join_btn:
                    break

        if not join_btn:
            log("가입 버튼 못 찾음 — 전체 페이지 스크린샷만 저장")
            await page.screenshot(path=SCREENSHOT, full_page=True)
            log(f"스크린샷: {SCREENSHOT}")
            return

        log(f"가입 버튼 발견: {join_btn[0]}")
        await join_btn[1].click()
        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception as e:
            log(f"load state 대기 타임아웃(무시): {e}")

        # 현재 URL 및 HTML 구조 확인
        log(f"현재 URL: {page.url}")

        # 입력 필드 정보 수집
        form_info = await page.evaluate("""
            () => {
                const frames = [document];
                for (const f of document.querySelectorAll('iframe')) {
                    try { if (f.contentDocument) frames.push(f.contentDocument); } catch(e){}
                }
                const out = [];
                for (const doc of frames) {
                    const inputs = doc.querySelectorAll('input, textarea, select');
                    for (const el of inputs) {
                        out.push({
                            tag: el.tagName,
                            type: el.type || '',
                            name: el.name || '',
                            id: el.id || '',
                            placeholder: el.placeholder || '',
                            required: el.required || false,
                            label: (el.labels && el.labels[0]) ? el.labels[0].textContent.trim() : ''
                        });
                    }
                }
                return out;
            }
        """)
        log("입력 필드 목록:")
        for f in form_info:
            log(f"  {f}")

        await page.screenshot(path=SCREENSHOT, full_page=True)
        log(f"스크린샷 저장: {SCREENSHOT}")
        await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
