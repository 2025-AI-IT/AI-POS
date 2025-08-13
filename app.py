# app.py
import os, requests, threading, time
from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

from flask import Flask, render_template, Response, jsonify, request
from flask_socketio import SocketIO

from app_utils import compare_cart_vs_scale
from detector import detect_once, get_detected_frame   # YOLO 모듈
from pay      import PAY_BP                            # 카카오페이 모듈

SCALE_API = (os.getenv("SCALE_API_BASE", "http://127.0.0.1:8080/") or "").rstrip("/")
def _scale_url(path: str) -> str:
    path = (path or "").lstrip("/")
    return f"{SCALE_API}/{path}"

REQ_TIMEOUT = (0.5, 3.0)   # (connect, read) 기본
REQ_TIMEOUT_TARE = (0.5, 5.0)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret")
app.register_blueprint(PAY_BP)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

SCALE_CACHE = {
    "weight_g": None,
    "state": None,
    "updated_at": 0.0,
    "ok": False,
    "err": None,
}

def _poll_scale_worker():
    url = _scale_url("/weight")
    while True:
        try:
            r = requests.get(url, timeout=REQ_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            SCALE_CACHE["weight_g"] = int(float(data.get("weight_g", 0)))
            SCALE_CACHE["state"]    = data.get("state")
            SCALE_CACHE["ok"]       = bool(data.get("ok", True)) if isinstance(data, dict) else True
            SCALE_CACHE["err"]      = None
            SCALE_CACHE["updated_at"] = time.time()
        except Exception as e:
            SCALE_CACHE["ok"] = False
            SCALE_CACHE["err"] = str(e)
            SCALE_CACHE["updated_at"] = time.time()
        time.sleep(0.5)

threading.Thread(target=_poll_scale_worker, daemon=True).start()

def _get_cached_weight(max_age=2.0) -> int:
    """최근 max_age초 이내에 갱신된 캐시가 있으면 정수 g 반환, 없으면 -1"""
    if SCALE_CACHE["weight_g"] is None:
        return -1
    if (time.time() - SCALE_CACHE["updated_at"]) > max_age:
        return -1
    return int(SCALE_CACHE["weight_g"])

# ────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/scale")
def scale():
    try:
        url = _scale_url("/weight")
        r = requests.get(url, timeout=REQ_TIMEOUT)
        r.raise_for_status()
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": f"scale proxy error: {e}"}), 502

@app.route("/weight")
def weight_proxy():
    try:
        url = _scale_url("/weight")
        r = requests.get(url, timeout=REQ_TIMEOUT)
        r.raise_for_status()
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": f"scale proxy error: {e}"}), 502


@app.route("/detect")
def detect_api():
    result = detect_once()            
    items = result.get("items", [])

    real_g = _get_cached_weight(max_age=2.0)
    weight_check = None
    if real_g >= 0 and items:
        weight_check = compare_cart_vs_scale(items, real_g)

    return jsonify({
        **result,
        "scale_cached_g": real_g if real_g >= 0 else None,
        "weight_check": weight_check
    })

@app.route("/cart/verify", methods=["POST"])
def cart_verify():
    """
    body:
      { "items": [[name, unit, qty, subTotal], ...],
        "abs_tol_g": 5.0, "pct_tol": 0.05 }
    return:
      { ok, real_g, expected_g, diff_g, abs_tol_g, pct_tol }
    """
    try:
        data = request.get_json(force=True) or {}
        items = data.get("items", [])
        abs_tol_g = float(data.get("abs_tol_g", 5.0))
        pct_tol   = float(data.get("pct_tol", 0.05))
   
        url = _scale_url("/weight")
        r = requests.get(url, timeout=REQ_TIMEOUT)
        r.raise_for_status()
        j = r.json()
        real_g = int(float(j.get("weight_g", 0)))

        result = compare_cart_vs_scale(items, real_g, abs_tol_g=abs_tol_g, pct_tol=pct_tol)
        result["abs_tol_g"] = abs_tol_g
        result["pct_tol"]   = pct_tol
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": f"verify error: {e}"}), 400

@app.route("/video_feed")
def video_feed():

    return Response(
        get_detected_frame(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

if __name__ == "__main__":
    print("[RUN] Web @ :5000  | SCALE_API ->", SCALE_API)
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
