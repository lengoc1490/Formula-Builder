# gia_thanh_san_xuat_complex.py — Ví dụ tính giá thành sản xuất phức tạp
# Cách chạy: python3 03_giathanh.py
from formula_builder.formula_utils import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
import random
import time
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# =====================================================
# HÀM IN BẢNG ĐẸP (tương tự tính giá xây dựng)
# =====================================================
def print_header():
    print(f"{'Khoản mục':<35} {'Ký hiệu':<8} {'Số lượng':>15} {'Đơn giá':>15} {'Thành tiền':>20}")

def print_line(width=100):
    print("-" * width)

# =====================================================
# TEMPLATE CHO NVL TRỰC TIẾP (Tính chi phí NVL chính)
# =====================================================
formulas_nvl = [
    {"name": "vlc_dau", "formula": "cong_doan[0][0] if cong_doan else 0"},
    {"name": "tong_vlp_nc_cm", "formula": "sum(dm_vlp + dm_nc + dm_cm for _, dm_vlp, dm_nc, dm_cm in cong_doan)"},
    {"name": "tt_nvl", "formula": "vlc_dau + tong_vlp_nc_cm"},
    {"name": "cpc_nvl", "formula": "tt_nvl * 0.1"},
    {"name": "vat_nvl", "formula": "tt_nvl * 0.1"},
    {"name": "dg_nvl", "formula": "tt_nvl + cpc_nvl + vat_nvl"},
]

# =====================================================
# TEMPLATE CHO CHI TIẾT SẢN PHẨM (Tổng NVL + chi phí nhân công + khấu hao máy)
# =====================================================
formulas_chitiet = [
    {"name": "tt_nvl_chitiet", "formula": "sum(dg_nvl for dg_nvl in dg_nvls)"},
    {"name": "chi_phi_nhan_cong", "formula": "so_gio_lao_dong * luong_gio"},
    {"name": "khau_hao_may_moc", "formula": "so_gio_may * chi_phi_khau_hao_gio"},
    {"name": "tt_chitiet", "formula": "tt_nvl_chitiet + chi_phi_nhan_cong + khau_hao_may_moc"},
]

# =====================================================
# TEMPLATE CHO SẢN PHẨM HOÀN THIỆN (Tổng chi tiết + phân bổ chi phí gián tiếp + quản lý)
# =====================================================
formulas_sp = [
    {"name": "tong_thanh_tien_chitiet", "formula": "sum(tt_chitiet for tt_chitiet in tt_chitiets)"},
    {"name": "chi_phi_gian_tiep", "formula": "tong_thanh_tien_chitiet * ty_le_gian_tiep"},
    {"name": "chi_phi_quan_ly", "formula": "tong_thanh_tien_chitiet * ty_le_quan_ly"},
    {"name": "tong_gia_thanh", "formula": "tong_thanh_tien_chitiet + chi_phi_gian_tiep + chi_phi_quan_ly"},
    {"name": "gia_thanh_sp", "formula": "safe_div(tong_gia_thanh, so_luong_sp, 0)"},
]

# Tạo engine theo mode (default dùng core cho nhanh)
core_nvl = FormulaEngineCore(formulas_nvl, on_error="default", default_value=0)
trace_nvl = FormulaEngineTrace(formulas_nvl, on_error="default", default_value=0)
audit_nvl = FormulaEngineAudit(formulas_nvl, on_error="default", default_value=0)

core_chitiet = FormulaEngineCore(formulas_chitiet, on_error="default", default_value=0)
trace_chitiet = FormulaEngineTrace(formulas_chitiet, on_error="default", default_value=0)
audit_chitiet = FormulaEngineAudit(formulas_chitiet, on_error="default", default_value=0)

core_sp = FormulaEngineCore(formulas_sp, on_error="default", default_value=0)
trace_sp = FormulaEngineTrace(formulas_sp, on_error="default", default_value=0)
audit_sp = FormulaEngineAudit(formulas_sp, on_error="default", default_value=0)

# =====================================================
# SINH 100K SẢN PHẨM (dữ liệu phức tạp nhiều thành phần)
# =====================================================
N_SAN_PHAM = 100_000
SAN_PHAM_LIST = []

