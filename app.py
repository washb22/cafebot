"""CafeBot - Naver Cafe Automation Flask App"""
import os
import sys
import json
import re
import asyncio
import threading
import time
from queue import Queue

from flask import Flask, request, jsonify, render_template, Response
from werkzeug.utils import secure_filename
from config import FLASK_PORT, ACCOUNTS_FILE, DATA_DIR

# Ensure data + uploads dir
os.makedirs(DATA_DIR, exist_ok=True)
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)

# ── State ──
log_queue = Queue()
task_running = False
stop_event = threading.Event()


# ── Account management ──

def load_accounts():
    """accounts.json 로드 + 구버전 schema 자동 마이그레이션.
    구: {"main": {...} or null, "commenters": [...]}
    신: {"mains": [{id, pw, label="글 1"}, ...], "commenters": [...]}
    구 main 필드는 읽을 때 mains[0] 로 흡수되고, 저장할 때 함께 기록(호환).
    """
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"mains": [], "commenters": []}

    # 마이그레이션: main 단수 → mains 배열
    if "mains" not in data:
        data["mains"] = []
    if data.get("main"):
        m = data["main"]
        # 이미 mains 에 같은 id 있으면 스킵
        if not any(x.get("id") == m.get("id") for x in data["mains"]):
            data["mains"].insert(0, {
                "id": m["id"],
                "pw": m["pw"],
                "label": m.get("label") or f"글 {len(data['mains']) + 1}",
            })
    # main 필드 제거 (신 schema)
    data.pop("main", None)
    if "commenters" not in data:
        data["commenters"] = []
    return data


def save_accounts(data):
    # main 필드가 올라오면 mains[0] 로 변환
    if "mains" not in data:
        data["mains"] = []
    if data.get("main"):
        m = data["main"]
        if not any(x.get("id") == m.get("id") for x in data["mains"]):
            data["mains"].insert(0, {
                "id": m["id"],
                "pw": m["pw"],
                "label": m.get("label") or "글 1",
            })
        data.pop("main", None)
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _resolve_main(accounts, main_id=None):
    """mains 배열에서 main_id 로 계정 선택. 미지정 시 첫 번째."""
    mains = accounts.get("mains", [])
    if not mains:
        return None
    if main_id:
        for m in mains:
            if m.get("id") == main_id:
                return m
        return None  # main_id 지정됐는데 없으면 실패
    return mains[0]


# ── Routes ──

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/accounts", methods=["GET"])
def get_accounts():
    return jsonify(load_accounts())


@app.route("/api/accounts", methods=["POST"])
def update_accounts():
    data = request.json
    save_accounts(data)
    return jsonify({"success": True})


@app.route("/api/adb/status")
def adb_status():
    from modules.adb_network import is_device_connected, get_current_ip
    return jsonify({
        "connected": is_device_connected(),
        "ip": get_current_ip()
    })


@app.route("/api/logs/stream")
def log_stream():
    """SSE endpoint for real-time logs."""
    def generate():
        while True:
            try:
                msg = log_queue.get(timeout=30)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            except Exception:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/tasks/run", methods=["POST"])
def run_task_api():
    global task_running
    if task_running:
        return jsonify({"error": "이미 작업이 실행 중입니다"}), 400

    task_data = request.json
    accounts = load_accounts()

    # Build task object
    main_acc = _resolve_main(accounts, task_data.get("main_id"))
    if not main_acc:
        return jsonify({"error": "메인(글 작성자) 계정이 선택되지 않았거나 존재하지 않습니다"}), 400

    commenters = accounts.get("commenters", [])
    commenter_map = {c["id"]: c for c in commenters}

    comments = []
    for c in task_data.get("comments", []):
        acc = commenter_map.get(c["account_id"])
        if acc:
            comments.append({"account": acc, "text": c["text"]})

    replies = []
    for r in task_data.get("replies", []):
        replies.append({"to_index": r["to_index"], "text": r["text"]})

    task = {
        "mode": task_data.get("mode", "new"),
        "cafe_url": task_data.get("cafe_url", ""),
        "post_url": task_data.get("post_url", ""),
        "board_name": task_data.get("board_name", ""),
        "title": task_data.get("title", ""),
        "body": task_data.get("body", ""),
        "main_account": main_acc,
        "comments": comments,
        "replies": replies,
    }

    # Run in background thread
    stop_event.clear()
    task_running = True

    def log_fn(msg):
        ts = time.strftime("%H:%M:%S")
        log_queue.put({"type": "log", "time": ts, "message": msg})

    def run_in_thread():
        global task_running
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            from modules.task_runner import run_task
            result = loop.run_until_complete(run_task(task, log_fn, stop_event))
            log_queue.put({"type": "done", "result": result})
        except Exception as e:
            log_queue.put({"type": "error", "message": str(e)})
        finally:
            task_running = False

    t = threading.Thread(target=run_in_thread, daemon=True)
    t.start()

    return jsonify({"success": True, "message": "작업 시작됨"})


