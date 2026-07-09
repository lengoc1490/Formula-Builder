"""
==============================================================================
  AllocationResult — Toàn bộ dạng kết quả đầu ra
  engine_v21 · Pure Python · Zero dependencies
==============================================================================

  Mỗi method trả về dạng dữ liệu khác nhau cho từng nhu cầu:

  ┌─────────────────────────────┬───────────────────────────────────────────┐
  │ Method / Attribute          │ Dùng khi nào                              │
  ├─────────────────────────────┼───────────────────────────────────────────┤
  │ result.lines                │ Flat list toàn bộ dòng phân bổ            │
  │ result.source_totals        │ Chỉ cần tổng đã phân bổ theo nguồn        │
  │ result.target_totals        │ Chỉ cần tổng nhận được theo đích           │
  │ result.unallocated          │ Kiểm tra phần dư chưa phân bổ             │
  │ result.summary()            │ Text tóm tắt human-readable               │
  │ result.to_dict()            │ Flat dict cho JSON / API                  │
  │ result.to_sources_detail()  │ Nguồn → [list đích nhận]  + toàn bộ field │
  │ result.to_targets_detail()  │ Đích  → [list nguồn vào] + toàn bộ field  │
  │ result.to_full_dict()       │ Tất cả trong 1 dict lớn                   │
  └─────────────────────────────┴───────────────────────────────────────────┘

  MỤC LỤC
  ─────────────────────────────────────────────────────────────────────────
  A.  Dữ liệu demo dùng chung
  B.  result.lines             — flat, từng dòng nguồn→đích
  C.  result.source_totals     — chỉ tổng theo nguồn (lược bỏ nhất)
  D.  result.target_totals     — chỉ tổng theo đích (lược bỏ nhất)
  E.  result.unallocated       — phần dư chưa phân bổ
  F.  result.summary()         — text human-readable
  G.  result.to_dict()         — flat dict / JSON / API
  H.  result.to_sources_detail()  — nguồn + list đích chi tiết
  I.  result.to_targets_detail()  — đích + list nguồn chi tiết
  J.  result.to_full_dict()       — tất cả trong 1
  K.  Dùng với mixed — thấy rõ method từng dòng & meta
  L.  Dùng với group_key — nhiều nhóm trong 1 lần gọi
  M.  Custom field keys — source_id_key / target_id_key
  N.  Công thức in đẹp / export helpers
==============================================================================
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from engine_v24 import allocate

SEP  = "─" * 68
SEP2 = "═" * 68

def section(title):
    print(f"\n{SEP2}\n  {title}\n{SEP2}")

def sub(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")


# ══════════════════════════════════════════════════════════════════════════════
#  A.  DỮ LIỆU DEMO DÙNG CHUNG
# ══════════════════════════════════════════════════════════════════════════════

section("A.  Dữ liệu demo dùng chung")

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

print(f"  2 nguồn × 3 đích = {len(result.lines)} dòng phân bổ   |   ok={result.ok}")
print("  Tiêu thức: qty  (BP01:100, BP02:200, BP03:50  → tổng 350)")


# ══════════════════════════════════════════════════════════════════════════════
#  B.  result.lines — FLAT LIST TỪNG DÒNG
# ══════════════════════════════════════════════════════════════════════════════

section("B.  result.lines — Flat list toàn bộ dòng phân bổ (AllocationLine)")

print("""
  Mỗi AllocationLine có:
    .source_id      id dòng nguồn
    .source_amount  giá trị gốc dòng nguồn
    .target_id      id dòng đích
    .allocated      số tiền được phân bổ
    .ratio          tỷ lệ (0.0 → 1.0)
    .method         tiêu thức ('qty', 'equal', 'mixed:manual_amount', ...)
    .weight         trọng số gốc dùng để tính ratio
    .meta           dict bổ sung (mixed_stage, residual_amount, ...)
    .to_dict()      serialize → dict
