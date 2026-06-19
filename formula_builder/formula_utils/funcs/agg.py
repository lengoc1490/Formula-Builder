# formula_utils/funcs/agg.py
# Aggregation functions (sum, count, average, conditional aggregations, etc.)

from typing import Any, Dict, List, Tuple
from collections import defaultdict

# Import helpers from sibling modules
from ..normalize import match_criteria, safe_str
from .math import _to_iter, _to_list, _extract_key, _NUMERIC_TYPES, builtins_sum

# Re-export builtins for internal use
builtins_sum = builtins_sum


# ----------------------------------------------------------------------
# count / counta / countnum
# ----------------------------------------------------------------------

def _safe_count(*args, **kwargs):
    """Count non-null, non-empty values. Supports key extraction."""
    key = kwargs.get('key')
    if len(args) == 1:
        a = args[0]
        if key is not None:
            return builtins_sum(1 for v in _extract_key(a, key) if v not in (None, ''))
        if hasattr(a, '__next__') or (hasattr(a, '__iter__') and not isinstance(a, (str, bytes))):
            return builtins_sum(1 for x in a if x not in (None, ''))
        return builtins_sum(1 for x in _to_iter(a) if x not in (None, ''))
    else:
        return builtins_sum(1 for x in args if x not in (None, ''))


def countnum(data: Any) -> int:
    """Count only numeric values."""
    return builtins_sum(1 for x in _to_iter(data) if isinstance(x, (int, float)))


# counta is alias for _safe_count (counts non-blank)
counta = _safe_count
count = _safe_count


# ----------------------------------------------------------------------
# average
# ----------------------------------------------------------------------

def _safe_average(*args, **kwargs) -> float:
    """Compute average of numeric values. Supports key extraction."""
    key = kwargs.get('key')

    def _collect(value) -> list:
        if type(value) in _NUMERIC_TYPES:
            return [float(value)]
        if type(value) is dict:
            if key is not None:
                v = value.get(key)
                return [float(v)] if type(v) in _NUMERIC_TYPES else []
            return [float(v) for v in value.values() if type(v) in _NUMERIC_TYPES]
        if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
            nums = []
            for item in value:
                if key is not None and type(item) is dict:
                    v = item.get(key)
                    if type(v) in _NUMERIC_TYPES:
                        nums.append(float(v))
                elif type(item) in _NUMERIC_TYPES:
                    nums.append(float(item))
            return nums
        return []

    if len(args) == 0:
        return 0.0
    if len(args) == 1:
        nums = _collect(args[0])
    else:
        nums = []
        for arg in args:
            nums.extend(_collect(arg))
    return builtins_sum(nums) / len(nums) if nums else 0.0


average = _safe_average


# ----------------------------------------------------------------------
# sumif / sumifs
# ----------------------------------------------------------------------

def sumif(range_vals: Any, criteria: Any, sum_range: Any = None, key: str = None) -> float:
    """Sum values where criteria matches."""
    if key is not None:
        if isinstance(key, tuple):
            crit_key, sum_key = key
        else:
            crit_key = sum_key = key
        total = 0.0
        src_it = range_vals.values() if type(range_vals) is dict else range_vals
        for r in src_it:
            if type(r) is not dict:
                continue
            if match_criteria(r.get(crit_key), criteria):
                v = r.get(sum_key)
                if type(v) in _NUMERIC_TYPES:
                    total += v
        return total
    rv = _to_list(range_vals)
    sv = _to_list(sum_range) if sum_range is not None else rv
    if len(rv) != len(sv):
        from ..errors import FormulaError, ErrorCode
        raise FormulaError("sumif: range và sum_range phải cùng độ dài", code=ErrorCode.RANGE_MISMATCH)
    total = 0.0
    for val, sum_val in zip(rv, sv):
        if match_criteria(val, criteria):
            if type(sum_val) in _NUMERIC_TYPES:
                total += sum_val
    return total


