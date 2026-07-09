# Time Bucket — Hướng dẫn sử dụng chi tiết

> Formula Engine v18 · Pure Python · Zero dependencies

---

## Tổng quan kiến trúc

Time Bucket được tích hợp **2 tầng** vào engine:

| Tầng                          | Thành phần                                                    | Dùng khi nào                  |
| ----------------------------- | ------------------------------------------------------------- | ----------------------------- |
| **Tầng 1** — Formula built-in | `time_buckets()`, `in_time_bucket()`, `get_bucket_label()`    | Trong công thức tính toán     |
| **Tầng 2** — Engine method    | `engine.get_time_buckets()`, `engine.get_time_buckets_flat()` | App code, UI, báo cáo, export |

---

## Cấu trúc dữ liệu: `TimeBucket`

```python
@dataclass
class TimeBucket:
    type:      str   # 'year' | 'half' | 'quarter' | 'month' | 'week'
    label:     str   # 'Năm 2025', 'H1', 'Q1', 'T1', 'Tuần 1', ...
    from_date: str   # ISO "YYYY-MM-DD" — ngày đầu kỳ
    to_date:   str   # ISO "YYYY-MM-DD" — ngày cuối kỳ
    year:      int   # năm dương lịch
    index:     int   # 1-based: Q2→2, T3→3, Tuần 12→12

    def to_dict(self) -> dict   # serialize cho JSON / API
```

---

## Tầng 2 — Engine Methods (App code, UI, Báo cáo)

### `engine.get_time_buckets(year, types=None, ...)`

Trả về **dict có cấu trúc** — dùng khi cần truy cập từng loại riêng.

```python
from engine_v17 import FormulaEngine

engine = FormulaEngine(formulas=[...])

b = engine.get_time_buckets(2025)

# Truy cập từng loại
b['year']                    # TimeBucket — Năm 2025: 01/01 → 31/12
b['halves']                  # [H1, H2]
b['quarters']                # [Q1, Q2, Q3, Q4]
b['months']                  # [T1, T2, ..., T12]
b['weeks']                   # [Tuần 1, ..., Tuần 52/53]

# Truy cập thuộc tính
b['quarters'][0].label       # 'Q1'
b['quarters'][0].from_date   # '2025-01-01'
b['quarters'][0].to_date     # '2025-03-31'
b['quarters'][0].index       # 1
b['months'][2].label         # 'T3'
b['weeks'][0].from_date      # '2024-12-30'  ← ISO: tuần 1/2025 bắt đầu 30/12/2024
```

**Chỉ lấy một số loại:**

```python
b = engine.get_time_buckets(2025, types=['quarter', 'month'])
# b chỉ có key 'quarters' và 'months'
```

**Label kèm năm (cho export/báo cáo):**

```python
b = engine.get_time_buckets(2025, include_year_label=True)
b['quarters'][0].label   # 'Q1/2025'
b['months'][0].label     # 'T1/2025'
b['weeks'][0].label      # 'Tuần 1/2025'
```

**Tuần kiểu US (Chủ Nhật → Thứ Bảy):**

```python
b = engine.get_time_buckets(2025, week_start='sunday')
```

---

### `engine.get_time_buckets_flat(year, types=None, ..., as_dict=False)`

Trả về **list phẳng** — dùng cho UI dropdown, API response, export.

```python
# Cho UI dropdown (list TimeBucket)
flat = engine.get_time_buckets_flat(2025, types=['quarter', 'month'])
# → [Q1, Q2, Q3, Q4, T1, T2, ..., T12]

options = [(b.label, b.from_date, b.to_date) for b in flat]

# Cho API / JSON serialization
flat_dict = engine.get_time_buckets_flat(2025, as_dict=True)
# → [{'type': 'year', 'label': 'Năm 2025', ...}, {'type': 'half', ...}, ...]

import json
response = json.dumps(flat_dict, ensure_ascii=False)

# Cho báo cáo — kèm năm trong label
flat = engine.get_time_buckets_flat(2025,
    types=['quarter', 'month'],
    include_year_label=True,
    as_dict=True,
)
# → [{'label': 'Q1/2025', ...}, ..., {'label': 'T1/2025', ...}, ...]
```

**Thứ tự trả về:** year → halves → quarters → months → weeks

---

## Tầng 1 — Formula Built-ins (Dùng trong công thức)

Ba hàm sau có thể dùng **trực tiếp trong chuỗi formula** của engine.

### `time_buckets(year, type='all')`

Trả về danh sách các bucket — dùng để lọc / nhóm trong formula.

```python
# Lấy list quý
time_buckets(2025, "quarter")      # → [Q1, Q2, Q3, Q4]

# Lấy list tháng
time_buckets(2025, "month")        # → [T1, ..., T12]

# Lấy list tuần
time_buckets(2025, "week")         # → [Tuần 1, ..., Tuần 53]

# Lấy nửa năm
time_buckets(2025, "half")         # → [H1, H2]

# Lấy toàn bộ dict
time_buckets(2025)                 # → dict {'quarters': [...], 'months': [...], ...}
time_buckets(2025, "all")          # tương đương
```