""")

print(f"  {'source_id':8} {'target_id':8} {'allocated':>16} {'ratio':>7} {'method':20} {'weight':>10}  meta")
print(f"  {'─'*8} {'─'*8} {'─'*16} {'─'*7} {'─'*20} {'─'*10}  {'─'*4}")
for ln in result.lines:
    print(f"  {ln.source_id:8} {ln.target_id:8} {ln.allocated:>16,.2f} {ln.ratio:>7.2%} {ln.method:20} {ln.weight:>10,.0f}  {ln.meta or '{}' }")

print("\n  # Lặp qua lines:")
print("""
  for ln in result.lines:
      print(ln.source_id, ln.target_id, ln.allocated, ln.ratio, ln.method)

  # Lọc chỉ xem 1 nguồn:
  cp001_lines = [ln for ln in result.lines if ln.source_id == 'CP001']

  # Lọc chỉ xem 1 đích:
  bp01_lines  = [ln for ln in result.lines if ln.target_id == 'BP01']

  # ln.to_dict() — serialize thành dict:
""")
print("  result.lines[0].to_dict() →", json.dumps(result.lines[0].to_dict(), ensure_ascii=False, indent=4))


# ══════════════════════════════════════════════════════════════════════════════
#  C.  result.source_totals — CHỈ TỔNG THEO NGUỒN
# ══════════════════════════════════════════════════════════════════════════════

section("C.  result.source_totals — Chỉ tổng đã phân bổ theo nguồn (lược bỏ nhất)")

print(f"""
  result.source_totals
  → {{source_id: tổng đã phân bổ đi}}

  Kết quả: {result.source_totals}
""")

print("  # Kiểm tra từng nguồn:")
for sid, total in result.source_totals.items():
    src_amount = next(s['amount'] for s in sources if s['id'] == sid)
    pct = total / src_amount * 100
    print(f"    {sid}: phân bổ {total:>14,.2f} / {src_amount:>14,.0f}  ({pct:.1f}%)")


# ══════════════════════════════════════════════════════════════════════════════
#  D.  result.target_totals — CHỈ TỔNG THEO ĐÍCH
# ══════════════════════════════════════════════════════════════════════════════

section("D.  result.target_totals — Chỉ tổng nhận được theo đích (lược bỏ nhất)")

print(f"""
  result.target_totals
  → {{target_id: tổng nhận được từ tất cả nguồn}}

  Kết quả: {result.target_totals}
""")

grand_total = sum(result.target_totals.values())
print(f"  {'Đích':8} {'Tổng nhận':>16} {'% tổng':>8}")
print(f"  {'─'*8} {'─'*16} {'─'*8}")
for tid, total in result.target_totals.items():
    print(f"  {tid:8} {total:>16,.2f} {total/grand_total:>8.2%}")
print(f"  {'─'*8} {'─'*16} {'─'*8}")
print(f"  {'TỔNG':8} {grand_total:>16,.2f} {'100.00%':>8}")


# ══════════════════════════════════════════════════════════════════════════════
#  E.  result.unallocated — PHẦN DƯ CHƯA PHÂN BỔ
# ══════════════════════════════════════════════════════════════════════════════

section("E.  result.unallocated — Phần dư chưa phân bổ")

print(f"""
  result.unallocated
  → {{source_id: phần dư}}   (thường = 0 nếu đủ đích và tiêu thức ổn)
  Kết quả: {result.unallocated}   ← empty = tất cả nguồn đã phân bổ hết
""")

# Demo case có unallocated
print("  [Demo: manual_amount tổng vượt source → unallocated âm]")
r_una = allocate(
    [{'id': 'CP001', 'amount': 100_000_000}],
    [{'id': 'BP01', 'alloc_amount': 80_000_000},
     {'id': 'BP02', 'alloc_amount': 40_000_000}],
    'manual_amount',
)
print(f"    unallocated = {r_una.unallocated}")
print(f"    ok          = {r_una.ok}")

print("""
  # Pattern kiểm tra chuẩn:
  for sid, una in result.unallocated.items():
      if una > 0:
          print(f"Nguồn {sid} còn dư: {una:,.0f}")
      elif una < 0:
          print(f"Nguồn {sid} thâm hụt: {abs(una):,.0f}")
""")


# ══════════════════════════════════════════════════════════════════════════════
#  F.  result.summary() — TEXT HUMAN-READABLE
# ══════════════════════════════════════════════════════════════════════════════

section("F.  result.summary() — Text tóm tắt human-readable")

print(result.summary())
print("""
  # Phù hợp cho: logging, debug console, email report đơn giản.
  # Không thích hợp cho: API response, DataFrame, UI table.
