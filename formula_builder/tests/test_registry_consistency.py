"""Tests api/registry consistency — bịt "HAI registry" bằng MÁY (D7).

Vì sao có tệp này: `formula_builder` đăng ký **cùng một hàm handler 2 lần** —
decorator `@register_source(...)` ở cấp module, rồi
`_register_all_to_central_registry()` chạy sau lúc import.
`SourceTypeRegistry.register()` **ghi ngược** `handler.fingerprint_fn` /
`handler.batchable` lên chính **đối tượng hàm**, nên **bản đăng ký SAU thắng —
im lặng**, và bộ giải batch đọc thuộc tính trên HÀM (xem
`batch_binding_resolver.py::_get_fingerprint_fn`) chứ ⛔ không đọc bản ghi
trong registry.

Đã xảy ra thật 2026-10 với `linked_doctype_field` (fingerprint còn sót
`target_field` ⇒ mỗi field 1 nhóm ⇒ N+1 không giảm). Lần đó chỉ có test riêng
cho MỘT source type (`TestLinkedDoctypeFieldBatching`); tệp này khẳng định trên
**TOÀN BỘ** registry để các source type khác ⛔ không trôi y hệt mà ⛔ không gì
bắt được.

Lưu ý thứ tự import: phải import `data_source_registry` TRƯỚC để module-level
`_register_all_to_central_registry()` nạp built-in vào central
SourceTypeRegistry (import `source_type_registry` một mình → registry rỗng).
"""

from frappe.tests.utils import FrappeTestCase

from formula_builder.api.data_source_registry import _data_source_handlers
from formula_builder.api.source_type_registry import SourceTypeRegistry


# 19 source type do `formula_builder` đăng ký — đo trên đĩa 2026-10-03.
# Đây là khẳng định CHỐT SỐ: thêm/bớt source type ⇒ test này ĐỎ ⇒ buộc người
# sửa cập nhật CẢ tài liệu (README §6.5 / §9.4, docs/fb_source_type_contract.md)
# — tài liệu đã từng trôi 17 → 19 mà ⛔ không gì bắt được.
EXPECTED_SOURCE_TYPES = (
    "aggregate_from_items",
    "child_table_aggregate",
    "child_table_lookup",
    "composite_key_lookup",
    "computed",
    "conditional",
    "constant",
    "custom_function",
    "doctype_query",
    "dynamic_link",
    "fallback_chain",
    "global_default",
    "linked_doctype_field",
    "matrix_lookup",
    "pipeline",
    "range_lookup",
    "reuse_formula_result",
    "session_variable",
    "whole_doctype",
)

# `pipeline` khai `batchable=True` nhưng CỐ Ý ⛔ không có `resolve_batch`: bộ giải
# batch rơi về `_execute_individual` (chạy từng binding) — trạng thái HỢP LỆ đã
# được thiết kế, có test riêng
# (tests/test_platform_phase1.py::TestPreviewGroups::test_batchable_without_resolve_batch_is_individual).
# Miễn trừ TƯỜNG MINH: thêm tên vào đây phải kèm lý do, ⛔ cấm nới test cho xanh.
_NO_BATCH_RESOLVER = {"pipeline"}

# Fixture của test module KHÁC, đăng ký ở CHỈ MỘT chỗ bằng `@batchable(...)` rồi
# `@register_source(...)` mà ⛔ không truyền metadata vào `register_source`.
# Hệ quả: HÀM có `batchable=True` + `fingerprint_fn`, còn bản ghi registry thì
# ⛔ không có gì (registry **báo thiếu**, ⛔ không phải bẫy ghi đè D7 — chỉ một
# chỗ đăng ký nên ⛔ không có "bản sau thắng"). ✅ Lúc chạy vẫn đúng.
# Miễn trừ TƯỜNG MINH, ⛔ không được dùng cho source type THẬT của app
# (xem `test_exemptions_cannot_mask_shipped_source_types`).
_DECORATOR_ONLY_BATCHABLE = {
    "test_batchable",              # tests/test_batch_resolver.py:28
    "fb_phase1_batch_no_resolve",  # tests/test_platform_phase1.py:47
}


