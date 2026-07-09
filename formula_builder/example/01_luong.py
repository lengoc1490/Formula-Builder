# payroll_calculation.py (đã bổ sung trace + audit)
# from engine_final import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
# from engine_v2 import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
# from engine_v4 import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
# from engine_v5 import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
# from engine_v10 import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
from engine_v28 import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
import random
import time
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

formulas_payroll = [
    {"name": "LuongCB", "formula": "he_so * muc_luong_co_ban"},
    {"name": "PhuCap", "formula": "SUM(so_tien for loai, so_tien in ds_phu_cap)"},
    {"name": "Thuong", "formula": "sum(thuong for loai, thuong in ds_thuong)"},
    {"name": "TongThuNhap", "formula": "LuongCB + PhuCap + Thuong"},
    
    {"name": "BH_TN", "formula": "LuongCB * 0.105"},
    {"name": "GiamTruGiaCanh", "formula": "11000000 + 4400000 * so_nguoi_phu_thuoc"},
    {"name": "ThuNhapChiuThue", "formula": "max(TongThuNhap - BH_TN - GiamTruGiaCanh, 0)"},

    {"name": "Thue_Bac1", "formula": "min(ThuNhapChiuThue, 5000000) * 0.05"},
    {"name": "Thue_Bac2", "formula": "IF(ThuNhapChiuThue > 5000000, min(ThuNhapChiuThue - 5000000, 5000000) * 0.1, 0)"},
    {"name": "Thue_Bac3", "formula": "if(ThuNhapChiuThue > 10000000, Min(ThuNhapChiuThue - 10000000, 8000000) * 0.15, 0)"},
    {"name": "Thue_Bac4", "formula": "IF(ThuNhapChiuThue > 18000000, min(ThuNhapChiuThue - 18000000, 14000000) * 0.2, 0)"},
    {"name": "Thue_Bac5", "formula": "IF(ThuNhapChiuThue > 32000000, MIN(ThuNhapChiuThue - 32000000, 28000000) * 0.25, 0)"},
    {"name": "Thue_Bac6", "formula": "IF(ThuNhapChiuThue > 60000000, min(ThuNhapChiuThue - 60000000, 36000000) * 0.3, 0)"},
    {"name": "Thue_Bac7", "formula": "IF(ThuNhapChiuThue > 96000000, (ThuNhapChiuThue - 96000000) * 0.35, 0)"},

    {"name": "ThueTNCN", "formula": "Thue_Bac1 + Thue_Bac2 + Thue_Bac3 + Thue_Bac4 + Thue_Bac5 + Thue_Bac6 + Thue_Bac7"},
    {"name": "LuongThucLinh", "formula": "TongThuNhap - BH_TN - ThueTNCN"},
]


# Tạo 3 instance khác nhau theo nhu cầu
core_engine = FormulaEngineCore(formulas_payroll, on_error="default", default_value=0)
trace_engine = FormulaEngineTrace(formulas_payroll, on_error="default", default_value=0)
audit_engine = FormulaEngineAudit(formulas_payroll, on_error="default", default_value=0)

N = 1_000_000
NHAN_VIEN = []

muc_luong_cb = [4870000, 6000000, 8000000, 12000000, 18000000]

for i in range(N):
    NHAN_VIEN.append({
        "ma_nv": f"NV{i+1:06d}",
        "ten": f"Nguyễn Văn {chr(65 + i%26)}",
        "he_so": round(random.uniform(3.5, 12.0), 2),
        "muc_luong_co_ban": random.choice(muc_luong_cb),
        "so_nguoi_phu_thuoc": random.randint(0, 3),
        "ds_phu_cap": [
            ("Ăn trưa", random.choice([0, 730000, 1000000])),
            ("Xăng xe", random.choice([0, 500000, 800000])),
            ("Điện thoại", random.choice([0, 300000, 500000])),
        ],
        "ds_thuong": [
            ("Thưởng doanh số", random.randint(0, 5000000)),
            ("Thưởng lễ", random.choice([0, 1000000, 2000000])),
        ]
    })
    