def sumifs(sum_range: Any, *criteria_pairs, **kwargs) -> float:
    """Sum with multiple criteria."""
    key = kwargs.get('key')
    # Shortcut: sumifs(rows, key='gia', loai='VL', status='active')
    if key is not None and not criteria_pairs:
        filters = {k: v for k, v in kwargs.items() if k != 'key'}
        total = 0.0
        src_it = sum_range.values() if type(sum_range) is dict else sum_range
        for r in src_it:
            if type(r) is not dict:
                continue
            if all(match_criteria(r.get(fk), fv) for fk, fv in filters.items()):
                v = r.get(key)
                if type(v) in _NUMERIC_TYPES:
                    total += v
        return total
    # Standard path: criteria_pairs positional
    if len(criteria_pairs) % 2 != 0:
        from ..errors import FormulaError, ErrorCode
        raise FormulaError('sumifs: criteria phải đi theo cặp (range, criteria)',
                           code=ErrorCode.INVALID_ARGUMENT_COUNT)
    pairs = [(criteria_pairs[i], criteria_pairs[i+1]) for i in range(0, len(criteria_pairs)-1, 2)]
    total = 0.0
    if key is not None:
        src_it = sum_range.values() if type(sum_range) is dict else sum_range
        for r in src_it:
            if type(r) is not dict:
                continue
            if all(match_criteria(r.get(ck), cv) for ck, cv in pairs):
                v = r.get(key)
                if type(v) in _NUMERIC_TYPES:
                    total += v
        return total
    rv = _to_list(sum_range)
    ranges = [_to_list(criteria_pairs[i]) for i in range(0, len(criteria_pairs)-1, 2)]
    crits = [criteria_pairs[i+1] for i in range(0, len(criteria_pairs)-1, 2)]
    for i, sum_val in enumerate(rv):
        if all(match_criteria(rng[i], crit) for rng, crit in zip(ranges, crits) if i < len(rng)):
            if type(sum_val) in _NUMERIC_TYPES:
                total += sum_val
    return total


# ----------------------------------------------------------------------
# countif / countifs
# ----------------------------------------------------------------------

def countif(range_vals: Any, criteria: Any, key: str = None) -> int:
    """Count values matching criteria."""
    if key is not None:
        src = range_vals.values() if type(range_vals) is dict else range_vals
        return builtins_sum(1 for r in src if type(r) is dict and match_criteria(r.get(key), criteria))
    return builtins_sum(1 for val in _to_iter(range_vals) if match_criteria(val, criteria))


def countifs(*criteria_pairs, **kwargs) -> int:
    """Count with multiple criteria."""
    # List[dict] shortcut: countifs(rows, field1=val1, field2=val2)
    if len(criteria_pairs) == 1 and kwargs:
        rows = criteria_pairs[0]
        src = rows.values() if isinstance(rows, dict) else rows
        return builtins_sum(
            1 for r in src
            if isinstance(r, dict)
            and all(match_criteria(r.get(fk), fv) for fk, fv in kwargs.items())
        )

    if len(criteria_pairs) % 2 != 0:
        from ..errors import FormulaError, ErrorCode
        raise FormulaError("countifs: criteria phải đi theo cặp", code=ErrorCode.INVALID_ARGUMENT_COUNT)
    if not criteria_pairs:
        return 0

    ranges = [_to_list(criteria_pairs[j]) for j in range(0, len(criteria_pairs), 2)]
    criterias = [criteria_pairs[j] for j in range(1, len(criteria_pairs), 2)]
    n = len(ranges[0])
    count = 0
    for i in range(n):
        if all(
            i < len(ranges[k]) and match_criteria(ranges[k][i], criterias[k])
            for k in range(len(ranges))
        ):
            count += 1
    return count


# ----------------------------------------------------------------------
# averageif
# ----------------------------------------------------------------------

def averageif(range_vals: Any, criteria: Any, average_range: Any = None, key: str = None) -> float:
    """Average values where criteria matches."""
    if key is not None:
        if isinstance(key, tuple):
            crit_key, avg_key = key
        else:
            crit_key = avg_key = key
        nums = []
        src_it = range_vals.values() if type(range_vals) is dict else range_vals
        for r in src_it:
            if type(r) is not dict:
                continue
            if match_criteria(r.get(crit_key), criteria):
                v = r.get(avg_key)
                if type(v) in _NUMERIC_TYPES:
                    nums.append(v)
        return builtins_sum(nums) / len(nums) if nums else 0.0
    rv = _to_list(range_vals)
    av = _to_list(average_range) if average_range is not None else rv
    if len(rv) != len(av):
        from ..errors import FormulaError, ErrorCode
        raise FormulaError("averageif: range và average_range phải cùng độ dài", code=ErrorCode.RANGE_MISMATCH)
    nums = [float(av_val) for val, av_val in zip(rv, av)
            if match_criteria(val, criteria) and type(av_val) in _NUMERIC_TYPES]
    return builtins_sum(nums) / len(nums) if nums else 0.0