---

### `in_time_bucket(date, bucket)`

Kiểm tra một ngày có nằm trong khoảng của bucket không.

```python
# Trả về True / False
in_time_bucket("2025-03-15", bucket)    # True nếu bucket chứa 15/3/2025
in_time_bucket(ngay_hd, bucket)         # ngay_hd là biến input
```

Hỗ trợ các dạng input ngày: `"YYYY-MM-DD"`, `"DD/MM/YYYY"`, `date`, `datetime`.

---

### `get_bucket_label(date, type)`

Trả về nhãn của kỳ mà ngày đó thuộc về.

```python
get_bucket_label("2025-03-15", "quarter")  # → "Q1"
get_bucket_label("2025-03-15", "month")    # → "T3"
get_bucket_label("2025-03-15", "week")     # → "Tuần 11"
get_bucket_label("2025-03-15", "half")     # → "H1"
```

---

## Ví dụ thực tế

### 1. Tính doanh thu theo quý

```python
engine = FormulaEngine(
    formulas=[
        # Lấy label quý từ ngày hóa đơn
        {'name': 'ky_quy', 'formula': 'get_bucket_label(ngay_hd, "quarter")'},

        # Kiểm tra hóa đơn có thuộc Q1 không
        {'name': 'la_q1',  'formula': 'in_time_bucket(ngay_hd, time_buckets(2025, "quarter")[0])'},

        # Tổng doanh thu Q1 từ list hóa đơn
        {'name': 'dt_q1',  'formula': 'sum(r["gia_tri"] for r in ds_hd if in_time_bucket(r["ngay"], time_buckets(2025, "quarter")[0]))'},
    ],
    deterministic=False,
)

# Tính cho 1 hóa đơn cụ thể
result = engine.calculate({
    'ngay_hd': '2025-03-15',
    'ds_hd': [
        {'ngay': '2025-01-10', 'gia_tri': 5_000_000},
        {'ngay': '2025-02-20', 'gia_tri': 3_000_000},
        {'ngay': '2025-07-05', 'gia_tri': 8_000_000},  # Q3 — bị loại
    ]
})

print(result['ky_quy'])  # 'Q1'
print(result['la_q1'])   # True
print(result['dt_q1'])   # 8_000_000 (5M + 3M, Q3 bị loại)
```

---

### 2. Nhóm doanh thu theo tháng

```python
engine = FormulaEngine(
    formulas=[
        # Nhóm doanh thu theo tháng: {'T1': 5000000, 'T2': 3000000, ...}
        {
            'name': 'dt_theo_thang',
            'formula': '''
                group_sum(
                    [{"ky": get_bucket_label(r["ngay"], "month"), "gia_tri": r["gia_tri"]} for r in ds_hd],
                    "ky",
                    "gia_tri"
                )
            '''
        },
    ],
    deterministic=False,
)

result = engine.calculate({
    'ds_hd': [
        {'ngay': '2025-01-10', 'gia_tri': 5_000_000},
        {'ngay': '2025-01-25', 'gia_tri': 2_000_000},
        {'ngay': '2025-02-20', 'gia_tri': 3_000_000},
        {'ngay': '2025-03-05', 'gia_tri': 4_500_000},
    ]
})

print(result['dt_theo_thang'])
# {'T1': 7_000_000, 'T2': 3_000_000, 'T3': 4_500_000}
```

---

### 3. UI Dropdown chọn kỳ báo cáo

```python
engine = FormulaEngine(formulas=[])

# Lấy toàn bộ options cho dropdown
options = engine.get_time_buckets_flat(2025, types=['quarter', 'month'])

# Render cho frontend (FastAPI, Django, Flask, ...)
dropdown_data = [
    {"value": b.label, "label": b.label, "from": b.from_date, "to": b.to_date}
    for b in options
]

# Kết quả:
# [
#   {"value": "Q1", "label": "Q1", "from": "2025-01-01", "to": "2025-03-31"},
#   {"value": "Q2", ...},
#   {"value": "Q3", ...},
#   {"value": "Q4", ...},
#   {"value": "T1", "label": "T1", "from": "2025-01-01", "to": "2025-01-31"},
#   {"value": "T2", ...},
#   ...
# ]
```

---

### 4. Export Excel/báo cáo theo kỳ

```python
engine = FormulaEngine(formulas=[])

# Lấy tất cả kỳ, kèm năm trong label, dạng dict cho JSON/Excel
buckets = engine.get_time_buckets_flat(
    2025,
    types=['quarter', 'month'],
    include_year_label=True,
    as_dict=True,
)

# Mỗi phần tử là dict sẵn sàng để ghi vào DataFrame / Excel
import csv, io
writer_buffer = io.StringIO()
writer = csv.DictWriter(writer_buffer, fieldnames=['type','label','from_date','to_date','year','index'])
writer.writeheader()
writer.writerows(buckets)
print(writer_buffer.getvalue())

# type,label,from_date,to_date,year,index
# quarter,Q1/2025,2025-01-01,2025-03-31,2025,1
# quarter,Q2/2025,2025-04-01,2025-06-30,2025,2
# ...
# month,T1/2025,2025-01-01,2025-01-31,2025,1
# ...
```

