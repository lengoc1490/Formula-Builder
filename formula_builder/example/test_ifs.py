from engine_v28 import FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
import random
import time
from collections import defaultdict
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')


# Công thức (viết gọn, rõ ràng)
formulas = [
    {
        "name": "result",
        "formula": "IF(C<B,(A-B)/(C-B),IF(A<=C,1,0))"
    }
]

engine = FormulaEngineCore(formulas)

# Input của bạn
inputs = {'A': 60.0, 'B': 70.0, 'C': 45.0}

# Kiểm tra kiểu dữ liệu
print("Kiểu dữ liệu:", {k: type(v) for k, v in inputs.items()})

# Tính
result = engine.calculate(inputs)
print("Kết quả:", result)

# Nếu vẫn sai, thử ép kiểu rõ ràng
inputs_safe = {k: float(v) for k, v in inputs.items()}
result_safe = engine.calculate(inputs_safe)
print("Kết quả sau ép float:", result_safe)


formulas = [
    {"name": "TongDoanhThuThang1", "formula": "sumifs(doanhthu, thang, '2025-01')"},
    {"name": "SoDonThang1", "formula": "countifs(thang, '2025-01')"},
    {"name": "DoanhThuTrungBinhThang1", "formula": "averageif(thang, '2025-01', doanhthu)"}
]

context = {
    "thang": ["2025-01", "2025-01", "2025-02", "2025-01"],
    "doanhthu": [50000000, 30000000, 40000000, 70000000]
}
engine = FormulaEngineCore(formulas)
result = engine.calculate(context)
print(f"Doanh thu tháng 1: {result['TongDoanhThuThang1']:,}")
print(f"Số đơn tháng 1: {result['SoDonThang1']}")
print(f"Trung bình tháng 1: {result['DoanhThuTrungBinhThang1']:,}")

formulas = [
    {"name": "ViTri", "formula": "match(ma_vt, [r[0] for r in bang_gia], 0)"},
    {"name": "DonGia", "formula": "index(bang_gia, ViTri, 2)"},
    {"name": "VatTuDat", "formula": "filter_array(ds_gia, '>', 200000)"},
    {"name": "DanhSachDat", "formula": "textjoin(', ', True, [n for q, dg, t, n in bom if dg > 200000])"},
    {"name": "KetQua", "formula": "ifs(DonGia > 300000, 'Cao cấp', DonGia > 200000, 'Trung cấp', 'Tiết kiệm')"}
]

context = {
    "ma_vt": "VT002",
    "bang_gia": [("VT001", 150000), ("VT002", 250000), ("VT003", 350000)],
    "ds_gia": [150000, 250000, 180000, 300000],
    "bom": [(10, 250000, "VL", "Thép"), (5, 300000, "VL", "Gạch"), (3, 150000, "NC", "Công")]
}

engine = FormulaEngineCore(formulas)
result = engine.calculate(context)
print(f"Vị trí: {result['ViTri']}")
print(f"Đơn giá: {result['DonGia']:,}")
print(f"Vật tư đặt: {result['VatTuDat']}")
print(f"Danh sách đặt: {result['DanhSachDat']}")
print(f"Kết quả: {result['KetQua']}")


formulas_cua_so_1canh = [
    # ===== NHÔM =====
    {
        "name": "ChieuDaiNhom",
        "formula": "(2 * H + 2 * W + hao_hut) / 1000",  # Đổi mm → m
        "group": "nhom"
    },
    {
        "name": "ChiPhiNhom",
        "formula": "ChieuDaiNhom * don_gia_nhom",
        "bucket": "nhom",
        "group": "nhom"
    },
    
    # ===== KÍNH =====
    {
        "name": "DienTichKinh",
        "formula": "(W * H) / 1000000",  # mm² → m²
        "group": "kinh"
    },
    {
        "name": "ChiPhiKinh",
        "formula": "DienTichKinh * don_gia_kinh",
        "bucket": "kinh",
        "group": "kinh"
    },
    
    # ===== PHỤ KIỆN =====
    {
        "name": "ChiPhiPhuKien",
        "formula": "so_canh * don_gia_phu_kien",
        "bucket": "phu_kien",
        "group": "phu_kien"
    },
    
    # ===== TỔNG CHI PHÍ =====
    {
        "name": "TongChiPhi",
        "formula": "ChiPhiNhom + ChiPhiKinh + ChiPhiPhuKien",
        "group": "tong_hop"
    },
    
    # ===== GIÁ BÁN =====
    {
        "name": "GiaBan",
        "formula": "TongChiPhi * he_so_loi_nhuan",
        "group": "tong_hop"
    },
    
    # ===== GIÁ/M² (QUY CHUẨN) =====
    {
        "name": "GiaBanM2",
        "formula": "safe_div(GiaBan, DienTichKinh, 0)",
        "group": "tong_hop"
    }
]

# Context mẫu
context = {
    # Kích thước (mm)
    "W": 1200,
    "H": 1500,
    "hao_hut": 200,  # Hao hụt cắt, nối (mm)
    
    # Cấu hình
    "so_canh": 1,
    
    # Đơn giá
    "don_gia_nhom": 180000,      # VND/m
    "don_gia_kinh": 450000,      # VND/m²
    "don_gia_phu_kien": 150000,  # VND/bộ
    
    # Hệ số
    "he_so_loi_nhuan": 1.35      # Lãi 35%
}

# Execute
engine = FormulaEngineCore(formulas_cua_so_1canh)
result = engine.calculate(context)

print(f"Giá bán: {result['GiaBan']:,} VND")
print(f"Giá/m²: {result['GiaBanM2']:,} VND/m²")