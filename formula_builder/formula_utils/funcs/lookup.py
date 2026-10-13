# formula_utils/funcs/lookup.py
# Lookup, array operations, and advanced data functions for formula engine

from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple, Union
import re

# Import from sibling modules
from ..normalize import safe_str, match_criteria
from .math import _to_iter, _to_list, _extract_key, _NUMERIC_TYPES, builtins_sum


# ----------------------------------------------------------------------
# Basic lookup
# ----------------------------------------------------------------------

def vlookup(key, table, col=1, default=0):
    """
    Excel-style VLOOKUP.

    Parameters:
        key: lookup value
        table: dict {key: row} or list of rows (each row list/tuple)
        col: 1 = first value after key, 0 = return key itself
        default: value if not found
    """
    if isinstance(table, dict):
        row = table.get(key)
        if row is None:
            return default
        if isinstance(row, (list, tuple)):
            if col == 0:
                return key
            idx = col - 1
            return row[idx] if idx < len(row) else default
        # scalar value dict
        return row if col <= 1 else default
    # List of rows
    for row in table:
        if row and row[0] == key:
            if col == 0:
                return key
            idx = col   # col=1 → index 1 (first value after key)
            return row[idx] if idx < len(row) else default
    return default


def xlookup(lookup_value: Any, lookup_array: Any, return_array: Any, if_not_found: Any = 0) -> Any:
    """Excel-style XLOOKUP."""
    if isinstance(lookup_array, dict):
        return lookup_array.get(lookup_value, if_not_found)

    la = _to_list(lookup_array)
    ra = _to_list(return_array)
    if not la or not ra or len(la) != len(ra):
        return if_not_found
    try:
        idx = la.index(lookup_value)
        return ra[idx]
    except ValueError:
        return if_not_found


def index(array, row_num, col_num=0):
    """Get element from array (1-indexed like Excel)."""
    if isinstance(array, (list, tuple)):
        if row_num < 1 or row_num > len(array):
            from ..errors import FormulaError, ErrorCode
            raise FormulaError(f"index: row {row_num} out of range", code=ErrorCode.INDEX_OUT_OF_RANGE)
        row = array[row_num - 1]
        if col_num == 0:
            return row
        if isinstance(row, (list, tuple)):
            if col_num < 1 or col_num > len(row):
                raise FormulaError(f"index: col {col_num} out of range", code=ErrorCode.INDEX_OUT_OF_RANGE)
            return row[col_num - 1]
        return row
    return array


def match(lookup_value: Any, lookup_array: Any, match_type: int = 1) -> int:
    """Excel-style MATCH: return 1-indexed position."""
    if isinstance(lookup_array, dict):
        la = list(lookup_array.keys())
    else:
        la = _to_list(lookup_array)

    if match_type == 0:
        for i, val in enumerate(la):
            if val == lookup_value:
                return i + 1
        from ..errors import FormulaError, ErrorCode
        raise FormulaError(f"match: không tìm thấy '{lookup_value}'", code=ErrorCode.INVALID_TYPE)
    elif match_type == 1:
        pos = 0
        for i, val in enumerate(la):
            try:
                if float(val) <= float(lookup_value):
                    pos = i + 1
                else:
                    break
            except (TypeError, ValueError):
                continue
        if pos == 0:
            raise FormulaError("match: không có giá trị <= lookup_value", code=ErrorCode.INVALID_TYPE)
        return pos
    else:  # match_type == -1
        pos = 0
        for i, val in enumerate(la):
            try:
                if float(val) >= float(lookup_value):
                    pos = i + 1
                else:
                    break
            except (TypeError, ValueError):
                continue
        if pos == 0:
            raise FormulaError("match: không có giá trị >= lookup_value", code=ErrorCode.INVALID_TYPE)
        return pos


def choose(index_num, *values):
    """Choose value from list by 1-indexed position (Excel-style)."""
    if not isinstance(index_num, int) or index_num < 1 or index_num > len(values):
        from ..errors import FormulaError, ErrorCode
        raise FormulaError(f"choose: index {index_num} out of range (1-{len(values)})", code=ErrorCode.INDEX_OUT_OF_RANGE)
    return values[index_num - 1]


# ----------------------------------------------------------------------
# filter_array
# ----------------------------------------------------------------------

