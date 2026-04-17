"""CafeBot Desktop — PyWebView 진입점.

PyInstaller exe 빌드 후 이 파일이 실행됨.
Flask 서버를 백그라운드 스레드로 띄우고, PyWebView 네이티브 창으로 UI 표시.
"""
import os
import sys
import threading
import time

# frozen 빌드 시 Playwright 브라우저 경로 설정 (import 전에)
if getattr(sys, 'frozen', False):
    _base = os.path.dirname(sys.executable)
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', os.path.join(_base, 'browsers'))

import webview
import requests
from app import run_server
from config import FLASK_PORT


def wait_for_server(port, timeout=30):
    """Flask 서버가 뜰 때까지 대기."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"http://127.0.0.1:{port}/api/tasks/status", timeout=1)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def main():
    # Flask 서버 백그라운드 시작
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # 서버 준비 대기
    if not wait_for_server(FLASK_PORT):
        print("서버 시작 실패")
        sys.exit(1)

    # PyWebView 네이티브 창
    window = webview.create_window(
        "CafeBot",
        f"http://127.0.0.1:{FLASK_PORT}",
        width=1400,
        height=900,
        min_size=(1000, 600),
    )

    # EdgeChromium 백엔드 사용 (SSE 지원 필수)
    webview.start(gui='edgechromium')


if __name__ == "__main__":
    main()