for i in range(N_SAN_PHAM):
    sp = {
        "ma_sp": f"SP{i+1:06d}",
        "ten_sp": f"Sản phẩm cơ khí {i+1}",
        "so_luong_sp": random.randint(50, 500),
        "ty_le_gian_tiep": random.uniform(0.05, 0.15),  # 5-15%
        "ty_le_quan_ly": random.uniform(0.03, 0.08),   # 3-8%
        "chi_tiet": []
    }
    
    n_chitiet = random.randint(3, 6)  # 3-6 chi tiết
    for _ in range(n_chitiet):
        chitiet = {
            "ten_chitiet": f"Chi tiết {_+1}",
            "nvl_chinh": [],
            "so_gio_lao_dong": random.uniform(10, 50),  # giờ nhân công
            "luong_gio": random.randint(100000, 300000),  # lương/giờ
            "so_gio_may": random.uniform(5, 20),  # giờ máy
            "chi_phi_khau_hao_gio": random.randint(50000, 150000)  # khấu hao/giờ
        }
        
        n_nvl = random.randint(4, 8)  # 4-8 NVL
        for _ in range(n_nvl):
            cong_doan = []
            n_cd = random.randint(3, 5)  # 3-5 công đoạn
            for j in range(n_cd):
                vlc = random.uniform(1000, 5000) if j == 0 else 0
                vlp = random.uniform(200, 1000)
                nc = random.uniform(300, 1500)
                cm = random.uniform(400, 2000)
                cong_doan.append((vlc, vlp, nc, cm))
            
            chitiet["nvl_chinh"].append(cong_doan)
        
        sp["chi_tiet"].append(chitiet)
    
    SAN_PHAM_LIST.append(sp)

