"""
table_formula_builder.py — MultiTableFormulaBuilder
=====================================================
Utility class giúp build formulas + context từ dữ liệu có cấu trúc dạng bảng
(child tables / nested data). HOÀN TOÀN GENERIC — không gắn với BOM hay ngành cụ thể.

Hỗ trợ:
- Nhiều formula fields trên 1 row
- Cross-reference với cú pháp UI: {table}.{slug}.{field}
- Normalize về engine format: {prefix}{slug}__{field}
- 2 chế độ normalize: "scoped" (giữ table prefix, an toàn) và "global" (bỏ prefix)
- Synthetic formulas qua callback
- Literal value injection vào context
- Phát hiện collision tên biến
- Override toàn bộ logic build cho 1 bảng
- Custom normalize function

Dùng được cho MỌI NGÀNH: nhôm kính, may mặc, hóa đơn, bảng lương, dự toán...

Cách dùng cơ bản:
─────────────────
    from formula_builder.table_formula_builder import MultiTableFormulaBuilder

    builder = MultiTableFormulaBuilder(normalize_mode="scoped")

    builder.add_table(
        table_name="profiles",
        rows=profile_rows,
        formula_fields=["width", "height", "qty"],
        literal_fields=["weight_per_unit", "unit_price", "calc_pattern"],
        id_field="slug",
        synthetic_formulas=my_synthetic,
    )

    builder.add_table(
        table_name="glasses",
        rows=glass_rows,
        formula_fields=["width", "height", "qty"],
        literal_fields=["unit_price", "glass_thick"],
        id_field="slug",
    )

    formulas, context = builder.build(base_context=inputs)
    engine = FormulaEngine(formulas=formulas, context=context)
    result = engine.evaluate(context)

Tùy chỉnh nâng cao:
───────────────────
    # Override toàn bộ formula build cho 1 table
    builder.add_table(
        table_name="custom_table",
        rows=custom_rows,
        formula_builder=custom_build_function,
    )

    # Override normalize function
    builder = MultiTableFormulaBuilder(
        normalize_fn=lambda expr: my_custom_normalize(expr)
    )

    # Hybrid: dùng builder cho hầu hết, tự code phần đặc biệt
    formulas, context = builder.build(base_inputs)
    formulas.extend(manual_formulas)  # merge thủ công
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


# ═══════════════════════════════════════════════════════════════════════════════
# §1  Cross-Reference Normalizers
# ═══════════════════════════════════════════════════════════════════════════════

def normalize_global(expr: str) -> str:
    """Option A: Slug unique toàn cục → bỏ table name.

    {table}.{slug}.{field} → {slug}__{field}

    VD: "profiles.canh_ngang.width" → "canh_ngang__width"
        "glasses.panel_top.height"  → "panel_top__height"
    """
    return re.sub(r'\w+\.(\w[\w-]*)\.(\w+)', r'\1__\2', expr)


def normalize_scoped(expr: str) -> str:
    """Option B: Slug unique trong bảng → giữ table name làm prefix.

    {table}.{slug}.{field} → {table}__{slug}__{field}

    VD: "profiles.canh_ngang.width" → "profiles__canh_ngang__width"
        "glasses.canh_ngang.width"  → "glasses__canh_ngang__width"
        → Không collision dù 2 bảng cùng slug "canh_ngang"
    """
    return re.sub(r'(\w+)\.(\w[\w-]*)\.(\w+)', r'\1__\2__\3', expr)


# Registry
_NORMALIZERS = {
    "global": normalize_global,
    "scoped": normalize_scoped,
}


# ═══════════════════════════════════════════════════════════════════════════════
# §2  MultiTableFormulaBuilder
# ═══════════════════════════════════════════════════════════════════════════════

class MultiTableFormulaBuilder:
    """Build formulas + context từ dữ liệu nhiều bảng (child tables).

    HOÀN TOÀN GENERIC — không phụ thuộc ngành nghề hay loại dữ liệu.
    Chỉ cần dữ liệu có cấu trúc rows + formula fields, builder sẽ tự động
    tạo ra List[{"name":..., "formula":...}] chuẩn cho FormulaEngine.

    Dùng cho MỌI bài toán: BOM, hóa đơn, bảng lương, dự toán, kế hoạch...

    Attributes:
        normalize_mode: "scoped" (Option B, mặc định, an toàn) | "global" (Option A)
        normalize_fn:   Hàm normalize — tự động set từ normalize_mode,
                        hoặc truyền custom function.
        tables:         List[Dict] — cấu hình các bảng đã thêm.
        _formula_names: Set[str] — registry chống trùng tên formula.
    """

    def __init__(
        self,
        normalize_mode: str = "scoped",
        normalize_fn: Optional[Callable[[str], str]] = None,
    ):
        """
        Args:
            normalize_mode: "scoped" | "global". Mặc định "scoped" (an toàn,
                            chống collision khi slug trùng giữa các bảng).
            normalize_fn:   Custom normalize function. Nếu truyền, bỏ qua
                            normalize_mode.
        """
        if normalize_fn:
            self.normalize_fn = normalize_fn
            self.normalize_mode = "custom"
        elif normalize_mode in _NORMALIZERS:
            self.normalize_mode = normalize_mode
            self.normalize_fn = _NORMALIZERS[normalize_mode]
        else:
            raise ValueError(
                f"normalize_mode phải là 'scoped' hoặc 'global', "
                f"nhận được: {normalize_mode!r}"
            )

        self.tables: List[Dict[str, Any]] = []
        self._formula_names: set = set()

    # ── Public API ──────────────────────────────────────────────────────────

    def add_table(
        self,
        table_name: str,
        rows: List[Dict[str, Any]],
        formula_fields: Optional[List[str]] = None,
        *,
        id_field: str = "slug",
        literal_fields: Optional[List[str]] = None,
        synthetic_formulas: Optional[
            Callable[..., List[Dict[str, str]]]
        ] = None,
        synthetic_kwargs: Optional[Dict[str, Any]] = None,
        formula_builder: Optional[
            Callable[..., List[Dict[str, str]]]
        ] = None,
        skip_empty_formula: bool = True,
        prefix: str = "",
    ) -> "MultiTableFormulaBuilder":
        """Thêm 1 bảng dữ liệu vào builder.

        Args:
            table_name:       Tên bảng, dùng làm namespace prefix trong Option B.
                              VD: "profiles", "invoice_items", "salary_lines".
            rows:             List[dict] — mỗi dict là 1 dòng dữ liệu.
            formula_fields:   Các field chứa công thức FB.
                              VD: ["width", "height", "qty"] hoặc ["amount", "tax"].
                              Mỗi field → 1 formula dict trong output.
                              Có thể bỏ qua nếu dùng formula_builder override.
            id_field:         Field định danh dòng. Mặc định "slug".
                              VD: "line_code", "item_code", "employee_id".
            literal_fields:   Các field cần inject literal vào context.
                              VD: ["unit_price", "tax_rate", "weight_per_unit"].
            synthetic_formulas: Callback sinh thêm formulas (không từ dữ liệu gốc).
                              Nhận (builder, table_name, slug, row, context,
                              var_prefix, **kwargs) → List[dict].
            synthetic_kwargs: Dict kwargs truyền thêm vào synthetic_formulas.
            formula_builder:  Callback thay thế TOÀN BỘ logic build cho bảng này.
                              Nhận (builder, table_name, rows, context) → List[dict].
                              Nếu truyền → bỏ qua formula_fields, literal_fields,
                              synthetic_formulas.
            skip_empty_formula: Bỏ qua dòng không có công thức. Mặc định True.
            prefix:           Prefix thêm vào tên biến.
                              VD: "TAX_" → "TAX_profiles__VAT".

        Returns:
            self (fluent interface).

        Raises:
            ValueError: Nếu table_name đã tồn tại.
        """
        if any(t["table_name"] == table_name for t in self.tables):
            raise ValueError(
                f"Table '{table_name}' đã được thêm. Mỗi table chỉ thêm 1 lần."
            )

        self.tables.append({
            "table_name": table_name,
            "rows": rows,
            "formula_fields": list(formula_fields or []),
            "id_field": id_field,
            "literal_fields": list(literal_fields or []),
            "synthetic_formulas": synthetic_formulas,
            "synthetic_kwargs": dict(synthetic_kwargs or {}),
            "formula_builder": formula_builder,
            "skip_empty_formula": skip_empty_formula,
            "prefix": prefix,
        })
        return self

    def build(
        self,
        base_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        """Build formulas + context từ tất cả bảng đã thêm.

        Args:
            base_context: Context gốc (global inputs, constants,...).
                          Các literal sẽ được merge vào đây.

        Returns:
            (formulas, context):
                formulas: List[{"name": str, "formula": str}]
                          Sẵn sàng truyền vào FormulaEngine.
                context:  Dict chứa base_context + tất cả literal đã inject.

        Raises:
            ValueError: Nếu phát hiện trùng tên formula.
        """
        self._formula_names = set()
        context = dict(base_context or {})

        all_formulas: List[Dict[str, str]] = []

        for tbl in self.tables:
            table_formulas = self._build_table(tbl, context)
            all_formulas.extend(table_formulas)

        return all_formulas, context

    # ── Internal Methods ────────────────────────────────────────────────────

    def _build_table(
        self,
        tbl: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        """Build formulas cho 1 bảng."""
        table_name = tbl["table_name"]

        # Nếu có custom formula_builder → ủy quyền toàn bộ
        if tbl["formula_builder"]:
            return tbl["formula_builder"](self, table_name, tbl["rows"], context)

        formulas: List[Dict[str, str]] = []
        for row in tbl["rows"]:
            row_formulas = self._build_row(tbl, row, context)
            formulas.extend(row_formulas)

        return formulas

    def _build_row(
        self,
        tbl: Dict[str, Any],
        row: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        """Build formulas cho 1 dòng."""
        id_field = tbl["id_field"]
        table_name = tbl["table_name"]
        extra_prefix = tbl["prefix"]
        slug = row.get(id_field)
        literal_fields = tbl["literal_fields"]
        synthetic_formulas = tbl["synthetic_formulas"]

        if not slug:
            if tbl["skip_empty_formula"]:
                return []
            raise ValueError(
                f"Dòng trong '{table_name}' thiếu '{id_field}'. "
                f"Row data: {row}"
            )

        # ── Xác định prefix cho tên biến ──
        if self.normalize_mode == "scoped":
            var_prefix = f"{table_name}__{slug}"
        elif self.normalize_mode == "global":
            var_prefix = slug
        else:  # custom — user tự xử lý trong normalize_fn
            var_prefix = slug

        if extra_prefix:
            var_prefix = f"{extra_prefix}{var_prefix}"

        # ── (a) Inject literal fields vào context ──
        for key in literal_fields:
            if key in row and row[key] is not None:
                ctx_key = f"{var_prefix}__{key}"
                if ctx_key not in context:
                    context[ctx_key] = row[key]

        # ── (b) Build formulas từ formula_fields ──
        formulas: List[Dict[str, str]] = []
        for field_name in tbl["formula_fields"]:
            expr = row.get(field_name)
            if expr is None or (isinstance(expr, str) and not expr.strip()):
                if tbl["skip_empty_formula"]:
                    continue
                raise ValueError(
                    f"Dòng '{slug}' trong '{table_name}' "
                    f"thiếu công thức cho field '{field_name}'"
                )

            expr_str = str(expr).strip()
            # Normalize cross-reference
            normalized = self.normalize_fn(expr_str)

            formula_name = f"{var_prefix}__{field_name}"

            # Collision check
            if formula_name in self._formula_names:
                raise ValueError(
                    f"TRÙNG TÊN FORMULA: '{formula_name}'.\n"
                    f"  Table: {table_name}, Slug: {slug}, Field: {field_name}\n"
                    f"  Công thức: {normalized}\n"
                    f"  Gợi ý: Đổi slug hoặc dùng normalize_mode='scoped'."
                )
            self._formula_names.add(formula_name)

            formulas.append({
                "name": formula_name,
                "formula": normalized,
            })

        # ── (c) Synthetic formulas (nếu có) ──
        if synthetic_formulas:
            kwargs = dict(tbl.get("synthetic_kwargs", {}))
            synth = synthetic_formulas(
                builder=self,
                table_name=table_name,
                slug=slug,
                row=row,
                context=context,
                var_prefix=var_prefix,
                **kwargs,
            )
            if synth:
                for sf in synth:
                    if sf["name"] in self._formula_names:
                        raise ValueError(
                            f"TRÙNG TÊN FORMULA (synthetic): '{sf['name']}'"
                        )
                    self._formula_names.add(sf["name"])
                    formulas.append(sf)

        return formulas

    # ── Utility ─────────────────────────────────────────────────────────────

    def get_var_ref(
        self,
        table_name: str,
        slug: str,
        field: str,
    ) -> str:
        """Trả về tên biến engine chuẩn cho 1 (table, slug, field).

        Dùng trong synthetic_formulas callback hoặc khi cần build biến thủ công.

        VD (scoped mode):
            builder.get_var_ref("profiles", "canh_ngang", "width")
            → "profiles__canh_ngang__width"

        VD (global mode):
            builder.get_var_ref("profiles", "canh_ngang", "width")
            → "canh_ngang__width"
        """
        if self.normalize_mode == "scoped":
            return f"{table_name}__{slug}__{field}"
        elif self.normalize_mode == "global":
            return f"{slug}__{field}"
        else:
            sample = f"{table_name}.{slug}.{field}"
            return self.normalize_fn(sample)

    def get_var_prefix(
        self,
        table_name: str,
        slug: str,
    ) -> str:
        """Trả về prefix cho 1 (table, slug).

        VD (scoped): "profiles__canh_ngang"
        VD (global): "canh_ngang"
        """
        if self.normalize_mode == "scoped":
            return f"{table_name}__{slug}"
        elif self.normalize_mode == "global":
            return slug
        else:
            sample = f"{table_name}.{slug}.x"
            normalized = self.normalize_fn(sample)
            return normalized.rsplit("__", 1)[0]

    def report(self) -> str:
        """Báo cáo cấu trúc builder — hữu ích cho debug."""
        lines = [
            f"MultiTableFormulaBuilder (mode={self.normalize_mode})",
            f"  Tables: {len(self.tables)}",
        ]
        for tbl in self.tables:
            lines.append(
                f"  ├─ {tbl['table_name']}: {len(tbl['rows'])} rows"
            )
            lines.append(f"  │  formula_fields: {tbl['formula_fields']}")
            lines.append(f"  │  literal_fields: {tbl['literal_fields']}")
            if tbl["synthetic_formulas"]:
                lines.append(
                    f"  │  synthetic: {tbl['synthetic_formulas'].__name__}"
                )
            if tbl["formula_builder"]:
                lines.append(
                    f"  │  custom builder: {tbl['formula_builder'].__name__}"
                )
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# §3  Synthetic Formula Helpers (các callback mẫu)
# ═══════════════════════════════════════════════════════════════════════════════

def synthetic_for_pattern(
    builder: MultiTableFormulaBuilder,
    table_name: str,
    slug: str,
    row: Dict[str, Any],
    context: Dict[str, Any],
    var_prefix: str,
    **kwargs,
) -> List[Dict[str, str]]:
    """Synthetic formulas chuẩn cho bảng có calc_pattern.

    Sinh ra: unit_qty (từ lookup_calc_pattern), total_qty, line_total.
    Phù hợp cho bảng cần tính số lượng đơn vị rồi nhân đơn giá.

    VD: profiles (nhôm), steel_bars (thép), fabric_rolls (vải)...
    """
    return [
        {
            "name": f"{var_prefix}__unit_qty",
            "formula": (
                f"lookup_calc_pattern({var_prefix}__calc_pattern, "
                f"{var_prefix}__width, {var_prefix}__height, "
                f"{var_prefix}__weight_per_unit, 1, 1, 1, 1)"
            ),
        },
        {
            "name": f"{var_prefix}__total_qty",
            "formula": f"{var_prefix}__unit_qty * ({var_prefix}__qty or 1)",
        },
        {
            "name": f"{var_prefix}__line_total",
            "formula": (
                f"{var_prefix}__total_qty * ({var_prefix}__unit_price or 0)"
            ),
        },
    ]


def synthetic_simple_total(
    builder: MultiTableFormulaBuilder,
    table_name: str,
    slug: str,
    row: Dict[str, Any],
    context: Dict[str, Any],
    var_prefix: str,
    **kwargs,
) -> List[Dict[str, str]]:
    """Synthetic đơn giản: line_total = unit_qty * qty * unit_price.

    Dùng cho bảng không có calc_pattern — unit_qty đã có sẵn
    hoặc được tính riêng.
    """
    return [
        {
            "name": f"{var_prefix}__line_total",
            "formula": (
                f"({var_prefix}__unit_qty or 1) * "
                f"({var_prefix}__qty or 1) * "
                f"({var_prefix}__unit_price or 0)"
            ),
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# §4  Convenience: build engine trực tiếp
# ═══════════════════════════════════════════════════════════════════════════════

def build_engine_from_builder(
    builder: MultiTableFormulaBuilder,
    base_context: Optional[Dict[str, Any]] = None,
    *,
    on_error: str = "raise",
    deterministic: bool = True,
    **engine_kwargs,
):
    """Build FormulaEngine trực tiếp từ MultiTableFormulaBuilder.

    Convenience function — gọi builder.build() rồi tạo FormulaEngine.

    Args:
        builder:       MultiTableFormulaBuilder đã cấu hình.
        base_context:  Context gốc (global inputs).
        on_error:      "raise" | "null" | "default".
        deterministic: Chặn non-deterministic functions.
        **engine_kwargs: Truyền thêm vào FormulaEngine.

    Returns:
        Tuple[FormulaEngine, Dict[str, Any]]: (engine, context)
    """
    from formula_builder.formula_utils import FormulaEngine

    formulas, context = builder.build(base_context)
    engine = FormulaEngine(
        formulas=formulas,
        on_error=on_error,
        deterministic=deterministic,
        **engine_kwargs,
    )
    return engine, context
