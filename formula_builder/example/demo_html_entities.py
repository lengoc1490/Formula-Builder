"""Demo chạy ĐỘC LẬP (⛔ không cần frappe, ⛔ không cần site) — Phần B.

Chứng minh bằng mắt: công thức có `>` `<` `>=` `<=` ở dạng HTML entity
(`&gt;` `&lt;` …) trước đây làm engine báo "Syntax error", sau bản vá chạy đúng.

Cách in ra TRƯỚC/SAU mà ⛔ không cần dựng lại bản cũ: tạm TẮT đúng hàm mà bản
vá thêm vào (`html_unescape_formula`) — tức là trả engine về đúng hành vi trước
vá — chạy, rồi bật lại. Không đoán, không mô phỏng tay.

Chạy:
    cd ~/myfrappe/apps/formula_builder-wt-noci
    python formula_builder/example/demo_html_entities.py
"""

import contextlib
import os
import sys

# Cho phép chạy trực tiếp từ bất kỳ đâu: thêm thư mục gốc app vào sys.path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

from formula_builder.formula_utils import FormulaEngine          # noqa: E402
from formula_builder.formula_utils.normalize import (            # noqa: E402
    html_unescape_formula,
    html_escape_formula,
)

LINE = "─" * 74


@contextlib.contextmanager
def ban_chua_va():
    """Tạm trả engine về HÀNH VI TRƯỚC KHI VÁ.

    Chỉ vô hiệu hoá đúng hàm mà bản vá thêm vào, ở mọi cửa vào đã dùng nó.
    Hết khối lệnh là trả nguyên trạng — ⛔ không sửa gì trên đĩa.
    """
    import formula_builder.formula_utils.engine_core as _ec
    import formula_builder.formula_utils.normalize as _nz
    import formula_builder.formula_utils.topo as _tp
    import formula_builder.flexible_formula_engine as _ffe

    da_luu = {}
    for mod in (_nz, _ec, _tp, _ffe):
        if getattr(mod, "html_unescape_formula", None) is not None:
            da_luu[mod] = mod.html_unescape_formula
            mod.html_unescape_formula = lambda s: s      # y như trước khi vá
    try:
        yield
    finally:
        for mod, fn in da_luu.items():
            mod.html_unescape_formula = fn


def _tinh(cong_thuc, inputs):
    """Tính 1 công thức → (kết quả, chuỗi lỗi). ⛔ Không để demo đổ."""
    try:
        eng = FormulaEngine(formulas=[{"name": "kq", "formula": cong_thuc}])
        return eng.calculate(inputs)["kq"], None
    except Exception as e:                      # noqa: BLE001 — demo, in ra là đủ
        # ⛔ chỉ lấy dòng đầu: thông báo của FormulaError có nhiều dòng, in hết
        # thì bảng TRƯỚC/SAU vỡ, không đọc được ca nào ra ca nào.
        return None, f"{type(e).__name__}: {str(e).splitlines()[0]}"


def _in_truoc_sau(cong_thuc, inputs, mo_ta):
    with ban_chua_va():
        truoc, loi_truoc = _tinh(cong_thuc, inputs)
    sau, loi_sau = _tinh(cong_thuc, inputs)      # bản đang chạy (đã vá)

    chuoi_truoc = f"LỖI  {loi_truoc}" if loi_truoc else f"{truoc!r}"
    chuoi_sau = f"LỖI  {loi_sau}" if loi_sau else f"{sau!r}"
    print(f"  • {mo_ta}")
    print(f"      TRƯỚC : engine nhận {cong_thuc!r:32} → {chuoi_truoc}")
    print(f"      SAU   : gỡ còn      {html_unescape_formula(cong_thuc)!r:32} → {chuoi_sau}")
    return loi_truoc, loi_sau


def phan_1_go_entity():
    print(LINE)
    print("1. GỠ HTML ENTITY Ở CỬA VÀO  (html_unescape_formula)")
    print(LINE)
    for raw in (
        "a &gt; b", "a &lt; b", "a &gt;= b", "a &lt;= b",
        "a &lt;&gt; b", "a &amp; b", '&quot;q&quot;', "a &#62; b",
        "AT&T",             # '&' trần — KHÔNG phải entity ⇒ phải giữ nguyên
        "a + b",  # &nbsp; giải ra U+00A0, eval() sẽ ném lỗi
        "“qty”",  # nháy cong dán từ Word
    ):
        print(f"      {raw!r:26} → {html_unescape_formula(raw)!r}")
    print("      (hai dòng đầu của nhóm '&' trần: giữ NGUYÊN — đó là công thức")
    print("       hợp lệ của người dùng, không phải HTML, ⛔ không được nuốt)")
    print()


def phan_2_so_sanh():
    print(LINE)
    print("2. CÔNG THỨC SO SÁNH — TRƯỚC / SAU")
    print(LINE)
    ca = [
        ("a &gt; b", {"a": 3, "b": 1}, "'a > b' — lớn hơn"),
        ("a &gt;= b", {"a": 3, "b": 3}, "'a >= b' — lớn hơn hoặc bằng"),
        ("a &lt;= b", {"a": 3, "b": 3}, "'a <= b' — nhỏ hơn hoặc bằng"),
        ("a &lt; b", {"a": 1, "b": 3}, "'a < b' — nhỏ hơn"),
        ("qty * rate &gt; 100", {"qty": 5, "rate": 30}, "so sánh với biểu thức"),
        ("IF(a &gt; b, 1, 0)", {"a": 3, "b": 1}, "so sánh trong IF()"),
        ("a &gt; b and b &lt; c", {"a": 3, "b": 1, "c": 9}, "kết hợp and/or"),
    ]
    so_ca_loi = 0
    for cong_thuc, inputs, mo_ta in ca:
        loi_truoc, loi_sau = _in_truoc_sau(cong_thuc, inputs, mo_ta)
        if loi_truoc and not loi_sau:
            so_ca_loi += 1
    print()
    print(f"  ⇒ {so_ca_loi}/{len(ca)} ca: TRƯỚC lỗi, SAU chạy đúng.")
    print()


