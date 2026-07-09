"""
==============================================================================
  Allocation Engine — Ví dụ PHỨC TẠP NHẤT: Nhiều nguồn × Nhiều tiêu thức
  Tập trung vào: nhiều tiêu thức, mixed đa tầng, cross-allocation, cascade
==============================================================================

  MỤC LỤC
  ─────────────────────────────────────────────────────────────────────────
  21 · Composite weight    — trọng số TỔ HỢP từ nhiều chỉ số (KPI, m², giờ)
  22 · Mixed 4 tầng        — alloc_amount → manual_pct → weight → equal
  23 · Cross-allocation    — BP phân bổ qua lại cho nhau (IT←→HR←→Finance)
  24 · Cascade 3 cấp       — Tập đoàn → Công ty → Phòng ban → Sản phẩm
  25 · Multi-source khác   — 10 nguồn × 12 đích × 7 tiêu thức khác nhau
  26 · Mixed tất cả 4 loại — manual_amount + manual_pct + weight + qty trong
       cùng 1 lần allocate (mỗi đích dùng tiêu thức riêng)
  27 · Phân bổ vòng lặp    — chi phí dịch vụ nội bộ lẫn nhau (iterative)
  28 · Tập đoàn đa ngành   — 15 nguồn × 18 đích × 9 tiêu thức + group_key
       + cascade + mixed + cross-check toàn bộ
==============================================================================
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from engine_v24 import allocate, FormulaEngine

W = 76
def title(s):   print(f"\n{'═'*W}\n  {s}\n{'═'*W}")
def section(s): print(f"\n{'─'*W}\n  {s}\n{'─'*W}")
def ok(label, val=None):
    if val is None: print(f"  ✓  {label}")
    else:           print(f"  ✓  {label:50s} = {val}")

def print_matrix(header_row, row_labels, data_rows, col_w=14, fmt=",.0f"):
    """In bảng ma trận nguồn × đích đẹp."""
    print(f"\n  {'':15}" + "".join(f"{h:>{col_w}}" for h in header_row) + f"{'TỔNG':>{col_w}}")
    print(f"  {'─'*( 15 + col_w*(len(header_row)+1) )}")
    grand = 0.0
    totals = [0.0] * len(header_row)
    for label, vals in zip(row_labels, data_rows):
        row_total = sum(vals)
        grand += row_total
        print(f"  {label:15}" + "".join(f"{v:>{col_w}{fmt}}" for v in vals) + f"{row_total:>{col_w}{fmt}}")
        for i, v in enumerate(vals): totals[i] += v
    print(f"  {'─'*( 15 + col_w*(len(header_row)+1) )}")
    print(f"  {'TỔNG':15}" + "".join(f"{v:>{col_w}{fmt}}" for v in totals) + f"{grand:>{col_w}{fmt}}")

def verify_total(label, result_list, expected_total):
    """Kiểm tra tổng phân bổ = tổng nguồn."""
    allocated = sum(sum(r.target_totals.values()) for r in result_list)
    ok_sign   = "✓" if abs(allocated - expected_total) < 1 else "⚠"
    print(f"  {ok_sign}  {label}: allocated={allocated:,.0f}  expected={expected_total:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
title("21 · COMPOSITE WEIGHT — Trọng số tổ hợp từ nhiều chỉ số")
# ══════════════════════════════════════════════════════════════════════════════
"""
Tình huống: Chi phí vận hành trung tâm dữ liệu phân bổ cho 6 hệ thống.
Tiêu thức COMPOSITE: alloc_weight = CPU_cores × 0.4 + RAM_GB × 0.3 + Storage_TB × 0.2 + Requests × 0.1
Không có tiêu thức đơn lẻ nào phản ánh đúng → tổ hợp có trọng số.
"""
section("Dữ liệu 6 hệ thống CNTT")
he_thong = [
    {'id': 'ERP',      'ten': 'ERP (SAP)',         'cpu': 32, 'ram': 256, 'storage': 50,  'req_M': 0.5},
    {'id': 'CRM',      'ten': 'CRM (Salesforce)',   'cpu': 16, 'ram': 128, 'storage': 20,  'req_M': 2.0},
    {'id': 'BI',       'ten': 'BI/Analytics',       'cpu': 64, 'ram': 512, 'storage': 200, 'req_M': 0.2},
    {'id': 'ECOM',     'ten': 'E-Commerce',         'cpu': 48, 'ram': 384, 'storage': 30,  'req_M': 8.0},
    {'id': 'HR',       'ten': 'HRM',                'cpu':  8, 'ram':  64, 'storage': 10,  'req_M': 0.3},
    {'id': 'SECURITY', 'ten': 'Security/SIEM',      'cpu': 24, 'ram': 192, 'storage': 80,  'req_M': 1.5},
]
print(f"\n  {'Hệ thống':12} {'CPU cores':>10} {'RAM (GB)':>10} {'Storage TB':>12} {'Req/tháng M':>13}")
print(f"  {'─'*60}")
for h in he_thong:
    print(f"  {h['id']:12} {h['cpu']:>10} {h['ram']:>10} {h['storage']:>12} {h['req_M']:>13.1f}")

# Tính composite weight
W_CPU, W_RAM, W_STORAGE, W_REQ = 0.40, 0.30, 0.20, 0.10
# Normalize mỗi chỉ số về [0,1] rồi tổ hợp
max_cpu     = max(h['cpu']     for h in he_thong)
max_ram     = max(h['ram']     for h in he_thong)
max_storage = max(h['storage'] for h in he_thong)
max_req     = max(h['req_M']   for h in he_thong)

for h in he_thong:
    h['alloc_weight'] = round(
        (h['cpu']/max_cpu)         * W_CPU    * 100 +
        (h['ram']/max_ram)         * W_RAM    * 100 +
        (h['storage']/max_storage) * W_STORAGE * 100 +
        (h['req_M']/max_req)       * W_REQ    * 100,
        2
    )

section("Composite weight = CPU×0.4 + RAM×0.3 + Storage×0.2 + Requests×0.1 (normalized)")
print(f"\n  {'Hệ thống':12} {'CPU norm':>10} {'RAM norm':>10} {'Stor norm':>10} {'Req norm':>10} {'WEIGHT':>10}")
print(f"  {'─'*64}")
for h in he_thong:
    cn  = h['cpu']/max_cpu
    rn  = h['ram']/max_ram
    sn  = h['storage']/max_storage
    qn  = h['req_M']/max_req
    print(f"  {h['id']:12} {cn:>10.3f} {rn:>10.3f} {sn:>10.3f} {qn:>10.3f} {h['alloc_weight']:>10.2f}")

# 4 khoản chi phí data center
dc_sources = [
    {'id': 'DC_DIEN',   'amount': 480_000_000, 'ten': 'Chi phí điện DC'},
    {'id': 'DC_COOLING','amount': 240_000_000, 'ten': 'Làm mát DC'},
    {'id': 'DC_BANDWIDTH','amount':180_000_000,'ten': 'Băng thông Internet'},
    {'id': 'DC_QUANLY', 'amount': 120_000_000, 'ten': 'Quản lý vận hành DC'},
]

results_21 = {}
for src in dc_sources:
    results_21[src['id']] = allocate([src], he_thong, 'weight')
    print(f"\n  [{src['id']}] {src['ten']}:")
    results_21[src['id']].print_by_source([src], label_key='ten')

section("TỔNG HỢP — Chi phí DC theo hệ thống (composite weight)")
tong_per_ht = {h['id']: 0.0 for h in he_thong}
for r in results_21.values():
    for hid, v in r.target_totals.items():
        tong_per_ht[hid] += v

ht_ids   = [h['id'] for h in he_thong]
src_ids  = [s['id'] for s in dc_sources]
src_names= [s['ten'][:12] for s in dc_sources]
data_rows= [[results_21[sid].target_totals.get(hid, 0) for hid in ht_ids] for sid in src_ids]
print_matrix(ht_ids, src_names, data_rows, col_w=13)
total_dc = sum(s['amount'] for s in dc_sources)
verify_total("DC total", list(results_21.values()), total_dc)

# Chi phí per CPU-core (phân tích hiệu quả)
print(f"\n  Phân tích hiệu quả — CP/CPU-core:")
for h in he_thong:
    cp_ht = tong_per_ht[h['id']]
    print(f"    {h['id']:10} weight={h['alloc_weight']:6.2f}  CP={cp_ht:>14,.0f}  CP/core={cp_ht/h['cpu']:>12,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
title("22 · MIXED 4 TẦNG ưu tiên: amount → manual_pct → weight → equal")
# ══════════════════════════════════════════════════════════════════════════════
"""
Tình huống: Chi phí overhead công ty 800M phân bổ cho 8 business unit.
Ưu tiên (từ cao đến thấp):
  Tầng 1: alloc_amount   — BU ký hợp đồng SLA cố định
  Tầng 2: manual_pct     — BU theo chiến lược CFO
  Tầng 3: alloc_weight   — BU còn lại theo headcount
  Tầng 4: equal          — BU không có dữ liệu nào
