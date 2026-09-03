# Đề xuất cải tiến cơ chế tính giá Quotation — hợp nhất Formula Builder + AlumGlass

> **Status:** ✅ **ĐÃ TRIỂN KHAI 2026-09-03** (Phase 0–4, job `2026-09-03_alumglass-patch3-merge-fb-platform-ph0-1`) — proposal này từng là DRAFT chờ Owner; sau khi Owner duyệt (2026-09-03) code + docs đã merge (KHÔNG verify site/golden theo job scope). Mô tả bên dưới giữ as-is làm bản ghi đề xuất — đối chiếu trạng thái thực tế: ADR `fvb-single-resolution-layer.md` §10/§12 + `alumglass/docs/design/p3-quotation-pricing-patch-3-full.md`.
> **Date:** 2026-09-01 (đề xuất) — trạng thái cập nhật 2026-09-03
> **Author:** SA1
> **Scope:** formula_builder (platform) + alumglass (app case study) — 1 roadmap hợp nhất cả 2 tầng
> **Liên quan (tham chiếu chéo, KHÔNG thay thế):**
> - `docs/design/co_che_tinh_gia_quotation.md` — cơ chế hiện tại (3 tầng, 8 phase B0–B7, 7 nguồn biến, composite pricing, 2 cơ chế snapshot)
> - `docs/design/review1.md` — review khi áp patch-3: kính đại diện, `cost_bucket_aggregate` deprecated, FVB chưa seed, N+1 pipeline/custom_function, đề xuất `chain_link_lookup`
> - `docs/design/fvb-single-resolution-layer.md` — ADR **Owner đã duyệt 2026-08-31** (dừng ở design, chưa triển khai): FVB = single resolution layer, 17 source_type, gap Select tĩnh 13 option, lộ trình Phase 0–4
> **Ràng buộc vàng:** mọi phase KHÔNG được phá golden `CDMQ-2C = 22,717,289` / `CDMQ-4C = 47,430,808` (chốt dashboard 2026-08-18)

---

## Trạng thái triển khai theo mục (2026-09-03)

> Mục nào trong proposal đã ĐÓNG (đối chiếu với code thật hiện tại):

| Mục | Nội dung | Trạng thái |
| --- | --- | --- |
| §1.2 | Bằng chứng patch-3-full CHƯA merge app thật | ✅ **ĐÃ ĐÓNG** — Phase 0 merge 2026-09-03 (app-side DEV1, xem alumglass p3 doc). Bảng bên dưới giữ as-is để đối chiếu lịch sử. |
| §3A A1–A5 | Platform formula_builder (FVB Admin/dropdown/test/preview/scope) | ✅ **ĐÃ ĐÓNG** — Phase 1 delivered (ADR §10, 2026-09-03). |
| §3B | App alumglass — áp patch-3-full (Phase 0) | ✅ **ĐÃ ĐÓNG (code)** — merge song song 2026-09-03; CHƯA migrate site/golden. |
| §3C C1 | Seed FVB đầy đủ + engine FB-first | ✅ **ĐÃ ĐÓNG (platform contract)** — app-side DEV1 (ADR §12.1). |
| §3C C2 | Migrate `cost_bucket_aggregate` → `aggregate_from_items` | ✅ **ĐÃ ĐÓNG (contract)** — `docs/aggregate_from_items.md` mục migration (ADR §12.2). |
| §3C C3–C5 | chain_link_lookup / batch cảnh báo / price_list seed | C5 fix app-side (install_fb_bindings seed động, xem p3 doc §E); C3/C4 là known-limitation ghi trong docs — xem lại theo quyết định DEV1. |
| §4 Phase 1 | A1–A5 + C5 | ✅ **ĐÃ ĐÓNG** (ADR §10; C5 trong p3 doc). |
| §4 Phase 2/3 | Seed FVB, FB-first, retire path cũ, migrate bucket | ✅ **ĐÃ ĐÓNG (code/contract)** — ADR §12.1–12.2; app-side DEV1. |
| §4 Phase 4 | Vệ sinh + docs | ✅ **ĐÃ ĐÓNG (docs platform)** — file này + ADR §12 + co_che note. |
| §5 AC | Golden CDMQ-2C/4C | ⛔ **CHỜ VERIFY SITE** — job scope không verify site; golden phải chạy sau migrate. |
| §6 File map | — | Giữ as-is làm chỉ dẫn; commit thật trong log git từng repo. |

---

## 0. Tóm tắt điều hành

