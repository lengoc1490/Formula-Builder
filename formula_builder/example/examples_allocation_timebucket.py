"""
==============================================================================
  Formula Engine v21 — Ví dụ toàn diện: Allocation + Time Bucket
  Từ cơ bản đến nâng cao · Pure Python · Zero dependencies
==============================================================================

  MỤC LỤC
  ──────────────────────────────────────────────────────────────────────────
  PHẦN 1 — ALLOCATION ENGINE
    1.1  equal          — Chia đều
    1.2  qty            — Theo số lượng
    1.3  amount         — Theo doanh thu / giá trị
    1.4  weight         — Theo trọng số tự đặt
    1.5  pct            — % kế toán cố định
    1.6  manual_amount  — Nhập tay số tiền từng dòng
    1.7  manual_pct     — % nhập tay từng dòng
    1.8  mixed          — Kết hợp manual + tự động
    1.9  group_key      — Phân bổ theo nhóm (phòng ban / dự án)
    1.10 Nhiều nguồn → nhiều đích (Cartesian)
    1.11 Kết quả: summary / to_dict / lược bỏ / to_sources_detail / to_full_dict
    1.12 Dùng qua FormulaEngine — engine.allocate() và built-in allocate()
    1.13 Custom field keys (schema khác mặc định)
    1.14 Rounding policies — last / largest / none
    1.15 Warnings & unallocated — kiểm tra sau phân bổ
    1.16 Thực tế: Phân bổ chi phí chung theo doanh thu từng bộ phận

  PHẦN 2 — TIME BUCKET
    2.1  generate_time_buckets()     — Dict đầy đủ cho 1 năm
    2.2  Chỉ lấy một số loại        — types=['quarter','month']
    2.3  Label kèm năm              — label_format="year"
    2.4  generate_time_buckets_flat() — List phẳng (UI/API/Export)
    2.5  as_ui / as_dict / as_filter / as_entry
    2.6  get_period()               — Lấy 1 kỳ cụ thể
    2.7  get_period_by_date()       — Tìm kỳ chứa ngày đó
    2.8  get_period_offset()        — Điều hướng prev/next
    2.9  same_period_last_year()    — Cùng kỳ năm trước
    2.10 "date" in bucket           — Kiểm tra ngày thuộc kỳ
    2.11 year_buckets()             — Buckets nhiều năm với offset
    2.12 TimeBucket.to_entry()      — Nhập liệu chứng từ
    2.13 Hàm built-in trong formula: time_buckets / in_time_bucket / get_bucket_label
    2.14 Nhóm doanh thu theo tháng  — group_sum + get_bucket_label
    2.15 So sánh cùng kỳ năm trước — tang_truong
    2.16 Tuần ISO và tuần US        — week_start='sunday'
    2.17 UI Dropdown / API JSON / Export CSV
    2.18 Lọc hóa đơn theo kỳ user chọn
    2.19 Thực tế: Báo cáo doanh thu Q/M + tỷ lệ

  PHẦN 3 — KẾT HỢP ALLOCATION + TIME BUCKET
    3.1  Phân bổ chi phí lương theo kỳ vào từng bộ phận
    3.2  So sánh phân bổ Q1 vs Q2 — bảng delta
==============================================================================
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# ─── Import engine ─────────────────────────────────────────────────────────────
try:
    from engine_v22 import (
        FormulaEngine,
        allocate,
        generate_time_buckets,
        generate_time_buckets_flat,
        get_period,
        get_period_by_date,
        get_period_offset,
        same_period_last_year,
        year_buckets,
    )
    ENGINE_AVAILABLE = True
except ImportError:
    ENGINE_AVAILABLE = False
    print("⚠  engine_v21 chưa tìm thấy — ví dụ hiển thị dưới dạng pseudo-code.\n")


# ══════════════════════════════════════════════════════════════════════════════
#  HELPER
# ══════════════════════════════════════════════════════════════════════════════
SEP  = "─" * 70
SEP2 = "═" * 70

def header(title):
    print(f"\n{SEP2}\n  {title}\n{SEP2}")

def subheader(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")

def print_lines(result):
    """In chi tiết từng dòng AllocationResult."""
    for ln in result.lines:
        print(f"    {ln.source_id:10s} → {ln.target_id:12s} : "
              f"{ln.allocated:>16,.0f}   ({ln.ratio:6.2%})   [{ln.method}]")

def print_summary(result):
    """In tóm tắt nguồn + đích."""
    print(f"    source_totals : {result.source_totals}")
    print(f"    target_totals : {result.target_totals}")
    print(f"    unallocated   : {result.unallocated}")
    print(f"    warnings      : {result.warnings}")
    print(f"    ok            : {result.ok}")


# ══════════════════════════════════════════════════════════════════════════════
#  PHẦN 1 — ALLOCATION ENGINE
# ══════════════════════════════════════════════════════════════════════════════

header("PHẦN 1 — ALLOCATION ENGINE")

# ─── 1.1 equal ───────────────────────────────────────────────────────────────
subheader("1.1  equal — Chia đều cho tất cả đích")

if ENGINE_AVAILABLE:
    sources = [{'id': 'CP001', 'amount': 120_000_000}]
    targets = [{'id': 'BP01'}, {'id': 'BP02'}, {'id': 'BP03'}]
    result = allocate(sources, targets, 'equal')
    print_lines(result)
    # CP001 → BP01 :  40,000,000  (33.33%)  [equal]
    # CP001 → BP02 :  40,000,000  (33.33%)  [equal]
    # CP001 → BP03 :  40,000,000  (33.33%)  [equal]
else:
    print("""
    sources = [{'id': 'CP001', 'amount': 120_000_000}]
    targets = [{'id': 'BP01'}, {'id': 'BP02'}, {'id': 'BP03'}]
    allocate(sources, targets, 'equal')
    → CP001→BP01: 40,000,000 (33.33%)
    → CP001→BP02: 40,000,000 (33.33%)
    → CP001→BP03: 40,000,000 (33.33%)
""")


# ─── 1.2 qty ─────────────────────────────────────────────────────────────────
subheader("1.2  qty — Theo tỷ lệ số lượng sản xuất")

if ENGINE_AVAILABLE:
    sources = [{'id': 'CP001', 'amount': 120_000_000}]
    targets = [
        {'id': 'BP01', 'qty': 100},   # 100/350 = 28.57%
        {'id': 'BP02', 'qty': 200},   # 200/350 = 57.14%
        {'id': 'BP03', 'qty':  50},   #  50/350 = 14.29%
    ]
    result = allocate(sources, targets, 'qty')
    print_lines(result)
else:
    print("""
    qty: [100, 200, 50] → tổng 350
    BP01: 120M × 100/350 =  34,285,714  (28.57%)
    BP02: 120M × 200/350 =  68,571,429  (57.14%)
    BP03: 120M ×  50/350 =  17,142,857  (14.29%)
""")


# ─── 1.3 amount ──────────────────────────────────────────────────────────────
subheader("1.3  amount — Theo tỷ lệ doanh thu")

if ENGINE_AVAILABLE:
    sources = [{'id': 'CP001', 'amount': 120_000_000}]
    targets = [
        {'id': 'BP01', 'amount':  5_000_000},   # 31.25%
        {'id': 'BP02', 'amount':  8_000_000},   # 50.00%
        {'id': 'BP03', 'amount':  3_000_000},   # 18.75%
    ]
    result = allocate(sources, targets, 'amount')
    print_lines(result)
else:
    print("""
    amount: [5M, 8M, 3M] → tổng 16M
    BP01: 120M × 5/16  = 37,500,000  (31.25%)
    BP02: 120M × 8/16  = 60,000,000  (50.00%)
    BP03: 120M × 3/16  = 22,500,000  (18.75%)
