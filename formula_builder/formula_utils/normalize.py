# formula_utils/normalize.py
# Formula normalization, hashing, and helper functions

import re
import ast
import hashlib
import json
from typing import Any, Dict, List, Set, Optional, Tuple, Union
from decimal import Decimal
import inspect

_PERCENT_RE = re.compile(r'(?<!\w)(\d+(?:\.\d+)?)\s*%')

_LOGIC_REMAP: Dict[str, str] = {
    'and': 'and_',
    'or':  'or_',
    'not': 'not_',
}

_PARAM_EXCLUDES: frozenset = frozenset({
    'x', 'y', 'z', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h',
    'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't',
    'lo', 'hi', 'dt',
    'col', 'key', 'fmt', 'nth', 'sep', 'end', 'old', 'new',
})

# ----------------------------------------------------------------------
# _build_known_kwargs  — LAZY import để tránh circular
# ----------------------------------------------------------------------

def _build_known_kwargs() -> frozenset:
    """
    Xây dựng frozenset chứa tất cả tham số keyword argument từ BASE_FUNCS.

    Import BASE_FUNCS bên trong hàm (lazy) để tránh circular:
      normalize → registry → agg/text → normalize  ❌
    Khi hàm này được gọi lần đầu, toàn bộ funcs/ đã load xong → an toàn.
    """
    # ── Lazy import ────────────────────────────────────────────────────
    from .funcs.registry import BASE_FUNCS  # noqa: PLC0415

    known: set = set()
    EXCLUDE_SHORT = 3
    SKIP_NAMES = {
        'self', 'cls', 'args', 'kwargs',
        'x', 'y', 'z', 'a', 'b', 'c',
        'i', 'j', 'k', 'n', 'm',
        'lo', 'hi', 'dt', 'col', 'key', 'fmt', 'nth', 'sep', 'end', 'old', 'new',
    }

    for func in BASE_FUNCS.values():
        if not callable(func):
            continue
        try:
            sig = inspect.signature(func)
            for param_name, param in sig.parameters.items():
                if param.kind in (
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.KEYWORD_ONLY,
                ):
                    if len(param_name) >= EXCLUDE_SHORT and param_name not in SKIP_NAMES:
                        known.add(param_name)
        except (ValueError, TypeError):
            continue

    extra = {
        "default", "sort_by", "reverse", "value_key", "group_by",
        "missing_value", "error_on_missing_sort_key",
        "unit", "start", "length", "match_type", "if_not_found",
        "trace_mode", "delimiter", "ignore_empty", "decimals", "ndigits",
        "preserve_order", "value", "days", "months", "years",
        "sources", "targets", "method", "source_id_key", "source_amount_key",
        "target_id_key", "target_qty_key", "target_amount_key",
        "target_weight_key", "target_pct_key", "target_manual_amount_key",
        "target_manual_pct_key", "rounding_policy", "round_digits",
        "mixed_residual_method", "id_key", "dep_ids_key", "deps_list_key",
        "dep_id_key", "id_fn", "deps_fn", "epsilon", "max_iter_fallback",
        "b_fn", "coeff_fn", "output_fn", "feasibility_fn",
    }
    known.update(extra)
    return frozenset(known)


# Khởi tạo lười — None cho đến lần gọi normalize_formula() đầu tiên
_KNOWN_KWARGS: Optional[frozenset] = None

def _get_known_kwargs() -> frozenset:
    global _KNOWN_KWARGS
    if _KNOWN_KWARGS is None:
        _KNOWN_KWARGS = _build_known_kwargs()
    return _KNOWN_KWARGS


# ----------------------------------------------------------------------
# normalize_formula
# ----------------------------------------------------------------------

def normalize_formula(expr: str, canonical_names: frozenset) -> str:
    """
    Chuẩn hóa công thức:
      - Chuyển % thành /100
      - Chuyển <> thành !=
      - Chuyển = thành == (trừ khi là keyword argument)
      - Chuẩn hóa tên hàm (lowercase → canonical)
      - Chuyển and/or/not thành and_/or_/not_ khi gọi hàm
    """
    known_kwargs = _get_known_kwargs()   # lazy load lần đầu gọi

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

        if ch == '<' and i + 1 < n and expr[i + 1] == '>':
            result.append('!=')
            i += 2
            continue

        if ch == '=':
            next_ch = expr[i + 1] if i + 1 < n else ''
            prev_ch = expr[i - 1] if i > 0    else ''

            if next_ch == '=':
                result.append('==')
                i += 2
                continue

            if prev_ch in ('!', '<', '>', '='):
                result.append(ch)
                i += 1
                continue

            if prev_ch == ' ' or next_ch == ' ':
                result.append('==')
                i += 1
                continue

            j = i - 1
            while j >= 0 and (expr[j].isalnum() or expr[j] == '_'):
                j -= 1
            ident_before = expr[j + 1:i]

            is_kwarg = (len(ident_before) >= 3 and ident_before in known_kwargs)
            result.append('=' if is_kwarg else '==')
            i += 1
            continue

        if ch.isalpha() or ch == '_':
            j = i
            while j < n and (expr[j].isalnum() or expr[j] == '_'):
                j += 1
            ident = expr[i:j]

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

        result.append(ch)
        i += 1

    return ''.join(result)


# ----------------------------------------------------------------------
# match_criteria
# ----------------------------------------------------------------------

def match_criteria(value: Any, criteria: Any) -> bool:
    """Kiểm tra giá trị có khớp với tiêu chí."""
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
    payload = json.dumps(formulas, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def hash_dict(data: Dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()