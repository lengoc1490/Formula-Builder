import html
import re
import hashlib
import json
from typing import Any, Dict, List, Set, Optional, Tuple, Union

_PERCENT_RE = re.compile(r'(?<!\w)(\d+(?:\.\d+)?)\s*%')


# ----------------------------------------------------------------------
# HTML entity / ký tự lạ — dán từ web, Word, hoặc đi qua đường HTML
# ----------------------------------------------------------------------
# VÌ SAO cần lớp này (không phải chuyện thẩm mỹ):
#   1. Frappe escape > < & " ' khi hiển thị / khi công thức đi qua HTML.
#      Công thức "a > b" tới engine thành "a &gt; b" ⇒ SyntaxError khi eval.
#   2. NGUY HIỂM HƠN: DependencyGraph.build_from_exprs dò định danh bằng regex
#      [a-zA-Z_]\w*. Chuỗi "a &gt; b" chứa định danh "gt"; "&lt;" chứa "lt";
#      "&amp;" chứa "amp"; "&quot;" chứa "quot"; "&nbsp;" chứa "nbsp". Nếu có
#      công thức/biến nào trùng các tên đó ⇒ SINH CẠNH PHỤ THUỘC MA ⇒ sai thứ
#      tự tính ⇒ sai số IM LẶNG. Vì vậy phải gỡ TRƯỚC bước dò phụ thuộc.
#   3. "&quot;qty&quot;" không khớp mẫu chuỗi trong nháy của build_from_exprs
#      nên bị coi là định danh trần.
#   4. html.unescape("a&nbsp;+&nbsp;b") trả U+00A0 — eval() ném
#      "SyntaxError: invalid non-printable character U+00A0". Nháy cong “ ” ‘ ’
#      dán từ Word cũng phá literal.
_WEIRD_CHAR_RE = re.compile(
    "[   -   　"      # khoảng trắng Unicode
    "​‌‍﻿"                           # zero-width + BOM
    "“”„‟‘’‚‛]"  # nháy cong
)

_WEIRD_CHAR_MAP: Dict[str, str] = {
    # nháy kép cong → nháy kép thẳng
    "“": '"', "”": '"', "„": '"', "‟": '"',
    # nháy đơn cong → nháy đơn thẳng
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    # zero-width / BOM → xoá hẳn (vô hình nhưng phá token)
    "​": "", "‌": "", "‍": "", "﻿": "",
    # khoảng trắng Unicode → space thường
    " ": " ", " ": " ", " ": " ", " ": " ", "　": " ",
}
for _cp in range(0x2000, 0x200B):     # EN QUAD … HAIR SPACE
    _WEIRD_CHAR_MAP[chr(_cp)] = " "


# charref SỐ dài quá ngưỡng `sys.set_int_max_str_digits` (mặc định 4300 chữ số)
# làm `html.unescape` ném ValueError NGAY khi đổi chuỗi sang int — trước cả bước
# kiểm giá trị có nằm trong Unicode hay không. Hai việc phải làm trước khi gỡ
# lại entity, để MỘT charref hỏng ⛔ không tắt luôn việc gỡ cho cả công thức:
#   • charref quá dài ⇒ thay U+FFFD (chắc chắn ngoài dải: 0x10FFFF chỉ 7 chữ số);
#   • charref nhiều số 0 vô nghĩa ⇒ bỏ số 0 (giá trị ⛔ không đổi: "&#000…65;"
#     vẫn là 'A', mà chuỗi thì ngắn lại, ⛔ không còn chạm ngưỡng int()).
# ⛔ KHÔNG `int()` ở đây — mọi phép đo đều trên ĐỘ DÀI, nên ⛔ không chạm lại
# đúng cái ngưỡng vừa làm `html.unescape` ném lỗi.
# ⛔ Cố ý KHÔNG đụng charref ngoài dải nhưng NGẮN (vd "&#99999999;"): lượt gỡ lại
# phải hành xử Y HỆT `html.unescape` bình thường (nó giữ nguyên literal đó).
_MAX_REF_DIGITS = 20              # 20 chữ số ≈ 10^20 ≫ 0x10FFFF ⇒ chắc chắn vô hiệu
_UNICODE_REPLACEMENT = "\ufffd"
_RE_NUMERIC_REF = re.compile(r"&#(\d+);")


def _neutralise_oversize_numeric_ref(m: "re.Match") -> str:
    """Làm sạch charref SỐ hỏng để lượt gỡ entity lại chạy được."""
    digits = m.group(1)
    sig = digits.lstrip("0") or "0"
    if len(sig) > _MAX_REF_DIGITS:
        return _UNICODE_REPLACEMENT
    if sig != digits:
        return f"&#{sig};"
    return m.group(0)


