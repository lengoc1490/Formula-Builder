# Formula Utils v29.1 — Hướng Dẫn Toàn Diện A-Z

> **Pure Python · Zero External Dependencies · ENGINE_VERSION = "29.1.0"**  
> File: `formula_utils.py` · Ứng dụng: Lương, giá thành, dự toán, KPI, phân bổ, BOM, ERP và mọi domain tính toán.

---

## Mục Lục

| #   | Phần                                                                                   |
| --- | -------------------------------------------------------------------------------------- |
| §1  | [Kiến trúc & Import](#1-kiến-trúc--import)                                             |
| §2  | [FormulaEngine — Khởi tạo & Cấu hình](#2-formulaengine--khởi-tạo--cấu-hình)            |
| §3  | [Cú pháp công thức](#3-cú-pháp-công-thức)                                              |
| §4  | [Hàm toán học](#4-hàm-toán-học)                                                        |
| §5  | [Hàm logic & điều kiện](#5-hàm-logic--điều-kiện)                                       |
| §6  | [Hàm tổng hợp — sum, min, max, average, count](#6-hàm-tổng-hợp)                        |
| §7  | [Hàm tổng hợp có điều kiện](#7-hàm-tổng-hợp-có-điều-kiện)                              |
| §8  | [Hàm mảng & collection](#8-hàm-mảng--collection)                                       |
| §9  | [⭐ Hàm last — Phân tích & Hướng dẫn đầy đủ](#9-hàm-last--phân-tích--hướng-dẫn-đầy-đủ) |
| §10 | [Hàm lookup — vlookup, xlookup](#10-hàm-lookup)                                        |
| §11 | [Hàm chuỗi](#11-hàm-chuỗi)                                                             |
| §12 | [Hàm ngày tháng](#12-hàm-ngày-tháng)                                                   |
| §13 | [Hàm tiện ích](#13-hàm-tiện-ích)                                                       |
| §14 | [calculate() và các biến thể](#14-calculate-và-các-biến-thể)                           |
| §15 | [IncrementalContext — Tính toán tăng tiến](#15-incrementalcontext)                     |
| §16 | [Explain API](#16-explain-api)                                                         |
| §17 | [Multi-Scenario & Diff](#17-multi-scenario--diff)                                      |
| §18 | [FormulaValidator — Kiểm tra AST tĩnh](#18-formulavalidator)                           |
| §19 | [Snapshot & Audit — EnterpriseSnapshot](#19-snapshot--audit)                           |
| §20 | [TimeBucket — Quản lý kỳ thời gian](#20-timebucket)                                    |
| §21 | [Allocation Engine — Phân bổ chi phí](#21-allocation-engine)                           |
| §22 | [TopoSort — Sắp xếp DAG](#22-toposort)                                                 |
| §23 | [SCC TopoSort — Đồ thị có chu kỳ](#23-scc-toposort)                                    |
| §24 | [SccLinearSolver — Giải hệ tuyến tính](#24-scclinearsolver)                            |
| §25 | [Hệ thống lỗi](#25-hệ-thống-lỗi)                                                       |
| §26 | [Ví dụ thực tế tổng hợp](#26-ví-dụ-thực-tế-tổng-hợp)                                   |

---

## §1. Kiến trúc & Import

### 1.1 Sơ đồ lớp

```
formula_utils.py
│
├── FormulaEngineCore           ← parse AST, DAG topological sort, eval, budget guard
│   └── FormulaEngineTrace      ← + execution trace (old→new, triggered_by, exec_ms)
│       └── FormulaEngineAudit  ← + audit session, batch audit, forensic report
│           └── FormulaEngine   ← PUBLIC API đầy đủ ← LUÔN DÙNG CLASS NÀY
│
├── BASE_FUNCS                  ← 80+ hàm built-in
├── TimeBucket v3               ← kỳ thời gian (year/half/quarter/month/week)
├── AllocationEngine            ← 8 phương pháp phân bổ chi phí
├── TopoSorter / topo_sort()    ← sort DAG data rows (cycle = fatal)
├── SccTopoSorter               ← sort cycle-aware (Tarjan SCC)
├── SccLinearSolver             ← giải (I-A)x=b trên graph
├── EnterpriseSnapshot          ← chốt số 5-layer, dual-hash, audit trail
├── IncrementalContext          ← tính toán tăng tiến
└── FormulaValidator            ← validate AST tĩnh
```

### 1.2 Chọn công cụ đúng

| Bài toán                           | Công cụ                       |
| ---------------------------------- | ----------------------------- |
| Công thức phụ thuộc nhau           | `FormulaEngine.calculate()`   |
| Reactive UI (user sửa field)       | `calculate_incremental()`     |
| Sort items DAG, **không** có cycle | `topo_sort()`                 |
| Sort items **có** cycle            | `scc_topo_sort_with_info()`   |
| Giải `x = Ax + b`, có cycle        | `solve_linear_on_graph()`     |
| Phân bổ chi phí nhiều phương pháp  | `allocate()`                  |
| Kỳ thời gian (Q1/2025, M3…)        | `generate_time_buckets()`     |
| Chốt số bất biến, lưu vết          | `EnterpriseSnapshot`          |
| Validate formula trước khi lưu     | `FormulaValidator.validate()` |

### 1.3 Import thường dùng

```python
# Core
from formula_utils import FormulaEngine, InputField, OutputField, FormulaSetMeta

# Lỗi
from formula_utils import (
    FormulaError, ErrorCode,
    FormulaBudgetExceeded, FormulaComplexityError,
    FormulaValidationError, FormulaDeterministicError,
)

# Snapshot
from formula_utils import (
    EnterpriseSnapshot, SnapshotTag, SnapshotStatus,
    SnapshotManager, SnapshotRegistry,
)

# Incremental
from formula_utils import IncrementalContext, IncrementalStats

# Validate
from formula_utils import FormulaValidator, ValidationResult

# Graph
from formula_utils import solve_linear_on_graph, SccLinearSolver
from formula_utils import scc_topo_sort, scc_topo_sort_with_info
from formula_utils import topo_sort, topo_sort_with_info, TopoSorter

# Allocation
from formula_utils import allocate, allocate_inplace, allocate_fast, AllocationEngine

# TimeBucket
from formula_utils import (
    generate_time_buckets, generate_time_buckets_flat,
    get_period, get_period_by_date, get_period_offset,
    same_period_last_year, TimeBucket, TB_FORMAT,
)

# Tiện ích
from formula_utils import BASE_FUNCS, hash_formulas, normalize_formula
```

---

## §2. FormulaEngine — Khởi tạo & Cấu hình

### 2.1 Cú pháp đầy đủ

```python
from formula_utils import FormulaEngine, InputField, OutputField, FormulaSetMeta
from datetime import date

engine = FormulaEngine(
    # ── BẮT BUỘC ────────────────────────────────────────────────────
    formulas = [
        {"name": "TONG_CP",   "formula": "NVL + NC + CPC"},
        {"name": "DON_GIA",   "formula": "TONG_CP / SAN_LUONG",      "bucket": "gia"},
        {"name": "GIA_BAN",   "formula": "DON_GIA * (1 + BIEN_LAI)", "bucket": "gia"},
        {"name": "THUE_VAT",  "formula": "GIA_BAN * 10%"},
        {"name": "TONG_TIEN", "formula": "GIA_BAN + THUE_VAT"},
    ],

    # ── SCHEMA ĐẦU VÀO (tùy chọn) ───────────────────────────────────
    input_fields = [
        InputField(name="NVL",       dtype=float, required=True,  description="Chi phí NVL"),
        InputField(name="NC",        dtype=float, required=True),
        InputField(name="CPC",       dtype=float, required=True),
        InputField(name="SAN_LUONG", dtype=float, required=True),
        InputField(name="BIEN_LAI",  dtype=float, required=False, default=0.15),
    ],

    # ── SCHEMA ĐẦU RA (tùy chọn, chỉ metadata) ──────────────────────
    output_fields = [
        OutputField(name="DON_GIA",   unit="VND/đv", primary=True),
        OutputField(name="TONG_TIEN", unit="VND",    primary=True),
    ],

    # ── XỬ LÝ LỖI ───────────────────────────────────────────────────
    on_error      = "default",   # "raise" | "null" | "default"
    default_value = 0,
    strict        = False,

    # ── HÀM TUỲ CHỈNH ───────────────────────────────────────────────
    safe_funcs = {
        "round_vnd": lambda v: round(float(v or 0) / 1000) * 1000,
    },

    # ── ASSERTIONS ───────────────────────────────────────────────────
    assertions = [
        {"name": "don_gia_duong", "expr": "DON_GIA > 0",
         "message": "Đơn giá phải dương", "severity": "ERROR"},
    ],

    # ── LÀM TRÒN ────────────────────────────────────────────────────
    rounding_policy = {
        "DON_GIA":   {"decimals": 0},
        "TONG_TIEN": {"decimals": 0},
    },

    # ── GIỚI HẠN & BẢO VỆ ───────────────────────────────────────────
    max_operations       = None,   # None = không giới hạn
    max_formula_count    = None,
    max_dependency_depth = None,
    max_iterable_size    = None,
    max_subscript_depth  = 5,

    # ── TÍNH NĂNG ────────────────────────────────────────────────────
    deterministic    = True,    # True = chặn now()/today()
    validate_on_init = False,

    # ── META ─────────────────────────────────────────────────────────
    meta = FormulaSetMeta(
        id             = "bang_gia_sp_v1",
        version        = "1.0.0",
        name           = "Bảng giá sản phẩm",
        effective_from = date(2025, 1, 1),
        frozen         = False,
    ),
)
```

### 2.2 on_error — 3 chế độ

| Giá trị     | Khi công thức lỗi                 | Khi nào dùng                   |
| ----------- | --------------------------------- | ------------------------------ |
| `"default"` | Trả `default_value` (0), tiếp tục | Production                     |
| `"null"`    | Trả `None`, tiếp tục              | Cần phân biệt lỗi vs giá trị 0 |
| `"raise"`   | Raise `FormulaError` ngay         | Debug                          |

```python
# raise — debug
engine_debug = FormulaEngine([{"name": "KQ", "formula": "A / B"}], on_error="raise")
try:
    engine_debug.calculate({"A": 10, "B": 0})
except FormulaError as e:
    print(e.code)       # ENGINE.INVALID_TYPE
    print(e.field_name) # "KQ"

# null — phân biệt lỗi vs giá trị 0
engine_null = FormulaEngine([{"name": "KQ", "formula": "A / B"}], on_error="null")
r = engine_null.calculate({"A": 10, "B": 0})
print(r["KQ"])  # None

# default — production safe
engine_prod = FormulaEngine([{"name": "KQ", "formula": "A / B"}], on_error="default")
r = engine_prod.calculate({"A": 10, "B": 0})
print(r["KQ"])  # 0
```

### 2.3 register_formula() — thêm công thức động

```python
vr = engine.register_formula(
    name        = "PHU_CAP",
    formula     = "LUONG_CB * 0.3",
    known_names = {"LUONG_CB"},
    validate    = True,
)
print(vr.ok)          # True
print(vr.normalized)  # công thức đã chuẩn hóa
# DAG tự rebuild, hash tự cập nhật
```

### 2.4 get_metadata()

```python
meta = engine.get_metadata()
print(meta["engine_version"])   # "29.1.0"
print(meta["formula_count"])    # 5
print(meta["topo_order"])       # thứ tự tính theo DAG
print(meta["dag_depth"])        # độ sâu phụ thuộc
print(meta["formula_hash"])     # SHA-256 formula set
print(meta["deterministic"])    # True
print(meta["groups"])           # {"": [...], "gia": [...]}
```

---

## §3. Cú pháp công thức

Engine dùng `ast.parse(mode='eval')` — chỉ nhận **biểu thức**, không nhận **câu lệnh**.

### 3.1 Số học và so sánh

```python
# Toán tử số học
"A + B * C / D"
"A ** 2"    # lũy thừa
"A % B"     # modulo

# So sánh — Excel-style tự động chuẩn hóa
"A = B"     # → A == B
"A <> B"    # → A != B
"A >= 100"
"A != B"

# Phần trăm — tự động chuẩn hóa
"GIA_BAN * 10%"   # → GIA_BAN * (10/100)
"A * 0.5%"        # → A * 0.005
```

### 3.2 Điều kiện

```python
# IF — Excel-style
"IF(A > 0, A, 0)"
"IF(LOAI = 'A', GIA_A, GIA_B)"

# Lồng IF
"IF(LOAI = 'A', GIA_A, IF(LOAI = 'B', GIA_B, GIA_MAC_DINH))"
```

### 3.3 List comprehension (chỉ bên trong hàm)

```python
# ✅ Hợp lệ — generator bên trong sum/min/max/any/all
"sum(r['qty'] * r['price'] for r in items)"
"max(r['score'] for r in nhan_vien if r['phong'] = 'IT')"
"any(r['vi_pham'] for r in ho_so)"

# ❌ KHÔNG hợp lệ
# "(x for x in lst)"        → SecurityViolation (standalone generator)
# "{k: v for k, v in d}"   → SecurityViolation (DictComp)
# "{x for x in lst}"        → SecurityViolation (SetComp)
```

### 3.4 Keyword arguments — dấu `=` không bị convert

```python
# Tham số có tên (len≥3, trong whitelist) giữ nguyên dấu =
"sorted_array(rows, sort_by='ngay', reverse=True)"
"safe_div(A, B, default=0)"
"last(rows, sort_by='ngay', value_key='gia')"
"filter_array(rows, key='loai', value='A')"
"date_diff(NGAY_KT, NGAY_BD, unit='months')"
```

### 3.5 Những gì KHÔNG được phép

```python
# ❌ import, exec, lambda, def, class
# ❌ gán (=, +=, :=)
# ❌ tên nguy hiểm: os, sys, eval, exec, globals, __import__
# ❌ attribute không whitelist (.format(), .append(), .strip() v.v.)
# ✅ Chỉ được: .get(), .keys(), .values(), .items(), .to_dict()
```

---

## §4. Hàm toán học

### 4.1 abs, round, roundup, rounddown, ceil, floor

```python
# abs(x) → giá trị tuyệt đối
abs(-5)        # → 5
abs(-3.14)     # → 3.14

# round(x, n=0) → banker's rounding
round(3.456, 2)   # → 3.46
round(1234.56, 0) # → 1235.0

# roundup(x, d=0) → luôn làm tròn LÊN
roundup(3.21, 0)   # → 4.0
roundup(3.21, 1)   # → 3.3
roundup(-3.1, 0)   # → -3.0

# rounddown(x, d=0) → luôn làm tròn XUỐNG
rounddown(3.99, 0)  # → 3.0
rounddown(3.99, 1)  # → 3.9

# ceil(x) / floor(x) → số nguyên
ceil(3.1)    # → 4
floor(3.9)   # → 3
```

**Ví dụ nghiệp vụ:**

```python
engine = FormulaEngine(formulas=[
    # Làm tròn lên đến 1000 đồng
    {"name": "GIA_BAN_TRON",
     "formula": "roundup(GIA_BAN / 1000, 0) * 1000"},
    # Số lượng cần mua (luôn làm tròn lên)
    {"name": "SO_LUONG_MUA",
     "formula": "roundup(TONG_NHUCAU / TONG_GOI, 0)"},
    # Thưởng làm tròn đến 100K
    {"name": "TIEN_THUONG_TRON",
     "formula": "round(TIEN_THUONG / 100000, 0) * 100000"},
])
```

### 4.2 sqrt, power, ln, log, log10, exp

```python
sqrt(9)          # → 3.0
sqrt(2)          # → 1.4142...
power(2, 10)     # → 1024.0
power(4, 0.5)    # → 2.0
ln(2.718)        # → ~1.0
log(100, 10)     # → 2.0
log10(1000)      # → 3.0
exp(1)           # → 2.718...

# Ví dụ: lãi suất kép liên tục P * e^(r*t)
{"name": "TIEN_LAI", "formula": "VON_GOC * exp(LAI_SUAT * THOI_GIAN)"}
```

### 4.3 safe_div — chia an toàn

```python
# safe_div(a, b, default=0.0) → float
safe_div(10, 2)        # → 5.0
safe_div(10, 0)        # → 0.0  (không raise)
safe_div(10, 0, -1)    # → -1.0 (custom default)
safe_div(0, 0, None)   # → None

# Ví dụ thực tế
{"name": "TY_LE_HT",   "formula": "safe_div(THUC_HIEN, KE_HOACH) * 100"},
{"name": "DON_GIA_TB", "formula": "safe_div(TONG_CP, SAN_LUONG, 0)"},
```

### 4.4 clamp, between, percent_of

```python
# clamp(x, lo, hi) → giới hạn x trong [lo, hi]
clamp(150, 0, 100)     # → 100
clamp(-5,  0, 100)     # → 0
clamp(50,  0, 100)     # → 50

# between(x, lo, hi) → bool: lo <= x <= hi
between(50,  0, 100)   # → True
between(150, 0, 100)   # → False
between(0,   0, 100)   # → True (đầu mút)

# percent_of(part, total, default=0.0) → float
percent_of(30, 200)       # → 15.0
percent_of(50, 0)         # → 0.0 (không raise)
percent_of(50, 0, -1.0)   # → -1.0 (custom default)

# Ví dụ tổng hợp — thưởng KPI
engine = FormulaEngine(formulas=[
    {"name": "TY_LE_KPI",    "formula": "percent_of(THUC_HIEN, KE_HOACH)"},
    {"name": "HE_SO_THUONG", "formula": "clamp(TY_LE_KPI / 100, 0.5, 2.0)"},
    {"name": "TIEN_THUONG",  "formula": "IF(between(TY_LE_KPI, 60, 999), LUONG_CB * HE_SO_THUONG, 0)"},
])
```

---

## §5. Hàm logic & điều kiện

### 5.1 IF, IIF, IFS, SWITCH

```python
# IF(condition, true_val, false_val)
IF(10 > 5, "Lớn", "Nhỏ")           # → "Lớn"
IF(LOAI = 'VIP', GIA * 0.9, GIA)

# Lồng IF
IF(DIEM >= 9, 'A',
   IF(DIEM >= 7, 'B',
      IF(DIEM >= 5, 'C', 'F')))

# IFS(c1, v1, c2, v2, ...) — cần fallback True ở cuối
IFS(DIEM >= 9, 'A',
    DIEM >= 7, 'B',
    DIEM >= 5, 'C',
    True,      'F')

# Thuế TNCN luỹ tiến với IFS
{"name": "THUE_TNCN", "formula": """
IFS(
    TNT <= 0,           0,
    TNT <= 5_000_000,   TNT * 5%,
    TNT <= 10_000_000,  TNT * 10% - 250_000,
    TNT <= 18_000_000,  TNT * 15% - 750_000,
    TNT <= 32_000_000,  TNT * 20% - 1_650_000,
    TNT <= 52_000_000,  TNT * 25% - 3_250_000,
    TNT <= 80_000_000,  TNT * 30% - 5_850_000,
    True,               TNT * 35% - 9_850_000
)"""}

# SWITCH(expr, val1, result1, ..., default)
SWITCH(LOAI, 'A', 10, 'B', 20, 'C', 30, 0)
{"name": "HE_SO_PC",
 "formula": "SWITCH(HANG_NV, 'A', 1.5, 'B', 1.2, 'C', 1.0, 0.8)"}
```

### 5.2 coalesce, is_blank, not_blank, isnumber, to_number

```python
# coalesce(*args) → giá trị đầu tiên không phải None và không rỗng ""
coalesce(None, "", 0, 5, 10)   # → 0  (0 không phải None/"")
coalesce(None, None, "hello")  # → "hello"
{"name": "GIA_AP_DUNG",
 "formula": "coalesce(GIA_OVERRIDE, GIA_STANDARD, GIA_MAC_DINH)"}

# is_blank(x) → True nếu x là None, "", 0, 0.0
is_blank(None)   # → True
is_blank("")     # → True
is_blank(0)      # → True
is_blank("a")    # → False

# not_blank(x) → ngược is_blank
not_blank(1)     # → True

# isnumber(x) → True nếu int/float
isnumber(5)       # → True
isnumber("3.14")  # → False (chuỗi)

# to_number(x, default=0.0) → float
to_number("1,234.5")   # → 1234.5
to_number("$100")      # → 100.0
to_number("100 VND")   # → 100.0
to_number(None)        # → 0.0
to_number("abc", -1)   # → -1.0
```

### 5.3 and*, or*, not\_

```python
# Dùng and_/or_/not_ vì 'and', 'or', 'not' là keyword Python
and_(A > 0, B > 0, C > 0)
or_(LOAI = 'A', LOAI = 'B', LOAI = 'C')
not_(IS_VOID)

{"name": "DUOC_CHIET_KHAU",
 "formula": "and_(KHACH_HANG = 'VIP', TONG_TIEN >= 10_000_000, not_(IS_OVERDUE))"}
```

---

## §6. Hàm tổng hợp

### 6.1 sum

```python
# sum(*args, key=None) → float

# Dạng 1: list số
sum([10, 20, 30])           # → 60
sum([1, None, 3, None, 5])  # → 9 (bỏ qua None)

# Dạng 2: nhiều tham số
sum(10, 20, 30)  # → 60
sum(A, B, C)

# Dạng 3: generator — phổ biến với list[dict]
rows = [
    {"sp": "A", "sl": 100, "gia": 50_000},
    {"sp": "B", "sl": 200, "gia": 30_000},
    {"sp": "C", "sl": 50,  "gia": 80_000},
]
sum(r["sl"] for r in rows)                        # → 350
sum(r["sl"] * r["gia"] for r in rows)             # → 15_000_000
sum(r["sl"] for r in rows if r["gia"] > 40_000)   # → 150

# Dạng 4: key parameter — shortcut cho list[dict]
sum(rows, key="sl")    # → 350
sum(rows, key="gia")   # → 160_000

# Dạng 5: dict values
sum({"a": 10, "b": 20, "c": 30})  # → 60

# Ví dụ thực tế
{"name": "TONG_DOANH_THU",
 "formula": "sum(r['sl'] * r['don_gia'] for r in chi_tiet)"},
{"name": "TONG_NVL",
 "formula": "sum(chi_phi_nvl)"},
```

### 6.2 min, max

```python
# min/max(*args, key=None) → Any

min(5, 3, 8, 1)    # → 1
max([5, 3, 8, 1])  # → 8

rows = [{"ma": "A", "gia": 50_000}, {"ma": "B", "gia": 30_000}, {"ma": "C", "gia": 80_000}]
min(rows, key="gia")   # → 30_000
max(rows, key="gia")   # → 80_000

max(r["gia"] for r in rows if r["gia"] > 40_000)  # → 80_000

# Thực tế
{"name": "GIA_THAP_NHAT", "formula": "min(lich_su_gia, key='gia')"},
{"name": "GIA_TOI_THIEU", "formula": "max(DON_GIA, GIA_SAN, 0)"},
```

### 6.3 average, count, counta, countnum

```python
average([10, 20, 30])                  # → 20.0
average([10, None, 30, None, 50])      # → 30.0 (bỏ None)
average(rows, key="gia")               # → 53_333.3

count([1, None, 3, None, 5])           # → 3 (bỏ None và "")
counta([1, None, 3])                   # → 2 (alias count)
countnum([1, "a", None, 2.5, True])    # → 3 (chỉ số)

# key parameter
count(rows, key="gia")  # → đếm phần tử có gia không None/""
```

---

## §7. Hàm tổng hợp có điều kiện

### 7.1 sumif

```python
# sumif(range_vals, criteria, sum_range=None, key=None) → float

# Bảng operators:
# ">100"  ">="  "<50"  "<="  "<>0"/"!=0"  "=X"  "*SP*"  None(is null)  100(số trực tiếp)

# Dạng 1: 2 list riêng — Excel-style
loai_list = ["A", "A", "B", "A", "B"]
gia_list  = [100, 200, 150, 300, 250]

sumif(loai_list, "A", sum_range=gia_list)   # → 600
sumif(gia_list, ">150")                      # → 750 (cộng chính list)

# Dạng 2: list[dict] với key=tuple(crit_field, sum_field)
rows = [
    {"phong": "IT", "luong": 20_000_000},
    {"phong": "IT", "luong": 15_000_000},
    {"phong": "KT", "luong": 18_000_000},
]
sumif(rows, "IT",  key=("phong", "luong"))  # → 35_000_000
sumif(rows, ">15000000", key="luong")       # → cộng luong > 15M

# Dạng 3: wildcard
sumif(loai_list, "*A*", sum_range=gia_list) # chứa "A"
```

### 7.2 sumifs

```python
# sumifs(sum_range, *criteria_pairs, key=None, **kwargs) → float

rows = [
    {"phong": "IT", "loai": "CT", "luong": 20_000_000},
    {"phong": "IT", "loai": "HĐ", "luong": 15_000_000},
    {"phong": "KT", "loai": "CT", "luong": 18_000_000},
]

# Dạng 1: kwargs (gọn nhất cho list[dict])
sumifs(rows, key="luong", phong="KT", loai="CT")  # → 18_000_000

# Dạng 2: positional pairs
sumifs(rows, "phong", "KT", "loai", "CT", key="luong")  # → 18_000_000

# Dạng 3: Excel-style (2 list riêng)
phong_list = ["IT", "IT", "KT"]
loai_list  = ["CT", "HĐ", "CT"]
luong_list = [20e6, 15e6, 18e6]
sumifs(luong_list, phong_list, "KT", loai_list, "CT")  # → 18_000_000
```

### 7.3 countif, countifs, averageif

```python
# countif
countif(["A", "B", "A", "C", "A"], "A")       # → 3
countif([10, 20, 5, 30, 15], ">10")            # → 3
countif(rows, "IT",  key="phong")              # → 2
countif(rows, ">80", key="kpi")

# countifs — nhiều điều kiện
countifs(rows, phong="IT", kpi=">80")          # kwargs style

# averageif
loai = ["A", "B", "A", "B"]
gia  = [100, 200, 300, 400]
averageif(loai, "A", average_range=gia)        # → 200.0
averageif(rows, "IT", key=("phong", "luong"))  # → TB lương phòng IT
```

---

## §8. Hàm mảng & collection

### 8.1 filter_array

```python
# filter_array(data, operator=None, threshold=None, key=None, value=None) → list

rows = [
    {"loai": "A", "gia": 100_000, "sl": 50},
    {"loai": "B", "gia": 200_000, "sl": 30},
    {"loai": "A", "gia": 150_000, "sl": 20},
]

# Chế độ 1: exact match
filter_array(rows, key="loai", value="A")            # → [row1, row3]

# Chế độ 2: so sánh số
filter_array(rows, ">", 100_000, key="gia")          # → [row2, row3]
filter_array(rows, ">=", 100_000, key="gia")         # → [row1, row2, row3]
filter_array(rows, "!=", "A", key="loai")            # → [row2]

# Chế độ 3: list số đơn giản
filter_array([10, 5, 20, 3, 15], ">", 10)            # → [20, 15]

# Phối hợp với sum
# Tổng tiền hàng loại A:
# sum(r["sl"] * r["gia"] for r in filter_array(rows, key="loai", value="A"))

{"name": "SO_HANG_LOI",
 "formula": "count(filter_array(SAN_PHAM, key='trang_thai', value='loi'))"},
{"name": "TONG_GIA_CAO",
 "formula": "sum(r['gia'] * r['sl'] for r in filter_array(SAN_PHAM, '>', 100_000, key='gia'))"},
```

### 8.2 sorted_array / sort

```python
# sorted_array(data, key=None, reverse=False) → list
# sort(...) — alias

sorted_array([3, 1, 4, 1, 5])                       # → [1, 1, 3, 4, 5]
sorted_array([3, 1, 4, 1, 5], reverse=True)          # → [5, 4, 3, 1, 1]

rows = [{"ma": "C", "gia": 300}, {"ma": "A", "gia": 100}]
sorted_array(rows, key="gia")               # tăng dần theo giá
sorted_array(rows, key="gia", reverse=True) # giảm dần
sorted_array(rows, key="ma")               # alpha

# ISO date sort tự động
lich_su = [{"ngay": "2025-03-15"}, {"ngay": "2025-01-01"}, {"ngay": "2025-06-20"}]
sorted_array(lich_su, key="ngay")  # sort đúng thứ tự ngày
```

### 8.3 group_sum, group_count, group_avg

```python
# group_sum(data, group_key, sum_key) → Dict[Any, float]
# group_count(data, group_key) → Dict[Any, int]
# group_avg(data, group_key, avg_key) → Dict[Any, float]

rows = [
    {"phong": "IT",  "luong": 20_000_000, "kpi": 90},
    {"phong": "IT",  "luong": 15_000_000, "kpi": 75},
    {"phong": "KT",  "luong": 18_000_000, "kpi": 85},
    {"phong": "HR",  "luong": 12_000_000, "kpi": 80},
]

group_sum(rows, "phong", "luong")
# → {"IT": 35_000_000, "KT": 18_000_000, "HR": 12_000_000}

group_count(rows, "phong")
# → {"IT": 2, "KT": 1, "HR": 1}

group_avg(rows, "phong", "kpi")
# → {"IT": 82.5, "KT": 85.0, "HR": 80.0}

# Ví dụ thực tế
{"name": "TONG_LUONG_THEO_PHONG",
 "formula": "group_sum(NHAN_VIEN, 'phong', 'luong')"},
{"name": "SO_NV_THEO_PHONG",
 "formula": "group_count(NHAN_VIEN, 'phong')"},
```

### 8.4 map_key, unique, count_unique, flatten, sum_dict

```python
# map_key(data, key) → list — lấy 1 field từ list[dict]
rows = [{"ma": "A", "gia": 100}, {"ma": "B", "gia": 200}]
map_key(rows, "ma")    # → ["A", "B"]
map_key(rows, "gia")   # → [100, 200]

# unique(data, key=None) → list (deterministic, sorted)
unique([3, 1, 4, 1, 5, 9, 2, 6, 5])    # → [1, 2, 3, 4, 5, 6, 9]
unique(rows, key="ma")                   # → ["A", "B"]

# count_unique(data, key=None) → int
count_unique([1, 2, 2, 3, 3, 3])        # → 3

# flatten(data) → list phẳng nhiều cấp
flatten([[1, 2], [3, [4, 5]], 6])        # → [1, 2, 3, 4, 5, 6]

# sum_dict(d) → float — tổng values trong dict
sum_dict({"A": 100, "B": 200, "C": 300}) # → 600.0
```

### 8.5 index, match, choose

```python
# index(array, row_num, col_num=0) — Excel-style 1-based
arr = [10, 20, 30, 40, 50]
index(arr, 1)         # → 10
index(arr, 3)         # → 30

matrix = [[1,2,3],[4,5,6],[7,8,9]]
index(matrix, 2, 3)   # → 6 (hàng 2, cột 3)
index(matrix, 2, 0)   # → [4,5,6] (cả hàng)

# match(lookup_value, lookup_array, match_type=1) → int (1-based)
# match_type=0: exact | 1: ≤ | -1: ≥
match("B", ["A","B","C","D"])           # → 2
match(15, [10,15,20,25], 0)             # → 2 (exact)
match(12, [10,15,20,25], 1)             # → 1 (≤12: lấy 10 ở pos 1)

# choose(index_num, *values) — 1-based
choose(1, "A", "B", "C")   # → "A"
choose(2, 10, 20, 30)      # → 20
```

---

## §9. ⭐ Hàm last — Phân tích & Hướng dẫn đầy đủ

### 9.1 Tổng quan & Nhận xét

Hàm `last()` là một trong những hàm **mạnh và linh hoạt nhất** của formula_utils. Nó không chỉ đơn thuần lấy phần tử cuối danh sách — mà là một **mini query engine** hỗ trợ:

- Sort đa chiều theo nhiều key
- Lấy N phần tử đầu/cuối
- Group by + aggregate trong 1 lần gọi
- Chỉ trả 1 field cụ thể (value_key)
- Giữ thứ tự gốc (preserve_order)
- Default khi không tìm thấy

**So sánh với SQL:**

```
last(rows, sort_by='ngay', value_key='gia')
≡ SELECT gia FROM rows ORDER BY ngay DESC LIMIT 1

last(rows, sort_by='ngay', group_by='ma_sp', value_key='gia')
≡ SELECT ma_sp, gia FROM rows ORDER BY ngay DESC GROUP BY ma_sp (FIRST)

last(rows, sort_by='gia', n=3)
≡ SELECT * FROM rows ORDER BY gia DESC LIMIT 3
```

### 9.2 Signature đầy đủ

```python
def last(
    data,                      # list | list[dict] — dữ liệu đầu vào
    sort_by = None,            # str | list[str] | None — field(s) để sort
    n        = 1,              # int — số phần tử cần lấy (1=scalar, >1=list)
    group_by = None,           # str | None — trả dict{group_val: result}
    reverse  = True,           # bool — True=lớn nhất trước, False=nhỏ nhất trước
    value_key= None,           # str | None — chỉ trả field này thay vì cả dict
    default  = None,           # Any — trả về khi không tìm thấy
    missing_value = None,      # Any — giá trị thay thế khi sort_key bị null
    error_on_missing_sort_key = False,  # bool — raise nếu sort key không tồn tại
    preserve_order = False,    # bool — giữ thứ tự gốc, không sort
) -> Any
```

**Aliases:**

- `first(...)` = `last(..., reverse=False)` — lấy giá trị **nhỏ nhất / cũ nhất**
- `latest(...)` = `last(..., reverse=True)` — lấy giá trị **lớn nhất / mới nhất**
- `earliest(...)` = `last(..., reverse=False)`
- `nth(data, n, ...)` — lấy phần tử thứ n

### 9.3 Các kiểu dữ liệu đầu vào

#### A. Plain list — số, chuỗi, ngày

```python
# ── List số ────────────────────────────────────────────────────────
nums = [3, 1, 4, 1, 5, 9, 2, 6]

last(nums)                         # → 9    (lớn nhất — reverse=True default)
first(nums)                        # → 1    (nhỏ nhất)
last(nums, n=3)                    # → [5, 6, 9]  (3 lớn nhất, sort giảm)
first(nums, n=3)                   # → [1, 1, 2]  (3 nhỏ nhất, sort tăng)

# preserve_order: không sort, lấy theo vị trí
last(nums, n=2, preserve_order=True)   # → [2, 6]  (2 phần tử CUỐI)
first(nums, n=2, preserve_order=True)  # → [3, 1]  (2 phần tử ĐẦU)

# ── List chuỗi ────────────────────────────────────────────────────
words = ["banana", "apple", "cherry", "date"]

last(words)          # → "date"    (alphabetically last — "d" > "c")
first(words)         # → "apple"   (alphabetically first)
last(words, n=2)     # → ["cherry", "date"]

# ── List ngày (ISO string — sort đúng) ───────────────────────────
dates = ["2025-03-15", "2025-01-01", "2025-12-31", "2025-06-20"]

last(dates)           # → "2025-12-31"   (mới nhất)
first(dates)          # → "2025-01-01"   (cũ nhất)
last(dates, n=2)      # → ["2025-06-20", "2025-12-31"]

# ── Default khi list rỗng ─────────────────────────────────────────
last([], default=0)        # → 0
last([], default="N/A")    # → "N/A"
last([], n=3, default=[])  # → []
```

#### B. List of dict — trường hợp phổ biến nhất

```python
lich_su = [
    {"ngay": "2025-01-01", "ma_sp": "A", "gia": 100_000, "so_luong": 50},
    {"ngay": "2025-03-15", "ma_sp": "A", "gia": 110_000, "so_luong": 30},
    {"ngay": "2025-02-10", "ma_sp": "B", "gia": 200_000, "so_luong": 20},
    {"ngay": "2025-04-01", "ma_sp": "B", "gia": 190_000, "so_luong": 40},
    {"ngay": "2025-05-20", "ma_sp": "A", "gia": 115_000, "so_luong": 60},
    {"ngay": "2025-05-22", "ma_sp": "B", "gia": 185_000, "so_luong": 25},
]

# ── Lấy cả dict ──────────────────────────────────────────────────
last(lich_su, sort_by="ngay")
# → {"ngay": "2025-05-22", "ma_sp": "B", "gia": 185_000, "so_luong": 25}

first(lich_su, sort_by="ngay")
# → {"ngay": "2025-01-01", "ma_sp": "A", "gia": 100_000, "so_luong": 50}

# ── value_key: chỉ lấy 1 field ───────────────────────────────────
last(lich_su, sort_by="ngay", value_key="gia")       # → 185_000
first(lich_su, sort_by="ngay", value_key="gia")      # → 100_000
last(lich_su, sort_by="gia", value_key="ma_sp")      # → "A" (gia cao nhất=115_000)

# ── n > 1: lấy nhiều phần tử ─────────────────────────────────────
last(lich_su, sort_by="ngay", n=3)
# → [row_Apr01, row_May20, row_May22]  (3 mới nhất, sort giảm → tăng trước khi slice)

last(lich_su, sort_by="gia", n=2, value_key="gia")
# → [115_000, 200_000]  (2 giá cao nhất: 200K và 115K, sort giảm)

# ── group_by: kết quả theo nhóm ──────────────────────────────────
last(lich_su, sort_by="ngay", group_by="ma_sp", value_key="gia")
# → {"A": 115_000, "B": 185_000}  (giá mới nhất của từng SP)

last(lich_su, sort_by="gia", group_by="ma_sp")
# → {"A": <dict May20 115K>, "B": <dict Feb10 200K>}  (gia cao nhất mỗi SP)

# ── sort_by nhiều key ────────────────────────────────────────────
last(lich_su, sort_by=["ma_sp", "ngay"])
# sort theo ma_sp trước, rồi ngày → lấy cái sort cao nhất
```

#### C. List of tuple

```python
# Tuple thường dùng trong dữ liệu đã zip hoặc từ DB cursor
giao_dich = [
    ("2025-01-10", "KH001", 500_000),
    ("2025-03-20", "KH001", 800_000),
    ("2025-02-15", "KH002", 300_000),
    ("2025-05-01", "KH002", 1_200_000),
    ("2025-04-10", "KH003", 600_000),
]

# Với tuple, sort_by nhận index (int) hoặc chuỗi "0", "1", "2"
# Hoặc wrap thành dict trước khi gọi
as_dicts = [{"ngay": t[0], "kh": t[1], "tien": t[2]} for t in giao_dich]

last(as_dicts, sort_by="ngay", value_key="tien")      # → 1_200_000
last(as_dicts, sort_by="ngay", group_by="kh", value_key="tien")
# → {"KH001": 800_000, "KH002": 1_200_000, "KH003": 600_000}
```

#### D. Dict of dict (nhóm có sẵn)

```python
# Dict {key: dict} — ít gặp nhưng hỗ trợ
ds_sp = {
    "SP_A": {"gia": 100_000, "ngay_cap_nhat": "2025-06-01"},
    "SP_B": {"gia": 200_000, "ngay_cap_nhat": "2025-05-15"},
    "SP_C": {"gia": 150_000, "ngay_cap_nhat": "2025-06-10"},
}
# last nhận values của dict
last(list(ds_sp.values()), sort_by="gia", value_key="gia")  # → 200_000
```

### 9.4 Các tham số đặc biệt

#### preserve_order

```python
history = [10, 50, 20, 80, 30, 60, 40]

# Mặc định (sort):
last(history, n=3)                        # → [60, 80, 50]  (3 giá trị lớn nhất)
first(history, n=3)                       # → [10, 20, 30]  (3 giá trị nhỏ nhất)

# preserve_order=True (theo vị trí gốc):
last(history, n=3, preserve_order=True)   # → [30, 60, 40]  (3 phần tử CUỐI list)
first(history, n=3, preserve_order=True)  # → [10, 50, 20]  (3 phần tử ĐẦU list)

# Ứng dụng: lấy N giao dịch gần nhất theo thứ tự đã được sort sẵn
sorted_rows = sorted_array(lich_su, key="ngay")
last(sorted_rows, n=5, preserve_order=True)  # 5 rows cuối = 5 mới nhất, giữ thứ tự
```

#### missing_value — xử lý null trong sort key

```python
rows_with_null = [
    {"ten": "An",   "ngay": "2025-03-01", "gia": 100},
    {"ten": "Bình", "ngay": None,         "gia": 200},   # ngày null
    {"ten": "Cường","ngay": "2025-01-01", "gia": 150},
    {"ten": "Dũng", "ngay": "2025-05-01", "gia": 180},
]

# Mặc định: None được coi là "nhỏ nhất" → nằm cuối khi reverse=True
last(rows_with_null, sort_by="ngay", value_key="ten")
# → "Dũng"  (2025-05-01)

# missing_value: đặt giá trị thay thế cho null
last(rows_with_null, sort_by="ngay", value_key="ten",
     missing_value="9999-99-99")
# → "Bình"  (None → "9999-99-99" → sort cao nhất)

last(rows_with_null, sort_by="ngay", value_key="ten",
     missing_value="0000-00-00")
# → "Dũng"  (None → "0000-00-00" → sort thấp nhất, Dũng vẫn win)
```

#### error_on_missing_sort_key

```python
rows_incomplete = [
    {"ten": "An", "gia": 100, "ngay": "2025-01"},
    {"ten": "Bình"},  # thiếu "gia" và "ngay"
]

# Mặc định: không raise, dùng None cho missing key
last(rows_incomplete, sort_by="ngay", value_key="ten")  # → "An"

# Strict mode: raise nếu sort key không tồn tại
try:
    last(rows_incomplete, sort_by="ngay", value_key="ten",
         error_on_missing_sort_key=True)
except FormulaError as e:
    print(e)  # "last: sort key 'ngay' not found in data"
```

### 9.5 Ví dụ nâng cao — kết hợp với FormulaEngine

```python
from formula_utils import FormulaEngine

engine = FormulaEngine(
    formulas=[
        # ── Giá mới nhất mỗi sản phẩm ─────────────────────────────
        {"name": "GIA_MOI_NHAT_THEO_SP",
         "formula": "last(LICH_SU_GIA, sort_by='ngay', group_by='ma_sp', value_key='gia')"},

        # ── Giá mới nhất toàn bộ ───────────────────────────────────
        {"name": "GIA_MOI_NHAT",
         "formula": "last(LICH_SU_GIA, sort_by='ngay', value_key='gia', default=0)"},

        # ── Top 3 doanh thu (dict đầy đủ) ──────────────────────────
        {"name": "TOP3_DON_HANG",
         "formula": "last(DON_HANG, sort_by='tong_tien', n=3)"},

        # ── Mã đơn hàng giá trị cao nhất ───────────────────────────
        {"name": "MA_DON_LON_NHAT",
         "formula": "last(DON_HANG, sort_by='tong_tien', value_key='ma_don', default='N/A')"},

        # ── Giá cũ nhất (để tính biến động) ─────────────────────────
        {"name": "GIA_CU_NHAT",
         "formula": "first(LICH_SU_GIA, sort_by='ngay', value_key='gia', default=0)"},

        # ── Biến động giá % ──────────────────────────────────────────
        {"name": "BIEN_DONG_GIA_PCT",
         "formula": "safe_div(GIA_MOI_NHAT - GIA_CU_NHAT, GIA_CU_NHAT) * 100"},

        # ── KPI nhân viên theo phòng (top performer) ─────────────────
        {"name": "TOP_KPI_THEO_PHONG",
         "formula": "last(NHAN_VIEN, sort_by='kpi', group_by='phong', value_key='ten')"},

        # ── 5 giao dịch gần nhất (giữ thứ tự) ───────────────────────
        {"name": "LAST_5_GD",
         "formula": "last(sorted_array(GIAO_DICH, key='ngay'), n=5, preserve_order=True)"},

        # ── Tổng 3 tháng gần nhất ────────────────────────────────────
        {"name": "TONG_3_THANG_GAN",
         "formula": "sum(r['doanh_thu'] for r in last(THANG_DATA, sort_by='thang', n=3))"},

        # ── nth: giá cao thứ 2 ───────────────────────────────────────
        {"name": "GIA_CAO_THU_2",
         "formula": "nth(LICH_SU_GIA, 2, sort_by='gia', value_key='gia', default=0)"},
    ],
    deterministic=True,
)

result = engine.calculate({
    "LICH_SU_GIA": [
        {"ngay": "2025-01-01", "ma_sp": "A", "gia": 100_000},
        {"ngay": "2025-03-15", "ma_sp": "A", "gia": 110_000},
        {"ngay": "2025-02-10", "ma_sp": "B", "gia": 200_000},
        {"ngay": "2025-05-20", "ma_sp": "A", "gia": 115_000},
        {"ngay": "2025-04-01", "ma_sp": "B", "gia": 185_000},
    ],
    "DON_HANG": [
        {"ma_don": "DH001", "tong_tien": 5_000_000},
        {"ma_don": "DH002", "tong_tien": 12_000_000},
        {"ma_don": "DH003", "tong_tien": 8_000_000},
        {"ma_don": "DH004", "tong_tien": 15_000_000},
    ],
    "NHAN_VIEN": [
        {"ten": "An",    "phong": "IT", "kpi": 90},
        {"ten": "Bình",  "phong": "IT", "kpi": 95},
        {"ten": "Cường", "phong": "KT", "kpi": 88},
        {"ten": "Dũng",  "phong": "KT", "kpi": 82},
    ],
    "GIAO_DICH": [
        {"ngay": "2025-01-10", "tien": 100},
        {"ngay": "2025-02-15", "tien": 200},
        {"ngay": "2025-03-20", "tien": 300},
        {"ngay": "2025-04-01", "tien": 400},
        {"ngay": "2025-05-05", "tien": 500},
        {"ngay": "2025-06-10", "tien": 600},
        {"ngay": "2025-07-15", "tien": 700},
    ],
    "THANG_DATA": [
        {"thang": "2025-01", "doanh_thu": 100_000_000},
        {"thang": "2025-02", "doanh_thu": 120_000_000},
        {"thang": "2025-03", "doanh_thu": 130_000_000},
        {"thang": "2025-04", "doanh_thu": 110_000_000},
        {"thang": "2025-05", "doanh_thu": 150_000_000},
    ],
})

print(result["GIA_MOI_NHAT_THEO_SP"])  # {"A": 115_000, "B": 185_000}
print(result["GIA_MOI_NHAT"])          # 185_000
print(result["MA_DON_LON_NHAT"])       # "DH004"
print(result["TOP_KPI_THEO_PHONG"])    # {"IT": "Bình", "KT": "Cường"}
print(result["TONG_3_THANG_GAN"])      # 390_000_000 (Mar+Apr+May)
print(result["GIA_CAO_THU_2"])         # 185_000
```

### 9.6 Bảng tóm tắt các pattern

| Pattern            | Code                                                           | Kết quả         |
| ------------------ | -------------------------------------------------------------- | --------------- |
| Giá trị lớn nhất   | `last(nums)`                                                   | scalar          |
| Giá trị nhỏ nhất   | `first(nums)`                                                  | scalar          |
| N lớn nhất         | `last(nums, n=3)`                                              | list[3]         |
| N phần tử cuối     | `last(nums, n=3, preserve_order=True)`                         | list[3]         |
| Dict mới nhất      | `last(rows, sort_by='ngay')`                                   | dict            |
| Field mới nhất     | `last(rows, sort_by='ngay', value_key='gia')`                  | scalar          |
| Mới nhất theo nhóm | `last(rows, sort_by='ngay', group_by='loai', value_key='gia')` | dict{loai: gia} |
| Top N              | `last(rows, sort_by='score', n=3, value_key='ten')`            | list[3]         |
| Phần tử thứ N      | `nth(rows, 2, sort_by='score', value_key='ten')`               | scalar          |
| Cũ nhất            | `first(rows, sort_by='ngay', value_key='gia')`                 | scalar          |

---

## §10. Hàm lookup

### 10.1 vlookup

```python
# vlookup(key, table, col=1, default=0) → Any
# col: 0=key, 1=cột đầu sau key, 2=cột thứ 2, ...

# Dạng 1: list of lists
bang_gia = [
    ["SP_A", "Sản phẩm A", 100_000, "VND"],
    ["SP_B", "Sản phẩm B", 150_000, "VND"],
    ["SP_C", "Sản phẩm C", 200_000, "USD"],
]
vlookup("SP_B", bang_gia, 1)    # → "Sản phẩm B"
vlookup("SP_B", bang_gia, 2)    # → 150_000
vlookup("SP_X", bang_gia, 2, -1) # → -1 (không tìm thấy)

# Dạng 2: dict {key: value}
gia_dict = {"SP_A": 100_000, "SP_B": 150_000}
vlookup("SP_B", gia_dict)        # → 150_000

# Dạng 3: dict {key: list}
gia_dict2 = {"SP_B": ["Sản phẩm B", 150_000, "VND"]}
vlookup("SP_B", gia_dict2, 2)    # → 150_000

# Ví dụ thực tế
{"name": "TEN_SP",   "formula": "vlookup(MA_SP, BANG_SAN_PHAM, 1, 'Không rõ')"},
{"name": "GIA_NHAP", "formula": "vlookup(MA_NVL, BANG_GIA_NVL, 2, 0)"},
{"name": "TY_GIA",   "formula": "vlookup(MA_NT, BANG_TY_GIA, 1, 1.0)"},
```

### 10.2 xlookup

```python
# xlookup(lookup_value, lookup_array, return_array, if_not_found=0) → Any

ma_hang  = ["H001", "H002", "H003", "H004"]
gia_nhap = [50_000, 75_000, 60_000, 80_000]
ten_hang = ["Hàng A", "Hàng B", "Hàng C", "Hàng D"]

xlookup("H002", ma_hang, gia_nhap, 0)    # → 75_000
xlookup("H002", ma_hang, ten_hang, "?")  # → "Hàng B"
xlookup("H999", ma_hang, gia_nhap, -1)   # → -1

# dict mode
bang = {"H001": 50_000, "H002": 75_000}
xlookup("H002", bang, {}, 0)             # → 75_000

{"name": "GIA_NVL", "formula": "xlookup(MA_NVL, DS_MA, DS_GIA, 0)"},
```

---

## §11. Hàm chuỗi

### 11.1 concat, text_join, textjoin

```python
concat("HD-", 2025, "-", 1)            # → "HD-2025-1"
concat("SO/", None, "/2025")            # → "SO//2025" (None bỏ qua)

text_join("/", 2025, 7, 15)             # → "2025/7/15"
text_join("-", "HD", NAM, STT)

textjoin(", ", True,  "An", None, "Bình", "")   # → "An, Bình" (bỏ empty)
textjoin(", ", False, "An", None, "Bình", "")   # → "An, , Bình, "

{"name": "DIA_CHI", "formula": "textjoin(', ', True, SO_NHA, DUONG, QUAN, TINH)"},
```

### 11.2 left, right, mid, len

```python
left("HD-2025-001", 2)     # → "HD"
right("HD-2025-001", 3)    # → "001"
mid("HD-2025-001", 4, 4)   # → "2025" (từ vị trí 4, lấy 4 ký tự)
len("Hello")               # → 5

# Ví dụ
{"name": "LOAI_CT",  "formula": "left(MA_CHUNG_TU, 2)"},    # "HD", "PO"...
{"name": "NAM_HD",   "formula": "int(mid(MA_HD, 4, 4))"},   # → 2025
{"name": "SO_THU_TU","formula": "right(MA_HD, 3)"},         # → "001"
```

### 11.3 upper, lower, trim, replace, substitute, find

```python
upper("hello")                         # → "HELLO"
lower("ABCDE")                         # → "abcde"
trim("  hello  ")                      # → "hello"
replace("a-b-c", "-", "/")             # → "a/b/c"
substitute("a-b-a-c", "a", "X")        # → "X-b-X-c" (tất cả)
substitute("a-b-a-c", "a", "X", 1)     # → "X-b-a-c" (chỉ lần 1)
substitute("a-b-a-c", "a", "X", 2)     # → "a-b-X-c" (chỉ lần 2)
find("2025", "HD-2025-001")            # → 4 (1-based)
find("X",    "HD-2025-001")            # → 0 (không tìm thấy)

{"name": "MA_CHUAN",   "formula": "upper(trim(MA_NHAP))"},
{"name": "URL_SP",     "formula": "replace(lower(TEN_SP), ' ', '-')"},
```

---

## §12. Hàm ngày tháng

### 12.1 year, month, day, quarter

```python
# Nhận: date, datetime, ISO string "YYYY-MM-DD", "DD/MM/YYYY"
year("2025-07-15")     # → 2025
month("2025-07-15")    # → 7
day("2025-07-15")      # → 15
quarter("2025-07-15")  # → 3  (Q3: tháng 7, 8, 9)
quarter("2025-01-01")  # → 1

{"name": "QUY_HD",     "formula": "quarter(NGAY_HD)"},
{"name": "DT_NAM_NAY", "formula": "sum(r['dt'] for r in DON_HANG if year(r['ngay']) = NAM)"},
```

### 12.2 date_diff

```python
# date_diff(date1, date2, unit='days') → int | float
# unit: 'days' | 'months' | 'years' | 'hours' | 'seconds'
# Kết quả: date1 - date2

date_diff("2025-12-31", "2025-01-01", "days")    # → 364
date_diff("2025-12-31", "2025-01-01", "months")  # → 11
date_diff("2025-12-31", "2024-01-01", "years")   # → 1
date_diff("2025-01-01", "2025-12-31", "days")    # → -364 (âm)

{"name": "TUOI_NO",      "formula": "date_diff(NGAY_HOM_NAY, NGAY_HD, 'days')"},
{"name": "SO_THANG_HD",  "formula": "date_diff(NGAY_KT, NGAY_BD, 'months')"},
{"name": "QUA_HAN",      "formula": "date_diff(NGAY_HOM_NAY, NGAY_HEN_TRA, 'days') > 0"},
```

### 12.3 date_add

```python
# date_add(dt, days=0, months=0, years=0) → date
# Xử lý đúng cuối tháng (31/1 + 1 tháng = 28/2)

date_add("2025-01-15", days=10)       # → date(2025, 1, 25)
date_add("2025-01-15", months=1)      # → date(2025, 2, 15)
date_add("2025-01-31", months=1)      # → date(2025, 2, 28)  (cuối tháng)
date_add("2025-01-15", years=1)       # → date(2026, 1, 15)
date_add("2025-01-15", days=5, months=2, years=1)

{"name": "NGAY_HEN_TRA",    "formula": "date_add(NGAY_GIAO, days=30)"},
{"name": "NGAY_HET_BH",     "formula": "date_add(NGAY_MUA, years=1)"},
{"name": "NGAY_TIEP_THEO",  "formula": "date_add(NGAY_HD, months=THOI_HAN)"},
```

### 12.4 date_format, workdays

```python
date_format("2025-07-15")              # → "15/07/2025" (mặc định)
date_format("2025-07-15", "%Y-%m")     # → "2025-07"
date_format("2025-07-15", "%d %b %Y")  # → "15 Jul 2025"

workdays("2025-01-01", "2025-01-31")   # → 23 (bỏ T7, CN)

{"name": "THANG_NAM", "formula": "date_format(NGAY_HD, '%m/%Y')"},
{"name": "NGAY_LV",   "formula": "workdays(NGAY_DAU_THANG, NGAY_CUOI_THANG)"},
```

---

## §13. Hàm tiện ích

### 13.1 now, today (chỉ khi deterministic=False)

```python
engine_rt = FormulaEngine(formulas=[...], deterministic=False)
{"name": "NGAY_TINH",  "formula": "today()"},   # date hôm nay
{"name": "GIO_CAP_NHAT", "formula": "now()"},   # datetime UTC
{"name": "TUOI_TS",    "formula": "date_diff(today(), NGAY_MUA, 'years')"},
```

### 13.2 Type conversion

```python
str(12345)     # → "12345"
int(3.7)       # → 3
float("3.14")  # → 3.14
bool(0)        # → False
safe_str(None) # → ""  (thay vì "None")

{"name": "MA_DON", "formula": "concat('DH-', str(year(NGAY)), '-', str(STT))"},
```

---

## §14. calculate() và các biến thể

### 14.1 calculate() — cơ bản

```python
result = engine.calculate({
    "NVL":       5_000_000,
    "NC":        2_000_000,
    "CPC":       1_000_000,
    "SAN_LUONG": 100,
    # BIEN_LAI không cần → dùng default=0.15
})
# Chỉ trả formula outputs (không trả inputs)
print(result["GIA_BAN"])    # 92_000
print(result["TONG_TIEN"])  # 92_000
```

### 14.2 calculate_safe() — không bao giờ raise

```python
result = engine.calculate_safe({"NVL": 5e6, "NC": 2e6, "CPC": 1e6, "SAN_LUONG": 0})
# SAN_LUONG=0 → DON_GIA / 0 → lỗi

print(result["_ok"])         # False
print(result["_error"])      # "Evaluation failed for 'DON_GIA'..."
print(result["_error_type"]) # "runtime_error"
print(result["DON_GIA"])     # 0  (default_value)
```

### 14.3 calculate_batch()

```python
rows = [
    {"NVL": 5e6, "NC": 2e6, "CPC": 1e6, "SAN_LUONG": 100},
    {"NVL": 6e6, "NC": 2.5e6, "CPC": 1.2e6, "SAN_LUONG": 120},
]
results = engine.calculate_batch(rows)
tong_gia_ban = sum(r["GIA_BAN"] for r in results)
```

### 14.4 calculate_batch_with_memory() — carry-forward

```python
# Mỗi row nhận thêm prev_<key> từ row trước — cho sổ kế toán, tồn kho
engine_so = FormulaEngine(formulas=[
    {"name": "TON_KHO_CUOI",  "formula": "prev_TON_KHO_CUOI + NHAP - XUAT"},
    {"name": "LUY_KE_NHAP",   "formula": "prev_LUY_KE_NHAP + NHAP"},
])

results = engine_so.calculate_batch_with_memory(
    rows           = [{"NHAP": 100, "XUAT": 30}, {"NHAP": 50, "XUAT": 80}],
    memory_keys    = ["TON_KHO_CUOI", "LUY_KE_NHAP"],
    initial_memory = {"TON_KHO_CUOI": 500, "LUY_KE_NHAP": 0},
)
# results[0]["TON_KHO_CUOI"] → 570  (500+100-30)
# results[1]["TON_KHO_CUOI"] → 540  (570+50-80)
```

### 14.5 Cache bytecode

```python
# Lưu — bỏ qua parse/compile khi restore (~10x nhanh hơn)
cache_data = engine.to_cache_dict()   # dict với compiled bytecodes

# Restore
engine2 = FormulaEngine.from_cache_dict(cache_data)
engine2 = FormulaEngine.from_cache_dict(cache_data,
    max_operations=100_000, on_error="null")

# Redis/Frappe
import json
frappe.cache().set_value("eng_v1", json.dumps(cache_data), 300)
engine3 = FormulaEngine.from_cache_dict(json.loads(frappe.cache().get_value("eng_v1")))
```

---

## §15. IncrementalContext

Chỉ eval công thức bị ảnh hưởng khi user sửa input — tiết kiệm 40-90% CPU.

```python
# Bước 1: tạo context (full calc lần đầu)
ctx = engine.create_context(
    initial_inputs = {"NVL": 5_000_000, "NC": 2_000_000,
                      "CPC": 1_000_000, "SAN_LUONG": 100},
    doc_id = "BG-2025-001",
)
print(ctx.outputs["DON_GIA"])   # 80_000
print(ctx.initialized)           # True

# Bước 2: sửa 1 field — chỉ recalc chain bị ảnh hưởng
outputs, stats = engine.calculate_incremental(
    ictx           = ctx,
    changed_inputs = {"NVL": 6_000_000},
    return_stats   = True,
)
print(outputs["DON_GIA"])          # 90_000
print(stats.recalculated_nodes)    # 3 (chỉ nodes phụ thuộc NVL)
print(stats.skip_ratio)            # 0.4 = 40% tiết kiệm
print(stats.elapsed_ms)            # < 1ms

# Bước 3: serialize → Redis
import json
frappe.cache().set_value(f"ctx_{doc}", json.dumps(ctx.to_dict()), 600)

# Bước 4: restore
raw = json.loads(frappe.cache().get_value(f"ctx_{doc}"))
ctx2 = IncrementalContext.from_dict(engine, raw)
# Tự kiểm tra engine_hash → raise STALE_CONTEXT nếu thay đổi

# Biết trước nodes bị ảnh hưởng
affected = engine.get_affected_nodes({"NVL", "NC"})
# → {"TONG_CP", "DON_GIA", "GIA_BAN", "THUE_VAT", "TONG_TIEN"}
```

---

## §16. Explain API

```python
expl = engine.explain("GIA_BAN", inputs={
    "NVL": 5_000_000, "NC": 2_000_000,
    "CPC": 1_000_000, "SAN_LUONG": 100
})

print(expl.field)        # "GIA_BAN"
print(expl.value)        # 92_000
print(expl.inputs_used)  # {"NVL": 5e6, "NC": 2e6, ...}

# Text dạng cây
print(expl.to_text())
# Giải thích: GIA_BAN = 92000
#
# Inputs sử dụng:
#   BIEN_LAI = 0.15   NVL = 5000000 ...
#
# Chuỗi tính toán:
#   TONG_CP = NVL + NC + CPC → 8000000
#     DON_GIA = TONG_CP / SAN_LUONG → 80000
#       GIA_BAN = DON_GIA * (1 + BIEN_LAI) → 92000

for step in expl.steps:
    print(f"depth={step.depth}  {step.name} = {step.formula} → {step.value}")

# JSON
data = expl.to_dict()

# Tất cả fields
all_expls = engine.explain_all(inputs)
```

---

## §17. Multi-Scenario & Diff

```python
# calculate_scenarios
results = engine.calculate_scenarios({
    "Gốc":    {"NVL": 5e6, "NC": 2e6, "CPC": 1e6, "SAN_LUONG": 100},
    "NVL+10%":{"NVL": 5.5e6, "NC": 2e6, "CPC": 1e6, "SAN_LUONG": 100},
    "SL+20%": {"NVL": 5e6, "NC": 2e6, "CPC": 1e6, "SAN_LUONG": 120},
})

# compare_scenarios — tính + so sánh + delta
cmp = engine.compare_scenarios(
    scenarios     = results,
    fields        = ["DON_GIA", "GIA_BAN", "TONG_TIEN"],
    base_scenario = "Gốc",
)
print(cmp.to_table())
# Field             Gốc             NVL+10%
# --------------------------------------------------
# DON_GIA           80,000          85,000
# ...
# Delta so với 'Gốc':
# GIA_BAN                           +5,750.00 (+6.25%)

print(cmp.delta["GIA_BAN"]["NVL+10%"]["pct"])   # 6.25

# diff_inputs — tìm thay đổi
changed = engine.diff_inputs(old_inputs, new_inputs)
# → {"NVL", "BIEN_LAI"}  (set tên fields thay đổi)

changed_detail = engine.diff_inputs_values(old_inputs, new_inputs)
# → {"NVL": (5_000_000, 6_000_000), "BIEN_LAI": (0.15, 0.20)}

# validate_inputs
issues = engine.validate_inputs({"NVL": "abc", "SAN_LUONG": -100})
for issue in issues:
    print(f"[{issue.severity}] {issue.field}: {issue.issue}")
```

---

## §18. FormulaValidator

```python
from formula_utils import FormulaValidator

validator = FormulaValidator(allowed_functions=list(BASE_FUNCS.keys()))

vr = validator.validate(
    formula     = "NVL + NC * TY_LE",
    known_names = {"NVL", "NC", "TY_LE"},
)
print(vr.ok)          # True
print(vr.normalized)  # công thức đã chuẩn hóa
print(vr.errors)      # []
bool(vr)              # True

vr.raise_if_invalid("ten_field")

# 4 lớp kiểm tra:
# 1. Syntax — cú pháp Python
# 2. Security — AST node bị cấm, tên nguy hiểm
# 2b. GeneratorExp — generator standalone bị cấm
# 3. Function whitelist — hàm có được phép
# 4. Variable whitelist — biến có khai báo (optional)

# Batch
results = validator.validate_batch(
    formulas    = {"F1": "A + B", "F2": "F1 * C", "F3": "unknown_fn(A)"},
    known_names = {"A", "B", "C"},
)
for name, r in results.items():
    if not r.ok:
        print(f"{name}: {r.errors}")
# F3: ["Hàm 'unknown_fn' không được hỗ trợ."]

# Qua engine
vr = engine.validate_formula("NVL * 1.1")
all_vr = engine.validate_all()
```

---

## §19. Snapshot & Audit

### 19.1 snapshot_with_trace() — chốt số với trace đầy đủ

```python
from formula_utils import SnapshotTag, SnapshotStatus

outputs, snap = engine.snapshot_with_trace(
    inputs          = raw_inputs,
    business_inputs = {"so_bao_gia": "BG-2025-001", "khach_hang": "Cty ABC"},
    tag             = SnapshotTag.ESTIMATE,
    status          = SnapshotStatus.DRAFT,
    created_by      = "user@company.com",
    source_doc      = "BG-2025-001",
    notes           = "Báo giá lần 1",
    previous_values = None,    # dict output cũ để trace delta
    dirty_nodes     = None,    # None = full calc
    calc_mode       = "full",
)

# Lưu
doc.snap_json = snap.to_json(indent=2)
doc.snap_id   = snap.snapshot_id
```

### 19.2 Kiểm tra toàn vẹn & đọc thông tin

```python
print(snap.verify())                     # True = OK, False = bị can thiệp
print(snap.payload_hash)                 # SHA-256(meta+dag+inputs+outputs)
print(snap.snapshot_id)                  # UUID
print(snap.created_at)                   # UTC ISO
print(snap.outputs["DON_GIA"])           # 80_000
print(snap.meta.engine_version)          # "29.1.0"
print(snap.meta.formula_hash)            # SHA-256 lúc chốt
print(snap.audit_trail.tag)              # "estimate"
print(snap.audit_trail.created_by)       # "user@company.com"

# Execution trace
for e in snap.exec_trace.entries:
    if not e.skipped:
        print(f"{e.field}: {e.old_value} → {e.new_value}")

# Forensic report
print(snap.to_audit_report())
```

### 19.3 Revision & So sánh

```python
snap2 = engine.snapshot_revise(
    previous_snapshot = snap,
    inputs            = new_inputs,
    outputs           = engine.calculate(new_inputs),
    tag               = SnapshotTag.ACTUAL,
    status            = SnapshotStatus.APPROVED,
    created_by        = "manager@company.com",
    notes             = "Cập nhật giá NVL thực tế",
)

diff = engine.compare_snapshots(snap, snap2)
print(diff["inputs_changed"])
# {"NVL": {"before": 5e6, "after": 5.5e6}}
print(diff["outputs_changed"]["GIA_BAN"])
# {"before": 92_000, "after": 97_750, "delta": 5_750, "delta_pct": 6.25}
```

### 19.4 SnapshotTag & SnapshotStatus

```python
SnapshotTag.ESTIMATE   # báo giá / ước tính
SnapshotTag.PLAN       # kế hoạch
SnapshotTag.ACTUAL     # thực tế
SnapshotTag.VARIANCE   # phân tích chênh lệch
SnapshotTag.VOID       # đã hủy

SnapshotStatus.DRAFT     # đang tạo
SnapshotStatus.LOCKED    # đã khóa
SnapshotStatus.APPROVED  # đã duyệt
SnapshotStatus.REJECTED  # bị từ chối
SnapshotStatus.ARCHIVED  # lưu trữ
```

---

## §20. TimeBucket

### 20.1 generate_time_buckets

```python
buckets = generate_time_buckets(
    year         = 2025,
    types        = ["year", "half", "quarter", "month", "week"],
    week_start   = "monday",   # "monday" | "sunday"
    label_format = "short",    # xem bảng format
    full_format  = "{type_full} {index} {year}",
)

# Cấu trúc:
buckets["year"]      # TimeBucket
buckets["halves"]    # List[TimeBucket] — 2 phần tử
buckets["quarters"]  # List[TimeBucket] — 4 phần tử
buckets["months"]    # List[TimeBucket] — 12 phần tử
buckets["weeks"]     # List[TimeBucket] — 52-53 phần tử

for q in buckets["quarters"]:
    print(f"{q.label}  {q.from_date} → {q.to_date}")
# Q1  2025-01-01 → 2025-03-31
# Q2  2025-04-01 → 2025-06-30
```

### 20.2 Label format tokens

| Token          | Ví dụ      |
| -------------- | ---------- |
| `{year}`       | 2025       |
| `{year2}`      | 25         |
| `{index}`      | 3          |
| `{index02}`    | 03         |
| `{type_short}` | Q          |
| `{type_full}`  | Quarter    |
| `{from_date}`  | 2025-07-01 |
| `{to_date}`    | 2025-09-30 |

**Preset TB_FORMAT:**

| Preset         | Kết quả                 |
| -------------- | ----------------------- |
| `"short"`      | Q3                      |
| `"short_year"` | Q3-2025                 |
| `"full"`       | Quarter 3 2025          |
| `"padded"`     | Q03                     |
| `"date_range"` | 2025-07-01 → 2025-09-30 |

### 20.3 TimeBucket properties & navigation

```python
q3 = get_period("quarter", 3, 2025)

q3.name        # "Q3"
q3.label       # "Q3"
q3.full_label  # "Quarter 3 2025"
q3.type        # "quarter"
q3.index       # 3
q3.year        # 2025
q3.from_date   # "2025-07-01"
q3.to_date     # "2025-09-30"
q3.prev_name   # "Q2"
q3.next_name   # "Q4"
q3.prev_period # → TimeBucket Q2/2025 (lazy)
q3.next_period # → TimeBucket Q4/2025 (lazy)

"2025-08-15" in q3   # True
"2025-11-01" in q3   # False

# Serialization
q3.to_dict()    # đầy đủ
q3.to_ui()      # {value, label, short_label, full_label, from_date, to_date}
q3.to_filter()  # {period, from_date, to_date} — cho DB query
q3.to_entry()   # {period, period_label, from_date, to_date, year, index}
```

### 20.4 Tìm kiếm & điều hướng

```python
# Tìm kỳ chứa ngày
q = get_period_by_date("2025-08-15", "quarter")    # → Q3/2025
m = get_period_by_date("2025-08-15", "month")      # → M8/2025

# Dịch kỳ ±n
q2      = get_period_offset(q3, -1)    # → Q2/2025
q1_2026 = get_period_offset(q3, +2)   # → Q1/2026

# Cùng kỳ năm trước
q3_2024 = same_period_last_year(q3)              # → Q3/2024
q3_2023 = same_period_last_year(q3, years_back=2)

# Flat list
flat = generate_time_buckets_flat(2025, ["quarter", "month"], as_ui=True)
# → [{value, label, from_date, to_date}, ...]

# year_buckets shortcut
this_year = year_buckets()
last_year = year_buckets(offset=-1)
```

---

## §21. Allocation Engine

### 21.1 allocate() — API chính

```python
result = allocate(
    sources = [
        {"id": "CPC_A", "amount": 50_000_000},
        {"id": "CPC_B", "amount": 30_000_000},
    ],
    targets = [
        {"id": "SP_X", "qty": 500, "amount": 150e6, "alloc_pct": 50,
         "alloc_amount": 20e6, "manual_pct": 45},
        {"id": "SP_Y", "qty": 300, "amount": 80e6,  "alloc_pct": 30,
         "alloc_amount": 15e6, "manual_pct": 35},
        {"id": "SP_Z", "qty": 200, "amount": 40e6,  "alloc_pct": 20,
         "manual_pct": 20},
    ],
    method = "qty",    # phương pháp phân bổ (xem bảng bên dưới)
    rounding_policy       = "last",   # "last" | "largest" | "none"
    round_digits          = 2,
    mixed_residual_method = "qty",
)
```

### 21.2 Bảng 8 phương pháp

| method            | Phân bổ theo          | Field cần có               |
| ----------------- | --------------------- | -------------------------- |
| `"equal"`         | Chia đều              | (không cần)                |
| `"qty"`           | Tỷ lệ số lượng        | `target_qty_key`           |
| `"amount"`        | Tỷ lệ doanh thu       | `target_amount_key`        |
| `"weight"`        | Trọng số tùy chọn     | `target_weight_key`        |
| `"pct"`           | % cố định (tổng ≈100) | `target_pct_key`           |
| `"manual_amount"` | Số tiền cố định       | `target_manual_amount_key` |
| `"manual_pct"`    | % nhập tay            | `target_manual_pct_key`    |
| `"mixed"`         | Pass1→Pass2→Pass3     | tùy pass                   |

**Mixed logic:** manual_amount (Pass1) → manual_pct trên phần còn lại (Pass2) → residual method (Pass3)

### 21.3 AllocationResult & 3 output modes

```python
# Mode 1: to_result() — đầy đủ (default)
result = ae.to_result()
result.ok             # True/False
result.lines          # List[AllocationLine]
result.source_totals  # {"CPC_A": 50e6, ...}
result.target_totals  # {"SP_X": ..., ...}
result.unallocated    # {} nếu phân bổ đủ
result.summary()      # text overview

# Duyệt từng dòng
for line in result.lines:
    print(f"{line.source_id} → {line.target_id}: "
          f"{line.allocated:,.0f} ({line.ratio:.1%}) [{line.method}]")

# Ghi vào rows
result.apply_to(rows, id_key="ma_sp", out_key="chi_phi_pb")
ln_map = result.to_line_map()   # {target_id: AllocationLine}

# Mode 2: to_inplace() — ghi thẳng vào target dict, nhanh nhất
src, tgt, warns = ae.to_inplace(out_key="allocated", reset_before=True)

# Mode 3: to_lines() — pipeline nhẹ
lines, src, tgt, warns = ae.to_lines()
# lines: [(src_id, src_amt, tgt_id, allocated, ratio, method, weight), ...]

# Alias functions
result = allocate(sources, targets, "qty")
src, tgt, w = allocate_inplace(sources, targets, "allocated")
lines, src, tgt, w = allocate_fast(sources, targets, "equal")
```

---

## §22. TopoSort

```python
from formula_utils import topo_sort, topo_sort_with_info, TopoSorter

tasks = [
    {"id": "D", "deps": ["B", "C"]},
    {"id": "C", "deps": ["A"]},
    {"id": "B", "deps": ["A"]},
    {"id": "A", "deps": []},
]

sorted_items = topo_sort(
    items   = tasks,
    id_fn   = lambda x: x["id"],
    deps_fn = lambda x: x["deps"],
)
# → [task_A, task_B, task_C, task_D]

info = topo_sort_with_info(tasks, lambda x: x["id"], lambda x: x["deps"])
info.has_cycle    # False
info.levels       # {"A":0, "B":1, "C":1, "D":2}
info.edges        # {"A":[], "B":["A"], "C":["A"], "D":["B","C"]}
print(info.summary())

# Data shortcut
from formula_utils import topo_sort_data, topo_sort_flat

sorted_wo = topo_sort_data(
    items         = work_orders,
    id_key        = "name",
    deps_list_key = "required_items",
    dep_id_key    = "item_code",
)

sorted_nodes = topo_sort_flat(
    items       = nodes,
    id_key      = "id",
    dep_ids_key = "dep_ids",
)
```

---

## §23. SCC TopoSort

Sort đồ thị **có chu kỳ** — Tarjan SCC + condensation order.

```python
from formula_utils import scc_topo_sort, scc_topo_sort_with_info

# A→B→C→A (cycle), D phụ thuộc A
items = [
    {"id": "A", "deps": ["C"]},
    {"id": "B", "deps": ["A"]},
    {"id": "C", "deps": ["B"]},
    {"id": "D", "deps": ["A"]},
]

sorted_items = scc_topo_sort(items, lambda x: x["id"], lambda x: x["deps"])
# → [A, B, C, D]  (cycle trước, D sau)

info = scc_topo_sort_with_info(items, lambda x: x["id"], lambda x: x["deps"])
info.has_cycle     # True
info.cycle_groups  # [["A","B","C"]]
info.levels        # {"A":-1, "B":-1, "C":-1, "D":1}  (-1=cycle)
print(info.summary())
```

---

## §24. SccLinearSolver

Giải hệ `x_i = b_i + Σ_j A_ij × x_j` ↔ `(I-A)x = b` trên đồ thị có cycle.

**Ứng dụng:** Chi phí reciprocal, BOM cycle, Leontief I-O, PageRank.

```python
from formula_utils import solve_linear_on_graph

departments = [
    {"id": "A", "direct": 500_000, "receives": [{"from": "B", "pct": 0.05}]},
    {"id": "B", "direct": 300_000, "receives": [{"from": "A", "pct": 0.20}]},
    {"id": "C", "direct": 100_000, "receives": [{"from": "A", "pct": 0.10}]},
]

result = solve_linear_on_graph(
    items   = departments,
    id_fn   = lambda item: item["id"],
    deps_fn = lambda item: [(r["from"], r) for r in item.get("receives", [])],
    b_fn    = lambda node_id, item: float(item["direct"]),
    coeff_fn = lambda node_id, dep_id, edge: float(edge["pct"]),
    output_fn = lambda node_id, x, item, resolved: item.update({"total": x}),
    epsilon           = 1e-9,
    max_iter_fallback = 100,
    clamp_nonneg      = True,
)

print(result.has_cycle)       # True
print(result.values)          # {"A": ~521K, "B": ~352K, "C": ~152K}
print(result.warnings)        # []

for entry in result.audit.values():
    print(entry.explain())
```

---

## §25. Hệ thống lỗi

### 25.1 Hierarchy

```
FormulaError (base)
├── FormulaBudgetExceeded     ← ops, limit
├── FormulaComplexityError    ← metric, value, limit
├── FormulaLimitError         ← size, limit
├── FormulaRuntimeError
├── FormulaValidationError    ← errors: List[str]
├── FormulaDeterministicError ← func_name
└── FormulaAssertionError     ← violations
```

### 25.2 ErrorCode quan trọng

| Code                                 | Khi nào                                  |
| ------------------------------------ | ---------------------------------------- |
| `ENGINE.CIRCULAR_DEPENDENCY`         | A → B → A                                |
| `ENGINE.SYNTAX_ERROR`                | Cú pháp sai                              |
| `ENGINE.SECURITY_VIOLATION`          | import, lambda, os...                    |
| `ENGINE.MISSING_REQUIRED_INPUT`      | Thiếu required field                     |
| `ENGINE.UNKNOWN_FUNCTION`            | Hàm không tồn tại                        |
| `ENGINE.CONTEXT_NOT_INITIALIZED`     | Incremental trước create_context         |
| `ENGINE.STALE_CONTEXT`               | Formula set thay đổi sau khi tạo context |
| `ENGINE.BUDGET_EXCEEDED`             | Vượt max_operations                      |
| `ENGINE.NON_DETERMINISTIC_IN_FROZEN` | now()/today() khi deterministic=True     |

### 25.3 Bắt lỗi

```python
from formula_utils import FormulaError, FormulaBudgetExceeded

try:
    result = engine.calculate(inputs)
except FormulaBudgetExceeded as e:
    print(f"Budget: {e.ops}/{e.limit}")
except FormulaError as e:
    print(f"Code:    {e.code}")
    print(f"Level:   {e.level}")       # "ERROR" | "FATAL"
    print(f"Field:   {e.field_name}")
    print(f"Formula: {e.formula}")
    print(str(e))  # gợi ý tên biến gần giống

# Không bao giờ raise
r = engine.calculate_safe(inputs)
if not r["_ok"]:
    print(r["_error_type"])  # machine-readable slug
```

### 25.4 Lỗi thường gặp & cách sửa

| Lỗi                       | Nguyên nhân               | Cách sửa                     |
| ------------------------- | ------------------------- | ---------------------------- |
| `CIRCULAR_DEPENDENCY`     | A → B → A                 | Xem lại DAG                  |
| `MISSING_REQUIRED_INPUT`  | Thiếu field               | Thêm field hoặc strict=False |
| `SECURITY_VIOLATION`      | import, lambda, .format() | Dùng BASE_FUNCS              |
| `UNKNOWN_FUNCTION`        | Hàm không trong runtime   | Thêm vào safe_funcs          |
| `CONTEXT_NOT_INITIALIZED` | incremental trước create  | Gọi create_context() trước   |
| `STALE_CONTEXT`           | Formula set thay đổi      | Tạo context mới              |
| `BUDGET_EXCEEDED`         | Vượt max_operations       | Tăng limit                   |
| `NON_DETERMINISTIC`       | now()/today()             | deterministic=False          |

---

## §26. Ví dụ thực tế tổng hợp

### 26.1 Hệ thống tính lương đầy đủ (Việt Nam)

```python
from formula_utils import FormulaEngine, InputField, SnapshotTag, SnapshotStatus

engine_luong = FormulaEngine(
    formulas=[
        {"name": "LUONG_GROSS",
         "formula": "LUONG_CB + PC_TRACH_NHIEM + PC_THAM_NIEN + THU_NHAP_KHAC"},

        {"name": "BHXH_NLD",  "formula": "min(LUONG_GROSS, 36 * LUONG_CSTT) * 8%"},
        {"name": "BHYT_NLD",  "formula": "min(LUONG_GROSS, 36 * LUONG_CSTT) * 1.5%"},
        {"name": "BHTN_NLD",  "formula": "min(LUONG_GROSS, 20 * LUONG_CSTT) * 1%"},
        {"name": "TONG_BH_NLD","formula": "BHXH_NLD + BHYT_NLD + BHTN_NLD"},

        {"name": "TNT",
         "formula": "LUONG_GROSS - TONG_BH_NLD - GIAM_TRU_BT - GIAM_TRU_TN"},

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

        {"name": "LUONG_THUC_NHAN",
         "formula": "LUONG_GROSS - TONG_BH_NLD - THUE_TNCN"},

        {"name": "BHXH_NSLD",  "formula": "min(LUONG_GROSS, 36 * LUONG_CSTT) * 17%"},
        {"name": "BHYT_NSLD",  "formula": "min(LUONG_GROSS, 36 * LUONG_CSTT) * 3%"},
        {"name": "BHTN_NSLD",  "formula": "min(LUONG_GROSS, 20 * LUONG_CSTT) * 1%"},
        {"name": "CHI_PHI_NS",
         "formula": "LUONG_GROSS + BHXH_NSLD + BHYT_NSLD + BHTN_NSLD"},
    ],
    input_fields=[
        InputField("LUONG_CB",       float, True),
        InputField("PC_TRACH_NHIEM", float, False, 0),
        InputField("PC_THAM_NIEN",   float, False, 0),
        InputField("THU_NHAP_KHAC",  float, False, 0),
        InputField("GIAM_TRU_BT",    float, False, 11_000_000),
        InputField("GIAM_TRU_TN",    float, False, 0),
        InputField("LUONG_CSTT",     float, False, 2_340_000),
    ],
    on_error="default",
    deterministic=True,
    rounding_policy={
        "THUE_TNCN":        {"decimals": 0},
        "LUONG_THUC_NHAN":  {"decimals": 0},
        "CHI_PHI_NS":       {"decimals": 0},
    },
)

r = engine_luong.calculate({
    "LUONG_CB":       15_000_000,
    "PC_TRACH_NHIEM":  3_000_000,
    "PC_THAM_NIEN":    1_500_000,
    "GIAM_TRU_TN":     4_400_000,
})
print(f"Lương Gross:      {r['LUONG_GROSS']:>15,.0f}")
print(f"BH nhân viên:     {r['TONG_BH_NLD']:>15,.0f}")
print(f"Thu nhập chịu thuế:{r['TNT']:>14,.0f}")
print(f"Thuế TNCN:        {r['THUE_TNCN']:>15,.0f}")
print(f"Lương thực nhận:  {r['LUONG_THUC_NHAN']:>15,.0f}")
print(f"Chi phí NS:       {r['CHI_PHI_NS']:>15,.0f}")

# So sánh kịch bản tăng lương
cmp = engine_luong.compare_scenarios({
    "Hiện tại": {"LUONG_CB": 15_000_000},
    "Tăng 20%": {"LUONG_CB": 18_000_000},
    "Tăng 40%": {"LUONG_CB": 21_000_000},
}, fields=["LUONG_GROSS", "THUE_TNCN", "LUONG_THUC_NHAN", "CHI_PHI_NS"])
print(cmp.to_table())
```

### 26.2 Dashboard KPI theo phòng ban

```python
engine_kpi = FormulaEngine(
    formulas=[
        {"name": "LUONG_THEO_PHONG",
         "formula": "group_sum(NHAN_VIEN, 'phong', 'luong')"},

        {"name": "KPI_TB",
         "formula": "average(NHAN_VIEN, key='kpi')"},

        {"name": "SO_NV_KPI_TOT",
         "formula": "countif(NHAN_VIEN, '>=90', key='kpi')"},

        {"name": "TY_LE_KPI_TOT",
         "formula": "safe_div(SO_NV_KPI_TOT, count(NHAN_VIEN)) * 100"},

        # Nhân viên KPI cao nhất mỗi phòng
        {"name": "TOP_NV_THEO_PHONG",
         "formula": "last(NHAN_VIEN, sort_by='kpi', group_by='phong', value_key='ten')"},

        # Top 3 nhân viên toàn công ty
        {"name": "TOP3_NV",
         "formula": "last(NHAN_VIEN, sort_by='kpi', n=3, value_key='ten')"},

        {"name": "LUONG_CHINH_THUC",
         "formula": "sumifs(NHAN_VIEN, key='luong', loai='CT')"},

        {"name": "BIEN_DONG_KPI",
         "formula": "max(NHAN_VIEN, key='kpi') - min(NHAN_VIEN, key='kpi')"},
    ],
    deterministic=True,
)

r = engine_kpi.calculate({
    "NHAN_VIEN": [
        {"ten": "An",    "phong": "IT",  "kpi": 90, "luong": 20e6, "loai": "CT"},
        {"ten": "Bình",  "phong": "IT",  "kpi": 95, "luong": 22e6, "loai": "CT"},
        {"ten": "Cường", "phong": "KT",  "kpi": 88, "luong": 18e6, "loai": "CT"},
        {"ten": "Dũng",  "phong": "KT",  "kpi": 82, "luong": 16e6, "loai": "HĐ"},
        {"ten": "Em",    "phong": "HR",  "kpi": 75, "luong": 14e6, "loai": "CT"},
    ]
})

print(f"Lương theo phòng: {r['LUONG_THEO_PHONG']}")
print(f"KPI TB:           {r['KPI_TB']:.1f}")
print(f"Top NV/phòng:     {r['TOP_NV_THEO_PHONG']}")
print(f"Top 3 toàn ty:    {r['TOP3_NV']}")
```

### 26.3 Phân bổ chi phí & Giá thành

```python
from formula_utils import allocate, FormulaEngine

# Bước 1: Phân bổ CPC theo giờ máy
sources = [{"id": "CPC", "amount": 350_000_000}]
targets = [
    {"id": "SP_001", "gio_may": 500},
    {"id": "SP_002", "gio_may": 700},
    {"id": "SP_003", "gio_may": 300},
]
result_alloc = allocate(sources, targets, "weight", target_weight_key="gio_may")
cpc_map = {ln.target_id: ln.allocated for ln in result_alloc.lines}

# Bước 2: Giá thành từng SP
engine_gt = FormulaEngine(formulas=[
    {"name": "TONG_CP",      "formula": "NVL + NC + CPC_PB"},
    {"name": "GIA_THANH_DV", "formula": "safe_div(TONG_CP, SAN_LUONG)"},
    {"name": "GIA_BAN",      "formula": "GIA_THANH_DV * (1 + BIEN_LAI)"},
    {"name": "LOI_NHUAN_DV", "formula": "GIA_BAN - GIA_THANH_DV"},
    {"name": "TY_SUAT_LN",   "formula": "percent_of(LOI_NHUAN_DV, GIA_BAN)"},
])

sp_data = [
    {"id": "SP_001", "NVL": 80e6, "NC": 20e6, "SAN_LUONG": 1000},
    {"id": "SP_002", "NVL": 60e6, "NC": 25e6, "SAN_LUONG": 800},
    {"id": "SP_003", "NVL": 30e6, "NC": 15e6, "SAN_LUONG": 500},
]

for sp in sp_data:
    r = engine_gt.calculate({**sp, "CPC_PB": cpc_map.get(sp["id"], 0), "BIEN_LAI": 0.20})
    print(f"{sp['id']}: GT={r['GIA_THANH_DV']:>10,.0f}  GB={r['GIA_BAN']:>10,.0f}"
          f"  LN={r['TY_SUAT_LN']:.1f}%")
```

### 26.4 IncrementalContext trong Frappe ERP

```python
import frappe, json
from formula_utils import FormulaEngine, IncrementalContext

def get_engine(formula_set_name: str) -> FormulaEngine:
    cache_key = f"formula_engine_{formula_set_name}"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        try:
            return FormulaEngine.from_cache_dict(json.loads(cached))
        except Exception:
            pass
    formulas = [{"name": r.field_name, "formula": r.formula}
                for r in frappe.get_doc("Formula Set", formula_set_name).formulas]
    engine = FormulaEngine(formulas=formulas, on_error="null", deterministic=True)
    frappe.cache().set_value(cache_key, json.dumps(engine.to_cache_dict()), 300)
    return engine


@frappe.whitelist()
def on_field_change(docname: str, field: str, value: float):
    engine = get_engine("BOM_Cost_Engine")
    cache_key = f"eng_ctx_{docname}"
    raw = frappe.cache().get_value(cache_key)
    ctx = None
    if raw:
        try:
            ctx = IncrementalContext.from_dict(engine, json.loads(raw))
        except Exception:
            ctx = None
    if ctx is None:
        doc = frappe.get_doc("BOM", docname)
        ctx = engine.create_context({"NVL": doc.nvl, "NC": doc.nc,
                                      "CPC": doc.cpc, "SAN_LUONG": doc.qty})
    result, stats = engine.calculate_incremental(
        ctx, {field: float(value)}, return_stats=True
    )
    frappe.cache().set_value(cache_key, json.dumps(ctx.to_dict()), 600)
    frappe.log_error(
        f"Incremental: {stats.recalculated_nodes}/{stats.total_nodes} "
        f"({stats.skip_ratio:.0%} skip) {stats.elapsed_ms:.2f}ms",
        "BOM Engine"
    )
    return result
```

### 26.5 TimeBucket + Báo cáo theo kỳ

```python
from formula_utils import FormulaEngine, generate_time_buckets

lich_su = [
    {"ngay": "2025-01-15", "sp": "A", "sl": 100, "dt": 10_000_000},
    {"ngay": "2025-03-20", "sp": "A", "sl": 120, "dt": 13_200_000},
    {"ngay": "2025-06-01", "sp": "B", "sl": 80,  "dt": 16_000_000},
    {"ngay": "2025-08-10", "sp": "A", "sl": 150, "dt": 16_500_000},
    {"ngay": "2025-09-15", "sp": "B", "sl": 90,  "dt": 18_000_000},
    {"ngay": "2025-11-20", "sp": "A", "sl": 200, "dt": 22_000_000},
]

engine_bc = FormulaEngine(
    formulas=[
        # Doanh thu Q3 (tháng 7-9)
        {"name": "DT_Q3",
         "formula": "sum(r['dt'] for r in DATA if r['ngay'] >= '2025-07-01' and r['ngay'] <= '2025-09-30')"},

        # Doanh thu SP_A
        {"name": "DT_SP_A",
         "formula": "sumif(DATA, 'A', key=('sp', 'dt'))"},

        # Doanh thu mới nhất theo SP
        {"name": "DT_MOI_THEO_SP",
         "formula": "last(DATA, sort_by='ngay', group_by='sp', value_key='dt')"},

        # Tháng có doanh thu cao nhất
        {"name": "THANG_DINH",
         "formula": "last(DATA, sort_by='dt', value_key='ngay')"},

        # Tổng doanh thu 3 tháng gần nhất
        {"name": "TONG_3T_CUOI",
         "formula": "sum(r['dt'] for r in last(sorted_array(DATA, key='ngay'), n=3, preserve_order=True))"},
    ],
    deterministic=True,
)

r = engine_bc.calculate({"DATA": lich_su})
print(f"DT Q3:               {r['DT_Q3']:>15,.0f}")
print(f"DT SP_A:             {r['DT_SP_A']:>15,.0f}")
print(f"DT mới nhất/SP:      {r['DT_MOI_THEO_SP']}")
print(f"Tháng doanh thu cao: {r['THANG_DINH']}")
print(f"Tổng 3 tháng cuối:   {r['TONG_3T_CUOI']:>15,.0f}")

# Báo cáo theo quý
buckets = generate_time_buckets(2025, ["quarter"])
for q in buckets["quarters"]:
    dt_q = [r["dt"] for r in lich_su
             if q.from_date <= r["ngay"] <= q.to_date]
    print(f"{q.full_label}: DT={sum(dt_q):,.0f}  n={len(dt_q)}")
```

---

## Cheat Sheet nhanh

### Patterns phổ biến

```python
# Tổng giá trị list[dict]
"sum(r['sl'] * r['dg'] for r in items)"

# Tổng có điều kiện
"sum(r['gia'] for r in items if r['loai'] = 'A')"

# Giá mới nhất
"last(lich_su, sort_by='ngay', value_key='gia')"

# Giá mới nhất THEO NHÓM
"last(lich_su, sort_by='ngay', group_by='ma_sp', value_key='gia')"

# N phần tử cuối (giữ thứ tự)
"last(sorted_array(rows, key='ngay'), n=5, preserve_order=True)"

# Tra bảng giá
"vlookup(MA_HANG, BANG_GIA, 2, 0)"

# Chia an toàn
"safe_div(TONG_CP, SAN_LUONG)"

# Giá trị trong khoảng
"clamp(DIEM_KPI * TY_LE, 0, MAX_THUONG)"

# Tổng theo phòng
"group_sum(NHAN_VIEN, 'phong', 'luong')"

# % hoàn thành
"percent_of(THUC_HIEN, KE_HOACH)"

# Lọc rồi đếm
"count(filter_array(SAN_PHAM, key='trang_thai', value='loi'))"

# Ngày + N tháng
"date_add(NGAY_HD, months=THOI_HAN)"

# Coalesce — ưu tiên override > standard > default
"coalesce(GIA_OVERRIDE, GIA_STANDARD, GIA_MAC_DINH)"

# Nhiều điều kiện
"and_(KHACH_HANG = 'VIP', TONG_TIEN >= 10_000_000, not_(IS_OVERDUE))"
```

---

_Formula Utils v29.1.0 — ENGINE_VERSION = "29.1.0" · Pure Python · Zero Dependencies_