Engine 'mixed' xử lý tầng 1+2 trực tiếp;
tầng 3+4 cần chạy 2 lần allocate (residual từng loại).
"""
section("Dữ liệu 8 Business Unit")
bu_list = [
    {'id': 'BU_KD',  'ten': 'Kinh doanh',     'headcount': 120},
    {'id': 'BU_SX',  'ten': 'Sản xuất',        'headcount': 450},
    {'id': 'BU_RD',  'ten': 'R&D',             'headcount':  80},
    {'id': 'BU_MKT', 'ten': 'Marketing',       'headcount':  60},
    {'id': 'BU_IT',  'ten': 'IT',              'headcount':  45},
    {'id': 'BU_HR',  'ten': 'Nhân sự',         'headcount':  35},
    {'id': 'BU_FIN', 'ten': 'Tài chính',       'headcount':  40},
    {'id': 'BU_LOG', 'ten': 'Logistics',       'headcount':  90},
]
OVERHEAD_TOTAL = 800_000_000

# Cấu hình phân bổ từng BU
config_22 = {
    # id          → (tiêu thức, giá trị)
    'BU_KD':  ('alloc_amount', 120_000_000),   # SLA cố định
    'BU_SX':  ('alloc_amount', 200_000_000),   # SLA cố định — lớn nhất
    'BU_RD':  ('manual_pct',   15),            # CFO: 15% chiến lược
    'BU_MKT': ('manual_pct',    8),            # CFO: 8%
    'BU_IT':  ('alloc_weight', None),          # theo headcount
    'BU_HR':  ('alloc_weight', None),          # theo headcount
    'BU_FIN': ('alloc_weight', None),          # theo headcount
    'BU_LOG': ('equal',        None),          # không có dữ liệu
}

# Tính toán thủ công để demo từng tầng
manual_amount_total = sum(v for tp, v in config_22.values() if tp == 'alloc_amount')
manual_pct_total    = sum(v for tp, v in config_22.values() if tp == 'manual_pct')
residual_after_manual = OVERHEAD_TOTAL - manual_amount_total
manual_pct_amount   = OVERHEAD_TOTAL * (manual_pct_total / 100)
residual_for_weight_equal = OVERHEAD_TOTAL - manual_amount_total - manual_pct_amount

weight_bus  = [b for b in bu_list if config_22[b['id']][0] == 'alloc_weight']
equal_bus   = [b for b in bu_list if config_22[b['id']][0] == 'equal']
total_hc_weight = sum(b['headcount'] for b in weight_bus)

# Một lần allocate duy nhất dùng mixed
# Cách implement: tất cả trong 1 allocate, engine tự xử lý ưu tiên
section("Bước 1 — Tầng 1+2: alloc_amount và manual_pct (mixed engine)")
src_22 = [{'id': 'OVERHEAD', 'amount': OVERHEAD_TOTAL, 'ten': 'Chi phí overhead 800M'}]

# Tầng 1+2 dùng mixed
tgt_22_mixed = []
for b in bu_list:
    tp, val = config_22[b['id']]
    t = dict(b)
    if tp == 'alloc_amount':  t['alloc_amount'] = val
    elif tp == 'manual_pct':  t['manual_pct']   = val
    elif tp == 'alloc_weight':t['qty']           = b['headcount']  # residual theo qty
    elif tp == 'equal':       pass  # chỉ chia equal, không có qty
    tgt_22_mixed.append(t)

r22 = allocate(src_22, tgt_22_mixed, method='mixed', mixed_residual_method='qty')
r22.print_by_source(src_22, label_key='ten')

section("Phân tích từng tầng")
g22 = r22.group_by_source(src_22)['OVERHEAD']['allocated_to']
by_method = {}
for item in g22:
    m = item['method']
    by_method.setdefault(m, []).append(item)

for method, items in sorted(by_method.items()):
    total_m = sum(i['allocated'] for i in items)
    print(f"\n  [{method}]  tổng={total_m:,.0f}")
    for i in items:
        stage = i['meta'].get('mixed_stage', '')
        print(f"    {i['target_id']:10}  {i['allocated']:>14,.0f}  stage={stage}")

verify_total("22 overhead", [r22], OVERHEAD_TOTAL)

section("Phân tích: CP overhead / headcount")
print(f"\n  {'BU':10} {'Tiêu thức':15} {'Headcount':>11} {'Nhận':>16} {'CP/head':>12}")
print(f"  {'─'*66}")
for b in bu_list:
    tp, val = config_22[b['id']]
    allocated = r22.target_totals.get(b['id'], 0)
    per_head  = allocated / b['headcount'] if b['headcount'] > 0 else 0
    print(f"  {b['id']:10} {tp:15} {b['headcount']:>11} {allocated:>16,.0f} {per_head:>12,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
title("23 · CROSS-ALLOCATION — Phòng hỗ trợ phân bổ lẫn nhau (Step-down)")
# ══════════════════════════════════════════════════════════════════════════════
"""
Tình huống: 3 phòng hỗ trợ (IT, HR, Finance) phân bổ chi phí cho nhau
trước khi phân về 4 bộ phận sản xuất (A, B, C, D).

Step-down method (phân bổ tuần tự, không quay lui):
  Bước 1: Finance → IT, HR, A, B, C, D  (% service usage)
  Bước 2: HR (+ phần từ Finance) → IT, A, B, C, D
  Bước 3: IT (+ phần từ Finance + HR) → A, B, C, D

