# test_100k_products_with_bom_levels_fixed.py — Ví dụ BOM đa cấp 100k sản phẩm
# Cách chạy: python3 04_multiple_bom.py
from formula_builder.formula_utils import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
import random
import time
from collections import defaultdict
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')


# =====================================================
# TEMPLATE BOM – Tính tiền với unique NVL (fix SUM → sum)
# =====================================================
formulas_bom = [
    {"name": "VL_total", "formula": "sum(kl * don_gia if type_=='VL' and nvl not in nvl_seen else 0 for kl, don_gia, type_, nvl, nvl_seen in boms)"},
    {"name": "VLP_total", "formula": "sum(kl * don_gia if type_=='VLP' else 0 for kl, don_gia, type_, nvl, nvl_seen in boms)"},
    {"name": "NC_total", "formula": "sum(kl * don_gia if type_=='NC' else 0 for kl, don_gia, type_, nvl, nvl_seen in boms)"},
    {"name": "CM_total", "formula": "sum(kl * don_gia if type_=='CM' else 0 for kl, don_gia, type_, nvl, nvl_seen in boms)"},
    {"name": "TT", "formula": "VL_total + VLP_total + NC_total + CM_total"},
    {"name": "CPC", "formula": "TT * 0.05"},
    {"name": "DG", "formula": "TT + CPC"},
]

# Tạo engine theo mode
core_engine = FormulaEngineCore(formulas_bom, on_error="default", default_value=0)
trace_engine = FormulaEngineTrace(formulas_bom, on_error="default", default_value=0)
audit_engine = FormulaEngineAudit(formulas_bom, on_error="default", default_value=0)

# =====================================================
# DỮ LIỆU MẪU NVL, TYPE, ĐƠN GIÁ (giữ nguyên)
# =====================================================
NVL_POOL = [
    "Cát", "Đá", "Xi măng", "Thép cây D16", "Thép tấm SS400",
    "Dây cáp điện", "Ống nước PVC", "Giấy decal", "Mực in", "Keo 502",
    "NC lắp ráp", "NC hàn", "NC sơn", "Máy cắt CNC", "Máy uốn", "Máy tiện"
]

TYPE_MAP = {
    "Cát": "VL", "Đá": "VL", "Xi măng": "VL", "Thép cây D16": "VL", "Thép tấm SS400": "VL",
    "Dây cáp điện": "VLP", "Ống nước PVC": "VLP", "Giấy decal": "VLP", "Mực in": "VLP", "Keo 502": "VLP",
    "NC lắp ráp": "NC", "NC hàn": "NC", "NC sơn": "NC",
    "Máy cắt CNC": "CM", "Máy uốn": "CM", "Máy tiện": "CM"
}

DON_GIA_POOL = {nvl: random.randint(80000, 300000) for nvl in NVL_POOL}

# =====================================================
# SINH 100K SẢN PHẨM VỚI CẤP BOM TRONG CHI TIẾT (giữ nguyên)
# =====================================================
N_PRODUCTS = 100_000
PRODUCTS = []

for pid in range(N_PRODUCTS):
    n_chi_tiet = random.randint(2, 5)
    chi_tiets = []

    for _ in range(n_chi_tiet):
        n_bom = random.randint(2, 4)  # Mỗi chi tiết có 2-4 BOM
        bom_list = []

        for _ in range(n_bom):
            n_line = random.randint(3, 6)  # Mỗi BOM có 3-6 dòng NVL
            bom = []

            for _ in range(n_line):
                nvl = random.choice(NVL_POOL)
                type_ = TYPE_MAP[nvl]
                kl = random.uniform(5.0, 50.0) if type_ in ("VL", "VLP") else random.uniform(10.0, 100.0)
                don_gia = DON_GIA_POOL[nvl]
                bom.append((kl, don_gia, type_, nvl))

            bom_list.append(bom)

        chi_tiets.append({"bom_list": bom_list})

    PRODUCTS.append({
        "ma_sp": f"MA-SP-{pid+1:06d}",
        "ten_sp": f"Sản phẩm {pid+1:06d}",
        "qty": random.randint(1, 10),
        "chi_tiets": chi_tiets
    })

# =====================================================
# HÀM IN BẢNG ĐẸP (tương tự dự toán xây dựng)
# =====================================================
def print_header():
    print(f"{'Tên':20} {'Ký hiệu':8} {'KL':>12} {'Đơn giá':>12} {'Thành tiền':>15}")

def print_line(width=100):
    print("-" * width)

