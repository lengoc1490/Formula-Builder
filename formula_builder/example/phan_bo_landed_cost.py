#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
phan_bo_landed_cost.py
======================
Mẫu phân bổ chi phí vận chuyển / hóa đơn / thuế vào item nhập kho.
Đúng với cấu trúc 2 bảng con của ERPNext đã thiết kế:

  Bảng 1 — Landed Cost Tax Item  (phiếu/khoản chi phí)
    voucher_type | voucher_no | expense_name | amount | allocation_method

  Bảng 2 — Landed Cost Receipt Item  (hàng hóa nhập kho)
    voucher_type | voucher_no | voucher_detail_no | item_code | item_name
    qty | uom | item_amount | net_weight
    cost_filter | item_method | allocation_amount | applicable_charges

Đặt file cùng thư mục engine_v24.py rồi nhấn F5.
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from engine_v24 import allocate

W = 72
def title(s): print(f"\n{'═'*W}\n  {s}\n{'═'*W}")
def sec(s):   print(f"\n  ── {s} ──")
def ok(l, v): print(f"  ✓  {l:48s} {v}")


# ══════════════════════════════════════════════════════════════════════════════
#  DỮ LIỆU MẪU — chỉnh sửa tại đây
# ══════════════════════════════════════════════════════════════════════════════

# ── Bảng 2: Hàng hóa nhập kho (Landed Cost Receipt Item) ─────────────────────
#
# cost_filter : để trống ("") = nhận từ TẤT CẢ khoản CP
#               điền voucher_no hoặc cost_id = chỉ nhận khoản đó
#
# item_method : để trống ("") = dùng tiêu thức của khoản CP
#               điền override = tiêu thức riêng cho dòng này
#               (khi điền manual_amount/manual_pct/pct → nhập allocation_amount)
#
# allocation_amount:
#   - item_method = manual_amount  → nhập SỐ TIỀN (VD: 500_000)
#   - item_method = manual_pct     → nhập TỶ LỆ % (VD: 25 = 25%)
#   - item_method = pct            → nhập TỶ LỆ % kế toán cố định
#   - item_method = auto (khác)    → để 0, engine tự tính

ITEMS = [
    # ── Phiếu nhập kho PUR-REC-2024-0041 ─────────────────────────────────────
    {
        "voucher_type":      "Purchase Receipt",
        "voucher_no":        "PUR-REC-2024-0041",
        "voucher_detail_no": "PRI-041-001",          # name dòng PR item
        "item_code":         "TV-55-4K",
        "item_name":         "Smart TV 55\" 4K",
        "qty":               10,
        "uom":               "cái",
        "rate":              8_000_000,
        "item_amount":       80_000_000,
        "net_weight":        150.0,                  # kg — dùng khi tiêu thức = weight
        "cost_filter":       "",                     # nhận tất cả khoản
        "item_method":       "",                     # dùng tiêu thức của khoản
        "allocation_amount": 0,
    },
    {
        "voucher_type":      "Purchase Receipt",
        "voucher_no":        "PUR-REC-2024-0041",
        "voucher_detail_no": "PRI-041-002",
        "item_code":         "LT-14-I7",
        "item_name":         "Laptop 14\" Core i7",
        "qty":               20,
        "uom":               "cái",
        "rate":              15_000_000,
        "item_amount":       300_000_000,
        "net_weight":        60.0,
        "cost_filter":       "",
        "item_method":       "",
        "allocation_amount": 0,
    },
    # ── PH-A15 dòng 1: nhận khoản k1 (cước) với manual_amount 1.5M ─────────
    {
        "voucher_type":      "Purchase Receipt",
        "voucher_no":        "PUR-REC-2024-0041",
        "voucher_detail_no": "PRI-041-003",
        "item_code":         "PH-A15",
        "item_name":         "iPhone 15 128GB",
        "qty":               100,
        "uom":               "cái",
        "rate":              5_000_000,
        "item_amount":       500_000_000,
        "net_weight":        50.0,
        "cost_filter":       "k1",        # CHỈ nhận từ khoản k1 (cước vận chuyển)
        "item_method":       "manual_amount",
        "allocation_amount": 1_500_000,   # nhập thẳng 1.5M cho khoản k1
    },
    # ── PH-A15 dòng 2: nhận khoản còn lại (k2,k3,k4) theo tiêu thức mặc định
    {
        "voucher_type":      "Purchase Receipt",
        "voucher_no":        "PUR-REC-2024-0041",
        "voucher_detail_no": "PRI-041-003b",   # cùng item, dòng khác
        "item_code":         "PH-A15",
        "item_name":         "iPhone 15 128GB",
        "qty":               100,
        "uom":               "cái",
        "rate":              5_000_000,
        "item_amount":       500_000_000,
        "net_weight":        50.0,
        "cost_filter":       "",          # nhận từ tất cả khoản (trừ k1 đã nhận trên)
        "item_method":       "",          # dùng tiêu thức của từng khoản
        "allocation_amount": 0,
    },
    # ── Phiếu nhập kho PUR-REC-2024-0042 ─────────────────────────────────────
    {
        "voucher_type":      "Purchase Receipt",
        "voucher_no":        "PUR-REC-2024-0042",
        "voucher_detail_no": "PRI-042-001",
        "item_code":         "TB-P12",
        "item_name":         "Lenovo Tab P12",
        "qty":               30,
        "uom":               "cái",
        "rate":              6_000_000,
        "item_amount":       180_000_000,
        "net_weight":        45.0,
        "cost_filter":       "",
        "item_method":       "",
        "allocation_amount": 0,
    },
    {
        "voucher_type":      "Purchase Receipt",
        "voucher_no":        "PUR-REC-2024-0042",
        "voucher_detail_no": "PRI-042-002",
        "item_code":         "CHG-65W",
        "item_name":         "Củ sạc GaN 65W",
        "qty":               200,
        "uom":               "cái",
        "rate":              500_000,
        "item_amount":       100_000_000,
        "net_weight":        40.0,
        "cost_filter":       "",
        "item_method":       "",
        "allocation_amount": 0,
    },
]