""")


# ══════════════════════════════════════════════════════════════════════════════
#  G.  result.to_dict() — FLAT DICT / JSON / API
# ══════════════════════════════════════════════════════════════════════════════

section("G.  result.to_dict() — Flat dict cho JSON / API")

d = result.to_dict()
print(f"""
  result.to_dict() trả về dict với keys:
    'lines'         → list[dict]  — toàn bộ dòng phân bổ (flat)
    'source_totals' → dict        — {{source_id: total}}
    'target_totals' → dict        — {{target_id: total}}
    'unallocated'   → dict        — {{source_id: dư}}
    'warnings'      → list[str]
    'ok'            → bool

  Kết quả:
    source_totals : {d['source_totals']}
    target_totals : {d['target_totals']}
    unallocated   : {d['unallocated']}
    ok            : {d['ok']}
    lines[0]      : {json.dumps(d['lines'][0], ensure_ascii=False)}
""")

# JSON export
json_str = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
print(f"  json.dumps(result.to_dict()) → {len(json_str)} ký tự")
print("  (Dùng trực tiếp cho REST API response, lưu DB, ghi file)")


# ══════════════════════════════════════════════════════════════════════════════
#  H.  result.to_sources_detail() — NGUỒN + LIST ĐÍCH CHI TIẾT
# ══════════════════════════════════════════════════════════════════════════════

section("H.  result.to_sources_detail() — Nguồn → list đích nhận chi tiết")

print("""
  Trả về: List[dict]  — cùng thứ tự với sources đầu vào.

  Mỗi dict = toàn bộ field của dòng nguồn gốc  +  3 key bổ sung:
    'allocated_total'  : tổng số tiền đã phân bổ đi
    'unallocated'      : phần chưa phân bổ (thường = 0)
    'allocated_to'     : List[dict] — chi tiết từng đích nhận
                         mỗi phần tử: {target_id, allocated, ratio, method, weight, meta}
""")

sources_detail = result.to_sources_detail(sources)

print("  Cấu trúc thực tế:")
for row in sources_detail:
    print(f"\n  ┌─ Nguồn: {row['id']}  ({row['ten']})")
    print(f"  │  amount          : {row['amount']:>16,.0f}")
    print(f"  │  allocated_total : {row['allocated_total']:>16,.2f}")
    print(f"  │  unallocated     : {row['unallocated']:>16,.2f}")
    print(f"  └─ allocated_to ({len(row['allocated_to'])} đích):")
    for item in row['allocated_to']:
        print(f"       target_id={item['target_id']:6}  allocated={item['allocated']:>14,.2f}  "
              f"ratio={item['ratio']:.4f}  method={item['method']:6}  weight={item['weight']:>6.0f}  meta={item['meta']}")

print("""
  # Truy cập:
  detail = result.to_sources_detail(sources)

  detail[0]                          # dòng nguồn đầu tiên (giữ nguyên thứ tự sources)
  detail[0]['id']                    # 'CP001'
  detail[0]['ten']                   # 'Chi phí nhân sự'   ← field gốc giữ nguyên
  detail[0]['allocated_total']       # 120,000,000.0
  detail[0]['unallocated']           # 0.0
  detail[0]['allocated_to']          # list các đích nhận
  detail[0]['allocated_to'][0]       # {'target_id': 'BP01', 'allocated': 34285714.29, ...}
  detail[0]['allocated_to'][0]['target_id']   # 'BP01'
  detail[0]['allocated_to'][0]['allocated']   # 34285714.29
  detail[0]['allocated_to'][0]['ratio']       # 0.29
  detail[0]['allocated_to'][0]['method']      # 'qty'
  detail[0]['allocated_to'][0]['weight']      # 100.0  ← qty của BP01

  # Lấy tổng đã phân bổ của từng nguồn:
  for row in detail:
      print(row['id'], row['allocated_total'])

  # Lấy chi tiết 1 nguồn cụ thể:
  cp001 = next(r for r in detail if r['id'] == 'CP001')
  for item in cp001['allocated_to']:
      print(item['target_id'], item['allocated'], item['method'])
""")


# ── H.2  Chỉ lấy tổng (không cần list chi tiết) ─────────────────────────────
sub("H.2  Chỉ lấy tổng per nguồn — không cần allocated_to list")

print("""
  Nếu chỉ cần totals, dùng result.source_totals thay vì to_sources_detail():

  result.source_totals  →  {'CP001': 120000000.0, 'CP002': 60000000.0}

  Hoặc nếu vẫn muốn giữ field gốc nhưng bỏ list chi tiết:
