"""Test 4 lỗi đã vá ở tầng ``FlexibleFormulaEngine`` (A1–A4).

Mỗi lớp test ghi rõ: TRIỆU CHỨNG người dùng thấy, rồi mới tới cách kiểm.
Test nào cũng chạy được KHÔNG cần site Frappe (xem `tests/__init__.py`).

A1  create_incremental_context() dựng engine chỉ với 4/13 tham số ⇒ RƠI
    rounding_policy / default_value / max_operations / assertions / schema /
    strict. Ca đau nhất là làm tròn: cùng input mà calculate() làm tròn còn
    incremental thì không ⇒ UI hiện một số, lưu xuống số khác.

A2  Điều kiện `hasattr(engine,'last_errors') and engine.last_errors` đảo ngược
    ý đồ: chạy SẠCH ⇒ last_errors == {} (falsy) ⇒ rơi vào nhánh dự phòng, dựng
    FormulaEngine THỨ HAI và eval lại toàn bộ. Kèm theo, nhánh dự phòng suy lỗi
    từ `val is None` nên công thức HỢP LỆ trả None bị báo lỗi oan.

A3  `assertions` được hứa ở 3 nơi (EngineConfig, ChildTableConfig,
    CalculationResult.warnings) nhưng CHƯA BAO GIỜ chạy — cấu hình assertion
    xong không có tác dụng gì, im lặng.

A4  (a) create_incremental_context() gán lại `fields` BÊN TRONG vòng lặp dòng nên
    bộ cột tự dò của dòng 1 dùng luôn cho dòng sau;
    (b) EngineConfig cảnh báo oan mọi config ≥2 bảng vì chỉ so `prefix` (mặc định "");
    (c) get_dependency_graph() chọc vào thuộc tính riêng của lớp khác.
"""

import warnings

from unittest import mock

import formula_builder.flexible_formula_engine as ffe_module
from formula_builder.flexible_formula_engine import (
    ChildTableConfig,
    EngineConfig,
    FlexibleFormulaEngine,
)
from formula_builder.formula_utils import FormulaEngine

from frappe.tests.utils import FrappeTestCase


def _config_mot_bang(**kwargs):
    """Config tối giản: 1 child table + tham số truyền thêm."""
    cfg = {
        "child_tables": [
            ChildTableConfig(
                table_key="items",
                formula_field="formula",
                id_field="line_ref",
                output_field="amount",
            )
        ],
    }
    cfg.update(kwargs)
    return EngineConfig(**cfg)


# ============================================================================
# A1 — MỘT bộ tham số cho mọi đường vào engine
# ============================================================================

