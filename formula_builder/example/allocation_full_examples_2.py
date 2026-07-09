"""
==============================================================================
  Allocation Engine — Ví dụ toàn diện từ A đến Z
  engine_v21  ·  Pure Python  ·  Zero dependencies
==============================================================================

  MỤC LỤC
  ─────────────────────────────────────────────────────────────────────────
   1  · equal          Chia đều
   2  · qty            Theo số lượng
   3  · amount         Theo doanh thu
   4  · weight         Theo trọng số tự đặt (m², điểm, ...)
   5  · pct            % kế toán cố định  (auto-normalize nếu ≠ 100)
   6  · manual_amount  Nhập tay số tiền từng dòng
   7  · manual_pct     % nhập tay từng dòng
   8  · mixed          Kết hợp manual + tự động  (4 residual method)
   9  · group_key      Phân bổ theo nhóm (dept / project / loại, ...)
  10  · Nhiều nguồn × nhiều đích  (Cartesian + tách nhóm thủ công)
  11  · Custom field keys   (schema DB khác tên mặc định)
  12  · Rounding policies   (last / largest / none)
  13  · Tất cả dạng kết quả (lines / totals / group / flat / print / JSON)
  14  · Warnings & unallocated  (kiểm tra & xử lý lỗi)
  15  · FormulaEngine   (engine.allocate + built-in allocate() trong formula)
  16  · Tình huống thực tế — chi phí sản xuất tháng 10
==============================================================================
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine_v24 import allocate, FormulaEngine

# ─── helpers in đẹp ──────────────────────────────────────────────────────────
W = 72
def title(s):   print(f"\n{'═'*W}\n  {s}\n{'═'*W}")
def section(s): print(f"\n{'─'*W}\n  {s}\n{'─'*W}")
def ok(label, val=None):
    if val is None: print(f"  ✓  {label}")
    else:           print(f"  ✓  {label:45s} = {val}")


# ══════════════════════════════════════════════════════════════════════════════
title("1 · EQUAL — Chia đều cho tất cả đích")
# ══════════════════════════════════════════════════════════════════════════════

sources = [{'id': 'CP001', 'amount': 120_000_000, 'ten': 'Chi phí điện'}]
targets = [{'id': 'BP01', 'ten': 'Kinh doanh'},
           {'id': 'BP02', 'ten': 'Sản xuất'},
           {'id': 'BP03', 'ten': 'Hành chính'}]

r = allocate(sources, targets, 'equal')
r.print_by_source(sources, label_key='ten')
ok("source_totals", r.source_totals)
ok("target_totals", r.target_totals)
ok("unallocated  ", r.unallocated)
ok("ok           ", r.ok)


# ══════════════════════════════════════════════════════════════════════════════
title("2 · QTY — Theo số lượng sản xuất")
# ══════════════════════════════════════════════════════════════════════════════

sources = [{'id': 'CP001', 'amount': 120_000_000, 'ten': 'Khấu hao máy'}]
targets = [{'id': 'SP_A', 'qty': 100, 'ten': 'Sản phẩm A'},
           {'id': 'SP_B', 'qty': 250, 'ten': 'Sản phẩm B'},
           {'id': 'SP_C', 'qty':  50, 'ten': 'Sản phẩm C'}]

r = allocate(sources, targets, 'qty')
r.print_by_source(sources, label_key='ten')
r.print_by_target(targets, label_key='ten')
g = r.group_by_source(sources)
ok("SP_A nhận", f"{g['CP001']['allocated_to'][0]['allocated']:,.2f}")
ok("SP_A tỷ lệ", f"{g['CP001']['allocated_to'][0]['ratio']:.2%}")


# ══════════════════════════════════════════════════════════════════════════════
title("3 · AMOUNT — Theo tỷ lệ doanh thu")
# ══════════════════════════════════════════════════════════════════════════════

sources = [{'id': 'CP_QC', 'amount': 48_000_000, 'ten': 'Chi phí quảng cáo'}]
targets = [{'id': 'KV_MB', 'amount':  800_000_000, 'ten': 'Miền Bắc'},
           {'id': 'KV_MT', 'amount':  300_000_000, 'ten': 'Miền Trung'},
           {'id': 'KV_MN', 'amount': 1_100_000_000, 'ten': 'Miền Nam'}]

r = allocate(sources, targets, 'amount')
r.print_by_source(sources, label_key='ten')
section("Chiều đích nhận")
r.print_by_target(targets, label_key='ten')


# ══════════════════════════════════════════════════════════════════════════════
title("4 · WEIGHT — Theo trọng số tự đặt (diện tích, điểm KPI, ...)")
# ══════════════════════════════════════════════════════════════════════════════

sources = [{'id': 'CP_VS', 'amount': 18_000_000, 'ten': 'Chi phí vệ sinh'}]
targets = [{'id': 'T01', 'alloc_weight': 500,  'ten': 'Tầng 1 — 500m²'},
           {'id': 'T02', 'alloc_weight': 300,  'ten': 'Tầng 2 — 300m²'},
           {'id': 'T03', 'alloc_weight': 200,  'ten': 'Tầng 3 — 200m²'}]

r = allocate(sources, targets, 'weight')
r.print_by_source(sources, label_key='ten')
ok("T01 tỷ lệ", f"{r.group_by_source()['CP_VS']['allocated_to'][0]['ratio']:.2%}")


# ══════════════════════════════════════════════════════════════════════════════
title("5 · PCT — % kế toán cố định")
# ══════════════════════════════════════════════════════════════════════════════

sources = [{'id': 'CP_QT', 'amount': 60_000_000, 'ten': 'Chi phí quản trị'}]
targets = [{'id': 'BD_KD', 'alloc_pct': 50, 'ten': 'Kinh doanh'},
           {'id': 'BD_SX', 'alloc_pct': 30, 'ten': 'Sản xuất'},
           {'id': 'BD_HC', 'alloc_pct': 20, 'ten': 'Hành chính'}]

r = allocate(sources, targets, 'pct')
r.print_by_source(sources, label_key='ten')
ok("warnings (tổng=100, sạch)", r.warnings)

section("Tổng pct ≠ 100 → engine tự normalize + ghi warning")
targets_bad = [{'id': 'X1', 'alloc_pct': 40, 'ten': 'X1'},
               {'id': 'X2', 'alloc_pct': 40, 'ten': 'X2'}]
r2 = allocate(sources, targets_bad, 'pct')
r2.print_by_source(sources, label_key='ten')
ok("warnings (normalize)", r2.warnings)


# ══════════════════════════════════════════════════════════════════════════════
title("6 · MANUAL_AMOUNT — Nhập tay số tiền từng dòng đích")
# ══════════════════════════════════════════════════════════════════════════════

sources = [{'id': 'CP001', 'amount': 120_000_000, 'ten': 'Chi phí nhân sự'}]
targets = [{'id': 'BP01', 'alloc_amount': 50_000_000, 'ten': 'Kinh doanh'},
           {'id': 'BP02', 'alloc_amount': 45_000_000, 'ten': 'Sản xuất'},
           {'id': 'BP03', 'alloc_amount': 25_000_000, 'ten': 'Hành chính'}]

r = allocate(sources, targets, 'manual_amount')
r.print_by_source(sources, label_key='ten')
ok("unallocated (tổng bằng source)", r.unallocated)

section("Tổng manual < source → unallocated dương (còn dư)")
r3 = allocate(sources,
              [{'id': 'BP01', 'alloc_amount': 50_000_000},
               {'id': 'BP02', 'alloc_amount': 40_000_000}],
              'manual_amount')
ok("unallocated còn dư 30M", r3.unallocated)

section("Tổng manual > source → unallocated âm (thâm hụt)")
r4 = allocate(sources,
              [{'id': 'BP01', 'alloc_amount': 80_000_000},
               {'id': 'BP02', 'alloc_amount': 60_000_000}],
              'manual_amount')
ok("unallocated thâm hụt 20M", r4.unallocated)


# ══════════════════════════════════════════════════════════════════════════════
title("7 · MANUAL_PCT — % nhập tay từng dòng đích")
# ══════════════════════════════════════════════════════════════════════════════

sources = [{'id': 'LN001', 'amount': 120_000_000, 'ten': 'Lợi nhuận phân phối'}]
targets = [{'id': 'QUY_A', 'manual_pct': 60, 'ten': 'Quỹ đầu tư'},
           {'id': 'QUY_B', 'manual_pct': 25, 'ten': 'Quỹ dự phòng'},
           {'id': 'QUY_C', 'manual_pct': 15, 'ten': 'Quỹ phúc lợi'}]

r = allocate(sources, targets, 'manual_pct')
r.print_by_source(sources, label_key='ten')
ok("unallocated (100% đã chia)", r.unallocated)


# ══════════════════════════════════════════════════════════════════════════════
title("8 · MIXED — Kết hợp manual + tự động chia phần còn lại")
# ══════════════════════════════════════════════════════════════════════════════
# Ưu tiên: alloc_amount > manual_pct > residual
# meta trả về: {'mixed_stage': 'manual'} hoặc {'mixed_stage': 'residual', 'residual_amount': X}

sources = [{'id': 'CP001', 'amount': 120_000_000, 'ten': 'Chi phí chung'}]

section("8a · residual = 'qty'")
targets_a = [
    {'id': 'BP01', 'ten': 'KD', 'alloc_amount': 30_000_000, 'qty': 100},
    {'id': 'BP02', 'ten': 'IT', 'manual_pct': 20,           'qty': 200},
    {'id': 'BP03', 'ten': 'SX', 'qty': 150},
    {'id': 'BP04', 'ten': 'HC', 'qty':  50},
]
r_a = allocate(sources, targets_a, method='mixed', mixed_residual_method='qty')
r_a.print_by_source(sources, label_key='ten')
lines = r_a.group_by_source(sources)['CP001']['allocated_to']
ok("Tổng manual  (30M+24M)", f"{sum(x['allocated'] for x in lines if 'manual' in x['method']):,.0f}")
ok("Tổng residual (66M)   ", f"{sum(x['allocated'] for x in lines if 'manual' not in x['method']):,.0f}")

section("8b · residual = 'amount'")
targets_b = [
    {'id': 'K01', 'ten': 'Online',   'alloc_amount': 20_000_000, 'amount': 500_000_000},
    {'id': 'K02', 'ten': 'Offline',  'manual_pct': 10,           'amount': 300_000_000},
    {'id': 'K03', 'ten': 'Đại lý',   'amount': 400_000_000},
    {'id': 'K04', 'ten': 'Xuất khẩu','amount': 100_000_000},
]
r_b = allocate(sources, targets_b, method='mixed', mixed_residual_method='amount')
r_b.print_by_source(sources, label_key='ten')

section("8c · residual = 'equal'")
targets_c = [
    {'id': 'D01', 'ten': 'Dự án cố định', 'alloc_amount': 24_000_000},
    {'id': 'D02', 'ten': 'Dự án A'},
    {'id': 'D03', 'ten': 'Dự án B'},
    {'id': 'D04', 'ten': 'Dự án C'},
]
r_c = allocate(sources, targets_c, method='mixed', mixed_residual_method='equal')
r_c.print_by_source(sources, label_key='ten')

section("8d · residual = 'weight'")
targets_d = [
    {'id': 'P01', 'ten': 'Phòng A', 'manual_pct': 15, 'alloc_weight': 3.0},
    {'id': 'P02', 'ten': 'Phòng B',                   'alloc_weight': 3.0},
    {'id': 'P03', 'ten': 'Phòng C',                   'alloc_weight': 2.0},
    {'id': 'P04', 'ten': 'Phòng D',                   'alloc_weight': 1.0},
]
r_d = allocate(sources, targets_d, method='mixed', mixed_residual_method='weight')
r_d.print_by_source(sources, label_key='ten')


# ══════════════════════════════════════════════════════════════════════════════
title("9 · GROUP_KEY — Phân bổ theo nhóm (dept / project / loại, ...)")
# ══════════════════════════════════════════════════════════════════════════════

sources = [
    {'id': 'LUONG_KD', 'amount': 120_000_000, 'dept': 'KD', 'ten': 'Lương Kinh doanh'},
    {'id': 'LUONG_IT', 'amount':  60_000_000, 'dept': 'IT', 'ten': 'Lương IT'},
    {'id': 'LUONG_HC', 'amount':  30_000_000, 'dept': 'HC', 'ten': 'Lương Hành chính'},
]
targets = [
    {'id': 'KD_N1', 'qty': 100, 'dept': 'KD', 'ten': 'KD nhóm 1'},
    {'id': 'KD_N2', 'qty': 200, 'dept': 'KD', 'ten': 'KD nhóm 2'},
    {'id': 'IT_N1', 'qty':  80, 'dept': 'IT', 'ten': 'IT nhóm 1'},
    {'id': 'IT_N2', 'qty': 120, 'dept': 'IT', 'ten': 'IT nhóm 2'},
    {'id': 'HC_N1', 'qty':   1, 'dept': 'HC', 'ten': 'HC (toàn bộ)'},
]

r = allocate(sources, targets, 'qty', group_key='dept')
r.print_by_source(sources, label_key='ten')
section("Chiều đích — từng nhóm nhận từ nguồn nào")
r.print_by_target(targets, label_key='ten')
ok("source_totals", r.source_totals)
ok("target_totals", r.target_totals)


# ══════════════════════════════════════════════════════════════════════════════
title("10 · NHIỀU NGUỒN × NHIỀU ĐÍCH")
# ══════════════════════════════════════════════════════════════════════════════

section("10a · 3 nguồn × 3 đích = 9 dòng (Cartesian)")
sources = [
    {'id': 'CP_DIEN', 'amount': 24_000_000, 'ten': 'Tiền điện'},
    {'id': 'CP_NUOC', 'amount':  6_000_000, 'ten': 'Tiền nước'},
    {'id': 'CP_MANG', 'amount': 3_600_000, 'ten': 'Internet'},
]
targets = [
    {'id': 'BP01', 'amount': 500_000_000, 'ten': 'Kinh doanh'},
    {'id': 'BP02', 'amount': 800_000_000, 'ten': 'Sản xuất'},
    {'id': 'BP03', 'amount': 200_000_000, 'ten': 'Hành chính'},
]
r = allocate(sources, targets, 'amount')
ok(f"Tổng dòng phân bổ", f"{len(r.lines)} dòng  (3 nguồn × 3 đích)")
r.print_by_source(sources, label_key='ten')

section("to_flat_rows → bảng phẳng cho DataFrame / Excel / CSV")
rows = r.to_flat_rows(ratio_as_pct=True)
print(f"  {'source_id':12} {'target_id':8} {'allocated':>16} {'ratio%':>8} {'method'}")
print(f"  {'─'*12} {'─'*8} {'─'*16} {'─'*8} {'─'*8}")
for row in rows:
    print(f"  {row['source_id']:12} {row['target_id']:8} {row['allocated']:>16,.2f}"
          f" {row['ratio']:>8.4f} {row['method']}")

section("10b · 2 nhóm thủ công — VP dùng amount, NM dùng qty")
r_vp = allocate(
    [{'id': 'CP_DIEN', 'amount': 24_000_000}, {'id': 'CP_NUOC', 'amount': 6_000_000}],
    [{'id': 'KD', 'amount': 500_000_000}, {'id': 'HC', 'amount': 100_000_000}],
    'amount'
)
r_nm = allocate(
    [{'id': 'CP_MB', 'amount': 60_000_000}, {'id': 'CP_BHTB', 'amount': 18_000_000}],
    [{'id': 'SX1', 'qty': 600}, {'id': 'SX2', 'qty': 400}],
    'qty'
)
print("\n  [Nhóm VP — theo doanh thu]")
r_vp.print_by_source()
print("\n  [Nhóm NM — theo số lượng]")
r_nm.print_by_source()


# ══════════════════════════════════════════════════════════════════════════════
title("11 · CUSTOM FIELD KEYS — Schema DB khác tên mặc định")
# ══════════════════════════════════════════════════════════════════════════════

sources = [
    {'ma_ct': 'HD001', 'gia_tri': 90_000_000, 'ten_ct': 'Hóa đơn điện T10'},
    {'ma_ct': 'HD002', 'gia_tri': 30_000_000, 'ten_ct': 'Hóa đơn nước T10'},
]
targets = [
    {'ma_bp': 'P_KD', 'so_luong': 300, 'ten_bp': 'Kinh doanh'},
    {'ma_bp': 'P_SX', 'so_luong': 500, 'ten_bp': 'Sản xuất'},
    {'ma_bp': 'P_HC', 'so_luong': 200, 'ten_bp': 'Hành chính'},
]

r = allocate(
    sources, targets, 'qty',
    source_id_key     = 'ma_ct',
    source_amount_key = 'gia_tri',
    target_id_key     = 'ma_bp',
    target_qty_key    = 'so_luong',
)

r.print_by_source(sources, source_id_key='ma_ct', label_key='ten_ct')
r.print_by_target(targets, target_id_key='ma_bp', label_key='ten_bp')

g_src = r.group_by_source(sources, source_id_key='ma_ct')
g_tgt = r.group_by_target(targets, target_id_key='ma_bp')
ok("HD001 allocated_total", f"{g_src['HD001']['allocated_total']:,.0f}")
ok("P_KD  received_total ", f"{g_tgt['P_KD']['received_total']:,.0f}")

sd = r.to_sources_detail(sources, source_id_key='ma_ct')
fd = r.to_full_dict(sources, targets, source_id_key='ma_ct', target_id_key='ma_bp')
ok("to_sources_detail keys[0]", list(sd[0].keys()))
ok("to_full_dict keys",         list(fd.keys()))


# ══════════════════════════════════════════════════════════════════════════════
title("12 · ROUNDING POLICIES — last / largest / none")
# ══════════════════════════════════════════════════════════════════════════════

sources_r = [{'id': 'S', 'amount': 100}]
targets_r  = [{'id': 'A'}, {'id': 'B'}, {'id': 'C'}]

section("last (mặc định) — phần dư vào dòng CUỐI")
r_last = allocate(sources_r, targets_r, 'equal', rounding_policy='last')
for ln in r_last.lines:
    print(f"    {ln.target_id}: {ln.allocated}")
ok("Tổng = 100", sum(ln.allocated for ln in r_last.lines))

section("largest — phần dư vào dòng GIÁ TRỊ LỚN NHẤT")
r_largest = allocate(sources_r, targets_r, 'equal', rounding_policy='largest')
for ln in r_largest.lines:
    marker = '  ← dư' if ln.allocated == 33.34 else ''
    print(f"    {ln.target_id}: {ln.allocated}{marker}")
ok("Tổng = 100", sum(ln.allocated for ln in r_largest.lines))

section("none — giữ số thực, round_digits=8")
r_none = allocate(sources_r, targets_r, 'equal', rounding_policy='none', round_digits=8)
for ln in r_none.lines:
    print(f"    {ln.target_id}: {ln.allocated}")


# ══════════════════════════════════════════════════════════════════════════════
title("13 · TẤT CẢ DẠNG KẾT QUẢ — Chọn đúng dạng cho từng nhu cầu")
# ══════════════════════════════════════════════════════════════════════════════

sources = [
    {'id': 'CP001', 'amount': 120_000_000, 'ten': 'Chi phí nhân sự'},
    {'id': 'CP002', 'amount':  60_000_000, 'ten': 'Chi phí vận hành'},
]
targets = [
    {'id': 'BP01', 'qty': 100, 'ten': 'Kinh doanh'},
    {'id': 'BP02', 'qty': 200, 'ten': 'Sản xuất'},
    {'id': 'BP03', 'qty':  50, 'ten': 'Hành chính'},
]
r = allocate(sources, targets, 'qty')

# ── 13.1  lines ───────────────────────────────────────────────────────────────
section("13.1 · result.lines — flat list AllocationLine (thuần túy nhất)")
print(f"  {len(r.lines)} dòng:")
for ln in r.lines:
    print(f"    {ln.source_id} → {ln.target_id}:"
          f"  {ln.allocated:>14,.2f}"
          f"  ratio={ln.ratio:.4f}  method={ln.method}"
          f"  weight={ln.weight:.0f}  meta={ln.meta}")
ok("lines[0].to_dict()", r.lines[0].to_dict())

# ── 13.2  totals ──────────────────────────────────────────────────────────────
section("13.2 · source_totals / target_totals / unallocated (lược bỏ nhất)")
ok("source_totals", r.source_totals)
ok("target_totals", r.target_totals)
ok("unallocated  ", r.unallocated)
ok("ok           ", r.ok)

# ── 13.3  summary ─────────────────────────────────────────────────────────────
section("13.3 · result.summary() — text human-readable (log / debug)")
print(r.summary())

# ── 13.4  to_dict ─────────────────────────────────────────────────────────────
section("13.4 · result.to_dict() — flat dict / JSON / API response")
d = r.to_dict()
ok("keys   ", list(d.keys()))
ok("lines[0]", d['lines'][0])
ok("JSON size", f"{len(json.dumps(d, ensure_ascii=False)):,} ký tự")

# ── 13.5  group_by_source ─────────────────────────────────────────────────────
section("13.5 · result.group_by_source() — {source_id: {…, allocated_to:[…]}}")
g = r.group_by_source(sources)
for sid, row in g.items():
    print(f"\n  [{sid}]  {row.get('ten','')}  allocated_total={row['allocated_total']:,.0f}  unallocated={row['unallocated']}")
    for item in row['allocated_to']:
        print(f"    → {item['target_id']:8}  {item['allocated']:>14,.2f}"
              f"  ({item['ratio']:.2%})  [{item['method']}]  weight={item['weight']:.0f}")

# ── 13.6  group_by_source totals_only ─────────────────────────────────────────
section("13.6 · group_by_source(include_totals_only=True) — chỉ tổng")
g2 = r.group_by_source(sources, include_totals_only=True)
for sid, row in g2.items():
    print(f"  {sid}: {row}")

# ── 13.7  group_by_target ─────────────────────────────────────────────────────
section("13.7 · result.group_by_target() — {target_id: {…, received_from:[…]}}")
g3 = r.group_by_target(targets)
for tid, row in g3.items():
    print(f"\n  [{tid}]  {row.get('ten','')}  received_total={row['received_total']:,.0f}")
    for item in row['received_from']:
        print(f"    ← {item['source_id']:8}  {item['allocated']:>14,.2f}"
              f"  ({item['ratio']:.2%})  [{item['method']}]")

# ── 13.8  group_by_target totals_only ─────────────────────────────────────────
section("13.8 · group_by_target(include_totals_only=True) — chỉ tổng")
g4 = r.group_by_target(targets, include_totals_only=True)
for tid, row in g4.items():
    print(f"  {tid}: {row}")

# ── 13.9  to_sources_detail ───────────────────────────────────────────────────
section("13.9 · result.to_sources_detail() — List nguồn enriched (giữ thứ tự)")
for row in r.to_sources_detail(sources):
    print(f"  {row['id']} | {row['ten']} | allocated_total={row['allocated_total']:,.0f}"
          f" | allocated_to→{[x['target_id'] for x in row['allocated_to']]}")

# ── 13.10  to_targets_detail ──────────────────────────────────────────────────
section("13.10 · result.to_targets_detail() — List đích enriched (giữ thứ tự)")
for row in r.to_targets_detail(targets):
    print(f"  {row['id']} | {row['ten']} | received_total={row['received_total']:,.0f}"
          f" | received_from←{[x['source_id'] for x in row['received_from']]}")

# ── 13.11  to_full_dict ───────────────────────────────────────────────────────
section("13.11 · result.to_full_dict() — Tất cả trong 1 (API / snapshot / audit)")
fd = r.to_full_dict(sources, targets)
ok("keys", list(fd.keys()))
ok("sources[0] allocated_total", fd['sources'][0]['allocated_total'])
ok("targets[0] received_total ", fd['targets'][0]['received_total'])
ok("JSON size", f"{len(json.dumps(fd, ensure_ascii=False)):,} ký tự")

# ── 13.12  to_flat_rows ───────────────────────────────────────────────────────
section("13.12 · result.to_flat_rows() — List phẳng cho pandas / Excel / CSV")
rows = r.to_flat_rows()
ok("Số dòng", len(rows))
ok("row[0] ratio 0→1 ", rows[0])
rows_pct = r.to_flat_rows(ratio_as_pct=True)
ok("row[0] ratio 0→100", rows_pct[0]['ratio'])

# ── 13.13  print_by_source / print_by_target ──────────────────────────────────
section("13.13 · print_by_source() / print_by_target() — In ra stdout")
r.print_by_source(sources, label_key='ten')
r.print_by_target(targets, label_key='ten')

section("13.14 · print không cần truyền sources / targets")
r.print_by_source()
r.print_by_target()


# ══════════════════════════════════════════════════════════════════════════════
title("14 · WARNINGS & UNALLOCATED — Kiểm tra và xử lý lỗi")
# ══════════════════════════════════════════════════════════════════════════════

section("14.1 · group_key không khớp → ok=False, warning, unallocated dương")
r_warn = allocate(
    [{'id': 'CP_X', 'amount': 50_000_000, 'dept': 'X'}],
    [{'id': 'BP_A', 'qty': 100,           'dept': 'A'}],
    'qty', group_key='dept',
)
ok("ok         ", r_warn.ok)
ok("warnings   ", r_warn.warnings)
ok("unallocated", r_warn.unallocated)

section("14.2 · pct normalize → ok=True nhưng có warning")
r_pct = allocate(
    [{'id': 'CP001', 'amount': 60_000_000}],
    [{'id': 'X1', 'alloc_pct': 40}, {'id': 'X2', 'alloc_pct': 40}],
    'pct',
)
ok("ok         ", r_pct.ok)
ok("warnings   ", r_pct.warnings)

section("14.3 · manual_amount thâm hụt → unallocated âm")
r_over = allocate(
    [{'id': 'CP001', 'amount': 100_000_000}],
    [{'id': 'BP01', 'alloc_amount': 80_000_000},
     {'id': 'BP02', 'alloc_amount': 50_000_000}],
    'manual_amount',
)
ok("unallocated (thâm hụt 30M)", r_over.unallocated)

section("14.4 · Pattern kiểm tra chuẩn sau mỗi lần phân bổ")
def check_result(r, label=""):
    print(f"\n  [{label}]")
    if not r.ok:
        print("    ⚠  result.ok = False — có lỗi nghiêm trọng")
    for sid, una in r.unallocated.items():
        if una > 0:   print(f"    ⚠  Nguồn {sid} còn dư    : {una:>14,.0f}")
        elif una < 0: print(f"    ⚠  Nguồn {sid} thâm hụt : {abs(una):>14,.0f}")
    for w in r.warnings:
        print(f"    ⚠  {w}")
    if r.ok and not any(v != 0 for v in r.unallocated.values()) and not r.warnings:
        print("    ✓  Phân bổ cân bằng hoàn toàn")

check_result(r,       "qty — bình thường")
check_result(r_warn,  "group_key không khớp")
check_result(r_pct,   "pct normalize")
check_result(r_over,  "manual_amount thâm hụt")


# ══════════════════════════════════════════════════════════════════════════════
title("15 · FORMULAENGINE — Tích hợp phân bổ vào công thức")
# ══════════════════════════════════════════════════════════════════════════════
"""
  (a) engine.allocate(sources, targets, method, **kwargs)
      → trả về AllocationResult (đầy đủ method: group_by_*, print_by_*, ...)

  (b) allocate(...) trong formula string
      → trả về dict = result.to_dict()
         keys: lines, source_totals, target_totals, unallocated, warnings, ok
         Mỗi item trong 'lines':
           {source_id, source_amount, target_id, allocated, ratio, method, weight, meta}
