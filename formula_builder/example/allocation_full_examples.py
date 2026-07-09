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
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

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
    {'id': 'CP_MANG', 'amount':  3_600_000, 'ten': 'Internet'},
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
print(f"\n{'═'*W}")
print("  ✅  Hoàn thành toàn bộ ví dụ Allocation A-Z  (16 chủ đề)")
print(f"{'═'*W}\n")
