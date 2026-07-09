# ============================================================================
# Ví dụ FULL: Tính chi phí sản phẩm + tạo SNAPSHOT + so sánh
# Có thể copy và chạy trực tiếp (nếu đã có engine_v4.py)
# ============================================================================

from datetime import datetime
import random
import time
from collections import defaultdict
import json
import uuid

# Giả sử bạn đã có file engine_v4.py chứa các class sau:
from engine_v4 import FormulaEngineAudit, FormulaError

# ────────────────────────────────────────────────────────────────────────────
# 1. Định nghĩa công thức (BOM đơn giản)
# ────────────────────────────────────────────────────────────────────────────
formulas_bom = [
    {"name": "VL_total", "formula": "sum(kl * don_gia if type_=='VL' and nvl not in nvl_seen else 0 for kl, don_gia, type_, nvl, nvl_seen in boms)"},
    {"name": "VLP_total", "formula": "sum(kl * don_gia if type_=='VLP' else 0 for kl, don_gia, type_, nvl, nvl_seen in boms)"},
    {"name": "NC_total", "formula": "sum(kl * don_gia if type_=='NC' else 0 for kl, don_gia, type_, nvl, nvl_seen in boms)"},
    {"name": "CM_total", "formula": "sum(kl * don_gia if type_=='CM' else 0 for kl, don_gia, type_, nvl, nvl_seen in boms)"},
    {"name": "TT", "formula": "VL_total + VLP_total + NC_total + CM_total"},
    {"name": "CPC", "formula": "TT * 0.05"},
    {"name": "DG", "formula": "TT + CPC"},
]

# ────────────────────────────────────────────────────────────────────────────
# 2. Tạo engine
# ────────────────────────────────────────────────────────────────────────────
engine = FormulaEngineAudit(
    formulas_bom,
    on_error="default",
    default_value=0
)

# ────────────────────────────────────────────────────────────────────────────
# 3. Dữ liệu mẫu (nguyên vật liệu giả lập)
# ────────────────────────────────────────────────────────────────────────────
NVL_POOL = ["Cát", "Xi măng", "Thép D10", "Thép D16", "Gạch", "Sơn", "Ống nhựa", "Dây điện"]
TYPE_MAP = {
    "Cát": "VL", "Xi măng": "VL", "Thép D10": "VL", "Thép D16": "VL", "Gạch": "VL",
    "Sơn": "VLP", "Ống nhựa": "VLP", "Dây điện": "VLP",
}
DON_GIA = {n: random.randint(50000, 280000) for n in NVL_POOL}

# ────────────────────────────────────────────────────────────────────────────
# 4. Tạo dữ liệu sản phẩm mẫu (5 sản phẩm để demo)
# ────────────────────────────────────────────────────────────────────────────
PRODUCTS = []
for i in range(5):
    boms = []
    for _ in range(random.randint(4, 8)):  # 4-8 dòng nguyên vật liệu
        nvl = random.choice(NVL_POOL)
        type_ = TYPE_MAP[nvl]
        kl = round(random.uniform(0.5, 25.0), 2) if type_ in ("VL", "VLP") else round(random.uniform(5, 60), 1)
        dg = DON_GIA[nvl]
        boms.append((kl, dg, type_, nvl))

    PRODUCTS.append({
        "ma_sp": f"SP-{i+1:03d}",
        "ten_sp": f"Sản phẩm mẫu {i+1}",
        "qty": random.randint(10, 50),
        "boms": boms,
        "ngay_tinh": datetime.now().strftime("%Y-%m-%d")
    })

