import re
import hashlib
import json
from typing import Any, Dict, List, Set, Optional, Tuple, Union

_PERCENT_RE = re.compile(r'(?<!\w)(\d+(?:\.\d+)?)\s*%')

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