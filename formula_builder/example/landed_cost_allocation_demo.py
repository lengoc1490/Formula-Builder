#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
phan_bo.py — Ví dụ phân bổ chi phí, chạy thẳng trong VSCode
Đặt file này cùng thư mục với engine_v24.py rồi nhấn Run (F5 / Ctrl+F5)

Bao gồm 8 tiêu thức + group_key + nhiều nguồn + tình huống thực tế
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine_v24 import allocate, FormulaEngine

# ─── helpers ──────────────────────────────────────────────────────────────────
W = 70
def title(s):   print(f"\n{'═'*W}\n  {s}\n{'═'*W}")
def sec(s):     print(f"\n  ── {s} ──")
def ok(lbl, v): print(f"  ✓  {lbl:42s} {v}")
def show(r, src_label="ten", tgt_label="ten"):
    """In kết quả phân bổ gọn."""
    r.print_by_source(sources if 'sources' in dir() else [], label_key=src_label)

def pr_table(result, s_list, t_list, src_lk="ten", tgt_lk="ten"):
    """In bảng nguồn → đích."""
    result.print_by_source(s_list, label_key=src_lk)


# ══════════════════════════════════════════════════════════════════════════════
title("1 · EQUAL — chia đều")
# ══════════════════════════════════════════════════════════════════════════════
sources = [{'id':'CP_DIEN', 'amount':120_000_000, 'ten':'Chi phí điện'}]
targets = [
    {'id':'KD', 'ten':'Kinh doanh'},
    {'id':'SX', 'ten':'Sản xuất'},
    {'id':'HC', 'ten':'Hành chính'},
]
r = allocate(sources, targets, 'equal')
r.print_by_source(sources, label_key='ten')
ok("source_totals", r.source_totals)
ok("target_totals", r.target_totals)
ok("unallocated  ", r.unallocated)
ok("ok           ", r.ok)


# ══════════════════════════════════════════════════════════════════════════════
title("2 · QTY — theo số lượng sản xuất")
# ══════════════════════════════════════════════════════════════════════════════
sources = [{'id':'KH_MAY', 'amount':120_000_000, 'ten':'Khấu hao máy'}]
targets = [
    {'id':'SP_A', 'ten':'Sản phẩm A', 'qty':500},
    {'id':'SP_B', 'ten':'Sản phẩm B', 'qty':800},
    {'id':'SP_C', 'ten':'Sản phẩm C', 'qty':300},
    {'id':'SP_D', 'ten':'Sản phẩm D', 'qty':400},
]
r = allocate(sources, targets, 'qty')
r.print_by_source(sources, label_key='ten')
r.print_by_target(targets, label_key='ten')