class TestA1ThamSoDongNhat(FrappeTestCase):
    """Triệu chứng: UI (reactive) hiện một số, lúc lưu lại ra số khác."""

    def test_rounding_policy_ap_dung_giong_nhau_o_ca_hai_duong(self):
        """calculate() và create_incremental_context() phải ra CÙNG con số.

        VÌ SAO dùng 3 * 1.4: kết quả 4.2 — chỉ khác nhau khi có làm tròn. Đây
        đúng là ca tiền, sai một đồng là sai thật.
        """
        eng = FlexibleFormulaEngine(EngineConfig(
            child_tables=[
                ChildTableConfig(
                    table_key="items", formula_field="formula", id_field="line_ref",
                    row_fields=["qty", "rate"], output_field="amount",
                )
            ],
            rounding_policy={"K1": {"decimals": 0}},
        ))
        inputs = {"items": [{"line_ref": "K1", "formula": "qty * rate", "qty": 3, "rate": 1.4}]}

        ket_qua = eng.calculate(inputs)
        ctx, _engine, _map = eng.create_incremental_context({
            "items": [{"line_ref": "K1", "formula": "qty * rate", "qty": 3, "rate": 1.4}]
        })

        self.assertEqual(ket_qua.values["K1"], 4)
        self.assertEqual(
            ctx.outputs["K1"], ket_qua.values["K1"],
            "incremental PHAI lam tron giong calculate (rounding_policy bi roi)",
        )

    def test_default_value_toi_duoc_incremental(self):
        """Khi công thức lỗi, cả 2 đường phải trả CÙNG giá trị mặc định."""
        eng = FlexibleFormulaEngine(EngineConfig(
            child_tables=[
                ChildTableConfig(
                    table_key="items", formula_field="formula", id_field="line_ref",
                    row_fields=["qty"], output_field="amount",
                )
            ],
            global_formulas=[{"name": "kq", "formula": "khong_ton_tai + 1"}],
            on_error="default",
            default_value=-1,
        ))
        inputs = {"items": [{"line_ref": "K1", "formula": "qty", "qty": 7}]}

        ket_qua = eng.calculate({"items": [{"line_ref": "K1", "formula": "qty", "qty": 7}]})
        ctx, _engine, _map = eng.create_incremental_context(inputs)

        self.assertEqual(ket_qua.values["kq"], -1)
        self.assertEqual(ctx.outputs["kq"], -1, "default_value bi roi o incremental")

    def test_max_operations_va_deterministic_di_cung(self):
        """Trần thao tác phải có hiệu lực ở CẢ hai đường — nếu không, UI là cửa hậu.

        UI gọi create_incremental_context() liên tục theo từng lần gõ phím: đây
        mới là chỗ dễ bị treo nhất, mà lại là chỗ duy nhất trước đây không có trần.
        """
        eng = FlexibleFormulaEngine(EngineConfig(
            child_tables=[
                ChildTableConfig(
                    table_key="items", formula_field="formula", id_field="line_ref",
                    row_fields=["qty"], output_field="amount",
                )
            ],
            # 2 công thức (K1, K2) mà trần chỉ cho 1 phép ⇒ phải nổ ở công thức thứ 2
            max_operations=1,
        ))
        inputs = {"items": [
            {"line_ref": "K1", "formula": "qty * 2", "qty": 3},
            {"line_ref": "K2", "formula": "qty * 4", "qty": 5},
        ]}

        from formula_builder.formula_utils import FormulaBudgetExceeded

        with self.assertRaises(FormulaBudgetExceeded):
            eng.create_incremental_context(inputs)


# ============================================================================
# A2 — Không dựng engine thứ hai, không báo lỗi oan
# ============================================================================