"""

section("15.1 · engine.allocate() — gọi trực tiếp, trả về AllocationResult")
engine = FormulaEngine(formulas=[], deterministic=False)
r_eng = engine.allocate(
    [{'id': 'CP001', 'amount': 120_000_000}],
    [{'id': 'BP01', 'qty': 100}, {'id': 'BP02', 'qty': 200}],
    'qty',
)
ok("type", type(r_eng).__name__)
ok("ok  ", r_eng.ok)
r_eng.print_by_source()

section("15.2 · allocate() built-in trong formula → dict (= result.to_dict())")
engine2 = FormulaEngine(
    formulas=[
        # Phân bổ — phan_bo là dict
        {'name': 'phan_bo',
         'formula': 'allocate(ds_cp, ds_bp, "qty")'},

        # Truy cập totals và ok
        {'name': 'source_totals',
         'formula': 'phan_bo["source_totals"]'},
        {'name': 'target_totals',
         'formula': 'phan_bo["target_totals"]'},
        {'name': 'pb_ok',
         'formula': 'phan_bo["ok"]'},

        # Lọc từ lines — mỗi l là dict {source_id, target_id, allocated, ratio, method, ...}
        {'name': 'bp01_nhan',
         'formula': 'sum(l["allocated"] for l in phan_bo["lines"] if l["target_id"] == "BP01")'},
        {'name': 'bp02_nhan',
         'formula': 'sum(l["allocated"] for l in phan_bo["lines"] if l["target_id"] == "BP02")'},
        {'name': 'ty_le_bp01',
         'formula': 'safe_div(bp01_nhan, bp01_nhan + bp02_nhan) * 100'},
        {'name': 'tong_allocated',
         'formula': 'sum(l["allocated"] for l in phan_bo["lines"])'},
        {'name': 'ratio_dong_dau',
         'formula': 'phan_bo["lines"][0]["ratio"]'},
    ],
    deterministic=False,
)
res = engine2.calculate({
    'ds_cp': [{'id': 'CP001', 'amount': 120_000_000}],
    'ds_bp': [{'id': 'BP01', 'qty': 100}, {'id': 'BP02', 'qty': 200}],
})
ok("pb_ok         ", res['pb_ok'])
ok("source_totals ", res['source_totals'])
ok("target_totals ", res['target_totals'])
ok("bp01_nhan     ", f"{res['bp01_nhan']:,.2f}")
ok("bp02_nhan     ", f"{res['bp02_nhan']:,.2f}")
ok("ty_le_bp01    ", f"{res['ty_le_bp01']:.2f}%")
ok("tong_allocated", f"{res['tong_allocated']:,.2f}  (= 120M ✓)")
ok("ratio_dong_dau", f"{res['ratio_dong_dau']:.4f}")

section("15.3 · mixed trong formula — lọc manual vs residual qua meta")
engine3 = FormulaEngine(
    formulas=[
        {'name': 'pb',
         'formula': 'allocate(ds_cp, ds_bp, "mixed", mixed_residual_method="qty")'},

        # Lọc dòng manual (method chứa 'manual')
        {'name': 'manual_lines',
         'formula': '[l for l in pb["lines"] if "manual" in l["method"]]'},
        {'name': 'tong_manual',
         'formula': 'sum(l["allocated"] for l in manual_lines)'},

        # Lọc dòng residual qua meta['mixed_stage']
        {'name': 'residual_lines',
         'formula': '[l for l in pb["lines"] if l["meta"].get("mixed_stage") == "residual"]'},
        {'name': 'tong_residual',
         'formula': 'sum(l["allocated"] for l in residual_lines)'},

        # Method từng dòng để audit
        {'name': 'method_moi_dong',
         'formula': '[(l["target_id"], l["method"]) for l in pb["lines"]]'},
    ],
    deterministic=False,
)
res2 = engine3.calculate({
    'ds_cp': [{'id': 'CP001', 'amount': 120_000_000}],
    'ds_bp': [
        {'id': 'BP01', 'alloc_amount': 30_000_000, 'qty': 100},
        {'id': 'BP02', 'manual_pct': 20,            'qty': 200},
        {'id': 'BP03', 'qty': 150},
    ],
})
ok("tong_manual   (30M+24M)", f"{res2['tong_manual']:,.0f}")
ok("tong_residual (66M)    ", f"{res2['tong_residual']:,.0f}")
ok("method_moi_dong", res2['method_moi_dong'])

section("15.4 · group_key trong formula")
engine4 = FormulaEngine(
    formulas=[
        {'name': 'pb',
         'formula': 'allocate(ds_cp, ds_bp, "qty", group_key="dept")'},
        {'name': 'pb_ok',
         'formula': 'pb["ok"]'},
        {'name': 'target_totals',
         'formula': 'pb["target_totals"]'},
        {'name': 'tong_kd',
         'formula': 'sum(l["allocated"] for l in pb["lines"] if "KD" in l["target_id"])'},
    ],
    deterministic=False,
)
res3 = engine4.calculate({
    'ds_cp': [
        {'id': 'L_KD', 'amount': 120_000_000, 'dept': 'KD'},
        {'id': 'L_IT', 'amount':  60_000_000, 'dept': 'IT'},
    ],
    'ds_bp': [
        {'id': 'KD_1', 'qty': 100, 'dept': 'KD'},
        {'id': 'KD_2', 'qty': 200, 'dept': 'KD'},
        {'id': 'IT_1', 'qty':  80, 'dept': 'IT'},
        {'id': 'IT_2', 'qty': 120, 'dept': 'IT'},
    ],
})
ok("pb_ok        ", res3['pb_ok'])
ok("target_totals", res3['target_totals'])
ok("tong_kd (=120M)", f"{res3['tong_kd']:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
title("16 · TÌNH HUỐNG THỰC TẾ — Chi phí sản xuất tháng 10")
# ══════════════════════════════════════════════════════════════════════════════

section("Bước 1 · Dữ liệu sản phẩm")
sp = [
    {'id': 'SP_A', 'ten': 'Sản phẩm A', 'qty': 500,  'amount': 800_000_000, 'gio_may': 200},
    {'id': 'SP_B', 'ten': 'Sản phẩm B', 'qty': 800,  'amount': 600_000_000, 'gio_may': 350},
    {'id': 'SP_C', 'ten': 'Sản phẩm C', 'qty': 300,  'amount': 400_000_000, 'gio_may': 150},
]
print(f"  {'SP':6} {'qty':>6} {'doanh thu':>18} {'giờ máy':>10}")
print("  " + "─"*44)
for s in sp:
    print(f"  {s['id']:6} {s['qty']:>6} {s['amount']:>18,.0f} {s['gio_may']:>10}")

section("Bước 2 · Phân bổ 6 khoản với 6 tiêu thức khác nhau")

# 1. Khấu hao máy → giờ máy (gán vào qty)
r_kh = allocate([{'id': 'KH_MAY', 'amount': 35_000_000, 'ten': 'Khấu hao máy'}],
                [{**s, 'qty': s['gio_may']} for s in sp], 'qty')
print("\n  [1] Khấu hao — theo giờ máy:")
r_kh.print_by_source([{'id': 'KH_MAY', 'amount': 35_000_000, 'ten': 'Khấu hao máy'}], label_key='ten')

# 2. Nhân công → số lượng SP
r_nc = allocate([{'id': 'NHAN_CONG', 'amount': 60_000_000, 'ten': 'Nhân công'}],
                sp, 'qty')
print("\n  [2] Nhân công — theo số lượng:")
r_nc.print_by_source([{'id': 'NHAN_CONG', 'amount': 60_000_000, 'ten': 'Nhân công'}], label_key='ten')

# 3. Điện nước → doanh thu
r_dn = allocate([{'id': 'DIEN_NUOC', 'amount': 12_000_000, 'ten': 'Điện nước'}],
                sp, 'amount')
print("\n  [3] Điện nước — theo doanh thu:")
r_dn.print_by_source([{'id': 'DIEN_NUOC', 'amount': 12_000_000, 'ten': 'Điện nước'}], label_key='ten')

# 4. Quản lý PX → % kế toán
r_ql = allocate([{'id': 'QL_PX', 'amount': 18_000_000, 'ten': 'Quản lý PX'}],
                [{**sp[0], 'alloc_pct': 45},
                 {**sp[1], 'alloc_pct': 35},
                 {**sp[2], 'alloc_pct': 20}], 'pct')
print("\n  [4] Quản lý PX — theo % kế toán:")
r_ql.print_by_source([{'id': 'QL_PX', 'amount': 18_000_000, 'ten': 'Quản lý PX'}], label_key='ten')

# 5. Vận chuyển → nhập tay
r_vc = allocate([{'id': 'VAN_CHUYEN', 'amount': 9_000_000, 'ten': 'Vận chuyển'}],
                [{**sp[0], 'alloc_amount': 4_500_000},
                 {**sp[1], 'alloc_amount': 3_000_000},
                 {**sp[2], 'alloc_amount': 1_500_000}], 'manual_amount')
print("\n  [5] Vận chuyển — nhập tay:")
r_vc.print_by_source([{'id': 'VAN_CHUYEN', 'amount': 9_000_000, 'ten': 'Vận chuyển'}], label_key='ten')

# 6. Chi phí đặc biệt → mixed
r_db = allocate([{'id': 'CP_DB', 'amount': 20_000_000, 'ten': 'Đặc biệt'}],
                [{**sp[0], 'alloc_amount': 8_000_000},
                 {**sp[1]}, {**sp[2]}],
                method='mixed', mixed_residual_method='qty')
print("\n  [6] Đặc biệt — mixed (SP_A cố định, còn lại theo qty):")
r_db.print_by_source([{'id': 'CP_DB', 'amount': 20_000_000, 'ten': 'Đặc biệt'}], label_key='ten')

section("Bước 3 · Bảng tổng hợp chi phí theo sản phẩm")
all_results = [r_kh, r_nc, r_dn, r_ql, r_vc, r_db]
ten_chi_phi = ['Khấu hao', 'Nhân công', 'Điện nước', 'Quản lý PX', 'Vận chuyển', 'Đặc biệt']
sp_ids      = ['SP_A', 'SP_B', 'SP_C']

tong_per_sp = {sid: 0.0 for sid in sp_ids}
for r in all_results:
    for sid, total in r.target_totals.items():
        if sid in tong_per_sp:
            tong_per_sp[sid] += total

header = f"  {'Chi phí':12}" + "".join(f"{sid:>16}" for sid in sp_ids) + f"{'TỔNG':>16}"
print(f"\n{header}\n  {'─'*60}")
tong_tong = 0.0
for r, ten in zip(all_results, ten_chi_phi):
    row = f"  {ten:12}"
    row_total = 0.0
    for sid in sp_ids:
        v = r.target_totals.get(sid, 0)
        row += f"{v:>16,.0f}"
        row_total += v
    row += f"{row_total:>16,.0f}"
    tong_tong += row_total
    print(row)
print(f"  {'─'*60}")
tot_row = f"  {'TỔNG':12}" + "".join(f"{tong_per_sp[sid]:>16,.0f}" for sid in sp_ids) + f"{tong_tong:>16,.0f}"
print(tot_row)

section("Bước 4 · Tỷ lệ chi phí / doanh thu")
print(f"\n  {'Sản phẩm':12} {'Tổng CP':>18} {'Doanh thu':>18} {'CP/DT':>10}")
print("  " + "─"*62)
for s in sp:
    cp = tong_per_sp.get(s['id'], 0)
    dt = s['amount']
    print(f"  {s['ten']:12} {cp:>18,.0f} {dt:>18,.0f} {cp/dt*100:>9.2f}%")

section("Bước 5 · Kiểm tra toàn bộ 6 khoản")
print()
for r, ten in zip(all_results, ten_chi_phi):
    una_sum = sum(abs(v) for v in r.unallocated.values())
    status = "✓" if r.ok and una_sum == 0 and not r.warnings else "⚠"
    print(f"  {status}  {ten:15} ok={r.ok}  unallocated={r.unallocated}  warnings={len(r.warnings)}")

section("Bước 6 · JSON export khoản nhân công (to_full_dict)")
fd_nc = r_nc.to_full_dict(
    [{'id': 'NHAN_CONG', 'amount': 60_000_000, 'ten': 'Nhân công'}], sp
)
print(json.dumps(fd_nc, ensure_ascii=False, indent=2)[:700] + "\n  ...[truncated]")


# ══════════════════════════════════════════════════════════════════════════════
# ██████████████████████████████████████████████████████████████████████████████
# ██  PHẦN NÂNG CAO — TÌNH HUỐNG PHỨC TẠP NHIỀU TIÊU THỨC                    ██
# ██████████████████████████████████████████████████████████████████████████████
# ══════════════════════════════════════════════════════════════════════════════

def print_dict_detail(label, d, indent=2):
    """In dict kết quả chi tiết dạng JSON đẹp."""
    pad = " " * indent
    print(f"\n{pad}{'─'*60}")
    print(f"{pad}[DICT] {label}")
    print(f"{pad}{'─'*60}")
    print(json.dumps(d, ensure_ascii=False, indent=indent + 2))

def print_summary_table(title_str, target_totals, sources_total, targets_meta=None):
    """In bảng tổng hợp target_totals."""
    print(f"\n  [TỔNG HỢP] {title_str}")
    print(f"  {'─'*55}")
    grand = sum(target_totals.values())
    for tid, total in target_totals.items():
        label = targets_meta.get(tid, '') if targets_meta else ''
        pct = total / grand * 100 if grand else 0
        print(f"  {tid:15} {total:>18,.2f}  ({pct:5.2f}%){('  ' + label) if label else ''}")
    print(f"  {'─'*55}")
    print(f"  {'TỔNG':15} {grand:>18,.2f}  (100.00%)")
    if sources_total:
        diff = grand - sources_total
        mark = '✓' if abs(diff) < 1 else '⚠ LỆCH'
        print(f"  {'Kiểm tra':15} {sources_total:>18,.2f}  ← source  {mark}")


# ══════════════════════════════════════════════════════════════════════════════
title("17 · TẬP ĐOÀN BÁN LẺ — Phân bổ chi phí vận hành 5 kênh bán")
# ══════════════════════════════════════════════════════════════════════════════
"""
  Tình huống: Tập đoàn bán lẻ có 5 kênh bán hàng.
  Chi phí vận hành tháng gồm 7 khoản, mỗi khoản dùng tiêu thức riêng:

    A. Lương nhân viên kho    → qty (số đơn hàng xử lý)
    B. Lương nhân viên CSKH   → equal (mỗi kênh đều cần CSKH như nhau)
    C. Chi phí kho bãi        → weight (diện tích kho mỗi kênh chiếm dụng)
    D. Chi phí marketing      → amount (doanh thu — kênh lớn hưởng nhiều)
    E. Chi phí logistics      → manual_amount (đã có báo giá từng kênh)
    F. Chi phí IT hệ thống    → pct (% phân bổ do IT dept quyết định)
    G. Chi phí thuê mặt bằng  → mixed:
         - Kênh offline cố định (alloc_amount — diện tích × đơn giá đã ký)
         - Kênh online/app chia đều phần còn lại (equal)