@app.route("/api/scenario/parse", methods=["POST"])
def parse_scenario():
    """업로드된 txt 파일을 파싱해 프리뷰 반환"""
    from modules.txt_parser import parse_scenario_text
    if 'file' in request.files:
        raw = request.files['file'].read().decode('utf-8', errors='replace')
    else:
        raw = (request.json or {}).get('text', '')
    try:
        parsed = parse_scenario_text(raw)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    accounts = load_accounts()
    commenter_map = {}
    for c in accounts.get("commenters", []):
        label = c.get("label", "")
        m = re.search(r'\d+', label)
        if m:
            commenter_map[int(m.group())] = c

    missing = [n for n in parsed["commenter_nums"] if n not in commenter_map]
    mapped = {n: commenter_map[n]["id"] for n in parsed["commenter_nums"] if n in commenter_map}

    return jsonify({
        "title": parsed["title"],
        "body": parsed["body"],
        "actions": parsed["actions"],
        "commenter_nums": parsed["commenter_nums"],
        "image_nums": parsed.get("image_nums", []),
        "mapped_accounts": mapped,
        "missing_nums": missing,
    })


@app.route("/api/scenario/run", methods=["POST"])
def run_scenario():
    """시나리오 기반 실행 (txt에서 파싱한 actions + 카페 URL).
    multipart/form-data 지원: text, cafe_url, main_id, board_name + image_1, image_2, ...
    JSON 도 호환 (이미지 없을 때).
    """
    global task_running
    if task_running:
        return jsonify({"error": "이미 작업이 실행 중입니다"}), 400

    from modules.txt_parser import parse_scenario_text

    # multipart 또는 json 모두 수용
    image_map = {}
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        data = {
            "text": request.form.get("text", ""),
            "cafe_url": request.form.get("cafe_url", ""),
            "board_name": request.form.get("board_name", ""),
            "main_id": request.form.get("main_id", ""),
        }
        # image_1, image_2, ... 저장
        for key, f in request.files.items():
            if not key.startswith("image_") or not f or not f.filename:
                continue
            try:
                num = int(key.split("_", 1)[1])
            except ValueError:
                continue
            safe = secure_filename(f.filename) or f"img{num}.jpg"
            ts = str(int(time.time() * 1000))
            fname = f"{ts}_{num}_{safe}"
            path = os.path.join(UPLOAD_DIR, fname)
            f.save(path)
            image_map[num] = path
    else:
        data = request.json or {}

    raw_text = data.get("text", "")
    try:
        parsed = parse_scenario_text(raw_text)
    except Exception as e:
        return jsonify({"error": f"파싱 오류: {e}"}), 400

    accounts = load_accounts()
    main_acc = _resolve_main(accounts, data.get("main_id"))
    if not main_acc:
        return jsonify({"error": "메인(글 작성자) 계정이 선택되지 않았거나 존재하지 않습니다"}), 400

    commenter_map = {}
    for c in accounts.get("commenters", []):
        label = c.get("label", "")
        m = re.search(r'\d+', label)
        if m:
            commenter_map[int(m.group())] = c

    # 시나리오 actions → 실행용 actions (계정 붙이기)
    exec_actions = []
    for act in parsed["actions"]:
        if act["action"] == "comment":
            acc = commenter_map.get(act["commenter_num"])
            if not acc:
                return jsonify({"error": f"댓글 {act['commenter_num']} 계정이 등록되지 않음"}), 400
            exec_actions.append({"action": "comment", "account": acc, "text": act["text"]})
        elif act["action"] == "reply":
            if act.get("is_main"):
                acc = main_acc
            else:
                acc = commenter_map.get(act["commenter_num"])
                if not acc:
                    return jsonify({"error": f"ㄴ 댓글 {act['commenter_num']} 계정이 등록되지 않음"}), 400
            exec_actions.append({
                "action": "reply", "account": acc,
                "to_index": act["to_index"], "text": act["text"]
            })

    task = {
        "mode": "new",
        "cafe_url": data.get("cafe_url", ""),
        "board_name": data.get("board_name", ""),
        "title": parsed["title"],
        "body": parsed["body"],
        "main_account": main_acc,
        "comments": [],
        "replies": [],
        "scenario": exec_actions,
        "image_map": image_map,
    }

    stop_event.clear()
    task_running = True

    def log_fn(msg):
        ts = time.strftime("%H:%M:%S")
        log_queue.put({"type": "log", "time": ts, "message": msg})

    def run_in_thread():
        global task_running
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            from modules.task_runner import run_task
            result = loop.run_until_complete(run_task(task, log_fn, stop_event))
            log_queue.put({"type": "done", "result": result})
        except Exception as e:
            log_queue.put({"type": "error", "message": str(e)})
        finally:
            task_running = False

    threading.Thread(target=run_in_thread, daemon=True).start()
    return jsonify({"success": True, "message": f"시나리오 실행 시작 ({len(exec_actions)}개 액션)"})


@app.route("/api/tasks/stop", methods=["POST"])
def stop_task():
    global task_running
    if task_running:
        stop_event.set()
        return jsonify({"success": True, "message": "중단 요청됨"})
    return jsonify({"success": False, "message": "실행 중인 작업 없음"})


@app.route("/api/tasks/status")
def task_status():
    return jsonify({"running": task_running})


if __name__ == "__main__":
    app.run(debug=True, port=FLASK_PORT, threaded=True)