class TestA2GomLoi(FrappeTestCase):
    """Triệu chứng: mọi lần tính SẠCH đều chạy công thức 2 lần (chậm gấp đôi),
    và công thức hợp lệ trả None bị gắn mác "lỗi"."""

    def _inputs_2_dong(self):
        return {
            "items": [
                {"line_ref": "K1", "formula": "qty * rate", "qty": 2, "rate": 3},
                {"line_ref": "K2", "formula": "qty * rate", "qty": 4, "rate": 5},
            ]
        }

    def test_chay_sach_chi_dung_mot_engine(self):
        """ĐẾM số lần khởi tạo FormulaEngine — chạy sạch thì phải đúng 1."""
        eng = FlexibleFormulaEngine(EngineConfig(
            child_tables=[
                ChildTableConfig(
                    table_key="items", formula_field="formula", id_field="line_ref",
                    row_fields=["qty", "rate"], output_field="amount",
                )
            ],
            global_formulas=[{"name": "tong", "formula": "K1 + K2"}],
        ))

        that_su = ffe_module.FormulaEngine
        so_lan = []

        class _Dem:
            def __init__(self, *args, **kwargs):
                so_lan.append(kwargs)
                self._inner = that_su(*args, **kwargs)

            def __getattr__(self, ten):
                return getattr(self._inner, ten)

        with mock.patch.object(ffe_module, "FormulaEngine", _Dem):
            ket_qua = eng.calculate(self._inputs_2_dong())

        self.assertEqual(ket_qua.values["tong"], 26)
        self.assertEqual(ket_qua.errors, {})
        self.assertEqual(
            len(so_lan), 1,
            f"chay sach ma dung {len(so_lan)} engine — nhanh du phong van con chay",
        )

    def test_gia_tri_none_hop_le_khong_bi_bao_loi(self):
        """Công thức trả None là HỢP LỆ (ô trống, .get() thiếu khoá) — ⛔ không phải lỗi.

        Trước bản vá, nhánh dự phòng suy lỗi từ `val is None` nên mọi ô trống đều
        hiện cảnh báo lỗi trên UI — người dùng học cách bỏ qua cảnh báo, và tới
        lúc có lỗi THẬT thì không ai còn đọc.
        """
        eng = FlexibleFormulaEngine(EngineConfig(
            child_tables=[
                ChildTableConfig(
                    table_key="items", formula_field="formula", id_field="line_ref",
                    row_fields=["qty"], output_field="amount",
                )
            ],
            global_formulas=[{"name": "ghichu", "formula": "note"}],
            on_error="null",
        ))
        ket_qua = eng.calculate({
            "note": None,
            "items": [{"line_ref": "K1", "formula": "qty", "qty": 7}],
        })

        self.assertIsNone(ket_qua.values["ghichu"])
        self.assertEqual(
            ket_qua.errors, {},
            "ô trống bị báo thành lỗi (None bi coi la loi)",
        )

    def test_loi_that_van_phai_bao(self):
        """ĐỐI CHỨNG ÂM: sửa A2 ⛔ không được làm câm lỗi thật."""
        eng = FlexibleFormulaEngine(EngineConfig(
            child_tables=[
                ChildTableConfig(
                    table_key="items", formula_field="formula", id_field="line_ref",
                    row_fields=["qty"], output_field="amount",
                )
            ],
            global_formulas=[{"name": "hong", "formula": "khong_ton_tai + 1"}],
            on_error="null",
        ))
        ket_qua = eng.calculate({"items": [{"line_ref": "K1", "formula": "qty", "qty": 7}]})

        self.assertIn("hong", ket_qua.errors)
        self.assertIn("khong_ton_tai", ket_qua.errors["hong"])


# ============================================================================
# A3 — Assertion: chạy thật, phân loại đúng, ⛔ không đổi giá trị
# ============================================================================

