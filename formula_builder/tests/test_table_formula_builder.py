"""Tests for table_formula_builder.py — MultiTableFormulaBuilder."""

from frappe.tests.utils import FrappeTestCase

from formula_builder.table_formula_builder import (
    MultiTableFormulaBuilder,
    normalize_global,
    normalize_scoped,
    synthetic_for_pattern,
    synthetic_simple_total,
    build_engine_from_builder,
)

# Mock custom function cho synthetic tests
def _mock_lookup_calc_pattern(calc_pattern, width, height,
                               weight_per_unit, a, b, c, d):
    """Mock lookup_calc_pattern — tính đơn giản: (width/1000) * weight_per_unit."""
    w = width or 0
    h = height or 1
    wpu = weight_per_unit or 1
    if calc_pattern and "AREA" in str(calc_pattern):
        return (w / 1000) * (h / 1000)
    elif calc_pattern and "COUNT" in str(calc_pattern):
        return 1
    else:
        return (w / 1000) * wpu


MOCK_SAFE_FUNCS = {
    "lookup_calc_pattern": _mock_lookup_calc_pattern,
}


# ═══════════════════════════════════════════════════════════════════════════════
# §1  Normalizer Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalizers(FrappeTestCase):
    """Test normalize_global and normalize_scoped."""

    def test_normalize_global_basic(self):
        self.assertEqual(
            normalize_global("profiles.canh_ngang.width"),
            "canh_ngang__width",
        )

    def test_normalize_global_with_math(self):
        self.assertEqual(
            normalize_global("2*(glasses.panel_top.width + glasses.panel_top.height)"),
            "2*(panel_top__width + panel_top__height)",
        )

    def test_normalize_global_multiple_refs(self):
        self.assertEqual(
            normalize_global("items.a.x + items.b.y - items.c.z"),
            "a__x + b__y - c__z",
        )

    def test_normalize_scoped_basic(self):
        self.assertEqual(
            normalize_scoped("profiles.canh_ngang.width"),
            "profiles__canh_ngang__width",
        )

    def test_normalize_scoped_same_slug_different_table(self):
        """Slug 'canh_ngang' exists in both profiles and glasses → no collision."""
        r1 = normalize_scoped("profiles.canh_ngang.width")
        r2 = normalize_scoped("glasses.canh_ngang.width")
        self.assertEqual(r1, "profiles__canh_ngang__width")
        self.assertEqual(r2, "glasses__canh_ngang__width")
        self.assertNotEqual(r1, r2)

    def test_normalize_scoped_with_math(self):
        self.assertEqual(
            normalize_scoped("2*(glasses.panel_top.width + glasses.panel_top.height)"),
            "2*(glasses__panel_top__width + glasses__panel_top__height)",
        )

    def test_normalize_preserves_non_ref_text(self):
        """Text without pattern stays unchanged."""
        expr = "W_mm - 2*OFFSET_FIXED"
        self.assertEqual(normalize_global(expr), expr)
        self.assertEqual(normalize_scoped(expr), expr)

    def test_normalize_slug_with_hyphen(self):
        self.assertEqual(
            normalize_scoped("items.my-slug.width"),
            "items__my-slug__width",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# §2  Single Table Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSingleTable(FrappeTestCase):
    """Tests với 1 bảng duy nhất."""

    def setUp(self):
        self.rows = [
            {"slug": "A", "width": "W_mm", "qty": "2", "unit_price": 100},
            {"slug": "B", "width": "W_mm/2", "qty": "1", "unit_price": 200},
            {"slug": "C", "width": "W_mm - 100", "height": "H_mm - 50", "qty": "3", "unit_price": 150},
        ]

    # ── Scoped mode ────────────────────────────────────────────────────────

    def test_single_table_scoped_basic(self):
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="items",
            rows=self.rows,
            formula_fields=["width", "qty"],
            literal_fields=["unit_price"],
            id_field="slug",
        )
        formulas, context = builder.build(base_context={"W_mm": 2400})

        # Check formula structure
        names = {f["name"] for f in formulas}
        self.assertIn("items__A__width", names)
        self.assertIn("items__A__qty", names)
        self.assertIn("items__B__width", names)
        self.assertIn("items__C__width", names)
        self.assertIn("items__C__qty", names)

        # Check context has injected literals
        self.assertEqual(context["items__A__unit_price"], 100)
        self.assertEqual(context["items__B__unit_price"], 200)
        self.assertEqual(context["items__C__unit_price"], 150)
        self.assertEqual(context["W_mm"], 2400)

        # Check formula content
        a_width = next(f for f in formulas if f["name"] == "items__A__width")
        self.assertEqual(a_width["formula"], "W_mm")

    def test_single_table_scoped_with_height_field(self):
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="items",
            rows=self.rows,
            formula_fields=["width", "height", "qty"],
            id_field="slug",
        )
        formulas, context = builder.build(
            base_context={"W_mm": 2400, "H_mm": 2600}
        )

        # Row A has no height → skipped
        # Row C has height
        c_height = next(
            (f for f in formulas if f["name"] == "items__C__height"), None
        )
        self.assertIsNotNone(c_height)
        self.assertEqual(c_height["formula"], "H_mm - 50")

        # Row A has no height → formula not created
        a_height = next(
            (f for f in formulas if f["name"] == "items__A__height"), None
        )
        self.assertIsNone(a_height)

    # ── Global mode ────────────────────────────────────────────────────────

    def test_single_table_global_basic(self):
        builder = MultiTableFormulaBuilder(normalize_mode="global")
        builder.add_table(
            table_name="items",
            rows=self.rows,
            formula_fields=["width", "qty"],
            literal_fields=["unit_price"],
            id_field="slug",
        )
        formulas, context = builder.build(base_context={"W_mm": 2400})

        # Global mode: no table prefix
        names = {f["name"] for f in formulas}
        self.assertIn("A__width", names)
        self.assertIn("A__qty", names)
        self.assertIn("B__width", names)
        self.assertNotIn("items__A__width", names)

        self.assertEqual(context["A__unit_price"], 100)

    # ── Cross-reference within same table ──────────────────────────────────

    def test_cross_ref_same_table_scoped(self):
        """Row B references Row A within the same table."""
        rows = [
            {"slug": "A", "width": "W_mm", "qty": "1", "unit_price": 100},
            {"slug": "B", "width": "items.A.width + 50", "qty": "1", "unit_price": 200},
        ]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="items",
            rows=rows,
            formula_fields=["width", "qty"],
            literal_fields=["unit_price"],
            id_field="slug",
        )
        formulas, context = builder.build(base_context={"W_mm": 2400})

        b_width = next(f for f in formulas if f["name"] == "items__B__width")
        # After normalize_scoped: "items.A.width" → "items__A__width"
        self.assertEqual(b_width["formula"], "items__A__width + 50")

        # Engine should resolve this correctly
        from formula_builder.formula_utils import FormulaEngine
        engine = FormulaEngine(formulas=formulas)
        result = engine.calculate(context)
        self.assertEqual(result["items__A__width"], 2400)
        self.assertEqual(result["items__B__width"], 2450)


