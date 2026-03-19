"""ADB airplane mode toggle for IP rotation."""
import subprocess
import asyncio
import requests
import time


def run_adb(cmd: str) -> str:
    """Run an ADB command and return output."""
    result = subprocess.run(
        f"adb {cmd}",
        shell=True, capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip()


def is_device_connected() -> bool:
    """Check if an Android device is connected via ADB."""
    output = run_adb("devices")
    lines = [l for l in output.split("\n") if "\tdevice" in l]
    return len(lines) > 0


def get_current_ip() -> str:
    """Get current external IP address."""
    try:
        resp = requests.get("https://api.ipify.org", timeout=10)
        return resp.text.strip()
    except Exception:
        try:
            resp = requests.get("https://ifconfig.me/ip", timeout=10)
            return resp.text.strip()
        except Exception:
            return ""


async def toggle_airplane_mode(log_fn=None):
    """Toggle airplane mode ON then OFF and return new IP."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    old_ip = get_current_ip()
    log(f"현재 IP: {old_ip}")

    # Airplane ON
    log("비행기 모드 ON...")
    run_adb("shell cmd connectivity airplane-mode enable")
    await asyncio.sleep(3)

    # Airplane OFF
    log("비행기 모드 OFF...")
    run_adb("shell cmd connectivity airplane-mode disable")

    # Wait for IP change
    log("IP 변경 대기 중...")
    for attempt in range(30):
        await asyncio.sleep(2)
        new_ip = get_current_ip()
        if new_ip and new_ip != old_ip:
            log(f"IP 변경 완료: {old_ip} → {new_ip}")
            return new_ip
        if attempt % 5 == 4:
            log(f"  아직 대기 중... ({attempt + 1}회 시도)")

    new_ip = get_current_ip()
    if new_ip and new_ip != old_ip:
        log(f"IP 변경 완료: {old_ip} → {new_ip}")
        return new_ip

    log(f"⚠ IP 변경 실패 (현재: {new_ip or '없음'}). 수동 확인 필요")
    return new_ip or old_ip


async def manual_ip_change(log_fn=None):
    """Prompt-based manual IP change (fallback if ADB unavailable)."""
    def log(msg):
        if log_fn:
            log_fn(msg)

    old_ip = get_current_ip()
    log(f"현재 IP: {old_ip}")
    log("⚠ 비행기 모드를 수동으로 껐다 켜주세요!")

    for attempt in range(60):
        await asyncio.sleep(2)
        new_ip = get_current_ip()
        if new_ip and new_ip != old_ip:
            log(f"IP 변경 확인: {old_ip} → {new_ip}")
            return new_ip

    log("⚠ IP 변경 감지 실패")
    return get_current_ip() or old_ip
