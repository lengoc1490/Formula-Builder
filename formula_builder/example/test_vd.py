from formula_builder.formula_utils import FormulaEngine, FormulaEngineCore, FormulaEngineTrace, FormulaEngineAudit
import random
import time

# # 1. Định nghĩa công thức
# formulas = [
#     {"name": "Tong", "formula": "a + b"},
#     {"name": "TrungBinh", "formula": "Tong / 2"}
# ]

# # 2. Khởi tạo engine
# engine = FormulaEngineCore(formulas)

# # 3. Tính toán
# context = {"a": 10, "b": 20}
# result = engine.calculate(context)

# print(result["Tong"])         # 30
# print(result["TrungBinh"])  # 15.0
# print(result)


formulas = [
    {"name": "Tong", "formula": "a + b"},
    {"name": "Hieu", "formula": "a - b"},
    {"name": "Tich", "formula": "a * b * 10%"},
    {"name": "Thuong", "formula": "SAFE_DIV(a, b, 0)"},
    {"name": "logic", "formula": "if(Or_(ANd_(a, b)), 'Cả hai đều đúng', 'Ít nhất một sai')"},
    {"name": "logic2", "formula": "if(a==b, 'giatri1', 'giatri2')"},
]

engine = FormulaEngineCore(formulas)
result = engine.calculate({"a": 20, "b": 5})

print(result["Tong"])     # 25
print(result["Hieu"])     # 15
print(result["Tich"])     # 100
print(result["Thuong"])  # 4.0
print(result["logic"])   # 'Cả hai đều đúng'
print(result["logic2"])  # 'giatri2'


formulas = [
    {"name": "sumdata", "formula": "(sum(v1)/sum(v2))*100"},
]

engine = FormulaEngineCore(formulas)
result = engine.calculate({"v1": [20, 10], "v2": [5]})
print("sumdata:", result["sumdata"])     # 25



formulas = [
    {
        "name": "giatri",
        "formula": "IF(and_(T<L,A=L),0,IF(and_(T=0,L=0,A>=L),0,IF(and_(T<=L,A=0),100,IF(and_(T>L),0,IF(and_(L-T=0),0,IF(and_(T<=L,A<L),max(0,min(1,(L-A)/(L-T)))*100,IF(and_(A>L),0,IF(and_(A=T),50,IF(and_(A<T),max(0,min(1,(A-T)/(L-T)))*100,IF(and_(A>0,T>0,L>0),max(0,min(1,(A+T)/(L+T)))*100,IF(and_(A=0,T>0),0,IF(and_(A>0,T=0),100,0))))))))))))"
    },
]

engine = FormulaEngineCore(formulas)
result = engine.calculate({"A": 10, "L": 50, "T": 10})
print("giatri:", result["giatri"])     # 25


# formulas = [
#     {"name": "ChietKhau", "formula": "gia * 0.1 if so_luong >= 100 else 0"},
#     {"name": "ThanhTien", "formula": "gia * so_luong - ChietKhau"}
# ]

# engine = FormulaEngineCore(formulas)
# result = engine.calculate({"gia": 50000, "so_luong": 100})
# print(result["ThanhTien"])  # 5,400,000

formulas = [
    { "name": "giatri", "formula": "1.2 * diem" },
    { "name": "giatri2", "formula": "1.2 * diem" },
]

engine = FormulaEngineCore(formulas)
print(engine.calculate({"diem": 10})["giatri"]) 
print(engine.calculate({"diem": 10})["giatri2"]) 



formulas = [
    {
        "name": "XepLoai",
        # "formula": "ifs(diem = 9, 'Xuat sac', diem >= 8, 'Gioi', diem >= 6.5, 'Kha', diem >= 5, 'Trung binh', 'Yeu')"
        "formula": "if(diem = 9, 'Xuat sac', if(diem >= 8, 'Gioi', if(diem >= 6.5, 'Kha', if(diem >= 5, 'Trung binh', 'Yeu'))))"
    }
]
engine = FormulaEngineCore(formulas)
result = engine.calculate({"diem": 9})
print('xep loai:', result["XepLoai"])  # 'Xuat sac'


# formulas = [
#     {
#         "name": "XepLoai",
#         "formula": "'Xuat sac' if diem >= 9 else 'Gioi' if diem >= 8 else 'Kha' if diem >= 6.5 else 'Trung binh' if diem >= 5 else 'YYeu'"
#     }
# ]