# ═══════════════════════════════════════════════════════════════════════════════
# §3  Multi-Table Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultiTable(FrappeTestCase):
    """Tests với nhiều bảng."""

    def setUp(self):
        self.profile_rows = [
            {"slug": "frame", "width": "W_mm", "qty": "2",
             "weight_per_unit": 1.257, "unit_price": 113000,
             "calc_pattern": "LENGTH_TO_WEIGHT"},
            {"slug": "sash", "width": "W_mm/n_panel - OFFSET_FRAME", "qty": "2*n_panel",
             "weight_per_unit": 1.350, "unit_price": 113000,
             "calc_pattern": "LENGTH_TO_WEIGHT"},
            {"slug": "nep_kinh", "width": "2*(glasses.panel.width + glasses.panel.height)", "qty": "2",
             "weight_per_unit": 0.312, "unit_price": 113000,
             "calc_pattern": "LENGTH_TO_WEIGHT"},
        ]
        self.glass_rows = [
            {"slug": "panel", "width": "W_mm - 2*OFFSET_FIXED",
             "height": "TransomH - OFFSET_FIXED", "qty": "1",
             "unit_price": 1150000},
        ]

    def test_two_tables_scoped(self):
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="profiles",
            rows=self.profile_rows,
            formula_fields=["width", "qty"],
            literal_fields=["weight_per_unit", "unit_price", "calc_pattern"],
            id_field="slug",
        )
        builder.add_table(
            table_name="glasses",
            rows=self.glass_rows,
            formula_fields=["width", "height", "qty"],
            literal_fields=["unit_price"],
            id_field="slug",
        )
        formulas, context = builder.build(base_context={
            "W_mm": 2400, "n_panel": 2, "OFFSET_FRAME": 48,
            "OFFSET_FIXED": 50, "TransomH": 600,
        })

        # All formulas from both tables exist
        names = {f["name"] for f in formulas}
        self.assertIn("profiles__frame__width", names)
        self.assertIn("profiles__sash__width", names)
        self.assertIn("profiles__nep_kinh__width", names)
        self.assertIn("glasses__panel__width", names)
        self.assertIn("glasses__panel__height", names)
        self.assertIn("glasses__panel__qty", names)

        # Cross-table reference is normalized
        nep_width = next(f for f in formulas if f["name"] == "profiles__nep_kinh__width")
        self.assertEqual(
            nep_width["formula"],
            "2*(glasses__panel__width + glasses__panel__height)",
        )

    def test_two_tables_global(self):
        builder = MultiTableFormulaBuilder(normalize_mode="global")
        builder.add_table(
            table_name="profiles",
            rows=self.profile_rows,
            formula_fields=["width", "qty"],
            id_field="slug",
        )
        builder.add_table(
            table_name="glasses",
            rows=self.glass_rows,
            formula_fields=["width", "height", "qty"],
            id_field="slug",
        )
        formulas, context = builder.build(base_context={
            "W_mm": 2400, "n_panel": 2, "OFFSET_FIXED": 50,
            "TransomH": 600,
        })

        names = {f["name"] for f in formulas}
        self.assertIn("frame__width", names)
        self.assertIn("panel__width", names)
        # No table prefix in global mode
        self.assertNotIn("profiles__frame__width", names)

    def test_build_then_engine_evaluate(self):
        """Full integration: builder → engine → correct results."""
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="profiles",
            rows=self.profile_rows,
            formula_fields=["width", "qty"],
            literal_fields=["weight_per_unit", "unit_price", "calc_pattern"],
            id_field="slug",
        )
        builder.add_table(
            table_name="glasses",
            rows=self.glass_rows,
            formula_fields=["width", "height", "qty"],
            literal_fields=["unit_price"],
            id_field="slug",
        )

        base = {
            "W_mm": 2400, "n_panel": 2, "OFFSET_FRAME": 48,
            "OFFSET_FIXED": 50, "TransomH": 600,
        }
        formulas, context = builder.build(base_context=base)

        from formula_builder.formula_utils import FormulaEngine
        engine = FormulaEngine(formulas=formulas)
        result = engine.calculate(context)

        # Verify results
        self.assertEqual(result["profiles__frame__width"], 2400)
        self.assertEqual(result["profiles__frame__qty"], 2)
        self.assertEqual(result["profiles__sash__width"], 2400 / 2 - 48)  # 1152
        self.assertEqual(result["profiles__sash__qty"], 4)
        self.assertEqual(result["glasses__panel__width"], 2400 - 100)  # 2300
        self.assertEqual(result["glasses__panel__height"], 600 - 50)  # 550
        self.assertEqual(result["glasses__panel__qty"], 1)

        # Cross-ref: nep_kinh depends on glass panel
        self.assertEqual(
            result["profiles__nep_kinh__width"],
            2 * (2300 + 550),  # 5700
        )