""")


# ─── 1.4 weight ──────────────────────────────────────────────────────────────
subheader("1.4  weight — Theo trọng số alloc_weight tự đặt")

if ENGINE_AVAILABLE:
    sources = [{'id': 'CP001', 'amount': 120_000_000}]
    targets = [
        {'id': 'BP01', 'alloc_weight': 3.0},   # 3/6 = 50%
        {'id': 'BP02', 'alloc_weight': 2.0},   # 2/6 = 33.33%
        {'id': 'BP03', 'alloc_weight': 1.0},   # 1/6 = 16.67%
    ]
    result = allocate(sources, targets, 'weight')
    print_lines(result)
else:
    print("""
    alloc_weight: [3.0, 2.0, 1.0] → tổng 6.0
    BP01: 120M × 3/6 = 60,000,000  (50.00%)
    BP02: 120M × 2/6 = 40,000,000  (33.33%)
    BP03: 120M × 1/6 = 20,000,000  (16.67%)
""")


# ─── 1.5 pct ─────────────────────────────────────────────────────────────────
subheader("1.5  pct — % kế toán cố định (auto-normalize nếu tổng != 100)")

if ENGINE_AVAILABLE:
    sources = [{'id': 'CP001', 'amount': 120_000_000}]
    targets = [
        {'id': 'BP01', 'alloc_pct': 50},
        {'id': 'BP02', 'alloc_pct': 30},
        {'id': 'BP03', 'alloc_pct': 20},
    ]
    result = allocate(sources, targets, 'pct')
    print_lines(result)
    print(f"\n    warnings: {result.warnings}")

    # Trường hợp tổng != 100 → engine tự normalize và cảnh báo
    print("\n  [Tổng alloc_pct = 80 (thiếu 20%) → engine normalize]")
    targets_bad = [
        {'id': 'BP01', 'alloc_pct': 60},
        {'id': 'BP02', 'alloc_pct': 20},
    ]
    result2 = allocate(sources, targets_bad, 'pct')
    print_lines(result2)
    print(f"\n    warnings: {result2.warnings}")
else:
    print("""
    alloc_pct: [50, 30, 20] → tổng = 100 ✓
    BP01: 60,000,000   BP02: 36,000,000   BP03: 24,000,000

    Nếu tổng != 100 → engine normalize + ghi result.warnings
    Vd: alloc_pct [60, 20] (tổng=80) → normalize 75% / 25%
""")


# ─── 1.6 manual_amount ───────────────────────────────────────────────────────
subheader("1.6  manual_amount — Nhập tay số tiền từng dòng")

if ENGINE_AVAILABLE:
    sources = [{'id': 'CP001', 'amount': 120_000_000}]
    targets = [
        {'id': 'BP01', 'alloc_amount': 50_000_000},
        {'id': 'BP02', 'alloc_amount': 40_000_000},
        {'id': 'BP03', 'alloc_amount': 30_000_000},
    ]
    result = allocate(sources, targets, 'manual_amount')
    print_lines(result)
    print(f"\n    unallocated: {result.unallocated}  ← 0 vì tổng manual = 120M = source")

    # Trường hợp tổng manual > source → phần âm trong unallocated
    print("\n  [Tổng manual (130M) > source (120M) → unallocated âm]")
    targets_over = [
        {'id': 'BP01', 'alloc_amount': 80_000_000},
        {'id': 'BP02', 'alloc_amount': 50_000_000},
    ]
    result3 = allocate(sources, targets_over, 'manual_amount')
    print(f"    unallocated: {result3.unallocated}")
else:
    print("""
    alloc_amount: [50M, 40M, 30M]  tổng = 120M = source → unallocated = 0
    BP01: 50,000,000   BP02: 40,000,000   BP03: 30,000,000

    Nếu tổng manual > source → unallocated < 0 (thâm hụt)
""")


# ─── 1.7 manual_pct ──────────────────────────────────────────────────────────
subheader("1.7  manual_pct — % nhập tay từng dòng")

if ENGINE_AVAILABLE:
    sources = [{'id': 'CP001', 'amount': 120_000_000}]
    targets = [
        {'id': 'BP01', 'manual_pct': 60},
        {'id': 'BP02', 'manual_pct': 25},
        {'id': 'BP03', 'manual_pct': 15},
    ]
    result = allocate(sources, targets, 'manual_pct')
    print_lines(result)
else:
    print("""
    manual_pct: [60%, 25%, 15%]
    BP01: 72,000,000   BP02: 30,000,000   BP03: 18,000,000
""")


# ─── 1.8 mixed ───────────────────────────────────────────────────────────────
subheader("1.8  mixed — Một số dòng manual, phần dư chia tự động")
print("  Ưu tiên: alloc_amount > manual_pct > residual (qty/amount/weight/equal)\n")

if ENGINE_AVAILABLE:
    sources = [{'id': 'CP001', 'amount': 120_000_000}]

    # Demo 1: residual theo qty
    print("  [Demo 1: mixed residual='qty']")
    targets = [
        {'id': 'BP01', 'alloc_amount': 30_000_000, 'qty': 100},  # manual số tiền
        {'id': 'BP02', 'manual_pct': 20,            'qty': 200},  # manual %
        {'id': 'BP03', 'qty': 50},                                # residual
        {'id': 'BP04', 'qty': 50},                                # residual
    ]
    result = allocate(sources, targets, method='mixed', mixed_residual_method='qty')
    print_lines(result)
    # BP01:  30M (25.00%) [mixed:manual_amount]
    # BP02:  24M (20.00%) [mixed:manual_pct(20.00%)]
    # BP03:  33M (27.50%) [mixed:qty]   ← dư 66M ÷ 100 qty × 50
    # BP04:  33M (27.50%) [mixed:qty]

    # Demo 2: residual theo amount
    print("\n  [Demo 2: mixed residual='amount']")
    targets2 = [
        {'id': 'K01', 'alloc_amount': 20_000_000, 'amount': 10_000_000},  # manual
        {'id': 'K02', 'manual_pct': 10,            'amount':  8_000_000},  # manual
        {'id': 'K03', 'amount': 12_000_000},   # residual → theo amount
        {'id': 'K04', 'amount':  6_000_000},   # residual
    ]
    result2 = allocate(sources, targets2, method='mixed', mixed_residual_method='amount')
    print_lines(result2)
    # K01: 20M  manual
    # K02: 12M  manual (10% × 120M)
    # K03: dư 88M × 12/(12+6) = 58.67M
    # K04: dư 88M ×  6/(12+6) = 29.33M

    # Demo 3: residual theo equal
    print("\n  [Demo 3: mixed residual='equal']")
    targets3 = [
        {'id': 'A1', 'alloc_amount': 24_000_000},   # manual cố định
        {'id': 'A2'},                                # residual equal
        {'id': 'A3'},                                # residual equal
        {'id': 'A4'},                                # residual equal
    ]
    result3 = allocate(sources, targets3, method='mixed', mixed_residual_method='equal')
    print_lines(result3)
    # A1: 24M  [manual]
    # A2-A4: dư 96M ÷ 3 = 32M mỗi dòng

    print()
    print_summary(result)
else:
    print("""
    Demo 1: mixed residual='qty'
    BP01: 30,000,000 (25.00%) [mixed:manual_amount]
    BP02: 24,000,000 (20.00%) [mixed:manual_pct(20.00%)]
    BP03: 33,000,000 (27.50%) [mixed:qty]
    BP04: 33,000,000 (27.50%) [mixed:qty]

    Demo 2: mixed residual='amount'  (dư theo tỷ lệ doanh thu)
    Demo 3: mixed residual='equal'   (dư chia đều)