# =====================================================
# HÀM TÍNH GIÁ THÀNH SẢN XUẤT (in chi tiết cách tính + kết quả như tính giá xây dựng)
# =====================================================
def calc_gia_thanh(sp, mode="core", print_tree=False, trace_fields=None, audit=False, target_output="gia_thanh_sp"):
    if print_tree:
        print(f"\nSẢN PHẨM: {sp['ma_sp']} - {sp['ten_sp']}")
        print("=" * 120)
        print(f"  Số lượng SP: {sp['so_luong_sp']}")
        print(f"  Tỷ lệ gián tiếp: {sp['ty_le_gian_tiep']*100:.2f}%")
        print(f"  Tỷ lệ quản lý: {sp['ty_le_quan_ly']*100:.2f}%")
        print("=" * 120)

    chi_tiet_results = []
    
    for idx_chitiet, chitiet in enumerate(sp["chi_tiet"]):
        if print_tree:
            print(f"\nI. CHI TIẾT: {chitiet['ten_chitiet']}")
            print_line()

        nvl_results = []
        for idx_nvl, cong_doan in enumerate(chitiet["nvl_chinh"]):
            if print_tree:
                print(f"  NVL {idx_nvl+1}:")
                print_header()

            engine = {
                "core": core_nvl,
                "trace": trace_nvl,
                "audit": audit_nvl
            }.get(mode, core_nvl)
            
            if mode == "audit":
                result = engine.calculate({"cong_doan": cong_doan}, audit=True)
            elif mode == "trace" and trace_fields:
                result = engine.calculate({"cong_doan": cong_doan}, trace_fields=trace_fields, explain_ui=print_tree)
            else:
                result = engine.calculate({"cong_doan": cong_doan})
            
            nvl_results.append(result["dg_nvl"])

            if print_tree:
                print_line()
                print(f"    {'TỔNG TRỰC TIẾP NVL':<33} {'':<8} {'':>15} {'':>15} {result['tt_nvl']:>20,}")
                print(f"    {'Chi phí chung NVL':<33} {'':<8} {'':>15} {'':>15} {result['cpc_nvl']:>20,}")
                print(f"    {'VAT NVL':<33} {'':<8} {'':>15} {'':>15} {result['vat_nvl']:>20,}")
                print_line()
                print(f"    {'ĐƠN GIÁ NVL':<33} {'':<8} {'':>15} {'':>15} {result['dg_nvl']:>20,}")
                print()

        chitiet_engine = {
            "core": core_chitiet,
            "trace": trace_chitiet,
            "audit": audit_chitiet
        }.get(mode, core_chitiet)

        chitiet_input = {
            "dg_nvls": nvl_results,
            "so_gio_lao_dong": chitiet["so_gio_lao_dong"],
            "luong_gio": chitiet["luong_gio"],
            "so_gio_may": chitiet["so_gio_may"],
            "chi_phi_khau_hao_gio": chitiet["chi_phi_khau_hao_gio"]
        }

        if mode == "audit":
            chitiet_result = chitiet_engine.calculate(chitiet_input, audit=True)
        elif mode == "trace" and trace_fields:
            chitiet_result = chitiet_engine.calculate(chitiet_input, trace_fields=trace_fields, explain_ui=print_tree)
        else:
            chitiet_result = chitiet_engine.calculate(chitiet_input)
        
        chi_tiet_results.append(chitiet_result["tt_chitiet"])

        if print_tree:
            print(f"  TỔNG CHI TIẾT: TT NVL = {chitiet_result['tt_nvl_chitiet']:>20,} | Nhân công = {chitiet_result['chi_phi_nhan_cong']:>20,} | Khấu hao = {chitiet_result['khau_hao_may_moc']:>20,}")
            print(f"  TỔNG CHI TIẾT: {chitiet_result['tt_chitiet']:>20,}")
            print_line()

    sp_engine = {
        "core": core_sp,
        "trace": trace_sp,
        "audit": audit_sp
    }.get(mode, core_sp)

    sp_input = {
        "tt_chitiets": chi_tiet_results,
        "so_luong_sp": sp["so_luong_sp"],
        "ty_le_gian_tiep": sp["ty_le_gian_tiep"],
        "ty_le_quan_ly": sp["ty_le_quan_ly"]
    }

    if mode == "audit":
        session = audit_sp.begin_audit_session(force_materialize=print_tree)
        result = sp_engine.calculate(sp_input, audit=True)
        _, report = sp_engine.calculate_batch([sp_input], audit=True, target_output=target_output)
        if report and print_tree:
            print("\nAUDIT REPORT:")
            print(report.summary())
            if report.execution_tree:
                print("\nAudit Lineage Tree (từ gia_thanh_sp):")
                print(report.execution_tree.to_tree_string(show_values=True, show_formula=True))
    elif mode == "trace" and trace_fields:
        result = sp_engine.calculate(sp_input, trace_fields=trace_fields, explain_ui=print_tree)
    else:
        result = sp_engine.calculate(sp_input)

    if print_tree:
        print(f"\nTỔNG SẢN PHẨM:")
        print_line()
        print(f"  Tổng chi tiết: {result['tong_thanh_tien_chitiet']:>20,}")
        print(f"  Chi phí gián tiếp: {result['chi_phi_gian_tiep']:>20,}")
        print(f"  Chi phí quản lý: {result['chi_phi_quan_ly']:>20,}")
        print_line()
        print(f"  TỔNG GIÁ THÀNH: {result['tong_gia_thanh']:>20,}")
        print(f"  GIÁ THÀNH / SP: {result['gia_thanh_sp']:>20,}")
        print("=" * 120)

    return result

# =====================================================
# CHẠY TEST
# =====================================================
t0 = time.time()
for i, sp in enumerate(SAN_PHAM_LIST):
    result = calc_gia_thanh(sp, mode="core")  # mode core cho full 100k
t1 = time.time()
print(f"\nThời gian tính 100k sản phẩm (mode core): {t1-t0:.2f}s | Avg: {(t1-t0)/N_SAN_PHAM*1000:.3f} ms/SP")

# Test audit + in chi tiết cho 3 SP đầu
print("\nTest audit + in chi tiết cho 3 sản phẩm đầu...")
for i, sp in enumerate(SAN_PHAM_LIST[:3]):
    result = calc_gia_thanh(sp, mode="audit", print_tree=True, target_output="gia_thanh_sp")
    print(f"SP {sp['ma_sp']}: Giá thành {result['gia_thanh_sp']:,.2f}")