formulas = [
    {
        "name": "XepLoai",
        "formula": (
            "'Xuất sắc' if diem >= 9 "
            "else 'Giỏi' if diem >= 8 "
            "else 'Khá' if diem >= 6.5 "
            "else 'Trung bình' if diem >= 5 "
            "else 'Yếu'"
        )
    }
]

engine = FormulaEngineCore(formulas)
print(engine.calculate({"diem": 9})["XepLoai"])     # → 'Xuat sac'
print(engine.calculate({"diem": 7.5})["XepLoai"])   # → 'Kha'
print(engine.calculate({"diem": 4})["XepLoai"])  # → 'Yeu'



formulas = [
    {"name": "VL", "formula": "sum(q * dg for q, dg, t, n in bom if t == 'VL')"},
    {"name": "NC", "formula": "sum(q * dg for q, dg, t, n in bom if t == 'NC')"},
    {"name": "TT", "formula": "VL + NC"}
]

context = {
    "bom": [
        (10, 150000, "VL", "Xi măng"),
        (5,  250000, "NC", "Nhân công"),
        (20, 200000, "VL", "Cát")
    ]
}
engine = FormulaEngineCore(formulas)
result = engine.calculate(context)
print(result["VL"])  # 5,500,000
print(result["NC"])  # 1,250,000
print(result["TT"])  # 6,750,000


formulas = [
    {"name": "DonGia", "formula": "vlookup(ma_vt, bang_gia, 2, 0)"},
    {"name": "ThanhTien", "formula": "DonGia * so_luong"}
]

context = {
    "ma_vt": "VT001",
    "so_luong": 100,
    "bang_gia": [
        ("VT001", 150000),
        ("VT002", 250000)
    ]
}
engine = FormulaEngineCore(formulas)
result = engine.calculate(context)
print(result["ThanhTien"])  # 15,000,000


formulas = [
    {"name": "TenVT", "formula": "xlookup(ma_vt, cot_ma, cot_ten, 'Không tìm thấy')"},
    {"name": "DonGia", "formula": "xlookup(ma_vt, cot_ma, cot_gia, 0)"}
]

context = {
    "ma_vt": "VT002",
    "cot_ma": ["VT001", "VT002", "VT003"],
    "cot_ten": ["Xi măng", "Cát", "Đá"],
    "cot_gia": [150000, 200000, 180000]
}
engine = FormulaEngineCore(formulas)
result = engine.calculate(context)
print(result["TenVT"])   # 'Cát'
print(result["DonGia"])  # 200000


formulas = [
    {
        "name": "GiaTriCuoi",
        "formula": "safe_div(round(xlookup(ma_sp, cot_ma, cot_gia, 0) * (1 + thue/100) * (1 - chiet_khau/100), 0) + sum(filter_array([dg for q, dg, t in bom if t == 'VL'], '>', 200000)), so_luong, 0)"
    }
]

context = {
    "ma_sp": "SP001",
    "cot_ma": ["SP001", "SP002"],
    "cot_gia": [500000, 600000],
    "thue": 10,
    "chiet_khau": 5,
    "bom": [(10, 250000, "VL"), (5, 300000, "VL"), (3, 150000, "NC")],
    "so_luong": 10
}
engine = FormulaEngineCore(formulas)
result = engine.calculate(context)
print(result["GiaTriCuoi"])  # Giá trị phức tạp đã tính


formulas = [
    {
        "name": "GiaTriCuoi",
        "formula": "sumif(criteria_range, criteria, sum_range)"
    }
]

context = {
    "criteria_range": [10, 20, 30, 40],
    "criteria": ">20",
    "sum_range": [1, 2, 3, 4]
}
engine = FormulaEngineCore(formulas)
result = engine.calculate(context)
print(result["GiaTriCuoi"])  # Giá trị phức tạp đã tính

formulas = [
    {
        "name": "GiaTriCuoi",
        "formula": "sumif(criteria_range, criteria, sum_range)"
    },
    {
        "name": "TongPhucTap",
        "formula": "sumifs(sum_range, crit1_range, crit1, crit2_range, crit2)"
    }
]

context = {
    # SUMIF
    "criteria_range": [10, 20, 30, 40],
    "criteria": ">20",
    "sum_range": [1, 2, 3, 4],

    # SUMIFS
    "crit1_range": [1, 2, 3, 4],
    "crit1": ">2",
    "crit2_range": ['A', 'B', 'A', 'B'],
    "crit2": "A"
}

engine = FormulaEngineCore(formulas)
result = engine.calculate(context)