"""

section("Dữ liệu 5 kênh bán hàng")
kenh = [
    {'id': 'SIEUTHI',  'ten': 'Siêu thị',        'don_hang': 8_500,  'doanh_thu': 12_000_000_000, 'dien_tich': 2_000, 'alloc_weight': 2_000},
    {'id': 'CUAHANG',  'ten': 'Cửa hàng nhỏ',    'don_hang': 5_200,  'doanh_thu':  4_800_000_000, 'dien_tich': 800,  'alloc_weight': 800},
    {'id': 'ONLINE',   'ten': 'Website/App',      'don_hang': 15_000, 'doanh_thu':  8_500_000_000, 'dien_tich': 50,   'alloc_weight': 50},
    {'id': 'DAILYB2B', 'ten': 'Đại lý B2B',       'don_hang': 3_200,  'doanh_thu':  6_200_000_000, 'dien_tich': 300,  'alloc_weight': 300},
    {'id': 'XUAT_KHAU','ten': 'Xuất khẩu',        'don_hang': 1_800,  'doanh_thu':  3_500_000_000, 'dien_tich': 150,  'alloc_weight': 150},
]
print(f"\n  {'Kênh':12} {'Đơn hàng':>10} {'Doanh thu':>20} {'Diện tích':>12}")
print(f"  {'─'*58}")
for k in kenh:
    print(f"  {k['id']:12} {k['don_hang']:>10,} {k['doanh_thu']:>20,} {k['dien_tich']:>10}m²")

# ── A. Lương kho → qty (đơn hàng) ─────────────────────────────────────────────
section("A · Lương nhân viên kho — theo số đơn hàng (qty)")
src_luong_kho = [{'id': 'LUONG_KHO', 'amount': 420_000_000, 'ten': 'Lương NV kho'}]
tgt_kho = [{**k, 'qty': k['don_hang']} for k in kenh]
r_A = allocate(src_luong_kho, tgt_kho, 'qty')
r_A.print_by_source(src_luong_kho, label_key='ten')
print_summary_table("Lương kho", r_A.target_totals, 420_000_000,
                    {k['id']: k['ten'] for k in kenh})

# ── B. CSKH → equal ────────────────────────────────────────────────────────────
section("B · Lương CSKH — chia đều (equal)")
src_cskh = [{'id': 'LUONG_CSKH', 'amount': 150_000_000, 'ten': 'Lương CSKH'}]
r_B = allocate(src_cskh, kenh, 'equal')
r_B.print_by_source(src_cskh, label_key='ten')

# ── C. Kho bãi → weight (diện tích) ───────────────────────────────────────────
section("C · Chi phí kho bãi — theo diện tích (weight)")
src_kho_bai = [{'id': 'KHO_BAI', 'amount': 280_000_000, 'ten': 'Thuê kho bãi'}]
r_C = allocate(src_kho_bai, kenh, 'weight')
r_C.print_by_source(src_kho_bai, label_key='ten')
# Xác minh: SIEUTHI chiếm 2000/3300 = 60.6%
tong_dt = sum(k['dien_tich'] for k in kenh)
print(f"\n  Kiểm tra tay — tổng diện tích = {tong_dt}m²")
for k in kenh:
    ly_thuyet = 280_000_000 * k['dien_tich'] / tong_dt
    thuc_te   = r_C.target_totals[k['id']]
    print(f"    {k['id']:12}: {k['dien_tich']}m²  →  {k['dien_tich']}/{tong_dt} × 280M"
          f" = {ly_thuyet:>14,.2f}  |  engine={thuc_te:>14,.2f}  {'✓' if abs(ly_thuyet - thuc_te) < 1 else '⚠'}")

# ── D. Marketing → amount (doanh thu) ─────────────────────────────────────────
section("D · Chi phí marketing — theo doanh thu (amount)")
src_mkt = [{'id': 'MARKETING', 'amount': 360_000_000, 'ten': 'Marketing'}]
tgt_amount = [{**k, 'amount': k['doanh_thu']} for k in kenh]
r_D = allocate(src_mkt, tgt_amount, 'amount')
r_D.print_by_source(src_mkt, label_key='ten')

# ── E. Logistics → manual_amount ──────────────────────────────────────────────
section("E · Chi phí logistics — nhập tay theo báo giá (manual_amount)")
src_log = [{'id': 'LOGISTICS', 'amount': 195_000_000, 'ten': 'Logistics'}]
tgt_manual = [
    {**kenh[0], 'alloc_amount': 85_000_000},   # SIEUTHI — phân phối nội địa lớn
    {**kenh[1], 'alloc_amount': 42_000_000},   # CUAHANG
    {**kenh[2], 'alloc_amount': 28_000_000},   # ONLINE — giao hàng last-mile
    {**kenh[3], 'alloc_amount': 25_000_000},   # DAILYB2B
    {**kenh[4], 'alloc_amount': 15_000_000},   # XUAT_KHAU
]   # tổng = 195M ✓
r_E = allocate(src_log, tgt_manual, 'manual_amount')
r_E.print_by_source(src_log, label_key='ten')
print(f"\n  Kiểm tra unallocated: {r_E.unallocated}  ← phải empty ✓")

# ── F. IT hệ thống → pct ──────────────────────────────────────────────────────
section("F · Chi phí IT hệ thống — % kế toán IT (pct)")
src_it = [{'id': 'IT_SYS', 'amount': 120_000_000, 'ten': 'IT System'}]
tgt_pct = [
    {**kenh[0], 'alloc_pct': 20},   # SIEUTHI — POS + quản lý tồn kho
    {**kenh[1], 'alloc_pct': 15},   # CUAHANG
    {**kenh[2], 'alloc_pct': 35},   # ONLINE  — nặng nhất (server, CDN, app)
    {**kenh[3], 'alloc_pct': 20},   # DAILYB2B — ERP + portal
    {**kenh[4], 'alloc_pct': 10},   # XUAT_KHAU
]   # tổng = 100% ✓
r_F = allocate(src_it, tgt_pct, 'pct')
r_F.print_by_source(src_it, label_key='ten')

# ── G. Thuê mặt bằng → mixed ──────────────────────────────────────────────────
section("G · Thuê mặt bằng — mixed (kênh vật lý cố định, kênh số chia đều)")
src_mb = [{'id': 'MAT_BANG', 'amount': 480_000_000, 'ten': 'Thuê mặt bằng'}]
tgt_mixed = [
    {**kenh[0], 'alloc_amount': 300_000_000},  # SIEUTHI — hợp đồng 300M/tháng
    {**kenh[1], 'alloc_amount': 120_000_000},  # CUAHANG — 120M/tháng
    {**kenh[2]},                                # ONLINE  — không có MB vật lý → residual
    {**kenh[3], 'alloc_amount': 45_000_000},   # DAILYB2B — kho nhỏ 45M
    {**kenh[4]},                                # XUAT_KHAU → residual
]   # manual = 300+120+45 = 465M  →  residual = 15M chia equal cho ONLINE, XUAT_KHAU
r_G = allocate(src_mb, tgt_mixed, method='mixed', mixed_residual_method='equal')
r_G.print_by_source(src_mb, label_key='ten')

g_G = r_G.group_by_source(src_mb)
print("\n  Chi tiết method từng kênh:")
for item in g_G['MAT_BANG']['allocated_to']:
    stage = item['meta'].get('mixed_stage', '')
    print(f"    {item['target_id']:12}  {item['allocated']:>14,.0f}  [{item['method']}]  stage={stage}")

# ── TỔNG HỢP 17 ───────────────────────────────────────────────────────────────
section("TỔNG HỢP — Chi phí vận hành 7 khoản theo kênh bán")
all_r17    = [r_A, r_B, r_C, r_D, r_E, r_F, r_G]
ten_cp17   = ['Lương kho', 'Lương CSKH', 'Kho bãi', 'Marketing', 'Logistics', 'IT System', 'Mặt bằng']
kenh_ids   = [k['id'] for k in kenh]
kenh_names = {k['id']: k['ten'] for k in kenh}

tong_per_kenh17 = {kid: 0.0 for kid in kenh_ids}
for r in all_r17:
    for kid, v in r.target_totals.items():
        if kid in tong_per_kenh17:
            tong_per_kenh17[kid] += v

col_w = 16
header17 = f"  {'Chi phí':13}" + "".join(f"{kid:>{col_w}}" for kid in kenh_ids) + f"{'TỔNG':>{col_w}}"
print(f"\n{header17}\n  {'─'*93}")
tong_tong17 = 0.0
for r, ten in zip(all_r17, ten_cp17):
    row = f"  {ten:13}"
    row_t = 0.0
    for kid in kenh_ids:
        v = r.target_totals.get(kid, 0)
        row += f"{v:>{col_w},.0f}"
        row_t += v
    row += f"{row_t:>{col_w},.0f}"
    tong_tong17 += row_t
    print(row)
print(f"  {'─'*93}")
tot17 = f"  {'TỔNG':13}" + "".join(f"{tong_per_kenh17[kid]:>{col_w},.0f}" for kid in kenh_ids) + f"{tong_tong17:>{col_w},.0f}"
print(tot17)

print(f"\n  Tỷ lệ chi phí / doanh thu:")
for k in kenh:
    cp  = tong_per_kenh17[k['id']]
    dt  = k['doanh_thu']
    print(f"    {k['id']:12} {k['ten']:18} CP={cp:>14,.0f}  DT={dt:>16,}  CP/DT={cp/dt*100:.2f}%")

# ── DICT KẾT QUẢ 17 ───────────────────────────────────────────────────────────
section("DICT — group_by_source chi tiết khoản Marketing (D)")
g_D = r_D.group_by_source(src_mkt)
print_dict_detail("Marketing — group_by_source", g_D)

section("DICT — group_by_target chi tiết kênh ONLINE nhận từ tất cả khoản")
# Gom tất cả lines của kênh ONLINE từ các khoản có nó
online_received = {}
for r, ten in zip(all_r17, ten_cp17):
    g = r.group_by_target(kenh)
    if 'ONLINE' in g:
        online_received[ten] = {
            'received_total':  g['ONLINE']['received_total'],
            'received_from':   g['ONLINE']['received_from'],
        }
print_dict_detail("ONLINE — nhận từ tất cả 7 khoản chi phí", online_received)

section("DICT — to_full_dict khoản mặt bằng (G) — mixed chi tiết")
fd_G = r_G.to_full_dict(src_mb, kenh)
print_dict_detail("Thuê mặt bằng — to_full_dict", fd_G)


# ══════════════════════════════════════════════════════════════════════════════
title("18 · DỰ ÁN XÂY DỰNG — Phân bổ chi phí gián tiếp 6 hạng mục")
# ══════════════════════════════════════════════════════════════════════════════
"""
  Tình huống: Công ty xây dựng có 4 dự án đang thi công đồng thời.
  Chi phí gián tiếp gồm 6 khoản:

    A. Lương BQL dự án    → weight (số kỹ sư × cấp bậc → điểm phức tạp)
    B. Khấu hao máy thi công → qty (giờ máy thực tế sử dụng)
    C. Chi phí văn phòng  → equal
    D. Bảo hiểm công trình → amount (giá trị hợp đồng)
    E. Chi phí an toàn lao động → mixed:
         - DA_CAOTANG cố định (yêu cầu đặc biệt về ATLĐ)
         - Còn lại theo qty (số công nhân)
    F. Lãi vay vốn thi công → manual_pct (% CFO phân bổ theo dòng tiền dự án)