Thứ tự step-down: Finance → HR → IT (theo mức độ phục vụ)
"""
section("Chi phí ban đầu 3 phòng hỗ trợ")
FINANCE_ORIG = 360_000_000
HR_ORIG      = 280_000_000
IT_ORIG      = 420_000_000

print(f"  Finance (nguyên gốc): {FINANCE_ORIG:>15,.0f}")
print(f"  HR      (nguyên gốc): {HR_ORIG:>15,.0f}")
print(f"  IT      (nguyên gốc): {IT_ORIG:>15,.0f}")
print(f"  TỔNG:                 {FINANCE_ORIG+HR_ORIG+IT_ORIG:>15,.0f}")

# Tỷ lệ sử dụng dịch vụ (% service usage matrix)
# Finance phục vụ: IT=5%, HR=8%, A=30%, B=25%, C=20%, D=12%
# HR phục vụ (sau Finance):    IT=10%, A=35%, B=28%, C=15%, D=12%
# IT phục vụ (sau Finance+HR): A=40%, B=30%, C=20%, D=10%

section("Bước 1 — Finance phân bổ xuống IT, HR và các bộ phận sản xuất")
src_fin = [{'id': 'FIN', 'amount': FINANCE_ORIG, 'ten': 'Finance dept'}]
tgt_fin = [
    {'id': 'IT',  'alloc_pct':  5, 'ten': 'IT'},
    {'id': 'HR',  'alloc_pct':  8, 'ten': 'HR'},
    {'id': 'BPA', 'alloc_pct': 30, 'ten': 'Sản xuất A'},
    {'id': 'BPB', 'alloc_pct': 25, 'ten': 'Sản xuất B'},
    {'id': 'BPC', 'alloc_pct': 20, 'ten': 'Sản xuất C'},
    {'id': 'BPD', 'alloc_pct': 12, 'ten': 'Sản xuất D'},
]  # tổng = 100%
r23_fin = allocate(src_fin, tgt_fin, 'pct')
r23_fin.print_by_source(src_fin, label_key='ten')

fin_to_it = r23_fin.target_totals['IT']
fin_to_hr = r23_fin.target_totals['HR']
hr_total  = HR_ORIG + fin_to_hr
it_total  = IT_ORIG + fin_to_it
print(f"\n  Finance→IT: {fin_to_it:,.0f}  →  IT total now: {it_total:,.0f}")
print(f"  Finance→HR: {fin_to_hr:,.0f}  →  HR total now: {hr_total:,.0f}")

section("Bước 2 — HR (gốc + nhận từ Finance) phân bổ xuống IT và sản xuất")
src_hr = [{'id': 'HR_TOTAL', 'amount': hr_total, 'ten': f'HR (gốc+Finance = {hr_total:,.0f})'}]
tgt_hr = [
    {'id': 'IT',  'alloc_pct': 10, 'ten': 'IT'},
    {'id': 'BPA', 'alloc_pct': 35, 'ten': 'Sản xuất A'},
    {'id': 'BPB', 'alloc_pct': 28, 'ten': 'Sản xuất B'},
    {'id': 'BPC', 'alloc_pct': 15, 'ten': 'Sản xuất C'},
    {'id': 'BPD', 'alloc_pct': 12, 'ten': 'Sản xuất D'},
]  # tổng = 100%
r23_hr = allocate(src_hr, tgt_hr, 'pct')
r23_hr.print_by_source(src_hr, label_key='ten')

hr_to_it = r23_hr.target_totals['IT']
it_total += hr_to_it
print(f"\n  HR→IT: {hr_to_it:,.0f}  →  IT total now: {it_total:,.0f}")

section("Bước 3 — IT (gốc + nhận từ Finance + HR) phân bổ xuống sản xuất")
src_it = [{'id': 'IT_TOTAL', 'amount': it_total, 'ten': f'IT (gốc+Finance+HR = {it_total:,.0f})'}]
tgt_it = [
    {'id': 'BPA', 'alloc_pct': 40, 'ten': 'Sản xuất A'},
    {'id': 'BPB', 'alloc_pct': 30, 'ten': 'Sản xuất B'},
    {'id': 'BPC', 'alloc_pct': 20, 'ten': 'Sản xuất C'},
    {'id': 'BPD', 'alloc_pct': 10, 'ten': 'Sản xuất D'},
]
r23_it = allocate(src_it, tgt_it, 'pct')
r23_it.print_by_source(src_it, label_key='ten')

section("TỔNG HỢP CROSS-ALLOCATION — Bộ phận sản xuất nhận cuối cùng")
bp_ids   = ['BPA', 'BPB', 'BPC', 'BPD']
bp_names = {'BPA':'Sản xuất A','BPB':'Sản xuất B','BPC':'Sản xuất C','BPD':'Sản xuất D'}
tong_cuoi = {bp: 0.0 for bp in bp_ids}

for r, label in [(r23_fin,'Finance'), (r23_hr,'HR'), (r23_it,'IT')]:
    for bp in bp_ids:
        v = r.target_totals.get(bp, 0)
        tong_cuoi[bp] += v

print(f"\n  {'BP':12} {'Từ Finance':>14} {'Từ HR':>14} {'Từ IT':>14} {'TỔNG':>14}")
print(f"  {'─'*68}")
grand23 = 0.0
for bp in bp_ids:
    vf = r23_fin.target_totals.get(bp, 0)
    vh = r23_hr.target_totals.get(bp, 0)
    vi = r23_it.target_totals.get(bp, 0)
    tt = vf + vh + vi
    grand23 += tt
    print(f"  {bp_names[bp]:12} {vf:>14,.0f} {vh:>14,.0f} {vi:>14,.0f} {tt:>14,.0f}")
print(f"  {'─'*68}")
print(f"  {'TỔNG':12} {'':>14} {'':>14} {'':>14} {grand23:>14,.0f}")
expected23 = FINANCE_ORIG + HR_ORIG + IT_ORIG
ok(f"Tổng phân về sản xuất = tổng gốc 3 phòng", f"{grand23:,.0f} = {expected23:,.0f} {'✓' if abs(grand23-expected23)<1 else '⚠'}")


# ══════════════════════════════════════════════════════════════════════════════
title("24 · CASCADE 3 CẤP — Tập đoàn → Công ty → Phòng ban → Sản phẩm")
# ══════════════════════════════════════════════════════════════════════════════
"""
Tập đoàn có 4 công ty thành viên, mỗi công ty có 3 phòng ban,
mỗi phòng ban có 2-4 dòng sản phẩm.

