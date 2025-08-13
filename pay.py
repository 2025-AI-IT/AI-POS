# 카카오페이 테스트 api 
import os, uuid, requests
from flask import Blueprint, jsonify, request, url_for, session
from base64 import b64encode
import qrcode, io

PAY_BP = Blueprint("pay", __name__)

KAKAO_API_HOST = "https://kapi.kakao.com/v1/payment"
CID_TEST = "TC0ONETIME"

def kakao_headers():
    admin_key = os.getenv("KAKAO_ADMIN_KEY")
    return {
        "Authorization": f"KakaoAK {admin_key}" if admin_key else "",
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
    }

@PAY_BP.route("/pay/ready", methods=["POST"])
def pay_ready():
    """
    결제 준비: 카카오페이 Ready API 호출 → PC/모바일 Redirect URL + QR 반환
    """
    admin_key = os.getenv("KAKAO_ADMIN_KEY")
    if not admin_key:
        return jsonify({"error": "KAKAO_ADMIN_KEY not set"}), 500

    body = request.get_json(silent=True) or {}
    try:
        total_amount = int(body.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "amount must be an integer"}), 400

    if total_amount <= 0:
        return jsonify({"error": "amount must be > 0"}), 400

    order_id = str(uuid.uuid4())[:8]

    try:
        payload = {
            "cid": CID_TEST,
            "partner_order_id": order_id,
            "partner_user_id": body.get("user_id", "demo_user"),
            "item_name": body.get("item_name", "스마트POS 장바구니"),
            "quantity": 1,
            "total_amount": total_amount,
            "tax_free_amount": 0,
            "approval_url": url_for("pay.pay_confirm", _external=True),
            "cancel_url":   url_for("pay.pay_cancel",  _external=True),
            "fail_url":     url_for("pay.pay_cancel",  _external=True),
        }

        res = requests.post(
            f"{KAKAO_API_HOST}/ready",
            data=payload,
            headers=kakao_headers(),
            timeout=5,
        )
        res.raise_for_status()
        data = res.json()

        session["kakao_tid"] = data.get("tid")
        session["order_id"] = order_id

        mobile_url = data.get("next_redirect_mobile_url")
        pc_url     = data.get("next_redirect_pc_url")

        # QR 생성 (모바일 진입용)
        buf = io.BytesIO()
        qrcode.make(mobile_url or pc_url or "").save(buf, format="PNG")
        qr_b64 = b64encode(buf.getvalue()).decode()

        return jsonify({
            "order_id": order_id,
            "tid": data.get("tid"),
            "mobile_url": mobile_url,
            "pc_url": pc_url,
            "qr": f"data:image/png;base64,{qr_b64}",
        }), 200

    except requests.exceptions.HTTPError as e:
        try:
            err = res.json()
        except Exception:
            err = {"message": str(e)}
        return jsonify({"error": "kakao_ready_failed", "detail": err}), res.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"error": "kakao_ready_timeout_or_network", "detail": str(e)}), 502

@PAY_BP.route("/pay/confirm")
def pay_confirm():
    return "<h2>결제 완료 (TEST)</h2>"

@PAY_BP.route("/pay/cancel")
def pay_cancel():
    return "<h2>결제 취소 또는 실패 (TEST)</h2>"