""")


# ─── 1.9 group_key ───────────────────────────────────────────────────────────
subheader("1.9  group_key — Nguồn & đích chỉ phân bổ khi cùng nhóm")

if ENGINE_AVAILABLE:
    sources = [
        {'id': 'CP001', 'amount': 120_000_000, 'dept': 'KD'},
        {'id': 'CP002', 'amount':  60_000_000, 'dept': 'IT'},
        {'id': 'CP003', 'amount':  30_000_000, 'dept': 'HC'},
    ]
    targets = [
        {'id': 'KD_BP01', 'qty': 100, 'dept': 'KD'},
        {'id': 'KD_BP02', 'qty': 200, 'dept': 'KD'},
        {'id': 'IT_BP01', 'qty':  80, 'dept': 'IT'},
        {'id': 'IT_BP02', 'qty': 120, 'dept': 'IT'},
        {'id': 'HC_BP01', 'qty':   1, 'dept': 'HC'},
    ]
    result = allocate(sources, targets, 'qty', group_key='dept')
    print_lines(result)
    print()
    print_summary(result)
else:
    print("""
    group_key='dept':
    CP001 (KD) → KD_BP01: 40,000,000 (33.33%)
               → KD_BP02: 80,000,000 (66.67%)
    CP002 (IT) → IT_BP01: 24,000,000 (40.00%)
               → IT_BP02: 36,000,000 (60.00%)
    CP003 (HC) → HC_BP01: 30,000,000 (100.00%)
""")


# ─── 1.10 Nhiều nguồn → nhiều đích ───────────────────────────────────────────
subheader("1.10 Nhiều nguồn → nhiều đích (Cartesian allocation)")

if ENGINE_AVAILABLE:
    sources = [
        {'id': 'CP001', 'amount': 120_000_000},
        {'id': 'CP002', 'amount':  60_000_000},
        {'id': 'CP003', 'amount':  30_000_000},
    ]
    targets = [
        {'id': 'BP01', 'qty': 100},
        {'id': 'BP02', 'qty': 200},
        {'id': 'BP03', 'qty': 100},
    ]
    result = allocate(sources, targets, 'qty')
    print_lines(result)   # 9 dòng: 3 nguồn × 3 đích
    print()
    print_summary(result)
else:
    print("""
    3 nguồn × 3 đích = 9 dòng
    Tỷ lệ qty: 100/400=25%, 200/400=50%, 100/400=25%
    source_totals = {'CP001': 120M, 'CP002': 60M, 'CP003': 30M}
    target_totals = {'BP01': 52.5M, 'BP02': 105M, 'BP03': 52.5M}
""")


# ─── 1.11 Kết quả — lược bỏ / full / detail ─────────────────────────────────
subheader("1.11 Kết quả: summary · to_dict · lược bỏ · to_sources_detail · to_targets_detail · to_full_dict")

if ENGINE_AVAILABLE:
    sources = [
        {'id': 'CP001', 'amount': 120_000_000, 'ten': 'Chi phí nhân sự'},
        {'id': 'CP002', 'amount':  60_000_000, 'ten': 'Chi phí vận hành'},
    ]
    targets = [
        {'id': 'BP01', 'qty': 100, 'ten': 'Kinh doanh'},
        {'id': 'BP02', 'qty': 200, 'ten': 'Sản xuất'},
        {'id': 'BP03', 'qty':  50, 'ten': 'Hành chính'},
    ]
    result = allocate(sources, targets, 'qty')

    # (a) summary() — text tóm tắt
    print("  [a] result.summary():")
    print(result.summary())

    # (b) to_dict() — serialize cho JSON/API
    print("  [b] result.to_dict():")
    d = result.to_dict()
    print(f"       keys      : {list(d.keys())}")
    print(f"       lines[0]  : {d['lines'][0]}")

    # (c) Chỉ cần totals (lược bỏ)
    print("\n  [c] Lược bỏ — chỉ xem totals:")
    print(f"       source_totals : {result.source_totals}")
    print(f"       target_totals : {result.target_totals}")
    print(f"       unallocated   : {result.unallocated}")

    # (d) to_sources_detail — v21
    print("\n  [d] result.to_sources_detail(sources)  [v21]:")
    try:
        for row in result.to_sources_detail(sources):
            print(f"       {row}")
    except AttributeError:
        print("       (chỉ có trong v21+)")

    # (e) to_targets_detail — v21
    print("\n  [e] result.to_targets_detail(targets)  [v21]:")
    try:
        for row in result.to_targets_detail(targets):
            print(f"       {row}")
    except AttributeError:
        print("       (chỉ có trong v21+)")

    # (f) to_full_dict — v21
    print("\n  [f] result.to_full_dict(sources, targets)  [v21]:")
    try:
        fd = result.to_full_dict(sources, targets)
        print(f"       keys: {list(fd.keys())}")
    except AttributeError:
        print("       (chỉ có trong v21+)")
else:
    print("""
  result.summary()                                → text human-readable
  result.to_dict()                                → dict đầy đủ cho JSON/API
  result.source_totals / target_totals            → lược bỏ, chỉ xem totals
  result.unallocated                              → phần chưa phân bổ
  result.to_sources_detail(sources)    [v21]      → list chi tiết từng nguồn
  result.to_targets_detail(targets)    [v21]      → list chi tiết từng đích
  result.to_full_dict(sources, targets)[v21]      → dict đầy đủ + summary
""")


# ─── 1.12 Dùng qua FormulaEngine ─────────────────────────────────────────────
subheader("1.12 Dùng qua FormulaEngine — engine.allocate() và built-in allocate()")

if ENGINE_AVAILABLE:
    # Cách 1: engine method
    engine = FormulaEngine(formulas=[], deterministic=False)
    sources = [{'id': 'CP001', 'amount': 120_000_000}]
    targets = [{'id': 'BP01', 'qty': 100}, {'id': 'BP02', 'qty': 200}]
    result = engine.allocate(sources, targets, 'qty')
    print(f"  [engine.allocate()] ok={result.ok}  target_totals={result.target_totals}")

    # Cách 2: built-in trong formula
    engine2 = FormulaEngine(
        formulas=[
            {'name': 'phan_bo',
             'formula': 'allocate(ds_cp, ds_bp, "qty")'},
            {'name': 'tong_bp01',
             'formula': 'sum(l["allocated"] for l in phan_bo["lines"] if l["target_id"] == "BP01")'},
            {'name': 'tong_bp02',
             'formula': 'sum(l["allocated"] for l in phan_bo["lines"] if l["target_id"] == "BP02")'},
            {'name': 'ty_le_bp01',
             'formula': 'safe_div(tong_bp01, tong_bp01 + tong_bp02) * 100'},
        ],
        deterministic=False,
    )
    r = engine2.calculate({'ds_cp': sources, 'ds_bp': targets})
    print(f"  [formula built-in] tong_bp01 = {r['tong_bp01']:,.0f}")
    print(f"  [formula built-in] tong_bp02 = {r['tong_bp02']:,.0f}")
    print(f"  [formula built-in] ty_le_bp01 = {r['ty_le_bp01']:.1f}%")
else:
    print("""
  # Cách 1: engine method
  result = engine.allocate(sources, targets, 'qty')   → AllocationResult

  # Cách 2: trong formula (trả về dict, dùng ["lines"], ["source_totals"], ...)
  engine = FormulaEngine(formulas=[
      {'name': 'phan_bo',  'formula': 'allocate(ds_cp, ds_bp, "qty")'},
      {'name': 'tong_bp01','formula': 'sum(l["allocated"] for l in phan_bo["lines"] if l["target_id"] == "BP01")'},
  ])