# Hàm tính lương với các mode khác nhau
def calc_payroll(nv, mode="core", print_tree=False, trace_fields=None, audit=False, target_output="LuongThucLinh"):
    engine = {
        "core": core_engine,
        "trace": trace_engine,
        "audit": audit_engine
    }.get(mode, core_engine)

    if mode == "audit":
        # Bắt đầu session audit
        session = audit_engine.begin_audit_session(force_materialize=True, sample_rate=0.01)
        result = engine.calculate(
            nv,
            trace_fields=trace_fields,
            explain_ui=print_tree,
            audit=True
        )
        # Kết thúc session và lấy report
        _, report = engine.calculate_batch([nv], trace_fields=trace_fields, audit=True, target_output=target_output)
        if report and print_tree:
            print(report.summary())
            if report.execution_tree:
                print("\nExecution Tree (audit lineage):")
                print(report.execution_tree.to_tree_string(show_values=True, show_formula=True))
        return result["LuongThucLinh"]

    elif mode == "trace" and trace_fields:
        result = engine.calculate(
            nv,
            trace_fields=trace_fields,
            explain_ui=print_tree
        )
        if print_tree and "explain_ui" in result:
            print(f"\nTrace explain cho {nv['ma_nv']} - {nv['ten']}:")
            print(result["explain_ui"])
        return result["LuongThucLinh"]

    else:
        # Mode core nhanh nhất
        result = engine.calculate(nv)
        if print_tree:
            # In bảng lương như cũ
            print(f"\nBẢNG LƯƠNG - {nv['ma_nv']} - {nv['ten']}")
            print("-" * 90)
            print(f"{'Khoản mục':35} {'Số tiền (VND)':>25}")
            print(f"  {'Lương cơ bản':33} {result['LuongCB']:25,.0f}")
            print(f"  {'Phụ cấp':33} {result['PhuCap']:25,.0f}")
            print(f"  {'Thưởng':33} {result['Thuong']:25,.0f}")
            print(f"  {'-'*60}")
            print(f"  {'TỔNG THU NHẬP':33} {result['TongThuNhap']:25,.0f}")
            print(f"  {'Bảo hiểm trừ':33} {result['BH_TN']:25,.0f}")
            print(f"  {'Thuế TNCN':33} {result['ThueTNCN']:25,.0f}")
            print(f"  {'='*60}")
            print(f"  {'LƯƠNG THỰC LÃNH':33} {result['LuongThucLinh']:25,.0f}")
            print("=" * 90)
        return result["LuongThucLinh"]

# Test với các mode
t0 = time.time()

# Mode core: nhanh nhất, 1M nhân viên
for i, nv in enumerate(NHAN_VIEN):
    if i < 10:
        calc_payroll(nv, mode="core", print_tree=True)
    else:
        calc_payroll(nv, mode="core")

t1 = time.time()
print(f"\n⏱ Core mode (1M NV): {t1-t0:.2f}s | Avg: {(t1-t0)/N*1000:.3f} ms/NV")

# Mode trace selective (chỉ trace vài field cho 100 NV đầu)
t0 = time.time()
for i, nv in enumerate(NHAN_VIEN[:100]):
    calc_payroll(nv, mode="trace", trace_fields={"LuongThucLinh", "ThueTNCN", "TongThuNhap"}, print_tree=True)
t1 = time.time()
print(f"\n⏱ Trace mode (100 NV): {t1-t0:.2f}s")

# Mode audit forensic (chỉ bật cho 10 NV đầu, có tree lineage)
t0 = time.time()
for i, nv in enumerate(NHAN_VIEN[:10]):
    calc_payroll(nv, mode="audit", print_tree=True, target_output="LuongThucLinh")
t1 = time.time()
print(f"\n⏱ Audit mode (10 NV): {t1-t0:.2f}s")