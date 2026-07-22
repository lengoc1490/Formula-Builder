# formula_utils/parser.py
# Formula parsing and AST transformation

import ast
import re
import sys
from typing import Dict, Any, Optional, Set

from .errors import FormulaError, ErrorCode
from .security import SecurityValidator
from .normalize import normalize_formula


class DotToSubscriptTransformer(ast.NodeTransformer):
    ALLOWED_ATTRS = frozenset({'get', 'keys', 'values', 'items', 'to_dict'})

    def visit_Attribute(self, node):
        # Nếu attr nằm trong danh sách cho phép, giữ nguyên
        if node.attr in self.ALLOWED_ATTRS:
            return self.generic_visit(node)

        # Python version compatibility
        if sys.version_info >= (3, 9):
            slice_node = ast.Constant(value=node.attr)
        else:
            slice_node = ast.Index(value=ast.Constant(value=node.attr))

        new_node = ast.Subscript(
            value=self.visit(node.value),
            slice=slice_node,
            ctx=ast.Load()
        )

        return ast.copy_location(new_node, node)

    
class IfCallRewriter(ast.NodeTransformer):
    """Rewrite IF(cond, true, false) to (true if cond else false)"""

    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == "IF":
            if len(node.args) == 3:
                return ast.IfExp(
                    test=node.args[0],
                    body=node.args[1],
                    orelse=node.args[2]
                )
        return node


class FormulaParser:
    """Parse and compile formulas with security checks"""

    # Functions allowed to contain GeneratorExp (must match FormulaValidator._GENEXP_ALLOWED_FUNCS)
    _GENEXP_ALLOWED: frozenset = frozenset({
        "sum", "min", "max", "any", "all", "sorted", "list", "tuple",
        "sumif", "countif", "filter_array", "count_unique"
    })

    def __init__(self, runtime_env: Dict, max_subscript_depth: int, max_iterable_size: int):
        self.runtime_env = runtime_env
        self.max_subscript_depth = max_subscript_depth
        self.max_iterable_size = max_iterable_size
        # Build canonical_funcs frozenset 1 lần → dùng trong mọi parse() call
        self._canonical_funcs: frozenset = frozenset(runtime_env.keys())

    def parse(self, formula: str) -> ast.Expression:
        """Parse formula string to AST"""
        formula = normalize_formula(formula, self._canonical_funcs)

        try:
            tree = ast.parse(formula, mode='eval')
        except SyntaxError as e:
            raise FormulaError(f"Syntax error: {e}", code=ErrorCode.SYNTAX_ERROR, error=e)

        # Transform IF calls
        tree = IfCallRewriter().visit(tree)
        ast.fix_missing_locations(tree)

        # Transform dot access to subscript
        tree = DotToSubscriptTransformer().visit(tree)
        ast.fix_missing_locations(tree)

        # Security validation
        SecurityValidator(self.max_subscript_depth, self.max_iterable_size).visit(tree)

        # GeneratorExp context validation (sum(x for x in lst) OK, standalone blocked)
        self._validate_genexp(tree)

        # Validate functions
        self._validate_functions(tree)

        return tree

    def _validate_genexp(self, tree):
        """Validate generator expressions: only allowed inside whitelisted functions."""
        parent: dict = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parent[id(child)] = node

        for node in ast.walk(tree):
            if not isinstance(node, ast.GeneratorExp):
                continue
            p = parent.get(id(node))
            if p is None:
                raise FormulaError(
                    "Standalone generator expression không được phép. "
                    "Dùng sum(x for x in lst) thay vì (x for x in lst).",
                    code=ErrorCode.SECURITY_VIOLATION,
                )
            if isinstance(p, ast.Call):
                if isinstance(p.func, ast.Name) and p.func.id not in self._GENEXP_ALLOWED:
                    raise FormulaError(
                        f"Generator expression bên trong '{p.func.id}()' không được phép.",
                        code=ErrorCode.SECURITY_VIOLATION,
                    )
            else:
                raise FormulaError(
                    "Generator expression chỉ được dùng trực tiếp bên trong sum/min/max/any/all.",
                    code=ErrorCode.SECURITY_VIOLATION,
                )

    def _validate_functions(self, tree):
        """Check all function calls are in runtime_env"""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id not in self.runtime_env:
                        raise FormulaError(
                            f"Unknown function: {node.func.id}",
                            code=ErrorCode.UNKNOWN_FUNCTION
                        )

    def compile(self, tree: ast.Expression, filename: str = "<formula>") -> Any:
        """Compile AST to bytecode"""
        return compile(tree, filename=filename, mode="eval")