""")


# ─── 1.13 Custom field keys ───────────────────────────────────────────────────
subheader("1.13 Custom field keys — schema khác mặc định")

if ENGINE_AVAILABLE:
    sources_c = [
        {'ma_ct': 'C01', 'gia_tri': 90_000_000},
        {'ma_ct': 'C02', 'gia_tri': 30_000_000},
    ]
    targets_c = [
        {'ma_bp': 'D01', 'so_luong': 300},
        {'ma_bp': 'D02', 'so_luong': 200},
        {'ma_bp': 'D03', 'so_luong': 100},
    ]
    result = allocate(
        sources_c, targets_c, 'qty',
        source_id_key     = 'ma_ct',
        source_amount_key = 'gia_tri',
        target_id_key     = 'ma_bp',
        target_qty_key    = 'so_luong',
    )
    print_lines(result)
else:
    print("""
  allocate(sources, targets, 'qty',
      source_id_key     = 'ma_ct',       # mặc định 'id'
      source_amount_key = 'gia_tri',     # mặc định 'amount'
      target_id_key     = 'ma_bp',       # mặc định 'id'
      target_qty_key    = 'so_luong',    # mặc định 'qty'
      target_amount_key = 'doanh_thu',   # mặc định 'amount'
  )
""")


# ─── 1.14 Rounding policies ───────────────────────────────────────────────────
subheader("1.14 Rounding policies — last / largest / none")

if ENGINE_AVAILABLE:
    sources = [{'id': 'CP001', 'amount': 100}]
    targets = [{'id': f'BP0{i}', 'qty': 1} for i in range(1, 4)]   # 3 đích equal → 33.33... each

    print("  [last]    — phần dư rounding vào dòng CUỐI:")
    for ln in allocate(sources, targets, 'qty', rounding_policy='last').lines:
        print(f"    {ln.target_id}: {ln.allocated}")

    print("  [largest] — phần dư rounding vào dòng GIÁ TRỊ LỚN NHẤT:")
    for ln in allocate(sources, targets, 'qty', rounding_policy='largest').lines:
        print(f"    {ln.target_id}: {ln.allocated}")

    print("  [none]    — không làm tròn, giữ số thực:")
    for ln in allocate(sources, targets, 'qty', rounding_policy='none', round_digits=8).lines:
        print(f"    {ln.target_id}: {ln.allocated}")
else:
    print("""
  rounding_policy='last'    → phần dư cent → dòng cuối cùng
  rounding_policy='largest' → phần dư cent → dòng có giá trị lớn nhất
  rounding_policy='none'    → không làm tròn (kết hợp round_digits=6/8)
""")


# ─── 1.15 Warnings & unallocated ─────────────────────────────────────────────
subheader("1.15 Warnings & Unallocated — kiểm tra sau phân bổ")

if ENGINE_AVAILABLE:
    sources = [{'id': 'CP001', 'amount': 100_000_000}]
    targets = [
        {'id': 'BP01', 'alloc_amount': 80_000_000},
        {'id': 'BP02', 'alloc_amount': 40_000_000},   # tổng 120M > 100M
    ]
    result = allocate(sources, targets, 'manual_amount')

    print("  Kiểm tra pattern chuẩn:")
    if not result.ok:
        print("  ⚠  result.ok = False — có vấn đề phân bổ!")

    for sid, una in result.unallocated.items():
        if una != 0:
            sign = "dư" if una > 0 else "thâm hụt"
            print(f"  Nguồn {sid} {sign}: {abs(una):,.0f}")

    for w in result.warnings:
        print(f"  ⚠  {w}")
else:
    print("""
  if not result.ok:
      print("Có vấn đề phân bổ")
  for sid, una in result.unallocated.items():
      if una != 0:
          sign = "dư" if una > 0 else "thâm hụt"
          print(f"Nguồn {sid} {sign}: {abs(una):,.0f}")
  for w in result.warnings:
      print(f"⚠ {w}")
""")


# ─── 1.16 Thực tế ────────────────────────────────────────────────────────────
subheader("1.16 Thực tế: Phân bổ chi phí chung 3 khoản → 4 bộ phận theo doanh thu + nhóm")

if ENGINE_AVAILABLE:
    sources = [
        {'id': 'CP_DIEN',  'amount': 24_000_000, 'loai': 'HANHCHINH'},
        {'id': 'CP_NUOC',  'amount':  6_000_000, 'loai': 'HANHCHINH'},
        {'id': 'CP_MB',    'amount': 60_000_000, 'loai': 'SANXUAT'},
        {'id': 'CP_IT',    'amount': 18_000_000, 'loai': 'SANXUAT'},
    ]
    targets = [
        {'id': 'BP_KD', 'amount': 500_000_000, 'loai': 'HANHCHINH'},
        {'id': 'BP_HC', 'amount': 100_000_000, 'loai': 'HANHCHINH'},
        {'id': 'BP_SX1','amount': 800_000_000, 'loai': 'SANXUAT'},
        {'id': 'BP_SX2','amount': 400_000_000, 'loai': 'SANXUAT'},
    ]
    result = allocate(sources, targets, method='amount', group_key='loai')
    print_lines(result)
    print()
    print_summary(result)
else:
    print("""
  HANHCHINH (CP_DIEN + CP_NUOC=30M) → BP_KD(83.33%), BP_HC(16.67%)
  SANXUAT   (CP_MB + CP_IT=78M)     → BP_SX1(66.67%), BP_SX2(33.33%)
""")


# ══════════════════════════════════════════════════════════════════════════════
#  PHẦN 2 — TIME BUCKET
# ══════════════════════════════════════════════════════════════════════════════

header("PHẦN 2 — TIME BUCKET")

# ─── 2.1 generate_time_buckets() ─────────────────────────────────────────────
subheader("2.1  generate_time_buckets() — Dict đầy đủ cho 1 năm")

if ENGINE_AVAILABLE:
    b = generate_time_buckets(2025)
    print(f"  keys: {list(b.keys())}")

    print(f"\n  year   : {b['year'].label}  {b['year'].from_date} → {b['year'].to_date}")
    print("\n  halves :")
    for h in b['halves']:
        print(f"    {h.label}: {h.from_date} → {h.to_date}")
    print("\n  quarters:")
    for q in b['quarters']:
        print(f"    {q.label}: {q.from_date} → {q.to_date}  (index={q.index})")
    print("\n  months (T1-T4):")
    for m in b['months'][:4]:
        print(f"    {m.label}: {m.from_date} → {m.to_date}")
    print("\n  weeks (Tuần 1-3, lưu ý ISO: Tuần 1/2025 bắt đầu 30/12/2024):")
    for w in b['weeks'][:3]:
        print(f"    {w.label}: {w.from_date} → {w.to_date}")
    print(f"\n  Tổng số tuần năm 2025: {len(b['weeks'])}  ← 53 tuần (ISO)")
else:
    print("""
  b = generate_time_buckets(2025)
  b['year']     → Năm 2025: 2025-01-01 → 2025-12-31
  b['halves']   → [H1: 01/01→30/06, H2: 01/07→31/12]
  b['quarters'] → [Q1: 01/01→31/03, Q2: 01/04→30/06, Q3: 01/07→30/09, Q4: 01/10→31/12]
  b['months']   → [T1→T12]
  b['weeks']    → [Tuần 1→Tuần 53]  (53 tuần năm 2025)
