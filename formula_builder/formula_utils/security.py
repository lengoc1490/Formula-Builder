# formula_utils/security.py
# Security validation for formula AST

import ast
from typing import Set, Iterable, Optional, List, Any, Dict, Tuple
import difflib

from .errors import FormulaError, ErrorCode
from .normalize import normalize_formula
from .types import ValidationResult


class SecurityValidator(ast.NodeVisitor):
    """Security checks: prevent imports, dangerous builtins, deep nesting."""
    
    FORBIDDEN = {
        'Import', 'ImportFrom', 'Exec', 'Eval',
        'FunctionDef', 'AsyncFunctionDef', 'ClassDef',
        'Delete', 'Global', 'Nonlocal', 'Await', 'Yield', 'YieldFrom',
        'Lambda',           # block lambda expressions
        'DictComp',         # block dict comprehensions
        'SetComp',          # block set comprehensions
    }

    # v16: block at AST level regardless of deterministic mode
    FORBIDDEN_NAMES: frozenset = frozenset({
        # stdlib modules
        'random', 'os', 'sys', 'open', 'exec', 'eval', 'compile',
        # introspection builtins
        '__import__', 'globals', 'locals', 'vars', 'dir',
        # dunder attributes used in sandbox escape chains
        '__class__', '__bases__', '__mro__', '__subclasses__',
        '__builtins__', '__globals__', '__code__', '__func__',
        '__self__', '__dict__', '__module__', '__qualname__',
        # other dangerous builtins not in __builtins__={}
        'breakpoint', 'input', 'print', 'help', 'quit', 'exit',
    })
    
    ALLOWED_ATTRS: frozenset = frozenset({
        'get',      # dict.get(key, default) — phổ biến nhất
        'keys',     # dict.keys()
        'values',   # dict.values()
        'items',    # dict.items()
        'to_dict',  # AllocationResult.to_dict() — trả về dict từ result
    })

    def __init__(self, max_depth: int, max_iter_size: int):
        self.max_depth = max_depth
        self.max_iter_size = max_iter_size
        self.current_depth = 0

    def visit(self, node):
        if type(node).__name__ in self.FORBIDDEN:
            raise FormulaError(
                f"Forbidden operation: {type(node).__name__}",
                code=ErrorCode.SECURITY_VIOLATION
            )
        return super().visit(node)

    def visit_Name(self, node):
        if node.id in self.FORBIDDEN_NAMES:
            raise FormulaError(
                f"Forbidden name: '{node.id}' is not allowed in formulas.",
                code=ErrorCode.SECURITY_VIOLATION,
            )
        self.generic_visit(node)

    def visit_Subscript(self, node):
        self.current_depth += 1
        if self.current_depth > self.max_depth:
            raise FormulaError(
                f"Subscript nesting too deep (max {self.max_depth})",
                code=ErrorCode.SUBSCRIPT_TOO_DEEP
            )
        self.generic_visit(node)
        self.current_depth -= 1

    def visit_Attribute(self, node):
        attr = node.attr
        if attr.startswith('__') or attr not in self.ALLOWED_ATTRS:
            raise FormulaError(
                f"Attribute access '.{attr}' is not allowed in formulas. "
                f"Allowed methods: {sorted(self.ALLOWED_ATTRS)}. "
                "Use named functions from the formula library instead.",
                code=ErrorCode.SECURITY_VIOLATION,
            )
        # attr hợp lệ → tiếp tục visit các node con (value/ctx)
        self.generic_visit(node)

    def visit_List(self, node):
        if len(node.elts) > self.max_iter_size:
            raise FormulaError(
                f"Literal list too large ({len(node.elts)} > {self.max_iter_size})",
                code=ErrorCode.LITERAL_LIST_TOO_LARGE
            )
        self.generic_visit(node)


