"""라이선스 인증 모듈 — HWID 락 + 기간제 + 서버 인증."""
import os
import sys
import json
import hashlib
import hmac
import time
import subprocess
import base64
import requests

from config import DATA_DIR

LICENSE_FILE = os.path.join(DATA_DIR, "license.dat")
LICENSE_SERVER = "https://cafebot-license.onrender.com"
HMAC_SECRET = b"CafeBot_LicenseKey_2026_v1_Secret"
CHECK_INTERVAL = 3600  # 1시간마다 서버 인증 시도


def _wmic(query):
    """wmic 명령어 실행 결과 반환."""
    try:
        r = subprocess.run(
            query, shell=True, capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
        )
        lines = [l.strip() for l in r.stdout.strip().split('\n') if l.strip()]
        return lines[-1] if len(lines) > 1 else lines[0] if lines else ""
    except Exception:
        return ""


def get_hwid():
    """PC 고유 지문 생성 (마더보드 + CPU + 디스크 시리얼 해시)."""
    board = _wmic("wmic baseboard get serialnumber")
    cpu = _wmic("wmic cpu get processorid")
    disk = _wmic("wmic diskdrive get serialnumber")
    raw = f"{board}|{cpu}|{disk}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _sign_token(data_dict):
    """토큰 데이터에 HMAC 서명 생성."""
    payload = json.dumps(data_dict, sort_keys=True).encode()
    sig = hmac.new(HMAC_SECRET, payload, hashlib.sha256).hexdigest()
    return sig


def _encode_token(data_dict, signature):
    """토큰 데이터 + 서명을 base64로 인코딩."""
    obj = {"data": data_dict, "sig": signature}
    return base64.b64encode(json.dumps(obj).encode()).decode()


def _decode_token(token_str):
    """base64 토큰을 디코딩하여 data, sig 반환."""
    try:
        obj = json.loads(base64.b64decode(token_str))
        return obj["data"], obj["sig"]
    except Exception:
        return None, None


def _save_token(token_str):
    """토큰을 로컬에 저장."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
        f.write(token_str)


def _load_token():
    """로컬 토큰 읽기."""
    if not os.path.exists(LICENSE_FILE):
        return None
    with open(LICENSE_FILE, 'r', encoding='utf-8') as f:
        return f.read().strip()


def activate(license_key):
    """라이선스 키로 활성화. 서버에 HWID 등록 후 토큰 저장.
    Returns: (success: bool, message: str, days_remaining: int)
    """
    hwid = get_hwid()
    try:
        resp = requests.post(
            f"{LICENSE_SERVER}/api/license/activate",
            json={"license_key": license_key, "hwid": hwid},
            timeout=15,
        )
        data = resp.json()
        if resp.status_code == 200 and data.get("success"):
            token_data = {
                "hwid": hwid,
                "license_key": license_key,
                "expiry": data["expiry"],
                "last_check": int(time.time()),
            }
            sig = _sign_token(token_data)
            _save_token(_encode_token(token_data, sig))
            days = max(0, (data["expiry"] - int(time.time())) // 86400)
            return True, data.get("message", "활성화 완료"), days
        else:
            return False, data.get("error", "활성화 실패"), 0
    except requests.ConnectionError:
        return False, "서버 연결 실패. 인터넷을 확인해주세요.", 0
    except Exception as e:
        return False, f"활성화 오류: {e}", 0


def verify():
    """로컬 토큰 검증. 필요시 서버 재인증.
    Returns: (valid: bool, days_remaining: int, error: str)
    """
    token_str = _load_token()
    if not token_str:
        return False, 0, "라이선스가 등록되지 않았습니다."

    data, sig = _decode_token(token_str)
    if not data:
        return False, 0, "라이선스 파일이 손상되었습니다."

    expected_sig = _sign_token(data)
    if not hmac.compare_digest(sig, expected_sig):
        return False, 0, "라이선스 파일이 변조되었습니다."

    hwid = get_hwid()
    if data.get("hwid") != hwid:
        return False, 0, "이 PC에 등록된 라이선스가 아닙니다."

    now = int(time.time())
    expiry = data.get("expiry", 0)
    if now > expiry:
        return False, 0, "라이선스가 만료되었습니다."

    days = max(0, (expiry - now) // 86400)

    # 1시간 경과 시 서버 재인증 시도 (실패해도 만료일 전이면 사용 가능)
    last_check = data.get("last_check", 0)
    if now - last_check > CHECK_INTERVAL:
        try:
            resp = requests.post(
                f"{LICENSE_SERVER}/api/license/verify",
                json={"hwid": hwid, "license_key": data.get("license_key", "")},
                timeout=10,
            )
            srv = resp.json()
            if srv.get("valid"):
                data["last_check"] = now
                data["expiry"] = srv.get("expiry", expiry)
                new_sig = _sign_token(data)
                _save_token(_encode_token(data, new_sig))
                days = max(0, (data["expiry"] - now) // 86400)
            else:
                return False, 0, srv.get("error", "서버 인증 실패")
        except requests.ConnectionError:
            pass  # 오프라인이어도 만료일 전이면 계속 사용

    return True, days, ""


def get_status():
    """현재 라이선스 상태 반환 (UI용)."""
    valid, days, error = verify()
    hwid = get_hwid()
    return {
        "valid": valid,
        "days_remaining": days,
        "error": error,
        "hwid": hwid,
    }
