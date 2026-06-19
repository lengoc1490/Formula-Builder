# formula_utils/funcs/math.py
# Math functions and numeric utilities for formula engine

import math
import sys
from typing import Any, List, Dict, Union, Iterable
from decimal import Decimal

# ----------------------------------------------------------------------
# Numeric type detection
# ----------------------------------------------------------------------

_NUMERIC_TYPES: frozenset = frozenset({int, float})
try:
    from decimal import Decimal as _Decimal
    _NUMERIC_TYPES = frozenset({int, float, _Decimal})
except ImportError:
    pass

# ----------------------------------------------------------------------
# Built-in references (preserved for internal use)
# ----------------------------------------------------------------------

builtins_sum = sum
builtins_min = min
builtins_max = max


# ----------------------------------------------------------------------
# Iterable helpers
# ----------------------------------------------------------------------

def _to_iter(data: Any):
    """Convert input to iterable without copying."""
    if isinstance(data, (list, tuple, set)):
        return data
    if isinstance(data, dict):
        return data.values()
    if hasattr(data, '__next__') or (hasattr(data, '__iter__') and not isinstance(data, (str, bytes))):
        return data
    return (data,)


def _to_list(data: Any) -> List[Any]:
    """Convert input to list (copy if necessary)."""
    td = type(data)
    if td is list:
        return data
    if td is tuple:
        return list(data)
    if td is set:
        return list(data)
    if td is dict:
        return list(data.values())
    if hasattr(data, '__next__') or (hasattr(data, '__iter__') and not isinstance(data, (str, bytes))):
        return list(data)
    return [data]


def _extract_key(data: Any, key: str):
    """Extract values by key from dict of dicts or list of dicts."""
    if isinstance(data, dict):
        src = data.values()
    else:
        src = data
    return (r.get(key) for r in src if isinstance(r, dict))


# ----------------------------------------------------------------------
# Safe min/max
# ----------------------------------------------------------------------

def _minmax_collect(value, key):
    """Collect numeric values from various structures."""
    if type(value) in _NUMERIC_TYPES:
        return [value]
    if type(value) is dict:
        if key is not None:
            v = value.get(key)
            return [v] if type(v) in _NUMERIC_TYPES else []
        return [v for v in value.values() if type(v) in _NUMERIC_TYPES]
    if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
        if key is not None:
            return [item.get(key) for item in value
                    if type(item) is dict and type(item.get(key)) in _NUMERIC_TYPES]
        return [x for x in value if type(x) in _NUMERIC_TYPES]
    return []


def _safe_min(*args, **kwargs) -> Any:
    """Safe min that handles iterables and key extraction."""
    key = kwargs.get('key')
    n = len(args)
    if key is None:
        if n == 2:
            a, b = args
            if type(a) in _NUMERIC_TYPES and type(b) in _NUMERIC_TYPES:
                return a if a <= b else b
        elif n == 1:
            v = args[0]
            if type(v) in _NUMERIC_TYPES:
                return v
        elif n == 0:
            return 0.0
        elif all(type(a) in _NUMERIC_TYPES for a in args):
            return builtins_min(args)
    if n == 0:
        return 0.0
    if n == 1:
        nums = _minmax_collect(args[0], key)
    else:
        nums = []
        for arg in args:
            nums.extend(_minmax_collect(arg, key))
    return builtins_min(nums) if nums else 0.0


def _safe_max(*args, **kwargs) -> Any:
    """Safe max that handles iterables and key extraction."""
    key = kwargs.get('key')
    n = len(args)
    if key is None:
        if n == 2:
            a, b = args
            if type(a) in _NUMERIC_TYPES and type(b) in _NUMERIC_TYPES:
                return a if a >= b else b
        elif n == 1:
            v = args[0]
            if type(v) in _NUMERIC_TYPES:
                return v
        elif n == 0:
            return 0.0
        elif all(type(a) in _NUMERIC_TYPES for a in args):
            return builtins_max(args)
    if n == 0:
        return 0.0
    if n == 1:
        nums = _minmax_collect(args[0], key)
    else:
        nums = []
        for arg in args:
            nums.extend(_minmax_collect(arg, key))
    return builtins_max(nums) if nums else 0.0