Báo giá Quotation của AlumGlass hiện chạy đúng nhưng đang **mang 2 kiến trúc tính giá song song** (đường cũ Python fallback + đường mới Formula Variable Binding/FB-max) chưa được gộp, và gói vá `alumglass-patch-3-full` (V6 P10) — thứ giải quyết kính/vật tư mã đại diện theo từng vị trí, validate công thức, zero-hardcode C1–C9, workflow thật, seed FB binding — **CHƯA merge vào app thật** (verify bằng code, mục 1.2). Đề xuất này chốt **1 roadmap hợp nhất 2 tầng**: (Phase 0) áp patch-3-full vào app alumglass → (Phase 1) platform formula_builder bổ sung FVB Admin UI + dropdown động + test-binding có doc → (Phase 2) seed FVB đầy đủ từ AL Variable Library → (Phase 3) retire path cũ + migrate `cost_bucket_aggregate` → `aggregate_from_items` → (Phase 4) vệ sinh + docs. Mỗi phase tách biệt, revert được, gate ra bằng **golden 2C/4C không đổi**. Rủi ro lớn nhất là bật FB-max pricing ở Phase 0 — có lưới an toàn `is_active=0`. Phát hiện thêm của SA1 ngoài 6 điểm Elon: seed binding `install_fb_bindings.py` còn hardcode `price_list="Standard Selling"`, lệch với C1 (engine đọc Selling Settings) — cần đồng bộ ở Phase 1/2.

## 1. Bối cảnh & trạng thái verified

### 1.1 Ba nguồn đầu vào

| Nguồn | Nội dung | Vai trò trong đề xuất |
|---|---|---|
| `co_che_tinh_gia_quotation.md` | Cơ chế hiện tại: BomOrchestrator 8 phase B0–B7, 7 nguồn biến, composite key + best-partial-match, 2 snapshot | **As-is** — đề xuất không lặp lại, chỉ tóm tắt + trỏ sang |
| `review1.md` | Review khi áp patch-3: kính đại diện đúng, `cost_bucket_aggregate` deprecated chưa migrate, FVB chưa seed pricing, pipeline/custom_function N+1, đề xuất `chain_link_lookup` | Nguồn phát hiện gap + giải pháp `chain_link_lookup` |
| `fvb-single-resolution-layer.md` | ADR đã duyệt 2026-08-31: FVB = single resolution layer, 17 source_type, Admin UI, lộ trình Phase 0–4 | **Kế hoạch platform** — đề xuất này hợp nhất với patch-3-full |

### 1.2 ⚠ BẢNG BẰNG CHỨNG — patch-3-full CHƯA merge vào app alumglass thật (quan trọng nhất)

Đây là tiền đề của toàn bộ lộ trình: **cải tiến lớn nhất (kính đại diện theo vị trí, zero-hardcode, workflow, seed FB binding) vẫn nằm trong gói vá, chưa phải là hành vi app thật đang chạy.**

| Bằng chứng | App thật (`alumglass/`) | Gói patch-3-full | Kết luận |
|---|---|---|---|
| `engine/bom_orchestrator.py` | 1439 dòng; grep 0 lần `_resolve_glass_override` / `_category_by_code` / `_dim_fieldnames_for_category` / `glass_master_map` / `_get_dim_mappings_raw` / `_default_price_list` / `composite_pricing` | 1575 dòng; đủ các hàm trên | Thật **thiếu** toàn bộ logic Phần A/E |
| `engine/composite_pricing.py` | KHÔNG tồn tại | Có (`best_partial_match`, 60 dòng) | Thật thiếu — 2 nhánh tra giá vẫn dùng 2 thuật toán |
| `al_bom_engine/formula_validate.py` | KHÔNG tồn tại (thư mục `al_bom_engine/` chỉ có `doctype/`) | Có (111 dòng) | Thật thiếu lớp validate dùng chung |
| `al_bom_engine/system_variable_resolver.py` | KHÔNG tồn tại | Có (113 dòng) | Thật thiếu — `_resolve_doc_values` vẫn hardcode (xem dưới) |
| `setup/install_workflows.py` | KHÔNG tồn tại (`setup/` chỉ có `custom_fields.py`, `install_roles.py`, `print_format.py`, `seed_demo_data.py`) | Có (4 workflow) | Thật thiếu workflow thật |
| `setup/install_fb_bindings.py` | KHÔNG tồn tại | Có (seed `COMPOSITE_MATERIAL_PRICE`) | Thật thiếu → FB-max pricing **chưa bao giờ chạy thật** |
| `patches/v28_10/` | KHÔNG (chỉ có `v28_9`) | Có (`rebackfill_snapshot_category_final_price.py`) | Thật thiếu backfill snapshot category |
| `api/__init__.py` | Không có `_resolve_variable_set_name` / `get_allowed_formula_functions`; `_resolve_doc_values` (dòng 213–240) hardcode `for f in ["offset_frame","offset_glass","offset_fixed","offset_crossbar"]: vals[f.upper()] = ps.get(f)` → sinh `OFFSET_CROSSBAR` thay vì biến thật `OFFSET_DO_NGANG` (bug D12) | Có `_resolve_variable_set_name`, `get_allowed_formula_functions`, `_resolve_doc_values` gọi `system_variable_resolver` | Thật **đang mắc bug autocomplete D12** |
| Git commit | `084896c` "chore: import code mới từ remote AlumGlass main … gói vá V6 P10" — chỉ thêm file vào `alumglass-patch-3-full/` (package tham chiếu) | — | **Chưa merge** — commit chỉ import gói, không đè vào `alumglass/` |

