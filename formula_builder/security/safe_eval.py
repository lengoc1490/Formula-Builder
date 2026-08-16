# formula_builder/security/safe_eval.py
# Safe evaluation wrapper cho Formula Builder
# ═══════════════════════════════════════════════════════════════════════════
# Pivot RCE (2026-08-16): Formula Builder có eval lỏng → fix ĐƯA VÀO FB.
#
# Chiến lược (giữ flexibility + performance):
#   1. VALIDATE 1 LẦN lúc build/compile — tái sử dụng SecurityValidator /
#      FormulaValidator có sẵn (formula_utils/security.py), KHÔNG viết validator
#      mới trùng. Cho phép 80+ hàm BASE_FUNCS, row.attr, conditional, backward-compat.
#   2. EVAL NHANH hot loop trên compiled code object đã qua validate —
#      KHÔNG AST-interpreter node-by-node (chậm), KHÔNG validate lại mỗi lần eval.
#   3. Security contract: eval(code, {"__builtins__": {}}, scope) — globals rỗng
#      → KHÔNG có builtin thật. Mọi name/function phải đến từ scope (locals) do
#      caller đưa vào. Biểu thức đã validate không thể import/eval/exec/lambda/
#      class/def/assign, không truy cập dunder attr, chỉ gọi hàm trong
#      allowed_functions (nếu được chỉ định).
# ═══════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import ast
import threading
from typing import Any, Dict, FrozenSet, Iterable, Optional, Tuple

from formula_builder.formula_utils.errors import FormulaError
from formula_builder.formula_utils.security import SecurityValidator

# ── AST node types bị cấm tuyệt đối ─────────────────────────────────────────
# Đồng bộ với SecurityValidator.FORBIDDEN + FormulaValidator._FORBIDDEN_NODES.
_FORBIDDEN_NODE_TYPES: FrozenSet[str] = frozenset({
    "Import", "ImportFrom", "Exec", "Eval",
    "FunctionDef", "AsyncFunctionDef", "ClassDef",
    "Delete", "Global", "Nonlocal", "Await", "Yield", "YieldFrom",
    "Lambda", "DictComp", "SetComp",
    "Assign", "AugAssign", "AnnAssign", "NamedExpr",
})

# ── Tên bị cấm tuyệt đối ────────────────────────────────────────────────────
# Tái sử dụng danh sách từ SecurityValidator + bổ sung getattr/setattr/delattr
# (attribute traversal qua getattr là vector sandbox-escape phổ biến).
_FORBIDDEN_NAMES: FrozenSet[str] = (
    SecurityValidator.FORBIDDEN_NAMES
    | frozenset({"getattr", "setattr", "delattr"})
)


# ── Policy ───────────────────────────────────────────────────────────────────

class ExpressionPolicy:
    """Chính sách bảo mật cho một biểu thức an toàn.

    Attributes:
        allow_attribute:     cho phép truy cập obj.attr (vd row.qty).
        allowed_attributes:  nếu set → chỉ cho phép các attr trong set này;
                             nếu None → cho phép mọi attr KHÔNG bắt đầu bằng "__".
        forbid_subscript:    chặn subscript obj[...] (vd row['qty']).
        forbid_method_calls: chặn gọi hàm qua thuộc tính obj.method().
        allowed_functions:   whitelist tên hàm được gọi; None = không giới hạn
                             (CHỈ dùng khi scope không chứa object nguy hiểm).
        forbidden_names:     set tên bị cấm bổ sung (mặc định: toàn bộ _FORBIDDEN_NAMES).
        max_subscript_depth: giới hạn độ sâu subscript lồng nhau.
        max_iter_size:       giới hạn list/set/tuple literal.
    """

    __slots__ = (
        "allow_attribute", "allowed_attributes", "forbid_subscript",
        "forbid_method_calls", "allowed_functions", "forbidden_names",
        "max_subscript_depth", "max_iter_size",
    )

    def __init__(
        self,
        *,
        allow_attribute: bool = True,
        allowed_attributes: Optional[Iterable[str]] = None,
        forbid_subscript: bool = False,
        forbid_method_calls: bool = True,
        allowed_functions: Optional[Iterable[str]] = None,
        forbidden_names: Optional[Iterable[str]] = None,
        max_subscript_depth: int = 5,
        max_iter_size: int = 2 ** 31,
    ):
        self.allow_attribute = allow_attribute
        self.allowed_attributes: Optional[FrozenSet[str]] = (
            frozenset(allowed_attributes) if allowed_attributes is not None else None
        )
        self.forbid_subscript = forbid_subscript
        self.forbid_method_calls = forbid_method_calls
        self.allowed_functions: Optional[FrozenSet[str]] = (
            frozenset(allowed_functions) if allowed_functions is not None else None
        )
        self.forbidden_names: FrozenSet[str] = (
            frozenset(forbidden_names) if forbidden_names is not None else _FORBIDDEN_NAMES
        )
        self.max_subscript_depth = max_subscript_depth
        self.max_iter_size = max_iter_size

    def signature(self) -> Tuple:
        """Cache-key signature — mọi tham số ảnh hưởng tới kết quả validate."""
        return (
            self.allow_attribute,
            tuple(sorted(self.allowed_attributes)) if self.allowed_attributes else None,
            self.forbid_subscript,
            self.forbid_method_calls,
            tuple(sorted(self.allowed_functions)) if self.allowed_functions else None,
            tuple(sorted(self.forbidden_names)),
            self.max_subscript_depth,
            self.max_iter_size,
        )


