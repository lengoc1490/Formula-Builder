# du_toan_xd_grouping_multi_template_full_print.py
# ĐÃ FIX: chạy 100.000 dự án, có trace + audit mẫu, in bảng đúng
# from engine_final import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
# from engine_v2 import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
# from engine_v3 import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
# from engine_v10 import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
from engine_v28 import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
import random
import time
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')


try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda iterable, **kwargs: iterable  # fallback nếu không có tqdm

# =====================================================
# HÀM IN BẢNG ĐẸP (định nghĩa trước để dùng trong hàm)
# =====================================================
def print_header():
    print(f"{'Tên vật tư/định mức':<35} {'Ký hiệu':<8} {'KL':>15} {'Đơn giá':>15} {'Thành tiền':>20}")

def print_line(width=100):
    print("-" * width)

# =====================================================
# TEMPLATE RIÊNG CHO TỪNG LOẠI CÔNG TÁC (giữ nguyên)
# =====================================================
formulas_dao = [
    {"name": "VL", "formula": "sum(kl * don_gia for kl, don_gia, type_, ten in bom if type_=='VL')"},
    {"name": "NC", "formula": "sum(kl * don_gia for kl, don_gia, type_, ten in bom if type_=='NC')"},
    {"name": "CM", "formula": "sum(kl * don_gia for kl, don_gia, type_, ten in bom if type_=='CM')"},
    {"name": "TT", "formula": "VL + NC + CM"},
    {"name": "CPC", "formula": "TT * 0.08"},
    {"name": "VAT", "formula": "TT * 0.1"},
    {"name": "DG", "formula": "TT + CPC + VAT"},
]

formulas_do_bt = [
    {"name": "VL", "formula": "sum(kl * don_gia for kl, don_gia, type_, ten in bom if type_=='VL')"},
    {"name": "VLK", "formula": "sum(kl * don_gia for kl, don_gia, type_, ten in bom if type_=='VLK')"},
    {"name": "NC", "formula": "sum(kl * don_gia for kl, don_gia, type_, ten in bom if type_=='NC')"},
    {"name": "CM", "formula": "sum(kl * don_gia for kl, don_gia, type_, ten in bom if type_=='CM')"},
    {"name": "TT", "formula": "VL + VLK + NC + CM"},
    {"name": "CPC", "formula": "TT * 0.12"},
    {"name": "VAT", "formula": "TT * 0.1"},
    {"name": "DG", "formula": "TT + CPC + VAT"},
]

formulas_cot_van = [
    {"name": "VL", "formula": "sum(kl * don_gia for kl, don_gia, type_, ten in bom if type_=='VL')"},
    {"name": "NC", "formula": "sum(kl * don_gia for kl, don_gia, type_, ten in bom if type_=='NC')"},
    {"name": "TT", "formula": "VL + NC"},
    {"name": "CPC", "formula": "TT * 0.1"},
    {"name": "VAT", "formula": "TT * 0.1"},
    {"name": "DG", "formula": "TT + CPC + VAT"},
]

formulas_default = [
    {"name": "VL", "formula": "sum(kl * don_gia for kl, don_gia, type_, ten in bom if type_=='VL')"},
    {"name": "VLK", "formula": "sum(kl * don_gia for kl, don_gia, type_, ten in bom if type_=='VLK')"},
    {"name": "NC", "formula": "sum(kl * don_gia for kl, don_gia, type_, ten in bom if type_=='NC')"},
    {"name": "CM", "formula": "sum(kl * don_gia for kl, don_gia, type_, ten in bom if type_=='CM')"},
    {"name": "TT", "formula": "VL + VLK + NC + CM"},
    {"name": "CPC", "formula": "TT * 0.1"},
    {"name": "VAT", "formula": "TT * 0.1"},
    {"name": "DG", "formula": "TT + CPC + VAT"},
]

# Tạo engine
core_engine = FormulaEngineCore(formulas_default, on_error="default", default_value=0)
trace_engine = FormulaEngineTrace(formulas_default, on_error="default", default_value=0)
audit_engine = FormulaEngineAudit(formulas_default, on_error="default", default_value=0)

ENGINE_MAP = {
    "Đào đất": core_engine,
    "Vận chuyển đất": core_engine,
    "Đổ bê tông lót": core_engine,
    "Bê tông móng": core_engine,
    "Bê tông tầng": core_engine,
    "Bê tông mái": core_engine,
    "Cốt thép móng": core_engine,
    "Cốt thép tầng": core_engine,
    "Cốt thép mái": core_engine,
    "Ván khuôn móng": core_engine,
    "Ván khuôn tầng": core_engine,
    "Ván khuôn mái": core_engine,
}