**Khác biệt hành vi cụ thể giữa thật và patch** (đã đọc 2 bản, không suy đoán):

| Điểm | App thật | Patch-3-full |
|---|---|---|
| `_load_accessories` | Hardcode `"calc_pattern": "COUNT", "cost_bucket": "VL_PK"` cho mọi dòng phụ kiện | `acc.get("calc_pattern") or "COUNT"` — đọc field mới trên `AL Accessory Item` (C2) |
| `_fetch_composite_prices` | Hardcode `price_list="Standard Selling"` (2 chỗ: dòng ~660, ~870) | `_default_price_list()` đọc `Selling Settings.selling_price_list` (C1) |
| `_match_composite_price` | Thuật toán best-partial-match **inline** (dòng 881–915) | Wrapper gọi `composite_pricing.best_partial_match` (dùng chung cả 2 nhánh) |
| `_fetch_composite_prices_via_fb` | `row_ctx` **không có `category`** (dòng 830–849) → nếu bật FB-max sẽ tái phát bug material_category | `row_ctx["category"]` + `row_ctx["row"]["category"]` qua `_category_by_code()` (E3) |
| `fb_handlers.aluminum_price_composite` exact_match | AND-filter cứng qua DB (`filters.append([cfn,"=",value])`) — khác thuật toán với fallback | Gọi `best_partial_match` — 2 nhánh cùng 1 thuật toán |
| `b6_calculate_cost_template` override snapshot | Không có `is_final_price` trong dict build | Có `is_final_price` (C3) |
| Kính đa vị trí | Chỉ hỗ trợ `glass_master_override` **global 1 mã cho cả BOM**; engine không đọc `glass_master_map` | `_resolve_glass_override(rep_code)` ưu tiên per-position (`glass_master_map`), batch fetch cả map (A) |

→ **Hệ quả:** app thật đang chạy đường Python fallback + kính 1-mã-global; mọi giá trị của patch-3-full nằm chờ merge. Đây chính là lý do Phase 0 (áp patch) phải đi đầu.

## 2. Hiện trạng (as-is) — tóm tắt

Chi tiết đầy đủ tại `co_che_tinh_gia_quotation.md` (mục 1–14). Tóm tắt để đọc đề xuất này không cần mở lại tài liệu kia:

- **3 tầng:** Tầng 1 dữ liệu (DocTypes AL*) → Tầng 2 `BomOrchestrator` (module `engine/`, 8 phase B0–B7) → Tầng 3 `formula_builder` (`FormulaEngine` B4 + `FlexibleFormulaEngine` B6, sandbox AST). AlumGlass **không tự eval** công thức.
- **7 nguồn biến** resolve trong `b1_gather_inputs` theo thứ tự 1.1→1.6; nguồn sau đè nguồn trước; user luôn thắng cuối (trừ override `_accessory_set`/`_profile_system`/`_cost_template`/`glass_master`).
- **Composite pricing:** `price_base_item` = mã đại diện tra giá; trọng lượng theo `item_code` thật. Matching **best-partial-match** (field trống = wildcard). Kính thêm tầng đổi theo vị trí.
- **2 đường song song (đang di trú, có chủ đích):** đường CŨ (alumglass tự viết: `system_variable_resolver`, `_fetch_composite_prices`, sum Python bucket) và đường MỚI (FVB: `linked_doctype_field`, `aluminum_price_composite`, `aggregate_from_items`). Đường mới ưu tiên nếu binding `is_active=1`; đường cũ là lưới an toàn.
- **Snapshot:** `AL BOM Version` snapshot CẤU HÌNH (bất biến, engine B0–B6 đọc) vs `ConfigSnapshot` snapshot KẾT QUẢ (tạo khi Submit Quotation, audit trail).
- **Ranh giới hiện tại:** 3 source type custom alumglass (`aluminum_price_composite`, `glass_master_data`, `cost_bucket_aggregate` — deprecated), đăng ký qua `@register_source` + `hooks.py::fb_source_types`.

## 3. Nhóm cải tiến đề xuất

### A. Platform formula_builder (theo ADR đã duyệt 2026-08-31)

Thực thi đúng `fvb-single-resolution-layer.md` §5–6 — không thiết kế lại:

