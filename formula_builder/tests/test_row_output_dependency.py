"""Vá lỗi "công thức header đọc output_field của dòng" — 8 ca bắt buộc.

TRIỆU CHỨNG người dùng thấy (đo được TRƯỚC bản vá), với cấu hình
``subtotal = sum(r.get('amount',0) for r in items)``:

    • gọi LẦN ĐẦU               → subtotal = 0     (đúng phải 350)
    • gọi LẦN HAI, input y nguyên → subtotal = 350   (đúng, nhưng chỉ do MAY)
    • sửa qty dòng A từ 2 thành 10 → subtotal = 350  (đúng phải 1150) ⇒ SAI Ở TIỀN

Nguyên nhân gốc: `FlexibleFormulaEngine` chạy MỘT lượt DAG cho cả công thức
dòng lẫn công thức header, còn việc ghi kết quả vào ``output_field`` của dòng
(`_write_back`) xảy ra SAU lượt đó. Lượt sau đọc phải giá trị do lượt TRƯỚC ghi
vào — vì ``inputs[table_key]`` là CÙNG các dict bị mutate in-place. Không có
exception nào: đây là lỗi im lặng, sai ở tiền.

Bản vá: "lượt hai có mục tiêu" — giữ nguyên lượt 1, chỉ chạy thêm một lượt nữa
cho ĐÚNG những công thức đọc-dòng (consumer) và các node phía sau chúng.

File này chạy được KHÔNG cần site Frappe: engine thuần, ⛔ không import frappe.
⛔ KHÔNG chạy bằng `bench run-tests` (before_tests() của ERPNext xoá sạch Item Price).
"""

import re
import unittest
from collections import defaultdict
from unittest import mock

from formula_builder.flexible_formula_engine import (
    ChildTableConfig,
    EngineConfig,
    FlexibleFormulaEngine,
)
from formula_builder.formula_utils import FormulaEngine, html_unescape_formula
from formula_builder.formula_utils.topo import DependencyGraph, extract_identifiers


# ─────────────────────────────────────────────────────────────────────────────
# Dữ liệu dùng chung của các ca test
# ─────────────────────────────────────────────────────────────────────────────

def _items_rows():
    """Bộ dòng MỚI mỗi lần gọi — tránh ca test này nhìn thấy ``amount`` do ca
    test trước ghi vào (write-back mutate tại chỗ trên chính dict dòng)."""
    return [
        {"ref": "A", "formula": "qty * price", "qty": 2, "price": 100},
        {"ref": "B", "formula": "qty * price", "qty": 3, "price": 50},
    ]


def _reading_cfg(**overrides) -> EngineConfig:
    """Config DÙNG mẫu đọc-dòng: subtotal đọc ``items[*]['amount']``.

    ``amount`` là ``output_field`` của chính bảng đó ⇒ trước bản vá lượt 1 đọc
    phải 0, lượt 2 trở đi đọc phải số cũ.
    """
    kwargs = dict(
        child_tables=[ChildTableConfig(
            table_key="items", formula_field="formula", id_field="ref",
            row_fields=["qty", "price"], output_field="amount",
        )],
        global_formulas=[
            {"name": "subtotal",   "formula": "sum(r.get('amount',0) for r in items)"},
            {"name": "grandtotal", "formula": "subtotal + shipping_fee"},
        ],
        extra_context={"shipping_fee": 35},
    )
    kwargs.update(overrides)
    return EngineConfig(**kwargs)


def _direct_cfg() -> EngineConfig:
    """Config ĐỐI CHỨNG (hồi quy): ⛔ KHÔNG dùng mẫu đọc-dòng — subtotal tham
    chiếu thẳng tên biến dòng (``K1 + K2``), tức là có cạnh DAG tường minh."""
    return EngineConfig(
        child_tables=[ChildTableConfig(
            table_key="items", formula_field="formula", id_field="ref",
            row_fields=["qty", "price"], output_field="amount",
        )],
        global_formulas=[
            {"name": "subtotal",   "formula": "A + B"},
            {"name": "grandtotal", "formula": "subtotal + shipping_fee"},
        ],
        extra_context={"shipping_fee": 35},
    )