class TestRegistryConsistency(FrappeTestCase):
    """Khẳng định dict legacy `_data_source_handlers` và `SourceTypeRegistry`
    ⛔ không được lệch nhau — cả về TẬP TÊN lẫn METADATA đã gán ngược lên hàm.
    """

    def setUp(self):
        self.registry = SourceTypeRegistry.get_instance()
        self.legacy = _data_source_handlers
        self.registry_names = set(self.registry.list_source_type_names())
        self.legacy_names = set(self.legacy.keys())
        # So metadata chỉ trên tên CÓ Ở CẢ HAI (tên lệch đã do #1 bắt).
        self.common_names = sorted(self.registry_names & self.legacy_names)
        self.metadata_names = [
            n for n in self.common_names if n not in _DECORATOR_ONLY_BATCHABLE
        ]

    # ── #1: đối xứng hai chiều bằng TẬP TÊN ─────────────────────────────

    def test_both_registries_hold_the_same_types(self):
        """Bắt lỗi "đăng ký nửa vời".

        Handler dùng legacy decorator (hoặc khối đời cũ) mà ⛔ không được
        `_register_all_to_central_registry()` đẩy sang: `get_handler()` vẫn
        chạy nhưng nó thiếu khỏi admin UI, thiếu `config_schema` (⇒ config
        ⛔ không được validate) và mất metadata batch.
        """
        self.assertEqual(
            sorted(self.legacy_names - self.registry_names), [],
            "có trong _data_source_handlers nhưng THIẾU ở SourceTypeRegistry "
            "→ đăng ký nửa vời (thiếu admin UI / config_schema / metadata batch)",
        )
        self.assertEqual(
            sorted(self.registry_names - self.legacy_names), [],
            "có trong SourceTypeRegistry nhưng THIẾU ở _data_source_handlers "
            "→ code cũ gọi get_handler(source_type) sẽ ⛔ không thấy handler",
        )

    # ── #2: fingerprint_fn phải là CÙNG MỘT ĐỐI TƯỢNG HÀM ───────────────

    def test_fingerprint_fn_is_same_object_in_both_registries(self):
        """CHÍNH cái bẫy ghi đè — phải so bằng `is`, ⛔ không phải "bằng kết quả".

        Hai bản đăng ký trỏ về cùng một hàm, nên `handler.fingerprint_fn` và
        `registry.get(name).fingerprint_fn` phải là CÙNG một object. So bằng
        giá trị trả về sẽ ⛔ không bắt được ca "hai hàm khác nhau tình cờ trả
        cùng chuỗi" — mà đó lại đúng là ca trôi.
        """
        mismatched = [
            name
            for name in self.metadata_names
            if getattr(self.legacy[name], "fingerprint_fn", None)
            is not self.registry.get(name).fingerprint_fn
        ]
        self.assertEqual(
            mismatched, [],
            "fingerprint_fn lệch nhau giữa _data_source_handlers và "
            "SourceTypeRegistry → SourceTypeRegistry.register() đã gán đè lên "
            "hàm, bản đăng ký SAU thắng im lặng",
        )

    # ── #3: cờ batchable phải khớp giữa hai chỗ khai ────────────────────

    def test_batchable_flag_matches_between_registries(self):
        mismatched = [
            name
            for name in self.metadata_names
            if bool(getattr(self.legacy[name], "batchable", False))
            != bool(self.registry.get(name).batchable)
        ]
        self.assertEqual(
            mismatched, [],
            "cờ batchable lệch giữa handler (thuộc tính trên hàm) và bản ghi "
            "registry → is_batchable() và admin UI trả lời khác nhau",
        )

    # ── #4: batchable ⇒ phải có fingerprint + bộ giải batch ─────────────

    def test_batchable_types_have_fingerprint_and_batch_resolver(self):
        """Khai batchable mà thiếu fingerprint hoặc thiếu `resolve_batch`."""
        missing_fingerprint = []
        missing_resolver = []
        # CHỈ soi 19 tên của CHÍNH formula_builder (⛔ không soi app khác).
        # Vì sao: `alumglass/fb_handlers.py:53` và `:258` khai `batchable=True`
        # + `fingerprint_fn` mà ⛔ không có `resolve_batch` — nhưng FB ĐÃ coi
        # trạng thái đó là HỢP LỆ (xem `_NO_BATCH_RESOLVER` + fixture
        # `fb_phase1_batch_no_resolve`), nên FB ⛔ không có quyền bắt app khác
        # đỏ vì nó. Bẫy D7 (đăng ký 2 lần) là chuyện RIÊNG của FB: app ngoài
        # đăng ký MỘT chỗ qua hook `fb_source_types` ⇒ ⛔ không có bẫy đó.
        for name in sorted(set(EXPECTED_SOURCE_TYPES) & self.registry_names):
            definition = self.registry.get(name)
            if not definition.batchable:
                continue
            if definition.fingerprint_fn is None:
                missing_fingerprint.append(name)
            if name in _NO_BATCH_RESOLVER:
                continue
            handler = self.legacy.get(name) or definition.handler
            if not callable(getattr(handler, "resolve_batch", None)):
                missing_resolver.append(name)

        self.assertEqual(
            missing_fingerprint, [],
            "batchable=True nhưng thiếu fingerprint_fn → _group_by_fingerprint "
            "rơi về fingerprint mặc định, nhóm sai (gom nhầm = sai kết quả)",
        )
        self.assertEqual(
            missing_resolver, [],
            "batchable=True nhưng thiếu resolve_batch callable → cờ hứa có "
            "đường batch mà lúc chạy rơi về _execute_individual (N+1). Nếu là "
            "CỐ Ý, thêm tên vào _NO_BATCH_RESOLVER kèm lý do — ⛔ cấm nới test "
            "cho xanh",
        )

    # ── #5: chốt số 19 — dạng BAO HÀM ──────────────────────────────────

    def test_expected_source_types_are_registered(self):
        """19 tên phải ⊆ CẢ HAI registry.

        Dùng dạng BAO HÀM (⛔ không đòi bằng đúng): trên site thật app khác
        (alumglass…) đăng ký thêm qua hook `fb_source_types` — chúng ⛔ không
        được làm đỏ test này. Dạng bằng đúng sẽ vỡ ngay khi có app thứ hai.
        """
        expected = set(EXPECTED_SOURCE_TYPES)

        self.assertEqual(
            len(EXPECTED_SOURCE_TYPES), 19,
            "danh sách chốt số phải đúng 19 tên (đo trên đĩa 2026-10-03)",
        )
        self.assertEqual(
            list(EXPECTED_SOURCE_TYPES), sorted(EXPECTED_SOURCE_TYPES),
            "danh sách phải sắp xếp sẵn để diff khi thêm/bớt là tối thiểu",
        )
        self.assertEqual(
            sorted(expected - self.registry_names), [],
            "source type đã mất khỏi SourceTypeRegistry → cập nhật CẢ tài liệu "
            "(README §6.5 / §9.4, docs/fb_source_type_contract.md)",
        )
        self.assertEqual(
            sorted(expected - self.legacy_names), [],
            "source type đã mất khỏi _data_source_handlers → cập nhật CẢ tài liệu "
            "(README §6.5 / §9.4, docs/fb_source_type_contract.md)",
        )

    # ── Khoá chống "nới test cho xanh" ─────────────────────────────────

    def test_exemptions_cannot_mask_shipped_source_types(self):
        """⛔ Cấm dùng danh sách miễn trừ để che source type THẬT của app."""
        masked = sorted(set(_DECORATOR_ONLY_BATCHABLE) & set(EXPECTED_SOURCE_TYPES))
        self.assertEqual(
            masked, [],
            "source type THẬT của app ⛔ không được nằm trong danh sách miễn trừ "
            "→ sửa chỗ đăng ký cho khớp, ⛔ đừng thêm vào đây",
        )
        unknown = sorted(_NO_BATCH_RESOLVER - self.registry_names)
        self.assertEqual(
            unknown, [],
            "_NO_BATCH_RESOLVER có tên ⛔ không tồn tại trong registry → miễn "
            "trừ đã mục, gỡ ra",
        )

    def test_decorator_only_exemptions_stay_honest(self):
        """Miễn trừ chỉ đúng khi bản ghi registry ⛔ không khai gì.

        Nếu fixture được sửa để khai metadata đầy đủ (hoặc bị đổi tên) thì
        dòng miễn trừ thành mục ⇒ test ĐỎ ⇒ gỡ tên ra khỏi
        `_DECORATOR_ONLY_BATCHABLE`.
        """
        stale = []
        for name in sorted(_DECORATOR_ONLY_BATCHABLE & self.registry_names):
            definition = self.registry.get(name)
            if definition.batchable or definition.fingerprint_fn is not None:
                stale.append(name)
        self.assertEqual(
            stale, [],
            "tên trong _DECORATOR_ONLY_BATCHABLE nay ĐÃ có metadata trong "
            "registry → miễn trừ đã mục, gỡ ra khỏi danh sách",
        )
