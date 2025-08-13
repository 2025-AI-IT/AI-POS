import torch
import cv2
import time
from app_utils import get_price, get_class_name, get_weight
from ultralytics import YOLO
from PIL import ImageFont, ImageDraw, Image
import numpy as np

import pathlib
temp = pathlib.PosixPath
pathlib.PosixPath = pathlib.WindowsPath


torch.set_num_threads(2)               
torch.backends.cudnn.enabled = False
IMG_SIZE = 416 

# YOLOv8 best.pt 사용 
model = YOLO('best.pt')
model.conf = 0.7  
model.iou = 0.3   
model.agnostic = False  
model.multi_label = False 
model.max_det = 23  

# 외부 웹캠 사용
cap = cv2.VideoCapture(1)   
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 30)


# 바운딩 박스 함수 
def get_detected_frame():
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        results = model(frame)
        boxes = results[0].boxes
        annotated_frame = frame.copy()

        if boxes is not None and len(boxes) > 0:
            # OpenCV → PIL 변환
            annotated_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
            annotated_frame = Image.fromarray(annotated_frame)
            draw = ImageDraw.Draw(annotated_frame)
            font = ImageFont.truetype("malgun.ttf", 20)
            
            # 클래스별로 바운딩 박스 색깔 다르게 설정
            CLASS_COLORS = {
                0: (220, 36, 38), 1: (255, 225, 53), 2: (102, 205, 170),
                3: (30, 144, 255), 4: (255, 170, 135), 5: (205, 133, 63),
                6: (255, 147, 0), 7: (200, 30, 30), 8: (255, 215, 0),
                9: (0, 0, 128), 10:(120,190,120), 11:(40,105,255),
                12:(78,52,46), 13:(0,255,0), 14:(245,205,92), 15:(97,54,32),
                16:(220,31,38), 17:(90,110,55), 18:(251,159,41), 19:(0,123,112)
            }
            DEFAULT_COLOR = (255, 0, 255)

            for box in boxes:
                conf = float(box.conf.cpu().numpy())
                if conf < 0.7:
                    continue

                cls = int(box.cls.cpu().numpy())
                xyxy = box.xyxy.cpu().numpy().astype(int)[0]
                label_text = f"{get_class_name(cls)} {conf:.2f}"

        
                color = CLASS_COLORS.get(cls, DEFAULT_COLOR)

                draw.rectangle([xyxy[0], xyxy[1], xyxy[2], xyxy[3]],
                            outline=color, width=2)
                draw.text((xyxy[0], xyxy[1] - 25),
                        label_text, font=font, fill=color)

            annotated_frame = np.array(annotated_frame)
            annotated_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR)

        ret, buffer = cv2.imencode('.jpg', annotated_frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')



COUNT_DELAY       = 1.5 
VANISH_TOLERANCE  = 2.0    
persistent = {}         
cart = {}                 
total_weight = 0

def detect_once():
    global persistent, cart, total_weight
    ok, frame = cap.read()
    now = time.time()
    if not ok:
        return {"items": [], "total": 0, "weight": 0}

    boxes = model(frame)[0].boxes
    visible = set()
    frame_counts = {} 

    if boxes is not None and len(boxes):
        for box in boxes:
            conf = float(box.conf.cpu())
            if conf < 0.7:          # 낮은 확률 필터
                continue

            label = get_class_name(int(box.cls))
            frame_counts[label] = frame_counts.get(label, 0) + 1
            visible.add(label)

    for label, cnt in frame_counts.items():
        info = persistent.get(label)
        if info is None:
            persistent[label] = {"start": now, "last": now,
                                 "max": cnt, "counted": 0}  # counted = 누적 집계된 수량
        else:
            info["last"] = now
            info["max"]  = max(info["max"], cnt)            # 세션 동안 본 최대 개수 저장

        info = persistent[label]

        # ③ 2초 연속 노출 → 새 수량만큼 cart에 추가
        if (now - info["start"] >= COUNT_DELAY):
            diff = info["max"] - info["counted"]            # 아직 반영 안 된 개수
            if diff > 0:
                entry = cart.setdefault(label, {"price": get_price(label), "qty": 0})
                entry["qty"] += diff
                total_weight += get_weight(label) * diff
                info["counted"] += diff                     # 반영된 만큼 기록

    for label, info in list(persistent.items()):
        if label not in visible and (now - info["last"] >= VANISH_TOLERANCE):
            del persistent[label]

    # 총액 & 응답
    total = sum(e["price"] * e["qty"] for e in cart.values())
    items = [
        [lbl, e["price"], e["qty"], e["price"] * e["qty"]]
        for lbl, e in cart.items()
    ]
    return {"items": items, "total": total, "weight": total_weight}