# ═══════════════════════════════════════════════════════════════════════════════
# §4  Synthetic Formulas Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyntheticFormulas(FrappeTestCase):
    """Tests cho synthetic formula callbacks."""

    def test_synthetic_for_pattern(self):
        rows = [
            {"slug": "frame", "width": "W_mm", "qty": "2",
             "unit_price": 113000, "calc_pattern": "LENGTH_TO_WEIGHT",
             "weight_per_unit": 1.257},
        ]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="profiles",
            rows=rows,
            formula_fields=["width", "qty"],
            literal_fields=["unit_price", "calc_pattern", "weight_per_unit"],
            id_field="slug",
            synthetic_formulas=synthetic_for_pattern,
        )
        formulas, context = builder.build(base_context={"W_mm": 2400})

        names = {f["name"] for f in formulas}
        self.assertIn("profiles__frame__unit_qty", names)
        self.assertIn("profiles__frame__total_qty", names)
        self.assertIn("profiles__frame__line_total", names)

        # Verify synthetic formula content
        unit_qty = next(f for f in formulas if f["name"] == "profiles__frame__unit_qty")
        self.assertIn("lookup_calc_pattern", unit_qty["formula"])
        self.assertIn("profiles__frame__calc_pattern", unit_qty["formula"])

        total_qty = next(f for f in formulas if f["name"] == "profiles__frame__total_qty")
        self.assertEqual(
            total_qty["formula"],
            "profiles__frame__unit_qty * (profiles__frame__qty or 1)",
        )

        line_total = next(f for f in formulas if f["name"] == "profiles__frame__line_total")
        self.assertIn("profiles__frame__unit_price", line_total["formula"])

    def test_synthetic_simple_total(self):
        rows = [
            {"slug": "glass_A", "width": "W_mm", "height": "H_mm",
             "qty": "1", "unit_price": 500000, "unit_qty": 1.5},
        ]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="glasses",
            rows=rows,
            formula_fields=["width", "height", "qty"],
            literal_fields=["unit_price", "unit_qty"],
            id_field="slug",
            synthetic_formulas=synthetic_simple_total,
        )
        formulas, context = builder.build(
            base_context={"W_mm": 2400, "H_mm": 2600}
        )

        lt = next(f for f in formulas if f["name"] == "glasses__glass_A__line_total")
        self.assertEqual(
            lt["formula"],
            "(glasses__glass_A__unit_qty or 1) * "
            "(glasses__glass_A__qty or 1) * "
            "(glasses__glass_A__unit_price or 0)",
        )

    def test_custom_synthetic_callback(self):
        def custom_synthetic(builder, table_name, slug, row, context, var_prefix, **kwargs):
            return [
                {"name": f"{var_prefix}__area",
                 "formula": f"({var_prefix}__width/1000)*({var_prefix}__height/1000)"},
            ]

        rows = [
            {"slug": "glass_A", "width": "W_mm", "height": "H_mm", "qty": "1"},
        ]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="glasses",
            rows=rows,
            formula_fields=["width", "height", "qty"],
            id_field="slug",
            synthetic_formulas=custom_synthetic,
        )
        formulas, context = builder.build(
            base_context={"W_mm": 2400, "H_mm": 2600}
        )

        area = next(f for f in formulas if f["name"] == "glasses__glass_A__area")
        self.assertEqual(
            area["formula"],
            "(glasses__glass_A__width/1000)*(glasses__glass_A__height/1000)",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# §5  Custom Override Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestCustomOverride(FrappeTestCase):
    """Tests cho formula_builder override và custom normalize."""

    def test_custom_formula_builder_override(self):
        def build_taxes(builder, table_name, rows, context):
            formulas = []
            for row in rows:
                formulas.append({
                    "name": f"TAX_{row['code']}",
                    "formula": f"{row['rate']} * SUBTOTAL",
                })
            return formulas

        tax_rows = [
            {"code": "VAT", "rate": 0.1},
            {"code": "PIT", "rate": 0.05},
        ]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="taxes",
            rows=tax_rows,
            formula_builder=build_taxes,  # ← Override
            # Không cần formula_fields hay literal_fields
        )
        formulas, context = builder.build(
            base_context={"SUBTOTAL": 1000000}
        )

        self.assertEqual(len(formulas), 2)
        names = {f["name"] for f in formulas}
        self.assertIn("TAX_VAT", names)
        self.assertIn("TAX_PIT", names)

        vat = next(f for f in formulas if f["name"] == "TAX_VAT")
        self.assertEqual(vat["formula"], "0.1 * SUBTOTAL")

    def test_custom_normalize_fn(self):
        def upper_normalize(expr):
            """Custom: uppercase all variable names."""
            import re
            return re.sub(r'(\w+)\.(\w+)\.(\w+)', r'\1__\2__\3', expr).upper()

        rows = [{"slug": "PartA", "width": "items.PartB.width + 10", "qty": "1"}]
        builder = MultiTableFormulaBuilder(normalize_fn=upper_normalize)
        builder.add_table(
            table_name="items",
            rows=rows,
            formula_fields=["width", "qty"],
            id_field="slug",
        )
        formulas, context = builder.build()

        w = next(f for f in formulas if f["name"] == "PartA__width")
        self.assertEqual(w["formula"], "ITEMS__PARTB__WIDTH + 10")

    def test_hybrid_merge_manual_formulas(self):
        """Dùng builder cho phần chuẩn, merge thêm formulas thủ công."""
        rows = [
            {"slug": "A", "width": "W_mm", "qty": "2"},
        ]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="items",
            rows=rows,
            formula_fields=["width", "qty"],
            id_field="slug",
        )
        formulas, context = builder.build(base_context={"W_mm": 2400})

        # Merge thêm formulas thủ công
        formulas.append({"name": "CUSTOM_TOTAL", "formula": "items__A__qty * 999"})

        from formula_builder.formula_utils import FormulaEngine
        engine = FormulaEngine(formulas=formulas)
        result = engine.calculate(context)
        self.assertEqual(result["CUSTOM_TOTAL"], 2 * 999)