CẤP 1: Chi phí tập đoàn → Công ty (weight = doanh thu × hệ số rủi ro)
CẤP 2: Chi phí công ty (gốc + từ TĐ) → Phòng ban (mixed: SLA + qty)
CẤP 3: Chi phí phòng ban → Sản phẩm (amount = doanh thu sản phẩm)
"""

section("Dữ liệu tập đoàn")
# Công ty
cty = [
    {'id': 'CTY_A', 'ten': 'Công ty Công nghệ',  'dt': 850_000_000_000, 'he_so_rr': 1.2, 'cp_goc': 2_400_000_000},
    {'id': 'CTY_B', 'ten': 'Công ty Sản xuất',   'dt': 620_000_000_000, 'he_so_rr': 1.5, 'cp_goc': 3_200_000_000},
    {'id': 'CTY_C', 'ten': 'Công ty Bán lẻ',     'dt': 430_000_000_000, 'he_so_rr': 1.0, 'cp_goc': 1_800_000_000},
    {'id': 'CTY_D', 'ten': 'Công ty Bất động sản','dt': 280_000_000_000, 'he_so_rr': 1.8, 'cp_goc': 1_200_000_000},
]
CP_TAPDO = 1_200_000_000  # Chi phí tập đoàn cần phân bổ

for c in cty:
    c['alloc_weight'] = round(c['dt'] / 1e9 * c['he_so_rr'], 1)  # tỷ đồng × hệ số rủi ro

print(f"\n  {'Công ty':15} {'DT (tỷ)':>10} {'H.S rủi ro':>12} {'Weight':>10} {'CP gốc':>16}")
print(f"  {'─'*65}")
for c in cty:
    print(f"  {c['id']:15} {c['dt']/1e9:>10.0f} {c['he_so_rr']:>12.1f} {c['alloc_weight']:>10.1f} {c['cp_goc']:>16,.0f}")

# CẤP 1
section("CẤP 1 — Chi phí tập đoàn → Công ty (weight = DT × hệ số rủi ro)")
src_td = [{'id': 'CP_TAPDO', 'amount': CP_TAPDO, 'ten': 'Chi phí tập đoàn'}]
r24_cap1 = allocate(src_td, cty, 'weight')
r24_cap1.print_by_source(src_td, label_key='ten')

# CẤP 2: mỗi công ty phân về phòng ban
section("CẤP 2 — Chi phí công ty (gốc + từ TĐ) → Phòng ban (mixed: SLA + headcount)")

# Phòng ban của mỗi công ty
pb_by_cty = {
    'CTY_A': [
        {'id': 'A_DEV',   'ten': 'Dev team',        'headcount': 120, 'alloc_amount': 300_000_000},
        {'id': 'A_SALES', 'ten': 'Sales',            'headcount':  60},
        {'id': 'A_OPS',   'ten': 'Operations',       'headcount':  45},
    ],
    'CTY_B': [
        {'id': 'B_SX1',   'ten': 'Xưởng 1',         'headcount': 200, 'alloc_amount': 800_000_000},
        {'id': 'B_SX2',   'ten': 'Xưởng 2',         'headcount': 180},
        {'id': 'B_QA',    'ten': 'Kiểm soát CL',     'headcount':  50, 'manual_pct': 10},
    ],
    'CTY_C': [
        {'id': 'C_HN',    'ten': 'Miền Bắc',         'headcount':  80, 'manual_pct': 35},
        {'id': 'C_HCM',   'ten': 'Miền Nam',          'headcount':  95, 'manual_pct': 45},
        {'id': 'C_MT',    'ten': 'Miền Trung',        'headcount':  40},
    ],
    'CTY_D': [
        {'id': 'D_DV1',   'ten': 'Dự án 1',          'headcount':  30, 'alloc_amount': 400_000_000},
        {'id': 'D_DV2',   'ten': 'Dự án 2',          'headcount':  25},
        {'id': 'D_DV3',   'ten': 'Dự án 3',          'headcount':  20},
    ],
}

r24_cap2 = {}
tong_per_pb = {}

for c in cty:
    cid = c['id']
    cp_tu_td = r24_cap1.target_totals[cid]
    total_cp_cty = c['cp_goc'] + cp_tu_td
    src_cty = [{'id': cid, 'amount': total_cp_cty,
                'ten': f"{c['ten']} (gốc {c['cp_goc']/1e9:.1f}B + TĐ {cp_tu_td/1e9:.2f}B)"}]
    # Thêm qty = headcount cho residual
    tgt_pb = []
    for pb in pb_by_cty[cid]:
        t = dict(pb)
        if 'alloc_amount' not in t and 'manual_pct' not in t:
            t['qty'] = t['headcount']
        tgt_pb.append(t)

    r = allocate(src_cty, tgt_pb, method='mixed', mixed_residual_method='qty')
    r24_cap2[cid] = r
    for pbid, v in r.target_totals.items():
        tong_per_pb[pbid] = v
    print(f"\n  {c['ten']:20} (tổng={total_cp_cty:,.0f}):")
    r.print_by_source(src_cty, label_key='ten')

# CẤP 3: mỗi phòng ban phân về sản phẩm
section("CẤP 3 — Chi phí phòng ban → Sản phẩm (theo doanh thu sản phẩm)")

# Sản phẩm của từng phòng ban
sp_by_pb = {
    'A_DEV':   [{'id': 'SP_ERP',  'amount': 200_000_000_000},
                {'id': 'SP_APP',  'amount': 150_000_000_000},
                {'id': 'SP_SAAS', 'amount': 100_000_000_000}],
    'A_SALES': [{'id': 'SP_ERP',  'amount': 200_000_000_000},
                {'id': 'SP_APP',  'amount': 150_000_000_000}],
    'A_OPS':   [{'id': 'SP_ERP',  'amount': 200_000_000_000},
                {'id': 'SP_SAAS', 'amount': 100_000_000_000}],
    'B_SX1':   [{'id': 'SP_CKH',  'amount': 320_000_000_000},
                {'id': 'SP_DT',   'amount': 180_000_000_000}],
    'B_SX2':   [{'id': 'SP_DT',   'amount': 180_000_000_000},
                {'id': 'SP_OCK',  'amount': 120_000_000_000}],
    'B_QA':    [{'id': 'SP_CKH',  'amount': 320_000_000_000},
                {'id': 'SP_DT',   'amount': 180_000_000_000},
                {'id': 'SP_OCK',  'amount': 120_000_000_000}],
    'C_HN':    [{'id': 'SP_FMCG1','amount':  80_000_000_000},
                {'id': 'SP_FMCG2','amount':  60_000_000_000}],
    'C_HCM':   [{'id': 'SP_FMCG1','amount':  80_000_000_000},
                {'id': 'SP_FMCG2','amount':  60_000_000_000},
                {'id': 'SP_FMCG3','amount':  40_000_000_000}],
    'C_MT':    [{'id': 'SP_FMCG1','amount':  80_000_000_000},
                {'id': 'SP_FMCG3','amount':  40_000_000_000}],
    'D_DV1':   [{'id': 'SP_BDS1', 'amount': 120_000_000_000}],
    'D_DV2':   [{'id': 'SP_BDS2', 'amount':  90_000_000_000}],
    'D_DV3':   [{'id': 'SP_BDS3', 'amount':  70_000_000_000}],
}

tong_per_sp24 = {}
r24_cap3 = {}
for pbid, pb_cp in tong_per_pb.items():
    if pbid not in sp_by_pb: continue
    src_pb = [{'id': pbid, 'amount': pb_cp, 'ten': pbid}]
    r = allocate(src_pb, sp_by_pb[pbid], 'amount')
    r24_cap3[pbid] = r
    for spid, v in r.target_totals.items():
        tong_per_sp24[spid] = tong_per_sp24.get(spid, 0) + v

section("TỔNG HỢP CUỐI — Chi phí đến từng sản phẩm (3 cấp cascade)")
tong_source = CP_TAPDO + sum(c['cp_goc'] for c in cty)
print(f"\n  Tổng nguồn (TĐ + 4 Cty): {tong_source:,.0f}")
print(f"\n  {'Sản phẩm':12} {'CP cuối':>18} {'% tổng':>10}")
print(f"  {'─'*42}")
tong_sp24 = sum(tong_per_sp24.values())
for spid, v in sorted(tong_per_sp24.items()):
    print(f"  {spid:12} {v:>18,.0f} {v/tong_sp24*100:>9.2f}%")
print(f"  {'─'*42}")
print(f"  {'TỔNG':12} {tong_sp24:>18,.0f} {'100.00%':>10}")
verify_total("Cascade 3 cấp (CP cuối về SP = tổng nguồn gốc)",
             list(r24_cap3.values()),
             CP_TAPDO + sum(c['cp_goc'] for c in cty))


# ══════════════════════════════════════════════════════════════════════════════
title("25 · MULTI-SOURCE × MULTI-TARGET × 7 TIÊU THỨC KHÁC NHAU")
# ══════════════════════════════════════════════════════════════════════════════
"""
Tình huống: Nhà máy sản xuất điện tử — tháng báo cáo.
10 khoản chi phí, mỗi khoản dùng 1 tiêu thức riêng,
phân bổ vào 12 dòng sản phẩm.
"""

section("Dữ liệu 12 dòng sản phẩm")
sp12 = [
    {'id':'TV32','ten':'TV 32"',       'qty':2000,'dt':6_400_000_000,'gio_may':800, 'gio_cong':600, 'dien_tich':200,'he_so_kh':1.0,'nvl':4_000_000_000},
    {'id':'TV55','ten':'TV 55"',       'qty': 800,'dt':5_600_000_000,'gio_may':700, 'gio_cong':500, 'dien_tich':200,'he_so_kh':1.5,'nvl':3_200_000_000},
    {'id':'TV75','ten':'TV 75"',       'qty': 300,'dt':4_500_000_000,'gio_may':600, 'gio_cong':400, 'dien_tich':200,'he_so_kh':2.0,'nvl':2_800_000_000},
    {'id':'TL14','ten':'Laptop 14"',   'qty':1500,'dt':9_000_000_000,'gio_may':1200,'gio_cong':900, 'dien_tich':150,'he_so_kh':1.8,'nvl':5_500_000_000},
    {'id':'TL16','ten':'Laptop 16"',   'qty': 800,'dt':7_200_000_000,'gio_may':900, 'gio_cong':700, 'dien_tich':150,'he_so_kh':2.0,'nvl':4_200_000_000},
    {'id':'MB_A','ten':'Máy bảng A',   'qty':3000,'dt':6_000_000_000,'gio_may':600, 'gio_cong':800, 'dien_tich':100,'he_so_kh':1.2,'nvl':3_000_000_000},
    {'id':'MB_B','ten':'Máy bảng B',   'qty':1200,'dt':3_600_000_000,'gio_may':400, 'gio_cong':500, 'dien_tich':100,'he_so_kh':1.3,'nvl':2_000_000_000},
    {'id':'DT_A','ten':'Điện thoại A', 'qty':8000,'dt':8_000_000_000,'gio_may':400, 'gio_cong':1200,'dien_tich': 80,'he_so_kh':1.0,'nvl':4_800_000_000},
    {'id':'DT_B','ten':'Điện thoại B', 'qty':5000,'dt':3_500_000_000,'gio_may':300, 'gio_cong':800, 'dien_tich': 80,'he_so_kh':0.9,'nvl':2_500_000_000},
    {'id':'PCB1','ten':'Bo mạch PCB-1','qty': 500,'dt':1_500_000_000,'gio_may':200, 'gio_cong':300, 'dien_tich': 60,'he_so_kh':1.1,'nvl':  900_000_000},
    {'id':'PCB2','ten':'Bo mạch PCB-2','qty': 400,'dt':2_000_000_000,'gio_may':300, 'gio_cong':400, 'dien_tich': 60,'he_so_kh':1.4,'nvl':1_200_000_000},
    {'id':'ACC', 'ten':'Phụ kiện mix', 'qty':12000,'dt':2_400_000_000,'gio_may':200,'gio_cong':600, 'dien_tich':120,'he_so_kh':0.8,'nvl':1_200_000_000},
]

print(f"\n  {'SP':8} {'qty':>6} {'DT(tỷ)':>9} {'GiờMáy':>9} {'GiờCông':>9} {'DT(m²)':>8} {'NVL(tỷ)':>9}")
print(f"  {'─'*66}")
for s in sp12:
    print(f"  {s['id']:8} {s['qty']:>6,} {s['dt']/1e9:>9.1f} {s['gio_may']:>9,} {s['gio_cong']:>9,} {s['dien_tich']:>8} {s['nvl']/1e9:>9.1f}")

section("10 khoản chi phí × 7 tiêu thức khác nhau")
chi_phi_25 = [
    # (id, tên, số tiền, tiêu thức, field tiêu thức, kwargs)
    ('KH_MAY_A',  'Khấu hao máy dây chuyền A', 2_800_000_000, 'weight',
     lambda s: s['gio_may'] * s['he_so_kh'], 'alloc_weight', {}),
    ('KH_MAY_B',  'Khấu hao máy dây chuyền B', 1_900_000_000, 'weight',
     lambda s: s['gio_may'] * s['he_so_kh'], 'alloc_weight', {}),
    ('LUONG_CN',  'Lương công nhân trực tiếp',  4_200_000_000, 'qty',
     lambda s: s['gio_cong'], 'qty', {}),
    ('LUONG_GT',  'Lương gián tiếp sản xuất',   1_800_000_000, 'qty',
     lambda s: s['gio_cong'], 'qty', {}),
    ('DIEN_NM',   'Điện nhà máy',               1_200_000_000, 'weight',
     lambda s: s['gio_may'], 'alloc_weight', {}),
    ('NUOC_VS',   'Nước + vệ sinh',               360_000_000, 'weight',
     lambda s: s['dien_tich'], 'alloc_weight', {}),
    ('NVL_PHU',   'NVL phụ trợ',                2_400_000_000, 'amount',
     lambda s: s['nvl'], 'amount', {}),
    ('QL_NM',     'Quản lý nhà máy',              960_000_000, 'equal',
     None, None, {}),
    ('KCS',       'Kiểm tra chất lượng (KCS)',    480_000_000, 'qty',
     lambda s: s['qty'], 'qty', {}),
    ('VAN_CHUYEN','Vận chuyển nội bộ',            720_000_000, 'amount',
     lambda s: s['dt'], 'amount', {}),
]

results_25 = {}
for cp_id, cp_ten, cp_amt, method, field_fn, field_key, extra in chi_phi_25:
    src = [{'id': cp_id, 'amount': cp_amt, 'ten': cp_ten}]
    if method == 'equal' or field_fn is None:
        tgt = sp12
    else:
        tgt = [{**s, field_key: field_fn(s)} for s in sp12]
    r = allocate(src, tgt, method, **extra)
    results_25[cp_id] = r
    print(f"\n  [{cp_id}] {cp_ten} ({method}):  {cp_amt:,.0f}")
    r.print_by_source(src, label_key='ten')

section("BẢNG TỔNG HỢP 10×12 — Chi phí theo sản phẩm")
sp_ids25  = [s['id'] for s in sp12]
cp_ids25  = [x[0] for x in chi_phi_25]
cp_names  = [x[1][:14] for x in chi_phi_25]
total_per_sp = {sid: 0.0 for sid in sp_ids25}

# In matrix 10×12
col_w25 = 10
print(f"\n  {'Chi phí':16}" + "".join(f"{sid:>{col_w25}}" for sid in sp_ids25) + f"{'TỔNG':>{col_w25+2}}")
print(f"  {'─'*( 16 + col_w25*(len(sp_ids25)+1) + 2 )}")
tong_tong25 = 0.0
for cp_id, cp_name, _, _, _, _, _ in chi_phi_25:
    r = results_25[cp_id]
    row_vals = [r.target_totals.get(sid, 0) for sid in sp_ids25]
    row_total = sum(row_vals)
    tong_tong25 += row_total
    print(f"  {cp_name:16}" + "".join(f"{v:>{col_w25},.0f}" for v in row_vals) + f"{row_total:>{col_w25+2},.0f}")
    for sid, v in zip(sp_ids25, row_vals):
        total_per_sp[sid] += v

print(f"  {'─'*( 16 + col_w25*(len(sp_ids25)+1) + 2 )}")
tot_row = f"  {'TỔNG CP':16}" + "".join(f"{total_per_sp[sid]:>{col_w25},.0f}" for sid in sp_ids25) + f"{tong_tong25:>{col_w25+2},.0f}"
print(tot_row)

section("Phân tích CP / Doanh thu và CP / sản phẩm")
print(f"\n  {'SP':8} {'CP tổng':>16} {'DT':>16} {'CP/DT%':>8} {'qty':>8} {'CP/SP':>14}")
print(f"  {'─'*72}")
for s in sp12:
    cp  = total_per_sp[s['id']]
    dt  = s['dt']
    qty = s['qty']
    print(f"  {s['id']:8} {cp:>16,.0f} {dt:>16,.0f} {cp/dt*100:>7.2f}% {qty:>8,} {cp/qty:>14,.0f}")

expected25 = sum(x[2] for x in chi_phi_25)
verify_total("25 multi-source", list(results_25.values()), expected25)


# ══════════════════════════════════════════════════════════════════════════════
title("26 · MIXED TẤT CẢ 4 LOẠI TRONG 1 ALLOCATE")
# ══════════════════════════════════════════════════════════════════════════════
"""
Tình huống: Chi phí vận hành kho 600M phân bổ cho 12 khách hàng.
Mỗi khách hàng có 1 tiêu thức khác nhau:
  KH01-KH03: alloc_amount  (hợp đồng SLA cố định)
  KH04-KH06: manual_pct    (% theo thỏa thuận dài hạn)
  KH07-KH09: alloc_weight  (theo diện tích kho thuê)
  KH10-KH12: equal         (khách mới, chưa có dữ liệu)