| # | Cải tiến | Bằng chứng gap | Vị trí code |
|---|---|---|---|
| A1 | **Dropdown `source_type` động** — FVB đang là Select tĩnh 13 option; 4 built-in mới (`matrix_lookup`, `reuse_formula_result`, `composite_key_lookup`, `aggregate_from_items`) + mọi custom type **không chọn được qua Form chuẩn** | `formula_variable_binding.json` options = 13; registry có 17 | FVB json + `...formula_variable_binding.js`; `source_type_registry.py:596 list_source_types` |
| A2 | **Form động `source_config` theo `config_schema`** (kể cả `required_unless` như `aggregate_from_items.value_field`) | `get_source_type_schema`/`validate_binding_source_config` có sẵn nhưng Form không dùng | `source_type_registry.py:606,624` |
| A3 | **`test_data_source_with_doc(source_type, config, doctype, docname, resolved_context)`** — `test_data_source` hiện gọi `handler(binding, doc=None, resolved_so_far={})` → chỉ test được source không cần doc | đọc thật: `source_type_registry.py:652–700` | thêm API cạnh `test_data_source` |
| A4 | **`preview_batch_groups(doctype, docname)`** — hiện "10 binding → N batch query" trước khi deploy | `_execute_one_group`/`_group_by_fingerprint` có sẵn logic, chưa lộ API | `batch_binding_resolver.py:426` |
| A5 | **Chuẩn hoá scope semantics**: `get_live_context` đã lọc `applies_to_field` trong Python; `_get_pricing_bindings` chỉ lọc `applies_to_doctype` → lệch preview vs runtime | `formula_builder.py:316–329` vs `bom_orchestrator.py:783–808` | `bom_orchestrator._get_pricing_bindings` (alumglass) |

### B. App alumglass — áp patch-3-full (Phase 0)

Đây là nhóm cải tiến **nằm sẵn trong gói patch**, cần merge đúng + regression:

| Mã | Nội dung | File chính |
|---|---|---|
| A | Kính/vật tư mã đại diện theo vị trí: `_resolve_glass_override` per-line, batch fetch `glass_master_map.values()`, lọc dimension theo `material_category` (`_dim_fieldnames_for_category`), gộp 2 nhánh tra giá về `composite_pricing.best_partial_match` | `engine/bom_orchestrator.py`, `engine/composite_pricing.py` (mới), `fb_handlers.py` |
| B | Validate công thức dùng chung 4 doctype thiếu (AL Bom Set/Item, Accessory Set, Alert Config) — normalize cross-row bằng đúng `normalize_global` của FB | `al_bom_engine/formula_validate.py` (mới), wiring vào các `al_*.py` |
| C1–C9 | Zero-hardcode: price list từ Selling Settings, `calc_pattern`/`cost_bucket` phụ kiện, `is_final_price` (C3), `_resolve_variable_set_name` (C4), `is_pricing_dimension` (C5), `get_allowed_formula_functions` (C6), gộp handler Preview (C7), xoá `bom_set_context.js` (C8), `FORMULA_DOCTYPE_REGISTRY` (C9) | `bom_orchestrator.py`, `api/__init__.py`, `quotation.js`, `formula_setup.js`, `cost_template.js`, `al_cost_template.js` |
| D11 | Workflow thật cho 4 doctype (`AL BOM Version`, `AL Change Order`, `AL Dynamic Item Rule Version`, `AL Design Revision`) — role-gating transition thay `workflow_state` Select tự chế | `setup/install_workflows.py` (mới), `hooks.py::_after_migrate` |
| D12 | Generalize `_resolve_doc_values` — bỏ hardcode 2 doctype + 4 offset field; sửa bug `OFFSET_CROSSBAR` → `OFFSET_DO_NGANG` | `al_bom_engine/system_variable_resolver.py` (mới), `api/__init__.py`, `bom_orchestrator._resolve_system_variables` |
| E | Seed FB binding pricing (`COMPOSITE_MATERIAL_PRICE`, `aluminum_price_composite`, exact_match, global) — **bật FB-max pricing thật** | `setup/install_fb_bindings.py` (mới), `hooks.py` |
| v28_10 | Backfill snapshot category + `is_final_price` cho BOM Version Published cũ | `patches/v28_10/rebackfill_snapshot_category_final_price.py` |

> **Lưu ý merge:** `hooks.py`, `patches.txt`, `quotation.js`, `al_bom_version.py`, `al_cost_template.py` là file app thật **đã có thay đổi riêng** — không copy đè trực tiếp, phải diff từng file. README patch đã cảnh báo điều này (mục "Lưu ý JSON").

### C. Tối đa hoá formula_builder trong engine (tận dụng FB hết mức)