""")

sources_totals_only = [
    {**src,
     'allocated_total': result.source_totals.get(src['id'], 0),
     'unallocated':     result.unallocated.get(src['id'], 0)}
    for src in sources
]
for row in sources_totals_only:
    print(f"  {row}")


# ══════════════════════════════════════════════════════════════════════════════
#  I.  result.to_targets_detail() — ĐÍCH + LIST NGUỒN CHI TIẾT
# ══════════════════════════════════════════════════════════════════════════════

section("I.  result.to_targets_detail() — Đích → list nguồn vào chi tiết")

print("""
  Trả về: List[dict]  — cùng thứ tự với targets đầu vào.

  Mỗi dict = toàn bộ field của dòng đích gốc  +  2 key bổ sung:
    'received_total'  : tổng số tiền nhận được từ tất cả nguồn
    'received_from'   : List[dict] — chi tiết từng nguồn phân bổ vào
                        mỗi phần tử: {source_id, source_amount, allocated, ratio, method, weight, meta}
""")

targets_detail = result.to_targets_detail(targets)

print("  Cấu trúc thực tế:")
for row in targets_detail:
    print(f"\n  ┌─ Đích: {row['id']}  ({row['ten']})  qty={row['qty']}")
    print(f"  │  received_total : {row['received_total']:>16,.2f}")
    print(f"  └─ received_from ({len(row['received_from'])} nguồn):")
    for item in row['received_from']:
        print(f"       source_id={item['source_id']:8}  source_amount={item['source_amount']:>14,.0f}  "
              f"allocated={item['allocated']:>14,.2f}  ratio={item['ratio']:.4f}  method={item['method']}")

print("""
  # Truy cập:
  detail = result.to_targets_detail(targets)

  detail[0]                          # dòng đích đầu tiên
  detail[0]['id']                    # 'BP01'
  detail[0]['ten']                   # 'Kinh doanh'    ← field gốc giữ nguyên
  detail[0]['qty']                   # 100             ← field gốc giữ nguyên
  detail[0]['received_total']        # 51,428,571.43
  detail[0]['received_from']         # list các nguồn vào
  detail[0]['received_from'][0]      # {'source_id': 'CP001', 'allocated': 34285714.29, ...}
  detail[0]['received_from'][0]['source_id']     # 'CP001'
  detail[0]['received_from'][0]['source_amount'] # 120,000,000   ← gốc nguồn
  detail[0]['received_from'][0]['allocated']     # 34,285,714.29
  detail[0]['received_from'][0]['ratio']         # 0.29
  detail[0]['received_from'][0]['method']        # 'qty'
  detail[0]['received_from'][0]['weight']        # 100.0

  # Lấy tổng nhận của từng đích:
  for row in detail:
      print(row['id'], row['received_total'])

  # Đích nào nhận nhiều nhất:
  best = max(detail, key=lambda r: r['received_total'])
  print(best['id'], best['received_total'])
""")


# ── I.2  Chỉ lấy tổng per đích ───────────────────────────────────────────────
sub("I.2  Chỉ lấy tổng per đích — không cần received_from list")

print("""
  Nếu chỉ cần totals, dùng result.target_totals:

  result.target_totals  →  {'BP01': 51428571.43, 'BP02': 102857142.86, 'BP03': 25714285.71}

  Hoặc nếu muốn giữ field gốc nhưng bỏ list chi tiết:
""")

targets_totals_only = [
    {**tgt, 'received_total': result.target_totals.get(tgt['id'], 0)}
    for tgt in targets
]
for row in targets_totals_only:
    print(f"  {row}")


# ══════════════════════════════════════════════════════════════════════════════
#  J.  result.to_full_dict() — TẤT CẢ TRONG 1
# ══════════════════════════════════════════════════════════════════════════════

section("J.  result.to_full_dict() — Tất cả trong 1 dict lớn")

full = result.to_full_dict(sources, targets)

print(f"""
  result.to_full_dict(sources, targets) trả về dict với keys:
    'sources'        → to_sources_detail()   (list nguồn enriched)
    'targets'        → to_targets_detail()   (list đích enriched)
    'source_totals'  → dict
    'target_totals'  → dict
    'lines'          → list[dict]   (flat, toàn bộ dòng)
    'unallocated'    → dict
    'warnings'       → list
    'ok'             → bool

  keys: {list(full.keys())}
  ok  : {full['ok']}
  len(sources): {len(full['sources'])}   len(targets): {len(full['targets'])}   len(lines): {len(full['lines'])}