def phan_3_canh_ma():
    print(LINE)
    print("3. CẠNH PHỤ THUỘC MA — lỗi IM LẶNG nguy hiểm nhất")
    print(LINE)
    print("  Chuỗi 'a &gt; b' chứa định danh 'gt'. Nếu tài liệu có công thức TÊN")
    print("  đúng bằng 'gt' thì DependencyGraph dựng cạnh 'gt → x' ⇒ đổi thứ tự")
    print("  tính ⇒ SAI SỐ mà ⛔ không có lỗi nào nổi lên.")
    print()

    from formula_builder.formula_utils.topo import DependencyGraph

    formulas = {"gt": "1 + 2", "x": "a &gt; b"}

    with ban_chua_va():
        g_truoc = DependencyGraph()
        g_truoc.build_from_exprs(formulas)

    g_sau = DependencyGraph()
    g_sau.build_from_exprs(formulas)

    print(f"      TRƯỚC : reverse_graph['x'] = {g_truoc.reverse_graph['x']}"
          f"   ← cạnh MA (gt → x)")
    print(f"      SAU   : reverse_graph['x'] = {g_sau.reverse_graph['x']}"
          f"   ← sạch")
    print()

    with ban_chua_va():
        truoc, loi_truoc = _tinh("a &gt; b", {"a": 3, "b": 1})
    sau, loi_sau = _tinh("a &gt; b", {"a": 3, "b": 1})
    print("      Cùng công thức đó, engine tính:")
    print("        TRƯỚC : " + (f"LỖI  {loi_truoc}" if loi_truoc else repr(truoc)))
    print("        SAU   : " + (f"LỖI  {loi_sau}" if loi_sau else repr(sau)))
    print()


def _esc_nhu_js(s):
    """Mô phỏng `_esc()` của `formula_builder.js` — đường hiển thị THẬT của app.

    VÌ SAO phải mô phỏng: hợp đồng của cả lớp là "escape ĐÚNG MỘT LẦN, ở lớp
    NGOÀI CÙNG của đường hiển thị". Lớp ngoài cùng ở đây là JS, ⛔ không phải
    Python — nên muốn chứng minh người dùng đọc đúng thì phải đi hết đường.
    """
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def phan_4_escape_chieu_ra():
    print(LINE)
    print("4. ESCAPE Ở CỬA RA — ĐÚNG MỘT LẦN, ở lớp NGOÀI CÙNG của đường hiển thị")
    print(LINE)
    eng = FormulaEngine(formulas=[{"name": "kq", "formula": "a > b"}])
    # Mặc định của explain() là RAW — vì lớp ngoài cùng (JS) ĐÃ escape.
    exp_raw = eng.explain("kq", {"a": 3, "b": 1})
    # Nơi render thẳng HTML mà ⛔ không tự escape (template in ấn) thì bật cờ:
    exp_esc = eng.explain("kq", {"a": 3, "b": 1}, escape_html=True)
    print(f"      người dùng nhập                    : {'a > b'!r}")
    print(f"      lõi LƯU + explain() trả (RAW)      : {exp_raw.steps[-1].formula!r}")
    print(f"      → JS `_esc()` escape MỘT lần       : {_esc_nhu_js(exp_raw.steps[-1].formula)!r}")
    print(f"        ⇒ người dùng ĐỌC                 : {'a > b'!r}   ✔ đúng, ⛔ không phải 'a &gt; b'")
    print()
    print(f"      nơi KHÔNG tự escape (in ấn)        : escape_html=True → "
          f"{exp_esc.steps[-1].formula!r}")
    print(f"      giá trị đã tính (⛔ không escape)   : {exp_esc.value!r}")
    print()
    print("      ⚠ CẠM BẪY: nếu đổi mặc định của explain() thành escape thì")
    print(f"        JS `_esc()` sẽ cho ra {_esc_nhu_js(exp_esc.steps[-1].formula)!r}")
    print("        ⇒ người dùng đọc thấy 'a &gt; b' — escape HAI lần.")
    print()
    print("      Vòng tròn an toàn (escape ở cửa ra → đọc lại → gỡ ở cửa vào):")
    vong = html_escape_formula("qty * rate > 100")
    print(f"        {vong!r} → {html_unescape_formula(vong)!r}")
    print()


def main():
    print()
    print("DEMO: HTML ENTITY TRONG CÔNG THỨC  (⛔ không cần frappe)")
    print("TRƯỚC = hành vi trước khi vá (tạm tắt html_unescape_formula) · "
          "SAU = bản đang chạy")
    print()
    phan_1_go_entity()
    phan_2_so_sanh()
    phan_3_canh_ma()
    phan_4_escape_chieu_ra()
    print(LINE)
    print("KẾT LUẬN")
    print(LINE)
    print("  • '>' '<' '>=' '<=' ở dạng entity (do HTML/form/JSON sinh ra) nay chạy đúng.")
    print("  • Cạnh phụ thuộc ma vào công thức tên 'gt'/'lt'/'amp'/'quot' đã hết.")
    print("  • Giá trị LƯU vẫn là bản gốc; chỉ escape khi chuỗi đi ra giao diện.")
    print()


if __name__ == "__main__":
    main()