# ────────────────────────────────────────────────────────────────────────────
# 5. Hàm tính + tạo snapshot + in kết quả
# ────────────────────────────────────────────────────────────────────────────
def tinh_va_tao_snapshot(sp, print_detail=False, tao_snapshot=False, tag="estimate"):
    nvl_seen = set()
    input_data = {
        "boms": [(kl, dg, t, nvl, nvl_seen) for kl, dg, t, nvl in sp["boms"]]
    }

    result = engine.calculate(input_data)

    # Tính tổng theo sản phẩm (nhân số lượng)
    total = {
        "VL": result["VL_total"] * sp["qty"],
        "VLP": result["VLP_total"] * sp["qty"],
        "NC": result["NC_total"] * sp["qty"],
        "CM": result["CM_total"] * sp["qty"],
        "TT": result["TT"] * sp["qty"],
        "CPC": result["CPC"] * sp["qty"],
        "DG": result["DG"] * sp["qty"],
        "Don_gia": result["DG"],
    }

    if print_detail:
        print(f"\n{'='*80}")
        print(f"SẢN PHẨM: {sp['ma_sp']} - {sp['ten_sp']}")
        print(f"Số lượng: {sp['qty']:,}   Ngày tính: {sp['ngay_tinh']}")
        print(f"{'-'*80}")
        print(f"{'Loại':8} {'Thành tiền':>15} {'Ghi chú':>20}")
        print(f"{'-'*80}")
        for k, v in total.items():
            if k != "Don_gia":
                print(f"{k:8} {v:15,.0f}")
        print(f"{'Don_gia':8} {total['Don_gia']:15,.0f} đ / sp")
        print(f"{'='*80}")

    snapshot = None
    if tao_snapshot:
        result_for_snap = {
            "VL": result["VL_total"],
            "VLP": result["VLP_total"],
            "NC": result["NC_total"],
            "CM": result["CM_total"],
            "TT": result["TT"],
            "CPC": result["CPC"],
            "DG": result["DG"],
            "Don_gia": result["DG"],
        }

        snapshot = engine.create_snapshot(
            inputs={
                "ma_sp": sp["ma_sp"],
                "ten_sp": sp["ten_sp"],
                "qty": sp["qty"],
                "ngay_tinh": sp["ngay_tinh"],
                # "boms": sp["boms"]   # có thể bỏ nếu dữ liệu lớn
            },
            result=result_for_snap,
            snapshot_name=f"{sp['ma_sp']}-{tag.upper()}",
            tag=tag,
            scenario="tinh_chi_phi_san_pham",
            project_code="DEMO-2026",
            created_by="test_user",
            meta={
                "so_luong": sp["qty"],
                "ngay_tinh": sp["ngay_tinh"],
                "so_dong_nvl": len(sp["boms"])
            },
            include_lineage=False,
            target_field_for_lineage="DG"
        )

        print(f"→ Đã tạo snapshot: {snapshot['snapshot_name']}")
        print(f"   Hash: {snapshot['integrity_hash'][:16]}...")

    return total, snapshot


# ────────────────────────────────────────────────────────────────────────────
# 6. Chạy thử
# ────────────────────────────────────────────────────────────────────────────
print("BẮT ĐẦU TÍNH TOÁN VÀ TẠO SNAPSHOT\n")

snapshots_luu = []

t0 = time.time()

for idx, sp in enumerate(PRODUCTS):
    print_detail = (idx < 3)          # in chi tiết 3 sản phẩm đầu
    tao_snap = True                   # tạo snapshot cho tất cả (demo)
    tag = "estimate" if idx < 2 else "plan" if idx < 4 else "actual"

    total, snap = tinh_va_tao_snapshot(
        sp,
        print_detail=print_detail,
        tao_snapshot=tao_snap,
        tag=tag
    )

    if snap:
        snapshots_luu.append({
            "ma_sp": sp["ma_sp"],
            "tag": tag,
            "DG": total["DG"],
            "TT": total["TT"],
            "snapshot_id": snap["snapshot_id"],
            "hash": snap["integrity_hash"][:12]
        })

t1 = time.time()

print(f"\nTổng thời gian: {t1-t0:.3f} giây cho {len(PRODUCTS)} sản phẩm")
print(f"Trung bình: {(t1-t0)/len(PRODUCTS)*1000:.2f} ms/sp\n")

# ────────────────────────────────────────────────────────────────────────────
# 7. So sánh nhanh các snapshot (demo)
# ────────────────────────────────────────────────────────────────────────────
print("SO SÁNH NHANH GIỮA CÁC SNAPSHOT:")
print(f"{'Mã SP':8} {'Tag':10} {'Đơn giá':>12} {'Thành tiền':>15} {'Snapshot ID':>20} {'Hash (prefix)':>14}")
print("-"*85)
for s in snapshots_luu:
    print(f"{s['ma_sp']:8} {s['tag']:10} {s['DG']:12,.0f} {s['TT']:15,.0f} {s['snapshot_id'][:20]} {s['hash']}")

print("\nHoàn tất. Bạn có thể mở rộng bằng cách lưu snapshots vào file hoặc database.")