""")

print("  # Truy cập thống nhất:")
print("""
  full = result.to_full_dict(sources, targets)

  # Nguồn
  full['sources'][0]['id']              # 'CP001'
  full['sources'][0]['allocated_total'] # 120,000,000.0
  full['sources'][0]['allocated_to']    # list đích

  # Đích
  full['targets'][0]['id']             # 'BP01'
  full['targets'][0]['received_total'] # 51,428,571.43
  full['targets'][0]['received_from']  # list nguồn

  # Flat lines (khi cần dạng bảng thuần)
  full['lines'][0]   # {'source_id':..., 'target_id':..., 'allocated':..., ...}

  # Totals
  full['source_totals']   # {'CP001': 120M, 'CP002': 60M}
  full['target_totals']   # {'BP01': 51.4M, ...}
""")

# JSON toàn bộ
json_full = json.dumps(full, ensure_ascii=False, indent=2)
print(f"  Kích thước JSON: {len(json_full):,} ký tự")
print("  (Dùng cho: API response đầy đủ, lưu snapshot, audit log)")


# ══════════════════════════════════════════════════════════════════════════════
#  K.  MIXED — THẤY RÕ METHOD TỪNG DÒNG & META
# ══════════════════════════════════════════════════════════════════════════════

section("K.  mixed — Thấy rõ method từng dòng và meta qua to_sources_detail()")

sources_m = [{'id': 'CP001', 'amount': 120_000_000, 'ten': 'Chi phí chung'}]
targets_m = [
    {'id': 'BP01', 'ten': 'KD',  'alloc_amount': 30_000_000, 'qty': 100},  # manual_amount
    {'id': 'BP02', 'ten': 'IT',  'manual_pct': 20,            'qty': 200},  # manual_pct
    {'id': 'BP03', 'ten': 'SX',  'qty': 150},                               # residual qty
    {'id': 'BP04', 'ten': 'HC',  'qty':  50},                               # residual qty
]

result_m = allocate(sources_m, targets_m, method='mixed', mixed_residual_method='qty')
detail_m  = result_m.to_sources_detail(sources_m)

print(f"\n  Nguồn: {detail_m[0]['id']}  ({detail_m[0]['ten']})")
print(f"  amount          : {detail_m[0]['amount']:>16,.0f}")
print(f"  allocated_total : {detail_m[0]['allocated_total']:>16,.2f}")
print(f"  unallocated     : {detail_m[0]['unallocated']:>16,.2f}")
print(f"\n  allocated_to ({len(detail_m[0]['allocated_to'])} đích):")
print(f"  {'target_id':8} {'ten':6} {'allocated':>16} {'ratio':>7} {'method':30} {'weight':>12}  meta")
print(f"  {'─'*8} {'─'*6} {'─'*16} {'─'*7} {'─'*30} {'─'*12}  {'─'*30}")
for item in detail_m[0]['allocated_to']:
    tgt_ten = next(t['ten'] for t in targets_m if t['id'] == item['target_id'])
    print(f"  {item['target_id']:8} {tgt_ten:6} {item['allocated']:>16,.2f} {item['ratio']:>7.2%} "
          f"{item['method']:30} {item['weight']:>12,.0f}  {item['meta']}")

print("""
  # Lọc chỉ lấy dòng manual:
  manual_lines = [i for i in detail[0]['allocated_to'] if 'manual' in i['method']]

  # Lọc chỉ lấy dòng residual:
  residual_lines = [i for i in detail[0]['allocated_to']
                    if i.get('meta', {}).get('mixed_stage') == 'residual']

  # Tổng phần manual vs residual:
  total_manual   = sum(i['allocated'] for i in detail[0]['allocated_to'] if 'manual' in i['method'])
  total_residual = sum(i['allocated'] for i in detail[0]['allocated_to'] if 'manual' not in i['method'])