"""
section("12 khách hàng, 4 loại tiêu thức khác nhau")
TONG_KHO = 600_000_000

khach_hang = [
    # SLA cố định
    {'id':'KH01','ten':'KH Lớn A',    'alloc_amount': 120_000_000},
    {'id':'KH02','ten':'KH Lớn B',    'alloc_amount':  90_000_000},
    {'id':'KH03','ten':'KH Lớn C',    'alloc_amount':  60_000_000},
    # % thỏa thuận
    {'id':'KH04','ten':'KH Vừa D',    'manual_pct': 8},
    {'id':'KH05','ten':'KH Vừa E',    'manual_pct': 6},
    {'id':'KH06','ten':'KH Vừa F',    'manual_pct': 4},
    # Diện tích kho
    {'id':'KH07','ten':'KH Weight G', 'alloc_weight': 800},
    {'id':'KH08','ten':'KH Weight H', 'alloc_weight': 500},
    {'id':'KH09','ten':'KH Weight I', 'alloc_weight': 300},
    # Mới, chia đều
    {'id':'KH10','ten':'KH Mới J',    'qty': 1},   # qty=1 cho equal giả
    {'id':'KH11','ten':'KH Mới K',    'qty': 1},
    {'id':'KH12','ten':'KH Mới L',    'qty': 1},
]

# Kiểm tra tổng trước
manual_a = sum(kh.get('alloc_amount', 0) for kh in khach_hang)
manual_p = sum(kh.get('manual_pct', 0) for kh in khach_hang)
print(f"  Tổng alloc_amount: {manual_a:,} ({manual_a/TONG_KHO*100:.1f}% tổng)")
print(f"  Tổng manual_pct:   {manual_p}% ({TONG_KHO*manual_p/100:,.0f})")
print(f"  Residual (weight+equal): {TONG_KHO - manual_a - TONG_KHO*manual_p/100:,.0f}")

src_26 = [{'id': 'CHI_PHI_KHO', 'amount': TONG_KHO, 'ten': 'Chi phí vận hành kho'}]
r26 = allocate(src_26, khach_hang, method='mixed', mixed_residual_method='weight')
r26.print_by_source(src_26, label_key='ten')

section("Chi tiết method từng khách hàng")
g26 = r26.group_by_source(src_26)['CHI_PHI_KHO']['allocated_to']
print(f"\n  {'KH':8} {'Method':35} {'Allocated':>16} {'Stage':>12}")
print(f"  {'─'*74}")
for item in g26:
    stage = item['meta'].get('mixed_stage', 'n/a')
    print(f"  {item['target_id']:8} {item['method']:35} {item['allocated']:>16,.0f} {stage:>12}")

verify_total("26 mixed all types", [r26], TONG_KHO)

section("Phân tích bình đẳng: CP/KH theo nhóm")
groups = [
    ('SLA cố định',  ['KH01','KH02','KH03']),
    ('% thỏa thuận', ['KH04','KH05','KH06']),
    ('Trọng số DT',  ['KH07','KH08','KH09']),
    ('Chia đều',     ['KH10','KH11','KH12']),
]
for gname, ids in groups:
    vals   = [r26.target_totals.get(i, 0) for i in ids]
    tong_g = sum(vals)
    avg_g  = tong_g / len(ids)
    print(f"  {gname:18}: tổng={tong_g:>14,.0f}  avg={avg_g:>14,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
title("27 · PHÂN BỔ VÒNG LẶP — Dịch vụ nội bộ lẫn nhau (Iterative)")
# ══════════════════════════════════════════════════════════════════════════════
"""
Tình huống: 4 bộ phận hỗ trợ cung cấp dịch vụ cho nhau VÀ cho 3 bộ phận sản xuất.
Ma trận dịch vụ (% cung cấp):

          IT    HR    FIN   LEGAL  SX1   SX2   SX3
