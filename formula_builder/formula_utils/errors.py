# formula_utils/errors.py
# Error classes and error codes for Formula Engine

from typing import Dict, List, Optional, Any, Type
from enum import Enum


class ErrorCode(Enum):
    CIRCULAR_DEPENDENCY          = "ENGINE.CIRCULAR_DEPENDENCY"
    INVALID_TYPE                 = "ENGINE.INVALID_TYPE"
    ASSERT_VIOLATION             = "ENGINE.ASSERT_VIOLATION"
    SYNTAX_ERROR                 = "ENGINE.SYNTAX_ERROR"
    SECURITY_VIOLATION           = "ENGINE.SECURITY_VIOLATION"
    MISSING_REQUIRED_INPUT       = "ENGINE.MISSING_REQUIRED_INPUT"
    TYPE_MISMATCH                = "ENGINE.TYPE_MISMATCH"
    RANGE_MISMATCH               = "ENGINE.RANGE_MISMATCH"
    INVALID_ARGUMENT_COUNT       = "ENGINE.INVALID_ARGUMENT_COUNT"
    INDEX_OUT_OF_RANGE           = "ENGINE.INDEX_OUT_OF_RANGE"
    DIVISION_BY_ZERO             = "ENGINE.DIVISION_BY_ZERO"
    ITERABLE_TOO_LARGE           = "ENGINE.ITERABLE_TOO_LARGE"
    SUBSCRIPT_TOO_DEEP           = "ENGINE.SUBSCRIPT_TOO_DEEP"
    LITERAL_LIST_TOO_LARGE       = "ENGINE.LITERAL_LIST_TOO_LARGE"
    NON_DETERMINISTIC_IN_FROZEN  = "ENGINE.NON_DETERMINISTIC_IN_FROZEN"
    SCHEMA_VIOLATION             = "ENGINE.SCHEMA_VIOLATION"
    UNKNOWN_FUNCTION             = "ENGINE.UNKNOWN_FUNCTION"
    UNSUPPORTED_NODE             = "ENGINE.UNSUPPORTED_NODE"
    CIRCULAR_REFERENCE_IN_TRACE  = "ENGINE.CIRCULAR_REFERENCE_IN_TRACE"
    AUDIT_SESSION_NOT_ACTIVE     = "ENGINE.AUDIT_SESSION_NOT_ACTIVE"
    TARGET_OUTPUT_NOT_FOUND      = "ENGINE.TARGET_OUTPUT_NOT_FOUND"
    INVALID_GROUP_NAME           = "ENGINE.INVALID_GROUP_NAME"
    INVALID_ROUNDING_POLICY      = "ENGINE.INVALID_ROUNDING_POLICY"
    UNKNOWN                      = "ENGINE.UNKNOWN"
    VALIDATION_ERROR             = "ENGINE.VALIDATION_ERROR"  # v14 FormulaValidator
    # v11 - Lazy evaluation
    CONTEXT_NOT_INITIALIZED      = "ENGINE.CONTEXT_NOT_INITIALIZED"
    STALE_CONTEXT                = "ENGINE.STALE_CONTEXT"