class TestA3Assertion(FrappeTestCase):
    """Triệu chứng trước bản vá: khai assertions xong KHÔNG có gì xảy ra."""

    def _engine(self, **kwargs):
        tham_so = {
            "formulas": [{"name": "K1", "formula": "a + b"}],
        }
        tham_so.update(kwargs)
        return FormulaEngine(**tham_so)

    def test_warning_vao_last_warnings_khong_vao_last_errors(self):
        eng = self._engine(assertions=[{
            "name": "K1_phai_lon", "expr": "K1 > 100",
            "message": "K1 phải lớn hơn 100", "severity": "WARNING",
        }])
        ket_qua = eng.calculate({"a": 2, "b": 3})

        self.assertEqual(ket_qua["K1"], 5)
        canh_bao = eng.last_warnings
        self.assertEqual(len(canh_bao), 1, "assertion WARNING khong duoc chay")
        self.assertEqual(canh_bao[0].assertion_name, "K1_phai_lon")
        self.assertEqual(eng.last_errors, {}, "WARNING khong duoc vao bang loi")

    def test_error_vao_last_errors_khong_raise_khi_on_error_default(self):
        eng = self._engine(
            on_error="default",
            assertions=[{
                "name": "K1_khac_0", "expr": "K1 <> 5",
                "message": "K1 phải khác 5", "severity": "ERROR",
            }],
        )
        ket_qua = eng.calculate({"a": 2, "b": 3})

        self.assertEqual(eng.last_errors.get("K1_khac_0"), "K1 phải khác 5")
        self.assertEqual(ket_qua["K1"], 5, "assertion ⛔ KHONG duoc doi gia tri")

    def test_error_raise_khi_on_error_raise(self):
        eng = self._engine(
            on_error="raise",
            assertions=[{
                "name": "K1_phai_duong", "expr": "K1 > 0",
                "message": "K1 phải dương", "severity": "ERROR",
            }],
        )
        from formula_builder.formula_utils import FormulaAssertionError

        with self.assertRaises(FormulaAssertionError):
            eng.calculate({"a": -2, "b": 1})   # K1 = -1 → assertion 'K1 > 0' sai

    def test_assertion_dat_thi_khong_bao_gi(self):
        eng = self._engine(assertions=[{
            "name": "K1_duong", "expr": "K1 > 0",
            "message": "K1 phải dương", "severity": "ERROR",
        }])
        eng.calculate({"a": 2, "b": 3})

        self.assertEqual(eng.last_errors, {})
        self.assertEqual(eng.last_warnings, [])

    def test_assertion_bien_chua_co_thi_bo_qua(self):
        """Assertion nhắc biến không tồn tại KHÔNG phải assertion thất bại.

        VÌ SAO: thường gặp khi công thức phía trước đã lỗi nên không sinh giá trị.
        Báo đỏ lúc đó là báo oan, che mất lỗi thật.
        """
        eng = self._engine(assertions=[{
            "name": "K9_duong", "expr": "K9 > 0",
            "message": "K9 phải dương", "severity": "ERROR",
        }])
        eng.calculate({"a": 2, "b": 3})

        self.assertEqual(eng.last_errors, {})
        self.assertEqual(eng.last_warnings, [])

    def test_assertion_di_qua_normalize_cua_loi(self):
        """'=' đơn lẻ phải được hiểu là SO SÁNH (normalize của lõi).

        Đây là một trong 3 chốt mà đường parse cũ của add_assertion bỏ sót.
        """
        eng = self._engine(assertions=[{
            "name": "K1_bang_4", "expr": "K1 = 4",
            "message": "K1 phải bằng 4", "severity": "WARNING",
        }])
        eng.calculate({"a": 2, "b": 3})

        self.assertEqual(len(eng.last_warnings), 1)

    def test_assertion_di_qua_go_entity(self):
        """Assertion cũng là chuỗi đi qua HTML ⇒ phải gỡ entity như công thức."""
        eng = self._engine(assertions=[{
            "name": "K1_khac_5", "expr": "K1 &lt;&gt; 5",
            "message": "K1 phải khác 5", "severity": "WARNING",
        }])
        eng.calculate({"a": 2, "b": 3})

        self.assertEqual(len(eng.last_warnings), 1)

    def test_assertion_nguy_hiem_bi_chan(self):
        """Assertion là đầu vào cấu hình ⇒ phải qua ĐÚNG chốt an toàn của lõi."""
        from formula_builder.formula_utils import FormulaError

        with self.assertRaises(FormulaError):
            self._engine(assertions=[{
                "name": "doc_tep", "expr": "__import__('os').system('id')",
                "message": "x", "severity": "WARNING",
            }])

    def test_khong_co_assertion_thi_khong_ton_chi_phi(self):
        eng = self._engine()
        eng.calculate({"a": 2, "b": 3})

        self.assertEqual(eng.last_errors, {})
        self.assertEqual(eng.last_warnings, [])