def html_unescape_formula(expr: str) -> str:
    """Gỡ HTML entity + ký tự lạ của công thức ở CỬA VÀO của engine.

    Nguyên tắc: giá trị LƯU giữ RAW, chỉ escape khi chuỗi đi RA giao diện.
    Nhờ có hàm này ở cửa vào, escape ở cửa ra là an toàn vòng tròn
    (escape → lưu → đọc lại → unescape ra đúng bản gốc).

    Quy trình:
      1. Chốt nhanh — công thức sạch (không '&', không ký tự lạ) trả về Y NGUYÊN:
         giữ hiệu năng cho hot path (engine parse mọi công thức) và tránh mọi rủi
         ro biến đổi ngoài ý muốn trên công thức vốn đã đúng.
      2. html.unescape — MỘT LƯỢT DUY NHẤT. ⛔ KHÔNG lặp tới khi hết entity:
         lặp sẽ phá ca người dùng cố ý viết literal "&gt;" trong chuỗi.
      3. Chuẩn hoá ký tự lạ (phần chống SyntaxError thật).

    ⛔ KHÔNG gọi hàm này lên TÊN công thức (`name`) — tên là khoá để khớp DAG,
    không phải biểu thức. Chỉ gọi lên phần `formula`.
    """
    if not isinstance(expr, str) or not expr:
        return expr

    if "&" not in expr and _WEIRD_CHAR_RE.search(expr) is None:
        return expr

    if "&" in expr:
        try:
            expr = html.unescape(expr)
        except ValueError:
            # Đường tới đây DUY NHẤT là charref SỐ khổng lồ (> ngưỡng
            # `sys.set_int_max_str_digits`, mặc định 4300 chữ số): `int()` ném lỗi
            # trước khi kịp kiểm dải Unicode.
            # ✅[V] ⛔ KHÔNG phải vì '&' trần: "AT&T", "a&b", "&&", "&#", "&zzz;",
            # "&gt" … đều trả về bình thường, ⛔ không ném (đo 2026-10-12 trên
            # CPython 3.10.12→3.14; đọc mã nguồn 5 nhánh — `return '&' + s`).
            # Phải vô hiệu charref hỏng rồi gỡ entity LẠI: nếu bỏ qua cả chuỗi thì
            # "&gt;" nằm CÙNG công thức cũng ⛔ không được gỡ ⇒ công thức sai IM LẶNG
            # (đúng loại lỗi mà lớp này sinh ra để chặn).
            try:
                expr = html.unescape(
                    _RE_NUMERIC_REF.sub(_neutralise_oversize_numeric_ref, expr)
                )
            except ValueError:
                pass  # cùng lắm giữ nguyên — thà ⛔ không gỡ còn hơn vỡ

    if _WEIRD_CHAR_RE.search(expr) is not None:
        expr = _WEIRD_CHAR_RE.sub(
            lambda m: _WEIRD_CHAR_MAP.get(m.group(0), " "), expr
        )
    return expr


def html_escape_formula(expr: str) -> str:
    """Escape công thức ở CỬA RA giao diện (HTML).

    Chỉ dùng cho chuỗi công thức hiển thị cho người dùng — ⛔ KHÔNG áp lên số/
    giá trị đã tính, ⛔ KHÔNG áp lên giá trị ghi xuống DB, ⛔ KHÔNG áp hai lần
    trên cùng một chuỗi (nếu hàm này gọi hàm khác thì chỉ escape ở lớp ngoài cùng).
    """
    if not isinstance(expr, str) or not expr:
        return expr
    return html.escape(expr, quote=True)

_LOGIC_REMAP: Dict[str, str] = {
    'and': 'and_',
    'or':  'or_',
    'not': 'not_',
}

# ----------------------------------------------------------------------
# normalize_formula
# ----------------------------------------------------------------------

