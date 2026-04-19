"""프록시 연결 검증 유틸리티.

Playwright 브라우저가 실제로 프록시 IP로 나가는지 확인한다.
외부 IP 확인 서비스 여러 개를 시도해 안정성 확보.
"""
import asyncio


IP_CHECK_URLS = [
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://ipinfo.io/ip",
]


def expected_ip_from_proxy(proxy_str):
    """'host:port' 또는 'host:port:user:pass' 에서 host(IP) 추출."""
    if not proxy_str:
        return None
    s = str(proxy_str).strip()
    if "://" in s:
        s = s.split("://", 1)[1]
    return s.split(":", 1)[0] if s else None


async def verify_proxy_ip(page, expected_ip, log_fn=None, timeout_ms=15000, retries=2):
    """페이지로 외부 IP 확인 후 expected_ip 와 비교.

    Returns: (status, actual_ip)
        status: "ok"          - 기대 IP 와 일치
                "mismatch"    - 응답은 받았지만 다른 IP (위험)
                "unreachable" - 모든 IP 확인 서비스가 응답 안 함 (프록시 다운/터널실패)
        actual_ip: 실제로 감지된 IP 또는 None

    retries: mismatch 가 아닌 unreachable 일 때 전체 재시도 횟수.
             mismatch 는 재시도 무의미 (실제 IP 가 찍힌 상태).
    """
    import asyncio as _aio

    def log(msg):
        if log_fn:
            log_fn(msg)

    attempts = max(1, retries + 1)
    for attempt in range(1, attempts + 1):
        last_err = None
        for url in IP_CHECK_URLS:
            try:
                await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                text = (await page.inner_text("body")).strip().split()[0]
                if text.count(".") == 3 and all(p.isdigit() for p in text.split(".")):
                    if expected_ip and text == expected_ip:
                        log(f"✓ 프록시 IP 확인: {text}" + (f" (재시도 {attempt-1}회)" if attempt > 1 else ""))
                        return "ok", text
                    log(f"⚠ 프록시 IP 불일치: 기대={expected_ip}, 실제={text}")
                    return "mismatch", text  # 재시도 의미없음 - 실제 IP 가 찍힘
            except Exception as e:
                last_err = e
                continue

        if attempt < attempts:
            log(f"⚠ IP 확인 실패 ({attempt}/{attempts}회): {last_err} — 3초 후 재시도")
            await _aio.sleep(3)
        else:
            log(f"⚠ IP 확인 실패 ({attempt}/{attempts}회 최종): {last_err}")
    return "unreachable", None
