"""Test HTML entity trong công thức — Phần B: gỡ ở CỬA VÀO, escape ở CỬA RA.

VÌ SAO cần lớp này:
  1. Công thức đi qua form HTML / JSON của Monaco rồi mới tới engine, nên `>`
     có thể tới dưới dạng `&gt;`, `&` dưới dạng `&amp;`, `"` dưới dạng `&quot;`.
     Đưa nguyên chuỗi entity vào engine ⇒ công thức ĐÚNG bị báo "Syntax error".
  2. NGUY HIỂM HƠN (lỗi im lặng): `&gt;` chứa định danh `gt`, `&lt;`→`lt`,
     `&amp;`→`amp`, `&quot;`→`quot`. Nếu tài liệu có công thức/biến TRÙNG tên đó
     thì DependencyGraph dựng CẠNH PHỤ THUỘC MA ⇒ đổi thứ tự tính ⇒ sai số mà
     không có lỗi nào nổi lên.
  3. `&nbsp;` giải ra U+00A0 — eval() ném "invalid non-printable character".

Hướng xử lý đã chọn: giá trị LƯU giữ RAW, gỡ entity ngay khi nạp, chỉ escape
khi chuỗi đi RA giao diện. Nhờ gỡ ở cửa vào nên escape ở cửa ra là an toàn
vòng tròn (escape → lưu → đọc lại → ra đúng bản người dùng nhập).
"""

import html
import unittest

from frappe.tests.utils import FrappeTestCase

from formula_builder.formula_utils import FormulaEngine
from formula_builder.formula_utils.topo import DependencyGraph

try:
    from formula_builder.formula_utils import (
        html_unescape_formula,
        html_escape_formula,
    )
except ImportError:
    # Bản CHƯA VÁ không có 2 helper này. Đặt stub báo lỗi để tệp test vẫn import
    # được — từng test tự ĐỎ với thông báo rõ ràng, thay vì cả module lỗi import
    # (khi đó ta không biết test nào thực sự bắt được lỗi).
    def html_unescape_formula(expr):
        raise AssertionError("html_unescape_formula chưa tồn tại — bản chưa vá")

    def html_escape_formula(expr):
        raise AssertionError("html_escape_formula chưa tồn tại — bản chưa vá")


# ============================================================================
# §1  Hàm gỡ / escape — đơn vị nhỏ nhất
# ============================================================================