# ═══════════════════════════════════════════════════════════════════════════════
# §6  Collision & Validation Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestCollisionAndValidation(FrappeTestCase):
    """Tests cho collision detection và edge cases."""

    def test_duplicate_table_name_raises(self):
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="items",
            rows=[{"slug": "A", "width": "W_mm"}],
            formula_fields=["width"],
            id_field="slug",
        )
        with self.assertRaises(ValueError):
            builder.add_table(
                table_name="items",  # Duplicate
                rows=[{"slug": "B", "width": "H_mm"}],
                formula_fields=["width"],
                id_field="slug",
            )

    def test_collision_detection_scoped(self):
        """Scoped mode: no collision between tables with different names."""
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="profiles",
            rows=[{"slug": "frame", "width": "W_mm"}],
            formula_fields=["width"],
            id_field="slug",
        )
        # Different table, same slug → no collision in scoped mode
        builder.add_table(
            table_name="glasses",
            rows=[{"slug": "frame", "width": "W_mm"}],
            formula_fields=["width"],
            id_field="slug",
        )
        formulas, ctx = builder.build()
        names = {f["name"] for f in formulas}
        self.assertIn("profiles__frame__width", names)
        self.assertIn("glasses__frame__width", names)
        self.assertEqual(len(formulas), 2)

    def test_collision_detection_global(self):
        """Global mode: same slug in different tables = collision."""
        builder = MultiTableFormulaBuilder(normalize_mode="global")
        builder.add_table(
            table_name="profiles",
            rows=[{"slug": "frame", "width": "W_mm"}],
            formula_fields=["width"],
            id_field="slug",
        )
        with self.assertRaises(ValueError):
            builder.add_table(
                table_name="glasses",
                rows=[{"slug": "frame", "width": "H_mm"}],  # Same slug!
                formula_fields=["width"],
                id_field="slug",
            )
            builder.build()

    def test_collision_same_table_same_slug(self):
        """Same table, same slug twice → collision on formula fields."""
        rows = [
            {"slug": "frame", "width": "W_mm"},
            {"slug": "frame", "width": "H_mm"},  # Duplicate slug in same table
        ]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="profiles",
            rows=rows,
            formula_fields=["width"],
            id_field="slug",
        )
        with self.assertRaises(ValueError):
            builder.build()

    def test_collision_literal_only_duplicate_slug(self):
        """Literal-only table, same slug with DIFFERENT values → ValueError.

        This catches the silent-failure bug where literal fields would
        silently keep the first row's value while discarding subsequent
        rows — causing wrong unit_price / weight in production.
        """
        rows = [
            {"slug": "frame", "unit_price": 113000},
            {"slug": "frame", "unit_price": 95000},  # Same slug, different value!
        ]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="profiles",
            rows=rows,
            formula_fields=[],  # No formula fields — literal only
            literal_fields=["unit_price"],
            id_field="slug",
        )
        with self.assertRaises(ValueError) as ctx:
            builder.build()
        self.assertIn("TRÙNG TÊN BIẾN LITERAL", str(ctx.exception))

    def test_collision_literal_same_value_no_error(self):
        """Literal-only table, same slug with SAME value → OK (no real collision)."""
        rows = [
            {"slug": "frame", "unit_price": 113000},
            {"slug": "frame", "unit_price": 113000},  # Same slug, same value → fine
        ]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="profiles",
            rows=rows,
            formula_fields=["width"],
            literal_fields=["unit_price"],
            id_field="slug",
        )
        # Second row will collide on formula field before literal,
        # so we need different test setup: only literal, no formula
        builder2 = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder2.add_table(
            table_name="prices",
            rows=rows,
            literal_fields=["unit_price"],
            id_field="slug",
        )
        # Should NOT raise — same slug + same literal value is harmless
        formulas, ctx = builder2.build()
        self.assertEqual(ctx["prices__frame__unit_price"], 113000)

    def test_invalid_normalize_mode(self):
        with self.assertRaises(ValueError):
            MultiTableFormulaBuilder(normalize_mode="invalid_mode")

    def test_missing_id_field_skipped(self):
        """Row without id_field → skipped silently."""
        rows = [
            {"slug": "A", "width": "W_mm"},
            {"width": "H_mm"},  # No slug field
            {"slug": "C", "width": "100"},
        ]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="items",
            rows=rows,
            formula_fields=["width"],
            id_field="slug",
        )
        formulas, ctx = builder.build()
        self.assertEqual(len(formulas), 2)  # Row without slug skipped

    def test_missing_id_field_raises_when_not_skip(self):
        rows = [
            {"slug": "A", "width": "W_mm"},
            {"width": "H_mm"},  # No slug
        ]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="items",
            rows=rows,
            formula_fields=["width"],
            id_field="slug",
            skip_empty_formula=False,
        )
        with self.assertRaises(ValueError):
            builder.build()

    def test_empty_formula_skipped(self):
        """Row has slug but empty formula → skipped."""
        rows = [
            {"slug": "A", "width": "W_mm", "height": "", "qty": "1"},
        ]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="items",
            rows=rows,
            formula_fields=["width", "height", "qty"],
            id_field="slug",
        )
        formulas, ctx = builder.build()
        names = {f["name"] for f in formulas}
        self.assertIn("items__A__width", names)
        self.assertIn("items__A__qty", names)
        self.assertNotIn("items__A__height", names)  # Empty → skipped

    def test_custom_prefix(self):
        rows = [{"slug": "VAT", "amount": "RATE * BASE"}]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="taxes",
            rows=rows,
            formula_fields=["amount"],
            id_field="slug",
            prefix="TAX_",
        )
        formulas, ctx = builder.build()
        self.assertIn("TAX_taxes__VAT__amount", {f["name"] for f in formulas})

    def test_synthetic_kwargs_passed(self):
        """synthetic_kwargs are forwarded to the callback."""
        captured_kwargs = {}

        def tracking_synthetic(builder, table_name, slug, row, context, var_prefix, **kwargs):
            captured_kwargs.update(kwargs)
            return []

        rows = [{"slug": "A", "width": "W_mm"}]
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="items",
            rows=rows,
            formula_fields=["width"],
            id_field="slug",
            synthetic_formulas=tracking_synthetic,
            synthetic_kwargs={"custom_param": 42, "mode": "test"},
        )
        builder.build()
        self.assertEqual(captured_kwargs.get("custom_param"), 42)
        self.assertEqual(captured_kwargs.get("mode"), "test")