| Mã | Cải tiến | Lý do / bằng chứng |
|---|---|---|
| C1 | **Seed FVB đầy đủ (mở rộng D3)** — seed cho MỌI system var có `source_doctype`+`source_field`, không chỉ 2 doctype trong `_LINK_BY_SOURCE_DOCTYPE`. Nguồn link_field: dùng chính `system_variable_resolver.resolve_source_record_names` (D12) tự dò Link field | ADR §1.2/§6 Phase 1: hiện B1.3 (Variable Library) và B1.4 (FVB) chạy song song — duplication; muốn retire path cũ phải FVB phủ 100% |
| C2 | **Migrate `cost_bucket_aggregate` → `aggregate_from_items`**: convert Cost Bucket record (`source_type=cost_bucket_aggregate`, `filter_by`/`sum_field`) sang `aggregate_from_items` (`rows_source=snapshot`, `snapshot_doctype=AL BOM Version`, `snapshot_field=bom_set_snapshot`, `rows_path=items`), rồi gỡ handler khỏi `fb_handlers.py` + `hooks.py::fb_source_types` (dòng 70) | `cost_bucket_aggregate` deprecated: `batchable=False`, chỉ 1 nguồn rows, filter `==` duy nhất; `aggregate_from_items` native: 3 nguồn rows + 7 operator + có `resolve_batch` (ADR §3.1, review1). Patch-3-full CHƯA migrate — "Phase B sẽ quyết migration" vẫn chưa làm |
| C3 | **`chain_link_lookup` (custom_function generic multi-hop)** — join 2–3 cấp doctype (Quotation Item → AL BOM → AL Bom Set → AL Profile System.field) qua 1 hàm dùng chung; inner dùng `get_cached_value`; docstring cảnh báo KHÔNG dùng cho binding per-line BOM quy mô lớn | review1: `linked_doctype_field`/`doctype_query` chỉ đọc field từ doc GỐC, không đọc `resolved_so_far` → pipeline cần bước custom_function làm cầu. `pipeline`/`custom_function` **không có `resolve_batch`** → `_execute_one_group` fallback `_execute_individual` = N+1 nếu per-line (đã verify: 7/17 handler có batch, pipeline/custom_function không) |
| C4 | **Cảnh báo batch per-line BOM** — binding dùng `custom_function`/`pipeline` resolve theo từng dòng BOM sẽ thành `số_dòng × số_chặng` query; ghi "known limitation" trong docs + preview batch (A4) hiển thị trước | `batch_binding_resolver.py:426–455` Strategy 3 fallback individual |
| C5 | **Đồng bộ price_list seed binding**: `install_fb_bindings.py` seed `source_config={"price_list": "Standard Selling"}` **cứng** — trong khi C1 (patch) làm engine đọc Selling Settings. Nếu Selling Settings đổi, FB-max (đọc binding config) lệch fallback (đọc `_default_price_list`) → 2 đường lại khác số | **Phát hiện mới của SA1** khi đối chiếu `install_fb_bindings.py:35–37` với `bom_orchestrator.py::_default_price_list`. Fix: seed theo `Selling Settings.selling_price_list` tại lúc seed, hoặc để handler fallback `_default_price_list()` khi cfg không có `price_list` |

## 4. Lộ trình theo phase (an toàn golden — 2C/4C không đổi, mỗi phase tách + revert được)

> Nguyên tắc: mỗi phase là 1 commit/merge riêng, có gate ra = regression golden, có đường revert. **Không nhảy tắt Phase 3 trước khi FVB phủ 100%** (rủi ro phá golden đúng kiểu ADR §6 cảnh báo — `""` override `OFFSET_FRAME=48`).

### Phase 0 — Áp patch-3-full vào app alumglass (Phase ĐẦU theo chốt Owner)

- **Việc:** merge từng file gói patch vào app thật (xem §3B + File map §6). Bench migrate → chạy `v28_10` + `install_workflows` + `install_fb_bindings`; clear-cache; restart. Chạy checklist test README_TONG_HOP (Phần A–E).
- **Điểm đặc biệt:** phase này **bật FB-max pricing thật** (install_fb_bindings) — đây là thay đổi hành vi tính giá lớn nhất của cả lộ trình. Lưới an toàn: `COMPOSITE_MATERIAL_PRICE` có `is_active=1`; nếu golden lệch → set `is_active=0` là quay về Python fallback, không cần revert code.
- **Gate ra (exit):** checklist Phần A/B/C/D/E pass; **golden CDMQ-2C=22,717,289 / CDMQ-4C=47,430,808 KHÔNG đổi** kể cả khi xác nhận `_fetch_composite_prices_via_fb` thực sự được gọi (không trả None).
- **Revert:** revert commit merge; hoặc set binding `is_active=0`.
- **Không phụ thuộc Phase 1:** binding seed bằng code, không qua UI → không cần chờ FVB Admin UI.

### Phase 1 — Platform formula_builder: FVB Admin UI + dropdown động + gap scope

