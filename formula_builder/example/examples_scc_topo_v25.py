"""
examples_scc_topo_v25.py
========================
Ví dụ thực tế sản xuất cho engine_v25.

Phân biệt rõ khi nào dùng topo_sort vs scc_topo_sort,
với các tình huống sản xuất nhôm/kính/nhựa/dệt may.

MỤC LỤC
--------
A. topo_sort  — 4 tình huống DAG không cycle
B. scc_topo_sort — 5 tình huống có cycle
C. Tích hợp vào NxCostPeriod (pattern thực tế)
D. Hướng dẫn chọn đúng hàm
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine_v25 import (
    topo_sort, topo_sort_with_info, TopoSorter,
    scc_topo_sort, scc_topo_sort_with_info, SccTopoSorter,
)

SEP = "=" * 60


# ═══════════════════════════════════════════════════════════════
# PHẦN A — topo_sort: khi biết chắc là DAG (không cycle)
# ═══════════════════════════════════════════════════════════════

def demo_A1_bom_nhom_kinh():
    """
    A1. BOM nhôm kính — cắt profile → lắp ráp khung → lắp kính → hoàn thiện.
    Quan hệ 1 chiều rõ ràng: không có sản phẩm nào là đầu vào của chính nó.

    Khi dùng: công đoạn sản xuất tuyến tính, BOM đơn giản.
    """
    print(f"\n{SEP}")
    print("A1. BOM nhôm kính — chuỗi công đoạn tuyến tính")
    print(SEP)

    work_orders = [
        {
            "wo": "WO-HOAN-THIEN",  # Hoàn thiện cửa
            "name": "Hoàn thiện + đóng gói",
            "deps": ["WO-LAP-KINH"],
        },
        {
            "wo": "WO-LAP-KINH",    # Lắp kính vào khung
            "name": "Lắp kính vào khung",
            "deps": ["WO-LAP-KHUNG", "WO-CAT-KINH"],
        },
        {
            "wo": "WO-CAT-KINH",    # Cắt kính
            "name": "Cắt + mài kính",
            "deps": [],
        },
        {
            "wo": "WO-LAP-KHUNG",   # Lắp ráp khung nhôm
            "name": "Lắp khung nhôm",
            "deps": ["WO-CAT-PROFILE", "WO-EP-SON"],
        },
        {
            "wo": "WO-EP-SON",      # Sơn tĩnh điện
            "name": "Sơn tĩnh điện profile",
            "deps": ["WO-CAT-PROFILE"],
        },
        {
            "wo": "WO-CAT-PROFILE", # Cắt nhôm định hình
            "name": "Cắt profile nhôm",
            "deps": [],
        },
    ]

    sorted_wo = topo_sort(
        items   = work_orders,
        id_fn   = lambda x: x["wo"],
        deps_fn = lambda x: x["deps"],
    )

    print("Thứ tự tính giá thành:")
    for i, wo in enumerate(sorted_wo, 1):
        deps_str = " ← " + ", ".join(wo["deps"]) if wo["deps"] else ""
        print(f"  {i}. {wo['wo']}: {wo['name']}{deps_str}")
    # → WO-CAT-PROFILE, WO-EP-SON, WO-CAT-KINH, WO-LAP-KHUNG, WO-LAP-KINH, WO-HOAN-THIEN


def demo_A2_bom_nhieu_cap():
    """
    A2. BOM nhiều cấp — sản xuất nhựa masterbatch.
    NVL → Compound → Granule → Film → Túi thành phẩm.
    Đây là DAG vì không có sản phẩm nào quay ngược lên cấp trước.

    Khi dùng: multi-level BOM, supply chain 1 chiều.
    """
    print(f"\n{SEP}")
    print("A2. BOM nhiều cấp — nhựa masterbatch")
    print(SEP)

    lsx_list = [
        {"lsx": "LSX-TUI",      "sp": "Túi PE thành phẩm", "deps": ["LSX-FILM"]},
        {"lsx": "LSX-FILM",     "sp": "Film PE",           "deps": ["LSX-GRANULE"]},
        {"lsx": "LSX-GRANULE",  "sp": "Hạt nhựa PE",       "deps": ["LSX-COMPOUND"]},
        {"lsx": "LSX-COMPOUND", "sp": "Compound base",     "deps": ["LSX-MIXING"]},
        {"lsx": "LSX-MIXING",   "sp": "Hỗn hợp NVL",      "deps": []},
        # LSX song song — không phụ thuộc nhau
        {"lsx": "LSX-MAST-R",   "sp": "Red masterbatch",   "deps": ["LSX-MIXING"]},
        {"lsx": "LSX-MAST-B",   "sp": "Blue masterbatch",  "deps": ["LSX-MIXING"]},
    ]

    info = topo_sort_with_info(
        items   = lsx_list,
        id_fn   = lambda x: x["lsx"],
        deps_fn = lambda x: x["deps"],
    )

    print("Kết quả topo sort:")
    print(info.summary())


def demo_A3_work_order_approval():
    """
    A3. Approval workflow — phê duyệt kế hoạch sản xuất.
    P-GD phê duyệt sau P-KT và P-SX.
    P-KT và P-SX độc lập nhau (có thể xử lý song song).

    Khi dùng: workflow phê duyệt, task dependencies.
    """
    print(f"\n{SEP}")
    print("A3. Approval workflow — kế hoạch sản xuất")
    print(SEP)

    tasks = [
        {"id": "DUYET-GD",  "name": "GĐ phê duyệt kế hoạch", "depends_on": ["DUYET-KT", "DUYET-SX"]},
        {"id": "DUYET-KT",  "name": "Kế toán duyệt chi phí",  "depends_on": ["LAP-KH"]},
        {"id": "DUYET-SX",  "name": "Sản xuất duyệt NVL",     "depends_on": ["LAP-KH"]},
        {"id": "LAP-KH",    "name": "Lập kế hoạch sản xuất",  "depends_on": []},
        {"id": "THUC-HIEN", "name": "Thực hiện sản xuất",     "depends_on": ["DUYET-GD"]},
    ]

    sorted_tasks = topo_sort(
        items   = tasks,
        id_fn   = lambda t: t["id"],
        deps_fn = lambda t: t["depends_on"],
    )

    print("Thứ tự xử lý:")
    for t in sorted_tasks:
        deps = " ← " + ", ".join(t["depends_on"]) if t["depends_on"] else " (bắt đầu)"
        print(f"  {t['id']}: {t['name']}{deps}")


def demo_A4_gl_posting_order():
    """
    A4. Thứ tự hạch toán GL — closing period.
    Một số bút toán phải đợi bút toán khác ghi trước.
    Đây là DAG vì GL không hạch toán ngược.

    Khi dùng: GL closing sequence, period-end procedures.
    """
    print(f"\n{SEP}")
    print("A4. GL closing order — kết thúc kỳ kế toán")
    print(SEP)

    gl_steps = [
        {"step": "CLOSE-PL",   "desc": "Kết chuyển P&L",        "after": ["ALLOC-OH", "COST-WO"]},
        {"step": "ALLOC-OH",   "desc": "Phân bổ chi phí SXC",   "after": ["POST-DIRECT"]},
        {"step": "COST-WO",    "desc": "Tính giá thành WO",      "after": ["ALLOC-OH", "POST-DIRECT"]},
        {"step": "POST-DIRECT","desc": "Hạch toán CP trực tiếp", "after": []},
        {"step": "REPOST-SLE", "desc": "Repost Stock Ledger",    "after": ["COST-WO"]},
        {"step": "CLOSE-INV",  "desc": "Đóng kho cuối kỳ",      "after": ["REPOST-SLE"]},
    ]

    sorted_steps = topo_sort(
        items   = gl_steps,
        id_fn   = lambda x: x["step"],
        deps_fn = lambda x: x["after"],
    )

    print("Thứ tự đóng sổ:")
    for i, s in enumerate(sorted_steps, 1):
        print(f"  Bước {i}: [{s['step']}] {s['desc']}")


# ═══════════════════════════════════════════════════════════════
# PHẦN B — scc_topo_sort: khi CÓ THỂ có cycle
# ═══════════════════════════════════════════════════════════════

def demo_B1_btp_quay_vong_2lsx():
    """
    B1. BTP quay vòng 2 LSX — tình huống gốc của bài toán.
    LSX1 (đúc phôi) → cấp BTP cho LSX2 (gia công CNC)
    LSX2 (gia công CNC) → cấp lại phế phẩm tái chế cho LSX1

    Đây là tình huống phổ biến trong: đúc + gia công, dệt + nhuộm,
    sơ chế + tinh chế nguyên liệu.

    Khi dùng: BẮT BUỘC dùng scc_topo_sort vì có cycle thật.
    """
    print(f"\n{SEP}")
    print("B1. BTP quay vòng 2 LSX — đúc + gia công CNC")
    print(SEP)

    lsx_data = [
        {
            "voucher_name"              : "LSX-DUC",
            "production_item"           : "Phôi nhôm A380",
            "direct_cost"               : 120_000_000,
            "finish_goods_qty"          : 1000,  # kg phôi
            "semi_finish_goods_qty"     : 0,
            # Nhận phế liệu tái chế từ LSX-CNC (cycle!)
            "semi_product_input_detail" : json.dumps([
                {"work_order": "LSX-CNC", "qty": 50, "is_fg": 0}  # 50kg phoi thai
            ]),
        },
        {
            "voucher_name"              : "LSX-CNC",
            "production_item"           : "Chi tiết gia công",
            "direct_cost"               : 80_000_000,
            "finish_goods_qty"          : 800,   # cái thành phẩm
            "semi_finish_goods_qty"     : 100,   # BTP chưa hoàn thiện
            # Nhận phôi từ LSX-DUC
            "semi_product_input_detail" : json.dumps([
                {"work_order": "LSX-DUC", "qty": 400, "is_fg": 1}  # 400kg phoi
            ]),
        },
        {
            "voucher_name"              : "LSX-FINISH",
            "production_item"           : "Sản phẩm hoàn chỉnh",
            "direct_cost"               : 30_000_000,
            "finish_goods_qty"          : 700,
            "semi_finish_goods_qty"     : 0,
            # Chỉ nhận từ LSX-CNC, không cycle
            "semi_product_input_detail" : json.dumps([
                {"work_order": "LSX-CNC", "qty": 700, "is_fg": 1}
            ]),
        },
    ]

    def deps_fn(item):
        raw = item.get("semi_product_input_detail") or "[]"
        try:
            return [d["work_order"] for d in json.loads(raw) if d.get("work_order")]
        except:
            return []

    info = scc_topo_sort_with_info(
        items   = lsx_data,
        id_fn   = lambda x: x["voucher_name"],
        deps_fn = deps_fn,
    )

    print(info.summary())
    print("\nSorted order:", [x["voucher_name"] for x in info.items])
    print("\nXử lý: cycle group [LSX-DUC ↔ LSX-CNC] bằng simultaneous equations")
    print("       sau đó tính LSX-FINISH với giá actual của LSX-CNC đã biết")

    # Demo tính giá với iterative convergence trong SCC
    _calc_costs_iterative(lsx_data, info, deps_fn)


def _calc_costs_iterative(data, scc_info, deps_fn, epsilon=0.01):
    """
    Tính giá thành cho từng SCC theo condensation order.
    Cycle SCC → iterative convergence.
    Non-cycle SCC → tính 1 lần.
    """
    data_map = {x["voucher_name"]: x for x in data}

    def flt(v):
        try: return float(v or 0)
        except: return 0.0

    def calc_item(item):
        fg  = flt(item.get("finish_goods_qty"))
        sfg = flt(item.get("semi_finish_goods_qty"))
        dc  = flt(item.get("direct_cost"))
        tq  = fg + sfg

        raw = item.get("semi_product_input_detail") or "[]"
        details = json.loads(raw) if isinstance(raw, str) else raw
        piv = sum(
            flt(d.get("qty")) * flt(data_map.get(d["work_order"], {}).get(
                "fn_unit_cost" if d.get("is_fg") else "semi_unit_cost", 0))
            for d in details if d.get("work_order")
        )

        direct_fg   = (dc * fg / tq) if tq else 0
        total_cost  = direct_fg + piv
        item["fn_unit_cost"]   = total_cost / fg  if fg  else 0
        item["semi_unit_cost"] = dc / tq          if (sfg and tq) else 0
        item["total_cost"]     = total_cost
        item["semi_product_input_value"] = piv

    print("\n--- Tính giá theo condensation order ---")
    for scc_idx in scc_info.condensation_order:
        scc_nodes = scc_info.sccs[scc_idx]
        is_cycle  = len(scc_nodes) > 1
        scc_items = [data_map[n] for n in scc_nodes if n in data_map]

        if not is_cycle:
            calc_item(scc_items[0])
            item = scc_items[0]
            print(f"  [{scc_nodes[0]}] 1 lần  → fn_unit_cost = {item['fn_unit_cost']:>12,.2f}")
        else:
            # Init: direct cost only
            for it in scc_items:
                fg = flt(it.get("finish_goods_qty"))
                it["fn_unit_cost"]   = flt(it.get("direct_cost")) / fg if fg else 0
                it["semi_unit_cost"] = 0

            for iteration in range(1, 200):
                old = {it["voucher_name"]: it["fn_unit_cost"] for it in scc_items}
                for it in scc_items:
                    calc_item(it)
                delta = max(abs(it["fn_unit_cost"] - old[it["voucher_name"]]) for it in scc_items)
                if delta < epsilon:
                    print(f"  CYCLE {scc_nodes}: hội tụ sau {iteration} lần, Δ={delta:.4f}")
                    break
            for it in scc_items:
                print(f"    [{it['voucher_name']}] fn_unit_cost = {it['fn_unit_cost']:>12,.2f}")

    print("\n--- Kết quả cuối ---")
    for item in scc_info.items:
        wo = item["voucher_name"]
        it = data_map[wo]
        print(f"  {wo:<15} fn_unit_cost = {it['fn_unit_cost']:>12,.2f}  total = {it['total_cost']:>15,.0f}")


def demo_B2_3_lsx_cycle():
    """
    B2. 3 LSX cycle — sản xuất dệt may.
    LSX-SX-SOI  (kéo sợi)    → cấp sợi cho LSX-DET
    LSX-DET     (dệt vải)    → cấp vải thô cho LSX-NHOM
    LSX-NHOM    (nhuộm vải)  → cấp lại vải nhuộm phế phẩm cho LSX-SX-SOI

    3-way cycle: SOI → DET → NHOM → SOI
    """
    print(f"\n{SEP}")
    print("B2. 3-LSX cycle — kéo sợi → dệt → nhuộm (quay vòng)")
    print(SEP)

    lsx_det_may = [
        {
            "voucher_name": "LSX-SOI",
            "production_item": "Sợi bông",
            "direct_cost": 50_000_000,
            "finish_goods_qty": 500,  # kg sợi
            "semi_finish_goods_qty": 0,
            "semi_product_input_detail": json.dumps([
                {"work_order": "LSX-NHOM", "qty": 20, "is_fg": 0}  # vải phế nhận lại
            ]),
        },
        {
            "voucher_name": "LSX-DET",
            "production_item": "Vải mộc",
            "direct_cost": 30_000_000,
            "finish_goods_qty": 300,  # m2 vải
            "semi_finish_goods_qty": 50,
            "semi_product_input_detail": json.dumps([
                {"work_order": "LSX-SOI", "qty": 400, "is_fg": 1}  # sợi
            ]),
        },
        {
            "voucher_name": "LSX-NHOM",
            "production_item": "Vải nhuộm",
            "direct_cost": 20_000_000,
            "finish_goods_qty": 250,  # m2 vải nhuộm
            "semi_finish_goods_qty": 0,
            "semi_product_input_detail": json.dumps([
                {"work_order": "LSX-DET", "qty": 280, "is_fg": 1}  # vải mộc
            ]),
        },
        {
            "voucher_name": "LSX-MAY",
            "production_item": "Áo thành phẩm",
            "direct_cost": 25_000_000,
            "finish_goods_qty": 200,
            "semi_finish_goods_qty": 0,
            # Không cycle — chỉ nhận từ LSX-NHOM
            "semi_product_input_detail": json.dumps([
                {"work_order": "LSX-NHOM", "qty": 220, "is_fg": 1}
            ]),
        },
    ]

    def deps_fn(x):
        try:
            return [d["work_order"] for d in json.loads(x.get("semi_product_input_detail") or "[]")
                    if d.get("work_order")]
        except: return []

    info = scc_topo_sort_with_info(
        lsx_det_may,
        id_fn   = lambda x: x["voucher_name"],
        deps_fn = deps_fn,
    )
    print(info.summary())


def demo_B3_multi_cycle_doc_lap():
    """
    B3. Nhiều cycle độc lập — 2 nhóm sản xuất riêng biệt.

    Nhóm A: LSX-A1 ↔ LSX-A2  (cycle nhôm)
    Nhóm B: LSX-B1 ↔ LSX-B2 ↔ LSX-B3  (cycle nhựa)
    LSX-C: phụ thuộc cả 2 nhóm (không cycle)

    SCC solver phát hiện đúng 2 cycle group riêng biệt.
    """
    print(f"\n{SEP}")
    print("B3. 2 cycle độc lập + 1 WO phụ thuộc cả 2")
    print(SEP)

    data = [
        # Nhóm nhôm: A1 ↔ A2
        {"id": "A1", "name": "Cán nhôm", "deps": ["A2"]},
        {"id": "A2", "name": "Ép nhôm",  "deps": ["A1"]},
        # Nhóm nhựa: B1 → B2 → B3 → B1
        {"id": "B1", "name": "Trộn nhựa",    "deps": ["B3"]},
        {"id": "B2", "name": "Ép nhựa",      "deps": ["B1"]},
        {"id": "B3", "name": "Nghiền tái chế","deps": ["B2"]},
        # Không cycle — nhận từ cả A và B
        {"id": "C",  "name": "Lắp ráp cuối", "deps": ["A1", "B2"]},
    ]

    info = scc_topo_sort_with_info(
        data,
        id_fn   = lambda x: x["id"],
        deps_fn = lambda x: x["deps"],
    )
    print(info.summary())
    print(f"\nSorted: {[x['id'] for x in info.items]}")
    print(f"→ 2 cycle group xử lý trước, C xử lý cuối sau khi cả 2 nhóm xong")


def demo_B4_cost_center_reciprocal():
    """
    B4. Cost center reciprocal allocation — SAP CO style.
    Điển hình trong kế toán quản trị:
    - Bộ phận Kho hỗ trợ cho Sản xuất (chi phí)
    - Bộ phận Sản xuất hỗ trợ lại cho Kho (giờ máy vận chuyển)

    Đây là "reciprocal service allocation" — chuẩn GAAP.
    scc_topo_sort detect đúng cycle và nhóm để giải phương trình.
    """
    print(f"\n{SEP}")
    print("B4. Cost center reciprocal allocation (SAP CO)")
    print(SEP)

    cost_centers = [
        {
            "cc": "CC-SX",  # Sản xuất
            "name": "Phân xưởng sản xuất",
            "direct_cost": 200_000_000,
            "reciprocal_from": ["CC-KHO"],    # nhận hỗ trợ từ Kho
            "reciprocal_qty": {"CC-KHO": 100}, # 100 giờ vận chuyển từ Kho
        },
        {
            "cc": "CC-KHO", # Kho
            "name": "Bộ phận kho",
            "direct_cost": 50_000_000,
            "reciprocal_from": ["CC-SX"],      # nhận hỗ trợ từ SX
            "reciprocal_qty": {"CC-SX": 40},   # 40 giờ máy từ SX
        },
        {
            "cc": "CC-QLD", # Quản lý doanh nghiệp — không cycle
            "name": "Quản lý doanh nghiệp",
            "direct_cost": 80_000_000,
            "reciprocal_from": ["CC-SX", "CC-KHO"],
            "reciprocal_qty": {},
        },
    ]

    info = scc_topo_sort_with_info(
        cost_centers,
        id_fn   = lambda x: x["cc"],
        deps_fn = lambda x: x["reciprocal_from"],
    )
    print(info.summary())
    print("\n→ Giải SCC [CC-SX ↔ CC-KHO] bằng simultaneous equations (SAP method)")
    print("  sau đó phân bổ vào CC-QLD với giá đã tính")


def demo_B5_reuse_sorter():
    """
    B5. SccTopoSorter — tái sử dụng nhiều kỳ.
    Cùng 1 sorter dùng cho nhiều tháng, chỉ thay data.

    Tình huống: mỗi tháng đóng kỳ có tập WO khác nhau,
    nhưng cấu trúc phụ thuộc (id_fn/deps_fn) không đổi.
    """
    print(f"\n{SEP}")
    print("B5. SccTopoSorter — tái sử dụng qua nhiều kỳ")
    print(SEP)

    sorter = SccTopoSorter(
        id_fn   = lambda x: x["voucher_name"],
        deps_fn = lambda x: [
            d["work_order"]
            for d in json.loads(x.get("semi_product_input_detail") or "[]")
            if d.get("work_order")
        ],
    )

    # Kỳ tháng 1 — có cycle
    ky_t1 = [
        {"voucher_name": "WO-T1-A", "semi_product_input_detail": json.dumps([{"work_order": "WO-T1-B", "qty": 10, "is_fg": 1}])},
        {"voucher_name": "WO-T1-B", "semi_product_input_detail": json.dumps([{"work_order": "WO-T1-A", "qty": 5,  "is_fg": 0}])},
        {"voucher_name": "WO-T1-C", "semi_product_input_detail": json.dumps([{"work_order": "WO-T1-A", "qty": 20, "is_fg": 1}])},
    ]
    info1 = sorter.sort_with_info(ky_t1)
    print(f"Tháng 1: has_cycle={info1.has_cycle}, order={info1.order}")

    # Kỳ tháng 2 — không cycle
    ky_t2 = [
        {"voucher_name": "WO-T2-X", "semi_product_input_detail": json.dumps([])},
        {"voucher_name": "WO-T2-Y", "semi_product_input_detail": json.dumps([{"work_order": "WO-T2-X", "qty": 15, "is_fg": 1}])},
        {"voucher_name": "WO-T2-Z", "semi_product_input_detail": json.dumps([{"work_order": "WO-T2-Y", "qty": 8,  "is_fg": 1}])},
    ]
    info2 = sorter.sort_with_info(ky_t2)
    print(f"Tháng 2: has_cycle={info2.has_cycle}, order={info2.order}")
    print("→ Cùng 1 sorter object, dùng lại không cần tạo lại")


# ═══════════════════════════════════════════════════════════════
# PHẦN C — Pattern tích hợp vào NxCostPeriod
# ═══════════════════════════════════════════════════════════════

def demo_C_integration_pattern():
    """
    C. Pattern tích hợp thực tế vào NxCostPeriod.calculate_detail().

    Đây là replacement cho:
        data = topo_sort(items, id_fn=..., deps_fn=...)
    trong get_cost_details() của NxCostPeriod.
    """
    print(f"\n{SEP}")
    print("C. Pattern tích hợp vào NxCostPeriod")
    print(SEP)

    code = '''
# ── Trong NxCostPeriod.get_cost_details() ──────────────────────
# Import thêm ở đầu file:
from engine_v25 import scc_topo_sort_with_info

# TRƯỚC (engine_v24 — chỉ đúng với DAG):
# _semi_cache = {}
# for _item in data:
#     _semi_cache[_item["voucher_name"]] = json.loads(...)
# data = topo_sort(
#     items   = data,
#     id_fn   = lambda x: x["voucher_name"],
#     deps_fn = lambda x: [...],
# )

# SAU (engine_v25 — đúng với cả DAG và cycle):
def _wo_deps_fn(item):
    raw = item.get("semi_product_input_detail") or "[]"
    try:
        return [d["work_order"] for d in json.loads(raw) if d.get("work_order")]
    except:
        return []

scc_info = scc_topo_sort_with_info(
    data,
    id_fn   = lambda x: x["voucher_name"],
    deps_fn = _wo_deps_fn,
)

# data đã được sort đúng thứ tự
data = scc_info.items

# Log nếu có cycle để kế toán biết
if scc_info.has_cycle:
    for cg in scc_info.cycle_groups:
        frappe.log_error(
            message=f"Cycle detected: {' ↔ '.join(cg)}\\n"
                    f"Sẽ dùng iterative convergence trong calculate_detail()",
            title="NxCostPeriod — Cycle WO"
        )

# ── Trong NxCostPeriod.calculate_detail() ─────────────────────
# KHÔNG thay đổi gì — vì calculate_detail() đã loop data
# và tra cứu fn_unit_cost của WO khác.
# Với thứ tự đúng từ scc_topo_sort, WO không cycle sẽ tính đúng.
# WO trong cycle → cần thêm outer loop hội tụ:

# Cách đơn giản nhất — wrap calculate_detail trong while loop:
MAX_ITER = 50
EPSILON  = 0.01
prev_costs = {}
for iteration in range(MAX_ITER):
    sum_data = self.calculate_detail(json_data=json_data, wo_amounts=wo_amounts)
    # Kiểm tra hội tụ
    curr_costs = {
        item["voucher_name"]: item.get("fn_unit_cost", 0)
        for item in json_data["data"]
    }
    if prev_costs:
        delta = max(abs(curr_costs[k] - prev_costs[k]) for k in curr_costs)
        if delta < EPSILON:
            break
    prev_costs = curr_costs
'''
    print(code)


# ═══════════════════════════════════════════════════════════════
# PHẦN D — Hướng dẫn chọn đúng hàm
# ═══════════════════════════════════════════════════════════════

def demo_D_decision_guide():
    print(f"\n{SEP}")
    print("D. Hướng dẫn chọn topo_sort vs scc_topo_sort")
    print(SEP)

    guide = """
    DÙNG topo_sort KHI:
    ├── BOM 1 chiều (NVL → BTP → TP, không quay ngược)
    ├── Approval workflow (A phê duyệt sau B phê duyệt)
    ├── Task dependencies (task A chờ task B)
    ├── GL closing order (hạch toán theo thứ tự)
    ├── Supply chain đơn giản (nhà cung cấp → SX → khách)
    └── Khi CHẮC CHẮN không có cycle trong data

    DÙNG scc_topo_sort KHI:
    ├── BTP/TP quay vòng giữa các LSX (tình huống gốc)
    ├── Phế phẩm/phế liệu tái đưa vào sản xuất
    ├── Cost center reciprocal allocation (SAP CO)
    ├── Co-products / by-products ảnh hưởng lẫn nhau
    ├── Bất kỳ khi nào KHÔNG CHẮC có cycle hay không
    └── → Safe mặc định: dùng scc_topo_sort luôn cũng được
        (overhead nhỏ nếu không có cycle: thêm O(V+E) Tarjan)

    KẾT QUẢ CYCLE GROUP:
    ├── Dùng iterative convergence (Gauss-Seidel) trong SCC
    ├── Thường hội tụ < 20 lần với data thực tế
    ├── KHÔNG hội tụ khi: tổng tỉ lệ phân bổ > 100%
    │   (WO nhận nhiều hơn output của nguồn → data sai)
    └── Giải trình: hiển thị hệ phương trình + nghiệm (như SAP CO report)
    """
    print(guide)


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\n" + "█" * 60)
    print("  PHẦN A — topo_sort: DAG, không cycle")
    print("█" * 60)
    demo_A1_bom_nhom_kinh()
    demo_A2_bom_nhieu_cap()
    demo_A3_work_order_approval()
    demo_A4_gl_posting_order()

    print("\n\n" + "█" * 60)
    print("  PHẦN B — scc_topo_sort: có thể cycle")
    print("█" * 60)
    demo_B1_btp_quay_vong_2lsx()
    demo_B2_3_lsx_cycle()
    demo_B3_multi_cycle_doc_lap()
    demo_B4_cost_center_reciprocal()
    demo_B5_reuse_sorter()

    demo_C_integration_pattern()
    demo_D_decision_guide()