# =====================================================
# ĐƠN GIÁ VÀ ĐƠN VỊ
# =====================================================
DON_GIA = {
    "Đất đào": ("VL", 150_000, "m³"),
    "Vận chuyển đất": ("VL", 120_000, "m³"),
    "Bê tông lót": ("VL", 1_800_000, "m³"),
    "Cốt thép": ("VL", 19_500, "kg"),
    "Ván khuôn": ("VL", 450_000, "m²"),
    "Bê tông móng": ("VL", 1_950_000, "m³"),
    "Xi măng": ("VLK", 1_400_000, "tấn"),
    "Cát": ("VLK", 350_000, "m³"),
    "Đá": ("VLK", 400_000, "m³"),
    "NC đào": ("NC", 250_000, "công"),
    "NC đổ BT": ("NC", 220_000, "công"),
    "NC tháo cốp pha": ("NC", 100_000, "công"),
    "Máy đào": ("CM", 1_200_000, "giờ"),
    "Máy trộn": ("CM", 250_000, "ca"),
    "Cẩu": ("CM", 1_500_000, "ca"),
}

# =====================================================
# SINH 100.000 DỰ ÁN
# =====================================================
N_DU_AN = 100_000
print(f"Đang sinh {N_DU_AN:,} dự án...")

DU_AN_LIST = []
for _ in range(N_DU_AN):
    du_an = {
        "ma_da": f"DA{random.randint(10000,999999)}",
        "ten_da": f"Dự án xây dựng nhà dân dụng {random.randint(1,999999)}",
        "phan": {}
    }

    # Phần móng (rút gọn để nhanh)
    du_an["phan"]["mong"] = [
        {"cong_viec": "Đào đất", "bom": [(random.uniform(100, 500), 150000, "VL", "Đất đào"),
                                         (random.uniform(50, 200), 250000, "NC", "NC đào"),
                                         (random.uniform(10, 50), 1200000, "CM", "Máy đào")]},
        {"cong_viec": "Bê tông móng", "bom": [(random.uniform(50, 200), 1950000, "VL", "Bê tông móng"),
                                              (random.uniform(100, 300), 400000, "VLK", "Đá")]}
    ]

    # Phần thân (2-4 tầng)
    du_an["phan"]["than"] = {}
    n_tang = random.randint(2, 4)
    for tang in range(1, n_tang + 1):
        du_an["phan"]["than"][f"Tầng {tang}"] = [
            {"cong_viec": "Cốt thép tầng", "bom": [(random.uniform(3000, 10000), 19500, "VL", "Cốt thép")]},
            {"cong_viec": "Bê tông tầng", "bom": [(random.uniform(80, 300), 1950000, "VL", "Bê tông tầng")]}
        ]

    # Phần mái
    du_an["phan"]["mai"] = [
        {"cong_viec": "Bê tông mái", "bom": [(random.uniform(30, 100), 1950000, "VL", "Bê tông mái")]}
    ]

    DU_AN_LIST.append(du_an)

print("Sinh dữ liệu xong.")