- **Việc:** A1–A5 (§3A) — dropdown động, form `source_config`, `test_data_source_with_doc`, `preview_batch_groups`, chuẩn hoá scope semantics (`_get_pricing_bindings` đọc `applies_to_field`). **C5** (đồng bộ price_list seed binding) cũng xử lý trong phase này.
- **Gate ra:** admin tạo được binding `composite_key_lookup`/`aggregate_from_items` qua UI; test binding có doc resolve đúng; preview scope khớp runtime. App alumglass **chưa đổi hành vi** — golden không bị ảnh hưởng bởi phase này (chỉ kiểm tra regression định kỳ).
- **Revert:** additive, bỏ commit platform là xong.

### Phase 2 — Seed FVB đầy đủ (mở rộng D3) + golden regression

- **Việc:** mở rộng `patches/v28_9/seed_fvb_from_variable_library.py` (idempotent, check `(variable_name, applies_to_doctype, is_global)` trước insert) sang **mọi system var có source + field**; nguồn link_field = `system_variable_resolver.resolve_source_record_names`. Seed `chain_link_lookup` binding nếu có nhu cầu multi-hop thật (C3). **KHÔNG xoá** `source_doctype`/`source_field` trên Variable Library ở phase này.
- **Gate ra:** FVB phủ 100% system vars có source (verify: B1.3 resolve ra giá trị giống B1.4 cho mọi biến); golden 2C/4C không đổi (đúng cơ chế D3 đã chứng minh).
- **Revert:** giữ patch cũ không chạy lại; hoặc gỡ record FVB seed thêm.

### Phase 3 — Retire path cũ (FVB thành nguồn duy nhất) + migrate bucket

- **Việc:**
  - Đảo ưu tiên B1: engine đọc FVB trước, chỉ fallback B1.3 khi biến chưa có FVB (guard `if var not in fb_ctx`). Khi không còn system var nào phải resolve bởi B1.3 → đánh dấu `source_doctype`/`source_field` **deprecated** (no-op, giữ data cũ) và bỏ nhánh 1.3 (hoặc giữ defensive no-op).
  - **C2:** migrate `cost_bucket_aggregate` → `aggregate_from_items` (convert record + gỡ handler khỏi `fb_handlers.py` + `hooks.py::fb_source_types`).
  - **D7 (từ review1/README):** thay `al_gia_ban` hardcode `cost_result.get("GIA_BAN", 0)` bằng field `is_pre_vat_price` (Check) hoặc Select — song song C3 `is_final_price`.
  - Cập nhật `get_formula_context()` bỏ mô tả theo `source_doctype/source_field` của system var.
- **Gate ra:** log/guard xác nhận path cũ không còn được gọi trong vận hành; golden 2C/4C không đổi.
- **Revert:** đảo ngược commit đảo ưu tiên.

### Phase 4 — Vệ sinh + docs

- **Việc:** cập nhật `alumglass/docs/quotation-pricing-flow.md` §2.2/§6 (FVB không còn "chưa seed"), `alumglass/docs/design/fvb-seed.md`, `review1.md` → "đã xử lý", `co_che_tinh_gia_quotation.md` (bổ sung cơ chế mới: kính theo vị trí, FB-max pricing active, workflow thật), đổi status ADR `fvb-single-resolution-layer.md` → "đã triển khai". Rà còn dead code (C8 đã xoá `bom_set_context.js`; C9 registry gộp; cache trùng D10).
- **Gate ra:** docs đồng bộ code tại thời điểm đóng phase; không còn path cũ/field deprecated được tham chiếu.
- **Revert:** không cần (docs-only, sau khi code đã ổn định).

## 5. Rủi ro & AC

### Rủi ro

| # | Rủi ro | Mức | Giảm thiểu |
|---|---|---|---|
| R1 | **Phá golden 2C/4C** khi bật FB-max pricing (Phase 0) | CAO | Gate cứng mọi phase: chạy regression; lệch → `is_active=0` binding (quay fallback) hoặc revert commit. Không đi tiếp phase sau khi chưa hết lệch |
| R2 | **Merge thủ công đè mất thay đổi app thật** (hooks.py, quotation.js, al_bom_version.py, al_cost_template.py, patches.txt) | CAO | Diff từng file trước copy; tuân thủ "Lưu ý JSON" của README (idx/docstatus); commit merge riêng phase 0 để dễ revert |
| R3 | Global binding `COMPOSITE_MATERIAL_PRICE` (`applies_to_doctype=""`) xuất hiện trong `get_live_context` của mọi doctype, resolve về 0 khi thiếu context → lọt vào autocomplete/formula | THẤP | AC A-3: filter biến này khỏi variables UI (không hiển thị khi không có context) |
| R4 | `chain_link_lookup` (custom_function) bị dùng sai cho binding per-line BOM lớn → N+1 query | TRUNG BÌNH | docstring cảnh báo + `get_cached_value` + preview batch (A4) hiển thị trước khi deploy |
| R5 | Migrate `cost_bucket_aggregate` convert sai cú pháp `aggregate_from_items` → bucket lệch số | TRUNG BÌNH | Convert + test bằng golden bucket VL_* trước khi gỡ handler; giữ handler chờ Phase 4 |
| R6 | `system_variable_resolver` (D12) đổi `source_records` từ hardcode sang tự dò Link → thiếu Link field cho 1 source_doctype mới = biến không resolve (fallback default) | THẤP | Gate: autocomplete + tính toán thật hiện đúng biến; golden phủ |
| R7 | C5: FB-max đọc `price_list` binding ("Standard Selling") lệch fallback đọc Selling Settings | TRUNG BÌNH | Xử lý trong Phase 1 — seed theo Selling Settings hoặc handler fallback `_default_price_list()` |

