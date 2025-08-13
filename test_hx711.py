# test_hx711.py
# 사용법:
#   1) 트레이를 비운 상태에서 실행
#   2) 안내에 따라 Enter를 누르고, 알려진 무게(예: 500)를 g 단위로 입력
#   3) 계산된 REF가 출력되고, 선택하면 calib.json/.env에 저장

import time, json, statistics, os
import RPi.GPIO as GPIO
from hx711 import HX711

# 배선/설정 
DT, SCK = 5, 6
GAIN = 128

# 필터/안정화 파라미터 
MEDIAN_N       = 15   
STABLE_STD_MAX = 2.0   
TARE_TIMES     = 15   

def setup_hx(reference_unit: float = 1.0):
    hx = HX711(dout=DT, pd_sck=SCK, gain=GAIN)
    hx.set_reading_format("MSB", "MSB")
    hx.set_reference_unit(reference_unit)  
    hx.reset()
    return hx

def median_read(hx: HX711, n: int = MEDIAN_N):
    vals = [hx.get_weight(times=1) for _ in range(n)]
    med  = statistics.median(vals)
    std  = statistics.pstdev(vals) if len(vals) > 1 else 0.0
    return med, std, vals

def wait_stable(hx: HX711, label: str, timeout_s: float = 5.0):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout_s:
        med, std, _ = median_read(hx, n=7)
        print(f"[{label}] med={med:.1f}, std={std:.2f}")
        last = (med, std)
        if std <= STABLE_STD_MAX:
            return last
        time.sleep(0.2)
    return last  

def save_ref(ref: float):
    # 1) calib.json 저장
    with open("calib.json", "w", encoding="utf-8") as f:
        json.dump({"REF": ref}, f, ensure_ascii=False, indent=2)
    print("✔ calib.json 저장 완료")

    # 2) .env 업데이트(이미 있으면 교체, 없으면 추가)
    line = f"SCALE_REF={ref:.6f}\n"
    try:
        env_path = ".env"
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            wrote = False
            with open(env_path, "w", encoding="utf-8") as f:
                for L in lines:
                    if L.startswith("SCALE_REF="):
                        f.write(line); wrote = True
                    else:
                        f.write(L)
                if not wrote:
                    f.write(line)
        else:
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(line)
        print(".env에 SCALE_REF 저장/갱신 완료")
    except Exception as e:
        print(".env 저장 실패:", e)

def main():
    print("=== HX711 자동 캘리브레이션 ===")
    print("1) 트레이를 완전히 비우고 센서를 안정된 곳(진동/바람 X)에 두세요.")
    input("준비되면 Enter를 눌러 영점(tare)을 시작합니다...")

    hx = setup_hx(reference_unit=1.0)  # 1.0으로 시작(원시 스케일)
    time.sleep(0.3)

    # 영점 전 안정 대기
    wait_stable(hx, "pre-tare", timeout_s=4.0)

    print("영점 중... 가만히 두세요.")
    hx.tare(times=TARE_TIMES)
    time.sleep(0.3)

    # 영점 후 확인
    med0, std0, _ = median_read(hx, n=11)
    print(f"영점 확인: med={med0:.1f}, std={std0:.2f}")

    # 캘리브용 물건 안내
    print("\n2) 알려진 무게의 물건을 트레이에 올려주세요.")
    print("   (예: 500g 추, 또는 주방저울로 미리 잰 정확한 무게)")
    input("올렸으면 Enter를 눌러 측정을 시작합니다...")

    # 올린 상태 안정 대기
    med1, std1 = wait_stable(hx, "with-weight", timeout_s=6.0)
    if med1 is None:
        print("⚠ 안정 상태를 확보하지 못했습니다. 주변 진동/전원/배선 확인 후 다시 시도하세요.")
        return

    # 실제 무게 입력
    while True:
        try:
            known_g = float(input("입력: 이 물건의 '정확한 무게(g)'를 숫자로 입력하세요: ").strip())
            if known_g <= 0:
                raise ValueError
            break
        except ValueError:
            print("유효한 g 값을 입력하세요. 예: 500")

    # REF 계산 (원시스케일=1.0 기준이므로 med1 / 실제g)
    ref = med1 / known_g
    print("\n=== 계산 결과 ===")
    print(f"측정값(중앙값): {med1:.2f}  |  실제: {known_g:.2f} g")
    print(f" REF = measured / actual = {med1:.4f} / {known_g:.4f} = {ref:.6f}")

    # 계산된 REF를 적용해서 즉시 검증
    print("\nREF 적용 후 재검증 중...")
    hx.set_reference_unit(ref)
    time.sleep(0.3)
    med2, std2, _ = median_read(hx, n=11)
    print(f"동일 물건, 환산 무게: {med2:.1f} g  (std={std2:.2f})")
    print(f"오차: {(med2 - known_g):+.1f} g")

if __name__ == "__main__":
    main()