""")

# Demo tính
detail0 = detail_m[0]['allocated_to']
total_manual   = sum(i['allocated'] for i in detail0 if 'manual' in i['method'])
total_residual = sum(i['allocated'] for i in detail0 if 'manual' not in i['method'])
print(f"  total_manual   = {total_manual:,.2f}")
print(f"  total_residual = {total_residual:,.2f}")


# ══════════════════════════════════════════════════════════════════════════════
#  L.  GROUP_KEY — NHIỀU NHÓM TRONG 1 LẦN GỌI
# ══════════════════════════════════════════════════════════════════════════════

section("L.  group_key — to_sources_detail / to_targets_detail với nhiều nhóm")

sources_g = [
    {'id': 'CP001', 'amount': 120_000_000, 'dept': 'KD', 'ten': 'Lương KD'},
    {'id': 'CP002', 'amount':  60_000_000, 'dept': 'IT', 'ten': 'Lương IT'},
    {'id': 'CP003', 'amount':  30_000_000, 'dept': 'HC', 'ten': 'Lương HC'},
]
targets_g = [
    {'id': 'KD1', 'qty': 100, 'dept': 'KD', 'ten': 'KD nhóm 1'},
    {'id': 'KD2', 'qty': 200, 'dept': 'KD', 'ten': 'KD nhóm 2'},
    {'id': 'IT1', 'qty':  80, 'dept': 'IT', 'ten': 'IT nhóm 1'},
    {'id': 'IT2', 'qty': 120, 'dept': 'IT', 'ten': 'IT nhóm 2'},
    {'id': 'HC1', 'qty':   1, 'dept': 'HC', 'ten': 'HC nhóm 1'},
]

result_g = allocate(sources_g, targets_g, 'qty', group_key='dept')

# to_sources_detail — mỗi nguồn chỉ thấy các đích cùng dept
print("  to_sources_detail() — mỗi nguồn chỉ thấy đích cùng nhóm:")
for row in result_g.to_sources_detail(sources_g):
    print(f"\n  [{row['id']}] {row['ten']}  dept={row['dept']}")
    print(f"    allocated_total: {row['allocated_total']:>14,.0f}")
    for item in row['allocated_to']:
        print(f"      → {item['target_id']:5}  {item['allocated']:>14,.0f}  ({item['ratio']:.2%})  [{item['method']}]")

# to_targets_detail — mỗi đích thấy nguồn cùng dept
print("\n  to_targets_detail() — mỗi đích thấy nguồn cùng nhóm:")
for row in result_g.to_targets_detail(targets_g):
    print(f"\n  [{row['id']}] {row['ten']}  dept={row['dept']}")
    print(f"    received_total : {row['received_total']:>14,.0f}")
    for item in row['received_from']:
        print(f"      ← {item['source_id']:6}  {item['allocated']:>14,.0f}  ({item['ratio']:.2%})  [{item['method']}]")


# ══════════════════════════════════════════════════════════════════════════════
#  M.  CUSTOM FIELD KEYS
# ══════════════════════════════════════════════════════════════════════════════

section("M.  Custom field keys — source_id_key / target_id_key")

print("""
  Khi schema dữ liệu dùng tên field khác 'id', phải truyền key vào
  cả allocate() lẫn to_sources_detail() / to_targets_detail():