### AC (Acceptance Criteria)

- **A-1 (Golden, mọi phase):** `CDMQ-2C = 22,717,289` và `CDMQ-4C = 47,430,808` sau mỗi phase. KHÔNG có phase nào được đóng khi golden lệch.
- **A-2 (Phase 0):** `Formula Variable Binding` có đúng 1 record `COMPOSITE_MATERIAL_PRICE` (source_type=`aluminum_price_composite`, `is_active=1`); log xác nhận `_fetch_composite_prices_via_fb` không trả None; kính đổi theo vị trí → giá + nẹp tra đúng từng vị trí; validate AL Bom Set/Accessory Set/Alert Config chặn sai biến; workflow thật 4 doctype hiện nút theo role.
- **A-3 (Phase 1):** dropdown `source_type` chọn được 17 built-in + custom; `test_data_source_with_doc` resolve được `linked_doctype_field`/`composite_key_lookup` trên doc thật; `preview_batch_groups` hiển thị grouping; scope preview khớp runtime (`applies_to_field` được tôn trọng ở `_get_pricing_bindings`).
- **A-4 (Phase 2):** FVB phủ 100% system var có source; autocomplete hiện biến đúng tên (không còn `OFFSET_CROSSBAR`).
- **A-5 (Phase 3):** không còn path cũ được gọi trong vận hành (guard log rỗng); không còn `cost_bucket_aggregate` trong `hooks.py::fb_source_types`.
- **A-6 (Phase 4):** docs đồng bộ code; status ADR `fvb-single-resolution-layer.md` = đã triển khai.

## 6. File map cho DEV

### Platform formula_builder

| Việc | File/API |
|---|---|
| Dropdown động + form `source_config` | `doctype/formula_variable_binding/formula_variable_binding.json` (Select→Data), `...formula_variable_binding.js` (hiện rỗng); dữ liệu từ `api/source_type_registry.py:596 list_source_types`, `:606 get_source_type_schema`, `:624 validate_binding_source_config` |
| Test có doc | `api/source_type_registry.py` — thêm `test_data_source_with_doc` cạnh `test_data_source` (:652, hiện `doc=None`) |
| Preview batch groups | `api/batch_binding_resolver.py` — lộ `_group_by_fingerprint`/`_execute_one_group` (:426) thành API preview |
| Scope preview (rule) | `api/formula_builder.py:274 get_live_context` (:316–329 — lọc `applies_to_field` trong Python) |

### App alumglass (Phase 0 merge patch-3-full)

| Việc | File |
|---|---|
| Kính/vật tư mã đại diện + category filter | `engine/bom_orchestrator.py` (`_resolve_glass_override`, `_category_by_code`, `_dim_fieldnames_for_category`, `_fetch_composite_prices*`), `engine/composite_pricing.py` (mới) |
| Validate công thức | `al_bom_engine/formula_validate.py` (mới); wiring: `doctype/al_bom_set/al_bom_set.py`, `al_bom_item.py`, `al_accessory_set.py`, `al_alert_config.py` |
| Zero-hardcode C1–C9 | `bom_orchestrator.py` (`_default_price_list`), `api/__init__.py` (`_resolve_variable_set_name`, `get_allowed_formula_functions`), `doctype/overrides/quotation.js`, `public/js/formula_setup.js`, `cost_template.js`, `al_cost_template.js` |
| Workflow thật | `setup/install_workflows.py` (mới), `hooks.py` |
| Seed FB binding + resolve system var | `setup/install_fb_bindings.py` (mới), `al_bom_engine/system_variable_resolver.py` (mới), `hooks.py::fb_source_types` |
| Backfill snapshot | `patches/v28_10/rebackfill_snapshot_category_final_price.py` (mới), `patches.txt` |
| Migration bucket + retire (Phase 3) | `bom_orchestrator._resolve_system_variables`/`_resolve_fb_context` (đảo ưu tiên), `fb_handlers.py` (gỡ `cost_bucket_aggregate`), `hooks.py:70` |
| C5 price_list seed | `setup/install_fb_bindings.py` (seed theo `Selling Settings`) hoặc `fb_handlers.aluminum_price_composite` (fallback `_default_price_list`) |