""")


# ─── 2.2 Chỉ lấy 1 số loại ───────────────────────────────────────────────────
subheader("2.2  Chỉ lấy một số loại — types=")

if ENGINE_AVAILABLE:
    b = generate_time_buckets(2025, types=['quarter', 'month'])
    print(f"  keys: {list(b.keys())}  ← chỉ có 'quarters', 'months'")
    print(f"  Q3: {b['quarters'][2].from_date} → {b['quarters'][2].to_date}")
    print(f"  T9: {b['months'][8].from_date} → {b['months'][8].to_date}")
else:
    print("  generate_time_buckets(2025, types=['quarter', 'month'])")


# ─── 2.3 Label kèm năm ───────────────────────────────────────────────────────
subheader("2.3  Label kèm năm — label_format='Y'")

if ENGINE_AVAILABLE:
    b = generate_time_buckets(2025)
    print("  Quý :", [q.label for q in b['quarters']])
    print("  Tháng:", [m.label for m in b['months'][:4]])
    print("  Tuần :", [w.label for w in b['weeks'][:4]])
else:
    print("""
  generate_time_buckets(2025)
  quarters: ['Q1/2025', 'Q2/2025', 'Q3/2025', 'Q4/2025']
  months  : ['T1/2025', 'T2/2025', ..., 'T12/2025']
  weeks   : ['Tuần 1/2025', 'Tuần 2/2025', ...]
""")


# ─── 2.4 + 2.5 generate_time_buckets_flat() ───────────────────────────────────
subheader("2.4 + 2.5  generate_time_buckets_flat() — as_dict / as_ui / as_filter / as_entry")

if ENGINE_AVAILABLE:
    import json

    # Mặc định: list TimeBucket objects
    flat = generate_time_buckets_flat(2025, types=['quarter', 'month'])
    print(f"  flat: {len(flat)} phần tử  [{flat[0].label} ... {flat[-1].label}]")

    # as_dict=True → JSON serializable
    flat_dict = generate_time_buckets_flat(2025, types=['quarter'], as_dict=True)
    print("\n  as_dict=True (quý):")
    for d in flat_dict:
        print(f"    {d}")

    # as_ui → [(label, from_date, to_date)] cho select widget
    try:
        flat_ui = generate_time_buckets_flat(2025, types=['quarter'], as_ui=True)
        print("\n  as_ui=True:")
        for item in flat_ui:
            print(f"    {item}")
    except (TypeError, AttributeError):
        print("\n  as_ui: không hỗ trợ trong phiên bản này, dùng as_dict=True")

    # as_filter → [{'label':..., 'from':..., 'to':...}]
    try:
        flat_filter = generate_time_buckets_flat(2025, types=['quarter'], as_filter=True)
        print("\n  as_filter=True:")
        for item in flat_filter[:2]:
            print(f"    {item}")
    except (TypeError, AttributeError):
        print("\n  as_filter: không hỗ trợ, dùng as_dict=True + rename keys")

    # as_entry → gắn vào chứng từ
    try:
        flat_entry = generate_time_buckets_flat(2025, types=['quarter'], as_entry=True)
        print("\n  as_entry=True:")
        for item in flat_entry[:2]:
            print(f"    {item}")
    except (TypeError, AttributeError):
        print("\n  as_entry: không hỗ trợ, dùng bucket.to_entry() trực tiếp")
else:
    print("""
  # Mặc định: list TimeBucket objects
  flat = generate_time_buckets_flat(2025, types=['quarter', 'month'])
  # → [Q1, Q2, Q3, Q4, T1, T2, ..., T12]   (16 phần tử)

  # JSON API
  as_dict=True  → [{'type':'quarter','label':'Q1','from_date':'2025-01-01',...}, ...]

  # UI dropdown
  as_ui=True    → [('Q1','2025-01-01','2025-03-31'), ...]

  # Query filter
  as_filter=True → [{'label':'Q1','from':'2025-01-01','to':'2025-03-31'}, ...]

  # Nhập liệu chứng từ
  as_entry=True → [{'ky':'Q1','tu_ngay':'2025-01-01','den_ngay':'2025-03-31',...}, ...]
""")


# ─── 2.6 get_period() ────────────────────────────────────────────────────────
subheader("2.6  get_period() — Lấy 1 kỳ cụ thể")

if ENGINE_AVAILABLE:
    for args in [('quarter',1,2025), ('quarter',3,2025), ('month',6,2025),
                 ('half',2,2025), ('week',1,2025)]:
        bk = get_period(*args)
        print(f"  {args[0]:8s} index={args[1]}: {bk.label:12s} {bk.from_date} → {bk.to_date}")
else:
    print("""
  get_period('quarter', 1, 2025) → Q1: 2025-01-01 → 2025-03-31
  get_period('quarter', 3, 2025) → Q3: 2025-07-01 → 2025-09-30
  get_period('month',   6, 2025) → T6: 2025-06-01 → 2025-06-30
  get_period('half',    2, 2025) → H2: 2025-07-01 → 2025-12-31
  get_period('week',    1, 2025) → Tuần 1: 2024-12-30 → 2025-01-05
""")


# ─── 2.7 get_period_by_date() ────────────────────────────────────────────────
subheader("2.7  get_period_by_date() — Tìm kỳ chứa ngày đó")

if ENGINE_AVAILABLE:
    ngay = '2025-08-20'
    print(f"  Ngày: {ngay}")
    for typ in ['year', 'half', 'quarter', 'month', 'week']:
        bk = get_period_by_date(ngay, typ)
        print(f"    {typ:8s}: {bk.label:15s} ({bk.from_date} → {bk.to_date})")
else:
    print("""
  get_period_by_date('2025-08-20', 'year')    → Năm 2025
  get_period_by_date('2025-08-20', 'half')    → H2
  get_period_by_date('2025-08-20', 'quarter') → Q3
  get_period_by_date('2025-08-20', 'month')   → T8
  get_period_by_date('2025-08-20', 'week')    → Tuần 34