def _legacy_values(eng: FlexibleFormulaEngine, inputs: dict) -> dict:
    """Bản sao ĐƯỜNG CŨ (trước bản vá): đúng 1 lượt DAG + write-back, ⛔ không
    có lượt hai. Dùng làm ĐỐI CHỨNG HỒI QUY cho ca 4: cấu hình không dùng mẫu
    đọc-dòng thì bản vá phải cho ra con số TRÙNG KHÍT.

    Sao chép lại logic cũ chứ ⛔ không gọi thẳng engine hiện tại, vì engine hiện
    tại đã mang bản vá — gọi nó thì phép đối chứng thành so chính nó với nó.
    """
    context = {**eng.config.extra_context, **inputs}
    all_formulas, _ = eng._build_all_formulas(context)
    engine = FormulaEngine(**eng._engine_kwargs(all_formulas))
    raw_results = engine.calculate(context)
    eng._write_back(inputs, raw_results)
    return raw_results


class TestRowOutputDependency(unittest.TestCase):
    """7 ca (1–7) cho bản vá "lượt hai có mục tiêu".

    Bọc trong `unittest.TestCase` ⛔ KHÔNG phải để dùng tiện ích của nó, mà vì
    `bench run-tests` gom test bằng `unittest.TestLoader().loadTestsFromModule()`
    — hàm `test_*` ở cấp module bị bỏ qua IM LẶNG (đo được: tệp này gom 0 test
    khi còn để hàm trần). 15 tệp test còn lại của repo đều dùng lớp.
    """

    # ─────────────────────────────────────────────────────────────────────────────
    # Ca 1 — lần gọi ĐẦU phải đọc đúng số vừa tính của dòng
    # ─────────────────────────────────────────────────────────────────────────────

    def test_1_lan_goi_dau_doc_dung_output_field_cua_dong(self):
        eng = FlexibleFormulaEngine(_reading_cfg())
        rows = _items_rows()

        result = eng.calculate({"items": rows})

        # A = 2*100 = 200, B = 3*50 = 150 ⇒ subtotal 350, grandtotal 350 + 35.
        assert result.values["subtotal"] == 350, f"subtotal = {result.values['subtotal']!r}"
        assert result.values["grandtotal"] == 385
        # Kết quả từng dòng vẫn nguyên (lượt 1 không bị đụng tới).
        assert result.values["A"] == 200
        assert result.values["B"] == 150
        # Write-back vẫn ghi đúng vào output_field của dòng.
        assert [r["amount"] for r in rows] == [200, 150]
        assert result.row_results["items"] == {"A": 200, "B": 150}


    # ─────────────────────────────────────────────────────────────────────────────
    # Ca 2 — gọi lần hai, KHÔNG đổi input: ⛔ không nhân đôi, ⛔ không đổi số
    # ─────────────────────────────────────────────────────────────────────────────

    def test_2_goi_lan_hai_khong_doi_input_thi_so_khong_doi(self):
        eng = FlexibleFormulaEngine(_reading_cfg())
        rows = _items_rows()

        first = eng.calculate({"items": rows})
        second = eng.calculate({"items": rows})

        assert second.values["subtotal"] == 350, (
            f"subtotal lượt 2 = {second.values['subtotal']!r} — bị nhân đôi hoặc đổi số"
        )
        assert second.values["grandtotal"] == 385
        assert dict(second.values) == dict(first.values)
        assert second.row_results == first.row_results
        assert [r["amount"] for r in rows] == [200, 150]


    # ─────────────────────────────────────────────────────────────────────────────
    # Ca 3 — đổi qty rồi gọi lại: phải ra số MỚI, ⛔ không phải số cũ
    # ─────────────────────────────────────────────────────────────────────────────

    def test_3_doi_qty_roi_goi_lai_thi_ra_so_moi(self):
        eng = FlexibleFormulaEngine(_reading_cfg())
        rows = _items_rows()

        eng.calculate({"items": rows})          # lượt 1: ghi amount 200/150 vào dòng
        rows[0]["qty"] = 10                     # A: 200 → 1000

        result = eng.calculate({"items": rows})

        assert result.values["A"] == 1000
        assert result.values["subtotal"] == 1150, (
            f"subtotal = {result.values['subtotal']!r} — còn đọc số CŨ của lượt trước"
        )
        assert result.values["grandtotal"] == 1185
        assert [r["amount"] for r in rows] == [1000, 150]


    # ─────────────────────────────────────────────────────────────────────────────
    # Ca 4 — cấu hình KHÔNG dùng mẫu đọc-dòng: đối chứng hồi quy
    # ─────────────────────────────────────────────────────────────────────────────

    def test_4_cau_hinh_khong_dung_mau_doc_dong_khong_doi_ket_qua(self):
        """Đối chứng hồi quy 2 lớp:

        (a) HÀNH VI: không có consumer ⇒ `_second_pass_formulas()` trả rỗng ⇒ bản vá
            thoát sớm, ⛔ không dựng engine thứ hai (zero-cost).
        (b) SỐ LIỆU: con số phải TRÙNG KHÍT đường cũ (`_legacy_values`).
        """
        eng = FlexibleFormulaEngine(_direct_cfg())

        seen = {"calls": 0, "last": None}
        _real = FlexibleFormulaEngine._second_pass_formulas

        def _spy(self, engine, all_formulas):
            seen["calls"] += 1
            seen["last"] = _real(self, engine, all_formulas)
            return seen["last"]

        with mock.patch.object(FlexibleFormulaEngine, "_second_pass_formulas", _spy):
            result = eng.calculate({"items": _items_rows()})

        assert seen["calls"] == 1
        assert seen["last"] == [], "cấu hình này ⛔ không được coi là có công thức đọc-dòng"

        expected = {"A": 200, "B": 150, "subtotal": 350, "grandtotal": 385}
        assert result.values == expected
        assert result.row_results == {"items": {"A": 200, "B": 150}}

        # (b) đường cũ (1 lượt) phải cho ra ĐÚNG cùng con số trên bộ dòng y hệt.
        legacy = _legacy_values(eng, {"items": _items_rows()})
        assert legacy == expected


    # ─────────────────────────────────────────────────────────────────────────────
    # Ca 5 — assertion phải thấy số CUỐI, ⛔ không báo lỗi oan
    # ─────────────────────────────────────────────────────────────────────────────

    def test_5_assertion_khong_bao_loi_oan(self):
        """Lượt 1 thấy `subtotal = 0` (lỗi đang vá) nên `subtotal > 0` sẽ FAIL oan.

        Ca này kiểm CẢ HAI CHIỀU (đối chứng dương): assertion đúng thì ⛔ không được
        báo, và assertion SAI thì ⛔ vẫn phải báo — nếu chỉ kiểm chiều "không có
        lỗi", một bản vá lỡ TẮT assertion sẽ vẫn xanh.
        """
        cfg = _reading_cfg(assertions=[
            {"name": "subtotal_duong", "expr": "subtotal > 0",
             "message": "subtotal phải dương"},
            {"name": "subtotal_am", "expr": "subtotal < 0",
             "message": "subtotal phải âm"},
        ])
        result = FlexibleFormulaEngine(cfg).calculate({"items": _items_rows()})

        assert result.values["subtotal"] == 350
        assert "subtotal_duong" not in result.errors, (
            f"assertion báo oan theo số lượt 1: {result.errors.get('subtotal_duong')!r}"
        )
        # Đối chứng dương: assertion SAI vẫn phải có mặt ⇒ assertion thật sự đã chạy.
        assert result.errors.get("subtotal_am") == "subtotal phải âm"
        assert set(result.errors) == {"subtotal_am"}


    # ─────────────────────────────────────────────────────────────────────────────
    # Ca 6 — công thức DÒNG tham chiếu công thức HEADER: vẫn chạy như trước
    # ─────────────────────────────────────────────────────────────────────────────

    def test_6_cong_thuc_dong_tham_chieu_cong_thuc_header(self):
        """``TAX_T1: subtotal * rate`` — đây là chiều tham chiếu mà cách chia thô
        "bảng trước, header sau" sẽ làm vỡ. Bản vá ⛔ không được đụng vào nó."""
        cfg = EngineConfig(
            child_tables=[
                ChildTableConfig(
                    table_key="items", formula_field="formula", id_field="ref",
                    row_fields=["qty", "price"], output_field="amount",
                ),
                ChildTableConfig(
                    table_key="taxes", formula_field="formula", id_field="ref",
                    row_fields=["rate"], output_field="tax_amount", prefix="TAX_",
                ),
            ],
            global_formulas=[
                {"name": "subtotal",   "formula": "A + B"},
                {"name": "grandtotal", "formula": "subtotal + TAX_T1"},
            ],
        )
        tax_rows = [{"ref": "T1", "formula": "subtotal * rate", "rate": 0.1}]

        result = FlexibleFormulaEngine(cfg).calculate({
            "items": _items_rows(),
            "taxes": tax_rows,
        })

        assert result.values["A"] == 200
        assert result.values["B"] == 150
        assert result.values["subtotal"] == 350
        assert abs(result.values["TAX_T1"] - 35) < 1e-9
        assert abs(result.values["grandtotal"] - 385) < 1e-9
        assert tax_rows[0]["tax_amount"] == result.values["TAX_T1"]
        assert result.errors == {}


    # ─────────────────────────────────────────────────────────────────────────────
    # Ca 7 — multi_scenario với mẫu đọc-dòng
    # ─────────────────────────────────────────────────────────────────────────────

    def test_7_multi_scenario_voi_mau_doc_dong(self):
        """Mỗi kịch bản phải ra SỐ CỦA NÓ. Đây là ca dễ vỡ nhất nếu bản vá quên
        `_run_engine()`: `calculate()` được vá mà `multi_scenario()` thì không, hoặc
        các kịch bản dùng chung dict dòng nên nhìn thấy kết quả của nhau."""
        eng = FlexibleFormulaEngine(_reading_cfg())
        base_inputs = {"items": _items_rows()}

        results = eng.multi_scenario(
            base_inputs=base_inputs,
            scenarios={
                "base":        {},
                "free_ship":   {"shipping_fee": 0},
                "chi_dong_A":  {"items": [
                    {"ref": "A", "formula": "qty * price", "qty": 10, "price": 100},
                ]},
            },
        )

        assert results["base"].values["subtotal"] == 350
        assert results["base"].values["grandtotal"] == 385
        assert results["free_ship"].values["subtotal"] == 350
        assert results["free_ship"].values["grandtotal"] == 350
        # Kịch bản đổi DỮ LIỆU DÒNG: A = 10*100 = 1000 ⇒ subtotal 1000, ⛔ không 350.
        assert results["chi_dong_A"].values["A"] == 1000
        assert results["chi_dong_A"].values["subtotal"] == 1000
        assert results["chi_dong_A"].values["grandtotal"] == 1035
        # Kịch bản ⛔ không được giẫm lên nhau qua dict dòng dùng chung.
        assert results["base"].row_results["items"] == {"A": 200, "B": 150}
        assert results["chi_dong_A"].row_results["items"] == {"A": 1000}