def filter_array(data: Any, operator: str = None, threshold: Any = None,
                 key: str = None, value: Any = None) -> List[Any]:
    """
    Filter array/list/dict by condition.
    Two modes:
        1) key=value shortcut (no operator)
        2) operator string: '>', '<', '>=', '<=', '==', '!='
    """
    # Chế độ 2: key=value shortcut (không cần operator)
    if operator is None and key is not None and value is not None:
        src = data.values() if type(data) is dict else data
        return [r for r in src if type(r) is dict and r.get(key) == value]

    # Chế độ 1: operator string (legacy)
    ops = {
        ">":  lambda x, t: x > t,
        "<":  lambda x, t: x < t,
        ">=": lambda x, t: x >= t,
        "<=": lambda x, t: x <= t,
        "==": lambda x, t: x == t,
        "!=": lambda x, t: x != t,
    }
    fn = ops.get(operator) if operator else None
    if fn is None:
        return []

    if key is not None:
        src = data.values() if isinstance(data, dict) else data
        result = []
        for r in src:
            if not isinstance(r, dict):
                continue
            v = r.get(key)
            try:
                if v is not None and fn(v, threshold):
                    result.append(r)
            except TypeError:
                pass
        return result

    result = []
    for x in _to_iter(data):
        try:
            if fn(x, threshold):
                result.append(x)
        except TypeError:
            pass
    return result


# ----------------------------------------------------------------------
# last, first, nth
# ----------------------------------------------------------------------

def last(
    data: List[Any],
    sort_by: Union[str, List[str], None] = None,
    n: int = 1,
    group_by: Optional[str] = None,
    reverse: bool = True,
    value_key: Optional[str] = None,
    default: Any = None,
    missing_value: Any = None,
    error_on_missing_sort_key: bool = False,
    preserve_order: bool = False,
) -> Any:
    """
    Get last (or first if reverse=False) n records, optionally grouped.

    Supports plain list [1,2,3] or list of dicts.
    """
    if not data or n < 1:
        return default if group_by is None else {}

    # Support plain list
    _plain_list = not isinstance(data[0], dict)
    if _plain_list:
        if preserve_order:
            if reverse:
                sliced = data[max(0, len(data) - n):]
            else:
                sliced = data[:n]
            if n == 1:
                return sliced[-1] if reverse and sliced else (sliced[0] if sliced else default)
            return list(sliced) if sliced else default
        else:
            data = [{"_v": item} for item in data]
            if sort_by is None:
                sort_by = "_v"
            if value_key is None:
                value_key = "_v"

    # Normalize sort_by to list
    if sort_by is None:
        sort_keys = []
    elif isinstance(sort_by, str):
        sort_keys = [sort_by]
    else:
        sort_keys = list(sort_by)

    if sort_by is not None and not sort_keys:
        from ..errors import FormulaError, ErrorCode
        raise FormulaError("last: sort_by cannot be empty", code=ErrorCode.INVALID_TYPE)

    # Check strict mode
    if error_on_missing_sort_key and sort_keys and data:
        first = data[0]
        for key in sort_keys:
            if key not in first:
                raise FormulaError(
                    f"last: sort key '{key}' not found in data",
                    code=ErrorCode.INVALID_TYPE
                )

    # ISO date pattern
    _ISO_RE = re.compile(r'^\d{4}-\d{2}-\d{2}')

    def _sortval(v):
        """Return tuple (tier, val) for consistent cross-type sorting."""
        if v is None:
            return (0, '')
        if isinstance(v, (datetime, date)):
            return (2, v.isoformat())
        if isinstance(v, str):
            sv = v.strip()
            if _ISO_RE.match(sv):
                return (2, sv)
            try:
                return (3, float(sv))
            except (ValueError, TypeError):
                return (4, sv.lower())
        try:
            return (3, float(v))
        except (TypeError, ValueError):
            return (4, str(v).lower())

    def sort_key_func(row):
        return tuple(_sortval(row.get(k, missing_value)) for k in sort_keys)

    def _apply_sort(items):
        if sort_keys:
            return sorted(items, key=sort_key_func, reverse=reverse)
        return items

    def _pick(sorted_items):
        selected = sorted_items[:n]
        if value_key:
            selected = [r.get(value_key, default) for r in selected]
        return selected if n > 1 else (selected[0] if selected else default)

    if group_by:
        groups: Dict[Any, List[Dict]] = defaultdict(list)
        for row in data:
            gval = row.get(group_by)
            if gval is not None:
                groups[gval].append(row)
        return {
            gval: _pick(_apply_sort(items)) if items else default
            for gval, items in groups.items()
        }

    return _pick(_apply_sort(data))


def first(
    data: Any,
    sort_by: Any = None,
    n: int = 1,
    group_by: Optional[str] = None,
    value_key: Optional[str] = None,
    default: Any = None,
    **kwargs,
) -> Any:
    """Get first n records (reverse=False)."""
    return last(data, sort_by=sort_by, n=n, group_by=group_by,
                reverse=False, value_key=value_key, default=default, **kwargs)


def nth(
    data: Any,
    n: int,
    sort_by: Any = None,
    reverse: bool = True,
    value_key: Optional[str] = None,
    default: Any = None,
    **kwargs,
) -> Any:
    """Get nth record (1-indexed)."""
    if n < 1:
        return default
    result = last(data, sort_by=sort_by, n=n, reverse=reverse,
                  value_key=value_key, default=default, **kwargs)
    if isinstance(result, list):
        return result[n - 1] if n <= len(result) else default
    return result if n == 1 else default