# ══════════════════════════════════════════════════════════════════════════════
title("3 · AMOUNT — theo doanh thu")
# ══════════════════════════════════════════════════════════════════════════════
sources = [{'id':'CP_QC', 'amount':48_000_000, 'ten':'Chi phí quảng cáo'}]
targets = [
    {'id':'MB', 'ten':'Miền Bắc',   'amount':  800_000_000},
    {'id':'MT', 'ten':'Miền Trung',  'amount':  300_000_000},
    {'id':'MN', 'ten':'Miền Nam',    'amount':1_100_000_000},
]
r = allocate(sources, targets, 'amount')
r.print_by_source(sources, label_key='ten')
# Kiểm tra tỷ lệ
g = r.group_by_source(sources)
for row in g['CP_QC']['allocated_to']:
    ok(row['target_id'], f"tỷ lệ = {row['ratio']:.2%}  nhận = {row['allocated']:>12,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
title("4 · WEIGHT — theo trọng số tự đặt (diện tích m², điểm KPI, giờ máy...)")
# ══════════════════════════════════════════════════════════════════════════════
sources = [{'id':'CP_VS', 'amount':18_000_000, 'ten':'Chi phí vệ sinh'}]
targets = [
    {'id':'T01', 'ten':'Tầng 1 (500m²)', 'alloc_weight':500},
    {'id':'T02', 'ten':'Tầng 2 (300m²)', 'alloc_weight':300},
    {'id':'T03', 'ten':'Tầng 3 (200m²)', 'alloc_weight':200},
]
r = allocate(sources, targets, 'weight')
r.print_by_source(sources, label_key='ten')


# ══════════════════════════════════════════════════════════════════════════════
title("5 · PCT — % kế toán cố định")
# ══════════════════════════════════════════════════════════════════════════════
sources = [{'id':'CP_QT', 'amount':60_000_000, 'ten':'Chi phí quản trị'}]
targets = [
    {'id':'KD', 'ten':'Kinh doanh', 'alloc_pct':50},
    {'id':'SX', 'ten':'Sản xuất',   'alloc_pct':30},
    {'id':'HC', 'ten':'Hành chính', 'alloc_pct':20},
]
r = allocate(sources, targets, 'pct')
r.print_by_source(sources, label_key='ten')
ok("warnings (tổng=100%, sạch)", r.warnings)

sec("Tổng pct ≠ 100 → engine tự normalize + cảnh báo")
targets_lech = [
    {'id':'X1', 'ten':'X1', 'alloc_pct':40},
    {'id':'X2', 'ten':'X2', 'alloc_pct':40},   # tổng 80%
]
r2 = allocate(sources, targets_lech, 'pct')
r2.print_by_source(sources, label_key='ten')
ok("warnings (normalize)", r2.warnings)


# ══════════════════════════════════════════════════════════════════════════════
title("6 · MANUAL_AMOUNT — nhập tay số tiền")
# ══════════════════════════════════════════════════════════════════════════════
sources = [{'id':'CP_NS', 'amount':120_000_000, 'ten':'Chi phí nhân sự'}]
targets = [
    {'id':'KD', 'ten':'Kinh doanh', 'alloc_amount': 50_000_000},
    {'id':'SX', 'ten':'Sản xuất',   'alloc_amount': 45_000_000},
    {'id':'HC', 'ten':'Hành chính', 'alloc_amount': 25_000_000},
]
r = allocate(sources, targets, 'manual_amount')
r.print_by_source(sources, label_key='ten')
ok("unallocated (tổng bằng nguồn)", r.unallocated)

sec("Tổng manual < nguồn → còn dư 30M")
r_du = allocate(sources,
                [{'id':'KD','alloc_amount':50_000_000},
                 {'id':'SX','alloc_amount':40_000_000}],
                'manual_amount')
ok("unallocated còn dư", r_du.unallocated)

sec("Tổng manual > nguồn → thâm hụt")
r_thieu = allocate(sources,
                   [{'id':'KD','alloc_amount':80_000_000},
                    {'id':'SX','alloc_amount':60_000_000}],
                   'manual_amount')
ok("unallocated thâm hụt", r_thieu.unallocated)


# ══════════════════════════════════════════════════════════════════════════════
title("7 · MANUAL_PCT — % nhập tay")
# ══════════════════════════════════════════════════════════════════════════════
sources = [{'id':'LN', 'amount':120_000_000, 'ten':'Lợi nhuận phân phối'}]
targets = [
    {'id':'QUY_A', 'ten':'Quỹ đầu tư',  'manual_pct':60},
    {'id':'QUY_B', 'ten':'Quỹ dự phòng','manual_pct':25},
    {'id':'QUY_C', 'ten':'Quỹ phúc lợi','manual_pct':15},
]
r = allocate(sources, targets, 'manual_pct')
r.print_by_source(sources, label_key='ten')
ok("unallocated (100% chia hết)", r.unallocated)


# ══════════════════════════════════════════════════════════════════════════════
title("8 · MIXED — kết hợp manual + tự động chia phần còn lại")
# ══════════════════════════════════════════════════════════════════════════════
# Ưu tiên: alloc_amount > manual_pct > residual
# residual có thể là: qty / amount / weight / equal
sources = [{'id':'CP', 'amount':120_000_000, 'ten':'Chi phí chung'}]

sec("8a · residual = qty  (BP01 cố định 30M + IT 20% → còn lại theo qty)")
targets_a = [
    {'id':'BP01','ten':'KD',  'alloc_amount':30_000_000, 'qty':100},
    {'id':'BP02','ten':'IT',  'manual_pct':20,            'qty':200},
    {'id':'BP03','ten':'SX',  'qty':150},
    {'id':'BP04','ten':'HC',  'qty': 50},
]
r_a = allocate(sources, targets_a, 'mixed', mixed_residual_method='qty')
r_a.print_by_source(sources, label_key='ten')

sec("8b · residual = amount")
targets_b = [
    {'id':'K01','ten':'Online',   'alloc_amount':20_000_000, 'amount':500_000_000},
    {'id':'K02','ten':'Offline',  'manual_pct':10,            'amount':300_000_000},
    {'id':'K03','ten':'Đại lý',   'amount':400_000_000},
    {'id':'K04','ten':'Xuất khẩu','amount':100_000_000},
]
r_b = allocate(sources, targets_b, 'mixed', mixed_residual_method='amount')
r_b.print_by_source(sources, label_key='ten')

sec("8c · residual = equal")
targets_c = [
    {'id':'A','ten':'A cố định 50M','alloc_amount':50_000_000},
    {'id':'B','ten':'B chia đều'},
    {'id':'C','ten':'C chia đều'},
    {'id':'D','ten':'D chia đều'},
]
r_c = allocate(sources, targets_c, 'mixed', mixed_residual_method='equal')
r_c.print_by_source(sources, label_key='ten')

sec("8d · residual = weight")
targets_d = [
    {'id':'P1','ten':'P1 manual_pct 30%','manual_pct':30, 'alloc_weight':100},
    {'id':'P2','ten':'P2 theo weight',    'alloc_weight':200},
    {'id':'P3','ten':'P3 theo weight',    'alloc_weight':150},
]
r_d = allocate(sources, targets_d, 'mixed', mixed_residual_method='weight')
r_d.print_by_source(sources, label_key='ten')


# ══════════════════════════════════════════════════════════════════════════════
title("9 · GROUP_KEY — phân bổ theo nhóm (dept / nganh / loai...)")
# ══════════════════════════════════════════════════════════════════════════════
# Source có dept='KD' chỉ phân về targets có dept='KD', v.v.
sources = [
    {'id':'CP_KD', 'amount':120_000_000, 'ten':'CP Kinh doanh', 'dept':'KD'},
    {'id':'CP_IT', 'amount': 60_000_000, 'ten':'CP IT',         'dept':'IT'},
]
targets = [
    {'id':'KD_HN','ten':'KD Hà Nội',   'qty':100, 'dept':'KD'},
    {'id':'KD_HCM','ten':'KD HCM',     'qty':200, 'dept':'KD'},
    {'id':'IT_DEV','ten':'IT Dev',      'qty': 80, 'dept':'IT'},
    {'id':'IT_OPS','ten':'IT Ops',      'qty':120, 'dept':'IT'},
]
r = allocate(sources, targets, 'qty', group_key='dept')
r.print_by_source(sources, label_key='ten')
ok("CP_KD chỉ về KD_*", {k:v for k,v in r.target_totals.items() if k.startswith('KD')})
ok("CP_IT chỉ về IT_*", {k:v for k,v in r.target_totals.items() if k.startswith('IT')})


# ══════════════════════════════════════════════════════════════════════════════
title("10 · NHIỀU NGUỒN × NHIỀU ĐÍCH — 4 khoản × 5 bộ phận")
# ══════════════════════════════════════════════════════════════════════════════
# 4 khoản chi phí, mỗi khoản 1 tiêu thức khác nhau,
# cùng phân về 5 bộ phận → bảng tổng hợp cuối
bp = [
    {'id':'KD','ten':'Kinh doanh',  'qty':5000,  'amount':2_000_000_000, 'alloc_weight':120, 'alloc_pct':30},
    {'id':'SX','ten':'Sản xuất',    'qty':15000, 'amount':5_000_000_000, 'alloc_weight':400, 'alloc_pct':40},
    {'id':'IT','ten':'IT',          'qty':1200,  'amount':  600_000_000, 'alloc_weight': 80, 'alloc_pct':15},
    {'id':'HR','ten':'Nhân sự',     'qty':800,   'amount':  400_000_000, 'alloc_weight': 60, 'alloc_pct':10},
    {'id':'HC','ten':'Hành chính',  'qty':500,   'amount':  200_000_000, 'alloc_weight': 40, 'alloc_pct': 5},
]

chi_phi = [
    {'id':'LUONG',  'amount':480_000_000, 'ten':'Lương nhân viên',    'method':'qty'},
    {'id':'VP',     'amount': 96_000_000, 'ten':'Văn phòng phẩm',     'method':'equal'},
    {'id':'DIEN',   'amount':120_000_000, 'ten':'Tiền điện',          'method':'weight'},
    {'id':'MARKETING','amount':240_000_000,'ten':'Marketing',         'method':'amount'},
    {'id':'KHDB',   'amount': 60_000_000, 'ten':'Khấu hao đặc biệt', 'method':'pct'},
]

results = {}
total_per_bp = {b['id']:0.0 for b in bp}

for cp in chi_phi:
    r = allocate([{'id':cp['id'],'amount':cp['amount']}], bp, cp['method'])
    results[cp['id']] = r
    for bid, v in r.target_totals.items():
        total_per_bp[bid] += v

# In bảng tổng hợp
print(f"\n  {'Chi phí':18}" + "".join(f"{b['id']:>13}" for b in bp) + f"{'TỔNG':>13}")
print(f"  {'─'*(18+13*(len(bp)+1))}")
tong_tong = 0.0
for cp in chi_phi:
    r = results[cp['id']]
    row_total = sum(r.target_totals.get(b['id'],0) for b in bp)
    tong_tong += row_total
    print(f"  {cp['ten']:18}" + "".join(f"{r.target_totals.get(b['id'],0):>13,.0f}" for b in bp)
          + f"{row_total:>13,.0f}")
print(f"  {'─'*(18+13*(len(bp)+1))}")
print(f"  {'TỔNG':18}" + "".join(f"{total_per_bp[b['id']]:>13,.0f}" for b in bp)
      + f"{tong_tong:>13,.0f}")

tong_nguon = sum(cp['amount'] for cp in chi_phi)
ok("Tổng nguồn = tổng phân bổ",
   f"{tong_tong:,.0f} = {tong_nguon:,.0f}  {'✓' if abs(tong_tong-tong_nguon)<1 else '⚠'}")


# ══════════════════════════════════════════════════════════════════════════════
title("11 · CUSTOM FIELD KEYS — field tên khác mặc định")
# ══════════════════════════════════════════════════════════════════════════════
# DB của bạn dùng tên field khác: 'ma' thay 'id', 'so_tien' thay 'amount', v.v.
sources_db = [{'ma':'S01', 'so_tien':100_000_000, 'ten':'CP test'}]
targets_db = [
    {'ma':'T01', 'ten':'Nhóm 1', 'so_luong':100},
    {'ma':'T02', 'ten':'Nhóm 2', 'so_luong':300},
    {'ma':'T03', 'ten':'Nhóm 3', 'so_luong':200},
]
r = allocate(sources_db, targets_db, 'qty',
             source_id_key='ma',
             source_amount_key='so_tien',
             target_id_key='ma',
             target_qty_key='so_luong')
r.print_by_source(sources_db, label_key='ten', source_id_key='ma')


# ══════════════════════════════════════════════════════════════════════════════
title("12 · ROUNDING POLICY — xử lý lệch làm tròn")
# ══════════════════════════════════════════════════════════════════════════════
sources = [{'id':'S','amount':100,'ten':'100đ chia 3'}]
targets = [{'id':'A'},{'id':'B'},{'id':'C'}]

for policy in ['last','largest','none']:
    r = allocate(sources, targets, 'equal', rounding_policy=policy, round_digits=2)
    vals = list(r.target_totals.values())
    print(f"  policy={policy:8s}: {vals}  sum={sum(vals):.2f}")


# ══════════════════════════════════════════════════════════════════════════════
title("13 · TẤT CẢ DẠNG KẾT QUẢ — lines / totals / group / print / JSON")
# ══════════════════════════════════════════════════════════════════════════════
sources = [{'id':'CP1','amount':120_000_000,'ten':'Chi phí A'}]
targets = [
    {'id':'X1','ten':'X1','qty':100},
    {'id':'X2','ten':'X2','qty':250},
    {'id':'X3','ten':'X3','qty': 50},
]
r = allocate(sources, targets, 'qty')

sec("lines (chi tiết từng dòng phân bổ)")
for ln in r.lines:
    print(f"  {ln.source_id} → {ln.target_id}: {ln.allocated:,.2f}  ratio={ln.ratio:.4f}  method={ln.method}")

sec("source_totals / target_totals / unallocated")
ok("source_totals", r.source_totals)
ok("target_totals", r.target_totals)
ok("unallocated  ", r.unallocated)

sec("group_by_source — phân tích theo nguồn")
g = r.group_by_source(sources)
for sid, row in g.items():
    print(f"  [{sid}] allocated_total={row['allocated_total']:,.0f}  unallocated={row['unallocated']:,.0f}")
    for ln in row['allocated_to']:
        print(f"    → {ln['target_id']:6} {ln['allocated']:>12,.2f}  {ln['ratio']:.2%}")

sec("group_by_target — phân tích theo đích")
g2 = r.group_by_target(targets)
for tid, row in g2.items():
    print(f"  [{tid}] received_total={row['received_total']:,.0f}")
    for ln in row['received_from']:
        print(f"    ← {ln['source_id']:6} {ln['allocated']:>12,.2f}")

sec("to_full_dict — export toàn bộ dạng dict")
fd = r.to_full_dict(sources, targets)
print("  keys:", list(fd.keys()))

sec("print_by_source / print_by_target (built-in)")
r.print_by_source(sources, label_key='ten')
r.print_by_target(targets, label_key='ten')

sec("JSON export")
print(json.dumps({
    'source_totals': r.source_totals,
    'target_totals': r.target_totals,
    'unallocated':   r.unallocated,
    'ok':            r.ok,
    'lines': [ln.to_dict() for ln in r.lines],
}, ensure_ascii=False, indent=2))


# ══════════════════════════════════════════════════════════════════════════════
title("14 · WARNINGS & UNALLOCATED — kiểm tra & xử lý")
# ══════════════════════════════════════════════════════════════════════════════
sources = [{'id':'S','amount':100_000_000,'ten':'Nguồn test'}]

sec("Target qty = 0 → engine bỏ qua, cảnh báo")
r = allocate(sources,
             [{'id':'A','qty':0},{'id':'B','qty':100},{'id':'C','qty':0}],
             'qty')
ok("warnings", r.warnings)
ok("target_totals", r.target_totals)

sec("manual_amount sum < source → unallocated dương")
r2 = allocate(sources,
              [{'id':'A','alloc_amount':30_000_000},
               {'id':'B','alloc_amount':20_000_000}],
              'manual_amount')
ok("unallocated còn dư 50M", r2.unallocated)
ok("ok (engine không báo lỗi)", r2.ok)


# ══════════════════════════════════════════════════════════════════════════════
title("15 · THỰC TẾ — Chi phí sản xuất tháng 10")
# ══════════════════════════════════════════════════════════════════════════════
sp = [
    {'id':'SP_A','ten':'Sản phẩm A','qty':500, 'amount':800_000_000,'gio_may':200,'alloc_pct':45},
    {'id':'SP_B','ten':'Sản phẩm B','qty':800, 'amount':600_000_000,'gio_may':350,'alloc_pct':35},
    {'id':'SP_C','ten':'Sản phẩm C','qty':300, 'amount':400_000_000,'gio_may':150,'alloc_pct':20},
]

danh_sach_cp = [
    # (id, tên, số tiền, tiêu thức, field override)
    ('KH_MAY',    'Khấu hao máy',     35_000_000, 'qty',           [{**s,'qty':s['gio_may']} for s in sp]),
    ('NHAN_CONG', 'Nhân công',        60_000_000, 'qty',           sp),
    ('DIEN_NUOC', 'Điện nước',        12_000_000, 'amount',        sp),
    ('QL_PX',     'Quản lý PX',       18_000_000, 'pct',           sp),
    ('VAN_CHUYEN','Vận chuyển',        9_000_000, 'manual_amount',
     [{**sp[0],'alloc_amount':4_500_000},
      {**sp[1],'alloc_amount':3_000_000},
      {**sp[2],'alloc_amount':1_500_000}]),
    ('CP_DB',     'Chi phí đặc biệt', 20_000_000, 'mixed',
     [{**sp[0],'alloc_amount':8_000_000,'qty':sp[0]['qty']},
      {**sp[1],'qty':sp[1]['qty']},
      {**sp[2],'qty':sp[2]['qty']}]),
]

all_results = []
ten_cp      = []
tong_per_sp = {s['id']:0.0 for s in sp}

for cp_id, cp_ten, cp_amt, method, tgt in danh_sach_cp:
    src = [{'id':cp_id,'amount':cp_amt}]
    kw  = {'mixed_residual_method':'qty'} if method == 'mixed' else {}
    r   = allocate(src, tgt, method, **kw)
    all_results.append(r)
    ten_cp.append(cp_ten[:14])
    print(f"\n  [{cp_ten:18}] {method:14}  phân bổ={sum(r.target_totals.values()):,.0f}  ok={r.ok}")
    r.print_by_source(src, label_key='id')
    for sid, v in r.target_totals.items():
        tong_per_sp[sid] += v

sec("Bảng tổng hợp chi phí theo sản phẩm")
sp_ids = [s['id'] for s in sp]
col_w  = 16
print(f"\n  {'Chi phí':16}" + "".join(f"{sid:>{col_w}}" for sid in sp_ids) + f"{'TỔNG':>{col_w}}")
print(f"  {'─'*(16+col_w*(len(sp)+1))}")
tong_grand = 0.0
for r, ten in zip(all_results, ten_cp):
    row_total = sum(r.target_totals.get(sid,0) for sid in sp_ids)
    tong_grand += row_total
    print(f"  {ten:16}" + "".join(f"{r.target_totals.get(sid,0):>{col_w},.0f}" for sid in sp_ids)
          + f"{row_total:>{col_w},.0f}")
print(f"  {'─'*(16+col_w*(len(sp)+1))}")
print(f"  {'TỔNG':16}" + "".join(f"{tong_per_sp[sid]:>{col_w},.0f}" for sid in sp_ids)
      + f"{tong_grand:>{col_w},.0f}")

sec("Tỷ lệ chi phí / doanh thu")
print(f"  {'Sản phẩm':14} {'Tổng CP':>16} {'Doanh thu':>16} {'CP/DT':>9}")
print(f"  {'─'*57}")
for s in sp:
    cp = tong_per_sp[s['id']]
    dt = s['amount']
    print(f"  {s['ten']:14} {cp:>16,.0f} {dt:>16,.0f} {cp/dt*100:>8.2f}%")

sec("Kiểm tra toàn bộ 6 khoản")
tong_nguon = sum(x[2] for x in danh_sach_cp)
ok("Tổng phân bổ = tổng nguồn",
   f"{tong_grand:,.0f} = {tong_nguon:,.0f}  {'✓' if abs(tong_grand-tong_nguon)<1 else '⚠'}")
for r, ten in zip(all_results, ten_cp):
    una = sum(abs(v) for v in r.unallocated.values())
    print(f"  {'✓' if r.ok and una==0 else '⚠'}  {ten:16}  ok={r.ok}  unallocated={r.unallocated}")


# ══════════════════════════════════════════════════════════════════════════════
print(f"\n{'═'*W}")
print("  ✅  Hoàn thành — 15 ví dụ với tất cả tiêu thức allocation")
print(f"     Chỉnh sửa data ngay trong file này để test thêm.")
print(f"{'═'*W}\n")