""")


# ─── 2.8 get_period_offset() ─────────────────────────────────────────────────
subheader("2.8  get_period_offset() — Điều hướng prev / next")

if ENGINE_AVAILABLE:
    q2_2025 = get_period('quarter', 2, 2025)
    print(f"  Gốc: {q2_2025.label}/{q2_2025.year}")

    for n, label in [(-1, "kỳ trước"), (+1, "kỳ sau"), (-4, "cùng kỳ năm trước"), (+4, "cùng kỳ năm sau")]:
        bk = get_period_offset(q2_2025, n)
        print(f"    offset {n:+d}  ({label:20s}): {bk.label}/{bk.year}")

    print()
    t1_2025 = get_period('month', 1, 2025)
    print(f"  T1/2025 offset -1 : {get_period_offset(t1_2025, -1).label}/{get_period_offset(t1_2025, -1).year}")
    print(f"  T1/2025 offset +13: {get_period_offset(t1_2025, 13).label}/{get_period_offset(t1_2025, 13).year}")
else:
    print("""
  q2 = get_period('quarter', 2, 2025)
  get_period_offset(q2, -1)  → Q1/2025  (kỳ trước)
  get_period_offset(q2, +1)  → Q3/2025  (kỳ sau)
  get_period_offset(q2, -4)  → Q2/2024  (cùng kỳ năm trước)
  get_period_offset(q2, +4)  → Q2/2026  (cùng kỳ năm sau)

  t1_2025 = get_period('month', 1, 2025)
  get_period_offset(t1_2025, -1)  → T12/2024
  get_period_offset(t1_2025, +13) → T2/2026
""")


# ─── 2.9 same_period_last_year() ─────────────────────────────────────────────
subheader("2.9  same_period_last_year() — Cùng kỳ năm trước")

if ENGINE_AVAILABLE:
    for typ in ['quarter', 'month', 'half']:
        cur  = get_period_by_date('2025-09-15', typ)
        prev = same_period_last_year(cur)
        print(f"  {typ:8s}: {cur.label}/{cur.year} → {prev.label}/{prev.year}")
else:
    print("""
  same_period_last_year(Q3/2025) → Q3/2024
  same_period_last_year(T9/2025) → T9/2024
  same_period_last_year(H2/2025) → H2/2024
""")


# ─── 2.10 "date" in bucket ───────────────────────────────────────────────────
subheader("2.10 'date' in bucket — Kiểm tra ngày thuộc kỳ (__contains__)")

if ENGINE_AVAILABLE:
    q3 = get_period('quarter', 3, 2025)
    tests = ['2025-06-30', '2025-07-01', '2025-09-30', '2025-10-01', '2025-08-15']
    print(f"  Kỳ: {q3.label} ({q3.from_date} → {q3.to_date})")
    for d in tests:
        print(f"    '{d}' in Q3: {d in q3}")
else:
    print("""
  q3 = get_period('quarter', 3, 2025)
  '2025-06-30' in q3  → False  (Q2, ranh giới ngoài)
  '2025-07-01' in q3  → True   (ngày đầu Q3)
  '2025-09-30' in q3  → True   (ngày cuối Q3)
  '2025-10-01' in q3  → False  (Q4)
""")


# ─── 2.11 year_buckets() ─────────────────────────────────────────────────────
subheader("2.11 year_buckets() — Buckets nhiều năm với offset")

if ENGINE_AVAILABLE:
    try:
        qs = year_buckets('quarter', year=2025, offset=-2)   # 2023, 2024, 2025
        print(f"  year_buckets('quarter', year=2025, offset=-2): {len(qs)} quý")
        for q in qs:
            print(f"    {q.label}/{q.year}: {q.from_date} → {q.to_date}")
    except Exception as e:
        # Fallback: một số phiên bản có signature khác
        print(f"  year_buckets: {e}")
        print("  Dùng thủ công: [get_period('quarter', i, y) for y in [2023,2024,2025] for i in range(1,5)]")
else:
    print("""
  year_buckets('quarter', year=2025, offset=-2)
  → Q1/2023, Q2/2023, Q3/2023, Q4/2023,
    Q1/2024, Q2/2024, Q3/2024, Q4/2024,
    Q1/2025, Q2/2025, Q3/2025, Q4/2025
  (12 quý, 3 năm gần nhất)
""")


# ─── 2.12 to_entry() ─────────────────────────────────────────────────────────
subheader("2.12 TimeBucket.to_entry() — Nhập liệu chứng từ")

if ENGINE_AVAILABLE:
    q2 = get_period('quarter', 2, 2025)
    try:
        entry = q2.to_entry()
        print(f"  q2.to_entry(): {entry}")
    except AttributeError:
        d = q2.to_dict()
        print(f"  q2.to_dict():  {d}")
        print("  (to_entry() chỉ có trong v21+)")
else:
    print("""
  q2.to_entry()
  → {'type': 'quarter', 'label': 'Q2', 'from_date': '2025-04-01',
     'to_date': '2025-06-30', 'year': 2025, 'index': 2}
""")


# ─── 2.13 Hàm built-in trong formula ─────────────────────────────────────────
subheader("2.13 Hàm built-in trong formula: time_buckets / in_time_bucket / get_bucket_label")

if ENGINE_AVAILABLE:
    engine = FormulaEngine(
        formulas=[
            {'name': 'ky_thang',   'formula': 'get_bucket_label(ngay_hd, "month")'},
            {'name': 'ky_quy',     'formula': 'get_bucket_label(ngay_hd, "quarter")'},
            {'name': 'ky_nua_nam', 'formula': 'get_bucket_label(ngay_hd, "half")'},
            {'name': 'la_q1',
             'formula': 'in_time_bucket(ngay_hd, time_buckets(2025, "quarter")[0])'},
            {'name': 'dt_q1',
             'formula': 'sum(r["gia_tri"] for r in ds_hd if in_time_bucket(r["ngay"], time_buckets(2025, "quarter")[0]))'},
            {'name': 'dt_q2',
             'formula': 'sum(r["gia_tri"] for r in ds_hd if in_time_bucket(r["ngay"], time_buckets(2025, "quarter")[1]))'},
        ],
        deterministic=False,
    )
    r = engine.calculate({
        'ngay_hd': '2025-05-20',
        'ds_hd': [
            {'ngay': '2025-01-10', 'gia_tri': 5_000_000},
            {'ngay': '2025-02-20', 'gia_tri': 3_000_000},
            {'ngay': '2025-04-05', 'gia_tri': 8_000_000},
            {'ngay': '2025-05-15', 'gia_tri': 4_000_000},
            {'ngay': '2025-07-01', 'gia_tri': 6_000_000},  # Q3 → không tính
        ],
    })
    print(f"  ky_thang   = {r['ky_thang']}")
    print(f"  ky_quy     = {r['ky_quy']}")
    print(f"  ky_nua_nam = {r['ky_nua_nam']}")
    print(f"  la_q1      = {r['la_q1']}")
    print(f"  dt_q1      = {r['dt_q1']:,.0f}")
    print(f"  dt_q2      = {r['dt_q2']:,.0f}")
else:
    print("""
  ky_thang   = 'T5'
  ky_quy     = 'Q2'
  ky_nua_nam = 'H1'
  la_q1      = False  (ngay_hd là tháng 5)
  dt_q1      = 8,000,000  (T1 + T2)
  dt_q2      = 12,000,000 (T4 + T5)