# =====================================================
# TÍNH VÀ IN DẠNG BẢNG CÂY VỚI CẤP BOM + THỐNG KÊ VL CHI TIẾT (bổ sung trace/audit)
# =====================================================
def calc_product(p, mode="core", print_tree=False, trace_fields=None, audit=False, target_output="DG"):
    total_VL = total_VLP = total_NC = total_CM = total_TT = total_CPC = total_DG = 0.0
    vl_detail = defaultdict(float)  # Thống kê KL VL theo mã NVL (unique)

    if mode == "audit":
        session = audit_engine.begin_audit_session(force_materialize=print_tree, sample_rate=0.1)

    if print_tree:
        print(f"\nSản phẩm: {p['ma_sp']} - {p['ten_sp']} (Số lượng: {p['qty']})")
        print("=" * 120)
        print_header()

    for ct_idx, ct in enumerate(p["chi_tiets"]):
        nvl_seen = set()
        ct_VL = ct_VLP = ct_NC = ct_CM = ct_TT = ct_CPC = ct_DG = 0.0

        if print_tree:
            print(f"  Chi tiết CT{ct_idx+1}:")
            print_line()

        for bom_idx, bom in enumerate(ct["bom_list"]):
            # Chuẩn bị input với nvl_seen
            bom_input = [(kl, dg, t, nvl, nvl_seen) for kl, dg, t, nvl in bom]

            engine = {
                "core": core_engine,
                "trace": trace_engine,
                "audit": audit_engine
            }.get(mode, core_engine)

            if mode == "audit":
                result_bom = engine.calculate({"boms": bom_input}, audit=True)
            elif mode == "trace" and trace_fields:
                result_bom = engine.calculate({"boms": bom_input}, trace_fields=trace_fields, explain_ui=print_tree)
            else:
                result_bom = engine.calculate({"boms": bom_input})

            ct_VL += result_bom["VL_total"]
            ct_VLP += result_bom["VLP_total"]
            ct_NC += result_bom["NC_total"]
            ct_CM += result_bom["CM_total"]
            ct_TT += result_bom["TT"]
            ct_CPC += result_bom["CPC"]
            ct_DG += result_bom["DG"]

            # Thống kê KL VL chi tiết theo mã NVL (unique)
            for kl, dg, t, nvl, _ in bom_input:
                if t == 'VL':
                    if nvl not in nvl_seen:
                        vl_detail[nvl] += kl * p['qty']
                    nvl_seen.add(nvl)

            if print_tree:
                print(f"    Bom {bom_idx+1}:")
                for kl, dg, t, nvl, _ in bom_input:
                    thanh_tien = kl * dg if (t != 'VL' or nvl not in nvl_seen) else 0
                    if thanh_tien > 0 or t != 'VL':  # In cả nếu không phải VL trùng
                        print(f"      {nvl:18} {t:8} {kl:12,.1f} {dg:12,} {thanh_tien:15,.0f}")
                print(f"      {'-'*70}")
                print(f"      {'CPTT':18} {'VL+VLP+NC+CM':8} {'':12} {'':12} {result_bom['TT']:15,.0f}")
                print(f"      {'Chi phí chung':18} {'5%':8} {'':12} {'':12} {result_bom['CPC']:15,.0f}")
                print(f"      {'Đơn giá Bom':18} {'':8} {'':12} {'':12} {result_bom['DG']:15,.0f}")
                print()

        # Cộng dồn chi tiết vào tổng sản phẩm (nhân qty)
        total_VL += ct_VL * p['qty']
        total_VLP += ct_VLP * p['qty']
        total_NC += ct_NC * p['qty']
        total_CM += ct_CM * p['qty']
        total_TT += ct_TT * p['qty']
        total_CPC += ct_CPC * p['qty']
        total_DG += ct_DG * p['qty']

        if print_tree:
            print(f"  Tổng chi tiết CT{ct_idx+1} (x{p['qty']}):")
            print(f"    {'CPTT':18} {'':8} {'':12} {'':12} {ct_TT * p['qty']:15,.0f}")
            print(f"    {'Chi phí chung':18} {'':8} {'':12} {'':12} {ct_CPC * p['qty']:15,.0f}")
            print(f"    {'Đơn giá chi tiết':18} {'':8} {'':12} {'':12} {ct_DG * p['qty']:15,.0f}")
            print("-" * 120)

    # Cấu trúc sản phẩm cuối + thống kê VL chi tiết
    if print_tree:
        don_gia_sp = total_DG / p['qty'] if p['qty'] > 0 else 0
        thanh_tien_sp = total_DG
        print(f"Tổng sản phẩm:")
        print(f"  Mã SP: {p['ma_sp']}")
        print(f"  Tên SP: {p['ten_sp']}")
        print(f"  Số lượng: {p['qty']}")
        print(f"  Đơn giá: {don_gia_sp:,.0f}")
        print(f"  Thành tiền: {thanh_tien_sp:,.0f}")
        print("\n  Thống kê VL chi tiết (cho sx):")
        for nvl, kl_total in sorted(vl_detail.items()):
            print(f"    {nvl:20} {kl_total:12,.1f}")
        print("=" * 120)

    if mode == "audit":
        _, report = audit_engine.calculate_batch([], audit=True, target_output=target_output)
        if report and print_tree:
            print("\nAUDIT REPORT:")
            print(report.summary())
            if report.execution_tree:
                print("\nAudit Lineage Tree (từ DG):")
                print(report.execution_tree.to_tree_string(show_values=True, show_formula=True))

    return {
        "VL": total_VL, "VLP": total_VLP, "NC": total_NC, "CM": total_CM,
        "TT": total_TT, "CPC": total_CPC, "DG": total_DG,
        "vl_detail": vl_detail  # Trả về thống kê VL chi tiết
    }

# =====================================================
# CHẠY TEST – IN CHI TIẾT 10 SẢN PHẨM ĐẦU
# =====================================================
t0 = time.time()

for i, prod in enumerate(PRODUCTS):
    calc_product(prod, print_tree=(i < 10), mode="audit", target_output="DG")  # Bật audit cho 10 đầu

t1 = time.time()

print(f"\n⏱ Thời gian tính {N_PRODUCTS:,} sản phẩm: {t1 - t0:.2f} giây")
print(f"   Trung bình: {(t1 - t0) / N_PRODUCTS * 1000:.3f} ms/sản phẩm")