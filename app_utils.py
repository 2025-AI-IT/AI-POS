price_table = {
    "농심매운새우깡": 1700,
    "농심바나나킥": 1800,
    "퓨어치약클린민트향": 2000,
    "가그린제로": 3200,
    "이클립스피치향": 3000,
    "닥터유단백질바": 1000,
    "비타500젤리": 1300,
    "동원고추참치": 2800,
    "오뚜기스위트콘": 5000,
    "CJ스팸": 3900,
    "참이슬후레쉬": 2500,
    "카스라이트": 2000,
    "오레오초콜릿크림": 2000,
    "농심새우깡" : 1700,
    "참깨라면_볶음면컵" : 1500,
    "참깨라면_큰컵" : 1500,
    "코카스프라이트": 1500,
    "옥수수수염차": 2200,
    "초코에몽": 1400,
    "농심신라면컵": 1100,
    "농심짜파게티큰사발": 1000,
    "참깨라면_작은컵": 1000,
    "마데카솔": 4000
}

weight_table = {
    "농심매운새우깡": 170,
    "농심바나나킥": 180,
    "퓨어치약클린민트향": 200,
    "가그린제로": 320,
    "이클립스피치향": 300,
    "닥터유단백질바": 100,
    "비타500젤리": 100,
    "동원고추참치": 800,
    "오뚜기스위트콘": 400,
    "CJ스팸": 200,
    "참이슬후레쉬": 250,
    "카스라이트": 200,
    "오레오초콜릿크림": 200,
    "농심새우깡" : 100,
    "참깨라면_볶음면컵" : 300,
    "참깨라면_큰컵" : 300,
    "코카스프라이트": 150,
    "옥수수수염차": 200,
    "초코에몽": 140,
    "농심신라면컵": 110,
    "농심짜파게티큰사발": 100,
    "참깨라면_작은컵": 100,
    "마데카솔": 400
}


def get_price(label):
    return price_table.get(label, 0)

def get_class_name(class_id):
    names = [
    "농심매운새우깡",
    "농심바나나킥",
    "퓨어치약클린민트향",
    "가그린제로",
    "이클립스피치향",
    "닥터유단백질바",
    "비타500젤리",
    "동원고추참치",
    "오뚜기스위트콘",
    "CJ스팸",
    "참이슬후레쉬",
    "카스라이트",
    "오레오초콜릿크림",
    "농심새우깡",
    "참깨라면_볶음면컵",
    "참깨라면_큰컵",
    "코카스프라이트",
    "옥수수수염차",
    "초코에몽",
    "농심신라면컵",
    "농심짜파게티큰사발",
    "참깨라면_작은컵",
    "마데카솔"
]

    return names[class_id] if class_id < len(names) else "unknown"


def get_weight(label):
    """상품명으로 예상 무게(g) 반환"""
    return weight_table.get(label, 0)

def cart_expected_weight_g(items):
    """
    items: [ [name, unit, qty, subTotal], ... ]
    return: 총 예상 무게(g)
    """
    total = 0
    for name, _unit, qty, _subtotal in items:
        total += get_weight(name) * max(int(qty), 1)
    return total

def weight_match(real_g, expected_g, abs_tol_g=5.0, pct_tol=0.05):
    """
    허용 오차 범위 내 일치 여부
    """
    if expected_g <= 0:
        return False
    diff = abs(real_g - expected_g)
    return (diff <= abs_tol_g) or (diff <= expected_g * pct_tol)

def compare_cart_vs_scale(items, scale_g, abs_tol_g=5.0, pct_tol=0.05):
    """
    장바구니 예상 무게와 저울 측정 무게 비교
    """
    expected = cart_expected_weight_g(items)
    ok = weight_match(scale_g, expected, abs_tol_g=abs_tol_g, pct_tol=pct_tol)
    return {
        "ok": ok,
        "real_g": int(round(scale_g)),     
        "expected_g": int(round(expected)), 
        "diff_g": int(round(scale_g - expected)), 
        "abs_tol_g": abs_tol_g,              
        "pct_tol": pct_tol                 
    }