# ═══════════════════════════════════════════════════════════════════════════════
# §7  Convenience & Utility Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestConvenience(FrappeTestCase):
    """Tests cho build_engine_from_builder và utility methods."""

    def test_build_engine_from_builder(self):
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="items",
            rows=[{"slug": "A", "width": "W_mm", "qty": "2"}],
            formula_fields=["width", "qty"],
            id_field="slug",
        )
        engine, context = build_engine_from_builder(
            builder, base_context={"W_mm": 2400},
            on_error="raise", deterministic=True,
        )
        result = engine.calculate(context)
        self.assertEqual(result["items__A__width"], 2400)
        self.assertEqual(result["items__A__qty"], 2)

    def test_get_var_ref_scoped(self):
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        self.assertEqual(
            builder.get_var_ref("profiles", "frame", "width"),
            "profiles__frame__width",
        )

    def test_get_var_ref_global(self):
        builder = MultiTableFormulaBuilder(normalize_mode="global")
        self.assertEqual(
            builder.get_var_ref("profiles", "frame", "width"),
            "frame__width",
        )

    def test_get_var_prefix_scoped(self):
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        self.assertEqual(
            builder.get_var_prefix("profiles", "frame"),
            "profiles__frame",
        )

    def test_get_var_prefix_global(self):
        builder = MultiTableFormulaBuilder(normalize_mode="global")
        self.assertEqual(
            builder.get_var_prefix("profiles", "frame"),
            "frame",
        )

    def test_report(self):
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="profiles",
            rows=[{"slug": "A", "width": "W_mm"}],
            formula_fields=["width"],
            literal_fields=["unit_price"],
            id_field="slug",
            synthetic_formulas=synthetic_simple_total,
        )
        report = builder.report()
        self.assertIn("MultiTableFormulaBuilder", report)
        self.assertIn("mode=scoped", report)
        self.assertIn("profiles", report)
        self.assertIn("synthetic_simple_total", report)

    def test_fluent_interface(self):
        """add_table returns self for chaining."""
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        result = builder.add_table(
            table_name="t1",
            rows=[{"slug": "A", "v": "1"}],
            formula_fields=["v"],
            id_field="slug",
        )
        self.assertIs(result, builder)

    def test_context_not_mutated_between_calls(self):
        """Verify base_context is not mutated — build creates a copy."""
        base = {"X": 100}
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")
        builder.add_table(
            table_name="items",
            rows=[{"slug": "A", "width": "X + 1", "unit_price": 50}],
            formula_fields=["width"],
            literal_fields=["unit_price"],
            id_field="slug",
        )
        builder.build(base_context=base)
        # base should still be {"X": 100}, not include injected literals
        self.assertEqual(base, {"X": 100})
        self.assertNotIn("items__A__unit_price", base)


