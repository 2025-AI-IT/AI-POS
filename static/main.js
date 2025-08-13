const Controllers = new Map(); // key -> AbortController
async function safeFetch(key, input, init = {}) {
  try {
    // 이전 요청 중단
    if (Controllers.has(key)) {
      Controllers.get(key).abort();
    }
    const ctrl = new AbortController();
    Controllers.set(key, ctrl);
    init.signal = ctrl.signal;

    init.cache = init.cache || "no-store";
    const res = await fetch(input, init);
    Controllers.delete(key);
    return res;
  } catch (e) {
    Controllers.delete(key);
    throw e;
  }
}
const $ = (id) => document.getElementById(id);
const setText = (id, txt) => { const el = $(id); if (el) el.textContent = txt; };
const esc = (s) => String(s)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const clientQty   = new Map(); 
const removedKeys = new Set(); 
const removedMap  = new Map(); 
const keyOf = (s) => String(s).trim().toLowerCase();

const listEl = $("item-list");
function formatPrice(price) { return `₩${Number(price||0).toLocaleString()}`; }

function updateLineAndTotal(row) {
  const unit = Number(row.dataset.unit || 0);
  const qty  = Number(row.querySelector(".item-qty")?.value || 1);
  const line = unit * qty;
  const tgt  = row.querySelector(".item-line-price");
  if (tgt) tgt.textContent = formatPrice(line);
  recomputeTotalFromDOM();
}
function recomputeTotalFromDOM() {
  let sum = 0;
  document.querySelectorAll(".item-row").forEach((r) => {
    const unit = Number(r.dataset.unit || 0);
    const qty  = Number(r.querySelector(".item-qty")?.value || 1);
    sum += unit * qty;
  });
  const totalEl = $("total-price");
  if (totalEl) {
    totalEl.textContent = formatPrice(sum);
    totalEl.dataset.raw = String(sum);
  }
}

// detect 폴링
if (window.__detectTimer) clearInterval(window.__detectTimer);
window.__detectTimer = setInterval(async () => {
  try {
    const res  = await safeFetch("poll_detect", "/detect");
    const data = await res.json();
    if (!listEl || !data || !Array.isArray(data.items)) return;

    const serverKeys = new Set();

    // 1) 서버 응답과 DOM 머지
    data.items.forEach(([name, unit, serverQty, subTotal]) => {
      const key = keyOf(name);
      serverKeys.add(key);

      // 억제 중이면 신규 증가가 있을 때만 해제
      if (removedMap.has(key)) {
        const baseline = removedMap.get(key);
        if (serverQty > baseline) {
          removedMap.delete(key);
        } else {
          return; // 재등록 억제
        }
      }

      // 표시 수량: 수동값 우선, 서버가 더 크면 올림
      let qty = clientQty.has(key) ? clientQty.get(key) : serverQty;
      if (serverQty > qty) {
        qty = serverQty;
        clientQty.set(key, qty);
      }
      const linePrice = unit * qty;

      const selectorKey = window.CSS?.escape ? CSS.escape(key) : key;
      let row = listEl.querySelector(`.item-row[data-key="${selectorKey}"]`);

      if (!row) {
        const div = document.createElement("div");
        div.className = "item-row";
        div.dataset.key  = key;    
        div.dataset.name = name;   
        div.dataset.unit = unit;

        div.innerHTML = `
          <span class="item-name">
            <button class="item-remove" title="삭제">
              <img src="/static/assets/trashcan.svg" alt="">
            </button>
            ${esc(name)}
          </span>
          <div class="item-controls">
            <button class="qty-btn minus">−</button>
            <input type="number" class="item-qty" min="1" max="99" value="${qty}">
            <button class="qty-btn plus">+</button>
          </div>
          <span class="item-line-price">${formatPrice(linePrice)}</span>
        `;
        listEl.appendChild(div);
      } else {
        // 기존 행 업데이트
        row.dataset.unit = unit;
        const input = row.querySelector(".item-qty");
        if (input && Number(input.value) !== Number(qty)) input.value = qty;
        const lp = row.querySelector(".item-line-price");
        if (lp) lp.textContent = formatPrice(linePrice);
      }
    });

    // 2) 서버에 없는 항목 제거
    [...document.querySelectorAll(".item-row")].forEach((row) => {
      const key = row.dataset.key;
      if (!serverKeys.has(key)) {
        clientQty.delete(key);
        row.remove();
      }
    });

    // 3) 부재 확인되면 억제 해제
    for (const key of [...removedKeys]) {
      if (!serverKeys.has(key)) removedKeys.delete(key);
    }

    // 4) 총합 갱신
    recomputeTotalFromDOM();
  } catch (e) {
  
    console.warn("detect poll error:", e?.message || e);
  }
}, 1000);