IT         0    10    15      5    30    25    15
HR        10     0    20      5    25    25    15
FIN        5    15     0     10    30    25    15
LEGAL      8    12    10      0    25    25    20

Iterative allocation (lặp đến hội tụ):
Cho đến khi phần còn lại của bộ phận hỗ trợ < 0.1% ban đầu.
"""
section("Chi phí gốc 4 bộ phận hỗ trợ")
bo_phan = {
    'IT':    500_000_000,
    'HR':    380_000_000,
    'FIN':   420_000_000,
    'LEGAL': 290_000_000,
}
total_goc27 = sum(bo_phan.values())

# Ma trận % (hàng = từ, cột = đến)
matrix_pct = {
    'IT':    {'IT': 0,  'HR': 10, 'FIN': 15, 'LEGAL':  5, 'SX1': 30, 'SX2': 25, 'SX3': 15},
    'HR':    {'IT': 10, 'HR':  0, 'FIN': 20, 'LEGAL':  5, 'SX1': 25, 'SX2': 25, 'SX3': 15},
    'FIN':   {'IT':  5, 'HR': 15, 'FIN':  0, 'LEGAL': 10, 'SX1': 30, 'SX2': 25, 'SX3': 15},
    'LEGAL': {'IT':  8, 'HR': 12, 'FIN': 10, 'LEGAL':  0, 'SX1': 25, 'SX2': 25, 'SX3': 20},
}

print(f"\n  Tổng CP gốc: {total_goc27:,}")
for bp, cp in bo_phan.items():
    print(f"    {bp:6}: {cp:,}")

# Iterative allocation
print(f"\n  Ma trận phân bổ (%):")
all_units = ['IT', 'HR', 'FIN', 'LEGAL', 'SX1', 'SX2', 'SX3']
support   = ['IT', 'HR', 'FIN', 'LEGAL']
sx_units  = ['SX1', 'SX2', 'SX3']

print(f"  {'':8}" + "".join(f"{u:>7}" for u in all_units))
for s in support:
    row_str = f"  {s:8}"
    row_sum = sum(matrix_pct[s].values())
    for u in all_units:
        row_str += f"{matrix_pct[s].get(u,0):>7}"
    row_str += f"  (tổng={row_sum}%)"
    print(row_str)

section("Iterative allocation — lặp đến hội tụ")
# Khởi tạo: pool = cp gốc cho mỗi bộ phận hỗ trợ
pool = {bp: cp for bp, cp in bo_phan.items()}
sx_total = {sx: 0.0 for sx in sx_units}
iterations = 0
MAX_ITER   = 50
THRESHOLD  = 0.001  # 0.1%

while iterations < MAX_ITER:
    iterations += 1
    max_change = 0.0

    for bp in support:
        if pool[bp] < 1:
            continue
        cp_to_distribute = pool[bp]
        pool[bp] = 0.0

        src_iter = [{'id': bp, 'amount': cp_to_distribute}]
        tgt_iter = []
        for u in all_units:
            if u == bp: continue
            pct = matrix_pct[bp].get(u, 0)
            if pct > 0:
                tgt_iter.append({'id': u, 'alloc_pct': pct})

        if not tgt_iter: continue
        r_iter = allocate(src_iter, tgt_iter, 'pct')

        for u in all_units:
            allocated_u = r_iter.target_totals.get(u, 0)
            if allocated_u > 0:
                if u in pool:
                    pool[u] += allocated_u
                    max_change = max(max_change, allocated_u)
                elif u in sx_total:
                    sx_total[u] += allocated_u

    print(f"  Vòng {iterations:3d}: pool={pool}  SX_total={sx_total}")
    if max_change < total_goc27 * THRESHOLD:
        print(f"  → Hội tụ sau {iterations} vòng (max_change={max_change:,.0f} < {total_goc27*THRESHOLD:,.0f})")
        break

section("Kết quả cuối — Bộ phận sản xuất nhận")
tong_sx = sum(sx_total.values())
for sx, v in sx_total.items():
    print(f"  {sx}: {v:>16,.0f}  ({v/tong_sx*100:.1f}%)")
print(f"\n  Tổng về SX:   {tong_sx:>16,.0f}")
print(f"  Tổng gốc:     {total_goc27:>16,.0f}")
print(f"  Còn lại pool: {sum(pool.values()):>16,.2f}")
ok("Hội tụ: SX + pool ≈ tổng gốc",
   f"{tong_sx + sum(pool.values()):,.0f} ≈ {total_goc27:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
title("28 · TẬP ĐOÀN ĐA NGÀNH — 15 nguồn × 18 đích × 9 tiêu thức")
# ══════════════════════════════════════════════════════════════════════════════
"""
Tập đoàn 3 ngành: Công nghệ (5 SP), Sản xuất (8 SP), Dịch vụ (5 SP) = 18 SP.
15 khoản chi phí dùng 9 tiêu thức:
  equal, qty, amount, weight, pct, manual_amount, manual_pct,
  mixed(qty), mixed(amount) + group_key