class TestHamGoEntity(FrappeTestCase):
    """``html_unescape_formula`` / ``html_escape_formula``."""

    def test_go_entity_so_sanh(self):
        for raw, mong_doi in [
            ("a &gt; b", "a > b"),
            ("a &lt; b", "a < b"),
            ("a &gt;= b", "a >= b"),
            ("a &lt;= b", "a <= b"),
            ("a &amp;&amp; b", "a && b"),
            ("a &amp; b", "a & b"),
            ("a &lt;&gt; b", "a <> b"),
            ('&quot;q&quot;', '"q"'),
            ("a &#62; b", "a > b"),          # entity dạng số
            ("a &#x3e; b", "a > b"),         # entity dạng hex
        ]:
            self.assertEqual(html_unescape_formula(raw), mong_doi, f"raw={raw!r}")

    def test_amp_tran_khong_lam_do(self):
        """'&' trần không phải entity — phải GIỮ NGUYÊN, ⛔ không để lỗi nổi lên.

        Đây là ca THẬT: người dùng gõ tên có '&' (AT&T, R&D) hoặc dùng toán tử
        bitwise '&'. Công thức hợp lệ ⛔ không được báo hỏng.

        ⚠️✅[V] Docstring này từng viết "'&' trần làm `html.unescape` ném
        ValueError" — SAI, đã đo lại 2026-10-12 (CPython 3.10.12→3.14): "AT&T",
        "a&b", "&&", "&#", "&zzz;", "&gt" … đều **trả về bình thường, ⛔ không ca
        nào ném**; đọc mã nguồn 5 nhánh cũng chỉ thấy ``return '&' + s``. Nhánh
        `except` của hàm chỉ tới được bằng charref SỐ khổng lồ — xem
        `TestCharrefSoQuaDai`. Giữ ca này vì HÀNH VI nó chốt (giữ nguyên) vẫn
        đúng và vẫn đáng chốt — chỉ lý do viết kèm là sai.
        """
        for raw in ("AT&T", "a&b", "x & y", 'a & "b"', "R&D * 2"):
            self.assertEqual(html_unescape_formula(raw), raw, f"raw={raw!r}")

    def test_ky_tu_la_khong_pha_duoc_cong_thuc(self):
        # &nbsp; giải ra U+00A0 → eval() sẽ ném lỗi non-printable ⇒ phải về space
        self.assertEqual(html_unescape_formula("a + b"), "a + b")
        # nháy cong dán từ Word → nháy thẳng, nếu không literal sẽ hỏng
        self.assertEqual(html_unescape_formula("“qty” * 2"), '"qty" * 2')
        self.assertEqual(html_unescape_formula("‘x’ + 1"), "'x' + 1")
        # zero-width / BOM: vô hình nhưng phá token ⇒ xoá hẳn
        self.assertEqual(html_unescape_formula("a﻿b"), "ab")

    def test_cong_thuc_sach_tra_ve_y_nguyen_object(self):
        """Chốt nhanh: công thức sạch phải trả về CHÍNH object đó.

        VÌ SAO khẳng định bằng `assertIs` chứ không `assertEqual`: đây là hot
        path (engine parse mọi công thức) — chốt nhanh phải thoát trước mọi phép
        biến đổi. So bằng giá trị sẽ không phát hiện được nếu sau này ai thêm một
        bước biến đổi luôn chạy.
        """
        for raw in ("qty * rate", "a > b", "sum(items)", "", "   "):
            self.assertIs(html_unescape_formula(raw), raw, f"raw={raw!r}")

    def test_chi_go_mot_luot(self):
        """⛔ KHÔNG lặp tới khi hết entity.

        Người dùng cố ý viết literal '&gt;' trong chuỗi thì phải giữ đúng một
        lượt gỡ. Lặp sẽ âm thầm phá chính ca mà ta đang bảo vệ.
        """
        self.assertEqual(html_unescape_formula("&amp;gt;"), "&gt;")
        self.assertEqual(html_unescape_formula("&amp;amp;"), "&amp;")

    def test_escape_chieu_ra(self):
        self.assertEqual(html_escape_formula("a > b"), html.escape("a > b", quote=True))
        self.assertEqual(html_escape_formula('"x"'), "&quot;x&quot;")
        self.assertEqual(html_escape_formula("a & b"), "a &amp; b")
        # chuỗi rỗng / không phải str giữ nguyên
        self.assertEqual(html_escape_formula(""), "")


# ============================================================================
# §1b  Charref SỐ hỏng — ⛔ không được tắt việc gỡ entity của CẢ công thức
# ============================================================================