# ── Bảng 1: Khoản chi phí (Landed Cost Tax Item) ─────────────────────────────
#
# allocation_method: equal | qty | amount | weight | pct
#                    manual_amount | manual_pct | mixed
#
# cost_id: dùng làm khóa để ITEMS.cost_filter tham chiếu
#   (trong ERPNext thực tế đây là row.name tự sinh)

COSTS = [
    {
        "cost_id":           "k1",                  # khóa nội bộ
        "voucher_type":      "Purchase Invoice",
        "voucher_no":        "PINV-2024-0123",
        "expense_name":      "Cước vận chuyển biển",
        "expense_account":   "1562",
        "amount":            5_000_000,
        "allocation_method": "qty",                 # phân theo số lượng
    },
    {
        "cost_id":           "k2",
        "voucher_type":      "Journal Entry",
        "voucher_no":        "JV-2024-0456",
        "expense_name":      "Thuế nhập khẩu",
        "expense_account":   "3333",
        "amount":            3_500_000,
        "allocation_method": "weight",              # phân theo trọng lượng kg
    },
    {
        "cost_id":           "k3",
        "voucher_type":      "Purchase Invoice",
        "voucher_no":        "PINV-2024-0124",
        "expense_name":      "Phí dịch vụ logistics",
        "expense_account":   "6278",
        "amount":            2_000_000,
        "allocation_method": "amount",              # phân theo giá trị hàng
    },
    {
        "cost_id":           "k4",
        "voucher_type":      "Journal Entry",
        "voucher_no":        "JV-2024-0457",
        "expense_name":      "Phí hải quan (chia đều)",
        "expense_account":   "6278",
        "amount":              800_000,
        "allocation_method": "equal",               # chia đều mọi item
    },
    {
        "cost_id":           "k5",
        "voucher_type":      "Journal Entry",
        "voucher_no":        "JV-2024-0458",
        "expense_name":      "Phí kiểm định — chỉ PR-042",
        "expense_account":   "6278",
        "amount":              600_000,
        "allocation_method": "equal",
        # ── Demo cost_filter từ phía items: ──────────────────────────────────
        # Khoản này chỉ phân cho items có cost_filter = "k5" hoặc cost_filter = ""
        # (xem TB-P12 và CHG-65W bên dưới sẽ override cost_filter)
    },
]