# ── Policy mặc định cho 3 nhóm eval user-controlled ─────────────────────────

# Biểu thức thông thường (condition / transform): cho phép attr đọc + subscript
# (data dạng dict/list), chặn method call + import + lambda + gán.
DEFAULT_POLICY = ExpressionPolicy()

# filter_expr (child_table_aggregate): subscript bị chặn (dùng row.field thay thế),
# mọi attr non-dunder được phép (row.qty, row.rate...).
FILTER_POLICY = ExpressionPolicy(forbid_subscript=True)

# condition (conditional branches): subscript được phép (resolved_so_far dạng dict/list).
CONDITION_POLICY = ExpressionPolicy()

# transform formula (batch_binding_resolver): arithmetic + attr đọc, subscript được phép.
TRANSFORM_POLICY = ExpressionPolicy()


# ── SafeExpression ────────────────────────────────────────────────────────────

class SafeExpression:
    """Biểu thức đã validate + compile 1 lần — eval nhanh trong hot loop.

    KHÔNG validate lại mỗi lần eval (giữ performance).
    Immutable → thread-safe khi dùng chung nhiều request/thread.
    """

    __slots__ = ("_code", "_source")

    def __init__(self, code: Any, source: str):
        self._code = code
        self._source = source

    @property
    def source(self) -> str:
        """Biểu thức gốc (đã strip) đã được validate + compile."""
        return self._source

    def eval(self, scope: Dict[str, Any]) -> Any:
        """Eval nhanh trên compiled code.

        Args:
            scope: dict biến/func cho biểu thức — caller CHỦ ĐỘNG đưa vào.
                   Globals cố định {"__builtins__": {}} → không có builtin thật.

        Returns:
            Giá trị biểu thức.
        """
        return eval(self._code, {"__builtins__": {}}, scope)


# ── AST validation ───────────────────────────────────────────────────────────

def _subscript_depth(node: ast.Subscript) -> int:
    """Đếm độ sâu chuỗi subscript lồng nhau (a[1][2][3] → 3)."""
    depth = 1
    value = node.value
    while isinstance(value, ast.Subscript):
        depth += 1
        value = value.value
    return depth


def _validate_ast(tree: ast.AST, policy: ExpressionPolicy) -> None:
    """Walk AST — kiểm tra cấu trúc nguy hiểm theo policy.

    Raises:
        ValueError: nếu phát hiện node/name/attr/call/subscript không cho phép.
    """
    for node in ast.walk(tree):
        node_type = type(node).__name__

        # ── Node type cấm tuyệt đối ──
        if node_type in _FORBIDDEN_NODE_TYPES:
            raise ValueError(f"Forbidden operation: {node_type}")

        if isinstance(node, ast.Name):
            if node.id in policy.forbidden_names:
                raise ValueError(f"Forbidden name: '{node.id}'")

        elif isinstance(node, ast.Attribute):
            attr = node.attr
            if attr.startswith("__"):
                raise ValueError(f"Dunder attribute '.{attr}' is not allowed")
            if policy.allow_attribute and policy.allowed_attributes is not None:
                if attr not in policy.allowed_attributes:
                    raise ValueError(f"Attribute '.{attr}' is not allowed")
            elif not policy.allow_attribute:
                raise ValueError(f"Attribute access '.{attr}' is not allowed")

        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if policy.forbid_method_calls:
                    raise ValueError("Method calls (obj.method()) are not allowed")
            elif isinstance(func, ast.Name):
                fname = func.id
                if policy.allowed_functions is not None and fname not in policy.allowed_functions:
                    raise ValueError(f"Function '{fname}()' is not allowed")
            else:
                # Call qua subscript/lambda/... — phức tạp, chặn.
                raise ValueError("Complex call expressions are not allowed")

        elif isinstance(node, ast.Subscript):
            if policy.forbid_subscript:
                raise ValueError("Subscript access (obj[...]) is not allowed")
            depth = _subscript_depth(node)
            if depth > policy.max_subscript_depth:
                raise ValueError(
                    f"Subscript nesting too deep (max {policy.max_subscript_depth})"
                )

        elif isinstance(node, (ast.List, ast.Set, ast.Tuple)):
            if len(node.elts) > policy.max_iter_size:
                raise ValueError(
                    f"Literal too large ({len(node.elts)} > {policy.max_iter_size})"
                )


