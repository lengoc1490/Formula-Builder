# Formula Utils — Hướng Dẫn Sử Dụng Toàn Diện Các Hàm

> **Engine Version:** 29.1.0 · Pure Python · Zero Dependencies  
> Tài liệu này tập trung **100% vào cách dùng các hàm** — từ cơ bản đến nâng cao, đơn lẻ đến kết hợp.

---

## Mục Lục

| #   | Nhóm hàm                                                     |
| --- | ------------------------------------------------------------ |
| §1  | [Toán học](#1-toán-học)                                      |
| §2  | [Logic & Điều kiện](#2-logic--điều-kiện)                     |
| §3  | [Tổng hợp — sum, min, max, average, count](#3-tổng-hợp)      |
| §4  | [Tổng hợp có điều kiện](#4-tổng-hợp-có-điều-kiện)            |
| §5  | [Mảng & Collection](#5-mảng--collection)                     |
| §6  | [last / first / nth — Truy vấn dữ liệu](#6-last--first--nth) |
| §7  | [Lookup — vlookup, xlookup](#7-lookup)                       |
| §8  | [Chuỗi](#8-chuỗi)                                            |
| §9  | [Ngày tháng](#9-ngày-tháng)                                  |
| §10 | [Tiện ích](#10-tiện-ích)                                     |
| §11 | [Ví dụ kết hợp nâng cao](#11-ví-dụ-kết-hợp-nâng-cao)         |

---

## 1. Toán học

### abs

```python
abs(-5)          # → 5
abs(-3.14)       # → 3.14
abs(0)           # → 0

# Trong formula
{"name": "DO_LECH", "formula": "abs(THUC_HIEN - KE_HOACH)"}
```

### round / roundup / rounddown

```python
round(3.456, 2)        # → 3.46   (2 chữ số thập phân)
round(3.456, 0)        # → 3.0
round(3.456, -1)       # → 0.0    (làm tròn đến hàng chục)
round(1234.5, -2)      # → 1200.0

roundup(3.01, 0)       # → 4.0    (luôn lên)
roundup(3.01, 1)       # → 3.1
roundup(-3.1, 0)       # → -3.0   (về 0, không phải -4)
roundup(1250, -3)      # → 2000.0

rounddown(3.99, 0)     # → 3.0    (luôn xuống)
rounddown(3.99, 1)     # → 3.9
rounddown(-3.9, 0)     # → -4.0   (xuống xa 0)

# Làm tròn đơn giá về bội số 1000
{"name": "GIA_TRON", "formula": "roundup(DON_GIA / 1000, 0) * 1000"}

# Số lượng cần mua (luôn làm tròn lên)
{"name": "SO_LUONG_MUA", "formula": "roundup(TONG_NHUCAU / SO_LUONG_GOI, 0)"}
```

### ceil / floor

```python
ceil(3.1)     # → 4
ceil(3.0)     # → 3
ceil(-3.1)    # → -3    (về phía +∞)

floor(3.9)    # → 3
floor(3.0)    # → 3
floor(-3.1)   # → -4    (về phía -∞)

# Số tháng (làm tròn lên)
{"name": "SO_THANG", "formula": "ceil(date_diff(NGAY_KT, NGAY_BD, 'days') / 30)"}
```

### sqrt / power / ln / log / log10 / exp

```python
sqrt(9)          # → 3.0
sqrt(2)          # → 1.4142135...
power(2, 10)     # → 1024.0
power(4, 0.5)    # → 2.0   (căn bậc 2)
power(8, 1/3)    # → 2.0   (căn bậc 3)

ln(1)            # → 0.0
ln(2.71828)      # ≈ 1.0
log(100, 10)     # → 2.0
log10(1000)      # → 3.0
exp(0)           # → 1.0
exp(1)           # ≈ 2.71828

# Lãi kép liên tục: P × e^(r×t)
{"name": "TIEN_LAI", "formula": "VON_GOC * exp(LAI_SUAT_NAM * SO_NAM)"}
```

### safe_div

```python
safe_div(10, 2)         # → 5.0
safe_div(10, 0)         # → 0.0   (mặc định, không raise)
safe_div(10, 0, -1)     # → -1.0  (custom default)
safe_div(10, 0, None)   # → None
safe_div(0, 0)          # → 0.0
safe_div("abc", 2)      # → 0.0   (lỗi type → default)

# Tỷ lệ hoàn thành KPI
{"name": "TY_LE_HT",    "formula": "safe_div(THUC_HIEN, KE_HOACH) * 100"}
{"name": "DON_GIA_TB",  "formula": "safe_div(TONG_CHI_PHI, SAN_LUONG, 0)"}
```

### clamp / between / percent_of

```python
clamp(150, 0, 100)      # → 100  (vượt trần → trả trần)
clamp(-5,  0, 100)      # → 0    (dưới sàn → trả sàn)
clamp(50,  0, 100)      # → 50   (trong khoảng → giữ nguyên)
clamp(0.35, 0.0, 1.0)   # → 0.35

between(50,  0, 100)    # → True
between(150, 0, 100)    # → False
between(0,   0, 100)    # → True  (đầu mút được tính)
between("B", "A", "Z")  # → True  (so sánh chuỗi)

percent_of(30, 200)         # → 15.0
percent_of(0, 200)          # → 0.0
percent_of(50, 0)           # → 0.0   (không raise)
percent_of(50, 0, default=-1) # → -1.0

# Hệ số thưởng KPI
{"name": "HE_SO_THUONG",  "formula": "clamp(TY_LE_KPI / 100, 0.5, 2.0)"}
{"name": "TIEN_THUONG",   "formula": "IF(between(TY_LE_KPI, 60, 999), LUONG_CB * HE_SO_THUONG, 0)"}
{"name": "TY_LE_HOAN_TT", "formula": "percent_of(SO_DA_THANH, TONG_CONG_NO)"}
```

### Lượng giác

```python
sin(pi / 2)          # → 1.0
cos(0)               # → 1.0
tan(pi / 4)          # → 1.0
asin(1.0)            # → 1.5707...  (π/2 radian)
degrees(asin(1.0))   # → 90.0
radians(180)         # → 3.14159...

# Tính diện tích mái dốc
{"name": "DIEN_TICH_MAI", "formula": "CHIEU_NGANG * CHIEU_DAI / cos(radians(GOC_DOC))"}
```

---

## 2. Logic & Điều kiện

### IF

```python
# IF(điều_kiện, giá_trị_đúng, giá_trị_sai)
IF(10 > 5, "Lớn", "Nhỏ")          # → "Lớn"
IF(0, "truthy", "falsy")           # → "falsy"
IF(None, "có", "không")            # → "không"

# Lồng nhau (nesting)
IF(DIEM >= 9, 'Xuất sắc',
   IF(DIEM >= 7, 'Giỏi',
      IF(DIEM >= 5, 'Khá', 'Yếu')))

# Với số
{"name": "PHAT_THEM", "formula": "IF(SO_NGAY_TRE > 30, SO_NGAY_TRE * PHAT_MOI_NGAY, 0)"}

# Với chuỗi
{"name": "NHOM_KH",   "formula": "IF(DOANH_SO >= 100_000_000, 'VIP', 'Thường')"}
```

### IFS

```python
# IFS(cond1, val1, cond2, val2, ..., True, default)
# Trả val đầu tiên có cond = True
IFS(DIEM >= 9, 'A',
    DIEM >= 7, 'B',
    DIEM >= 5, 'C',
    True,      'F')          # True = fallback bắt buộc

# Thuế TNCN 7 bậc lũy tiến
{"name": "THUE_TNCN", "formula": """
IFS(
    TNT <= 0,            0,
    TNT <= 5_000_000,    TNT * 5%,
    TNT <= 10_000_000,   TNT * 10% - 250_000,
    TNT <= 18_000_000,   TNT * 15% - 750_000,
    TNT <= 32_000_000,   TNT * 20% - 1_650_000,
    TNT <= 52_000_000,   TNT * 25% - 3_250_000,
    TNT <= 80_000_000,   TNT * 30% - 5_850_000,
    True,                TNT * 35% - 9_850_000
)"""}
```

### SWITCH

```python
# SWITCH(biểu_thức, val1, kết_quả1, val2, kết_quả2, ..., default)
SWITCH(2, 1, "Một", 2, "Hai", 3, "Ba", "Khác")    # → "Hai"
SWITCH("B", "A", 10, "B", 20, "C", 30, 0)          # → 20
SWITCH("X", "A", 10, "B", 20, 0)                   # → 0  (default)

# Hệ số phụ cấp theo hạng nhân viên
{"name": "HE_SO_PC",     "formula": "SWITCH(HANG_NV, 'A', 1.5, 'B', 1.2, 'C', 1.0, 0.8)"}
{"name": "MUC_BH_MAX",   "formula": "SWITCH(LOAI_HOP_DONG, 'CT', 36, 'HĐ', 20, 0)"}
```

### coalesce / is_blank / not_blank

```python
coalesce(None, "", 0, 5, 10)     # → 0    (0 không phải None hay "")
coalesce(None, None, "hello")    # → "hello"
coalesce(None, 0.0, 100)         # → 0.0  (0.0 hợp lệ)
coalesce()                        # → None

is_blank(None)     # → True
is_blank("")       # → True
is_blank(0)        # → True
is_blank(0.0)      # → True
is_blank("abc")    # → False
is_blank(1)        # → False

not_blank(0)       # → False
not_blank("a")     # → True

# Ưu tiên giá override → giá chuẩn → giá mặc định
{"name": "GIA_AP_DUNG",  "formula": "coalesce(GIA_OVERRIDE, GIA_STANDARD, GIA_MAC_DINH)"}
{"name": "CO_SL",        "formula": "not_blank(SO_LUONG)"}
```

### and* / or* / not\_

```python
and_(True, True, True)        # → True
and_(True, False, True)       # → False
and_(1, 2, 3)                 # → True   (truthy)

or_(False, False, True)       # → True
or_(0, "", None)              # → False

not_(True)     # → False
not_(0)        # → True
not_(None)     # → True

# Điều kiện chiết khấu: VIP + đơn hàng lớn + không quá hạn
{"name": "DUOC_CHIET_KHAU", "formula":
    "and_(LOAI_KH = 'VIP', TONG_TIEN >= 10_000_000, not_(QUA_HAN))"}

# Đơn hàng cần xử lý ngay
{"name": "KHAN_CAP", "formula":
    "or_(DO_UU_TIEN = 'Cao', and_(DO_UU_TIEN = 'TB', SO_NGAY_TRE > 3))"}
```

### isnumber / to_number

```python
isnumber(5)           # → True
isnumber(3.14)        # → True
isnumber("3.14")      # → False  (chuỗi)
isnumber(True)        # → False  (bool không tính)
isnumber(None)        # → False

to_number("1,234.5")   # → 1234.5   (bỏ dấu phẩy nghìn)
to_number("$100")      # → 100.0    (bỏ ký tự đặc biệt)
to_number("100 VNĐ")   # → 100.0
to_number("-50.5")     # → -50.5
to_number(None)        # → 0.0
to_number("abc", -1)   # → -1.0     (custom default)
to_number(150)         # → 150.0    (số → float)

{"name": "GIA_NUM", "formula": "to_number(GIA_RAW, 0) * TY_GIA"}
```

---

## 3. Tổng hợp

### sum

```python
# Dạng 1: list số
sum([10, 20, 30])              # → 60
sum([1, None, 3, None, 5])     # → 9    (bỏ qua None)
sum([])                         # → 0

# Dạng 2: nhiều tham số
sum(10, 20, 30)                # → 60
sum(A, B, C)

# Dạng 3: dict values
sum({"a": 10, "b": 20, "c": 30})   # → 60

# Dạng 4: list[dict] + key
rows = [
    {"sp": "A", "sl": 100, "gia": 50_000},
    {"sp": "B", "sl": 200, "gia": 30_000},
    {"sp": "C", "sl": 50,  "gia": 80_000},
]
sum(rows, key="sl")     # → 350
sum(rows, key="gia")    # → 160_000

# Dạng 5: generator (phổ biến nhất với list[dict])
sum(r["sl"] * r["gia"] for r in rows)                       # → 15_000_000
sum(r["sl"] for r in rows if r["gia"] > 40_000)             # → 150

# Trong formula engine
{"name": "TONG_DT",  "formula": "sum(r['sl'] * r['don_gia'] for r in chi_tiet)"}
{"name": "TONG_NVL", "formula": "sum(chi_phi_nvl)"}
```

### min / max

```python
# Scalar
min(5, 3, 8, 1)             # → 1
max(5, 3, 8, 1)             # → 8
min([5, 3, 8, 1])           # → 1
max([5, 3, 8, 1])           # → 8

# Với list[dict] + key
rows = [{"ma": "A", "gia": 50_000}, {"ma": "B", "gia": 30_000}, {"ma": "C", "gia": 80_000}]
min(rows, key="gia")        # → 30_000
max(rows, key="gia")        # → 80_000

# Generator
max(r["gia"] for r in rows if r["gia"] < 70_000)    # → 50_000

# Đảm bảo không âm
{"name": "GIA_MIN_0",    "formula": "max(DON_GIA - CHIET_KHAU, 0)"}
{"name": "GIA_THA_NHAT", "formula": "min(lich_su_gia, key='gia')"}
```

### average / count / counta / countnum

```python
average([10, 20, 30])                    # → 20.0
average([10, None, 30, None, 50])        # → 30.0  (bỏ None)
average(10, 20, 30)                      # → 20.0  (*args)

rows = [{"ten": "A", "diem": 8}, {"ten": "B", "diem": 6}, {"ten": "C", "diem": None}]
average(rows, key="diem")               # → 7.0  (bỏ None)

count([1, None, 3, None, 5])            # → 3   (bỏ None và "")
count(["a", "", "b", None, "c"])        # → 3
counta([1, None, 3])                    # → 2   (alias count)
countnum([1, "a", None, 2.5, True, 3])  # → 3   (chỉ int/float: 1, 2.5, 3)

{"name": "DIEM_TB",    "formula": "average(ds_diem, key='diem')"}
{"name": "SO_HOA_DON", "formula": "count(ds_hd, key='so_tien')"}
```

---

## 4. Tổng hợp có điều kiện

### sumif

```python
# Cú pháp A: 2 list riêng (Excel-style)
loai = ["Ban", "Mua", "Ban", "Ban", "Mua"]
tien = [1_000_000, 500_000, 2_000_000, 1_500_000, 300_000]

sumif(loai, "Ban", sum_range=tien)          # → 4_500_000
sumif(tien, ">1000000")                      # → 3_500_000  (sum chính mảng)
sumif(loai, "<>Mua", sum_range=tien)        # → 4_500_000
sumif(loai, "*an*", sum_range=tien)         # → 4_500_000  (wildcard)

# Cú pháp B: list[dict] + key=tuple
rows = [
    {"phong": "IT",  "luong": 20_000_000},
    {"phong": "IT",  "luong": 15_000_000},
    {"phong": "KT",  "luong": 18_000_000},
    {"phong": "HR",  "luong": 12_000_000},
]
sumif(rows, "IT",       key=("phong", "luong"))  # → 35_000_000
sumif(rows, ">15000000", key="luong")            # → 38_000_000

{"name": "TONG_DOANH_THU", "formula": "sumif(giao_dich, 'Ban', key=('loai', 'so_tien'))"}
{"name": "TONG_CHI_PHI",   "formula": "sumif(giao_dich, 'Mua', key=('loai', 'so_tien'))"}
```

### sumifs

```python
rows = [
    {"phong": "IT",  "loai": "CT", "luong": 20_000_000, "kpi": 95},
    {"phong": "IT",  "loai": "HĐ", "luong": 15_000_000, "kpi": 80},
    {"phong": "KT",  "loai": "CT", "luong": 18_000_000, "kpi": 88},
    {"phong": "KT",  "loai": "CT", "luong": 22_000_000, "kpi": 70},
    {"phong": "HR",  "loai": "CT", "luong": 12_000_000, "kpi": 85},
]

# Cú pháp kwargs (gọn nhất)
sumifs(rows, key="luong", phong="KT", loai="CT")      # → 40_000_000
sumifs(rows, key="luong", phong="IT")                  # → 35_000_000

# Cú pháp positional pairs
sumifs(rows, "phong", "KT", "loai", "CT", key="luong") # → 40_000_000

# Excel-style thuần (3 list riêng)
phong_l = ["IT",  "IT",  "KT",  "KT",  "HR"]
loai_l  = ["CT",  "HĐ",  "CT",  "CT",  "CT"]
luong_l = [20e6, 15e6, 18e6, 22e6, 12e6]
sumifs(luong_l, phong_l, "KT", loai_l, "CT")           # → 40_000_000

{"name": "LUONG_IT_CT", "formula": "sumifs(nhan_vien, key='luong', phong='IT', loai='CT')"}
```

### countif / countifs / averageif

```python
ds = ["A", "B", "A", "C", "A", "B"]
countif(ds, "A")                                        # → 3
countif(ds, "<>A")                                      # → 3
countif([10, 20, 5, 30, 15], ">10")                    # → 3

rows = [
    {"phong": "IT",  "luong": 20_000_000, "kpi": 90},
    {"phong": "IT",  "luong": 15_000_000, "kpi": 75},
    {"phong": "KT",  "luong": 18_000_000, "kpi": 88},
    {"phong": "HR",  "luong": 12_000_000, "kpi": 70},
]
countif(rows, "IT",  key="phong")                       # → 2
countif(rows, ">80", key="kpi")                         # → 2
countif(rows, None,  key="luong")                       # → 0  (không có None)

# countifs
countifs(rows, phong="IT")                              # → 2
countifs(rows, phong="IT", kpi=">80")                   # → 1  (chỉ kpi=90)

# averageif
loai = ["A", "B", "A", "B"]
gia  = [100, 200, 300, 400]
averageif(loai, "A", average_range=gia)                 # → 200.0   ((100+300)/2)
averageif(rows, "IT", key=("phong", "kpi"))             # → 82.5    ((90+75)/2)

{"name": "SO_NV_KPI_TOT",  "formula": "countif(nhan_vien, '>=90', key='kpi')"}
{"name": "TY_LE_KPI_TOT",  "formula": "safe_div(SO_NV_KPI_TOT, count(nhan_vien)) * 100"}
{"name": "KPI_TB_IT",      "formula": "averageif(nhan_vien, 'IT', key=('phong', 'kpi'))"}
```

---

## 5. Mảng & Collection

### filter_array

```python
rows = [
    {"loai": "A", "gia": 100_000, "sl": 50},
    {"loai": "B", "gia": 200_000, "sl": 30},
    {"loai": "A", "gia": 150_000, "sl": 20},
    {"loai": "C", "gia": 80_000,  "sl": 10},
]

# Exact match
filter_array(rows, key="loai", value="A")               # → [row1, row3]

# Numeric comparison
filter_array(rows, ">", 100_000, key="gia")             # → [row2, row3]
filter_array(rows, ">=", 100_000, key="gia")            # → [row1, row2, row3]
filter_array(rows, "!=", "A", key="loai")               # → [row2, row4]

# Plain list
filter_array([10, 5, 20, 3, 15], ">", 10)              # → [20, 15]
filter_array([10, 5, 20, 3, 15], "<=", 5)              # → [5, 3]

# Kết hợp với sum
{"name": "TONG_TIEN_LOAI_A",
 "formula": "sum(r['gia'] * r['sl'] for r in filter_array(san_pham, key='loai', value='A'))"}

{"name": "SO_HANG_GIA_CAO",
 "formula": "count(filter_array(san_pham, '>', 100_000, key='gia'))"}
```

### sorted_array / sort

```python
# List số
sorted_array([3, 1, 4, 1, 5])                          # → [1, 1, 3, 4, 5]
sorted_array([3, 1, 4, 1, 5], reverse=True)            # → [5, 4, 3, 1, 1]

# List chuỗi
sorted_array(["chuối", "táo", "ổi"])                   # → ['chuối', 'ổi', 'táo']

# List ISO date (sort đúng)
sorted_array(["2025-03-15", "2025-01-01", "2025-12-31"])
# → ["2025-01-01", "2025-03-15", "2025-12-31"]

# List[dict] + key
rows = [{"ma": "C", "gia": 300}, {"ma": "A", "gia": 100}, {"ma": "B", "gia": 200}]
sorted_array(rows, key="gia")                           # tăng dần theo giá
sorted_array(rows, key="gia", reverse=True)            # giảm dần

# sort = alias của sorted_array
sort(rows, key="ma")                                    # alpha

{"name": "TOP3_SAN_PHAM",
 "formula": "sorted_array(san_pham, key='doanh_so', reverse=True)[:3]"}
```

### group_sum / group_count / group_avg

```python
rows = [
    {"phong": "IT",  "luong": 20_000_000, "kpi": 90},
    {"phong": "IT",  "luong": 15_000_000, "kpi": 75},
    {"phong": "KT",  "luong": 18_000_000, "kpi": 85},
    {"phong": "HR",  "luong": 12_000_000, "kpi": 80},
    {"phong": "KT",  "luong": 22_000_000, "kpi": 70},
]

group_sum(rows, "phong", "luong")
# → {"IT": 35_000_000, "KT": 40_000_000, "HR": 12_000_000}

group_count(rows, "phong")
# → {"IT": 2, "KT": 2, "HR": 1}

group_avg(rows, "phong", "kpi")
# → {"IT": 82.5, "KT": 77.5, "HR": 80.0}

{"name": "LUONG_THEO_PHONG",  "formula": "group_sum(nhan_vien, 'phong', 'luong')"}
{"name": "SL_THEO_PHONG",     "formula": "group_count(nhan_vien, 'phong')"}
{"name": "KPI_TB_THEO_PHONG", "formula": "group_avg(nhan_vien, 'phong', 'kpi')"}
```

### map_key / unique / count_unique / flatten

```python
rows = [{"ma": "A", "gia": 100}, {"ma": "B", "gia": 200}, {"ma": "A", "gia": 150}]

map_key(rows, "ma")         # → ["A", "B", "A"]
map_key(rows, "gia")        # → [100, 200, 150]

unique([3, 1, 4, 1, 5, 9, 2, 6, 5])    # → [1, 2, 3, 4, 5, 6, 9]  (sorted)
unique(rows, key="ma")                   # → ["A", "B"]

count_unique([1, 2, 2, 3, 3, 3])        # → 3
count_unique(rows, key="ma")             # → 2

flatten([[1, 2], [3, [4, 5]], 6])        # → [1, 2, 3, 4, 5, 6]
flatten([[["a","b"],["c"]], ["d"]])      # → ["a","b","c","d"]

{"name": "MA_SP_DUY_NHAT",   "formula": "unique(map_key(don_hang, 'ma_sp'))"}
{"name": "SO_KH_DUY_NHAT",   "formula": "count_unique(don_hang, key='ma_kh')"}
```

### index / match / choose

```python
# index(array, row_num, col_num=0) — 1-based như Excel
arr = [10, 20, 30, 40, 50]
index(arr, 1)              # → 10
index(arr, 3)              # → 30
index(arr, 5)              # → 50

# Matrix
mat = [[1,2,3],[4,5,6],[7,8,9]]
index(mat, 2, 3)           # → 6   (hàng 2, cột 3)
index(mat, 2, 0)           # → [4,5,6]  (cả hàng 2)

# match(lookup_val, array, match_type)
# match_type=0: exact, 1: ≤, -1: ≥
match("B", ["A","B","C","D"])           # → 2  (exact)
match(15,  [10,15,20,25], 0)            # → 2  (exact)
match(12,  [10,15,20,25], 1)            # → 1  (≤12: max là 10 ở pos 1)
match(17,  [10,15,20,25], 1)            # → 2  (≤17: max là 15 ở pos 2)

# choose(index_num, *values) — 1-based
choose(1, "A", "B", "C")   # → "A"
choose(2, 10, 20, 30)      # → 20
choose(3, "x", "y", "z")   # → "z"

# Lấy giá theo bậc thuế
{"name": "BAC_THUE", "formula": "match(TNT, [0, 5e6, 10e6, 18e6, 32e6], 1)"}
{"name": "THUE_RATE","formula": "choose(BAC_THUE, 5%, 10%, 15%, 20%, 25%)"}
```

### sum_by_type / unique_sum

```python
# sum_by_type(items, type_key_idx, value_key_idx, target_type)
# Dành cho list of lists/tuples
ds_phu_cap = [
    ("Ăn trưa",    730_000),
    ("Xăng xe",    500_000),
    ("Ăn trưa",    300_000),   # cùng loại, cộng dồn
    ("Điện thoại", 200_000),
]
sum_by_type(ds_phu_cap, 0, 1, "Ăn trưa")      # → 1_030_000
sum_by_type(ds_phu_cap, 0, 1, "Xăng xe")      # → 500_000

{"name": "PC_AN_TRUA", "formula": "sum_by_type(ds_phu_cap, 0, 1, 'Ăn trưa')"}
{"name": "PC_XANG_XE", "formula": "sum_by_type(ds_phu_cap, 0, 1, 'Xăng xe')"}

# unique_sum(items, key_index, value_index)
# Tổng theo unique key (lần đầu gặp key mới cộng vào)
ds_sp = [
    ["SP001", 100_000],
    ["SP002", 200_000],
    ["SP001", 150_000],   # SP001 lặp lại → bỏ qua
]
unique_sum(ds_sp, 0, 1)    # → 300_000  (100K + 200K, bỏ 150K)
```

### zip / sum_dict

```python
ma_list  = ["A",  "B",  "C"]
gia_list = [100, 200, 300]
sl_list  = [10,   5,   8]

zip(ma_list, gia_list, sl_list)
# → [("A",100,10), ("B",200,5), ("C",300,8)]

# Kết hợp với sum
sum(g * s for _, g, s in zip(ma_list, gia_list, sl_list))   # → 100×10 + 200×5 + 300×8 = 4400

sum_dict({"a": 100, "b": 200, "c": 300})   # → 600.0
sum_dict({"IT": 35e6, "KT": 40e6})         # → 75_000_000.0

{"name": "TONG_LUONG_CT",
 "formula": "sum_dict(group_sum(filter_array(nhan_vien, key='loai', value='CT'), 'phong', 'luong'))"}
```

---

## 6. last / first / nth

### Cú pháp đầy đủ

```python
last(
    data,                        # list, list[dict], list[tuple]
    sort_by     = None,          # str | list[str] — field để sort
    n           = 1,             # int — số phần tử (1 → scalar, >1 → list)
    group_by    = None,          # str — trả dict{group: result}
    reverse     = True,          # True=lớn nhất/mới nhất trước
    value_key   = None,          # str — chỉ lấy field này
    default     = None,          # giá trị khi không tìm thấy
    missing_value = None,        # thay thế sort key null
    error_on_missing_sort_key = False,
    preserve_order = False,      # True → không sort, lấy theo vị trí
)
first(...)   # = last(..., reverse=False)
nth(data, n, sort_by=None, reverse=True, value_key=None, default=None)
```

### Trên plain list

```python
nums = [3, 1, 4, 1, 5, 9, 2, 6]

last(nums)                         # → 9    (giá trị lớn nhất)
first(nums)                        # → 1    (giá trị nhỏ nhất)
last(nums, n=3)                    # → [6, 9, 5]  (3 lớn nhất)
first(nums, n=3)                   # → [1, 1, 2]  (3 nhỏ nhất)

# preserve_order: không sort, lấy theo vị trí
last(nums, n=2, preserve_order=True)   # → [2, 6]  (2 phần tử CUỐI)
first(nums, n=2, preserve_order=True)  # → [3, 1]  (2 phần tử ĐẦU)

# String
words = ["chuối", "táo", "ổi", "xoài"]
last(words)                        # → "xoài"  (alphabetically last)
first(words)                       # → "chuối"

# ISO date
dates = ["2025-03-15", "2025-01-01", "2025-12-31", "2025-06-20"]
last(dates)                        # → "2025-12-31"  (mới nhất)
first(dates)                       # → "2025-01-01"  (cũ nhất)
last(dates, n=2)                   # → ["2025-06-20", "2025-12-31"]

# Empty list với default
last([], default=0)                # → 0
last([], n=3, default=[])          # → []
```

### Trên list[dict] — không group

```python
lich_su = [
    {"ngay": "2025-01-01", "ma_sp": "A", "gia": 100_000, "sl": 50},
    {"ngay": "2025-03-15", "ma_sp": "A", "gia": 110_000, "sl": 30},
    {"ngay": "2025-02-10", "ma_sp": "B", "gia": 200_000, "sl": 20},
    {"ngay": "2025-04-01", "ma_sp": "B", "gia": 190_000, "sl": 40},
    {"ngay": "2025-05-20", "ma_sp": "A", "gia": 115_000, "sl": 60},
    {"ngay": "2025-05-22", "ma_sp": "B", "gia": 185_000, "sl": 25},
]

# Lấy cả dict
last(lich_su, sort_by="ngay")
# → {"ngay":"2025-05-22","ma_sp":"B","gia":185_000,"sl":25}

first(lich_su, sort_by="ngay")
# → {"ngay":"2025-01-01","ma_sp":"A","gia":100_000,"sl":50}

# Chỉ lấy 1 field (value_key)
last(lich_su, sort_by="ngay", value_key="gia")       # → 185_000
first(lich_su, sort_by="ngay", value_key="gia")      # → 100_000

# Lấy n bản ghi
last(lich_su, sort_by="ngay", n=3)                   # → [row_Apr, row_May20, row_May22]
last(lich_su, sort_by="gia", n=2, value_key="gia")   # → [190_000, 200_000]  (2 giá cao nhất)

# Sort theo nhiều key
last(lich_su, sort_by=["ma_sp", "ngay"])             # sort sp trước, rồi ngày

# Giá trị cao nhất theo 1 field, lấy field khác
last(lich_su, sort_by="gia", value_key="ma_sp")      # → "B"  (gia=200K → sp B)
```

### Trên list[dict] — có group_by

```python
# Giá mới nhất của từng sản phẩm
last(lich_su, sort_by="ngay", group_by="ma_sp", value_key="gia")
# → {"A": 115_000, "B": 185_000}

# Giá cao nhất theo sản phẩm
last(lich_su, sort_by="gia", group_by="ma_sp", value_key="gia")
# → {"A": 115_000, "B": 200_000}

# Lấy bản ghi đầy đủ mới nhất theo nhóm
last(lich_su, sort_by="ngay", group_by="ma_sp")
# → {"A": {...row A mới nhất...}, "B": {...row B mới nhất...}}
```

### missing_value — xử lý null key

```python
rows = [
    {"ten": "An",    "ngay": "2025-03-01", "gia": 100},
    {"ten": "Bình",  "ngay": None,         "gia": 200},  # sort key null
    {"ten": "Cường", "ngay": "2025-01-01", "gia": 150},
]

# Mặc định: None = "nhỏ nhất"
last(rows, sort_by="ngay", value_key="ten")             # → "An"

# Đặt missing_value = "9999" → Null trở thành "lớn nhất"
last(rows, sort_by="ngay", value_key="ten",
     missing_value="9999-99-99")                         # → "Bình"
```

### nth — phần tử thứ n

```python
data = [10, 30, 50, 20, 40]
nth(data, 1)                          # → 50  (lớn nhất, n=1)
nth(data, 2)                          # → 40  (lớn nhất thứ 2)
nth(data, 1, reverse=False)           # → 10  (nhỏ nhất)

rows = [{"ma":"A","doanh_so":500},{"ma":"B","doanh_so":800},{"ma":"C","doanh_so":300}]
nth(rows, 2, sort_by="doanh_so", value_key="ma")   # → "A"  (đứng thứ 2)
```

### Ví dụ formula kết hợp

```python
# Giá mới nhất cho từng sản phẩm
{"name": "GIA_MOI_NHAT",
 "formula": "last(LICH_SU_GIA, sort_by='ngay', group_by='ma_sp', value_key='gia')"}

# Top 3 đơn hàng theo giá trị
{"name": "TOP3_DON_HANG",
 "formula": "last(DON_HANG, sort_by='tong_tien', n=3)"}

# Tổng 3 tháng gần nhất
{"name": "TONG_3T",
 "formula": "sum(r['doanh_thu'] for r in last(THANG_DATA, sort_by='thang', n=3))"}

# 5 giao dịch cuối giữ thứ tự gốc (đã sort sẵn)
{"name": "GD_GAN_NHAT",
 "formula": "last(sorted_array(GIAO_DICH, key='ngay'), n=5, preserve_order=True)"}

# Giá cũ nhất để tính biến động
{"name": "BIEN_DONG_GIA",
 "formula": "safe_div(last(LICH_SU, sort_by='ngay', value_key='gia') - first(LICH_SU, sort_by='ngay', value_key='gia'), first(LICH_SU, sort_by='ngay', value_key='gia')) * 100"}
```

---

## 7. Lookup

### vlookup

```python
# vlookup(key, table, col=1, default=0)
# col: 1=cột đầu sau key, 2=cột thứ 2, ...

# Dạng 1: list of lists
bang_gia = [
    ["SP_A", "Sản phẩm A", 100_000, "VND"],
    ["SP_B", "Sản phẩm B", 150_000, "VND"],
    ["SP_C", "Sản phẩm C", 200_000, "USD"],
]
vlookup("SP_B", bang_gia, 1)        # → "Sản phẩm B"  (col 1)
vlookup("SP_B", bang_gia, 2)        # → 150_000        (col 2)
vlookup("SP_B", bang_gia, 3)        # → "VND"          (col 3)
vlookup("SP_X", bang_gia, 2, -1)    # → -1             (không tìm thấy)
vlookup("SP_X", bang_gia, 2, 0)     # → 0

# Dạng 2: dict {key: value}
gia_dict = {"SP_A": 100_000, "SP_B": 150_000, "SP_C": 200_000}
vlookup("SP_B", gia_dict)           # → 150_000
vlookup("SP_X", gia_dict, 1, 0)     # → 0

# Dạng 3: dict {key: list}
gia_dict2 = {
    "SP_B": ["Sản phẩm B", 150_000, "VND"],
    "SP_C": ["Sản phẩm C", 200_000, "USD"],
}
vlookup("SP_B", gia_dict2, 2)       # → 150_000

# Trong formula
{"name": "TEN_SP",    "formula": "vlookup(MA_SP, BANG_SAN_PHAM, 1, 'Không rõ')"}
{"name": "GIA_NHAP",  "formula": "vlookup(MA_NVL, BANG_GIA_NVL, 2, 0)"}
{"name": "TY_GIA",    "formula": "vlookup(MA_NT, BANG_TY_GIA, 1, 1.0)"}
{"name": "THANH_TIEN","formula": "SO_LUONG * vlookup(MA_HANG, BANG_GIA, 2, 0)"}
```

### xlookup

```python
# xlookup(lookup_value, lookup_array, return_array, if_not_found=0)
ma_hang  = ["H001", "H002", "H003", "H004"]
gia_nhap = [50_000, 75_000, 60_000, 80_000]
ten_hang = ["Hàng A", "Hàng B", "Hàng C", "Hàng D"]

xlookup("H002", ma_hang, gia_nhap, 0)      # → 75_000
xlookup("H002", ma_hang, ten_hang, "?")    # → "Hàng B"
xlookup("H999", ma_hang, gia_nhap, -1)     # → -1
xlookup("H001", ma_hang, gia_nhap)         # → 50_000

# Dict mode
xlookup("H002", {"H001":50_000,"H002":75_000}, {}, 0)  # → 75_000

{"name": "GIA_NVL",   "formula": "xlookup(MA_NVL, DS_MA, DS_GIA, 0)"}
{"name": "HE_SO",     "formula": "xlookup(HANG, ['A','B','C'], [1.5,1.2,1.0], 1.0)"}
```

### Kết hợp vlookup với tính toán

```python
formulas = [
    {"name": "DON_GIA",    "formula": "vlookup(MA_SP, BANG_GIA, 2, 0)"},
    {"name": "THUE_SUAT",  "formula": "vlookup(MA_SP, BANG_THUE, 2, 0.1)"},
    {"name": "THANH_TIEN", "formula": "SO_LUONG * DON_GIA"},
    {"name": "THUE_VAT",   "formula": "THANH_TIEN * THUE_SUAT"},
    {"name": "TONG_CONG",  "formula": "THANH_TIEN + THUE_VAT"},
    {"name": "CHIET_KHAU", "formula": "IF(SO_LUONG >= 100, THANH_TIEN * 5%, 0)"},
    {"name": "PHAI_THANH", "formula": "TONG_CONG - CHIET_KHAU"},
]
```

---

## 8. Chuỗi

### concat / text_join / textjoin

```python
concat("HD-", 2025, "-", 1)                      # → "HD-2025-1"
concat("SO/", None, "/2025")                      # → "SO//2025"  (None → "")
concat(MA, "-", str(year(NGAY)))                  # → "ABC-2025"

text_join("/", 2025, 7, 15)                       # → "2025/7/15"
text_join("-", "HD", NAM, STT)
text_join(", ", "Hà Nội", "Việt Nam")             # → "Hà Nội, Việt Nam"

textjoin(", ", True,  "An", None, "Bình", "")     # → "An, Bình"  (bỏ empty)
textjoin(", ", False, "An", None, "Bình", "")     # → "An, , Bình, "  (giữ empty)

{"name": "DIA_CHI_DAY_DU",  "formula": "textjoin(', ', True, SO_NHA, DUONG, QUAN, TINH)"}
{"name": "MA_CHUNG_TU",     "formula": "concat('HD-', str(year(NGAY)), '-', str(STT))"}
```

### left / right / mid / len

```python
left("HD-2025-001", 2)        # → "HD"
left("Nguyễn Văn A", 6)       # → "Nguyễn"
right("HD-2025-001", 3)       # → "001"
right("10/2025", 4)           # → "2025"
mid("HD-2025-001", 4, 4)      # → "2025"  (từ vị trí 4, lấy 4 ký tự)
mid("abcdefgh", 3, 3)         # → "cde"
len("Hello World")            # → 11

{"name": "LOAI_CT",    "formula": "left(MA_CHUNG_TU, 2)"}    # "HD", "PO", "DN"
{"name": "NAM_CT",     "formula": "int(mid(MA_CT, 4, 4))"}   # → 2025
{"name": "SO_THU_TU",  "formula": "right(MA_CT, 3)"}         # → "001"
{"name": "MA_VIET_TAT","formula": "left(TEN_NV, 1) + left(HO_NV, 1)"}
```

### upper / lower / trim / replace / substitute / find

```python
upper("hello world")              # → "HELLO WORLD"
lower("ABCDE-XYZ")                # → "abcde-xyz"
trim("  hello world  ")           # → "hello world"
trim("\t  abc  \n")               # → "abc"

replace("a-b-c-d", "-", "/")      # → "a/b/c/d"  (tất cả)
replace("2025_01_15", "_", "-")   # → "2025-01-15"

substitute("aababc", "a", "X")     # → "XXbXbc"   (tất cả)
substitute("aababc", "a", "X", 1)  # → "Xababc"   (lần 1)
substitute("aababc", "a", "X", 2)  # → "aXbabc"   (lần 2)
substitute("aababc", "ab", "Y", 1) # → "aYabc"

find("2025", "HD-2025-001")        # → 4   (1-based)
find("X",    "HD-2025-001")        # → 0   (không tìm thấy)
find("a", "banana", 2)             # → 2   (tìm từ vị trí 2)

{"name": "MA_CHUAN",    "formula": "upper(trim(MA_NHAP))"}
{"name": "URL_SP",      "formula": "replace(lower(TEN_SP), ' ', '-')"}
{"name": "NAM_TU_MA",   "formula": "mid(MA_CT, find('-', MA_CT) + 1, 4)"}
```

### str / int / float / safe_str / to_number

```python
str(12345)           # → "12345"
str(3.14)            # → "3.14"
int(3.9)             # → 3
int("42")            # → 42
float("3.14")        # → 3.14
float(True)          # → 1.0

safe_str(None)       # → ""   (thay vì "None")
safe_str(0)          # → "0"
safe_str("")         # → ""

to_number("1,234.5")          # → 1234.5
to_number("$ 50,000 VNĐ")    # → 50000.0
to_number(None, default=0)    # → 0.0

{"name": "MA_DON", "formula": "concat('DH-', str(year(NGAY)), '-', str(STT))"}
```

---

## 9. Ngày tháng

### year / month / day / quarter

```python
# Nhận: date, datetime, ISO string, VN format
year("2025-07-15")        # → 2025
year("15/07/2025")        # → 2025    (VN format)
month("2025-07-15")       # → 7
day("2025-07-15")         # → 15
quarter("2025-07-15")     # → 3   (Q3: tháng 7–9)
quarter("2025-01-01")     # → 1
quarter("2025-10-31")     # → 4

{"name": "QUY_HD",       "formula": "quarter(NGAY_HD)"}
{"name": "NAM_THANG",    "formula": "concat(str(year(NGAY)), 'Q', str(quarter(NGAY)))"}
{"name": "DT_THANG_NAY", "formula": "sum(r['dt'] for r in DON_HANG if month(r['ngay']) = THANG_HT)"}
```

### date_diff

```python
# date_diff(date1, date2, unit='days')  → date1 - date2
date_diff("2025-12-31", "2025-01-01", "days")     # → 364
date_diff("2025-12-31", "2025-01-01", "months")   # → 11
date_diff("2025-12-31", "2024-01-01", "years")    # → 1
date_diff("2025-01-01", "2025-12-31", "days")     # → -364  (âm)
date_diff("2025-12-31", "2025-12-01", "hours")    # → 720.0

{"name": "TUOI_NO",     "formula": "date_diff(NGAY_HOM_NAY, NGAY_THANH_TOAN, 'days')"}
{"name": "SO_THANG_HD", "formula": "date_diff(NGAY_KT, NGAY_BD, 'months')"}
{"name": "QUA_HAN",     "formula": "date_diff(NGAY_HOM_NAY, NGAY_HEN_TRA, 'days') > 0"}
{"name": "PHI_TRE_HAN", "formula": "IF(QUA_HAN, TUOI_NO * PHI_TREN_NGAY, 0)"}
```

### date_add

```python
# date_add(dt, days=0, months=0, years=0) → date
# Xử lý đúng cuối tháng (31/1 + 1m = 28/2)
date_add("2025-01-15", days=10)          # → date(2025,1,25)
date_add("2025-01-15", months=1)         # → date(2025,2,15)
date_add("2025-01-31", months=1)         # → date(2025,2,28)  (cuối tháng)
date_add("2025-01-31", months=3)         # → date(2025,4,30)
date_add("2025-01-15", years=1)          # → date(2026,1,15)
date_add("2025-01-15", days=5, months=2) # → date(2025,3,20)

{"name": "NGAY_HEN_TRA",   "formula": "date_add(NGAY_GIAO, days=30)"}
{"name": "NGAY_HET_BH",    "formula": "date_add(NGAY_MUA, years=1)"}
{"name": "NGAY_NHAC_LICH", "formula": "date_add(NGAY_HEN_TRA, days=-3)"}
```

### date_format / workdays

```python
date_format("2025-07-15")                # → "15/07/2025"  (mặc định VN)
date_format("2025-07-15", "%Y-%m")       # → "2025-07"
date_format("2025-07-15", "%d/%m/%Y")    # → "15/07/2025"
date_format("2025-07-15", "%B %Y")       # → "July 2025"   (locale EN)
date_format("2025-07-15", "Tháng %m/%Y") # → "Tháng 07/2025"

workdays("2025-01-01", "2025-01-31")     # → 23  (bỏ T7, CN)
workdays("2025-01-20", "2025-01-10")     # → -8  (âm nếu d1 < d2)

{"name": "THANG_NAM",  "formula": "date_format(NGAY_HD, '%m/%Y')"}
{"name": "NGAY_NGHI",  "formula": "date_diff(NGAY_KT, NGAY_BD, 'days') - workdays(NGAY_BD, NGAY_KT)"}
```

---

## 10. Tiện ích

### coalesce

```python
coalesce(None, "", 0, 5, 10)     # → 0    (0 khác None/"")
coalesce(None, None, "hello")    # → "hello"
coalesce(None, 0.0, 100)         # → 0.0  (0.0 hợp lệ)
coalesce(None, [])               # → []   (list rỗng hợp lệ)
coalesce()                        # → None

{"name": "GIA_AP_DUNG",
 "formula": "coalesce(GIA_DAC_BIET, GIA_KHUYEN_MAI, GIA_NIEM_YET)"}
{"name": "DIA_CHI_GN",
 "formula": "coalesce(DIA_CHI_GIAO_HANG, DIA_CHI_HOA_DON, DIA_CHI_MAC_DINH)"}
```

### safe_str / len_text / find

```python
safe_str(None)         # → ""
safe_str(0)            # → "0"
safe_str([1,2,3])      # → "[1, 2, 3]"

len_text("Hello")      # → 5
len_text("")           # → 0

find("abc", "xyzabcdef")    # → 4   (1-based)
find("xyz", "abcdef", 1)    # → 0   (không tìm thấy)
```

### now / today (chỉ khi deterministic=False)

```python
# Cần khởi tạo engine với deterministic=False
engine = FormulaEngine(formulas=[...], deterministic=False)

{"name": "NGAY_TINH",     "formula": "today()"}
{"name": "GIO_CAP_NHAT",  "formula": "now()"}
{"name": "TUOI_TS",       "formula": "date_diff(today(), NGAY_MUA, 'years')"}
{"name": "THANG_TINH",    "formula": "month(today())"}
```

---

## 11. Ví dụ kết hợp nâng cao

### Bài 1 — Bảng lương đầy đủ

```python
formulas = [
    # Phụ cấp theo loại
    {"name": "PC_AN_TRUA",    "formula": "sum_by_type(DS_PHU_CAP, 0, 1, 'Ăn trưa')"},
    {"name": "PC_XANG_XE",    "formula": "sum_by_type(DS_PHU_CAP, 0, 1, 'Xăng xe')"},
    {"name": "PC_DIEN_THOAI", "formula": "sum_by_type(DS_PHU_CAP, 0, 1, 'Điện thoại')"},
    {"name": "TONG_PHU_CAP",  "formula": "PC_AN_TRUA + PC_XANG_XE + PC_DIEN_THOAI"},
    # Lương
    {"name": "LUONG_CB",      "formula": "HE_SO * MUC_LUONG_CO_BAN"},
    {"name": "LUONG_GROSS",   "formula": "LUONG_CB + TONG_PHU_CAP"},
    # Bảo hiểm NLĐ
    {"name": "BH_XH",         "formula": "min(LUONG_GROSS, 36 * LUONG_CSTT) * 8%"},
    {"name": "BH_YT",         "formula": "min(LUONG_GROSS, 36 * LUONG_CSTT) * 1.5%"},
    {"name": "BH_TN",         "formula": "min(LUONG_GROSS, 20 * LUONG_CSTT) * 1%"},
    {"name": "TONG_BH",       "formula": "BH_XH + BH_YT + BH_TN"},
    # Giảm trừ gia cảnh
    {"name": "GIAM_TRU_BT",   "formula": "11_000_000"},
    {"name": "GIAM_TRU_PN",   "formula": "4_400_000 * SO_NGUOI_PHU_THUOC"},
    {"name": "TONG_GIAM_TRU", "formula": "GIAM_TRU_BT + GIAM_TRU_PN"},
    # Thu nhập chịu thuế
    {"name": "TNT",  "formula": "max(LUONG_GROSS - TONG_BH - TONG_GIAM_TRU, 0)"},
    # Thuế TNCN lũy tiến
    {"name": "THUE_TNCN", "formula": """
IFS(
    TNT <= 0,            0,
    TNT <= 5_000_000,    TNT * 5%,
    TNT <= 10_000_000,   TNT * 10% - 250_000,
    TNT <= 18_000_000,   TNT * 15% - 750_000,
    TNT <= 32_000_000,   TNT * 20% - 1_650_000,
    TNT <= 52_000_000,   TNT * 25% - 3_250_000,
    TNT <= 80_000_000,   TNT * 30% - 5_850_000,
    True,                TNT * 35% - 9_850_000
)"""},
    # Lương thực lĩnh
    {"name": "LUONG_THUC_LINH", "formula": "LUONG_GROSS - TONG_BH - THUE_TNCN"},
    # KPI và thưởng
    {"name": "TY_LE_KPI",   "formula": "percent_of(DOANH_SO_THUC, CHI_TIEU)"},
    {"name": "HE_SO_THUONG","formula": "clamp(TY_LE_KPI / 100, 0.0, 2.0)"},
    {"name": "TIEN_THUONG",
     "formula": "IF(between(TY_LE_KPI, 60, 300), LUONG_CB * HE_SO_THUONG, 0)"},
    {"name": "TONG_NHAN",   "formula": "LUONG_THUC_LINH + TIEN_THUONG"},
]
```

### Bài 2 — Phân tích đơn hàng theo thời gian

```python
formulas = [
    # Tổng hợp cơ bản
    {"name": "TONG_DON_HANG",  "formula": "count(DON_HANG, key='so_tien')"},
    {"name": "TONG_DOANH_THU", "formula": "sum(DON_HANG, key='so_tien')"},
    {"name": "DON_HANG_TB",    "formula": "safe_div(TONG_DOANH_THU, TONG_DON_HANG)"},

    # Lọc theo khoảng thời gian
    {"name": "DH_THANG_NAY",
     "formula": "filter_array(DON_HANG, key='thang', value=THANG_TINH)"},
    {"name": "DT_THANG_NAY",
     "formula": "sum(r['so_tien'] for r in DH_THANG_NAY)"},
    {"name": "SO_DH_THANG_NAY",
     "formula": "count(DH_THANG_NAY, key='so_tien')"},

    # Top khách hàng
    {"name": "DT_THEO_KH",
     "formula": "group_sum(DON_HANG, 'ma_kh', 'so_tien')"},
    {"name": "TOP_KH",
     "formula": "last(DON_HANG, sort_by='so_tien', group_by='ma_kh', value_key='ma_kh')"},

    # Giá trị trung bình 3 tháng gần nhất
    {"name": "DT_3THANG_GAN",
     "formula": "last(sorted_array(THANG_DATA, key='thang'), n=3, preserve_order=True)"},
    {"name": "DT_TB_3T",
     "formula": "safe_div(sum(r['doanh_thu'] for r in DT_3THANG_GAN), 3)"},

    # So sánh với tháng trước
    {"name": "DT_THANG_TRUOC",
     "formula": "last(THANG_DATA, sort_by='thang', n=2, value_key='doanh_thu')[0]"},
    {"name": "TANG_GIAM",
     "formula": "DT_THANG_NAY - DT_THANG_TRUOC"},
    {"name": "TANG_GIAM_PCT",
     "formula": "percent_of(TANG_GIAM, DT_THANG_TRUOC)"},

    # Phân loại tháng
    {"name": "NHAN_XET",
     "formula": """
IFS(
    TANG_GIAM_PCT >= 20, 'Tăng trưởng mạnh',
    TANG_GIAM_PCT >= 5,  'Tăng trưởng tốt',
    TANG_GIAM_PCT >= 0,  'Ổn định',
    TANG_GIAM_PCT >= -10,'Giảm nhẹ',
    True,                'Cần chú ý'
)"""},
]
```

### Bài 3 — Dự toán xây dựng + tra bảng giá

```python
formulas = [
    # Khối lượng
    {"name": "THE_TICH_BETONG",  "formula": "CHIEU_DAI * CHIEU_RONG * DO_DAY"},
    {"name": "DIEN_TICH_COFFA",  "formula": "(CHIEU_DAI * DO_DAY + CHIEU_RONG * DO_DAY) * 2"},
    # Tra bảng đơn giá
    {"name": "DG_BETONG",  "formula": "vlookup(MAC_BETONG, BANG_GIA_BETONG, 2, 0)"},
    {"name": "DG_COFFA",   "formula": "vlookup(LOAI_COFFA, BANG_GIA_COFFA,  2, 0)"},
    {"name": "DG_THEPCB",  "formula": "vlookup(CHUNG_LOAI_THEP, BANG_GIA_THEP, 2, 0)"},
    # Chi phí vật liệu
    {"name": "CP_BETONG",  "formula": "THE_TICH_BETONG * DG_BETONG"},
    {"name": "CP_COFFA",   "formula": "DIEN_TICH_COFFA * DG_COFFA"},
    {"name": "CP_THEP",    "formula": "KL_THEP * DG_THEPCB"},
    {"name": "TONG_VL",    "formula": "CP_BETONG + CP_COFFA + CP_THEP"},
    # Chi phí nhân công (tra bảng)
    {"name": "DG_NC_DO",   "formula": "vlookup('Đổ bê tông', BANG_GIA_NC, 2, 0)"},
    {"name": "DG_NC_GIA",  "formula": "vlookup('Gia cốt thép', BANG_GIA_NC, 2, 0)"},
    {"name": "NC_DO",      "formula": "THE_TICH_BETONG * DG_NC_DO"},
    {"name": "NC_GIA",     "formula": "KL_THEP * DG_NC_GIA"},
    {"name": "TONG_NC",    "formula": "NC_DO + NC_GIA"},
    # Chi phí trực tiếp và gián tiếp
    {"name": "CP_TRUC_TIEP", "formula": "TONG_VL + TONG_NC"},
    {"name": "CP_GIAN_TIEP", "formula": "CP_TRUC_TIEP * TY_LE_CPC"},
    {"name": "LNCTT",        "formula": "CP_TRUC_TIEP * TY_LE_LNCTT"},
    {"name": "GIA_TRUOC_THUE","formula": "CP_TRUC_TIEP + CP_GIAN_TIEP + LNCTT"},
    {"name": "THUE_GTGT",    "formula": "GIA_TRUOC_THUE * 10%"},
    {"name": "GIA_SAU_THUE", "formula": "GIA_TRUOC_THUE + THUE_GTGT"},
    # Làm tròn
    {"name": "GIA_SAU_THUE_TRON",
     "formula": "roundup(GIA_SAU_THUE / 1_000_000, 0) * 1_000_000"},
]
```

### Bài 4 — Dashboard KPI đa chiều

```python
formulas = [
    # ── Cá nhân ──
    {"name": "KPI_CA_NHAN",
     "formula": "percent_of(DOANH_SO_CA_NHAN, CHI_TIEU_CA_NHAN)"},
    {"name": "XEP_LOAI_CA_NHAN",
     "formula": "IFS(KPI_CA_NHAN>=120,'Xuất sắc', KPI_CA_NHAN>=100,'Đạt', KPI_CA_NHAN>=80,'Gần đạt', True,'Chưa đạt')"},

    # ── Nhóm ──
    {"name": "TONG_DS_NHOM",
     "formula": "sumifs(THANH_VIEN, key='doanh_so', nhom=MA_NHOM)"},
    {"name": "KPI_NHOM",
     "formula": "percent_of(TONG_DS_NHOM, CHI_TIEU_NHOM)"},
    {"name": "XEP_HANG_TRONG_NHOM",
     "formula": "match(DOANH_SO_CA_NHAN, sorted_array(map_key(filter_array(THANH_VIEN, key='nhom', value=MA_NHOM), 'doanh_so'), reverse=True), 0)"},

    # ── Lịch sử ──
    {"name": "DS_THANG_TRUOC",
     "formula": "last(LICH_SU_CA_NHAN, sort_by='thang', value_key='doanh_so', default=0)"},
    {"name": "TANG_TRUONG",
     "formula": "percent_of(DOANH_SO_CA_NHAN - DS_THANG_TRUOC, DS_THANG_TRUOC)"},
    {"name": "DS_TB_3T",
     "formula": "safe_div(sum(r['doanh_so'] for r in last(LICH_SU_CA_NHAN, sort_by='thang', n=3)), 3)"},

    # ── Thưởng ──
    {"name": "HE_SO_THUONG",
     "formula": "SWITCH(XEP_LOAI_CA_NHAN, 'Xuất sắc', 0.3, 'Đạt', 0.15, 'Gần đạt', 0.05, 0)"},
    {"name": "TIEN_THUONG_CA_NHAN",
     "formula": "LUONG_CB * HE_SO_THUONG"},
    {"name": "BONUS_TANG_TRUONG",
     "formula": "IF(TANG_TRUONG >= 20, DOANH_SO_CA_NHAN * 0.01, 0)"},
    {"name": "TONG_THUONG",
     "formula": "TIEN_THUONG_CA_NHAN + BONUS_TANG_TRUONG"},

    # ── Dự báo ──
    {"name": "DU_BAO_THANG_SAU",
     "formula": "DS_TB_3T * (1 + clamp(TANG_TRUONG / 100, -0.3, 0.5))"},
]
```

### Bài 5 — Xử lý dữ liệu phức tạp

```python
formulas = [
    # Chuẩn hóa mã hàng
    {"name": "MA_HANG_CHUAN",    "formula": "upper(trim(replace(MA_HANG_RAW, ' ', '')))"},

    # Phân tích mã để lấy thông tin
    {"name": "LOAI_HANG",        "formula": "left(MA_HANG_CHUAN, 2)"},
    {"name": "NAM_SAN_XUAT",     "formula": "int(mid(MA_HANG_CHUAN, 3, 4))"},
    {"name": "STT_LOT",          "formula": "right(MA_HANG_CHUAN, 4)"},

    # Tra bảng thông tin
    {"name": "TEN_LOAI",
     "formula": "vlookup(LOAI_HANG, [['SP','Sản phẩm'],['VT','Vật tư'],['HH','Hàng hóa']], 2, 'Khác')"},

    # Tính tuổi hàng hóa
    {"name": "TUOI_THANG",
     "formula": "date_diff(NGAY_KIEM_KHO, concat(str(NAM_SAN_XUAT), '-01-01'), 'months')"},
    {"name": "NHOM_TUOI",
     "formula": "IFS(TUOI_THANG <= 3,'Mới',TUOI_THANG <= 12,'Trung bình',TUOI_THANG <= 24,'Cũ',True,'Rất cũ')"},

    # Giá theo tuổi
    {"name": "TY_LE_GIAM_GIA",
     "formula": "SWITCH(NHOM_TUOI,'Mới',0,'Trung bình',0.1,'Cũ',0.25,'Rất cũ',0.5)"},
    {"name": "GIA_HIEN_TAI",
     "formula": "GIA_GHI_SO * (1 - TY_LE_GIAM_GIA)"},
    {"name": "TONG_GIA_TRI_KHO",
     "formula": "GIA_HIEN_TAI * SO_LUONG_TON"},

    # Đề xuất xử lý
    {"name": "DE_XUAT",
     "formula": """
IFS(
    and_(NHOM_TUOI = 'Rất cũ', SO_LUONG_TON > 0), 'Thanh lý ngay',
    and_(NHOM_TUOI = 'Cũ', SO_LUONG_TON > 100),   'Khuyến mãi mạnh',
    NHOM_TUOI = 'Cũ',                               'Theo dõi',
    True,                                            'Bình thường'
)"""},
]
```

### Bài 6 — Tính giá vật liệu xây dựng có phụ kiện động

```python
formulas = [
    # Diện tích và chu vi
    {"name": "DIEN_TICH",        "formula": "CHIEU_DAI * CHIEU_RONG"},
    {"name": "CHU_VI",           "formula": "(CHIEU_DAI + CHIEU_RONG) * 2"},

    # Vật liệu chính (có hao hụt)
    {"name": "NHOM_THANH_MET",   "formula": "CHU_VI * 1.05"},   # +5% hao hụt
    {"name": "KINH_M2",          "formula": "DIEN_TICH * 1.02"},  # +2% hao hụt

    # Phụ kiện theo loại cửa
    {"name": "SO_BANH_XE",       "formula": "IF(LOAI_CUA = 'Trượt', 4, 0)"},
    {"name": "SO_BAN_LE",        "formula": "IF(LOAI_CUA = 'Mở quay', 2, 0)"},
    {"name": "SO_KHOA",          "formula": "IF(LOAI_CUA = 'Trượt', 1, 1)"},

    # Đơn giá tra bảng
    {"name": "DG_NHOM",  "formula": "vlookup(LOAI_NHOM,  BANG_GIA_NHOM,  2, 0)"},
    {"name": "DG_KINH",  "formula": "vlookup(DO_DAY_KINH, BANG_GIA_KINH, 2, 0)"},

    # Thành tiền vật liệu
    {"name": "TIEN_NHOM",        "formula": "NHOM_THANH_MET * DG_NHOM"},
    {"name": "TIEN_KINH",        "formula": "KINH_M2 * DG_KINH"},
    {"name": "TIEN_PHU_KIEN",
     "formula": "SO_BANH_XE * 150_000 + SO_BAN_LE * 80_000 + SO_KHOA * 250_000"},
    {"name": "TONG_VAT_LIEU",    "formula": "TIEN_NHOM + TIEN_KINH + TIEN_PHU_KIEN"},

    # Nhân công
    {"name": "CONG_LAP_DAT",     "formula": "DIEN_TICH * 0.5"},
    {"name": "TIEN_CONG",        "formula": "CONG_LAP_DAT * 250_000"},

    # Tổng và giá bán
    {"name": "TONG_CHI_PHI",     "formula": "TONG_VAT_LIEU + TIEN_CONG"},
    {"name": "LOI_NHUAN",        "formula": "TONG_CHI_PHI * HE_SO_LOI_NHUAN"},
    {"name": "GIA_BAN",          "formula": "TONG_CHI_PHI + LOI_NHUAN"},
    {"name": "GIA_BAN_M2",       "formula": "safe_div(GIA_BAN, DIEN_TICH)"},
    {"name": "GIA_BAN_TRON",     "formula": "roundup(GIA_BAN / 100_000, 0) * 100_000"},
]
```

---

## Bảng Tham Chiếu Nhanh

### Chọn hàm đúng cho từng tình huống

| Tình huống              | Hàm nên dùng                                                   |
| ----------------------- | -------------------------------------------------------------- |
| Tổng list số            | `sum(lst)`                                                     |
| Tổng list[dict]         | `sum(rows, key='field')` hoặc `sum(r['f'] for r in rows)`      |
| Tổng có 1 điều kiện     | `sumif(rows, 'IT', key=('phong','luong'))`                     |
| Tổng có nhiều điều kiện | `sumifs(rows, key='luong', phong='IT', loai='CT')`             |
| Đếm phần tử             | `count(lst)` / `countif(lst, '>0')`                            |
| Trung bình              | `average(lst)` / `averageif(...)`                              |
| Lấy giá mới nhất        | `last(data, sort_by='ngay', value_key='gia')`                  |
| Lấy n phần tử cuối      | `last(data, sort_by='ngay', n=3)`                              |
| Nhóm và tổng            | `group_sum(rows, 'nhom', 'gia_tri')`                           |
| Nhóm mới nhất           | `last(rows, sort_by='ngay', group_by='nhom', value_key='gia')` |
| Lọc list                | `filter_array(rows, key='loai', value='A')`                    |
| Sắp xếp                 | `sorted_array(rows, key='field', reverse=True)`                |
| Tra bảng giá            | `vlookup(ma, bang, col, default)`                              |
| Điều kiện đơn           | `IF(cond, a, b)`                                               |
| Nhiều nhánh             | `IFS(c1,v1, c2,v2, True,default)`                              |
| Switch-case             | `SWITCH(expr, v1,r1, v2,r2, default)`                          |
| Null-safe               | `coalesce(a, b, c)`                                            |
| Chia an toàn            | `safe_div(a, b, 0)`                                            |
| Giới hạn phạm vi        | `clamp(x, lo, hi)`                                             |
| Tính %                  | `percent_of(part, total)`                                      |
| Nối chuỗi               | `concat(a, b, c)` / `textjoin(', ', True, a, b)`               |
| Tra ngày                | `date_diff(d1, d2, 'months')` / `date_add(d, months=1)`        |

---

_Formula Utils v29.1.0 — Pure Python · Zero Dependencies_