Đây là bài toán phức tạp nhất: nhiều nguồn, nhiều đích, nhiều tiêu thức,
có group_key, có mixed, có cross-check toàn bộ.
"""

section("18 sản phẩm thuộc 3 ngành")
nganh_cn = [  # Công nghệ
    {'id':'CN_SAAS','ten':'SaaS Platform', 'nganh':'CN','qty':5000,'dt':12_000_000_000,'hc': 80,'gm':  200,'dt_m2':150,'nvl': 2_000_000_000,'kpi': 95},
    {'id':'CN_APP', 'ten':'Mobile App',    'nganh':'CN','qty':8000,'dt': 6_400_000_000,'hc': 60,'gm':  100,'dt_m2': 80,'nvl': 1_200_000_000,'kpi': 88},
    {'id':'CN_IOT', 'ten':'IoT Platform',  'nganh':'CN','qty':2000,'dt': 8_000_000_000,'hc': 90,'gm':  300,'dt_m2':200,'nvl': 3_000_000_000,'kpi': 92},
    {'id':'CN_AI',  'ten':'AI Services',   'nganh':'CN','qty': 500,'dt':10_000_000_000,'hc':120,'gm':  500,'dt_m2':300,'nvl': 4_000_000_000,'kpi': 98},
    {'id':'CN_SEC', 'ten':'Cybersecurity', 'nganh':'CN','qty':1200,'dt': 4_800_000_000,'hc': 50,'gm':  150,'dt_m2':100,'nvl': 1_500_000_000,'kpi': 90},
]
nganh_sx = [  # Sản xuất
    {'id':'SX_TV',  'ten':'TV cao cấp',   'nganh':'SX','qty':3000,'dt':18_000_000_000,'hc':200,'gm':1800,'dt_m2':600,'nvl':10_000_000_000,'kpi': 85},
    {'id':'SX_LT',  'ten':'Laptop',       'nganh':'SX','qty':5000,'dt':30_000_000_000,'hc':300,'gm':2500,'dt_m2':800,'nvl':18_000_000_000,'kpi': 88},
    {'id':'SX_DT',  'ten':'Điện thoại',   'nganh':'SX','qty':20000,'dt':24_000_000_000,'hc':400,'gm':1200,'dt_m2':400,'nvl':15_000_000_000,'kpi': 82},
    {'id':'SX_MB',  'ten':'Máy bảng',     'nganh':'SX','qty':8000,'dt': 9_600_000_000,'hc':150,'gm': 800,'dt_m2':300,'nvl': 6_000_000_000,'kpi': 80},
    {'id':'SX_PCB', 'ten':'PCB boards',   'nganh':'SX','qty':15000,'dt': 4_500_000_000,'hc': 80,'gm': 600,'dt_m2':200,'nvl': 2_500_000_000,'kpi': 75},
    {'id':'SX_ACC', 'ten':'Phụ kiện',     'nganh':'SX','qty':50000,'dt': 5_000_000_000,'hc': 60,'gm': 400,'dt_m2':150,'nvl': 2_000_000_000,'kpi': 78},
    {'id':'SX_BAT', 'ten':'Pin lithium',  'nganh':'SX','qty':30000,'dt': 6_000_000_000,'hc': 70,'gm': 500,'dt_m2':180,'nvl': 3_500_000_000,'kpi': 83},
    {'id':'SX_CAM', 'ten':'Camera module','nganh':'SX','qty':25000,'dt': 5_000_000_000,'hc': 90,'gm': 700,'dt_m2':220,'nvl': 3_000_000_000,'kpi': 86},
]
nganh_dv = [  # Dịch vụ
    {'id':'DV_LOG', 'ten':'Logistics',    'nganh':'DV','qty':10000,'dt': 8_000_000_000,'hc':300,'gm':  100,'dt_m2':500,'nvl': 1_000_000_000,'kpi': 88},
    {'id':'DV_BH',  'ten':'Bảo hiểm',    'nganh':'DV','qty': 5000,'dt':12_000_000_000,'hc':120,'gm':   50,'dt_m2':200,'nvl':   500_000_000,'kpi': 92},
    {'id':'DV_TC',  'ten':'Tài chính',   'nganh':'DV','qty': 2000,'dt':15_000_000_000,'hc':150,'gm':   80,'dt_m2':300,'nvl':   800_000_000,'kpi': 95},
    {'id':'DV_BDS', 'ten':'Bất động sản','nganh':'DV','qty':  500,'dt':20_000_000_000,'hc':200,'gm':  200,'dt_m2':800,'nvl': 2_000_000_000,'kpi': 90},
    {'id':'DV_EDU', 'ten':'Giáo dục',    'nganh':'DV','qty': 3000,'dt': 6_000_000_000,'hc': 80,'gm':   60,'dt_m2':250,'nvl':   400_000_000,'kpi': 85},
]
sp18 = nganh_cn + nganh_sx + nganh_dv

print(f"\n  Tổng: {len(sp18)} sản phẩm  |  3 ngành: CN={len(nganh_cn)}, SX={len(nganh_sx)}, DV={len(nganh_dv)}")
tong_dt28 = sum(s['dt'] for s in sp18)
print(f"  Tổng doanh thu tập đoàn: {tong_dt28:,.0f}")

section("15 khoản chi phí × 9 tiêu thức")
# Composite weight cho KH&IT
for s in sp18:
    s['alloc_weight_kpit'] = round(s['hc'] * 0.5 + s['kpi'] * 0.5, 1)
    s['alloc_weight_gm']   = round(s['gm'] * s['kpi'] / 100, 1)

cp28 = [
    # id, tên, số tiền, method, prep_fn (None = dùng thẳng)
    ('CP_LUONG_QL', 'Lương quản lý TĐ',    3_600_000_000, 'weight',
     lambda s, _: {**s, 'alloc_weight': s['alloc_weight_kpit']}, None),
    ('CP_KH_VP',   'Khấu hao VP TĐ',         960_000_000, 'pct',
     lambda s, i: {**s, 'alloc_pct': [15,12,10,8,5,8,7,6,5,4,3,3,3,3,4,2,1,1][i]}, None),
    ('CP_DIEN',    'Điện VP + server',         720_000_000, 'weight',
     lambda s, _: {**s, 'alloc_weight': s['dt_m2']}, None),
    ('CP_MARKETING','Marketing chung TĐ',    2_400_000_000, 'amount',
     lambda s, _: {**s, 'amount': s['dt']}, None),
    ('CP_IT_CHUNG','IT hạ tầng chung',       1_800_000_000, 'weight',
     lambda s, _: {**s, 'alloc_weight': s['alloc_weight_gm']}, None),
    ('CP_LUONG_SX','Lương CN sản xuất',      8_400_000_000, 'qty',
     lambda s, _: {**s, 'qty': s['hc']}, 'nganh'),  # group_key=nganh → chỉ phân vào SX
    ('CP_KH_MAY',  'Khấu hao máy SX',        5_200_000_000, 'weight',
     lambda s, _: {**s, 'alloc_weight': s['gm']}, 'nganh'),
    ('CP_NVL_PHU', 'NVL phụ',                3_800_000_000, 'amount',
     lambda s, _: {**s, 'amount': s['nvl']}, 'nganh'),
    ('CP_RD',      'R&D toàn tập đoàn',      4_200_000_000, 'manual_pct',
     # % R&D cho 18 SP — tổng = 100%
     # CN(5): SaaS=12, App=8, IoT=10, AI=15, Sec=5  → 50%
     # SX(8): TV=6, LT=8, DT=7, MB=5, PCB=3, ACC=2, BAT=4, CAM=4  → 39%
     # DV(5): Log=3, BH=2, TC=2, BDS=2, Edu=2  → 11%
     lambda s, i: {**s, 'manual_pct': [12,8,10,15,5, 6,8,7,5,3,2,4,4, 3,2,2,2,2][i] if i<18 else 0}, None),
    ('CP_PHAPLUAT','Pháp lý + tuân thủ',       840_000_000, 'equal',
     None, None),
    ('CP_BH_TS',   'Bảo hiểm tài sản',        480_000_000, 'amount',
     lambda s, _: {**s, 'amount': s['nvl']}, None),
    ('CP_TRAVEL',  'Chi phí đi lại TĐ',        360_000_000, 'equal',
     None, None),
    ('CP_MIXED_A', 'CP đặc biệt ngành CN',    1_200_000_000, 'mixed',
     # Chỉ phân vào ngành CN: CN_SAAS+CN_IOT cố định, còn lại theo hc
     lambda s, i: ({**s, 'alloc_amount': [400_000_000,0,300_000_000,0,0][i], 'qty': s['hc']}
                   if s['nganh'] == 'CN'
                   else {**s, 'qty': 0}), None),  # SX/DV qty=0 → không nhận
    ('CP_MIXED_B', 'CP flagship SX',          2_400_000_000, 'mixed',
     # Chỉ phân vào ngành SX: SX_TV+SX_LT flagship cố định, còn lại theo giờ máy
     lambda s, i: ({**s, 'alloc_amount': 600_000_000 if s['id'] in ['SX_TV','SX_LT'] else 0,
                   'qty': s['gm']}
                   if s['nganh'] == 'SX'
                   else {**s, 'qty': 0}), None),
    ('CP_MIXED_C', 'CP đặc thù DV',            720_000_000, 'mixed',
     # Chỉ phân vào ngành DV: DV_TC+DV_BDS manual_pct, còn lại theo hc
     lambda s, i: ({**s, 'manual_pct': {'DV_TC': 30, 'DV_BDS': 40}.get(s['id'], 0),
                   'qty': s['hc']}
                   if s['nganh'] == 'DV'
                   else {**s, 'qty': 0}), None),
]

results_28 = {}
total_per_sp28 = {s['id']: 0.0 for s in sp18}

for entry in cp28:
    cp_id, cp_ten, cp_amt, method, prep_fn, gkey = entry
    src = [{'id': cp_id, 'amount': cp_amt, 'ten': cp_ten, 'nganh': 'ALL'}]

    if prep_fn is None:
        tgt = sp18
    else:
        tgt = [prep_fn(s, i) for i, s in enumerate(sp18)]

    if method == 'mixed':
        r = allocate(src, tgt, method='mixed', mixed_residual_method='qty')

    elif gkey is not None:
        # group_key='nganh': tạo 1 source duy nhất với nganh=SX → chỉ phân về targets nganh=SX
        # Đây là pattern đúng: source.nganh phải match target.nganh
        src_group = [{'id': cp_id, 'amount': cp_amt, 'ten': cp_ten, 'nganh': 'SX'}]
        r = allocate(src_group, tgt, method, group_key='nganh')

    else:
        r = allocate(src, tgt, method)

    results_28[cp_id] = r
    for spid, v in r.target_totals.items():
        if spid in total_per_sp28:
            total_per_sp28[spid] += v
    print(f"  [{cp_id:14}] {cp_ten:25} {cp_amt/1e9:>6.2f}B  {method:12}  {'group:'+gkey if gkey else '':>12}  ok={r.ok}")

section("BẢNG TỔNG HỢP — CP toàn bộ 18 sản phẩm (15 khoản)")
print(f"\n  {'SP':10} {'Ngành':6} {'CP tổng':>16} {'DT':>16} {'CP/DT%':>8} {'CP/NVL%':>9}")
print(f"  {'─'*67}")
for s in sp18:
    cp  = total_per_sp28[s['id']]
    dt  = s['dt']
    nvl = s['nvl']
    print(f"  {s['id']:10} {s['nganh']:6} {cp:>16,.0f} {dt:>16,.0f} {cp/dt*100:>7.2f}% {cp/nvl*100:>8.2f}%")

# Tổng theo ngành
print(f"\n  {'─'*67}")
print(f"  Tổng theo ngành:")
for nganh_label, nganh_sp in [('CN', nganh_cn), ('SX', nganh_sx), ('DV', nganh_dv)]:
    tong_cp = sum(total_per_sp28[s['id']] for s in nganh_sp)
    tong_dt = sum(s['dt'] for s in nganh_sp)
    print(f"  {nganh_label:10} {'':6} {tong_cp:>16,.0f} {tong_dt:>16,.0f} {tong_cp/tong_dt*100:>7.2f}%")

# Verify
tong_nguon_28 = sum(x[2] for x in cp28)
tong_phan_bo  = sum(total_per_sp28.values())
print(f"\n  Tổng nguồn:    {tong_nguon_28:>18,.0f}")
print(f"  Tổng phân bổ: {tong_phan_bo:>18,.0f}")
print(f"  Chênh lệch:   {abs(tong_nguon_28-tong_phan_bo):>18,.0f}")
ok(f"28 tổng chênh lệch < 0.01%",
   f"{'✓' if abs(tong_nguon_28-tong_phan_bo)/tong_nguon_28 < 0.0001 else '⚠'}")

section("TOP 5 sản phẩm nhận nhiều chi phí nhất")
top5 = sorted(total_per_sp28.items(), key=lambda x: -x[1])[:5]
for spid, cp in top5:
    sp_data = next(s for s in sp18 if s['id'] == spid)
    print(f"  {spid:10} {sp_data['ten']:20} {cp:>16,.0f}  ({cp/tong_phan_bo*100:.2f}% tổng CP)")

section("CROSS-CHECK: 5 câu hỏi kiểm tra tính đúng đắn")

# 1. Tổng CP = tổng nguồn (đã làm ở trên)
ok("1. Σ allocated = Σ sources",
   f"{tong_phan_bo:,.0f} ≈ {tong_nguon_28:,.0f} {'✓' if abs(tong_phan_bo-tong_nguon_28) < 1000 else '⚠'}")

# 2. CP_LUONG_SX dùng group_key='nganh': source SX chỉ allocate về targets nganh='SX'
r_sx_check = results_28.get('CP_LUONG_SX')
if r_sx_check:
    sx_nhận   = sum(v for k, v in r_sx_check.target_totals.items() if k.startswith('SX'))
    non_sx    = sum(v for k, v in r_sx_check.target_totals.items() if not k.startswith('SX'))
    ok("2. CP lương SX (group_key) → SX nhận toàn bộ",
       f"SX={sx_nhận:,.0f}  non-SX={non_sx:,.0f} {'✓' if abs(sx_nhận-8_400_000_000)<1 else '⚠'}")

# 3. Mixed: flagship SX nhận alloc_amount trước
r_f_check = results_28.get('CP_MIXED_B')
if r_f_check:
    tv_nhận  = r_f_check.target_totals.get('SX_TV', 0)
    lt_nhận  = r_f_check.target_totals.get('SX_LT', 0)
    ok("3. Flagship SX_TV nhận alloc_amount 600M",
       f"SX_TV={tv_nhận:,.0f} {'✓' if abs(tv_nhận-600_000_000)<1 else '⚠'}")
    ok("3. Flagship SX_LT nhận alloc_amount 600M",
       f"SX_LT={lt_nhận:,.0f} {'✓' if abs(lt_nhận-600_000_000)<1 else '⚠'}")

# 4. Khoản manual_pct (R&D): tổng % = 100
tong_pct_rd = sum([12,8,10,15,5, 6,8,7,5,3,2,4,4, 3,2,2,2,2])
ok("4. R&D manual_pct tổng = 100%", f"{tong_pct_rd}% {'✓' if tong_pct_rd==100 else '⚠'}")

# 5. equal: mỗi SP nhận bằng nhau
r_eq = results_28.get('CP_PHAPLUAT')
if r_eq:
    vals_eq = list(r_eq.target_totals.values())
    max_diff = max(vals_eq) - min(vals_eq)
    ok("5. equal: chênh lệch max-min giữa các SP",
       f"{max_diff:.2f} (do rounding) {'✓' if max_diff < 2 else '⚠'}")

# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{'═'*W}")
print("  ✅  Hoàn thành toàn bộ ví dụ PHỨC TẠP NHẤT (8 chủ đề, 21–28)")
print(f"{'═'*W}")
print(f"  21 · Composite weight    — trọng số tổ hợp 4 chỉ số")
print(f"  22 · Mixed 4 tầng        — alloc_amount → manual_pct → weight → equal")
print(f"  23 · Cross-allocation    — step-down Finance→HR→IT→Sản xuất")
print(f"  24 · Cascade 3 cấp       — TĐ→CTY→PB→SP, mỗi cấp 1 tiêu thức riêng")
print(f"  25 · 10 nguồn × 12 đích  — 7 tiêu thức khác nhau, matrix đầy đủ")
print(f"  26 · Mixed 4 loại        — alloc_amount+manual_pct+weight+equal trong 1")
print(f"  27 · Iterative loop      — phân bổ dịch vụ nội bộ lẫn nhau, lặp hội tụ")
print(f"  28 · Tập đoàn đa ngành   — 15 nguồn×18 đích×9 tiêu thức+cross-check đầy đủ")
print(f"{'═'*W}\n")