""")

sources_ck = [{'ma_ct': 'C01', 'gia_tri': 90_000_000, 'ten': 'Chi phí A'}]
targets_ck = [
    {'ma_bp': 'D01', 'so_luong': 3, 'ten': 'Nhóm 1'},
    {'ma_bp': 'D02', 'so_luong': 7, 'ten': 'Nhóm 2'},
]

result_ck = allocate(
    sources_ck, targets_ck, 'qty',
    source_id_key     = 'ma_ct',
    source_amount_key = 'gia_tri',
    target_id_key     = 'ma_bp',
    target_qty_key    = 'so_luong',
)

# Phải truyền source_id_key vào to_sources_detail()
sd_ck = result_ck.to_sources_detail(sources_ck, source_id_key='ma_ct')
td_ck = result_ck.to_targets_detail(targets_ck, target_id_key='ma_bp')
fd_ck = result_ck.to_full_dict(sources_ck, targets_ck,
                                source_id_key='ma_ct', target_id_key='ma_bp')

print("  to_sources_detail (source_id_key='ma_ct'):")
for row in sd_ck:
    print(f"    {row['ma_ct']}  allocated_total={row['allocated_total']:,.0f}  allocated_to={row['allocated_to']}")

print("\n  to_targets_detail (target_id_key='ma_bp'):")
for row in td_ck:
    print(f"    {row['ma_bp']}  received_total={row['received_total']:,.0f}  received_from={row['received_from']}")

print("\n  to_full_dict (cả 2 keys):")
print(f"    keys: {list(fd_ck.keys())}")
print(f"    sources[0]['ma_ct']          = {fd_ck['sources'][0]['ma_ct']}")
print(f"    sources[0]['allocated_total'] = {fd_ck['sources'][0]['allocated_total']:,.0f}")
print(f"    targets[0]['ma_bp']           = {fd_ck['targets'][0]['ma_bp']}")
print(f"    targets[0]['received_total']  = {fd_ck['targets'][0]['received_total']:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
#  N.  CÔNG THỨC IN ĐẸP / EXPORT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

section("N.  Công thức in đẹp & export helpers")

# ─── N.1  Print bảng nguồn → đích ────────────────────────────────────────────
sub("N.1  Print bảng nguồn → đích (chiều nguồn)")

def print_by_source(result, sources):
    detail = result.to_sources_detail(sources)
    for row in detail:
        sid = row.get('id') or row.get('ma_ct') or '?'
        amt = row.get('amount') or row.get('gia_tri') or 0
        print(f"\n  [{sid}]  gốc: {amt:>16,.0f}  "
              f"phân bổ: {row['allocated_total']:>16,.2f}  "
              f"dư: {row['unallocated']:>10,.2f}")
        for item in row['allocated_to']:
            print(f"     → {item['target_id']:10}  {item['allocated']:>16,.2f}  "
                  f"({item['ratio']:6.2%})  [{item['method']}]"
                  + (f"  meta={item['meta']}" if item['meta'] else ''))

print_by_source(result, sources)


# ─── N.2  Print bảng đích ← nguồn ────────────────────────────────────────────
sub("N.2  Print bảng đích ← nguồn (chiều đích)")

def print_by_target(result, targets):
    detail = result.to_targets_detail(targets)
    for row in detail:
        tid = row.get('id') or row.get('ma_bp') or '?'
        print(f"\n  [{tid}]  tổng nhận: {row['received_total']:>16,.2f}")
        for item in row['received_from']:
            print(f"     ← {item['source_id']:10}  {item['allocated']:>16,.2f}  "
                  f"({item['ratio']:6.2%})  [{item['method']}]")

print_by_target(result, targets)


# ─── N.3  Export to list of flat rows (cho DataFrame / Excel) ─────────────────
sub("N.3  Export flat rows — dùng cho pandas DataFrame / Excel")

def to_flat_rows(result):
    """Trả về list dict phẳng — 1 dict = 1 dòng phân bổ."""
    return [
        {
            'source_id':     ln.source_id,
            'source_amount': ln.source_amount,
            'target_id':     ln.target_id,
            'allocated':     ln.allocated,
            'ratio_pct':     round(ln.ratio * 100, 4),
            'method':        ln.method,
            'weight':        ln.weight,
        }
        for ln in result.lines
    ]

flat_rows = to_flat_rows(result)
print(f"  {len(flat_rows)} dòng flat:")
header_fmt = "  {{:10}} {{:10}} {{:>16}} {{:>10}} {{:20}} {{:>10}}"
print(header_fmt.format('source_id','target_id','allocated','ratio_pct','method','weight'))
print(f"  {'─'*10} {'─'*10} {'─'*16} {'─'*10} {'─'*20} {'─'*10}")
for r in flat_rows:
    print(f"  {r['source_id']:10} {r['target_id']:10} {r['allocated']:>16,.2f} "
          f"{r['ratio_pct']:>10.4f} {r['method']:20} {r['weight']:>10,.0f}")

print("""
  # Dùng với pandas:
  import pandas as pd
  df = pd.DataFrame(to_flat_rows(result))
  df.groupby('target_id')['allocated'].sum()   # tổng nhận theo đích
  df.groupby('source_id')['allocated'].sum()   # tổng phân bổ theo nguồn
  df.pivot_table(index='source_id', columns='target_id', values='allocated')