def normalize_formula(expr: str, canonical_names: frozenset) -> str:
    """
    Chuẩn hóa công thức:
      - Chuyển % thành /100
      - Chuyển <> thành !=
      - Chuyển = thành == (mọi dấu = đơn lẻ đều là so sánh)
      - Chuẩn hóa tên hàm (lowercase → canonical)
      - Chuyển and/or/not thành and_/or_/not_ khi gọi hàm

    Tham số:
        expr: Công thức gốc (string)
        canonical_names: Tên hàm/variable chuẩn hóa (frozenset)
    """
    # Gỡ HTML entity TRƯỚC mọi phép thay thế khác — thứ tự này quan trọng:
    # "&lt;&gt;" phải thành "<>" rồi mới được nhận diện thành "!="; còn "<" ">"
    # "&gt;=" chỉ đúng sau khi entity đã được giải.
    expr = html_unescape_formula(expr)

    expr = _PERCENT_RE.sub(r'(\1/100)', expr)

    lower_map: Dict[str, str] = {}
    for name in canonical_names:
        lname = name.lower()
        if lname not in lower_map:
            lower_map[lname] = name

    result: list = []
    i = 0
    n = len(expr)

    while i < n:
        ch = expr[i]

        # Xử lý chuỗi trong dấu nháy
        if ch in ('"', "'"):
            quote = ch
            result.append(ch)
            i += 1
            while i < n:
                c = expr[i]
                result.append(c)
                if c == '\\':
                    i += 1
                    if i < n:
                        result.append(expr[i])
                        i += 1
                    continue
                if c == quote:
                    i += 1
                    break
                i += 1
            continue

        # Xử lý '<>' -> '!='
        if ch == '<' and i + 1 < n and expr[i + 1] == '>':
            result.append('!=')
            i += 2
            continue

        # Xử lý dấu '='
        if ch == '=':
            next_ch = expr[i + 1] if i + 1 < n else ''
            prev_ch = expr[i - 1] if i > 0    else ''

            # Đã có '==' -> giữ nguyên
            if next_ch == '=':
                result.append('==')
                i += 2
                continue

            # Các trường hợp '!=', '<=', '>=' hoặc '=' đứng sau các ký tự này
            if prev_ch in ('!', '<', '>', '='):
                result.append(ch)
                i += 1
                continue

            # Mọi '=' còn lại đều là so sánh
            result.append('==')
            i += 1
            continue

        # Xử lý tên (identifier) và hàm
        if ch.isalpha() or ch == '_':
            j = i
            while j < n and (expr[j].isalnum() or expr[j] == '_'):
                j += 1
            ident = expr[i:j]

            # Kiểm tra xem có phải gọi hàm không (theo sau là '(')
            k = j
            while k < n and expr[k] == ' ':
                k += 1
            is_func_call = (k < n and expr[k] == '(')

            if is_func_call:
                prev_ok = (i == 0) or not (expr[i - 1].isalnum() or expr[i - 1] == '_')
                low = ident.lower()

                if low in _LOGIC_REMAP and prev_ok:
                    result.append(_LOGIC_REMAP[low])
                    i = k
                elif low in lower_map:
                    result.append(lower_map[low])
                    i = j
                else:
                    result.append(ident)
                    i = j
            else:
                result.append(ident)
                i = j
            continue

        # Các ký tự khác giữ nguyên
        result.append(ch)
        i += 1

    return ''.join(result)


# ----------------------------------------------------------------------
# match_criteria
# ----------------------------------------------------------------------

def match_criteria(value: Any, criteria: Any) -> bool:
    """Kiểm tra giá trị có khớp với tiêu chí (hỗ trợ wildcard và so sánh)."""
    tc = type(criteria)
    if tc is int or tc is float:
        try:
            return float(value) == criteria
        except (TypeError, ValueError):
            return False
    if criteria is None:
        return value is None
    crit = (criteria if tc is str else str(criteria)).strip()
    if not crit:
        return False
    c0 = crit[0]
    if c0 not in ('>', '<', '=', '!', '*') and '*' not in crit:
        v = '' if value is None else (value if type(value) is str else str(value))
        return v == crit or v.lower() == crit.lower()
    v = '' if value is None else (value if type(value) is str else str(value))
    if c0 == '>':
        if len(crit) > 1 and crit[1] == '=':
            try:
                return float(value) >= float(crit[2:])
            except (TypeError, ValueError):
                return False
        try:
            return float(value) > float(crit[1:])
        except (TypeError, ValueError):
            return False
    if c0 == '<':
        if len(crit) > 1:
            c1 = crit[1]
            if c1 == '=':
                try:
                    return float(value) <= float(crit[2:])
                except (TypeError, ValueError):
                    return False
            if c1 == '>':
                return v != crit[2:].strip()
        try:
            return float(value) < float(crit[1:])
        except (TypeError, ValueError):
            return False
    if c0 == '!':
        if len(crit) > 1 and crit[1] == '=':
            return v != crit[2:].strip()
        return False
    if c0 == '=':
        rest = crit[1:]
        if rest.startswith('='):
            rest = rest[1:]
        return v == rest.strip()
    if '*' in crit:
        pat = '^' + re.escape(crit).replace(r'\*', '.*') + '$'
        return re.match(pat, v, re.IGNORECASE) is not None
    return v.lower() == crit.lower()


# ----------------------------------------------------------------------
# safe_str
# ----------------------------------------------------------------------

def safe_str(x: Any) -> str:
    """Chuyển đối tượng sang chuỗi an toàn (None -> '')."""
    return str(x or "")


# ----------------------------------------------------------------------
# Hashing utilities
# ----------------------------------------------------------------------

def hash_formulas(formulas: List[Dict[str, str]]) -> str:
    """Tạo SHA-256 hash cho danh sách công thức."""
    payload = json.dumps(formulas, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def hash_dict(data: Dict[str, Any]) -> str:
    """Tạo SHA-256 hash cho một dict bất kỳ."""
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()