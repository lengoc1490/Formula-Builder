# formula_utils/funcs/logic.py
# Logical and conditional functions for formula engine

from typing import Any


# ----------------------------------------------------------------------
# Basic logical operators
# ----------------------------------------------------------------------

def and_(*args) -> bool:
    """Logical AND of all arguments."""
    return all(args)


def or_(*args) -> bool:
    """Logical OR of all arguments."""
    return any(args)


def not_(x: Any) -> bool:
    """Logical NOT."""
    return not x


# ----------------------------------------------------------------------
# Conditional functions
# ----------------------------------------------------------------------

def IF(cond: Any, true_val: Any, false_val: Any) -> Any:
    """Excel-style IF: return true_val if cond else false_val."""
    return true_val if cond else false_val


def IIF(condition: Any, true_val: Any, false_val: Any) -> Any:
    """Alias for IF."""
    return true_val if condition else false_val


def IFS(*args) -> Any:
    """
    Excel-style IFS: evaluate pairs (condition, value).
    Returns value for first true condition.
    """
    if len(args) % 2 != 0:
        from ..errors import FormulaError, ErrorCode
        raise FormulaError("IFS requires even number of arguments", code=ErrorCode.INVALID_ARGUMENT_COUNT)
    for i in range(0, len(args), 2):
        if args[i]:
            return args[i+1]
    return None


def SWITCH(expr: Any, *args) -> Any:
    """
    Excel-style SWITCH: match expression against value/result pairs.
    Optional default value as last argument if odd number of args.
    """
    if len(args) < 2:
        from ..errors import FormulaError, ErrorCode
        raise FormulaError("SWITCH requires at least value and result", code=ErrorCode.INVALID_ARGUMENT_COUNT)
    for i in range(0, len(args)-1, 2):
        if expr == args[i]:
            return args[i+1]
    if len(args) % 2 == 1:
        return args[-1]
    return None


ifs = IFS  # Alias for backward compatibility
switch = SWITCH  # Alias for backward compatibility
iif = IIF  # Alias for backward compatibility 
# ----------------------------------------------------------------------
# Utility functions
# ----------------------------------------------------------------------

def coalesce(*args) -> Any:
    """Return first non-None non-empty string argument."""
    for arg in args:
        if arg is not None and arg != "":
            return arg
    return None


def is_blank(x: Any) -> bool:
    """Check if value is None, empty string, zero, or zero float."""
    return x is None or x == "" or x == 0 or x == 0.0


def not_blank(x: Any) -> bool:
    """Opposite of is_blank."""
    return not is_blank(x)