print(result["GiaTriCuoi"])   # 7
print(result["TongPhucTap"])  # 30


formulas = [
    {"name": "PhuCap", "formula": "sum(tien for loai,tien in ds_phu_cap)"},
    {"name": "TongThuNhap", "formula": "LuongCB + PhuCap + Thuong"},
    {"name": "BH", "formula": "LuongCB * 0.105"},
    {"name": "ThuNhapChiuThue", "formula": "max(TongThuNhap - BH - (11000000 + 4400000 * nguoi_phu_thuoc), 0)"},
    {"name": "Thue", "formula": "min(ThuNhapChiuThue, 5000000) * 0.05 + max(ThuNhapChiuThue - 5000000, 0) * 0.1"},
    {"name": "LuongThucLinh", "formula": "TongThuNhap - BH - Thue"}
]

context = {
    "LuongCB": 35100000,
    "ds_phu_cap": [("Ăn trưa", 800000), ("Xăng xe", 600000), ("Điện thoại", 300000)],
    "Thuong": 2000000,
    "nguoi_phu_thuoc": 2
}

engine = FormulaEngineCore(formulas)
result = engine.calculate(context)
print(result["LuongThucLinh"]) 
print(result)


formulas = [
    {"name": "NVL_unique", "formula": "sum(q * dg if t == 'NVL' and n not in seen else 0 for q, dg, t, n, seen in bom)"},
    {"name": "NC", "formula": "sum(q * dg for q, dg, t, n in bom if t == 'NC')"},
    {"name": "TongCP", "formula": "NVL_unique + NC"},
    {"name": "GiaThanhDonVi", "formula": "safe_div(TongCP, so_luong, 0)"}
]

context = {
    "bom": [
        (10, 50000, "NVL", "Nguyên liệu A", set()),
        (5,  150000, "NC", "Công", set()),
        (10, 50000, "NVL", "Nguyên liệu A", set())  # trùng → skip
    ],
    "so_luong": 50
}

engine = FormulaEngineCore(formulas)
result = engine.calculate(context)
print(result["GiaThanhDonVi"]) 
print(result)


formulas = [
    {"name": "PhuCap", "formula": "sum(tien for _, tien in ds_phu_cap)"},
    {"name": "TongThuNhap", "formula": "LuongCB + PhuCap + Thuong"},
    {"name": "BH_XH", "formula": "LuongCB * 0.105"},
    {"name": "GiamTru", "formula": "11000000 + 4400000 * nguoi_phu_thuoc"},
    {"name": "ThuNhapChiuThue", "formula": "max(TongThuNhap - BH_XH - GiamTru, 0)"},

    # Thuế lũy tiến 7 bậc
    {"name": "Thue_B1", "formula": "min(ThuNhapChiuThue, 5000000) * 0.05"},
    {"name": "Thue_B2", "formula": "max(min(ThuNhapChiuThue - 5000000, 5000000), 0) * 0.10"},
    {"name": "Thue_B3", "formula": "max(min(ThuNhapChiuThue - 10000000, 8000000), 0) * 0.15"},
    {"name": "Thue_B4", "formula": "max(min(ThuNhapChiuThue - 18000000, 14000000), 0) * 0.20"},
    {"name": "Thue_B5", "formula": "max(min(ThuNhapChiuThue - 32000000, 28000000), 0) * 0.25"},
    {"name": "Thue_B6", "formula": "max(min(ThuNhapChiuThue - 60000000, 36000000), 0) * 0.30"},
    {"name": "Thue_B7", "formula": "max(ThuNhapChiuThue - 96000000, 0) * 0.35"},
    {"name": "ThueTNCN", "formula": "Thue_B1 + Thue_B2 + Thue_B3 + Thue_B4 + Thue_B5 + Thue_B6 + Thue_B7"},

    {"name": "LuongThucLinh", "formula": "TongThuNhap - BH_XH - ThueTNCN"}
]

context = {
    "LuongCB": 35100000,
    "ds_phu_cap": [("Ăn trưa", 800000), ("Xăng xe", 600000), ("Điện thoại", 300000)],
    "Thuong": 5000000,
    "nguoi_phu_thuoc": 3
}

engine = FormulaEngineCore(formulas)
result = engine.calculate(context)
print(result["LuongThucLinh"]) 
print(result)