class TestA3AssertionQuaFlexible(FrappeTestCase):
    """Tầng Flexible: `CalculationResult.warnings` trước đây LUÔN rỗng."""

    def _engine(self, assertions, **kwargs):
        return FlexibleFormulaEngine(EngineConfig(
            child_tables=[
                ChildTableConfig(
                    table_key="items", formula_field="formula", id_field="line_ref",
                    row_fields=["qty"], output_field="amount",
                )
            ],
            assertions=assertions,
            **kwargs,
        ))

    def test_warning_cua_global_assertion_len_toi_ket_qua(self):
        eng = self._engine([{
            "name": "K1_phai_lon", "expr": "K1 > 100",
            "message": "K1 phải lớn hơn 100", "severity": "WARNING",
        }])
        ket_qua = eng.calculate({"items": [{"line_ref": "K1", "formula": "qty", "qty": 7}]})

        self.assertEqual(len(ket_qua.warnings), 1, "CalculationResult.warnings luon rong")
        self.assertIn("K1 phải lớn hơn 100", ket_qua.warnings[0])

    def test_assertion_cua_child_table_cung_chay(self):
        """`ChildTableConfig.assertions` là lời hứa thứ hai — cũng phải chạy."""
        eng = FlexibleFormulaEngine(EngineConfig(
            child_tables=[
                ChildTableConfig(
                    table_key="items", formula_field="formula", id_field="line_ref",
                    row_fields=["qty"], output_field="amount",
                    assertions=[{
                        "name": "K1_phai_lon", "expr": "K1 > 100",
                        "message": "K1 phải lớn hơn 100", "severity": "WARNING",
                    }],
                )
            ],
        ))
        ket_qua = eng.calculate({"items": [{"line_ref": "K1", "formula": "qty", "qty": 7}]})

        self.assertEqual(len(ket_qua.warnings), 1)

    def test_assertion_dat_thi_warnings_rong(self):
        eng = self._engine([{
            "name": "K1_duong", "expr": "K1 > 0",
            "message": "K1 phải dương", "severity": "WARNING",
        }])
        ket_qua = eng.calculate({"items": [{"line_ref": "K1", "formula": "qty", "qty": 7}]})

        self.assertEqual(ket_qua.warnings, [])
        self.assertEqual(ket_qua.errors, {})


# ============================================================================
# A4 — Cột tự dò, cảnh báo oan, accessor công khai
# ============================================================================

class TestA4A_(FrappeTestCase):
    """A4a — bộ cột tự dò phải hợp nhất MỌI dòng, ⛔ không lấy dòng đầu rồi dùng mãi."""

    def _engine(self):
        return FlexibleFormulaEngine(EngineConfig(
            child_tables=[
                ChildTableConfig(
                    table_key="items", formula_field="formula", id_field="line_ref",
                    output_field="amount",
                )
            ],
            global_formulas=[{"name": "tong", "formula": "K1 + K2"}],
        ))

    def _inputs(self):
        return {
            # `vat` là biến cấp tài liệu — cố tình đặt giá trị khác hẳn để lộ rò rỉ
            "vat": 100,
            "items": [
                {"line_ref": "K1", "formula": "qty * rate", "qty": 2, "rate": 3},
                {"line_ref": "K2", "formula": "qty * vat", "qty": 4, "vat": 5},
            ],
        }

    def test_cot_chi_co_o_dong_sau_van_duoc_doi_ten(self):
        """Dòng 2 có cột `vat` mà dòng 1 không có ⇒ vẫn phải thành `vat_K2`.

        Trước bản vá: `vat` giữ tên trần nên bám vào biến cấp tài liệu `vat`=100
        ⇒ K2 = 4 * 100 = 400 thay vì 4 * 5 = 20. Sai số im lặng, chỉ lộ ở tiền.
        """
        ctx, _engine, _map = self._engine().create_incremental_context(self._inputs())

        self.assertEqual(ctx.outputs["K2"], 20, "cot 'vat' cua dong 2 bi roi ten")
        self.assertEqual(ctx.outputs["K1"], 6)

    def test_calculate_va_incremental_khop_nhau(self):
        eng = self._engine()
        ket_qua = eng.calculate(self._inputs())
        ctx, _e, _m = eng.create_incremental_context(self._inputs())

        self.assertEqual(ket_qua.values["K2"], 20)
        self.assertEqual(ctx.outputs["K2"], ket_qua.values["K2"])
        self.assertEqual(ctx.outputs["tong"], ket_qua.values["tong"])

    def test_truong_he_thong_frappe_khong_bi_doi_ten(self):
        """`name`/`owner`/`idx`... là trường hệ thống ⇒ ⛔ không thành `name_K1`.

        Không lọc thì chúng thành biến rác trong context và có thể che biến thật.
        """
        inputs = {
            "items": [{
                "line_ref": "K1", "formula": "qty + 1", "qty": 7,
                "name": "ROW-0001", "owner": "Administrator", "idx": 1,
            }],
        }
        ctx, _engine, _map = self._engine().create_incremental_context(inputs)

        self.assertEqual(ctx.outputs["K1"], 8)
        for ten_rac in ("name_K1", "owner_K1", "idx_K1"):
            self.assertNotIn(ten_rac, ctx.inputs)