# ── Ghi đè cost_filter cho 2 items PR-042 → chỉ nhận khoản k5 ────────────────
# (Simulate: phí kiểm định chỉ áp dụng riêng cho lô hàng PR-042)
for it in ITEMS:
    if it["voucher_no"] == "PUR-REC-2024-0042":
        it["cost_filter"] = "k5"

# ── PH-A15 dòng 2 (PRI-041-003b) không nhận khoản k1 (đã xử lý ở dòng 1) ────
for it in ITEMS:
    if it["voucher_detail_no"] == "PRI-041-003b":
        it["_exclude_costs"] = {"k1"}  # exclude k1 — handled via dòng 1

# ── Default allocation method (mixed_residual) ────────────────────────────────
DEFAULT_METHOD  = "qty"        # tiêu thức mặc định khi item không chỉ định
RESIDUAL_METHOD = "qty"        # mixed residual: phần còn lại chia theo qty


# ══════════════════════════════════════════════════════════════════════════════
#  ENGINE: phân bổ 1 khoản CP
# ══════════════════════════════════════════════════════════════════════════════

def run_one_cost(cost: dict, items: list) -> dict:
    """
    Phân bổ 1 khoản CP cho danh sách items phù hợp.
    Trả về {item voucher_detail_no: allocated_amount}
    """
    cost_method = cost["allocation_method"]
    cost_id     = cost["cost_id"]

    # Lọc items:
    #   cost_filter rỗng = nhận tất cả
    #   cost_filter có giá = chỉ nhận nếu khớp cost_id
    #   _exclude_costs = loại trừ cost_id cụ thể
    filtered = [
        it for it in items
        if (it["cost_filter"] == "" or it["cost_filter"] == cost_id)
        and cost_id not in it.get("_exclude_costs", set())
    ]
    if not filtered:
        return {}

    sources = [{"id": cost_id, "amount": cost["amount"]}]
    targets = []
    has_manual_override = False

    for it in filtered:
        per_method = it.get("item_method") or cost_method
        alloc_val  = it.get("allocation_amount", 0) or 0
        t = {"id": it["voucher_detail_no"]}

        if per_method == "manual_amount":
            if alloc_val <= 0:
                continue                      # không có giá → bỏ qua dòng này
            t["alloc_amount"] = alloc_val
            has_manual_override = True

        elif per_method == "manual_pct":
            if alloc_val <= 0:
                continue
            t["manual_pct"] = alloc_val
            has_manual_override = True

        elif per_method == "pct":
            if alloc_val <= 0:
                continue
            t["alloc_pct"] = alloc_val

        elif per_method == "qty":
            t["qty"] = it["qty"]

        elif per_method == "amount":
            t["amount"] = it["item_amount"]

        elif per_method == "weight":
            t["alloc_weight"] = it["net_weight"]

        elif per_method == "equal":
            pass

        elif per_method == "mixed":
            if alloc_val > 0:
                t["alloc_amount"] = alloc_val
                has_manual_override = True
            else:
                t["qty"] = it["qty"]

        targets.append(t)

    if not targets:
        return {}

    # Nếu có manual override trên items nhưng tiêu thức khoản không phải manual
    # → chuyển sang mixed để engine xử lý đúng
    use_method = cost_method
    if has_manual_override and cost_method not in ("manual_amount", "manual_pct", "pct"):
        use_method = "mixed"

    result = allocate(sources, targets, use_method, mixed_residual_method=RESIDUAL_METHOD)
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  CHẠY PHÂN BỔ TOÀN BỘ
# ══════════════════════════════════════════════════════════════════════════════

title("LANDED COST ALLOCATION — Phân bổ chi phí vào hàng hóa nhập kho")

# Hiển thị dữ liệu đầu vào
sec("Bảng 1: Khoản chi phí cần phân bổ")
print(f"\n  {'#':3} {'Phiếu':22} {'Tên khoản':28} {'Số tiền':>12} {'Tiêu thức':14}")
print(f"  {'─'*82}")
for i, c in enumerate(COSTS, 1):
    print(f"  {i:<3} {c['voucher_no']:22} {c['expense_name']:28} "
          f"{c['amount']:>12,.0f} {c['allocation_method']:14}")