"""

section("Dữ liệu 4 dự án")
du_an = [
    {'id': 'DA_CAOTANG',  'ten': 'Cao tầng HN',   'gio_may': 2_400, 'cong_nhan': 180, 'gia_tri_hd': 85_000_000_000, 'diem_phuc_tap': 9.5, 'so_ky_su': 12},
    {'id': 'DA_KHUDT',    'ten': 'Khu đô thị',    'gio_may': 1_800, 'cong_nhan': 220, 'gia_tri_hd': 65_000_000_000, 'diem_phuc_tap': 7.0, 'so_ky_su':  9},
    {'id': 'DA_NHAMAY',   'ten': 'Nhà máy KCN',   'gio_may': 3_200, 'cong_nhan': 150, 'gia_tri_hd': 42_000_000_000, 'diem_phuc_tap': 6.5, 'so_ky_su':  8},
    {'id': 'DA_CAUDUONG',  'ten': 'Cầu đường',    'gio_may': 4_100, 'cong_nhan': 95,  'gia_tri_hd': 28_000_000_000, 'diem_phuc_tap': 8.0, 'so_ky_su':  6},
]
print(f"\n  {'Dự án':15} {'Giờ máy':>10} {'Công nhân':>11} {'Giá trị HĐ':>18} {'Điểm PT':>9} {'KS':>5}")
print(f"  {'─'*70}")
for d in du_an:
    print(f"  {d['id']:15} {d['gio_may']:>10,} {d['cong_nhan']:>11,} {d['gia_tri_hd']:>18,} {d['diem_phuc_tap']:>9.1f} {d['so_ky_su']:>5}")

# ── A. Lương BQL → weight (điểm phức tạp × số kỹ sư) ─────────────────────────
section("A · Lương ban quản lý dự án — theo điểm phức tạp × số kỹ sư (weight)")
src_bql = [{'id': 'LUONG_BQL', 'amount': 680_000_000, 'ten': 'Lương BQL'}]
tgt_bql = [{**d, 'alloc_weight': round(d['diem_phuc_tap'] * d['so_ky_su'], 1)} for d in du_an]
print(f"\n  alloc_weight = điểm_phức_tạp × số_kỹ_sư:")
for t in tgt_bql:
    print(f"    {t['id']:15}: {t['diem_phuc_tap']} × {t['so_ky_su']} = {t['alloc_weight']}")
r18_A = allocate(src_bql, tgt_bql, 'weight')
r18_A.print_by_source(src_bql, label_key='ten')

# Xác minh
tong_w = sum(t['alloc_weight'] for t in tgt_bql)
print(f"\n  Tổng weight = {tong_w}")
for t in tgt_bql:
    ly_thuyet = 680_000_000 * t['alloc_weight'] / tong_w
    thuc_te   = r18_A.target_totals[t['id']]
    print(f"    {t['id']:15}: {t['alloc_weight']}/{tong_w} × 680M = {ly_thuyet:>14,.2f}  engine={thuc_te:>14,.2f}  {'✓' if abs(ly_thuyet-thuc_te)<1 else '⚠'}")

# ── B. Khấu hao máy → qty (giờ máy) ──────────────────────────────────────────
section("B · Khấu hao máy thi công — theo giờ máy thực tế (qty)")
src_may = [{'id': 'KH_MAY_TC', 'amount': 950_000_000, 'ten': 'Khấu hao máy TC'}]
tgt_may = [{**d, 'qty': d['gio_may']} for d in du_an]
r18_B = allocate(src_may, tgt_may, 'qty')
r18_B.print_by_source(src_may, label_key='ten')

# ── C. Văn phòng → equal ──────────────────────────────────────────────────────
section("C · Chi phí văn phòng ban điều hành — chia đều (equal)")
src_vp = [{'id': 'VP_BDH', 'amount': 96_000_000, 'ten': 'VP ban điều hành'}]
r18_C = allocate(src_vp, du_an, 'equal')
r18_C.print_by_source(src_vp, label_key='ten')

# ── D. Bảo hiểm → amount (giá trị HĐ) ────────────────────────────────────────
section("D · Bảo hiểm công trình — theo giá trị hợp đồng (amount)")
src_bh = [{'id': 'BAO_HIEM', 'amount': 220_000_000, 'ten': 'Bảo hiểm CT'}]
tgt_bh = [{**d, 'amount': d['gia_tri_hd']} for d in du_an]
r18_D = allocate(src_bh, tgt_bh, 'amount')
r18_D.print_by_source(src_bh, label_key='ten')

# ── E. An toàn lao động → mixed (cao tầng cố định, còn lại theo công nhân) ────
section("E · An toàn lao động — mixed (DA_CAOTANG cố định, còn lại theo công nhân)")
src_atlđ = [{'id': 'AN_TOAN', 'amount': 185_000_000, 'ten': 'An toàn lao động'}]
tgt_atld = [
    {**du_an[0], 'alloc_amount': 100_000_000, 'qty': du_an[0]['cong_nhan']},  # cố định — tiêu chuẩn đặc biệt
    {**du_an[1], 'qty': du_an[1]['cong_nhan']},   # residual
    {**du_an[2], 'qty': du_an[2]['cong_nhan']},   # residual
    {**du_an[3], 'qty': du_an[3]['cong_nhan']},   # residual
]
r18_E = allocate(src_atlđ, tgt_atld, method='mixed', mixed_residual_method='qty')
r18_E.print_by_source(src_atlđ, label_key='ten')

print(f"\n  Xác minh mixed:")
print(f"    DA_CAOTANG : cố định 100M")
residual_atlđ = 185_000_000 - 100_000_000
cn_residual   = [du_an[1]['cong_nhan'], du_an[2]['cong_nhan'], du_an[3]['cong_nhan']]
tong_cn_res   = sum(cn_residual)
print(f"    Còn lại    : 85,000,000  (= 185M - 100M)")
print(f"    Tổng CN residual: {tong_cn_res}")
for i, d in enumerate(du_an[1:]):
    ly_t = residual_atlđ * d['cong_nhan'] / tong_cn_res
    thuc = r18_E.target_totals[d['id']]
    print(f"    {d['id']:15}: {d['cong_nhan']}/{tong_cn_res} × 85M = {ly_t:>14,.2f}  engine={thuc:>14,.2f}  {'✓' if abs(ly_t-thuc)<1 else '⚠'}")

# ── F. Lãi vay → manual_pct (CFO quyết định) ─────────────────────────────────
section("F · Lãi vay vốn thi công — % do CFO phân bổ theo dòng tiền (manual_pct)")
src_lai = [{'id': 'LAI_VAY', 'amount': 340_000_000, 'ten': 'Lãi vay TC'}]
tgt_lai = [
    {**du_an[0], 'manual_pct': 40},   # cao tầng dùng vốn nhiều nhất
    {**du_an[1], 'manual_pct': 30},
    {**du_an[2], 'manual_pct': 20},
    {**du_an[3], 'manual_pct': 10},
]
r18_F = allocate(src_lai, tgt_lai, 'manual_pct')
r18_F.print_by_source(src_lai, label_key='ten')

# ── TỔNG HỢP 18 ───────────────────────────────────────────────────────────────
section("TỔNG HỢP — Chi phí gián tiếp 6 khoản theo dự án")
all_r18  = [r18_A, r18_B, r18_C, r18_D, r18_E, r18_F]
ten_cp18 = ['Lương BQL', 'KH máy TC', 'VP BĐH', 'Bảo hiểm', 'An toàn LĐ', 'Lãi vay']
da_ids   = [d['id'] for d in du_an]

tong_per_da = {did: 0.0 for did in da_ids}
for r in all_r18:
    for did, v in r.target_totals.items():
        if did in tong_per_da:
            tong_per_da[did] += v

col_w2 = 15
h18 = f"  {'Chi phí':13}" + "".join(f"{did:>{col_w2}}" for did in da_ids) + f"{'TỔNG':>{col_w2}}"
print(f"\n{h18}\n  {'─'*75}")
tt18 = 0.0
for r, ten in zip(all_r18, ten_cp18):
    row = f"  {ten:13}"
    rt = 0.0
    for did in da_ids:
        v = r.target_totals.get(did, 0)
        row += f"{v:>{col_w2},.0f}"
        rt += v
    row += f"{rt:>{col_w2},.0f}"
    tt18 += rt
    print(row)
print(f"  {'─'*75}")
tot18 = f"  {'TỔNG CP':13}" + "".join(f"{tong_per_da[did]:>{col_w2},.0f}" for did in da_ids) + f"{tt18:>{col_w2},.0f}"
print(tot18)

print(f"\n  Tỷ lệ CP gián tiếp / Giá trị HĐ:")
for d in du_an:
    cp = tong_per_da[d['id']]
    hd = d['gia_tri_hd']
    print(f"    {d['id']:15} {d['ten']:16} CP={cp:>13,.0f}  HĐ={hd:>18,}  CP/HĐ={cp/hd*100:.3f}%")

# ── DICT KẾT QUẢ 18 ───────────────────────────────────────────────────────────
section("DICT — to_full_dict khoản An toàn lao động (E) — mixed")
fd_18E = r18_E.to_full_dict(src_atlđ, du_an)
print_dict_detail("An toàn lao động — to_full_dict (mixed)", fd_18E)

section("DICT — group_by_target DA_CAOTANG — nhận từ tất cả 6 khoản")
caotang_summary = {}
for r, ten in zip(all_r18, ten_cp18):
    g = r.group_by_target(du_an)
    if 'DA_CAOTANG' in g:
        caotang_summary[ten] = {
            'received_total': g['DA_CAOTANG']['received_total'],
            'method': g['DA_CAOTANG']['received_from'][0]['method'] if g['DA_CAOTANG']['received_from'] else '',
        }
print_dict_detail("DA_CAOTANG — nhận từ 6 khoản", caotang_summary)


# ══════════════════════════════════════════════════════════════════════════════
title("19 · NGÂN HÀNG — Phân bổ chi phí vận hành theo đơn vị kinh doanh")
# ══════════════════════════════════════════════════════════════════════════════
"""
  Tình huống: Ngân hàng thương mại phân bổ chi phí hội sở về 5 khối kinh doanh.
  8 khoản chi phí với 6 tiêu thức khác nhau:

    A. Lương hội sở — bộ phận hỗ trợ  → equal (mỗi khối đều được serve)
    B. Khấu hao hệ thống core banking  → qty (số giao dịch)
    C. Chi phí trụ sở + thuê văn phòng → weight (số nhân sự × hệ số mặt bằng)
    D. Chi phí marketing thương hiệu   → amount (dư nợ cho vay + tiền gửi)
    E. Chi phí đào tạo & HR            → qty (số nhân sự)
    F. Chi phí tuân thủ & pháp lý      → pct (% quy định nội bộ theo rủi ro)
    G. Chi phí công nghệ & IT          → mixed:
         - Khối Bán lẻ cố định (hạ tầng mobile banking lớn)
         - Còn lại theo số giao dịch (qty)
    H. Lãi điều vốn nội bộ (FTP cost)  → manual_amount (bộ phận ALM quyết định)