# =====================================================
# HÀM TÍNH DỰ TOÁN (đã fix đầy đủ)
# =====================================================
def calc_du_toan(da, mode="core", print_tree=False, trace_fields=None, audit=False, target_output="DG"):
    total_TT = total_CPC = total_VAT = total_DG = 0.0

    if mode == "audit":
        session = audit_engine.begin_audit_session(force_materialize=print_tree, sample_rate=0.1)

    if print_tree:
        print(f"\nDỰ ÁN: {da['ma_da']} - {da['ten_da']}")
        print("=" * 120)

    for phan_key, phan_data in da["phan"].items():
        phan_TT = phan_CPC = phan_VAT = phan_DG = 0.0

        if print_tree:
            print(f"\nI. PHẦN {phan_key.upper()}:")
            print_line()

        if phan_key == "than":
            for tang_key, tang_cv in phan_data.items():
                tang_TT = tang_CPC = tang_VAT = tang_DG = 0.0

                if print_tree:
                    print(f"  {tang_key.upper()}:")
                    print_line()

                for cv in tang_cv:
                    engine = {
                        "core": core_engine,
                        "trace": trace_engine,
                        "audit": audit_engine
                    }[mode]

                    bom = cv.get("bom", [])
                    if mode == "audit":
                        result = engine.calculate({"bom": bom}, audit=True)
                    elif mode == "trace" and trace_fields:
                        result = engine.calculate({"bom": bom}, trace_fields=trace_fields, explain_ui=print_tree)
                    else:
                        result = engine.calculate({"bom": bom})

                    tang_TT += result.get("TT", 0)
                    tang_CPC += result.get("CPC", 0)
                    tang_VAT += result.get("VAT", 0)
                    tang_DG += result.get("DG", 0)

                    if print_tree:
                        print(f"    Công việc: {cv['cong_viec']}")
                        print_header()
                        for item in bom:
                            kl, dg, ky_hieu, ten = item
                            thanh_tien = kl * dg
                            don_vi = DON_GIA.get(ten, ("", 0, ""))[2]
                            print(f"      {ten:<33} {ky_hieu:<8} {kl:>12,.2f} {don_vi:>3} {dg:>15,} {thanh_tien:>20,}")
                        print_line()
                        print(f"      TỔNG TRỰC TIẾP (TT): {result.get('TT', 0):>20,}")
                        if "CPC" in result:
                            print(f"      Chi phí chung: {result.get('CPC', 0):>20,}")
                        if "VAT" in result:
                            print(f"      VAT 10%: {result.get('VAT', 0):>20,}")
                        print(f"      ĐƠN GIÁ CÔNG VIỆC: {result.get('DG', 0):>20,}")
                        print()

                phan_TT += tang_TT
                phan_CPC += tang_CPC
                phan_VAT += tang_VAT
                phan_DG += tang_DG

                if print_tree:
                    print(f"  TỔNG {tang_key.upper()}: TT = {tang_TT:>20,} | ĐƠN GIÁ TẦNG = {tang_DG:>20,}")
                    print_line()

        else:
            # Phần móng và mái
            for cv in phan_data:
                engine = {
                    "core": core_engine,
                    "trace": trace_engine,
                    "audit": audit_engine
                }[mode]

                bom = cv.get("bom", [])
                if mode == "audit":
                    result = engine.calculate({"bom": bom}, audit=True)
                elif mode == "trace" and trace_fields:
                    result = engine.calculate({"bom": bom}, trace_fields=trace_fields, explain_ui=print_tree)
                else:
                    result = engine.calculate({"bom": bom})

                phan_TT += result.get("TT", 0)
                phan_CPC += result.get("CPC", 0)
                phan_VAT += result.get("VAT", 0)
                phan_DG += result.get("DG", 0)

                if print_tree:
                    print(f"  Công việc: {cv['cong_viec']}")
                    print_header()
                    for item in bom:
                        kl, dg, ky_hieu, ten = item
                        thanh_tien = kl * dg
                        don_vi = DON_GIA.get(ten, ("", 0, ""))[2]
                        print(f"    {ten:<33} {ky_hieu:<8} {kl:>12,.2f} {don_vi:>3} {dg:>15,} {thanh_tien:>20,}")
                    print_line()
                    print(f"    TỔNG TRỰC TIẾP (TT): {result.get('TT', 0):>20,}")
                    if "CPC" in result:
                        print(f"    Chi phí chung: {result.get('CPC', 0):>20,}")
                    if "VAT" in result:
                        print(f"    VAT 10%: {result.get('VAT', 0):>20,}")
                    print(f"    ĐƠN GIÁ CÔNG VIỆC: {result.get('DG', 0):>20,}")
                    print()

        total_TT += phan_TT
        total_CPC += phan_CPC
        total_VAT += phan_VAT
        total_DG += phan_DG

        if print_tree:
            print(f"TỔNG PHẦN {phan_key.upper()}: TT = {phan_TT:>20,} | ĐƠN GIÁ PHẦN = {phan_DG:>20,}")
            print_line()

    if mode == "audit":
        _, report = audit_engine.calculate_batch([], audit=True, target_output=target_output)
        if report and print_tree:
            print("\nAUDIT REPORT:")
            print(report.summary())
            if report.execution_tree:
                print("\nAudit Lineage Tree (từ DG):")
                print(report.execution_tree.to_tree_string(show_values=True, show_formula=True))

    if print_tree:
        print(f"\nTỔNG DỰ ÁN:")
        print("-" * 100)
        print(f"  Tổng trực tiếp (TT): {total_TT:>20,}")
        print(f"  Tổng chi phí chung: {total_CPC:>20,}")
        print(f"  Tổng VAT: {total_VAT:>20,}")
        print("=" * 120)
        print(f"  TỔNG GIÁ TRỊ DỰ ÁN: {total_DG:>20,}")

    return total_DG

# =====================================================
# CHẠY TEST VỚI 100.000 DỰ ÁN
# =====================================================
print(f"\nBắt đầu tính {N_DU_AN:,} dự án...")

t0 = time.time()

# Mass run mode core cho full 100k
total_gia_tri = 0.0
for da in tqdm(DU_AN_LIST, desc="Tính dự án (core mode)", disable=False):
    gia_tri = calc_du_toan(da, mode="core")  # Không in để nhanh
    total_gia_tri += gia_tri

t1 = time.time()

print(f"\nHoàn thành tính {N_DU_AN:,} dự án ở mode core:")
print(f"  Tổng giá trị tất cả dự án: {total_gia_tri:,.0f} VND")
print(f"  Thời gian: {t1-t0:.2f}s")
print(f"  Trung bình: {(t1-t0)/N_DU_AN*1000:.3f} ms/dự án")

# Test trace + audit cho 10 dự án đầu (in chi tiết)
print("\nTest trace + audit cho 10 dự án đầu...")
for i, da in enumerate(DU_AN_LIST[:10]):
    calc_du_toan(da, mode="audit", print_tree=True, target_output="DG")