# ─────────────────────────────────────────────────────────────────────────────
# Ca 8 — `extract_identifiers` sau refactor: ⛔ không đổi hành vi dò định danh
# ─────────────────────────────────────────────────────────────────────────────

# Bản sao NGUYÊN VĂN cách dò định danh TRƯỚC refactor (4 bước nội tuyến trong
# `DependencyGraph.build_from_exprs`). Giữ ở đây làm "bản gốc" để đối chứng —
# ⛔ không import lại từ code sản phẩm, vì như thế phép so thành tự-so-với-mình.
_REF_STRING = re.compile(r"""(?:"[^"]*"|'[^']*')""")
_REF_ATTR = re.compile(r'\.[a-zA-Z_]\w*')
_REF_IDENTIFIER = re.compile(r'[a-zA-Z_]\w*')


def _ref_extract_identifiers(expr: str) -> set:
    expr = html_unescape_formula(expr)
    clean = _REF_STRING.sub('""', expr)
    clean = _REF_ATTR.sub('', clean)
    return set(_REF_IDENTIFIER.findall(clean))


def _ref_edges(exprs: dict):
    """Cạnh DAG theo thuật toán CŨ (trước refactor)."""
    names = set(exprs)
    forward, reverse = defaultdict(set), defaultdict(set)
    for name, expr in exprs.items():
        for dep in _ref_extract_identifiers(expr) & names:
            forward[dep].add(name)
            reverse[name].add(dep)
    return forward, reverse