# Alias
latest = lambda *args, **kwargs: last(*args, reverse=True, **{k: v for k, v in kwargs.items() if k != 'reverse'})
earliest = lambda *args, **kwargs: last(*args, reverse=False, **{k: v for k, v in kwargs.items() if k != 'reverse'})


# ----------------------------------------------------------------------
# sorted_array, map_key
# ----------------------------------------------------------------------

def sorted_array(data: Any, key: str = None, reverse: bool = False) -> List[Any]:
    """Return sorted list from iterable."""
    if isinstance(data, dict):
        src = list(data.values())
    else:
        src = list(data)

    if not src:
        return src

    if key is not None:
        def _sort_key(r):
            v = r.get(key) if isinstance(r, dict) else r
            if v is None:
                return (1, "")
            return (0, v)
        try:
            return sorted(src, key=_sort_key, reverse=reverse)
        except TypeError:
            return sorted(src, key=lambda r: (0, str(r.get(key, "") if isinstance(r, dict) else r)), reverse=reverse)
    try:
        return sorted(src, reverse=reverse)
    except TypeError:
        return sorted(src, key=str, reverse=reverse)


sort = sorted_array  # alias


def map_key(data: Any, key: str) -> List[Any]:
    """Extract a key from each dict in data."""
    src = data.values() if isinstance(data, dict) else data
    return [r.get(key) if isinstance(r, dict) else None for r in src]


# ----------------------------------------------------------------------
# sum_dict (aggregates dict values)
# ----------------------------------------------------------------------

def sum_dict(d: Any) -> float:
    """Sum numeric values from dict values."""
    if isinstance(d, dict):
        return builtins_sum(v for v in d.values() if isinstance(v, (int, float)))
    return 0.0


# Avoid circular import of datetime/date inside function
from datetime import datetime, date


# ─── unique ───────────────────────────────────────────────────────────────────
def unique(data: Any, key: str = None) -> List[Any]:
    if key is not None:
        src = _extract_key(data, key)
    else:
        src = _to_iter(data)

    seen_hash = set()
    seen_list = []   # fallback cho unhashable
    result = []
    for item in src:
        try:
            if item not in seen_hash:
                seen_hash.add(item)
                result.append(item)
        except TypeError:
            key_str = str(item)
            if key_str not in seen_list:
                seen_list.append(key_str)
                result.append(item)
    return result


# ─── count_unique ─────────────────────────────────────────────────────────────
def count_unique(data: Any, key: str = None) -> int:
    return len(unique(data, key=key))


# ─── flatten ──────────────────────────────────────────────────────────────────
def flatten(data: Any) -> List[Any]:
    if isinstance(data, dict):
        data = data.values()
    result = []
    for item in data:
        if isinstance(item, (list, tuple)):
            result.extend(flatten(item))
        elif isinstance(item, dict):
            result.extend(flatten(list(item.values())))
        else:
            result.append(item)
    return result


# ─── group_sum ────────────────────────────────────────────────────────────────
def group_sum(data: Any, group_key: str, sum_key: str) -> Dict[Any, float]:
    result: Dict[Any, float] = {}
    src = data.values() if isinstance(data, dict) else data
    for r in src:
        if not isinstance(r, dict):
            continue
        gval = r.get(group_key)
        v = r.get(sum_key)
        if gval is None:
            continue
        if gval not in result:
            result[gval] = 0.0
        if isinstance(v, (int, float)):
            result[gval] += v
    return result

group_by_sum = lambda data, group_key, sum_key: group_sum(data, group_key, sum_key)  # alias

# ─── group_count ──────────────────────────────────────────────────────────────
def group_count(data: Any, group_key: str) -> Dict[Any, int]:
    result: Dict[Any, int] = {}
    src = data.values() if isinstance(data, dict) else data
    for r in src:
        if not isinstance(r, dict):
            continue
        gval = r.get(group_key)
        if gval is None:
            continue
        result[gval] = result.get(gval, 0) + 1
    return result

group_by_count = lambda data, group_key: group_count(data, group_key)  # alias

# ─── group_avg ────────────────────────────────────────────────────────────────
def group_avg(data: Any, group_key: str, avg_key: str) -> Dict[Any, float]:
    sums: Dict[Any, float] = {}
    counts: Dict[Any, int] = {}
    src = data.values() if isinstance(data, dict) else data
    for r in src:
        if not isinstance(r, dict):
            continue
        gval = r.get(group_key)
        v = r.get(avg_key)
        if gval is None or not isinstance(v, (int, float)):
            continue
        sums[gval] = sums.get(gval, 0.0) + v
        counts[gval] = counts.get(gval, 0) + 1
    return {g: sums[g] / counts[g] for g in sums if counts[g] > 0}