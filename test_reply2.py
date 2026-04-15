"""답글 textarea 구조 상세 덤프 (클릭 전/후)"""
import asyncio
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

from modules.browser import new_session
from modules.naver_auth import naver_login

DEBUG_DIR = os.path.join(os.path.dirname(__file__), "test_debug")
with open(os.path.join(DEBUG_DIR, "post_url.txt"), 'r', encoding='utf-8') as f:
    POST_URL = f.read().strip()
ID = "kyqwgdvdfuz"; PW = "plSubx0nbK"


def log(msg):
    print(f"[{msg}]", flush=True)


async def dump_textareas(page, label):
    log(f"=== {label} ===")
    for i, t in enumerate([page] + list(page.frames)):
        try:
            data = await t.evaluate("""
                () => Array.from(document.querySelectorAll('textarea')).map(el => {
                    const r = el.getBoundingClientRect();
                    return {
                        placeholder: el.placeholder || '',
                        class: (el.className||'').toString().substring(0,80),
                        parentClass: (el.parentElement?.className||'').toString().substring(0,80),
                        ancestorClasses: (function(){
                            let cur = el.parentElement;
                            const out = [];
                            for(let j=0;j<5 && cur;j++){out.push((cur.className||'').toString().substring(0,60));cur=cur.parentElement;}
                            return out;
                        })(),
                        w: r.width, h: r.height, x: r.x, y: r.y
                    };
                })
            """)
            if data:
                log(f"  [{i}]:")
                for d in data:
                    log(f"    {d}")
        except Exception:
            pass


async def main():
    async with new_session(headless=False) as (ctx, page):
        page.on("dialog", lambda d: asyncio.create_task(d.dismiss()))
        await naver_login(page, ID, PW, log_fn=log)
        await page.goto(POST_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(5)
        for _ in range(3):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            for f in page.frames:
                try:
                    await f.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except Exception:
                    pass
            await asyncio.sleep(1.5)

        await dump_textareas(page, "BEFORE 답글쓰기 클릭")

        # 첫 댓글 답글쓰기 클릭
        for t in [page] + list(page.frames):
            try:
                els = await t.query_selector_all('li.CommentItem a.comment_info_button')
                for el in els:
                    txt = (await el.text_content() or '').strip()
                    if '답글쓰기' in txt:
                        log(f"답글쓰기 버튼 클릭: text={txt}")
                        await el.click()
                        await asyncio.sleep(2)
                        break
                break
            except Exception:
                pass

        await dump_textareas(page, "AFTER 답글쓰기 클릭")
        await page.screenshot(path=os.path.join(DEBUG_DIR, "after_reply_click.png"), full_page=True)

        # 답글 모드 표시 요소 찾기
        log("=== 답글 모드 표시 탐색 ===")
        for i, t in enumerate([page] + list(page.frames)):
            try:
                data = await t.evaluate("""
                    () => {
                        // CommentWriter 관련 요소의 현재 클래스 상태
                        const writer = document.querySelector('.CommentWriter');
                        const box = document.querySelector('.CommentBox');
                        const out = {};
                        if (writer) {
                            out.writer_class = (writer.className||'').toString();
                            out.writer_innerHTML_snippet = writer.innerHTML.substring(0, 500);
                        }
                        if (box) {
                            out.box_class = (box.className||'').toString();
                        }
                        // reply 관련 모든 요소
                        out.reply_elements = Array.from(document.querySelectorAll('[class*="reply"], [class*="Reply"]')).slice(0,5).map(el => ({
                            tag: el.tagName, class: (el.className||'').toString().substring(0,100),
                            text: (el.textContent||'').trim().substring(0,40)
                        }));
                        return out;
                    }
                """)
                if data:
                    log(f"  [{i}]: {data}")
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
