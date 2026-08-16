# test_config_io.py — F13: test Import/Export formula sets (JSON)
# Chạy không cần site, không cần frappe: python -m unittest formula_builder.tests.test_config_io

import json
import unittest

from formula_builder.formula_utils.config_io import (
    ConfigIOError,
    export_config,
    import_config,
    roundtrip,
)

FORMULAS = [
    {"name": "tt_nvl", "formula": "vlc_dau + tong_vlp_nc_cm", "description": "Tổng NVL", "group": "nvl"},
    {"name": "dg_nvl", "formula": "tt_nvl + cpc_nvl + vat_nvl"},
    {"name": "gia_thanh_sp", "formula": "safe_div(tong_gia_thanh, so_luong_sp, 0)"},
]

BINDINGS = [
    {"source_type": "matrix_lookup", "source_config": {"doctype": "Item Price", "value_field": "price"}},
    {"source_type": "constant", "source_config": {"value": 5}},
    {"source_type": "doctype_query", "source_config": "{\"doctype\": \"Item\", \"fieldname\": \"weight_per_unit\"}"},
]


class TestExportConfig(unittest.TestCase):
    def test_export_returns_valid_json(self):
        out = export_config(FORMULAS, BINDINGS, meta={"name": "Gia thanh", "app": "alumglass"})
        data = json.loads(out)
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(len(data["formula_set"]), 3)
        self.assertEqual(len(data["bindings"]), 3)
        self.assertEqual(data["meta"]["name"], "Gia thanh")
        self.assertTrue(data["exported_at"].endswith("Z"))
        self.assertTrue(len(data["checksum"]) == 64)

    def test_export_normalizes_string_source_config_to_dict(self):
        out = export_config(FORMULAS, BINDINGS)
        data = json.loads(out)
        third = data["bindings"][2]
        self.assertIsInstance(third["source_config"], dict)
        self.assertEqual(third["source_config"]["doctype"], "Item")

    def test_export_requires_formulas(self):
        with self.assertRaises(ConfigIOError):
            export_config([])

    def test_export_missing_formula_key_raises(self):
        with self.assertRaises(ConfigIOError):
            export_config([{"name": "x"}])

    def test_export_invalid_binding_raises(self):
        with self.assertRaises(ConfigIOError):
            export_config(FORMULAS, [{"source_type": "constant"}])

    def test_export_no_bindings_allowed(self):
        out = export_config(FORMULAS)
        data = json.loads(out)
        self.assertEqual(data["bindings"], [])


class TestImportConfig(unittest.TestCase):
    def test_import_roundtrip_preserves_formulas_and_bindings(self):
        out = export_config(FORMULAS, BINDINGS, meta={"app": "x"})
        data = import_config(out)
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["formula_set"], FORMULAS)
        self.assertEqual(len(data["bindings"]), 3)
        self.assertEqual(data["bindings"][0]["source_config"]["doctype"], "Item Price")
        self.assertEqual(data["bindings"][2]["source_config"], {"doctype": "Item", "fieldname": "weight_per_unit"})
        self.assertEqual(data["meta"]["app"], "x")

    def test_import_invalid_json_raises(self):
        with self.assertRaises(ConfigIOError):
            import_config("{not json")

    def test_import_wrong_schema_version_raises(self):
        out = export_config(FORMULAS)
        data = json.loads(out)
        data["schema_version"] = 99
        with self.assertRaises(ConfigIOError):
            import_config(json.dumps(data))

    def test_import_tampered_payload_checksum_fails(self):
        out = export_config(FORMULAS)
        data = json.loads(out)
        data["formula_set"][0]["formula"] = "x + 1"  # tamper
        with self.assertRaises(ConfigIOError):
            import_config(json.dumps(data))

    def test_import_empty_formula_set_raises(self):
        with self.assertRaises(ConfigIOError):
            import_config(json.dumps({"schema_version": 1, "formula_set": []}))

    def test_import_no_checksum_still_validates(self):
        data = {"schema_version": 1, "formula_set": FORMULAS}
        result = import_config(json.dumps(data))
        self.assertEqual(len(result["formula_set"]), 3)
        self.assertIsNone(result["checksum"])

    def test_import_missing_formula_set_raises(self):
        with self.assertRaises(ConfigIOError):
            import_config(json.dumps({"schema_version": 1}))


class TestRoundtrip(unittest.TestCase):
    def test_roundtrip_idempotent(self):
        first = export_config(FORMULAS, BINDINGS, meta={"name": "GT"})
        second = roundtrip(first)
        a = json.loads(first)
        b = json.loads(second)
        self.assertEqual(a["formula_set"], b["formula_set"])
        self.assertEqual(a["bindings"], b["bindings"])
        self.assertEqual(a["meta"], b["meta"])
        self.assertEqual(a["checksum"], b["checksum"])


if __name__ == "__main__":
    unittest.main()