formulas = [
    {"name": "ChieuDaiThuc", "formula": "2 * H + 2 * W + hao_hut"},
    {"name": "DienTichKinh", "formula": "(W * H) / 1000000"},
    {"name": "ChiPhiNhom", "formula": "ChieuDaiThuc * don_gia_nhom"},
    {"name": "ChiPhiKinh", "formula": "DienTichKinh * don_gia_kinh"},
    {"name": "TongChiPhi", "formula": "ChiPhiNhom + ChiPhiKinh"},
    {"name": "GiaBan", "formula": "TongChiPhi * 1.35"}
]

context = {
    "W": 1200,
    "H": 1500,
    "hao_hut": 200,
    "don_gia_nhom": 180000,
    "don_gia_kinh": 450000
}
engine = FormulaEngineCore(formulas)
result = engine.calculate(context)
print(result["GiaBan"]) 
print(result)


formulas = [
    {"name": "ChietKhau", "formula": "gia * 0.1 if so_luong >= 100 else 0"},
    {"name": "ThanhTien", "formula": "gia * so_luong - ChietKhau"}
]
engine = FormulaEngineCore(formulas)
result = engine.calculate({"gia": 50000, "so_luong": 120})
print(result["ThanhTien"])  # 5400000



formulas = [
    {
        "name": "GiaTriCuoi",
        "formula": "safe_div(round(xlookup(ma_sp, cot_ma, cot_gia, 0) * (1 + thue/100) * (1 - chiet_khau/100), 0) + sum(filter_array([dg for q, dg, t in bom if t == 'VL'], '>', 200000)), so_luong, 0)"
    }
]

context = {
    "ma_sp": "SP001",
    "cot_ma": ["SP001", "SP002"],
    "cot_gia": [500000, 600000],
    "thue": 10,
    "chiet_khau": 5,
    "bom": [(10, 250000, "VL"), (5, 300000, "VL"), (3, 150000, "NC")],
    "so_luong": 10
}
engine = FormulaEngineCore(formulas)
result = engine.calculate(context)
print(result["GiaTriCuoi"])  # Kết quả phức tạp đã tính


formulas = [
    {"name": "KLThucTe", "formula": "khoi_luong"},
    {"name": "LuyKeKL", "formula": "prev_LuyKeKL + KLThucTe"},
    {"name": "TyLeHoanThanh", "formula": "LuyKeKL / tong_khoi_luong * 100"}
]

rows = [
    {"khoi_luong": 200, "tong_khoi_luong": 1000},
    {"khoi_luong": 300, "tong_khoi_luong": 1000},
    {"khoi_luong": 250, "tong_khoi_luong": 1000},
]
engine = FormulaEngineCore(formulas)
results = engine.calculate_batch_with_memory(
    rows,
    memory_keys=["LuyKeKL"],
    initial_memory={"LuyKeKL": 0}
)

for r in results:
    print(f"Lũy kế KL: {r['LuyKeKL']:,} | Tỷ lệ: {r['TyLeHoanThanh']:.1f}%")



formulas = [
    {"name": "lastest", "formula": "last(v1) / last(v2)"},
]

# Cách 1: Truyền 1 row (dict) — đơn giản nhất
row = {
    "v1": [3, 1, 4, 1, 5],
    "v2": [2, 3, 1, 4, 1]
}

engine = FormulaEngine(formulas)
result = engine.calculate(row)          # ← Truyền dict thay vì list

print(result)
print("Lastest =", result["lastest"])



formulas = [
    # Lương tháng gần nhất
    {"name": "LuongThangTruoc", 
     "formula": "last(lich_su_luong, 'thang', value_key='luong_thuc_linh', default=0)"},
    
    # So sánh với tháng trước
    {"name": "TangGiam", "formula": "LuongThucLinh - LuongThangTruoc"},
    {"name": "TangGiam_Pct", "formula": "safe_div(TangGiam, LuongThangTruoc, 0) * 100"},
    
    # Lương trung bình 3 tháng gần nhất
    {"name": "TB_3Thang", 
     "formula": "average(last(lich_su_luong, 'thang', n=3, value_key='luong_thuc_linh', default=0))"},
]

engine = FormulaEngine(formulas)

result = engine.calculate({
    "LuongThucLinh": 25000000,
    "lich_su_luong": [
        {"thang": "2026-01", "luong_thuc_linh": 23000000},
        {"thang": "2026-02", "luong_thuc_linh": 24000000},
        {"thang": "2025-12", "luong_thuc_linh": 22000000},
    ]
})

print(f"Tăng/giảm: {result['TangGiam']:,} ({result['TangGiam_Pct']:.1f}%)")
print(f"TB 3 tháng: {result['TB_3Thang']:,}")