class FormulaError(ValueError):
    def __init__(
        self,
        message: str = "",
        code: ErrorCode = None,
        level: str = "ERROR",
        field_name: Optional[str] = None,
        formula: Optional[str] = None,
        error: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.field_name = field_name
        self.formula = formula
        self.error = error
        self.context = context or {}
        self.code = code.value if code else ErrorCode.UNKNOWN.value
        self.level = level
        super().__init__(message)

    def __str__(self):
        import difflib
        lines = [f"[{self.code}] {self.level}: {self.args[0]}" if self.args and self.args[0] else ""]
        if self.field_name:
            lines.append(f"Error in field '{self.field_name}':")
        if self.formula:
            lines.append(f" Formula: {self.formula}")
        if self.error:
            lines.append(f" Underlying error: {str(self.error)}")
        if self.context:
            available_vars = list(self.context.keys())
            lines.append(f" Available variables: {', '.join(available_vars[:10])}{' ...' if len(available_vars) > 10 else ''}")
            if self.error and hasattr(self.error, 'args') and self.error.args:
                suspect = str(self.error.args[0]).lower()
                suggestions = difflib.get_close_matches(
                    suspect,
                    [v.lower() for v in available_vars],
                    n=3,
                    cutoff=0.6
                )
                if suggestions:
                    lines.append(f" Did you mean: {', '.join(suggestions)}?")
        return "\n".join(lines) if lines else "Unknown formula error"


class SchemaError(FormulaError):
    pass


class FormulaBudgetExceeded(FormulaError):
    def __init__(self, message: str = "Operation budget exceeded", ops: int = 0, limit: int = 0):
        self.ops = ops
        self.limit = limit
        super().__init__(message, code=ErrorCode.UNKNOWN, level="FATAL")
        self.code = "ENGINE.BUDGET_EXCEEDED"

    def __str__(self):
        return f"[ENGINE.BUDGET_EXCEEDED] FATAL: {self.args[0]} (ops={self.ops}, limit={self.limit})"


class FormulaComplexityError(FormulaError):
    def __init__(self, message: str, metric: str = "", value: int = 0, limit: int = 0):
        self.metric = metric
        self.value = value
        self.limit = limit
        super().__init__(message, code=ErrorCode.UNKNOWN, level="ERROR")
        self.code = "ENGINE.COMPLEXITY_ERROR"

    def __str__(self):
        extra = f" ({self.metric}={self.value}, limit={self.limit})" if self.metric else ""
        return f"[ENGINE.COMPLEXITY_ERROR] ERROR: {self.args[0]}{extra}"


class FormulaLimitError(FormulaError):
    def __init__(self, message: str, size: int = 0, limit: int = 0):
        self.size = size
        self.limit = limit
        super().__init__(message, code=ErrorCode.ITERABLE_TOO_LARGE, level="ERROR")
        self.code = "ENGINE.LIMIT_EXCEEDED"

    def __str__(self):
        extra = f" (size={self.size}, limit={self.limit})" if self.size else ""
        return f"[ENGINE.LIMIT_EXCEEDED] ERROR: {self.args[0]}{extra}"


class FormulaRuntimeError(FormulaError):
    def __init__(self, message: str, field_name: str = None, formula: str = None, error: Exception = None):
        super().__init__(message, code=ErrorCode.UNKNOWN, level="ERROR",
                         field_name=field_name, formula=formula, error=error)
        self.code = "ENGINE.RUNTIME_ERROR"


class FormulaValidationError(FormulaError):
    def __init__(self, message: str, errors: List[str] = None):
        self.validation_errors = errors or []
        super().__init__(message, code=ErrorCode.VALIDATION_ERROR, level="ERROR")
        self.code = "ENGINE.VALIDATION_ERROR"

    def __str__(self):
        base = f"[ENGINE.VALIDATION_ERROR] ERROR: {self.args[0]}"
        if self.validation_errors:
            details = "\n  ".join(self.validation_errors)
            return f"{base}\n  {details}"
        return base


class FormulaDeterministicError(FormulaError):
    """Raised when a non-deterministic function is called in deterministic mode."""
    def __init__(self, func_name: str):
        self.func_name = func_name
        super().__init__(
            f"Function '{func_name}' is non-deterministic and not allowed in deterministic mode. "
            f"Set deterministic=False to enable time/random functions.",
            code=ErrorCode.NON_DETERMINISTIC_IN_FROZEN,
            level="ERROR",
        )
        self.code = "ENGINE.DETERMINISTIC_VIOLATION"


class FormulaAssertionError(FormulaError):
    def __init__(self, message: str, violations: List['AssertionViolation']):
        self.violations = violations
        super().__init__(message, code=ErrorCode.ASSERT_VIOLATION)

    def __str__(self):
        lines = [f"Assertion violation(s) detected: {super().__str__()}"]
        for v in self.violations:
            lines.append(f" • {v.severity.value} - {v.assertion_name}: {v.message}")
            if v.context:
                lines.append(f" Context (sample): {{... {len(v.context)} vars ...}}")
        return "\n".join(lines)


# ── Map error class → machine-readable slug ────────────────────────────────

_ERROR_TYPE_MAP: Dict[type, str] = {
    FormulaBudgetExceeded:    "budget_exceeded",
    FormulaComplexityError:   "complexity_error",
    FormulaLimitError:        "limit_exceeded",
    FormulaRuntimeError:      "runtime_error",
    FormulaValidationError:   "validation_error",
    FormulaDeterministicError:"deterministic_violation",
    FormulaError:             "formula_error",
    SchemaError:              "schema_error",
}

def _error_type_slug(exc: Exception) -> str:
    """Return machine-readable slug for an exception."""
    for cls in type(exc).__mro__:
        if cls in _ERROR_TYPE_MAP:
            return _ERROR_TYPE_MAP[cls]
    return "unknown_error"


# Avoid circular import for AssertionViolation
from .types import AssertionViolation
FormulaAssertionError.__annotations__['violations'] = List[AssertionViolation]