def _real_edges(edges: dict) -> dict:
    """Chỉ lấy CẠNH THẬT (bỏ khoá có tập rỗng).

    `DependencyGraph` là `defaultdict(set)`: `_detect_cycles()` duyệt
    ``self.graph[node]`` cho MỌI node nên nó tự đẻ ra khoá rỗng cho node không
    có cạnh nào. Khoá rỗng ⛔ không phải cạnh ⇒ phải bỏ trước khi so, nếu không
    phép so báo lệch vì lý do chẳng liên quan gì tới refactor.
    """
    return {k: set(v) for k, v in edges.items() if v}


# Bộ biểu thức bao đủ các cạnh dễ vỡ: HTML entity (&gt; &lt; &amp; &nbsp; &quot;),
# string literal, .attr, genexp đọc bảng, tên hàm trùng tên công thức.
_IDENTIFIER_CORPUS = [
    "qty * price",
    "K1 + K2",
    "a &gt; b",
    "a &lt;= b &amp;&amp; c",
    "&nbsp; total &nbsp;",
    "if(x &gt; 0, 'NC', \"NC\")",
    "r.get('amount', 0)",
    "sum(r.get('amount',0) for r in items)",
    "len(items) + count_unique(items)",
    "snap.total + snap.qty",
    "obj.to_dict()",
    "gt + lt + amp + quot + nbsp",
    "subtotal * rate + TAX_T1",
    "x if y else z",
    "min(a, b) + max(c, d)",
]