class TestA4B_CanhBaoOan(FrappeTestCase):
    """A4b — cảnh báo lúc khởi tạo config phải phân biệt được TRÙNG THẬT."""

    def test_hai_bang_prefix_rong_nhung_id_field_khac_thi_khong_canh_bao(self):
        """`prefix` mặc định là "" nên MỌI config ≥2 bảng từng bị kêu oan.

        Cảnh báo báo oan thì người ta học cách bỏ qua — tới lúc có cảnh báo thật
        cũng không ai đọc.
        """
        with warnings.catch_warnings(record=True) as bat_duoc:
            warnings.simplefilter("always")
            EngineConfig(child_tables=[
                ChildTableConfig(
                    table_key="items", formula_field="formula", id_field="line_ref"),
                ChildTableConfig(
                    table_key="taxes", formula_field="formula", id_field="tax_code"),
            ])

        self.assertEqual(
            len(bat_duoc), 0,
            f"canh bao oan: {[str(w.message) for w in bat_duoc]}",
        )

    def test_trung_ca_prefix_lan_id_field_thi_van_canh_bao(self):
        """ĐỐI CHỨNG ÂM: sửa xong ⛔ không được làm câm cảnh báo THẬT."""
        with warnings.catch_warnings(record=True) as bat_duoc:
            warnings.simplefilter("always")
            EngineConfig(child_tables=[
                ChildTableConfig(
                    table_key="items", formula_field="formula", id_field="line_ref"),
                ChildTableConfig(
                    table_key="taxes", formula_field="formula", id_field="line_ref"),
            ])

        self.assertEqual(len(bat_duoc), 1)
        self.assertIn("id_field", str(bat_duoc[0].message))


class TestA4C_AccessorCongKhai(FrappeTestCase):
    """A4c — ⛔ không chọc vào thuộc tính riêng (`_deps_cache`, `_topo_order`)."""

    def test_loi_co_accessor_cong_khai(self):
        eng = FormulaEngine(formulas=[
            {"name": "a", "formula": "1 + 1"},
            {"name": "b", "formula": "a * 2"},
        ])
        eng.calculate({})

        self.assertEqual(eng.topo_order, ["a", "b"])
        self.assertEqual(eng.deps_of("b"), {"a"})
        self.assertEqual(eng.deps_of("a"), set())
        self.assertEqual(eng.dependency_edges(), {"a": [], "b": ["a"]})

    def test_do_thi_tra_ve_on_dinh(self):
        """Danh sách phụ thuộc phải SẮP XẾP — cùng tài liệu, cùng kết quả.

        `list(set)` cho thứ tự phụ thuộc vào hash ⇒ UI đổi thứ tự mỗi lần tải.
        """
        eng = FlexibleFormulaEngine(EngineConfig(
            child_tables=[
                ChildTableConfig(
                    table_key="items", formula_field="formula", id_field="line_ref",
                    row_fields=["qty"], output_field="amount",
                )
            ],
            global_formulas=[{"name": "tong", "formula": "K1 + K2 + K3"}],
        ))
        inputs = {"items": [
            {"line_ref": "K1", "formula": "qty", "qty": 1},
            {"line_ref": "K2", "formula": "K1 + qty", "qty": 2},
            {"line_ref": "K3", "formula": "K2 + qty", "qty": 3},
        ]}

        lan_1 = eng.get_dependency_graph(inputs)
        lan_2 = eng.get_dependency_graph(inputs)

        self.assertEqual(lan_1, lan_2)
        self.assertEqual(lan_1["K2"], ["K1"])
        self.assertEqual(lan_1["K3"], ["K2"])
        for ten, ds in lan_1.items():
            self.assertEqual(ds, sorted(ds), f"{ten}: danh sach chua sap xep")