"""

section("Dữ liệu 5 khối kinh doanh")
khoi = [
    {'id': 'BAN_LE',    'ten': 'Khối Bán lẻ',        'giao_dich': 2_500_000, 'nhan_su': 4_200, 'du_no': 85_000_000_000_000, 'he_so_mb': 1.2, 'rui_ro_pct': 30},
    {'id': 'DOANH_NGH', 'ten': 'Khối DN vừa & nhỏ',  'giao_dich':   380_000, 'nhan_su': 1_800, 'du_no': 62_000_000_000_000, 'he_so_mb': 1.0, 'rui_ro_pct': 25},
    {'id': 'KHACH_HANG_LON', 'ten': 'Khối KH Lớn',   'giao_dich':    45_000, 'nhan_su':   420, 'du_no':120_000_000_000_000, 'he_so_mb': 1.5, 'rui_ro_pct': 20},
    {'id': 'DICH_VU_TC', 'ten': 'Dịch vụ tài chính', 'giao_dich':   650_000, 'nhan_su':   680, 'du_no': 18_000_000_000_000, 'he_so_mb': 0.8, 'rui_ro_pct': 15},
    {'id': 'DTVON',      'ten': 'Đầu tư & Vốn',       'giao_dich':    12_000, 'nhan_su':   240, 'du_no': 35_000_000_000_000, 'he_so_mb': 0.5, 'rui_ro_pct': 10},
]
print(f"\n  {'Khối':20} {'GD':>12} {'Nhân sự':>9} {'Dư nợ (tỷ)':>14} {'Rủi ro':>8}")
print(f"  {'─'*67}")
for k in khoi:
    print(f"  {k['ten']:20} {k['giao_dich']:>12,} {k['nhan_su']:>9,} {k['du_no']/1e9:>14,.0f} {k['rui_ro_pct']:>7}%")

# ── A. Lương hội sở → equal ────────────────────────────────────────────────────
section("A · Lương hội sở bộ phận hỗ trợ — chia đều (equal)")
src_hs = [{'id': 'LUONG_HOISO', 'amount': 1_200_000_000, 'ten': 'Lương HS hỗ trợ'}]
r19_A = allocate(src_hs, khoi, 'equal')
r19_A.print_by_source(src_hs, label_key='ten')

# ── B. Core banking → qty (giao dịch) ─────────────────────────────────────────
section("B · Khấu hao core banking — theo số giao dịch (qty)")
src_core = [{'id': 'CORE_BANKING', 'amount': 2_400_000_000, 'ten': 'Core banking'}]
tgt_gd = [{**k, 'qty': k['giao_dich']} for k in khoi]
r19_B = allocate(src_core, tgt_gd, 'qty')
r19_B.print_by_source(src_core, label_key='ten')

# ── C. Trụ sở → weight (nhân sự × hệ số mặt bằng) ────────────────────────────
section("C · Trụ sở + thuê văn phòng — theo nhân sự × hệ số mặt bằng (weight)")
src_ts = [{'id': 'TRU_SO', 'amount': 840_000_000, 'ten': 'Trụ sở & VP'}]
tgt_ts = [{**k, 'alloc_weight': round(k['nhan_su'] * k['he_so_mb'], 1)} for k in khoi]
print(f"\n  alloc_weight = nhân_sự × hệ_số_mặt_bằng:")
for t in tgt_ts:
    print(f"    {t['id']:20}: {t['nhan_su']} × {t['he_so_mb']} = {t['alloc_weight']}")
r19_C = allocate(src_ts, tgt_ts, 'weight')
r19_C.print_by_source(src_ts, label_key='ten')

# ── D. Marketing → amount (dư nợ) ─────────────────────────────────────────────
section("D · Marketing thương hiệu — theo dư nợ tổng (amount)")
src_mkt19 = [{'id': 'MKT_TH', 'amount': 560_000_000, 'ten': 'Marketing TH'}]
tgt_duno = [{**k, 'amount': k['du_no']} for k in khoi]
r19_D = allocate(src_mkt19, tgt_duno, 'amount')
r19_D.print_by_source(src_mkt19, label_key='ten')

# ── E. Đào tạo → qty (nhân sự) ────────────────────────────────────────────────
section("E · Chi phí đào tạo & HR — theo số nhân sự (qty)")
src_dt = [{'id': 'DAO_TAO', 'amount': 380_000_000, 'ten': 'Đào tạo & HR'}]
tgt_ns = [{**k, 'qty': k['nhan_su']} for k in khoi]
r19_E = allocate(src_dt, tgt_ns, 'qty')
r19_E.print_by_source(src_dt, label_key='ten')

# ── F. Tuân thủ → pct (% rủi ro nội bộ) ──────────────────────────────────────
section("F · Tuân thủ & pháp lý — theo % rủi ro nội bộ (pct)")
src_tt = [{'id': 'TUAN_THU', 'amount': 290_000_000, 'ten': 'Tuân thủ & PL'}]
tgt_tt = [{**k, 'alloc_pct': k['rui_ro_pct']} for k in khoi]
r19_F = allocate(src_tt, tgt_tt, 'pct')
r19_F.print_by_source(src_tt, label_key='ten')

# ── G. IT → mixed (BAN_LE cố định, còn lại theo giao dịch) ────────────────────
section("G · Công nghệ & IT — mixed (Bán lẻ cố định mobile infra, còn lại theo GD)")
src_it19 = [{'id': 'CONG_NGHE', 'amount': 1_800_000_000, 'ten': 'Công nghệ IT'}]
tgt_it19 = [
    {**khoi[0], 'alloc_amount': 900_000_000, 'qty': khoi[0]['giao_dich']},  # BAN_LE cố định
    {**khoi[1], 'qty': khoi[1]['giao_dich']},
    {**khoi[2], 'qty': khoi[2]['giao_dich']},
    {**khoi[3], 'qty': khoi[3]['giao_dich']},
    {**khoi[4], 'qty': khoi[4]['giao_dich']},
]
r19_G = allocate(src_it19, tgt_it19, method='mixed', mixed_residual_method='qty')
r19_G.print_by_source(src_it19, label_key='ten')
print(f"\n  Xác minh mixed IT:")
residual_it = 1_800_000_000 - 900_000_000
gd_res = [k['giao_dich'] for k in khoi[1:]]
tong_gd_res = sum(gd_res)
print(f"    BAN_LE     : cố định 900,000,000")
print(f"    Còn lại    : {residual_it:,}  (= 1,800M - 900M)")
print(f"    Tổng GD residual: {tong_gd_res:,}")
for k in khoi[1:]:
    lt = residual_it * k['giao_dich'] / tong_gd_res
    tt = r19_G.target_totals[k['id']]
    print(f"    {k['id']:20}: {k['giao_dich']:,}/{tong_gd_res:,} × 900M = {lt:>14,.2f}  engine={tt:>14,.2f}  {'✓' if abs(lt-tt)<1 else '⚠'}")

# ── H. FTP cost → manual_amount (ALM) ─────────────────────────────────────────
section("H · Lãi điều vốn nội bộ FTP — manual_amount (bộ phận ALM)")
src_ftp = [{'id': 'FTP_COST', 'amount': 3_600_000_000, 'ten': 'FTP cost'}]
tgt_ftp = [
    {**khoi[0], 'alloc_amount': 1_400_000_000},  # BAN_LE — huy động vốn lớn
    {**khoi[1], 'alloc_amount':   900_000_000},
    {**khoi[2], 'alloc_amount':   750_000_000},  # KH Lớn — dư nợ lớn nhưng ít giao dịch
    {**khoi[3], 'alloc_amount':   300_000_000},
    {**khoi[4], 'alloc_amount':   250_000_000},
]   # tổng = 3,600M ✓
r19_H = allocate(src_ftp, tgt_ftp, 'manual_amount')
r19_H.print_by_source(src_ftp, label_key='ten')
print(f"  Unallocated: {r19_H.unallocated}  ✓")

# ── TỔNG HỢP 19 ───────────────────────────────────────────────────────────────
section("TỔNG HỢP — Chi phí vận hành 8 khoản theo khối kinh doanh")
all_r19  = [r19_A, r19_B, r19_C, r19_D, r19_E, r19_F, r19_G, r19_H]
ten_cp19 = ['Lương HS', 'Core bank', 'Trụ sở', 'Marketing', 'Đào tạo', 'Tuân thủ', 'IT', 'FTP cost']
khoi_ids = [k['id'] for k in khoi]

tong_per_khoi = {kid: 0.0 for kid in khoi_ids}
for r in all_r19:
    for kid, v in r.target_totals.items():
        if kid in tong_per_khoi:
            tong_per_khoi[kid] += v

col_w3 = 14
h19 = f"  {'Chi phí':12}" + "".join(f"{kid[:12]:>{col_w3}}" for kid in khoi_ids) + f"{'TỔNG':>{col_w3}}"
print(f"\n{h19}\n  {'─'*84}")
tt19 = 0.0
for r, ten in zip(all_r19, ten_cp19):
    row = f"  {ten:12}"
    rt = 0.0
    for kid in khoi_ids:
        v = r.target_totals.get(kid, 0)
        row += f"{v:>{col_w3},.0f}"
        rt += v
    row += f"{rt:>{col_w3},.0f}"
    tt19 += rt
    print(row)
print(f"  {'─'*84}")
tot19 = f"  {'TỔNG':12}" + "".join(f"{tong_per_khoi[kid]:>{col_w3},.0f}" for kid in khoi_ids) + f"{tt19:>{col_w3},.0f}"
print(tot19)

print(f"\n  Tỷ lệ CP hội sở / Dư nợ:")
for k in khoi:
    cp = tong_per_khoi[k['id']]
    dn = k['du_no']
    print(f"    {k['ten']:22} CP={cp:>15,.0f}  CP/Dư nợ={cp/dn*100:.4f}%")

# ── DICT KẾT QUẢ 19 ───────────────────────────────────────────────────────────
section("DICT — to_full_dict khoản IT (G) — mixed")
fd_19G = r19_G.to_full_dict(src_it19, khoi)
print_dict_detail("Công nghệ IT — to_full_dict (mixed)", fd_19G)

section("DICT — group_by_source tất cả 8 khoản → tổng theo tiêu thức")
summary_19 = {}
for r, ten in zip(all_r19, ten_cp19):
    g = r.group_by_source(include_totals_only=True)
    src_id = list(g.keys())[0]
    summary_19[ten] = {
        'allocated_total': g[src_id]['allocated_total'],
        'target_totals':   r.target_totals,
        'ok':              r.ok,
    }
print_dict_detail("Tổng hợp 8 khoản chi phí ngân hàng", summary_19)


# ══════════════════════════════════════════════════════════════════════════════
title("20 · TẬP HỢP CHI PHÍ SẢN XUẤT PHỨC TẠP — 3 NHÀ MÁY × 4 DÒNG SẢN PHẨM")
# ══════════════════════════════════════════════════════════════════════════════
"""
  Tình huống thực tế nhất — gần với ERPNext production costing:
  3 nhà máy, mỗi nhà máy sản xuất một số dòng SP.
  Chi phí tập hợp theo 2 cấp:

  CẤP 1 — Phân bổ chi phí từ CÔNG TY về NHÀ MÁY (group_key='nha_may'):
    A. Lương quản lý công ty   → equal (3 nhà máy)
    B. Khấu hao VP công ty     → weight (% doanh thu ke hoach)
    C. Chi phí R&D             → manual_pct (% chiến lược)

  CẤP 2 — Phân bổ chi phí từ NHÀ MÁY về DÒNG SẢN PHẨM (group_key='nha_may'):
    D. Lương công nhân NM      → qty (giờ công trực tiếp)
    E. Khấu hao dây chuyền     → weight (giờ máy × hệ số hao mòn)
    F. Nguyên vật liệu phụ     → amount (giá trị NVL chính đã tiêu)
    G. Chi phí NL&NL đặc biệt  → mixed per nhà máy:
         - 1 dòng SP flagship cố định (manual_amount)
         - Còn lại theo qty