""")


# ─── 2.14 Nhóm doanh thu theo tháng ──────────────────────────────────────────
subheader("2.14 Nhóm doanh thu theo tháng và quý — group_sum + get_bucket_label")

if ENGINE_AVAILABLE:
    engine = FormulaEngine(
        formulas=[
            {'name': 'dt_theo_thang',
             'formula': 'group_sum([{"ky": get_bucket_label(r["ngay"], "month"), "gt": r["dt"]} for r in ds_hd], "ky", "gt")'},
            {'name': 'dt_theo_quy',
             'formula': 'group_sum([{"ky": get_bucket_label(r["ngay"], "quarter"), "gt": r["dt"]} for r in ds_hd], "ky", "gt")'},
        ],
        deterministic=False,
    )
    r = engine.calculate({
        'ds_hd': [
            {'ngay': '2025-01-10', 'dt': 5_000_000},
            {'ngay': '2025-01-25', 'dt': 2_000_000},
            {'ngay': '2025-02-20', 'dt': 3_000_000},
            {'ngay': '2025-03-05', 'dt': 4_500_000},
            {'ngay': '2025-04-01', 'dt': 7_000_000},
            {'ngay': '2025-05-15', 'dt': 6_000_000},
        ],
    })
    print(f"  dt_theo_thang: {r['dt_theo_thang']}")
    print(f"  dt_theo_quy  : {r['dt_theo_quy']}")
else:
    print("""
  dt_theo_thang: {'T1': 7,000,000, 'T2': 3,000,000, 'T3': 4,500,000, 'T4': 7,000,000, 'T5': 6,000,000}
  dt_theo_quy  : {'Q1': 14,500,000, 'Q2': 13,000,000}
""")


# ─── 2.15 So sánh cùng kỳ năm trước ─────────────────────────────────────────
subheader("2.15 So sánh cùng kỳ năm trước — tang_truong")

if ENGINE_AVAILABLE:
    engine = FormulaEngine(
        formulas=[
            {'name': 'dt_q1_nay',
             'formula': 'sum(r["dt"] for r in ds_hd if in_time_bucket(r["ngay"], time_buckets(nam_nay,   "quarter")[0]))'},
            {'name': 'dt_q1_truoc',
             'formula': 'sum(r["dt"] for r in ds_hd if in_time_bucket(r["ngay"], time_buckets(nam_truoc, "quarter")[0]))'},
            {'name': 'tang_truong',
             'formula': 'safe_div(dt_q1_nay - dt_q1_truoc, dt_q1_truoc) * 100'},
        ],
        deterministic=False,
    )
    r = engine.calculate({
        'nam_nay': 2025, 'nam_truoc': 2024,
        'ds_hd': [
            {'ngay': '2024-01-15', 'dt': 10_000_000},
            {'ngay': '2024-02-20', 'dt':  5_000_000},
            {'ngay': '2024-07-05', 'dt':  8_000_000},
            {'ngay': '2025-01-10', 'dt': 18_000_000},
            {'ngay': '2025-03-30', 'dt':  7_000_000},
        ],
    })
    print(f"  Q1/2025    : {r['dt_q1_nay']:>15,.0f}")
    print(f"  Q1/2024    : {r['dt_q1_truoc']:>15,.0f}")
    print(f"  Tăng trưởng: {r['tang_truong']:>14.1f}%")
else:
    print("""
  Q1/2025    :      25,000,000
  Q1/2024    :      15,000,000
  Tăng trưởng:            66.7%
""")


# ─── 2.16 Tuần ISO và tuần US ────────────────────────────────────────────────
subheader("2.16 Tuần ISO và tuần US — week_start='sunday'")

if ENGINE_AVAILABLE:
    b_iso = generate_time_buckets(2025, types=['week'])
    b_us  = generate_time_buckets(2025, types=['week'], week_start='sunday')

    print(f"  ISO (Thứ Hai → CN), {len(b_iso['weeks'])} tuần:")
    for w in b_iso['weeks'][:4]:
        print(f"    {w.label}: {w.from_date} → {w.to_date}")

    print(f"\n  US  (Chủ Nhật → Thứ Bảy), {len(b_us['weeks'])} tuần:")
    for w in b_us['weeks'][:4]:
        print(f"    {w.label}: {w.from_date} → {w.to_date}")
else:
    print("""
  ISO (mặc định): Thứ Hai → Chủ Nhật
    Tuần 1/2025: 2024-12-30 → 2025-01-05  ← bắt đầu 30/12/2024
    Tuần 2/2025: 2025-01-06 → 2025-01-12
    2025 có 53 tuần ISO

  US (week_start='sunday'): Chủ Nhật → Thứ Bảy
    Tuần 1/2025: 2024-12-29 → 2025-01-04
""")


# ─── 2.17 UI Dropdown / API JSON / Export CSV ────────────────────────────────
subheader("2.17 UI Dropdown / API JSON / Export CSV")

if ENGINE_AVAILABLE:
    import json, csv, io

    # UI Dropdown
    flat = generate_time_buckets_flat(2025, types=['quarter', 'month'])
    dropdown = [
        {"value": bk.label, "label": bk.label, "from": bk.from_date, "to": bk.to_date}
        for bk in flat
    ]
    print("  UI Dropdown (4 option đầu):")
    for opt in dropdown[:4]:
        print(f"    {opt}")

    # JSON API
    flat_dict = generate_time_buckets_flat(2025, types=['quarter'], as_dict=True)
    json_str = json.dumps(flat_dict, ensure_ascii=False)
    print(f"\n  JSON API: {json_str[:100]}...")

    # Export CSV
    flat_csv = generate_time_buckets_flat(
        2025, types=['quarter', 'month'],
        label_format='Y', as_dict=True,
    )
    # buf = io.StringIO()
    # w = csv.DictWriter(buf, fieldnames=['type','label','from_date','to_date','year','index'])
    # w.writeheader()
    # w.writerows(flat_csv)
    # print("\n  CSV (5 dòng đầu):")
    # for line in buf.getvalue().split('\n')[:6]:
    #     if line: print(f"    {line}")
else:
    print("""
  # UI Dropdown
  [{"value":"Q1","label":"Q1","from":"2025-01-01","to":"2025-03-31"}, ...]

  # JSON API
  json.dumps(generate_time_buckets_flat(2025, as_dict=True))

  # CSV
  type,label,from_date,to_date,year,index
  quarter,Q1/2025,2025-01-01,2025-03-31,2025,1
  ...
""")


# ─── 2.18 Lọc hóa đơn theo kỳ user chọn ─────────────────────────────────────
subheader("2.18 Lọc hóa đơn theo kỳ user chọn — filter_array between")

if ENGINE_AVAILABLE:
    engine = FormulaEngine(
        formulas=[
            {'name': 'hd_trong_ky',
             'formula': 'filter_array(ds_hd, key="ngay", operator="between", lo=ky["from_date"], hi=ky["to_date"])'},
            {'name': 'tong_ky',
             'formula': 'sum(r["gia_tri"] for r in hd_trong_ky)'},
            {'name': 'so_hd',
             'formula': 'len(hd_trong_ky)'},
        ],
        deterministic=False,
    )
    ds_hd = [
        {'ngay': '2025-03-31', 'gia_tri': 1_000_000},
        {'ngay': '2025-04-01', 'gia_tri': 5_000_000},
        {'ngay': '2025-05-15', 'gia_tri': 3_500_000},
        {'ngay': '2025-06-30', 'gia_tri': 2_000_000},
        {'ngay': '2025-07-01', 'gia_tri': 4_000_000},
    ]
    selected = get_period('quarter', 2, 2025)
    r = engine.calculate({'ky': selected.to_dict(), 'ds_hd': ds_hd})
    print(f"  Kỳ chọn   : {selected.label} ({selected.from_date} → {selected.to_date})")
    print(f"  Số hóa đơn: {r['so_hd']}")
    print(f"  Tổng Q2   : {r['tong_ky']:,.0f}")
else:
    print("""
  selected = get_period('quarter', 2, 2025)
  engine.calculate({'ky': selected.to_dict(), 'ds_hd': [...]})
  so_hd    = 3
  tong_ky  = 10,500,000