tong_cp = sum(c["amount"] for c in COSTS)
print(f"  {'─'*82}")
print(f"  {'TỔNG':55} {tong_cp:>12,.0f}")

sec("Bảng 2: Hàng hóa nhập kho")
print(f"\n  {'voucher_detail_no':22} {'item_code':14} {'qty':>5} "
      f"{'item_amount':>14} {'weight':>8} {'cost_filter':12} {'item_method':14}")
print(f"  {'─'*100}")
for it in ITEMS:
    cf = it["cost_filter"] or "tất cả"
    im = it["item_method"] or "— (default)"
    print(f"  {it['voucher_detail_no']:22} {it['item_code']:14} {it['qty']:>5} "
          f"{it['item_amount']:>14,.0f} {it['net_weight']:>8.1f} {cf:12} {im:14}"
          + (f"  ← nhập tay {it['allocation_amount']:,.0f}"
             if it.get("allocation_amount", 0) > 0 else ""))

# ── Chạy từng khoản ───────────────────────────────────────────────────────────
sec("Kết quả phân bổ từng khoản")

applicable_charges = {it["voucher_detail_no"]: 0.0 for it in ITEMS}
allocated_detail   = []   # JSON detail lưu vào field allocated_detail
all_results        = {}

for cost in COSTS:
    r = run_one_cost(cost, ITEMS)
    all_results[cost["cost_id"]] = r

    if r is None:
        cost["allocated_amount"] = 0.0
        print(f"\n  [{cost['expense_name']}]: không có item nào phù hợp")
        continue

    allocated_total = sum(r.target_totals.values())
    cost["allocated_amount"] = allocated_total

    print(f"\n  📄 {cost['voucher_no']} · {cost['expense_name']}"
          f"  ({cost['allocation_method']})  →  {allocated_total:,.0f}")
    print(f"  {'─'*70}")

    for ln in sorted(r.lines, key=lambda x: -x.allocated):
        it = next((i for i in ITEMS if i["voucher_detail_no"] == ln.target_id), {})
        applicable_charges[ln.target_id] += ln.allocated
        print(f"    {ln.target_id:22} {it.get('item_code',''):14}"
              f" {ln.allocated:>12,.0f}  {ln.ratio*100:>6.2f}%"
              f"  [{ln.method}]")
        allocated_detail.append({
            "voucher_no":   cost["voucher_no"],
            "expense_name": cost["expense_name"],
            "method":       ln.method,
            "target_id":    ln.target_id,
            "item_code":    it.get("item_code", ""),
            "allocated":    ln.allocated,
            "ratio":        round(ln.ratio * 100, 4),
        })

    diff = abs(allocated_total - cost["amount"])
    print(f"    {'─'*58}")
    print(f"    {'TỔNG':36} {allocated_total:>12,.0f}  "
          f"{'✓' if diff < 1 else '⚠ chênh ' + str(round(diff))}")

# ── Ghi applicable_charges vào items ─────────────────────────────────────────
for it in ITEMS:
    it["applicable_charges"] = applicable_charges[it["voucher_detail_no"]]

# ── Bảng tổng hợp ─────────────────────────────────────────────────────────────
sec("Bảng tổng hợp: Item × Khoản CP")
cost_ids   = [c["cost_id"] for c in COSTS]
cost_names = [c["expense_name"][:12] for c in COSTS]
col_w = 13

print(f"\n  {'Item':22}" + "".join(f"{n:>{col_w}}" for n in cost_names)
      + f"{'TỔNG':>{col_w}}")
print(f"  {'─'*(22 + col_w * (len(COSTS) + 1))}")

for it in ITEMS:
    row_total = it["applicable_charges"]
    row = f"  {it['item_code']:22}"
    for c in COSTS:
        r = all_results.get(c["cost_id"])
        v = r.target_totals.get(it["voucher_detail_no"], 0) if r else 0
        row += f"{v:>{col_w},.0f}"
    row += f"{row_total:>{col_w},.0f}"
    print(row)