_EDGE_CASES = {
    "entity_khong_sinh_canh_ma": {
        "gt": "a + b",
        "a": "1",
        "b": "2",
        "c": "a &gt; b",          # ⛔ KHÔNG được sinh cạnh c → gt
    },
    "string_literal_va_attr": {
        "NC": "1",
        "total": "2",
        "snap": "3",
        "kq": "if(1 &gt; 0, 'NC', snap.total)",   # phụ thuộc snap, ⛔ không NC/total
    },
    "genexp_doc_bang": {
        "K1": "1",
        "K2": "2",
        "items": "3",
        "subtotal": "sum(r.get('amount',0) for r in items) + K1 + K2",
    },
    "ten_ham_trung_ten_cong_thuc": {
        "sum": "1",
        "len_text": "2",
        "kq": "sum + len_text",
    },
}


class TestExtractIdentifiersRefactor(unittest.TestCase):
    """Ca 8 — `extract_identifiers()` sau refactor ⛔ không đổi hành vi dò định danh."""

    def test_8_extract_identifiers_va_build_from_exprs_khong_doi_hanh_vi(self):
        # (a) `extract_identifiers()` phải cho ĐÚNG tập định danh như bản cũ.
        for expr in _IDENTIFIER_CORPUS:
            assert extract_identifiers(expr) == _ref_extract_identifiers(expr), (
                f"lệch định danh ở biểu thức: {expr!r}"
            )

        # (b) `build_from_exprs()` phải cho ĐÚNG tập cạnh như bản cũ — cả hai chiều
        #     (graph: cha → con, reverse_graph: con → cha).
        for label, exprs in _EDGE_CASES.items():
            graph = DependencyGraph()
            graph.build_from_exprs(exprs)

            ref_fwd, ref_rev = _ref_edges(exprs)
            assert _real_edges(graph.graph) == _real_edges(ref_fwd), f"lệch cạnh xuôi ở {label}"
            assert _real_edges(graph.reverse_graph) == _real_edges(ref_rev), f"lệch cạnh ngược ở {label}"
            # Thứ tự tính cũng phải dựng được (⛔ không vỡ vì refactor).
            assert set(graph.topological_sort()) == set(exprs)

        # (c) Chốt riêng ca "entity không sinh cạnh ma" — lỗi im lặng đắt nhất:
        #     `c = a &gt; b` chỉ được phụ thuộc a và b, ⛔ KHÔNG phụ thuộc công thức
        #     tên "gt" (ma) dù bộ công thức có sẵn tên đó.
        graph = DependencyGraph()
        graph.build_from_exprs(_EDGE_CASES["entity_khong_sinh_canh_ma"])
        assert graph.reverse_graph["c"] == {"a", "b"}
        assert "gt" not in graph.reverse_graph["c"]



if __name__ == "__main__":
    unittest.main()