if (listEl) {
  listEl.addEventListener("click", (e) => {
    const row = e.target.closest(".item-row");
    if (!row) return;

    const key   = row.dataset.key;
    const name  = row.dataset.name;
    const input = row.querySelector(".item-qty");

    // 삭제
    if (e.target.closest(".item-remove")) {
      removedMap.set(key, 1); 
      clientQty.delete(key);
      row.remove();
      recomputeTotalFromDOM();
      removeItem(name).catch(console.warn);
      return;
    }

    // +
    if (e.target.closest(".qty-btn.plus")) {
      const next = Math.min(99, (Number(input?.value) || 1) + 1);
      clientQty.set(key, next);
      if (input) input.value = next;
      updateLineAndTotal(row);
      updateQty(name, next).catch(console.warn);
      return;
    }

    // −
    if (e.target.closest(".qty-btn.minus")) {
      const next = Math.max(1, (Number(input?.value) || 1) - 1);
      clientQty.set(key, next);
      if (input) input.value = next;
      updateLineAndTotal(row);
      updateQty(name, next).catch(console.warn);
      return;
    }
  });

  listEl.addEventListener("change", (e) => {
    if (!e.target.matches(".item-qty")) return;
    const row  = e.target.closest(".item-row");
    const key  = row.dataset.key;
    const name = row.dataset.name;

    let v = parseInt(e.target.value || "1", 10);
    if (Number.isNaN(v)) v = 1;
    v = Math.min(99, Math.max(1, v));

    clientQty.set(key, v);
    e.target.value = v;
    updateLineAndTotal(row);
    updateQty(name, v).catch(console.warn);
  });
}

// 결제하기 버튼
const payBtn = $("pay-btn");
if (payBtn) {
  payBtn.addEventListener("click", async () => {
    const totalEl = $("total-price");
    const total = Number(totalEl?.dataset?.raw || 0);
    if (!total) {
      openInfoModal("장바구니가 비어 있습니다!");
      return;
    }

    // DOM → items 수집
    const items = [];
    document.querySelectorAll(".item-row").forEach((row) => {
      const name = row.dataset.name;
      const unit = Number(row.dataset.unit || 0);
      const qty  = Number(row.querySelector(".item-qty")?.value || 1);
      items.push([name, unit, qty, unit * qty]);
    });

    try {
      const res = await safeFetch("verify", "/cart/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items, abs_tol_g: ABS_TOL_G, pct_tol: PCT_TOL })
      });
      const v = await res.json();
      if (!res.ok) throw new Error(v.error || "verify error");

      if (!v.ok) {
        openMismatchModal(v.expected_g, v.real_g, v.diff_g);
        return;
      }

      // 결제 시작
      const ready = await safeFetch("pay_ready", "/pay/ready", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount: total }),
      });
      const d = await ready.json();
      const qrImg = $("qrImg"), qrModal = $("qrModal");
      if (qrImg && qrModal) {
        qrImg.src = d.qr;
        qrModal.classList.remove("hidden");
      }
    } catch (e) {
      openInfoModal("결제 전 무게 검증 실패: " + (e?.message || e));
    }
  });
}

async function updateQty(name, qty) {
  try {
    await safeFetch(`qty_${name}`, "/cart/qty", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, qty }),
    });
  } catch (e) {
    console.warn("수량 업데이트 실패:", e);
  }
}
async function removeItem(name) {
  try {
    await safeFetch(`rm_${name}`, "/cart/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
  } catch (e) {
    console.warn("삭제 실패:", e);
  }
}

function openMismatchModal(expected, real, diff){
  const ex = $("mm-expected"), re = $("mm-real"), di = $("mm-diff"), md = $("mismatchModal");
  if (ex) ex.textContent = `${expected} g`;
  if (re) re.textContent = `${real} g`;
  if (di) di.textContent = `${diff > 0 ? "+" : ""}${diff} g`;
  if (md) md.classList.remove("hidden");
}
function closeMismatchModal(){
  const md = $("mismatchModal");
  if (md) md.classList.add("hidden");
}
const mmClose = $("mm-close"), mmRetry = $("mm-retry");
if (mmClose) mmClose.addEventListener("click", closeMismatchModal);
if (mmRetry) mmRetry.addEventListener("click", () => { closeMismatchModal(); });

function openInfoModal(msg){
  const im = $("infoModal"), imsg = $("infoMsg");
  if (imsg) imsg.textContent = msg || "";
  if (im) im.classList.remove("hidden");
}
const infoClose = $("infoClose");
if (infoClose) infoClose.addEventListener("click", ()=>{ const im=$("infoModal"); if (im) im.classList.add("hidden"); });