## 7. Out of scope

- **Batch-optimize inner steps** của `pipeline`/`conditional`/`fallback_chain` (D6 ADR) — known limitation, có `get_cached_value` + cảnh báo.
- **Monaco / formula workspace**: Admin UI FVB chỉ quản lý biến, không quản lý công thức.
- **RBAC chi tiết FVB**: hiện chỉ `System Manager`, đủ giai đoạn này.
- **Merge legacy `Formula Global Variable` vào FVB** — việc riêng, làm sau khi FVB admin ổn định.
- **Migrate `matrix_lookup` → `composite_key_lookup`** — giữ backward-compat.
- **Dời `aluminum_price_composite` sang built-in `composite_key_lookup`** — ADR D1 giữ custom handler (best_partial_match ≠ fallback_keys tường minh); chỉ khi AL bỏ lớp Mapping mới xét.
- **Scope đa chiều (company/role/context)** — chỉ làm khi có app thứ 2 có nhu cầu.
- **Xây doctype mapping mới "biến → doctype → field"** — đã loại ở ADR Q1 (FVB đủ).

## Phụ lục A — Bảng verify code (đã đọc thật 2026-09-01)

| Claim | Bằng chứng (file:dòng) |
|---|---|
| `bom_orchestrator.py` thật = 1439 dòng, patch = 1575 | `wc -l` cả 2; grep thật 0 hit `_resolve_glass_override`/`_category_by_code`/`_dim_fieldnames_for_category`/`glass_master_map`/`_get_dim_mappings_raw`/`_default_price_list`/`composite_pricing` |
| `engine/` thật chỉ `__init__.py` + `bom_orchestrator.py`; thiếu `composite_pricing.py` | `ls engine/` |
| `setup/` thật thiếu `install_workflows.py`/`install_fb_bindings.py` | `ls setup/` (chỉ custom_fields, install_roles, print_format, seed_demo_data) |
| `al_bom_engine/` thật thiếu `formula_validate.py`/`system_variable_resolver.py` | `ls al_bom_engine/` (chỉ `doctype/`) |
| `patches/` thật chỉ có `v28_9`, thiếu `v28_10` | `ls patches/` |
| `_resolve_doc_values` thật hardcode 4 offset field → `OFFSET_CROSSBAR` (bug D12) | `alumglass/api/__init__.py:213–240` |
| Thật thiếu `_resolve_variable_set_name`/`get_allowed_formula_functions` | `grep` trong `alumglass/api/__init__.py` |
| Commit `084896c` chỉ import gói vào `alumglass-patch-3-full/` | `git show --stat 084896c` |
| `_load_accessories` thật hardcode `COUNT`/`VL_PK` | `bom_orchestrator.py:522–523` (thật) vs patch `acc.get(...) or ...` |
| `_fetch_composite_prices` thật hardcode `price_list="Standard Selling"` | thật dòng ~660 (resolved items) + ~870 (Item Price query) |
| `_match_composite_price` thật inline; patch wrapper `best_partial_match` | thật `bom_orchestrator.py:881–915`; patch `:1010–1027` |
| `_fetch_composite_prices_via_fb` thật `row_ctx` thiếu `category` | thật `:830–849`; patch `:941–952` |
| `fb_handlers.aluminum_price_composite` exact_match thật AND-filter; patch best_partial_match | thật `fb_handlers.py:81–100`; patch `:85–108` |
| `cost_bucket_aggregate` deprecated vẫn active cả thật lẫn patch | `fb_handlers.py:192–253`; `hooks.py:70` |
| `b6_calculate_cost_template` override snapshot thật thiếu `is_final_price` | thật `bom_orchestrator.py:1308–1320`; patch `:1443–1456` |
| FVB `source_type` = Select tĩnh 13 option | `formula_variable_binding.json` field `source_type` options (constant→fallback_chain) |
| Registry có 17 source_type built-in; 7 handler có `resolve_batch`; pipeline/custom_function không | `data_source_registry.py` — đếm `@register_source`; script check `resolve_batch` |
| `_execute_one_group` fallback `_execute_individual` khi không batch | `batch_binding_resolver.py:426–455` |
| `test_data_source` resolve với `doc=None, resolved_so_far={}` | `source_type_registry.py:652–700` |
| `get_live_context` lọc `applies_to_field` trong Python; `_get_pricing_bindings` thì không | `formula_builder.py:316–329`; `bom_orchestrator.py:783–808` |
| `install_fb_bindings.py` seed `price_list="Standard Selling"` cứng (phát hiện mới) | `alumglass-patch-3-full/.../setup/install_fb_bindings.py:35–37` |
| Golden 2C/4C | ADR `fvb-single-resolution-layer.md` §6; chốt dashboard 2026-08-18 |