---

### 5. Lọc hóa đơn theo kỳ do user chọn

```python
engine = FormulaEngine(
    formulas=[
        # Lọc hóa đơn theo kỳ được truyền vào dưới dạng dict
        {
            'name': 'hd_trong_ky',
            'formula': 'filter_array(ds_hd, key="ngay", operator="between", lo=ky["from_date"], hi=ky["to_date"])'
        },
        {
            'name': 'tong_ky',
            'formula': 'sum(r["gia_tri"] for r in hd_trong_ky)'
        },
    ],
    deterministic=False,
)

# User chọn Q2 từ dropdown
selected = engine.get_time_buckets(2025)['quarters'][1]  # Q2

result = engine.calculate({
    'ky': selected.to_dict(),           # truyền bucket dưới dạng dict
    'ds_hd': [
        {'ngay': '2025-03-31', 'gia_tri': 1_000_000},  # Q1 — loại
        {'ngay': '2025-04-01', 'gia_tri': 5_000_000},  # Q2 ✓
        {'ngay': '2025-05-15', 'gia_tri': 3_500_000},  # Q2 ✓
        {'ngay': '2025-07-01', 'gia_tri': 2_000_000},  # Q3 — loại
    ]
})

print(result['tong_ky'])   # 8_500_000
```

---

### 6. Đa năm — so sánh cùng kỳ năm trước

```python
engine = FormulaEngine(
    formulas=[
        {'name': 'dt_q1_nam_nay',   'formula': 'sum(r["gia_tri"] for r in ds_hd if in_time_bucket(r["ngay"], time_buckets(nam_nay,   "quarter")[0]))'},
        {'name': 'dt_q1_nam_truoc', 'formula': 'sum(r["gia_tri"] for r in ds_hd if in_time_bucket(r["ngay"], time_buckets(nam_truoc, "quarter")[0]))'},
        {'name': 'tang_truong',     'formula': 'safe_div(dt_q1_nam_nay - dt_q1_nam_truoc, dt_q1_nam_truoc) * 100'},
    ],
    deterministic=False,
)

result = engine.calculate({
    'nam_nay':   2025,
    'nam_truoc': 2024,
    'ds_hd': [
        {'ngay': '2024-01-15', 'gia_tri': 10_000_000},
        {'ngay': '2024-02-20', 'gia_tri':  5_000_000},
        {'ngay': '2025-01-10', 'gia_tri': 18_000_000},
        {'ngay': '2025-03-30', 'gia_tri':  7_000_000},
    ]
})

print(f"Q1/2025: {result['dt_q1_nam_nay']:,.0f}")     # 25,000,000
print(f"Q1/2024: {result['dt_q1_nam_truoc']:,.0f}")   # 15,000,000
print(f"Tăng trưởng: {result['tang_truong']:.1f}%")   # 66.7%
```

---

## Tóm tắt nhanh

| Nhu cầu                       | Cách dùng                                                                   |
| ----------------------------- | --------------------------------------------------------------------------- |
| UI dropdown kỳ                | `engine.get_time_buckets_flat(year, types=[...])`                           |
| API / JSON                    | `engine.get_time_buckets_flat(year, as_dict=True)`                          |
| Export báo cáo                | `engine.get_time_buckets_flat(year, include_year_label=True, as_dict=True)` |
| Truy cập quý/tháng theo dict  | `engine.get_time_buckets(year)['quarters']`                                 |
| Lấy label kỳ từ ngày          | `get_bucket_label(ngay, "quarter")` trong formula                           |
| Kiểm tra ngày thuộc kỳ        | `in_time_bucket(ngay, bucket)` trong formula                                |
| Lấy list bucket trong formula | `time_buckets(year, "month")` trong formula                                 |
| Nhóm theo kỳ                  | kết hợp `get_bucket_label` + `group_sum` trong formula                      |
| So sánh cùng kỳ năm trước     | truyền `nam_nay`, `nam_truoc` vào `time_buckets(nam_nay, ...)`              |

---

## Ghi chú kỹ thuật

- **Tuần ISO 8601** (mặc định): Tuần bắt đầu Thứ Hai. Tuần 1 là tuần chứa ngày thứ Năm đầu tiên của năm. Có thể bao gồm vài ngày cuối năm trước (vd: Tuần 1/2025 bắt đầu 30/12/2024).
- **Tuần US** (`week_start='sunday'`): Tuần bắt đầu Chủ Nhật.
- **Năm có 53 tuần**: 2025 có 53 tuần ISO do ngày 1/1/2025 là Thứ Tư.
- **`in_time_bucket`** hỗ trợ cả `TimeBucket` object lẫn `dict` có key `from_date` / `to_date`.
- **`get_bucket_label`** trả về `""` (chuỗi rỗng) nếu không tìm thấy bucket phù hợp.
- **Tất cả hàm dùng `stdlib` Python thuần** — không cần cài thêm package.
