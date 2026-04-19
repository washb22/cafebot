"""프록시 수동 테스트 스크립트.
지정한 프록시로 브라우저를 열어 실제 IP를 눈으로 확인.

사용: python test_proxy.py 125.7.181.170:15648
"""
import asyncio
import sys
from playwright.async_api import async_playwright
from modules.browser import _normalize_proxy


async def main():
    proxy_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if not proxy_arg:
        print("사용법: python test_proxy.py <host:port>")
        print("예:    python test_proxy.py 125.7.181.170:15648")
        return

    proxy_cfg = _normalize_proxy(proxy_arg)
    print(f"프록시: {proxy_cfg}")

    async with async_playwright() as pw:
        # 프록시 없이 한 번
        b1 = await pw.chromium.launch(headless=False)
        p1 = await (await b1.new_context()).new_page()
        await p1.goto("https://api.ipify.org")
        pc_ip = (await p1.inner_text("body")).strip()
        print(f"PC 직접 IP    : {pc_ip}")

        # 프록시 통해서 한 번
        b2 = await pw.chromium.launch(headless=False, proxy=proxy_cfg)
        p2 = await (await b2.new_context()).new_page()
        await p2.goto("https://api.ipify.org")
        proxy_ip = (await p2.inner_text("body")).strip()
        print(f"프록시 경유 IP: {proxy_ip}")

        # 네이버도 열어봄 (시각 확인용)
        await p2.goto("https://whatismyipaddress.com/")

        print()
        print(f"기대 IP: {proxy_arg.split(':')[0]}")
        print(f"실제 IP: {proxy_ip}")
        print(f"일치: {'✓' if proxy_ip == proxy_arg.split(':')[0] else '✗ 불일치!'}")
        print()
        print("브라우저 2개 열려있음. 확인 후 Enter 누르면 종료.")
        input()

        await b1.close()
        await b2.close()


if __name__ == "__main__":
    asyncio.run(main())