class FormulaValidator:
    """Validate formula string for security and correctness."""
    
    # AST nodes bị cấm tuyệt đối
    _FORBIDDEN_NODES: frozenset = frozenset({
        "Import", "ImportFrom", "Exec", "Eval",
        "FunctionDef", "AsyncFunctionDef", "ClassDef",
        "Delete", "Global", "Nonlocal", "Await", "Yield", "YieldFrom",
        "Lambda",        # lambda: None  ← không bao giờ cần trong formula
        "DictComp",      # {k:v for k,v in d}  ← không hợp lệ
        "SetComp",       # {x for x in lst}  ← không hợp lệ
        "Assign", "AugAssign", "AnnAssign", "NamedExpr",
    })

    # Whitelist attr an toàn — đồng bộ với SecurityValidator.ALLOWED_ATTRS
    _ALLOWED_ATTRS: frozenset = frozenset({
        'get', 'keys', 'values', 'items', 'to_dict',
    })

    # Hàm được phép chứa GeneratorExp làm argument
    _GENEXP_ALLOWED_FUNCS: frozenset = frozenset({
        "sum", "min", "max", "any", "all", "sorted", "list", "tuple",
        "sumif", "countif", "filter_array",
    })

    def __init__(
        self,
        allowed_functions: Iterable[str],
        forbidden_nodes: Optional[frozenset] = None,
    ):
        self._allowed_funcs: frozenset = frozenset(allowed_functions)
        self._forbidden: frozenset = forbidden_nodes if forbidden_nodes is not None else self._FORBIDDEN_NODES
        self._canonical_funcs: frozenset = self._allowed_funcs

    def _check_generator_expr(self, tree: ast.Expression) -> List[str]:
        """Check generator expressions are only allowed in whitelisted functions."""
        errors: List[str] = []

        parent: dict = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parent[id(child)] = node

        for node in ast.walk(tree):
            if not isinstance(node, ast.GeneratorExp):
                continue
            p = parent.get(id(node))
            if p is None:
                errors.append(
                    "Generator expression đứng độc lập không được phép. "
                    "Dùng list comprehension [x for x in lst] hoặc sum(x for x in lst)."
                )
            elif isinstance(p, ast.Call):
                if isinstance(p.func, ast.Name):
                    if p.func.id not in self._GENEXP_ALLOWED_FUNCS:
                        errors.append(
                            f"Generator expression bên trong '{p.func.id}()' không được phép. "
                            f"Chỉ sum/min/max/any/all/sorted/list/tuple được dùng với generator."
                        )
            else:
                errors.append(
                    "Generator expression chỉ được dùng trực tiếp bên trong "
                    "sum(), min(), max(), any(), all() — không dùng trong biểu thức khác."
                )
        return errors

    def validate(
        self,
        formula: str,
        known_names: Optional[Set[str]] = None,
    ) -> ValidationResult:
        errors: List[str] = []
        warnings: List[str] = []

        if not formula or not isinstance(formula, str):
            return ValidationResult(
                ok=False,
                errors=["Công thức không được để trống."],
                warnings=[],
                normalized="",
                formula=str(formula or ""),
            )

        # Normalize
        try:
            normalized = normalize_formula(formula, self._canonical_funcs)
        except Exception as ex:
            return ValidationResult(
                ok=False,
                errors=[f"Lỗi khi chuẩn hóa công thức: {ex}"],
                warnings=[],
                normalized=formula,
                formula=formula,
            )

        # Syntax check
        try:
            tree = ast.parse(normalized, mode="eval")
        except SyntaxError as ex:
            return ValidationResult(
                ok=False,
                errors=[f"Cú pháp không hợp lệ: {ex.msg} (dòng {ex.lineno}, cột {ex.offset})"],
                warnings=[],
                normalized=normalized,
                formula=formula,
            )
        except Exception as ex:
            return ValidationResult(
                ok=False,
                errors=[f"Lỗi phân tích công thức: {ex}"],
                warnings=[],
                normalized=normalized,
                formula=formula,
            )

        # Security: forbidden nodes
        for node in ast.walk(tree):
            node_type = type(node).__name__
            if node_type in self._forbidden:
                label = {
                    "Import": "lệnh import",
                    "ImportFrom": "lệnh import",
                    "Lambda": "hàm lambda ẩn danh",
                    "Assign": "phép gán",
                    "AugAssign": "phép gán cộng dồn (+=, -=, ...)",
                    "AnnAssign": "phép gán có kiểu",
                    "NamedExpr": "phép gán walrus (:=)",
                    "GeneratorExp": "generator expression",
                    "DictComp": "dict comprehension",
                    "SetComp": "set comprehension",
                    "ClassDef": "định nghĩa class",
                    "FunctionDef": "định nghĩa hàm",
                    "Global": "lệnh global",
                    "Nonlocal": "lệnh nonlocal",
                }.get(node_type, f"cấu trúc bị cấm ({node_type})")
                errors.append(f"Không cho phép {label} trong công thức.")

            # Attribute whitelist check
            if node_type == "Attribute":
                attr = node.attr  # type: ignore[attr-defined]
                if attr.startswith('__') or attr not in self._ALLOWED_ATTRS:
                    errors.append(
                        f"Không cho phép truy cập thuộc tính '.{attr}' trong công thức. "
                        f"Thuộc tính được phép: {sorted(self._ALLOWED_ATTRS)}."
                    )

        if errors:
            return ValidationResult(ok=False, errors=errors, warnings=warnings,
                                    normalized=normalized, formula=formula)

        # GeneratorExp context check
        genexp_errors = self._check_generator_expr(tree)
        errors.extend(genexp_errors)
        if errors:
            return ValidationResult(ok=False, errors=errors, warnings=warnings,
                                    normalized=normalized, formula=formula)

        # Function whitelist
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    fname = node.func.id
                    if fname not in self._allowed_funcs:
                        suggestions = difflib.get_close_matches(
                            fname.lower(),
                            [f.lower() for f in self._allowed_funcs],
                            n=3, cutoff=0.6
                        )
                        hint = f" Ý bạn là: {', '.join(suggestions)}?" if suggestions else ""
                        errors.append(
                            f"Hàm '{fname}' không được hỗ trợ.{hint}"
                        )
                elif isinstance(node.func, ast.Attribute):
                    errors.append(
                        "Không cho phép gọi hàm qua thuộc tính (method chaining)."
                    )

        if errors:
            return ValidationResult(ok=False, errors=errors, warnings=warnings,
                                    normalized=normalized, formula=formula)

        # Variable whitelist (optional)
        if known_names is not None:
            _python_keywords = frozenset({
                "True", "False", "None",
                "and", "or", "not", "in", "is",
                "if", "else", "elif",
            })
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    vname = node.id
                    if (vname not in self._allowed_funcs
                            and vname not in _python_keywords
                            and vname not in known_names):
                        suggestions = difflib.get_close_matches(
                            vname.lower(),
                            [n.lower() for n in known_names],
                            n=3, cutoff=0.6
                        )
                        hint = f" Ý bạn là: {', '.join(suggestions)}?" if suggestions else ""
                        errors.append(
                            f"Biến '{vname}' chưa được khai báo.{hint}"
                        )

        if errors:
            return ValidationResult(ok=False, errors=errors, warnings=warnings,
                                    normalized=normalized, formula=formula)

        # Warnings
        all_names_used = {
            n.id for n in ast.walk(tree)
            if isinstance(n, ast.Name) and n.id not in self._allowed_funcs
        }
        if not all_names_used:
            warnings.append(
                "Công thức không sử dụng bất kỳ biến nào — kết quả sẽ là hằng số."
            )

        for node in ast.walk(tree):
            if isinstance(node, ast.IfExp):
                if node.orelse is None:
                    warnings.append(
                        "IF thiếu nhánh else — có thể trả về None không mong muốn."
                    )

        return ValidationResult(
            ok=True,
            errors=[],
            warnings=warnings,
            normalized=normalized,
            formula=formula,
        )

    def validate_batch(
        self,
        formulas: Dict[str, str],
        known_names: Optional[Set[str]] = None,
    ) -> Dict[str, ValidationResult]:
        all_formula_names = set(formulas.keys())
        results: Dict[str, ValidationResult] = {}

        for name, formula in formulas.items():
            scope = (known_names or set()) | (all_formula_names - {name})
            results[name] = self.validate(formula, known_names=scope if known_names is not None else None)

        return results