""")


# ─── 2.19 Báo cáo doanh thu đầy đủ ──────────────────────────────────────────
subheader("2.19 Thực tế: Báo cáo doanh thu theo Quý + Tháng + Tỷ lệ")

if ENGINE_AVAILABLE:
    import random
    random.seed(42)

    ds_hd = []
    for month in range(1, 13):
        for _ in range(random.randint(8, 20)):
            ds_hd.append({
                'ngay': f'2025-{month:02d}-{random.randint(1,28):02d}',
                'dt': random.randint(5_000_000, 80_000_000),
            })

    engine = FormulaEngine(
        formulas=[
            *[{'name': f'dt_q{i}',
               'formula': f'sum(r["dt"] for r in ds_hd if in_time_bucket(r["ngay"], time_buckets(2025, "quarter")[{i-1}]))'}
              for i in range(1, 5)],
            {'name': 'dt_h1', 'formula': 'dt_q1 + dt_q2'},
            {'name': 'dt_h2', 'formula': 'dt_q3 + dt_q4'},
            {'name': 'dt_nam','formula': 'dt_h1 + dt_h2'},
            *[{'name': f'pct_q{i}',
               'formula': f'safe_div(dt_q{i}, dt_nam) * 100'}
              for i in range(1, 5)],
        ],
        deterministic=False,
    )

    r = engine.calculate({'ds_hd': ds_hd})

    print(f"\n  {'':10s} {'Doanh thu':>18} {'Tỷ lệ':>8}")
    print(f"  {'-'*40}")
    for i in range(1, 5):
        print(f"  Q{i}         {r[f'dt_q{i}']:>18,.0f}  {r[f'pct_q{i}']:>7.1f}%")
    print(f"  {'-'*40}")
    print(f"  H1         {r['dt_h1']:>18,.0f}  {r['dt_h1']/r['dt_nam']*100:>7.1f}%")
    print(f"  H2         {r['dt_h2']:>18,.0f}  {r['dt_h2']/r['dt_nam']*100:>7.1f}%")
    print(f"  {'-'*40}")
    print(f"  Cả năm    {r['dt_nam']:>18,.0f}  {'100.0':>7}%")
else:
    print("""
               Doanh thu        Tỷ lệ
  ──────────────────────────────────────
  Q1          287,000,000      23.2%
  Q2          312,000,000      25.3%
  Q3          345,000,000      28.0%
  Q4          290,000,000      23.5%
  H1          599,000,000      48.5%
  H2          635,000,000      51.5%
  Cả năm    1,234,000,000     100.0%
""")


# ══════════════════════════════════════════════════════════════════════════════
#  PHẦN 3 — KẾT HỢP ALLOCATION + TIME BUCKET
# ══════════════════════════════════════════════════════════════════════════════

header("PHẦN 3 — KẾT HỢP ALLOCATION + TIME BUCKET")

# ─── 3.1 Phân bổ chi phí theo kỳ + bộ phận ───────────────────────────────────
subheader("3.1 Phân bổ chi phí lương theo kỳ vào từng bộ phận (qty + group_key)")

if ENGINE_AVAILABLE:
    import random

    bo_phan = [
        {'id': 'BP_KD1', 'qty': 15, 'dept': 'KD'},
        {'id': 'BP_KD2', 'qty': 10, 'dept': 'KD'},
        {'id': 'BP_IT1', 'qty': 12, 'dept': 'IT'},
        {'id': 'BP_IT2', 'qty':  8, 'dept': 'IT'},
        {'id': 'BP_HC1', 'qty': 20, 'dept': 'HC'},
    ]

    for quy_idx in range(1, 5):
        ky = get_period('quarter', quy_idx, 2025)
        random.seed(quy_idx * 7)
        chi_phi = [
            {'id': f'LUONG_KD_Q{quy_idx}', 'amount': random.randint(60, 90) * 1_000_000, 'dept': 'KD'},
            {'id': f'LUONG_IT_Q{quy_idx}', 'amount': random.randint(40, 60) * 1_000_000, 'dept': 'IT'},
            {'id': f'LUONG_HC_Q{quy_idx}', 'amount': random.randint(20, 35) * 1_000_000, 'dept': 'HC'},
        ]
        result = allocate(chi_phi, bo_phan, method='qty', group_key='dept')
        tong = sum(s['amount'] for s in chi_phi)
        print(f"\n  {ky.label}/{ky.year}  ({ky.from_date} → {ky.to_date})  Tổng: {tong:,.0f}")
        print_lines(result)
else:
    print("""
  Cho mỗi quý Q1→Q4:
    chi_phi = lấy từ DB theo kỳ (from_date, to_date)
    result = allocate(chi_phi, bo_phan, method='qty', group_key='dept')
    → KD chi phí → BP_KD1, BP_KD2  (theo tỷ lệ qty)
    → IT chi phí → BP_IT1, BP_IT2
    → HC chi phí → BP_HC1
""")


# ─── 3.2 So sánh phân bổ Q1 vs Q2 ───────────────────────────────────────────
subheader("3.2 So sánh phân bổ Q1 vs Q2 — bảng delta")

if ENGINE_AVAILABLE:
    sources_q1 = [{'id': 'LUONG_Q1', 'amount': 180_000_000}]
    sources_q2 = [{'id': 'LUONG_Q2', 'amount': 210_000_000}]
    targets = [
        {'id': 'BP_KD',  'qty': 50},
        {'id': 'BP_IT',  'qty': 30},
        {'id': 'BP_SX',  'qty': 80},
        {'id': 'BP_HC',  'qty': 20},
    ]

    r_q1 = allocate(sources_q1, targets, 'qty')
    r_q2 = allocate(sources_q2, targets, 'qty')

    print(f"\n  {'Bộ phận':<10} {'Q1':>16} {'Q2':>16} {'Chênh lệch':>16} {'%':>8}")
    print(f"  {'─'*58}")
    for bp in targets:
        bid  = bp['id']
        v1   = r_q1.target_totals.get(bid, 0)
        v2   = r_q2.target_totals.get(bid, 0)
        diff = v2 - v1
        pct  = (diff / v1 * 100) if v1 else 0
        print(f"  {bid:<10} {v1:>16,.0f} {v2:>16,.0f} {diff:>+16,.0f} {pct:>7.1f}%")

    print(f"  {'─'*58}")
    t1 = sum(r_q1.target_totals.values())
    t2 = sum(r_q2.target_totals.values())
    print(f"  {'TỔNG':<10} {t1:>16,.0f} {t2:>16,.0f} {t2-t1:>+16,.0f} {(t2-t1)/t1*100:>7.1f}%")
else:
    print("""
  Bộ phận            Q1              Q2     Chênh lệch       %
  ────────────────────────────────────────────────────────────
  BP_KD      50,000,000      58,333,333    +8,333,333      16.7%
  BP_IT      30,000,000      35,000,000    +5,000,000      16.7%
  BP_SX      80,000,000      93,333,333   +13,333,333      16.7%
  BP_HC      20,000,000      23,333,333    +3,333,333      16.7%
  ────────────────────────────────────────────────────────────
  TỔNG      180,000,000     210,000,000   +30,000,000      16.7%
""")


# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{SEP2}")
print(f"  ✅  Hoàn thành toàn bộ ví dụ  |  Engine available: {ENGINE_AVAILABLE}")
print(SEP2)
