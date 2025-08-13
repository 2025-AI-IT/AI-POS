# weight_api.py
import os, json, time, statistics, threading
import RPi.GPIO as GPIO
from hx711 import HX711
from flask import Flask, jsonify, request
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv(dotenv_path=".env")

DT, SCK = 5, 6
GAIN = 128
DEFAULT_REF = float(os.getenv("SCALE_REF", 1.0))
CALIB_JSON = "calib.json"

def load_ref() -> float:
    env_ref = os.getenv("SCALE_REF")
    if env_ref:
        try:
            return float(env_ref)
        except:
            pass
    if os.path.exists(CALIB_JSON):
        try:
            with open(CALIB_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            return float(data.get("REF"))
        except:
            pass
    return DEFAULT_REF

def save_ref(ref: float):
    with open(CALIB_JSON, "w", encoding="utf-8") as f:
        json.dump({"REF": ref}, f, ensure_ascii=False, indent=2)
    line = f"SCALE_REF={ref:.8f}\n"
    path = ".env"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        wrote = False
        with open(path, "w", encoding="utf-8") as f:
            for L in lines:
                if L.startswith("SCALE_REF="):
                    f.write(line); wrote = True
                else:
                    f.write(L)
            if not wrote:
                f.write(line)
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(line)

# ── 2) HX711 초기화
GPIO.setmode(GPIO.BCM)
hx = HX711(dout=DT, pd_sck=SCK, gain=GAIN)
hx.set_reading_format("MSB", "MSB")

REF = load_ref()
hx.set_reference_unit(REF)
hx.reset()
hx.tare()

app = Flask(__name__)

try:
    from flask_cors import CORS
    CORS(app, resources={r"/*": {"origins": "*"}})
except Exception:
    pass

MEDIAN_N          = 9      
ZERO_CLAMP_G      = 0.6   
ABS_DEADBAND_G    = 1     
EMA_ALPHA         = 0.25  
TARE_CHECK_MAX    = 5.0
ZERO_RETURN_FORCE = 2
STABLE_STD_MAX    = 1.2
STABLE_WINDOW_N   = 9

SETTLE_SEC         = 2.5   
COOLDOWN_SEC       = 1.5  
PLACE_THRESHOLD_G  = 10    
REMOVE_THRESHOLD_G = 6     
LATCH_SAMPLE_N     = 21   

_ema = None
_last_int = 0
_sm_state = 'idle'         
_sm_t0 = None
_plateau_value = 0      
_last_delta_g = 0          

# 가격 테이블
price_table = {
    "농심매운새우깡": 1700, "농심바나나킥": 1800, "퓨어치약클린민트향": 2000, "가그린제로": 3200,
    "이클립스피치향": 3000, "닥터유단백질바": 1000, "비타500젤리": 1300, "동원고추참치": 2800,
    "오뚜기스위트콘": 5000, "CJ스팸": 3900, "참이슬후레쉬": 2500, "카스라이트": 2000,
    "오레오초콜릿크림": 2000, "농심새우깡": 1700, "참깨라면_볶음면컵": 1500, "참깨라면_큰컵": 1500,
    "코카스프라이트": 1500, "옥수수수염차": 2200, "초코에몽": 1400, "농심신라면컵": 1100,
    "농심짜파게티큰사발": 1000, "참깨라면_작은컵": 1000, "마데카솔": 4000
}
# 무게 테이블
weight_table = {
    "농심매운새우깡": 170, "농심바나나킥": 180, "퓨어치약클린민트향": 200, "가그린제로": 100,
    "이클립스피치향": 300, "닥터유단백질바": 100, "비타500젤리": 100, "동원고추참치": 800,
    "오뚜기스위트콘": 350, "CJ스팸": 200, "참이슬후레쉬": 600, "카스라이트": 200,
    "오레오초콜릿크림": 200, "농심새우깡": 100, "참깨라면_볶음면컵": 300, "참깨라면_큰컵": 300,
    "코카스프라이트": 150, "옥수수수염차": 200, "초코에몽": 140, "농심신라면컵": 110,
    "농심짜파게티큰사발": 100, "참깨라면_작은컵": 100, "마데카솔": 400
}

def get_weight(label): return weight_table.get(label, 0)

def cart_expected_weight_g(items):
    total = 0
    for name, _unit, qty, _subtotal in items:
        total += get_weight(name) * max(int(qty), 1)
    return total

def weight_match(real_g, expected_g, abs_tol_g= 5.0, pct_tol=0.05):
    if expected_g <= 0: return False
    diff = abs(real_g - expected_g)
    return (diff <= abs_tol_g) or (diff <= expected_g * pct_tol)

def read_once():
    return hx.get_weight(times=1)

def _reads(n):
    return [hx.get_weight(times=1) for _ in range(n)]

def _median_n(n=MEDIAN_N):
    vals = _reads(n)
    return statistics.median(vals)

def _current_int_value():
    global _ema, _last_int
    med = _median_n(MEDIAN_N)
    if abs(med) < ZERO_CLAMP_G:
        med = 0.0
    _ema = med if _ema is None else (EMA_ALPHA * med + (1.0 - EMA_ALPHA) * _ema)
    cur_int = int(round(_ema))
    if abs(cur_int - _last_int) <= ABS_DEADBAND_G:
        cur_int = _last_int
    _last_int = cur_int
    if abs(cur_int) <= ZERO_RETURN_FORCE:
        return 0
    return cur_int


def read_accumulating():
    import statistics as stats
    global _sm_state, _sm_t0, _plateau_value, _last_delta_g

    cur = _current_int_value()
    window_vals = _reads(STABLE_WINDOW_N)
    std_g = stats.pstdev(window_vals) if len(window_vals) > 1 else 0.0

    if _sm_state == 'idle':
        _plateau_value = 0
        _last_delta_g = 0
        if abs(cur) >= PLACE_THRESHOLD_G:
            _sm_state = 'settling'
            _sm_t0 = time.time()
        return _plateau_value, _last_delta_g, _sm_state

    elif _sm_state == 'settling':
        if (time.time() - _sm_t0) < SETTLE_SEC:
            return _plateau_value, 0, _sm_state
        vals = _reads(LATCH_SAMPLE_N)
        med = statistics.median(vals)
        if abs(med) < ZERO_CLAMP_G:
            med = 0.0
        latch_int = int(round(med))
        delta = latch_int - _plateau_value
        if abs(delta) < max(PLACE_THRESHOLD_G // 2, REMOVE_THRESHOLD_G):
            _sm_state = 'idle' if latch_int == 0 else 'latched'
            _last_delta_g = 0
            _plateau_value = latch_int if latch_int != 0 else 0
            return _plateau_value, _last_delta_g, _sm_state
        _plateau_value = latch_int
        _last_delta_g = int(round(delta))
        _sm_state = 'cooldown'
        _sm_t0 = time.time()
        return _plateau_value, _last_delta_g, _sm_state

    elif _sm_state == 'cooldown':
        if (time.time() - _sm_t0) >= COOLDOWN_SEC:
            _sm_state = 'latched'
        return _plateau_value, 0, _sm_state

    elif _sm_state == 'latched':
        delta_now = cur - _plateau_value
        if abs(delta_now) >= PLACE_THRESHOLD_G:
            _sm_state = 'settling'
            _sm_t0 = time.time()
        if abs(cur) <= REMOVE_THRESHOLD_G:
            _sm_state = 'idle'
            _plateau_value = 0
            _last_delta_g = 0
            return 0, 0, _sm_state
        return _plateau_value, 0, _sm_state

    _sm_state = 'idle'
    _plateau_value = 0
    _last_delta_g = 0
    return 0, 0, _sm_state

_cache = {
    "weight_g": 0,
    "last_delta_g": 0,
    "state": "idle",
    "updated_at": time.time(),
    "ok": False,
    "err": None,
}

def _update_cache():
    global _cache
    try:
        total, last_delta, state = read_accumulating()
        _cache.update({
            "weight_g": int(total),
            "last_delta_g": int(last_delta),
            "state": state,
            "updated_at": time.time(),
            "ok": True,
            "err": None,
        })
    except Exception as e:
        _cache.update({
            "ok": False,
            "err": str(e),
            "updated_at": time.time(),
        })

def _worker_loop():
    while True:
        _update_cache()
        time.sleep(0.05)

worker = threading.Thread(target=_worker_loop, daemon=True)
worker.start()

# 8080 api 열렸는지 확인
@app.route("/")
def home():
    return f"OK - weight API running (REF={REF:.6f})"

@app.route("/health")
def health():
    alive = (time.time() - _cache["updated_at"]) < 2.0
    return jsonify({"alive": alive, "ok": _cache["ok"], "err": _cache["err"]})

@app.route("/weight")
def weight():
    return jsonify({
        "weight_g": _cache["weight_g"],
        "last_delta_g": _cache["last_delta_g"],
        "state": _cache["state"],
        "ok": _cache["ok"],
        "err": _cache["err"],
        "updated_at": _cache["updated_at"],
    })

@app.route("/scale")
def scale_alias():
    return weight()

@app.route("/tare", methods=["POST"])
def tare():
    try:
        samples = [read_once() for _ in range(5)]
        med = statistics.median(samples)
        if abs(med) > TARE_CHECK_MAX:
            return jsonify({"ok": False, "reason": "not_empty", "measured_g": round(med,1)}), 400
    except:
        pass
    hx.tare(times=15)
    time.sleep(0.2)
    return jsonify({"ok": True})

@app.route("/scale/tare", methods=["POST"])
def scale_tare_alias():
    return tare()

@app.route("/calibrate", methods=["POST"])
def calibrate():
    global REF
    try:
        data = request.get_json(force=True) or {}
        new_ref = float(data["ref"])
        if not (0.1 <= new_ref <= 1e6):
            return jsonify({"ok": False, "error": "ref out of range"}), 400
        hx.set_reference_unit(new_ref)
        REF = new_ref
        save_ref(new_ref)
        return jsonify({"ok": True, "ref": new_ref})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/weights")
def weights():
    return jsonify({"weight_table": weight_table, "price_table": price_table})

@app.route("/cart/verify", methods=["POST"])
def verify_cart_weight():
    try:
        data = request.get_json(force=True) or {}
        items = data.get("items", []) 
        abs_tol_g = float(data.get("abs_tol_g", 5.0))
        pct_tol   = float(data.get("pct_tol", 0.05))

        expected = cart_expected_weight_g(items)
        real = int(_cache["weight_g"])   

        ok = weight_match(real, expected, abs_tol_g=abs_tol_g, pct_tol=pct_tol)
        return jsonify({
            "ok": ok,
            "real_g": real,
            "expected_g": int(round(expected)),
            "diff_g": real - int(round(expected)),
            "abs_tol_g": abs_tol_g,
            "pct_tol": pct_tol
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

if __name__ == "__main__":
    print("[RUN] / , /health , /weight , /tare , /calibrate , /weights , /cart/verify")
    app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)