"""

section("Dữ liệu 3 nhà máy và 8 dòng sản phẩm")
# Mỗi SP thuộc 1 nhà máy (group_key)
san_pham = [
    # NM1 — Nhà máy điện tử
    {'id': 'SP_TV',    'ten': 'Smart TV',        'nha_may': 'NM1', 'gio_cong': 15_000, 'gio_may': 8_000,  'nvl_chinh': 12_000_000_000, 'he_so_hm': 2.0},
    {'id': 'SP_MAN',   'ten': 'Màn hình',         'nha_may': 'NM1', 'gio_cong': 9_000,  'gio_may': 6_000,  'nvl_chinh':  6_500_000_000, 'he_so_hm': 1.5},
    {'id': 'SP_AUDIO', 'ten': 'Âm thanh',          'nha_may': 'NM1', 'gio_cong': 5_000,  'gio_may': 2_500,  'nvl_chinh':  3_200_000_000, 'he_so_hm': 1.2},
    # NM2 — Nhà máy gia dụng
    {'id': 'SP_TL',    'ten': 'Tủ lạnh',           'nha_may': 'NM2', 'gio_cong': 18_000, 'gio_may': 12_000, 'nvl_chinh': 18_500_000_000, 'he_so_hm': 2.5},
    {'id': 'SP_DIEU_HOA','ten': 'Điều hòa',        'nha_may': 'NM2', 'gio_cong': 12_000, 'gio_may': 9_000,  'nvl_chinh': 14_000_000_000, 'he_so_hm': 2.2},
    # NM3 — Nhà máy linh kiện
    {'id': 'SP_PCB',   'ten': 'Bo mạch PCB',       'nha_may': 'NM3', 'gio_cong': 22_000, 'gio_may': 18_000, 'nvl_chinh': 24_000_000_000, 'he_so_hm': 3.0},
    {'id': 'SP_IC',    'ten': 'Vi mạch IC',         'nha_may': 'NM3', 'gio_cong': 8_000,  'gio_may': 12_000, 'nvl_chinh': 35_000_000_000, 'he_so_hm': 3.5},
    {'id': 'SP_SENSOR','ten': 'Cảm biến',           'nha_may': 'NM3', 'gio_cong': 6_000,  'gio_may': 4_000,  'nvl_chinh':  8_000_000_000, 'he_so_hm': 2.8},
]
nha_may_meta = {
    'NM1': {'ten': 'NM Điện tử',  'dt_ke_hoach': 85_000_000_000},
    'NM2': {'ten': 'NM Gia dụng', 'dt_ke_hoach': 120_000_000_000},
    'NM3': {'ten': 'NM Linh kiện','dt_ke_hoach': 210_000_000_000},
}
print(f"\n  {'SP':10} {'Nhà máy':6} {'Giờ công':>10} {'Giờ máy':>10} {'NVL chính (tỷ)':>16} {'HM':>5}")
print(f"  {'─'*60}")
for s in san_pham:
    print(f"  {s['id']:10} {s['nha_may']:6} {s['gio_cong']:>10,} {s['gio_may']:>10,} {s['nvl_chinh']/1e9:>16,.1f} {s['he_so_hm']:>5}")

# ═══ CẤP 1 — Công ty → Nhà máy ══════════════════════════════════════════════
section("CẤP 1 · Phân bổ từ Công ty về 3 Nhà máy")

nha_may_list = [
    {'id': 'NM1', 'ten': nha_may_meta['NM1']['ten'], 'alloc_weight': nha_may_meta['NM1']['dt_ke_hoach'], 'amount': nha_may_meta['NM1']['dt_ke_hoach']},
    {'id': 'NM2', 'ten': nha_may_meta['NM2']['ten'], 'alloc_weight': nha_may_meta['NM2']['dt_ke_hoach'], 'amount': nha_may_meta['NM2']['dt_ke_hoach']},
    {'id': 'NM3', 'ten': nha_may_meta['NM3']['ten'], 'alloc_weight': nha_may_meta['NM3']['dt_ke_hoach'], 'amount': nha_may_meta['NM3']['dt_ke_hoach']},
]

# A. Lương QL công ty → equal
src_ql_cty = [{'id': 'LUONG_QL_CTY', 'amount': 480_000_000, 'ten': 'Lương QL công ty'}]
r20_A = allocate(src_ql_cty, nha_may_list, 'equal')
print("\n  A. Lương QL công ty (equal):")
r20_A.print_by_source(src_ql_cty, label_key='ten')

# B. Khấu hao VP → weight (DT kế hoạch)
src_kh_vp = [{'id': 'KH_VP_CTY', 'amount': 120_000_000, 'ten': 'KH VP công ty'}]
r20_B = allocate(src_kh_vp, nha_may_list, 'weight')
print("\n  B. KH VP công ty (weight = DT kế hoạch):")
r20_B.print_by_source(src_kh_vp, label_key='ten')

# C. R&D → manual_pct (chiến lược công ty)
src_rd = [{'id': 'RD_CTY', 'amount': 900_000_000, 'ten': 'R&D công ty'}]
tgt_rd = [
    {**nha_may_list[0], 'manual_pct': 25},  # NM1 — TV/màn hình cần R&D ít hơn
    {**nha_may_list[1], 'manual_pct': 20},  # NM2
    {**nha_may_list[2], 'manual_pct': 55},  # NM3 — linh kiện cần R&D nhiều nhất
]
r20_C = allocate(src_rd, tgt_rd, 'manual_pct')
print("\n  C. R&D công ty (manual_pct chiến lược):")
r20_C.print_by_source(src_rd, label_key='ten')

# Tổng cấp 1 theo nhà máy
all_r20_cap1 = [r20_A, r20_B, r20_C]
ten_cap1     = ['Lương QL', 'KH VP', 'R&D']
tong_cap1    = {'NM1': 0.0, 'NM2': 0.0, 'NM3': 0.0}
for r in all_r20_cap1:
    for nm, v in r.target_totals.items():
        tong_cap1[nm] += v
print(f"\n  Tổng CP Cấp 1 phân về nhà máy:")
for nm, v in tong_cap1.items():
    print(f"    {nm} ({nha_may_meta[nm]['ten']:15}): {v:>15,.0f}")

# ═══ CẤP 2 — Nhà máy → Sản phẩm ═════════════════════════════════════════════
section("CẤP 2 · Phân bổ từ Nhà máy về từng dòng Sản phẩm (group_key='nha_may')")

# D. Lương CN → qty (giờ công) — group_key='nha_may'
src_luong_cn = [
    {'id': 'LUONG_CN_NM1', 'amount': 1_200_000_000, 'ten': 'Lương CN NM1', 'nha_may': 'NM1'},
    {'id': 'LUONG_CN_NM2', 'amount':   980_000_000, 'ten': 'Lương CN NM2', 'nha_may': 'NM2'},
    {'id': 'LUONG_CN_NM3', 'amount': 1_560_000_000, 'ten': 'Lương CN NM3', 'nha_may': 'NM3'},
]
tgt_gio_cong = [{**s, 'qty': s['gio_cong']} for s in san_pham]
r20_D = allocate(src_luong_cn, tgt_gio_cong, 'qty', group_key='nha_may')
print("\n  D. Lương công nhân (qty = giờ công, group_key='nha_may'):")
r20_D.print_by_source(src_luong_cn, label_key='ten')

# E. Khấu hao dây chuyền → weight (giờ máy × hệ số hao mòn) — group_key
src_kh_dc = [
    {'id': 'KH_DC_NM1', 'amount':  850_000_000, 'ten': 'KH dây chuyền NM1', 'nha_may': 'NM1'},
    {'id': 'KH_DC_NM2', 'amount': 1_100_000_000, 'ten': 'KH dây chuyền NM2', 'nha_may': 'NM2'},
    {'id': 'KH_DC_NM3', 'amount': 2_200_000_000, 'ten': 'KH dây chuyền NM3', 'nha_may': 'NM3'},
]
tgt_kh = [{**s, 'alloc_weight': round(s['gio_may'] * s['he_so_hm'], 1)} for s in san_pham]
print(f"\n  alloc_weight = giờ_máy × hệ_số_hao_mòn:")
for t in tgt_kh:
    print(f"    {t['id']:10}: {t['gio_may']:,} × {t['he_so_hm']} = {t['alloc_weight']:,.0f}")
r20_E = allocate(src_kh_dc, tgt_kh, 'weight', group_key='nha_may')
print()
r20_E.print_by_source(src_kh_dc, label_key='ten')

# F. NVL phụ → amount (giá trị NVL chính) — group_key
src_nvlp = [
    {'id': 'NVL_PHU_NM1', 'amount':  380_000_000, 'ten': 'NVL phụ NM1', 'nha_may': 'NM1'},
    {'id': 'NVL_PHU_NM2', 'amount':  520_000_000, 'ten': 'NVL phụ NM2', 'nha_may': 'NM2'},
    {'id': 'NVL_PHU_NM3', 'amount':  890_000_000, 'ten': 'NVL phụ NM3', 'nha_may': 'NM3'},
]
tgt_nvl = [{**s, 'amount': s['nvl_chinh']} for s in san_pham]
r20_F = allocate(src_nvlp, tgt_nvl, 'amount', group_key='nha_may')
print("\n  F. NVL phụ (amount = NVL chính, group_key='nha_may'):")
r20_F.print_by_source(src_nvlp, label_key='ten')

# G. CP đặc biệt → mixed per nhà máy (flagship cố định, còn lại theo qty)
src_cpdb = [
    {'id': 'DB_NM1', 'amount':  250_000_000, 'ten': 'CP đặc biệt NM1', 'nha_may': 'NM1'},
    {'id': 'DB_NM2', 'amount':  180_000_000, 'ten': 'CP đặc biệt NM2', 'nha_may': 'NM2'},
    {'id': 'DB_NM3', 'amount':  420_000_000, 'ten': 'CP đặc biệt NM3', 'nha_may': 'NM3'},
]
# Flagship mỗi NM: NM1=SP_TV, NM2=SP_TL, NM3=SP_PCB
tgt_db20 = [
    {**san_pham[0], 'alloc_amount': 150_000_000, 'qty': san_pham[0]['gio_cong']},  # SP_TV flagship
    {**san_pham[1], 'qty': san_pham[1]['gio_cong']},
    {**san_pham[2], 'qty': san_pham[2]['gio_cong']},
    {**san_pham[3], 'alloc_amount': 100_000_000, 'qty': san_pham[3]['gio_cong']},  # SP_TL flagship
    {**san_pham[4], 'qty': san_pham[4]['gio_cong']},
    {**san_pham[5], 'alloc_amount': 280_000_000, 'qty': san_pham[5]['gio_cong']},  # SP_PCB flagship
    {**san_pham[6], 'qty': san_pham[6]['gio_cong']},
    {**san_pham[7], 'qty': san_pham[7]['gio_cong']},
]
r20_G = allocate(src_cpdb, tgt_db20, method='mixed',
                 mixed_residual_method='qty', group_key='nha_may')
print("\n  G. CP đặc biệt mixed (flagship cố định, còn lại theo giờ công):")
r20_G.print_by_source(src_cpdb, label_key='ten')

# ── TỔNG HỢP 20 ───────────────────────────────────────────────────────────────
section("TỔNG HỢP — Chi phí toàn bộ 2 cấp phân bổ theo dòng sản phẩm")

# Cấp 1 phân về nhà máy (chưa đến SP), cộng vào SP theo tỷ lệ bằng qty nội bộ
# Đơn giản: gán CP cấp 1 của NM xuống SP theo tỷ lệ giờ công
all_r20_cap2 = [r20_D, r20_E, r20_F, r20_G]
ten_cap2     = ['Lương CN', 'KH DC', 'NVL phụ', 'CP ĐB']

sp_ids20 = [s['id'] for s in san_pham]
tong_per_sp20 = {sid: 0.0 for sid in sp_ids20}

# Cộng cấp 2
for r in all_r20_cap2:
    for sid, v in r.target_totals.items():
        if sid in tong_per_sp20:
            tong_per_sp20[sid] += v

# Cộng cấp 1 về SP theo tỷ lệ giờ công trong từng NM
for nm in ['NM1', 'NM2', 'NM3']:
    sp_nm = [s for s in san_pham if s['nha_may'] == nm]
    tong_gc_nm = sum(s['gio_cong'] for s in sp_nm)
    cp_cap1_nm = tong_cap1[nm]
    for s in sp_nm:
        tong_per_sp20[s['id']] += cp_cap1_nm * s['gio_cong'] / tong_gc_nm

col_w20 = 15
print(f"\n  {'SP':12} {'NM':6} {'CP Cấp 1':>{col_w20}} {'CP Cấp 2':>{col_w20}} {'TỔNG CP':>{col_w20}} {'NVL chính (tỷ)':>{col_w20}} {'CP/NVL':>8}")
print(f"  {'─'*88}")
for s in san_pham:
    sid    = s['id']
    nm     = s['nha_may']
    sp_nm  = [x for x in san_pham if x['nha_may'] == nm]
    tong_gc_nm = sum(x['gio_cong'] for x in sp_nm)
    cp1    = tong_cap1[nm] * s['gio_cong'] / tong_gc_nm
    cp2    = sum(r.target_totals.get(sid, 0) for r in all_r20_cap2)
    cp_tot = tong_per_sp20[sid]
    nvl    = s['nvl_chinh']
    print(f"  {sid:12} {nm:6} {cp1:>{col_w20},.0f} {cp2:>{col_w20},.0f} {cp_tot:>{col_w20},.0f} {nvl/1e9:>{col_w20}.1f} {cp_tot/nvl*100:>7.2f}%")

tong_cp20 = sum(tong_per_sp20.values())
print(f"  {'─'*88}")
print(f"  {'TỔNG':12} {'':6} {'':>{col_w20}} {'':>{col_w20}} {tong_cp20:>{col_w20},.0f}")

# ── DICT KẾT QUẢ 20 ───────────────────────────────────────────────────────────
section("DICT — to_full_dict khoản KH dây chuyền NM3 (E) — group_key")
src_nm3 = [s for s in src_kh_dc if s['id'] == 'KH_DC_NM3']
sp_nm3  = [s for s in san_pham   if s['nha_may'] == 'NM3']
tgt_nm3 = [t for t in tgt_kh     if t['nha_may'] == 'NM3']
# Tạo sub-result cho NM3
r20_E_nm3 = allocate(src_nm3, tgt_nm3, 'weight')
fd_20E = r20_E_nm3.to_full_dict(src_nm3, sp_nm3)
print_dict_detail("KH dây chuyền NM3 — to_full_dict", fd_20E)

section("DICT — group_by_source tổng hợp cấp 2 (4 khoản, toàn bộ 8 SP)")
summary_cap2 = {}
for r, ten in zip(all_r20_cap2, ten_cap2):
    g = r.group_by_source(include_totals_only=True)
    summary_cap2[ten] = {
        src_id: {
            'allocated_total': row['allocated_total'],
            'target_totals':   r.target_totals,
        }
        for src_id, row in g.items()
    }
print_dict_detail("Tổng hợp 4 khoản cấp 2 — group_by_source", summary_cap2)


# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{'═'*W}")
print("  ✅  Hoàn thành toàn bộ ví dụ Allocation A-Z  (20 chủ đề)")
print(f"     16 chủ đề cơ bản + 4 tình huống phức tạp nâng cao")
print(f"     17 · Tập đoàn bán lẻ   — 5 kênh × 7 tiêu thức")
print(f"     18 · Xây dựng          — 4 dự án × 6 tiêu thức")
print(f"     19 · Ngân hàng         — 5 khối  × 8 tiêu thức + FTP")
print(f"     20 · Sản xuất 2 cấp    — 3 NM × 8 SP × 7 tiêu thức + group_key")
print(f"{'═'*W}\n")