# ----------------------------------------------------------------------
# sum_by_type, unique_key_sum_by_type, unique_sum
# ----------------------------------------------------------------------

def sum_by_type(items, type_key: int, value_key: int, target: str, trace_mode=False):
    """Sum values where type column matches target."""
    total = 0.0
    matched = 0
    for it in items:
        if isinstance(it, (list, tuple)) and len(it) > max(type_key, value_key):
            if it[type_key] == target:
                v = it[value_key]
                if isinstance(v, (int, float)):
                    total += v
                    matched += 1
    if trace_mode:
        return total, {"matched": matched, "type": target}
    return total


def unique_key_sum_by_type(items, type_key: int, key_index: int, value_key: int, target: str, trace_mode=False):
    """Sum unique values by type and key."""
    seen_keys = set()
    total = 0.0
    matched = 0
    for row in items:
        if len(row) <= max(type_key, key_index, value_key):
            continue
        if row[type_key] == target:
            ukey = row[key_index]
            if ukey not in seen_keys:
                seen_keys.add(ukey)
                val = row[value_key]
                if isinstance(val, (int, float)):
                    total += val
                    matched += 1
    if trace_mode:
        return total, {"unique_keys": len(seen_keys), "matched": matched}
    return total


def unique_sum(items, key_index: int, value_index: int):
    """Sum unique values based on key."""
    seen = set()
    total = 0.0
    for it in items:
        if isinstance(it, (list, tuple)) and len(it) > max(key_index, value_index):
            key = it[key_index]
            if key not in seen:
                seen.add(key)
                val = it[value_index]
                if isinstance(val, (int, float)):
                    total += val
    return total


# ----------------------------------------------------------------------
# unique, count_unique, flatten
# ----------------------------------------------------------------------

def unique(data: Any, key: str = None) -> List[Any]:
    """Return unique values from iterable."""
    if key is not None:
        src = _extract_key(data, key)
    else:
        src = _to_iter(data)

    seen_hash = set()
    seen_list = []   # fallback for unhashable
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


def count_unique(data: Any, key: str = None) -> int:
    """Return count of unique values."""
    return len(unique(data, key=key))


def flatten(data: Any) -> List[Any]:
    """Recursively flatten nested lists/tuples/dicts."""
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


# ----------------------------------------------------------------------
# group_sum, group_count, group_avg
# ----------------------------------------------------------------------

def group_sum(data: Any, group_key: str, sum_key: str) -> Dict[Any, float]:
    """Group by group_key and sum sum_key."""
    result: Dict[Any, float] = {}
    src = data.values() if isinstance(data, dict) else data
    for r in src:
        if not isinstance(r, dict):
            continue
        gval = r.get(group_key)
        v = r.get(sum_key)
        if gval is None:
            continue
        if isinstance(v, (int, float)):
            result[gval] = result.get(gval, 0.0) + v
    return result


def group_count(data: Any, group_key: str) -> Dict[Any, int]:
    """Count rows by group_key."""
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


def group_avg(data: Any, group_key: str, avg_key: str) -> Dict[Any, float]:
    """Average by group_key."""
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


# ----------------------------------------------------------------------
# rf - row field access with safety and key support
# ----------------------------------------------------------------------
def rf(*args, **kwargs):
    """Lấy giá trị từ row hoặc từ table theo index.
       Cú pháp:
         rf(row, field, default=0)
         rf(table, idx, field, default=0)
    """
    default = kwargs.get('default', 0)
    if len(args) == 2:
        # rf(row, field)
        row, field = args
        try:
            if isinstance(row, dict):
                return row.get(field, default)
            else:
                return getattr(row, field, default)
        except (AttributeError, KeyError, TypeError):
            return default
    elif len(args) >= 3:
        # rf(table, idx, field)
        table, idx, field = args[0], args[1], args[2]
        if len(args) > 3:
            default = args[3]
        try:
            row = table[idx]
            if isinstance(row, dict):
                return row.get(field, default)
            else:
                return getattr(row, field, default)
        except (IndexError, KeyError, AttributeError, TypeError):
            return default
    return default