print(f"  {'─'*(22 + col_w * (len(COSTS) + 1))}")
col_totals = []
for c in COSTS:
    r = all_results.get(c["cost_id"])
    col_totals.append(sum(r.target_totals.values()) if r else 0)
grand = sum(col_totals)
print(f"  {'TỔNG':22}" + "".join(f"{v:>{col_w},.0f}" for v in col_totals)
      + f"{grand:>{col_w},.0f}")

# ── Giá vốn mới sau landed cost ───────────────────────────────────────────────
sec("Giá vốn mới = Giá gốc + Landed Cost")
print(f"\n  {'voucher_detail_no':22} {'item_code':14} {'qty':>5} "
      f"{'Giá gốc':>14} {'Landed CP':>12} {'Giá vốn mới':>14} {'ĐG/unit':>12} {'LC%':>6}")
print(f"  {'─'*103}")
for it in ITEMS:
    lc  = it["applicable_charges"]
    amt = it["item_amount"]
    qty = it["qty"]
    new = amt + lc
    print(f"  {it['voucher_detail_no']:22} {it['item_code']:14} {qty:>5} "
          f"{amt:>14,.0f} {lc:>12,.0f} {new:>14,.0f} {new/qty:>12,.0f} {lc/amt*100:>5.2f}%")

# ── Gộp theo item_code (khi 1 item có nhiều dòng) ────────────────────────────
from collections import defaultdict
merged = defaultdict(lambda: {"qty": 0, "item_amount": 0, "applicable_charges": 0})
for it in ITEMS:
    key = (it["voucher_no"], it["item_code"])
    merged[key]["qty"]               = it["qty"]     # qty không đổi
    merged[key]["item_amount"]       += it["item_amount"]
    merged[key]["applicable_charges"]+= it["applicable_charges"]

# Chỉ in phần gộp nếu có item bị tách dòng
if len(merged) < len(ITEMS):
    sec("Tóm tắt gộp (merged) — 1 item_code = 1 dòng")
    hdr = f"  {'item_code':14} {'qty':>5} {'Giá gốc':>16} {'Landed CP':>12} {'Giá vốn mới':>14} {'LC%':>6}"
    print()
    print(hdr)
    print(f"  {'─'*67}")
    for (vno, icode), m in merged.items():
        lc  = m["applicable_charges"]
        amt = m["item_amount"]
        qty = m["qty"]
        new_total = amt + lc
        print(f"  {icode:14} {qty:>5} {amt:>16,.0f} {lc:>12,.0f} "
              f"{new_total:>14,.0f} {lc/amt*100:>5.2f}%")

# ── Kiểm tra ──────────────────────────────────────────────────────────────────
sec("Kiểm tra")
tong_allocated = sum(it["applicable_charges"] for it in ITEMS)
ok("Tổng phân bổ = Tổng nguồn",
   f"{tong_allocated:,.0f} = {tong_cp:,.0f}  "
   f"{'✓' if abs(tong_allocated - tong_cp) < 1 else '⚠ chênh ' + str(round(abs(tong_allocated-tong_cp)))}")

for c in COSTS:
    allocated = c.get("allocated_amount", 0)
    diff = abs(c["amount"] - allocated)
    ok(f"{c['expense_name'][:35]:35} ({c['allocation_method']:14})",
       f"{allocated:>10,.0f} / {c['amount']:>10,.0f}  "
       f"{'✓' if diff < 1 else '⚠ chênh ' + str(round(diff))}")

# ── JSON detail (lưu vào field allocated_detail trên ERPNext) ─────────────────
sec("allocated_detail — JSON (lưu vào field ẩn, dùng cho audit + GL entries)")
print(json.dumps(allocated_detail[:4], ensure_ascii=False, indent=2))
if len(allocated_detail) > 4:
    print(f"  ... và {len(allocated_detail)-4} dòng nữa "
          f"(tổng {len(allocated_detail)} lines)")

print(f"\n{'═'*W}")
print("  ✅  Hoàn thành — chỉnh sửa ITEMS và COSTS ở trên để test với data thật")
print(f"{'═'*W}\n")