# ── Compile cache (validate 1 lần, reuse nhiều binding) ─────────────────────

_CACHE_MAX = 2048
_COMPILED_CACHE: Dict[Tuple, SafeExpression] = {}
_CACHE_LOCK = threading.Lock()


def _cache_key(
    expr: str,
    policy: ExpressionPolicy,
) -> Tuple:
    return (
        expr,
        policy.signature(),
    )


def clear_cache() -> None:
    """Xóa cache compiled expressions — gọi khi Formula Builder Settings thay đổi."""
    with _CACHE_LOCK:
        _COMPILED_CACHE.clear()


def _cache_get(key: Tuple) -> Optional[SafeExpression]:
    with _CACHE_LOCK:
        return _COMPILED_CACHE.get(key)


def _cache_set(key: Tuple, expr: SafeExpression) -> None:
    with _CACHE_LOCK:
        if len(_COMPILED_CACHE) >= _CACHE_MAX:
            _COMPILED_CACHE.pop(next(iter(_COMPILED_CACHE)))
        _COMPILED_CACHE[key] = expr


# ── Public API ───────────────────────────────────────────────────────────────

def compile_expression(
    expr: str,
    *,
    allowed_functions: Optional[Iterable[str]] = None,
    policy: Optional[ExpressionPolicy] = None,
    filename: str = "<safe_expr>",
    use_cache: bool = True,
) -> SafeExpression:
    """Validate + compile một biểu thức an toàn (1 lần lúc build).

    Args:
        expr: chuỗi biểu thức (Python expression) — user-controlled.
        allowed_functions: whitelist tên hàm được gọi. None = không giới hạn
            (CHỈ dùng khi scope không chứa object nguy hiểm — khuyến nghị luôn truyền).
        policy: cấu trúc cho phép (attr/subscript/method-call/names/depth).
            Mặc định DEFAULT_POLICY.
        filename: tên hiển thị trong traceback.
        use_cache: cache compiled expression theo (expr, policy).
            Hit → trả về ngay, miss → validate + compile + lưu cache.

    Returns:
        SafeExpression — gọi .eval(scope) trong hot loop.

    Raises:
        ValueError: nếu biểu thức không hợp lệ hoặc chứa cấu trúc nguy hiểm.
    """
    if expr is None:
        raise ValueError("Expression cannot be None")
    expr = expr.strip()
    if not expr:
        raise ValueError("Expression cannot be empty")

    pol = policy if policy is not None else DEFAULT_POLICY
    if allowed_functions is not None and pol.allowed_functions != frozenset(allowed_functions):
        # Bản sao policy với allowed_functions riêng (không mutate policy chung).
        pol = ExpressionPolicy(
            allow_attribute=pol.allow_attribute,
            allowed_attributes=pol.allowed_attributes,
            forbid_subscript=pol.forbid_subscript,
            forbid_method_calls=pol.forbid_method_calls,
            allowed_functions=allowed_functions,
            forbidden_names=pol.forbidden_names,
            max_subscript_depth=pol.max_subscript_depth,
            max_iter_size=pol.max_iter_size,
        )

    if use_cache:
        key = _cache_key(expr, pol)
        cached = _cache_get(key)
        if cached is not None:
            return cached

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Expression syntax error: {e.msg}") from e

    _validate_ast(tree, pol)

    code = compile(tree, filename=filename, mode="eval")
    result = SafeExpression(code, expr)

    if use_cache:
        _cache_set(key, result)
    return result


def validate_expression(
    expr: str,
    *,
    allowed_functions: Optional[Iterable[str]] = None,
    policy: Optional[ExpressionPolicy] = None,
) -> None:
    """Validate biểu thức an toàn (không compile) — dùng cho UI validation.

    Raises:
        ValueError: nếu biểu thức không hợp lệ.
    """
    compile_expression(
        expr,
        allowed_functions=allowed_functions,
        policy=policy,
        use_cache=False,
    )


def validate_formula_sources(
    expressions: Dict[str, str],
    *,
    runtime_env: Optional[Dict[str, Any]] = None,
    max_subscript_depth: int = 5,
    max_iter_size: int = 2 ** 31,
) -> None:
    """Gate validate cho cache-restore: re-validate formula SOURCE khi engine
    được khôi phục từ serialized cache (bytecodes KHÔNG được tin mù).

    Dùng FormulaParser.parse() — chính là gate mà __init__/register_formula
    dùng (normalize + IfCallRewriter + DotToSubscriptTransformer + SecurityValidator
    + genexp + function whitelist). Đảm bảo compiled bytecode từ cache không thể
    bypass validation.

    Raises:
        FormulaError / ValueError: nếu bất kỳ formula source nào không qua validate.
    """
    from formula_builder.formula_utils.parser import FormulaParser

    env = runtime_env if runtime_env is not None else {}
    parser = FormulaParser(env, max_subscript_depth, max_iter_size)
    for name, expr in expressions.items():
        parser.parse(expr)  # SecurityValidator + func whitelist