class TestCharrefSoQuaDai(unittest.TestCase):
    """Charref SỐ quá dài làm `html.unescape` ném ValueError.

    Kế thừa `unittest.TestCase` (⛔ không phải `FrappeTestCase`) vì các ca dưới
    đây chỉ chạm HÀM THUẦN — ⛔ không cần site, ⛔ không cần DB. Dùng
    `FrappeTestCase` sẽ kéo thêm một `setUpClass` phải có site, tức là thêm một
    lý do ĐỎ không liên quan gì tới thứ đang kiểm. Cùng tiền lệ với
    `test_security.py` (trộn 2 lớp cha trong một tệp).

    VÌ SAO có lớp này (lỗi thật, tìm ra ở lượt kiểm cuối 2026-10-12): nhánh
    `except ValueError` bản cũ nuốt lỗi rồi giữ nguyên CẢ chuỗi. Nghĩa là MỘT
    charref hỏng nằm ở bất kỳ đâu ⇒ "&gt;" cùng công thức ⛔ không được gỡ ⇒
    công thức chạy SAI IM LẶNG — đúng loại lỗi mà cả lớp này sinh ra để chặn.

    ⚠️ Các ca dưới đây CHỈ XANH SAU KHI VÁ. ⛔ Khác các đối chứng âm ở §1 — những
    ca đó cố ý xanh cả trước lẫn sau để chứng minh bản vá ⛔ không đụng vào đường
    thường; ở đây thì ngược lại, đỏ-trước/xanh-sau mới là điều cần chứng minh.
    """

    # > ngưỡng `sys.set_int_max_str_digits` (mặc định 4300 chữ số)
    _DAI = "&#" + "9" * 5000 + ";"
    # ⛔ không hỏng vì giá trị: vẫn là 'A', chỉ phình ra bằng số 0 vô nghĩa
    _DEM_SO_0 = "&#" + "0" * 5000 + "65;"

    def test_charref_dai_khong_tat_viec_go_entity_ca_cong_thuc(self):
        """Điểm mấu chốt: "&gt;" trong CÙNG chuỗi vẫn phải được gỡ."""
        ket_qua = html_unescape_formula("a &gt; b " + self._DAI)
        self.assertTrue(ket_qua.startswith("a > b "), repr(ket_qua[:40]))
        # charref hỏng → ký tự thay thế, ⛔ không phải chuỗi literal còn nguyên
        self.assertIn("�", ket_qua)

    def test_charref_nhieu_so_0_van_ra_dung_ky_tu(self):
        """Số 0 vô nghĩa ⛔ không được biến 'A' thành ký tự thay thế.

        `&#0000…065;` và `&#65;` là CÙNG một điểm mã — bỏ số 0 là phép biến đổi
        ⛔ không đổi giá trị, nên phải ra 'A' chứ ⛔ không phải U+FFFD.
        """
        self.assertEqual(
            html_unescape_formula("a &gt; b " + self._DEM_SO_0), "a > b A"
        )

    def test_duong_thuong_khong_doi_hanh_vi(self):
        """Đối chứng âm: ca ⛔ KHÔNG ném thì kết quả phải Y HỆT `html.unescape`.

        Bộ ca này cố ý ⛔ không chứa ký tự lạ (nháy cong, zero-width…) để phép so
        với `html.unescape` gốc là hợp lệ — hàm còn chuẩn hoá thêm lớp đó.
        """
        for raw in (
            "a &gt; b", "&lt;&amp;&quot;", "AT&T", "a&b", "&amp;gt;",
            "&#62;", "&#x3e;", "a + b", "",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(html_unescape_formula(raw), html.unescape(raw))

    def test_khong_dau_vao_nao_lam_ham_nem(self):
        """⛔ Không đầu vào nào được để lỗi thoát ra ngoài (công thức là dữ liệu
        người dùng — lỗi ở đây thành "công thức hỏng" khó hiểu)."""
        for raw in (
            "a &gt; b " + self._DAI, self._DAI, self._DEM_SO_0,
            "&#" + "9" * 4301 + ";",   # ngay SÁT ngưỡng
            "&" * 100, "&#;", "&#x;", "�", "&#" + "0" * 9000 + ";",
        ):
            with self.subTest(raw=raw[:28]):
                html_unescape_formula(raw)          # ⛔ không được ném

    def test_doi_chung_duong_cu_that_su_hong(self):
        """Đối chứng DƯƠNG: dựng lại nhánh `except` CŨ và chứng minh nó HỎNG.

        ⛔ Không gọi code sản phẩm — sao chép nguyên văn cách cũ (nuốt lỗi, giữ
        nguyên cả chuỗi) để phép so ⛔ không thành tự-so-với-chính-mình. Nếu ai
        đó gỡ bản vá ra, ca này vẫn chỉ đúng chỗ: đường cũ hỏng thật.
        """
        def _duong_cu(expr):
            try:
                return html.unescape(expr)
            except ValueError:
                return expr                     # ← nguyên văn hành vi CŨ

        raw = "a &gt; b " + self._DAI
        self.assertTrue(
            _duong_cu(raw).startswith("a &gt; b "),
            "đường cũ phải để '&gt;' còn nguyên (đó là lỗi đang vá)",
        )
        self.assertNotEqual(html_unescape_formula(raw), _duong_cu(raw))


# ============================================================================
# §2  FormulaEngine — công thức có entity phải CHẠY ĐÚNG
# ============================================================================

class TestFormulaEngineVoiEntity(FrappeTestCase):
    """Trước bản vá: 'a &gt; b' báo Syntax error. Sau: chạy như 'a > b'."""

    def _tinh(self, cong_thuc, inputs):
        eng = FormulaEngine(formulas=[{"name": "kq", "formula": cong_thuc}])
        return eng.calculate(inputs)["kq"]

    def test_lon_hon(self):
        self.assertTrue(self._tinh("a &gt; b", {"a": 3, "b": 1}))
        self.assertFalse(self._tinh("a &gt; b", {"a": 1, "b": 3}))

    def test_lon_hon_bang(self):
        self.assertTrue(self._tinh("a &gt;= b", {"a": 3, "b": 3}))
        self.assertFalse(self._tinh("a &gt;= b", {"a": 2, "b": 3}))

    def test_nho_hon_va_nho_hon_bang(self):
        self.assertTrue(self._tinh("a &lt; b", {"a": 1, "b": 3}))
        self.assertFalse(self._tinh("a &lt; b", {"a": 3, "b": 1}))
        self.assertTrue(self._tinh("a &lt;= b", {"a": 3, "b": 3}))

    def test_so_sanh_trong_if(self):
        self.assertEqual(self._tinh("IF(a &gt; b, 1, 0)", {"a": 3, "b": 1}), 1)
        self.assertEqual(self._tinh("IF(a &lt; b, 1, 0)", {"a": 3, "b": 1}), 0)

    def test_so_sanh_voi_bieu_thuc_that(self):
        self.assertTrue(self._tinh("qty * rate &gt; 100", {"qty": 5, "rate": 30}))
        self.assertFalse(self._tinh("qty * rate &lt;= 100", {"qty": 5, "rate": 30}))

    def test_entity_trong_chuoi_literal(self):
        """Chuỗi trong nháy cũng được gỡ entity — MỘT lượt, như phần còn lại.

        Ghi nhận hành vi: '&gt;' trong nháy thành '>' thật. Đây là lựa chọn có
        chủ ý (một quy tắc duy nhất cho cả biểu thức) và ⛔ không lặp, nên người
        dùng vẫn viết được literal bằng cách viết '&amp;gt;'.
        """
        self.assertEqual(
            self._tinh('IF(a &gt; b, "&gt;", "&lt;")', {"a": 3, "b": 1}), ">"
        )

    def test_entity_dang_so_va_hex(self):
        self.assertTrue(self._tinh("a &#62; b", {"a": 3, "b": 1}))
        self.assertTrue(self._tinh("a &#x3e; b", {"a": 3, "b": 1}))


# ============================================================================
# §3  Cạnh phụ thuộc MA — lỗi im lặng nguy hiểm nhất
# ============================================================================

class TestKhongSinhCanhPhuThuocMa(FrappeTestCase):
    """``DependencyGraph`` dò định danh bằng regex trên CHÍNH chuỗi công thức.

    Chuỗi 'a &gt; b' chứa định danh 'gt'. Chỉ khi tài liệu có công thức TRÙNG
    tên đó thì cạnh ma mới thành hình — nên test phải dựng đúng tình huống ấy.
    """

    def test_khong_co_canh_ma_vao_cong_thuc_ten_gt(self):
        eng = FormulaEngine(formulas=[
            {"name": "gt", "formula": "1 + 2"},
            {"name": "x", "formula": "a &gt; b"},
        ])
        eng.calculate({"a": 3, "b": 1})
        self.assertEqual(
            eng.dependency_edges()["x"], [],
            "'x' KHONG duoc phu thuoc vao cong thuc ten 'gt'",
        )

    def test_khong_co_canh_ma_vao_cong_thuc_ten_lt(self):
        eng = FormulaEngine(formulas=[
            {"name": "lt", "formula": "7"},
            {"name": "y", "formula": "a &lt; b"},
        ])
        eng.calculate({"a": 1, "b": 3})
        self.assertEqual(eng.dependency_edges()["y"], [])

    def test_khong_co_canh_ma_voi_amp_va_quot(self):
        eng = FormulaEngine(formulas=[
            {"name": "amp", "formula": "1"},
            {"name": "quot", "formula": "2"},
            {"name": "z", "formula": '4 &amp; 5 if a &gt; b else 0'},
        ])
        eng.calculate({"a": 3, "b": 1})
        self.assertEqual(eng.dependency_edges()["z"], [])

    def test_canh_phu_thuoc_that_van_phai_con(self):
        """ĐỐI CHỨNG ÂM: gỡ entity ⛔ KHÔNG được làm mất cạnh phụ thuộc THẬT.

        Nếu bản vá gỡ nhầm cả bước dò định danh (hoặc gỡ quá tay), thứ tự tính
        sẽ sai ở chỗ khác — test này canh đúng chỗ đó.
        """
        eng = FormulaEngine(formulas=[
            {"name": "a", "formula": "1 + 1"},
            {"name": "b", "formula": "a &gt; 0"},
            {"name": "c", "formula": "b + 1"},
        ])
        eng.calculate({})
        edges = eng.dependency_edges()
        self.assertEqual(edges["b"], ["a"])
        self.assertEqual(edges["c"], ["b"])
        self.assertLess(eng.topo_order.index("a"), eng.topo_order.index("b"))

    def test_dependency_graph_truc_tiep(self):
        """Tầng thấp nhất: dựng graph bằng tay rồi kiểm cạnh."""
        g = DependencyGraph()
        g.build_from_exprs({"gt": "1 + 2", "x": "a &gt; b"})
        self.assertEqual(g.reverse_graph["x"], set())
        # nhưng công thức có entity KHÔNG được coi là phụ thuộc chính mình
        self.assertIn("x", g.nodes)
        self.assertIn("gt", g.nodes)


# ============================================================================
# §4  Escape ở cửa RA — chỉ hiển thị, ⛔ không hai lần
# ============================================================================

def _esc_nhu_js(s: str) -> str:
    """Mô phỏng ĐÚNG hàm `_esc()` của `formula_builder.js` (đường hiển thị thật).

    VÌ SAO phải mô phỏng: test ở Python chỉ chứng minh được nửa đầu của hợp
    đồng "escape đúng MỘT lần". Nửa sau nằm ở phía JS. Mô phỏng lại đúng chuỗi
    thay thế của `_esc()` cho phép khẳng định cả đầu-cuối: engine trả RAW →
    JS escape một lần → người dùng đọc đúng `a > b`.
    """
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


class TestEscapeKhiHienThi(FrappeTestCase):
    """`explain()` trả `step.formula` — chuỗi này đi thẳng ra UI.

    Hợp đồng của cả lớp: **escape ĐÚNG MỘT LẦN, ở lớp NGOÀI CÙNG của đường
    hiển thị**. Đường hiển thị của app này là `formula_builder.js` — nó ĐÃ
    escape bằng `_esc()` trước khi đổ vào innerHTML. Nên tầng Python phải trả
    RAW; escape ở đây nữa là escape hai lần, người dùng đọc thấy `a &gt; b`.
    """

    def _engine(self):
        return FormulaEngine(formulas=[{"name": "kq", "formula": "a > b"}])

    def test_explain_mac_dinh_tra_ban_raw(self):
        """Mặc định PHẢI là RAW — ⛔ không phải sót, mà là chủ ý (xem docstring)."""
        exp = self._engine().explain("kq", {"a": 3, "b": 1})
        buoc = exp.steps[-1]
        self.assertEqual(buoc.formula, "a > b")
        self.assertEqual(buoc.value, True)

    def test_explain_bat_escape_thi_moi_escape(self):
        """Nơi render thẳng HTML mà ⛔ không tự escape thì bật cờ này."""
        exp = self._engine().explain("kq", {"a": 3, "b": 1}, escape_html=True)
        self.assertEqual(exp.steps[-1].formula, "a &gt; b")

    def test_explain_all_mac_dinh_tra_ban_raw(self):
        tat_ca = self._engine().explain_all({"a": 3, "b": 1})
        self.assertEqual(tat_ca["kq"].steps[-1].formula, "a > b")

    def test_explain_all_bat_escape(self):
        tat_ca = self._engine().explain_all({"a": 3, "b": 1}, escape_html=True)
        self.assertEqual(tat_ca["kq"].steps[-1].formula, "a &gt; b")

    def test_to_dict_qua_duong_js_chi_escape_mot_lan(self):
        """Đầu-cuối: engine RAW → `_esc()` của JS → người dùng đọc `a > b`.

        ⛔ Đây là test bắt đúng lỗi escape-hai-lần: nếu ai đó đổi mặc định của
        `explain()` thành escape, `_esc()` sẽ biến `&gt;` thành `&amp;gt;` và
        assertEqual dưới đây đổ ngay.
        """
        d = self._engine().explain("kq", {"a": 3, "b": 1}).to_dict()
        hien_thi = _esc_nhu_js(d["steps"][-1]["formula"])
        # Chuỗi người dùng nhìn thấy trên màn hình (đã render):
        self.assertIn("&gt;", hien_thi)
        self.assertNotIn("&amp;gt;", hien_thi)
        self.assertNotIn("&amp;amp;", hien_thi)

    def test_cong_thuc_luu_da_go_entity_nen_explain_khong_con_entity(self):
        """Công thức nhập từ HTML (`&gt;`) đã gỡ ở cửa vào ⇒ explain trả `>`."""
        eng = FormulaEngine(formulas=[{"name": "kq", "formula": "a &gt; b"}])
        exp = eng.explain("kq", {"a": 3, "b": 1})
        self.assertEqual(exp.steps[-1].formula, "a > b")
        self.assertEqual(exp.steps[-1].value, True)

    def test_gia_tri_khong_bi_escape(self):
        """⛔ Chỉ chuỗi CÔNG THỨC được escape — giá trị đã tính phải giữ nguyên.

        Escape lên giá trị là lỗi nặng hơn cả việc không escape: số và boolean
        sẽ hỏng ngay ở tầng dưới.

        VÌ SAO gọi KHÔNG kèm `escape_html`: đây là ĐỐI CHỨNG ÂM — cố ý viết sao
        cho nó xanh CẢ TRƯỚC LẪN SAU khi vá (bản chưa vá chưa có tham số này).
        Giữ nó xanh ở cả hai bên mới chứng minh được bản vá ⛔ không đụng vào giá
        trị; nếu gọi kèm `escape_html=True` thì trước khi vá nó đỏ vì thiếu tham
        số — đỏ vì lý do sai, ⛔ không nói lên điều gì về giá trị.
        """
        exp = self._engine().explain("kq", {"a": 3, "b": 1})
        self.assertIs(exp.value, True)

    def test_gia_tri_van_nguyen_khi_bat_escape(self):
        """Bật escape thì chuỗi công thức đổi, ⛔ giá trị tính ra phải y nguyên."""
        exp = self._engine().explain("kq", {"a": 3, "b": 1}, escape_html=True)
        self.assertEqual(exp.steps[-1].formula, "a &gt; b")
        self.assertIs(exp.value, True)