# ----------------------------------------------------------------------
# Safe sum
# ----------------------------------------------------------------------

def _safe_sum(*args, **kwargs):
    """Safe sum that filters non-numeric values and supports key extraction."""
    key = kwargs.get('key')
    if len(args) == 1:
        a = args[0]
        if key is not None:
            return builtins_sum(float(v) for v in _extract_key(a, key) if type(v) in _NUMERIC_TYPES)
        if hasattr(a, '__next__') or (hasattr(a, '__iter__') and not isinstance(a, (str, bytes))):
            return builtins_sum(x for x in a if type(x) in _NUMERIC_TYPES)
        if type(a) in _NUMERIC_TYPES:
            return a
        if type(a) is dict:
            return builtins_sum(v for v in a.values() if type(v) in _NUMERIC_TYPES)
        return builtins_sum(x for x in a if type(x) in _NUMERIC_TYPES)
    else:
        nums = []
        for a in args:
            if type(a) in _NUMERIC_TYPES:
                nums.append(a)
            elif type(a) is dict:
                nums.extend(v for v in a.values() if type(v) in _NUMERIC_TYPES)
            elif hasattr(a, '__iter__') and not isinstance(a, (str, bytes)):
                nums.extend(x for x in a if type(x) in _NUMERIC_TYPES)
        return builtins_sum(nums)


# ----------------------------------------------------------------------
# Basic math functions
# ----------------------------------------------------------------------

# abs, round, etc. are built-in, but we need to expose them
# roundup and rounddown are custom
def roundup(x: float, d: int = 0) -> float:
    """Round up (ceiling) to d decimal places."""
    return math.ceil(x * (10 ** d)) / (10 ** d)


def rounddown(x: float, d: int = 0) -> float:
    """Round down (floor) to d decimal places."""
    return math.floor(x * (10 ** d)) / (10 ** d)


# math module functions (safe whitelist)
floor = math.floor
ceil = math.ceil
power = math.pow
sqrt = math.sqrt
ln = math.log
log10 = math.log10
pi = math.pi
sin = math.sin
cos = math.cos
tan = math.tan
asin = math.asin
acos = math.acos
atan = math.atan
atan2 = math.atan2
degrees = math.degrees
radians = math.radians
exp = math.exp
log = math.log
abs = abs
round = round

# Basic builtins
len = len
length = len
zip = lambda *args: list(zip(*args))  # eagerly materialized

# Type conversions
int = int
float = float
str = str
bool = bool


# ----------------------------------------------------------------------
# Utility math functions
# ----------------------------------------------------------------------

def safe_div(a: Any, b: Any, default: float = 0.0) -> float:
    """Safe division with default for divide-by-zero."""
    try:
        return a / b
    except (ZeroDivisionError, TypeError):
        return default


def percent_of(part: Any, total: Any, default: float = 0.0) -> float:
    """Calculate part/total * 100."""
    try:
        return float(part) / float(total) * 100
    except (ZeroDivisionError, TypeError, ValueError):
        return default


def clamp(x: Any, lo: Any, hi: Any) -> Any:
    """Clamp x between lo and hi."""
    try:
        if x < lo:
            return lo
        if x > hi:
            return hi
        return x
    except TypeError:
        return x


def isnumber(x: Any) -> bool:
    """Check if x is numeric (int, float, Decimal)."""
    return type(x) in _NUMERIC_TYPES


def to_number(x: Any, default: float = 0.0) -> float:
    """Convert x to float, stripping non-numeric characters."""
    if x is None:
        return default
    if isinstance(x, bool):
        return float(x)
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    # Remove non-numeric characters except dot and minus
    import re
    s = re.sub(r'[^\d.\-]', '', s)
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def between(x: Any, lo: Any, hi: Any) -> bool:
    """Check if lo <= x <= hi."""
    try:
        return lo <= x <= hi
    except TypeError:
        return False