# ═══════════════════════════════════════════════════════════════════════════════
# §8  End-to-End: Full AlumGlass-like BOM
# ═══════════════════════════════════════════════════════════════════════════════

class TestEndToEndBOM(FrappeTestCase):
    """End-to-end test simulating a real BOM calculation."""

    def test_full_bom_three_tables_with_cross_ref(self):
        """Simulate AlumGlass BOM: profiles + glasses → cost calculation."""
        builder = MultiTableFormulaBuilder(normalize_mode="scoped")

        # Bảng 1: Nhôm profiles
        builder.add_table(
            table_name="profiles",
            rows=[
                {"slug": "khung_ngang", "width": "W_mm", "qty": "2",
                 "unit_price": 113000, "calc_pattern": "LENGTH_TO_WEIGHT",
                 "weight_per_unit": 1.257},
                {"slug": "khung_dung", "width": "H_mm", "qty": "2",
                 "unit_price": 113000, "calc_pattern": "LENGTH_TO_WEIGHT",
                 "weight_per_unit": 1.257},
                {"slug": "canh_ngang", "width": "W_mm/n_panel - OFFSET_FRAME", "qty": "2*n_panel",
                 "unit_price": 113000, "calc_pattern": "LENGTH_TO_WEIGHT",
                 "weight_per_unit": 1.350},
            ],
            formula_fields=["width", "qty"],
            literal_fields=["unit_price", "calc_pattern", "weight_per_unit"],
            id_field="slug",
            synthetic_formulas=synthetic_for_pattern,
        )

        # Bảng 2: Kính
        builder.add_table(
            table_name="glasses",
            rows=[
                {"slug": "panel_top", "width": "W_mm - 2*OFFSET_FIXED",
                 "height": "TransomH - OFFSET_FIXED", "qty": "1",
                 "unit_price": 1150000},
                {"slug": "panel_bottom", "width": "profiles.canh_ngang.width - OFFSET_GL",
                 "height": "H_mm - TransomH - OFFSET_GL", "qty": "n_panel",
                 "unit_price": 1150000},
            ],
            formula_fields=["width", "height", "qty"],
            literal_fields=["unit_price"],
            id_field="slug",
        )

        # Build
        base = {
            "W_mm": 2400, "H_mm": 2600,
            "TransomH": 600, "n_panel": 2,
            "OFFSET_FRAME": 48, "OFFSET_FIXED": 50,
            "OFFSET_GL": 90,
        }
        formulas, context = builder.build(base_context=base)

        from formula_builder.formula_utils import FormulaEngine
        engine = FormulaEngine(formulas=formulas, safe_funcs=MOCK_SAFE_FUNCS)
        result = engine.calculate(context)

        # Verify profiles
        self.assertEqual(result["profiles__khung_ngang__width"], 2400)
        self.assertEqual(result["profiles__khung_dung__width"], 2600)
        self.assertEqual(result["profiles__canh_ngang__width"], 2400 / 2 - 48)  # 1152

        # Verify glasses (including cross-ref from profiles)
        self.assertEqual(result["glasses__panel_top__width"], 2400 - 100)  # 2300
        self.assertEqual(result["glasses__panel_top__height"], 600 - 50)  # 550
        self.assertEqual(
            result["glasses__panel_bottom__width"],
            (2400 / 2 - 48) - 90,  # canh_ngang.width - OFFSET_GL = 1152 - 90 = 1062
        )

        # Verify synthetic formulas were created
        self.assertIn("profiles__khung_ngang__line_total", result)
        self.assertIn("profiles__khung_ngang__unit_qty", result)