""")


# ─── N.4  Export to_sources_detail / to_targets_detail dạng flat ──────────────
sub("N.4  Export to_sources_detail dạng flat rows (bỏ nested list)")

def sources_detail_flat(result, sources, source_id_key='id'):
    """Bỏ nested 'allocated_to', giữ lại totals và field gốc."""
    rows = []
    for row in result.to_sources_detail(sources, source_id_key):
        flat = {k: v for k, v in row.items() if k != 'allocated_to'}
        rows.append(flat)
    return rows

def targets_detail_flat(result, targets, target_id_key='id'):
    """Bỏ nested 'received_from', giữ lại totals và field gốc."""
    rows = []
    for row in result.to_targets_detail(targets, target_id_key):
        flat = {k: v for k, v in row.items() if k != 'received_from'}
        rows.append(flat)
    return rows

print("  sources_detail_flat (không có allocated_to):")
for row in sources_detail_flat(result, sources):
    print(f"    {row}")

print("\n  targets_detail_flat (không có received_from):")
for row in targets_detail_flat(result, targets):
    print(f"    {row}")


# ─── N.5  JSON export từng dạng ───────────────────────────────────────────────
sub("N.5  JSON export — so sánh kích thước các dạng")

sizes = {
    'result.to_dict()':                   len(json.dumps(result.to_dict())),
    'to_sources_detail()':                len(json.dumps(result.to_sources_detail(sources))),
    'to_targets_detail()':                len(json.dumps(result.to_targets_detail(targets))),
    'to_full_dict()':                     len(json.dumps(result.to_full_dict(sources, targets))),
    'sources_detail_flat (no nested)':    len(json.dumps(sources_detail_flat(result, sources))),
    'targets_detail_flat (no nested)':    len(json.dumps(targets_detail_flat(result, targets))),
    'flat_rows (to_flat_rows)':           len(json.dumps(to_flat_rows(result))),
}

print()
for name, size in sizes.items():
    print(f"  {name:45} : {size:>6,} ký tự")


# ══════════════════════════════════════════════════════════════════════════════
#  TÓM TẮT NHANH
# ══════════════════════════════════════════════════════════════════════════════

section("TÓM TẮT — Chọn dạng kết quả phù hợp nhu cầu")

print("""
  ┌──────────────────────────────────────┬────────────────────────────────────────────────┐
  │ Nhu cầu                              │ Dùng                                           │
  ├──────────────────────────────────────┼────────────────────────────────────────────────┤
  │ Tổng đã phân bổ theo nguồn           │ result.source_totals                           │
  │ Tổng nhận được theo đích             │ result.target_totals                           │
  │ Kiểm tra phần dư                     │ result.unallocated                             │
  │ Log / debug nhanh                    │ result.summary()                               │
  │ REST API, JSON, lưu DB               │ result.to_dict()                               │
  │ Mỗi nguồn → list đích (chi tiết)     │ result.to_sources_detail(sources)              │
  │ Mỗi đích ← list nguồn (chi tiết)     │ result.to_targets_detail(targets)              │
  │ Tất cả trong 1 (API đầy đủ)          │ result.to_full_dict(sources, targets)          │
  │ pandas / Excel / CSV                 │ to_flat_rows(result)  [helper tự viết]         │
  │ Nguồn enriched nhưng bỏ nested list  │ sources_detail_flat() [helper tự viết]         │
  │ Tiêu thức từng dòng (mixed)          │ result.lines → ln.method, ln.meta              │
  │ Custom field keys                    │ truyền source_id_key / target_id_key vào       │
  │                                      │ cả allocate() lẫn to_*_detail()               │
  └──────────────────────────────────────┴────────────────────────────────────────────────┘

  KEY FIELDS trên mỗi dòng phân bổ (AllocationLine):
    .source_id      id nguồn
    .source_amount  số tiền gốc của nguồn
    .target_id      id đích
    .allocated      số tiền được phân bổ
    .ratio          tỷ lệ (0.0→1.0)  ×100 → %
    .method         tiêu thức — 'qty','equal','amount','weight','pct',
                                'manual_amount','manual_pct',
                                'mixed:manual_amount','mixed:manual_pct(X%)','mixed:qty',...
    .weight         trọng số gốc dùng tính ratio (qty=100, amount=5M, ...)
    .meta           dict bổ sung — mixed có 'mixed_stage', 'residual_amount'
""")
