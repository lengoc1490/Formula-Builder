# Formula Builder

**Generic Excel-like formula engine and builder for Frappe Framework**

> Version: **29.1.0** | License: MIT | Author: Lê Ngọc

---

## Mục lục

- [Formula Builder](#formula-builder)
  - [Mục lục](#mục-lục)
  - [1. Giới thiệu](#1-giới-thiệu)
  - [2. Tổng quan tính năng](#2-tổng-quan-tính-năng)
  - [3. Kiến trúc tổng thể](#3-kiến-trúc-tổng-thể)
  - [4. Cài đặt](#4-cài-đặt)
  - [5. Cấu trúc thư mục](#5-cấu-trúc-thư-mục)
  - [6. Data Model — DocTypes](#6-data-model--doctypes)
    - [6.1 Formula Builder Settings (Single)](#61-formula-builder-settings-single)
    - [6.2 Formula Global Variable](#62-formula-global-variable)
    - [6.3 Formula Set](#63-formula-set)
    - [6.4 Formula Set Line (Child Table)](#64-formula-set-line-child-table)
    - [6.5 Formula Variable Binding](#65-formula-variable-binding)
    - [6.6 Formula Allowed Function (Child Table)](#66-formula-allowed-function-child-table)
    - [6.7 Formula DB Query Doctype (Child Table)](#67-formula-db-query-doctype-child-table)
    - [6.8 Formula Column Name (Child Table)](#68-formula-column-name-child-table)
  - [7. Formula Engine — Engine Lõi](#7-formula-engine--engine-lõi)
    - [7.1 Lớp kế thừa Engine](#71-lớp-kế-thừa-engine)
      - [FormulaEngineCore](#formulaenginecore)
      - [FormulaEngine (public top-level)](#formulaengine-public-top-level)
    - [7.2 Dependency Graph \& Topological Sort](#72-dependency-graph--topological-sort)
    - [7.3 FormulaParser — Parser \& Compiler](#73-formulaparser--parser--compiler)
    - [7.4 Security Validator](#74-security-validator)
    - [7.5 Normalize \& Hash](#75-normalize--hash)
    - [7.6 Incremental Context](#76-incremental-context)
    - [7.7 Error Handling](#77-error-handling)
    - [7.8 Snapshot System](#78-snapshot-system)
    - [7.9 Allocation Engine](#79-allocation-engine)
    - [7.10 SCC Linear Solver](#710-scc-linear-solver)
    - [7.11 Time Bucket System](#711-time-bucket-system)
    - [7.12 EngineTrace \& EngineAudit](#712-enginetrace--engineaudit)
  - [8. Built-in Functions — Hàm có sẵn](#8-built-in-functions--hàm-có-sẵn)
    - [8.1 Logical — Điều kiện](#81-logical--điều-kiện)
    - [8.2 Math — Toán học](#82-math--toán-học)
    - [8.3 Text — Chuỗi](#83-text--chuỗi)
    - [8.4 Date — Ngày tháng](#84-date--ngày-tháng)
    - [8.5 Lookup — Tra cứu](#85-lookup--tra-cứu)
    - [8.6 Aggregation — Tổng hợp](#86-aggregation--tổng-hợp)
    - [8.7 Time Bucket Functions](#87-time-bucket-functions)
    - [8.8 Number to Vietnamese Words](#88-number-to-vietnamese-words)
  - [9. API Layer — Backend](#9-api-layer--backend)
    - [9.1 `formula_builder.py` — Main API](#91-formula_builderpy--main-api)
    - [9.2 `formula_table_api.py` — Table API](#92-formula_table_apipy--table-api)
    - [9.3 `variable_resolver.py` — Variable Resolution](#93-variable_resolverpy--variable-resolution)
    - [9.4 `data_source_registry.py` — Data Source Registry](#94-data_source_registrypy--data-source-registry)
    - [9.5 `settings_cache.py` — Settings Cache](#95-settings_cachepy--settings-cache)
  - [10. Variable Resolution — Hệ thống biến](#10-variable-resolution--hệ-thống-biến)
    - [Resolution Chain (thứ tự ưu tiên)](#resolution-chain-thứ-tự-ưu-tiên)
    - [Cross-row Reference Syntax](#cross-row-reference-syntax)
    - [Cross-ref DAG Engine](#cross-ref-dag-engine)
  - [11. Frontend — Giao diện](#11-frontend--giao-diện)
    - [11.1 Formula Builder Dialog](#111-formula-builder-dialog)
    - [11.2 Inline Field Patching](#112-inline-field-patching)
    - [11.3 Grid Cell Editor](#113-grid-cell-editor)
    - [11.4 Declarative Dialog System](#114-declarative-dialog-system)
    - [11.5 CSS Design Tokens](#115-css-design-tokens)
  - [12. FlexibleFormulaEngine — Multi-table Engine](#12-flexibleformulaengine--multi-table-engine)
    - [Data Structures](#data-structures)
    - [Key Methods](#key-methods)
    - [ERPNextAdapter \& FrappeERPNextAdapter](#erpnextadapter--frappeerpnextadapter)
  - [13. Security](#13-security)
    - [Defense in Depth](#defense-in-depth)
    - [Rate Limits (configurable)](#rate-limits-configurable)
  - [14. Performance \& Caching](#14-performance--caching)
    - [Cache Architecture](#cache-architecture)
    - [Optimization Patterns](#optimization-patterns)
  - [15. Integration Guide](#15-integration-guide)
    - [Quick Start — Add Formula Field to a DocType](#quick-start--add-formula-field-to-a-doctype)
    - [Using the Frontend](#using-the-frontend)
    - [Formula Syntax Examples](#formula-syntax-examples)
  - [16. Hooks \& Lifecycle](#16-hooks--lifecycle)
    - [Install Lifecycle](#install-lifecycle)
  - [17. Development Guide](#17-development-guide)
    - [Setup](#setup)
    - [Code Quality](#code-quality)
    - [Testing](#testing)
    - [Adding a New Built-in Function](#adding-a-new-built-in-function)
    - [Adding a New Data Source Type](#adding-a-new-data-source-type)
    - [Extending the Frontend](#extending-the-frontend)
  - [18. Roadmap / Future Work](#18-roadmap--future-work)
  - [License](#license)
  - [Author](#author)

---

## 1. Giới thiệu

**Formula Builder** là một Frappe App cung cấp engine tính toán công thức kiểu Excel, tích hợp trực tiếp vào ERPNext/Frappe Framework. Người dùng có thể viết công thức động (`qty * rate * (1 - discount/100)`) trong bất kỳ DocType nào, tham chiếu đến các trường khác, child tables, biến toàn cục, và nhiều nguồn dữ liệu khác.

**Đặc điểm nổi bật:**
- **Zero hardcode** — Mọi business rule, công thức, hệ số được lưu trong DocTypes
- **Excel-like formula syntax** — Cú pháp quen thuộc: `IF()`, `SUMIF()`, `VLOOKUP()`, `XLOOKUP()`, tham chiếu chéo `items[0].qty`
- **DAG-based dependency resolution** — Tự động sắp xếp thứ tự tính toán theo đồ thị phụ thuộc
- **Incremental calculation** — Chỉ tính lại các node bị ảnh hưởng khi input thay đổi
- **Multi-table engine** — Hỗ trợ tính toán đồng thời nhiều child table + global formulas trong một DAG
- **Monaco Editor** — VS Code editor với syntax highlighting, autocomplete, hover, validation
- **10 data source types** — Hệ thống binding biến mở rộng với topological dependency resolution
- **Snapshot / Audit** — Ghi nhận và so sánh các phiên bản tính toán
- **Allocation Engine** — Phân bổ chi phí từ nhiều nguồn đến nhiều đích
- **SCC Linear Solver** — Giải hệ phương trình tuyến tính trên đồ thị có chu trình
- **Time Bucket** — Phân kỳ thời gian (năm/quý/tháng/tuần)
- **Security-first** — Input sanitization, rate limiting, permission checks, restricted AST
- **80+ built-in functions** — Math, Logic, Text, Date, Lookup, Aggregation, Number-to-Words (Vietnamese)

---

## 2. Tổng quan tính năng

| Nhóm tính năng | Mô tả | File chính |
|---|---|---|
| **Formula Editor UI** | Monaco Editor tích hợp Frappe, autocomplete, validation real-time, explain, debug | `public/js/formula_builder.js` |
| **Inline Field Editor** | Monaco editor nhúng trong form field, grid cell | `public/js/formula_builder_field.js` |
| **Declarative Dialog** | Dialog/table/HTML builder system | `public/js/formula_builder_dialog.js` |
| **Formula Engine** | DAG-based calculation, incremental, batch, multi-table | `formula_utils/engine_core.py` |
| **Parser & Compiler** | AST parsing → bytecode compilation, IF→ternary rewrite, dot→subscript transform | `formula_utils/parser.py` |
| **Security** | AST validation, function whitelist, variable whitelist, syntax normalization | `formula_utils/security.py` |
| **80+ Functions** | Math, Logic, Text, Date, Lookup, Agg, Number-to-Vietnamese | `formula_utils/funcs/` |
| **Variable Resolution** | 6-level scope chain + 10 data source handlers | `api/variable_resolver.py` |
| **Data Source Registry** | Extensible handler registry với topological sorting | `api/data_source_registry.py` |
| **Flexible Formula Engine** | Multi-table ERP engine (Sales Order, Quotation, etc.) | `flexible_formula_engine.py` |
| **Snapshot** | 5-layer Enterprise Snapshot với dual SHA-256 hash | `formula_utils/snapshot.py` |
| **Allocation** | 7 allocation methods, 3 output modes | `formula_utils/allocation.py` |
| **SCC Linear Solver** | Gaussian elimination + iterative fallback | `formula_utils/scc_linear.py` |
| **Time Bucket** | Year/Half/Quarter/Month/Week buckets | `formula_utils/time_bucket.py` |
| **AI Suggestions** | Anthropic/Deepseek/ChatGPT integration | `api/formula_builder.py` |
| **Rate Limiting** | Redis-based atomic rate limiting per user/action | `api/formula_builder.py` |
| **Caching** | Redis cache cho suggestions, settings, context | `api/settings_cache.py` |

---

## 3. Kiến trúc tổng thể

```
┌──────────────────────────────────────────────────────────────┐
│                     FRONTEND (JS/CSS)                        │
│  ┌─────────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ formula_builder │  │ formula_     │  │ formula_builder │  │
│  │ .js (Dialog)    │  │ builder_field│  │ _dialog.js      │  │
│  │                 │  │ .js (Inline) │  │ (Declarative)   │  │
│  └────────┬────────┘  └──────┬───────┘  └─────────┬───────┘  │
│           │                  │                    │          │
│           └──────────────────┼────────────────────┘          │
│                              │                               │
│                    Monaco Editor v0.45.0                     │
│                    (CDN: jsDelivr)                           │
└──────────────────────────────┼───────────────────────────────┘
                               │ frappe.call()
                               ▼
┌────────────────────────────────────────────────────────────┐
│                     BACKEND (Python)                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              API Layer                              │   │
│  │  formula_builder.py    formula_table_api.py         │   │
│  │  variable_resolver.py  data_source_registry.py      │   │
│  │  settings_cache.py                                  │   │
│  └──────────────────────────┬──────────────────────────┘   │
│                             │                              │
│  ┌──────────────────────────▼──────────────────────────┐   │
│  │         FlexibleFormulaEngine (Multi-table)         │   │
│  │         integration.py (Frappe Adapter)             │   │
│  └──────────────────────────┬──────────────────────────┘   │
│                             │                              │
│  ┌──────────────────────────▼──────────────────────────┐   │
│  │           FormulaEngine (formula_utils/)            │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │   │
│  │  │EngineCore│→│EngineTrace│→│EngineAudit│→│Formula│ │   │
│  │  │          │ │          │ │          │ │Engine   │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐             │   │
│  │  │ Parser   │ │ Security │ │ Normalize│             │   │
│  │  └──────────┘ └──────────┘ └──────────┘             │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐             │   │
│  │  │ TopoSort │ │Snapshot  │ │Allocation│             │   │
│  │  └──────────┘ └──────────┘ └──────────┘             │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐             │   │
│  │  │SCC Linear│ │TimeBucket│ │ 80+ Funcs│             │   │
│  │  └──────────┘ └──────────┘ └──────────┘             │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                   DATA LAYER                                 │
│  ┌─────────────────┐  ┌─────────────────┐                    │
│  │ 8 DocTypes      │  │ Redis Cache     │                    │
│  │ (MariaDB)       │  │ (Suggestions,   │                    │
│  │                 │  │  Settings,      │                    │
│  │                 │  │  Context)       │                    │
│  └─────────────────┘  └─────────────────┘                    │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Cài đặt

```bash
# 1. Get the app
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/your-org/formula_builder --branch develop

# 2. Install on target site
bench --site your-site install-app formula_builder

# 3. Migrate (seeds default settings + all built-in functions)
bench --site your-site migrate

# 4. Build frontend assets
bench build --app formula_builder
```

**Requirements:**
- Frappe Framework >= v15
- Python >= 3.10
- Redis (for caching & rate limiting)

---

## 5. Cấu trúc thư mục

```
formula_builder/
├── pyproject.toml                       # Project metadata, dependencies, ruff config
├── README.md                            # This file
├── formula_builder/
│   ├── __init__.py                      # Package init, version = "0.0.1"
│   ├── hooks.py                         # Frappe hooks (assets, doc_events, fixtures, after_migrate)
│   ├── install.py                       # Post-migration: seed default settings
│   ├── modules.txt                      # Module list: "Formula Builder"
│   ├── patches.txt                      # Migration patches (empty)
│   │
│   ├── flexible_formula_engine.py       # Multi-table ERP engine + ERPNextAdapter ABC
│   ├── integration.py                   # Public integration surface + FrappeERPNextAdapter
│   │
│   ├── formula_utils/                   # ⭐ Core Formula Engine v29.1.0
│   │   ├── __init__.py                  # Public API exports (~110+ names)
│   │   ├── engine_core.py              # FormulaEngineCore + IncrementalContext
│   │   ├── engine_trace.py             # FormulaEngineTrace
│   │   ├── engine_audit.py             # FormulaEngineAudit
│   │   ├── engine_public.py            # FormulaEngine (top-level public API)
│   │   ├── parser.py                   # FormulaParser (AST parse → bytecode compile)
│   │   ├── security.py                 # SecurityValidator + FormulaValidator
│   │   ├── normalize.py                # Formula normalization, hashing
│   │   ├── topo.py                     # Topological sort (Kahn + Tarjan SCC)
│   │   ├── types.py                    # All dataclasses, enums, type definitions
│   │   ├── errors.py                   # Error hierarchy (33 error codes)
│   │   ├── snapshot.py                 # SnapshotRegistry + SnapshotManager
│   │   ├── allocation.py               # AllocationEngine v20
│   │   ├── scc_linear.py              # SCC-based linear solver
│   │   ├── time_bucket.py             # Time bucket generation
│   │   └── funcs/                      # ~80+ Built-in functions
│   │       ├── registry.py             # BASE_FUNCS dictionary
│   │       ├── math.py                # Math functions + safe operations
│   │       ├── logic.py               # IF, IFS, SWITCH, COALESCE, etc.
│   │       ├── text.py                # CONCAT, LEFT, RIGHT, MID, etc.
│   │       ├── date.py                # NOW, TODAY, YEAR, MONTH, DATE_DIFF, etc.
│   │       ├── lookup.py              # VLOOKUP, XLOOKUP, INDEX, MATCH, etc.
│   │       ├── agg.py                 # SUMIF, COUNTIFS, AVERAGEIF, GROUP BY, etc.
│   │       └── number_to_words.py     # Number → Vietnamese words
│   │
│   ├── api/                             # Backend API (Frappe whitelisted endpoints)
│   │   ├── formula_builder.py          # Main API: validate, evaluate, context, suggestions, AI
│   │   ├── formula_table_api.py        # Child table cell calculation & validation
│   │   ├── variable_resolver.py        # VariableResolver + SuggestionsBuilder
│   │   ├── data_source_registry.py     # 10 data source handlers + dependency resolver
│   │   └── settings_cache.py           # Cached settings access (Redis, 5-min TTL)
│   │
│   ├── formula_builder/                 # Doctype definitions (Frappe conventions)
│   │   └── doctype/
│   │       ├── formula_builder_settings/    # Singletone: global config
│   │       │   ├── formula_builder_settings.json
│   │       │   ├── formula_builder_settings.py
│   │       │   ├── formula_builder_settings.js
│   │       │   └── test_formula_builder_settings.py
│   │       ├── formula_global_variable/     # Global/shared variables
│   │       ├── formula_set/                 # Named formula collections
│   │       ├── formula_set_line/            # Child: formula lines
│   │       ├── formula_variable_binding/    # v2: extensible variable bindings
│   │       ├── formula_allowed_function/    # Child: whitelisted functions
│   │       ├── formula_db_query_doctype/    # Child: DB-queryable doctypes
│   │       └── formula_column_name/         # Child: formula field names for auto-detection
│   │
│   ├── public/                           # Frontend assets
│   │   ├── js/
│   │   │   ├── formula_builder.js        # Core: Monaco editor, FunctionRegistry, AluglassFormulaEditor
│   │   │   ├── formula_builder_field.js  # Inline field patching + grid cell editing
│   │   │   └── formula_builder_dialog.js # Declarative dialog/table/HTML builder
│   │   └── css/
│   │       ├── formula_builder_vars.css   # Design tokens (CSS custom properties)
│   │       ├── formula_builder.css        # Main dialog styles
│   │       ├── formula_builder_field.css  # Inline field styles
│   │       ├── formula_builder_monaco.css # Monaco Editor overrides
│   │       └── formula_builder_dialog.css # Declarative dialog styles
│   │
│   ├── config/                          # Python package marker (empty)
│   │   └── __init__.py
│   │
│   └── templates/                       # Jinja templates (package markers only)
│       ├── __init__.py
│       └── pages/
│           └── __init__.py
│
├── .claude/                            # Claude Code config
│   └── settings.local.json
└── screen/                             # Screenshots
    ├── dialog-bang-me.png
    ├── dialog-bang-con.png
    └── cong-thuc-o-field.png
```

---

## 6. Data Model — DocTypes

### 6.1 Formula Builder Settings (Single)

**Purpose:** Global configuration singleton for the entire Formula Builder app.

| Field | Type | Default | Description |
|---|---|---|---|
| `title` | Data | — | Display title |
| `max_formula_length` | Int | 2000 | Max characters per formula |
| `rate_limit_validate` | Int | 40 | Validate rate limit (req/min) |
| `rate_limit_evaluate` | Int | 20 | Evaluate rate limit (req/min) |
| `rate_limit_ai` | Int | 5 | AI suggest rate limit (req/min) |
| `ai_provider` | Select | — | Anthropic / Deepseek / ChatGPT |
| `ai_model` | Data | `claude-3-sonnet-20240229` | AI model identifier |
| `allowed_functions` | Table → Formula Allowed Function | — | Whitelisted formula functions |
| `db_query_allowed_doctypes` | Table → Formula DB Query Doctype | — | Doctypes allowed for DB_QUERY source |
| `formula_column_names` | Table → Formula Column Name | — | Formula field names for auto-detection |
| `custom_function_whitelist` | Small Text | — | Allowed module prefixes (newline-separated) |

**Permission:** Only `System Manager` role.

### 6.2 Formula Global Variable

**Purpose:** Global/shared variables accessible across all doctypes via `$var_name` prefix.

| Field | Type | Description |
|---|---|---|
| `var_name` | Data (unique) | Variable identifier |
| `label` | Data | Display label |
| `var_type` | Select | Float / Int / Currency / Percent / Check / Data |
| `unit` | Data | Unit of measurement |
| `category` | Data | Categorization |
| `description` | Small Text | Description |
| `value_source` | Select | **CONSTANT** / **FORMULA** / **DB_QUERY** |
| `constant_value` | Data | Value for CONSTANT source |
| `formula_expr` | Small Text | Formula for FORMULA source |
| `db_query_doctype` | Link → DocType | Target doctype for DB_QUERY |
| `db_query_field` | Data | Target field for DB_QUERY |
| `db_query_filters` | JSON | Filters for DB_QUERY |
| `is_active` | Check (default 1) | Active flag |

**Resolution modes:**
- `CONSTANT` — Returns `constant_value` cast to `var_type`
- `FORMULA` — Evaluates `formula_expr` with other global constants as context (max 10k operations)
- `DB_QUERY` — Runs `frappe.get_all()` with configured filters; enforces `db_query_allowed_doctypes` whitelist

**Permission:** Only `System Manager` role. Naming rule: "By fieldname".

### 6.3 Formula Set

**Purpose:** Named collections of formulas with a unique code identifier. Referenced as `FS-CODE.var_name` in formulas.

| Field | Type | Description |
|---|---|---|
| `set_code` | Data (unique) | Unique code (e.g., `VAT`, `PRICING`) |
| `label` | Data | Human-readable label |
| `linked_doctype` | Link → DocType | Optional scope limitation |
| `is_active` | Check (default 0) | Active flag |
| `formulas` | Table → Formula Set Line | Formula definitions |

**Permission:** Only `System Manager` role.

### 6.4 Formula Set Line (Child Table)

**Purpose:** Individual formula entries within a Formula Set.

| Field | Type | Description |
|---|---|---|
| `var_name` | Data | Output variable name |
| `formula` | Small Text | Formula expression |
| `description` | Small Text | What the formula computes |

### 6.5 Formula Variable Binding

**Purpose:** **v2 Variable Binding System** — Extensible, declarative variable bindings. Replaces legacy `custom_` field conventions with a registry-based approach.

| Field | Type | Default | Description |
|---|---|---|---|
| `variable_name` | Data (reqd) | — | Unique variable identifier |
| `variable_label` | Data | — | Display label |
| `source_type` | Select (reqd) | — | constant / linked_doctype_field / whole_doctype / child_table_aggregate / global_default / session_variable / doctype_query / custom_function / dynamic_link / computed |
| `resolve_priority` | Int | 100 | Resolution order (lower = earlier) |
| `source_config` | JSON | — | Type-specific configuration |
| `applies_to_doctype` | Link → DocType | — | Optional scope limitation |
| `applies_to_field` | Data | — | Optional field scope limitation |
| `data_type` | Select | — | Float / Int / Currency / Percent / Check / Data / Object |
| `default_value` | Data | — | Fallback when resolution fails |
| `is_global` | Check | 0 | Applies to all doctypes |
| `is_active` | Check | 1 | Active flag |

**10 Source Types** — See [Section 9.4](#94-data_source_registrypy--data-source-registry) for full details.

**Permission:** Only `System Manager` role.

### 6.6 Formula Allowed Function (Child Table)

**Purpose:** Child table of `Formula Builder Settings` defining which built-in functions are available and their display metadata.

| Field | Type | Description |
|---|---|---|
| `func_name` | Data | Function name (must match BASE_FUNCS key) |
| `alias` | Data | Optional alias name |
| `category` | Data | Categorization (e.g., "Toan hoc", "Dieu kien") |
| `signature` | Data | Function signature display |
| `description` | Small Text | Documentation |
| `example` | Data | Usage example |
| `insert_template` | Data | Template for insertion (e.g., `IF($1, $2, $3)`) |
| `enabled` | Check (default 1) | Enable/disable flag |

### 6.7 Formula DB Query Doctype (Child Table)

**Purpose:** Child table of `Formula Builder Settings` listing doctypes that can be queried via `DB_QUERY` source type.

| Field | Type | Description |
|---|---|---|
| `doctype_name` | Link → DocType (reqd) | Allowed doctype |
| `description` | Data | Description |
| `disabled` | Check (default 0) | Disable flag |

### 6.8 Formula Column Name (Child Table)

**Purpose:** Child table of `Formula Builder Settings` defining fieldnames in child table doctypes that contain formulas. Used by the cross-ref DAG engine to auto-detect formula fields.

| Field | Type | Description |
|---|---|---|
| `fieldname` | Data (reqd) | Formula field name (e.g., `custom_qty_formula`) |

---

## 7. Formula Engine — Engine Lõi

> **Version:** 29.1.0 | **Location:** `formula_utils/`

Đây là engine độc lập với Frappe, có thể dùng standalone. Mọi file trong `formula_utils/` **không import `frappe`**.

### 7.1 Lớp kế thừa Engine

```
FormulaEngineCore          — Parse, compile, DAG, evaluate
    ↑
FormulaEngineTrace         — Thêm optional trace (dep values, formulas)
    ↑
FormulaEngineAudit         — Thêm audit sessions, sample logging, execution trees
    ↑
FormulaEngine              — Top-level: explain, snapshot, scenarios, cache, static utils
```

#### FormulaEngineCore

**Constructor parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `formulas` | `Dict[str, str]` | required | `{name: formula_expr}` map |
| `safe_funcs` | `Dict[str, Callable]` | `BASE_FUNCS` | Allowed functions |
| `on_error` | `str` | `"default"` | `"raise"` / `"null"` / `"default"` |
| `default_value` | `any` | `0` | Value when on_error=`"default"` |
| `meta` | `FormulaSetMeta` | `None` | Formula set metadata |
| `input_fields` | `List[InputField]` | `None` | Expected input schema |
| `output_fields` | `List[OutputField]` | `None` | Expected output schema |
| `assertions` | `List[Assertion]` | `None` | Runtime assertion rules |
| `max_iterable_size` | `int` | `None` | Max iterable elements |
| `max_subscript_depth` | `int` | `5` | Max nesting depth for `a[b][c]` |
| `rounding_policy` | `Dict[str, int]` | `None` | Per-variable decimal rounding |
| `strict` | `bool` | `True` | Raise on unknown variable? |
| `validate_on_init` | `bool` | `False` | Validate all formulas on init? |
| `max_operations` | `int` | `None` | Operation budget cap |
| `max_formula_count` | `int` | `None` | Maximum number of formulas |
| `max_dependency_depth` | `int` | `None` | Maximum DAG depth |
| `deterministic` | `bool` | `True` | Block `now()`/`today()`/`random()`? |

**Key methods:**

| Method | Description |
|---|---|
| `calculate(inputs) → Dict` | Full DAG evaluation |
| `calculate_batch(rows) → List[Dict]` | Batch evaluate with same formulas |
| `calculate_batch_with_memory(rows, memory_keys, initial_memory) → List[Dict]` | Batch with `prev_` memory references |
| `create_context(initial_inputs, doc_id) → IncrementalContext` | Create persistent context |
| `calculate_incremental(ictx, changed_inputs) → Dict` | Only recompute affected nodes |
| `recalculate_full(ictx, new_inputs) → Dict` | Full recalc preserving context |
| `get_affected_nodes(changed_inputs) → Set[str]` | Downstream nodes affected by changes |
| `validate_formula(formula, known_names) → ValidationResult` | Validate one formula |
| `validate_all(known_names) → Dict[str, ValidationResult]` | Validate all formulas |
| `register_formula(name, formula) → ValidationResult` | Dynamically add/replace a formula |
| `get_metadata() → Dict` | Engine metadata (version, counts, DAG depth, hash) |

#### FormulaEngine (public top-level)

Extends `FormulaEngineAudit` with:

| Method | Description |
|---|---|
| `explain(field, inputs) → ExplainResult` | Step-by-step calculation trace |
| `explain_all(inputs) → Dict[str, ExplainResult]` | Explain all fields |
| `validate_inputs(inputs) → List[InputIssue]` | Schema validation |
| `calculate_scenarios(scenarios) → Dict` | Multi-scenario calculation |
| `compare_scenarios(scenarios, fields, base) → ScenarioComparison` | With delta/pct |
| `calculate_safe(inputs) → Dict` | Never raises; returns `_ok`, `_error`, `_error_type` |
| `snapshot(inputs, outputs, ...) → EnterpriseSnapshot` | Create enterprise snapshot |
| `snapshot_with_trace(inputs, ...) → (Dict, EnterpriseSnapshot)` | Trace + snapshot |
| `to_cache_dict() → Dict` | Serialize engine for cache |
| `from_cache_dict(d) → FormulaEngine` | Classmethod: restore from cache |

### 7.2 Dependency Graph & Topological Sort

**File:** `topo.py`

**Class `DependencyGraph`:**
- Builds parent→children and child→parents maps from AST
- DFS cycle detection on add → raises `FormulaError(CIRCULAR_DEPENDENCY)`
- Topological sort via Kahn's algorithm
- `get_affected(changed_inputs)` — BFS to find all downstream nodes
- `max_depth()` — Memoized DFS from leaves to roots

**Module-level functions:**
- `topo_sort(items, id_fn, deps_fn)` — Simple Kahn sort
- `topo_sort_with_info(items, id_fn, deps_fn) → TopoSortResult` — With levels, cycle info
- `scc_topo_sort_with_info(items, id_fn, deps_fn) → SccTopoResult` — Tarjan SCC + condensation
- `topo_sort_data(items, id_key, deps_list_key, dep_id_key)` — Convenience for dict data
- `scc_topo_sort_flat(items, id_key, dep_ids_key)` — SCC: flat dependency list

### 7.3 FormulaParser — Parser & Compiler

**File:** `parser.py`

**Pipeline:**
```
Formula String
  → normalize_formula()         # percent→/100, <>→!=, =→==, and/or/not remap
  → ast.parse(mode='eval')      # Python AST
  → IfCallRewriter               # IF(cond, t, f) → (t if cond else f)
  → DotToSubscriptTransformer   # obj.field → obj['field'] (for non-whitelisted attrs)
  → SecurityValidator            # Block forbidden nodes, names, deep subscript
  → _validate_genexp()           # Generator expressions only in SUMIF, FILTER, etc.
  → _validate_functions()        # All calls must exist in runtime_env
  → compile()                    # Python bytecode
```

**DotToSubscriptTransformer:**
- Converts `items.K1.qty` → `items['K1']['qty']` (except 5 whitelisted attrs: `get`, `keys`, `values`, `items`, `to_dict`)

**IfCallRewriter:**
- `IF(cond, true, false)` → `(true if cond else false)` — turns function call into Python ternary

### 7.4 Security Validator

**File:** `security.py`

**SecurityValidator (NodeVisitor):**
- Blocks: `Import`, `ImportFrom`, `Exec`, `Eval`, `FunctionDef`, `Lambda`, `DictComp`, `SetComp`, `ListComp`, `GeneratorExp` (except in whitelisted functions)
- Forbidden names: `os`, `sys`, `exec`, `eval`, `compile`, `__import__`, `__class__`, `__subclasses__`, `__builtins__`, `globals`, `locals`, `vars`, `getattr`, `setattr`, `delattr`, `type`, `issubclass`, `__dict__`, `__bases__`, etc.
- Allowed attributes: only `get`, `keys`, `values`, `items`, `to_dict`
- Max subscript depth: configurable (default 5)
- Max literal list size: configurable

**FormulaValidator:**
- Complete validation pipeline: normalize → syntax check → security check → function whitelist → variable whitelist
- Added checks for: generator expressions context, missing IF-else, no-variable formulas
- `validate(formula, known_names) → ValidationResult`
- `validate_batch(formulas, known_names) → Dict[str, ValidationResult]`

### 7.5 Normalize & Hash

**File:** `normalize.py`

**`normalize_formula(expr, canonical_names)`:**
- `50%` → `(50/100)`
- `<>` → `!=`
- `=` → `==` (unless inside keyword argument like `key=value`)
- Function name canonicalization (e.g., `Sum` → `sum`)
- Logic remap: `and` → `and_`, `or` → `or_`, `not` → `not_`
- Known kwargs detection (from `BASE_FUNCS` introspection) to avoid false positives

**Other utilities:**
- `match_criteria(value, criteria)` — Supports exact, `>`, `<`, `>=`, `<=`, `!=`, `=`, `*` wildcard
- `hash_formulas(formulas)` — SHA-256 of JSON-sorted formulas
- `hash_dict(data)` — SHA-256 of JSON-sorted dict
- `safe_str(x)` — None-safe str conversion

### 7.6 Incremental Context

**File:** `engine_core.py`

**Class `IncrementalContext`:**
- Stores persistent state across incremental calculation calls
- `engine_hash` — detects if formula set has changed (stale detection)
- `doc_id` — optional document identifier
- `patch(field, value)` — directly set field in context
- Serializes to/from dict for cache/DB storage
- `_apply_inputs(inputs) → Set[str]` — diff inputs, returns changed field names

**Incremental flow:**
```python
engine = FormulaEngine(formulas, safe_funcs=BASE_FUNCS)
ictx = engine.create_context(initial_inputs, doc_id="SO-00001")

# User changes qty
result1 = engine.calculate_incremental(ictx, {"qty_K1": 10})
# Only K1 fields + downstream are recalculated

# User changes rate
result2 = engine.calculate_incremental(ictx, {"rate": 2.5})
# Only rate-dependent fields recalculated
```

### 7.7 Error Handling

**File:** `errors.py`

**33 Error Codes:** `CIRCULAR_DEPENDENCY`, `INVALID_TYPE`, `SYNTAX_ERROR`, `SECURITY_VIOLATION`, `DIVISION_BY_ZERO`, `UNKNOWN_FUNCTION`, `NON_DETERMINISTIC_IN_FROZEN`, `BUDGET_EXCEEDED`, etc.

**Exception Hierarchy:**
```
FormulaError(ValueError)
├── SchemaError
├── FormulaBudgetExceeded       # Operation budget exceeded
├── FormulaComplexityError      # Too many formulas / too deep DAG
├── FormulaLimitError           # Iterable too large
├── FormulaRuntimeError         # Runtime evaluation error
├── FormulaValidationError      # Validation errors
├── FormulaDeterministicError   # Non-deterministic in deterministic mode
└── FormulaAssertionError       # Assertion violation
```

All errors have `field_name`, `formula`, `error`, `context`, `code`, `level` attributes and rich `__str__()` with `difflib` suggestions for unknown names.

### 7.8 Snapshot System

**File:** `snapshot.py`

**EnterpriseSnapshot (5-layer architecture):**

| Layer | Block | Content |
|---|---|---|
| 1 | `EngineMetaBlock` | Engine version, formula hash, formula count, topo order hash |
| 2 | `EngineContextBlock` | DAG version, input/output keys, rounding policy, error mode |
| 3 | `DagStateBlock` | Execution order, dependency edges, input nodes, dirty nodes |
| 4 | `ExecutionTraceBlock` | Per-field trace entries, execution time, changed fields |
| 5 | `AuditTrailBlock` | Tag, status, creator, approver, revision chain, notes |

**Dual hash verification:**
- `payload_hash` — SHA-256 of layers 1-4 combined
- `trace_hash` — SHA-256 of layer 4 execution trace
- `verify()` — Recomputes and compares payload hash

**SnapshotRegistry:**
- In-memory store with query by tag, status, creator, source doc
- `revision_history(snapshot_id)` — Follow parent chain
- `lock(snapshot_id)` — Set status → `LOCKED`
- `export_json(snapshot_id)` — Full JSON export

### 7.9 Allocation Engine

**File:** `allocation.py`

**7 Allocation Methods:** `equal`, `qty`, `amount`, `weight`, `pct`, `manual_amount`, `manual_pct`, `mixed`

**3 Output Modes:** `lines` (full), `inplace` (write into targets), `fast` (tuple output)

**Class `AllocationEngine`:**
- Partition support via `group_key`
- Rounding policies: `last` (adjust last target), `largest` (adjust largest), `none`
- Mixed method: 3-pass (manual_amount → manual_pct → residual)

**Result inspection:**
```python
result = allocate(sources, targets, method="amount", ...)
result.summary()            # Text summary
result.to_dict()            # Full dict
result.group_by_source()    # Grouped by source
result.group_by_target()    # Grouped by target
result.to_flat_rows()       # CSV-friendly
```

### 7.10 SCC Linear Solver

**File:** `scc_linear.py`

Solves `x_i = b_i + sum_j A[i][j] * x_j` on directed graphs:
- Uses Tarjan SCC + condensation to handle cycles
- Inside SCCs: Gaussian elimination with partial pivoting
- Fallback: Gauss-Seidel iterative method on singular matrices
- Non-negative clamping option for economic allocation

### 7.11 Time Bucket System

**File:** `time_bucket.py`

**TimeBucket dataclass:**
- `name`, `short_label`, `full_label`, `type`, `index`, `year`, `from_date`, `to_date`
- Navigation: `prev_period`, `next_period`
- Query: `get_period(period_type, index, year)`, `get_period_by_date(date, period_type)`
- Format presets: `short`, `short_year`, `full`, `date_range`, `padded`

**Built-in functions:**
- `time_buckets(year)` — Generate all buckets for a year
- `in_time_bucket(date, bucket)` — Check membership
- `same_period_last_year(bucket)` — PY comparison

### 7.12 EngineTrace & EngineAudit

**EngineTrace:** Extends `FormulaEngineCore` with optional trace — captures dep values and formula text per calculated field.

**EngineAudit:** Extends `EngineTrace` with:
- Audit sessions (`begin_audit_session`, `end_audit_session`)
- Sample logging (configurable sample rate)
- Execution tree materialization from log entries
- Audit reports with violations, timing, and tree visualization
- Batch calculation with optional audit report output

---

## 8. Built-in Functions — Hàm có sẵn

> **Location:** `formula_utils/funcs/` | **Registry:** `BASE_FUNCS` in `registry.py`

### 8.1 Logical — Điều kiện

| Function | Signature | Description |
|---|---|---|
| `IF` | `IF(cond, true_val, false_val)` | Excel-style conditional |
| `IIF` / `iif` | `IIF(cond, true, false)` | Alias for IF |
| `IFS` / `ifs` | `IFS(cond1, val1, cond2, val2, ...)` | Multiple conditions |
| `SWITCH` / `switch` | `SWITCH(expr, case1, val1, case2, val2, ..., default)` | Value matching |
| `COALESCE` | `coalesce(*args)` | First non-None, non-empty |
| `IS_BLANK` | `is_blank(x)` | True if None, "", 0, 0.0 |
| `NOT_BLANK` | `not_blank(x)` | Inverse of IS_BLANK |
| `and_` | `and_(a, b, ...)` | Logical AND |
| `or_` | `or_(a, b, ...)` | Logical OR |
| `not_` | `not_(x)` | Logical NOT |

### 8.2 Math — Toán học

| Function | Signature | Description |
|---|---|---|
| `abs` | `abs(x)` | Absolute value |
| `round` | `round(x, d=0)` | Standard rounding |
| `roundup` | `roundup(x, d=0)` | Ceiling rounding |
| `rounddown` | `rounddown(x, d=0)` | Floor rounding |
| `floor` | `floor(x)` | Math floor |
| `ceil` | `ceil(x)` | Math ceiling |
| `power` | `power(x, y)` | Exponentiation |
| `sqrt` | `sqrt(x)` | Square root |
| `ln` | `ln(x)` | Natural log |
| `log10` | `log10(x)` | Base-10 log |
| `log` | `log(x, base)` | Logarithm with base |
| `pi` | `pi()` | π constant |
| `sin` | `sin(x)` | Sine (radians) |
| `cos` | `cos(x)` | Cosine |
| `tan` | `tan(x)` | Tangent |
| `exp` | `exp(x)` | e^x |
| `min` | `min(*args)` | Minimum |
| `max` | `max(*args)` | Maximum |
| `sum` | `sum(*args)` | Sum (non-numeric filtered) |
| `safe_div` | `safe_div(a, b, default=0)` | Safe division (no ZeroDivision) |
| `percent_of` | `percent_of(part, total, default=0)` | (part/total)*100 |
| `clamp` | `clamp(x, lo, hi)` | Clamp to range |
| `between` | `between(x, lo, hi)` | lo <= x <= hi |
| `isnumber` | `isnumber(x)` | Numeric type check |
| `to_number` | `to_number(x, default=0)` | Parse to float |
| `int` / `float` / `str` / `bool` | Type casting | Standard type conversion |

### 8.3 Text — Chuỗi

| Function | Signature | Description |
|---|---|---|
| `concat` | `concat(*args)` | Concatenate (skip None) |
| `concatenate` | `concatenate(*args)` | Alias |
| `text_join` | `text_join(delim, *args)` | Join with delimiter |
| `textjoin` | `textjoin(delim, ignore_empty, *texts)` | Flexible join |
| `left` | `left(text, n=1)` | First n chars |
| `right` | `right(text, n=1)` | Last n chars |
| `mid` | `mid(text, start, length)` | Substring (1-indexed) |
| `upper` | `upper(text)` | Uppercase |
| `lower` | `lower(text)` | Lowercase |
| `trim` | `trim(text)` | Strip whitespace |
| `replace` | `replace(text, old, new)` | Replace all |
| `substitute` | `substitute(text, old, new, nth)` | Replace all or nth |
| `find` | `find(search, text, start=1)` | Find position (1-indexed, 0 if not found) |
| `len_text` | `len_text(text)` | String length |

### 8.4 Date — Ngày tháng

| Function | Signature | Description |
|---|---|---|
| `now` | `now()` | Current UTC datetime |
| `today` | `today()` | Current date |
| `year` | `year(dt)` | Extract year |
| `month` | `month(dt)` | Extract month |
| `day` | `day(dt)` | Extract day |
| `quarter` | `quarter(dt)` | Quarter 1-4 |
| `date_diff` | `date_diff(d1, d2, unit='days')` | Difference (days/months/years/hours/seconds) |
| `date_add` | `date_add(dt, days=0, months=0, years=0)` | Add offset |
| `date_format` | `date_format(dt, fmt="%d/%m/%Y")` | strftime |
| `workdays` | `workdays(date1, date2)` | Mon-Fri count |

### 8.5 Lookup — Tra cứu

| Function | Signature | Description |
|---|---|---|
| `vlookup` | `vlookup(key, table, col=1, default=0)` | Excel-style VLOOKUP |
| `xlookup` | `xlookup(lookup, lookup_arr, return_arr, if_not_found=0)` | Excel-style XLOOKUP |
| `index` | `index(array, row, col=0)` | 1-indexed element |
| `match` | `match(value, array, match_type=1)` | Excel-style MATCH |
| `choose` | `choose(index, *values)` | 1-indexed picker |
| `filter_array` | `filter_array(data, operator, threshold, key, value)` | Filter by condition |
| `last` / `latest` | `last(data, sort_by, n, group_by, ...)` | Last N records |
| `first` / `earliest` | `first(data, sort_by, n, group_by, ...)` | First N records |
| `nth` | `nth(data, n, sort_by, ...)` | Nth record |
| `sorted_array` / `sort` | `sort(data, key, reverse)` | Sorted list |
| `unique` | `unique(data, key)` | Deduplicate |
| `flatten` | `flatten(data)` | Recursive flatten |
| `map_key` | `map_key(data, key)` | Extract key from dicts |
| `sum_dict` | `sum_dict(d)` | Sum dict values |
| `rf` | `rf(row, field)` / `rf(table, idx, field)` | Row field accessor |

### 8.6 Aggregation — Tổng hợp

| Function | Signature | Description |
|---|---|---|
| `sumif` | `sumif(range, criteria, sum_range)` | Single-criterion SUMIF |
| `sumifs` | `sumifs(sum_range, *criteria_pairs)` | Multi-criteria SUMIFS |
| `countif` | `countif(range, criteria)` | Single-criterion COUNTIF |
| `countifs` | `countifs(*criteria_pairs)` | Multi-criteria COUNTIFS |
| `averageif` | `averageif(range, criteria, avg_range)` | Single-criterion AVERAGEIF |
| `count` / `counta` | `count(*args)` | Non-null count |
| `countnum` | `countnum(data)` | Count numeric only |
| `average` | `average(*args)` | Average numeric |
| `sum_by_type` | `sum_by_type(items, type_key, val_key, target)` | Sum by column value |
| `unique_key_sum_by_type` | `unique_key_sum_by_type(...)` | Dedup before sum |
| `unique_sum` | `unique_sum(items, key_idx, val_idx)` | Unique key sum |
| `count_unique` | `count_unique(data, key)` | Count unique |
| `group_sum` / `group_by_sum` | `group_sum(data, group_key, sum_key)` | Group-and-sum |
| `group_count` / `group_by_count` | `group_count(data, group_key)` | Group-and-count |
| `group_avg` | `group_avg(data, group_key, avg_key)` | Group-and-average |

### 8.7 Time Bucket Functions

| Function | Description |
|---|---|
| `time_buckets(year)` | Generate all time buckets |
| `in_time_bucket(date, bucket)` | Check date membership |
| `get_bucket_label(bucket, format)` | Get formatted label |
| `get_period(type, index, year)` | Get specific period |
| `period_offset(bucket, offset)` | Navigate periods |
| `same_period_last_year(bucket)` | PY comparison |
| `year_buckets(year)` | Full year buckets |

### 8.8 Number to Vietnamese Words

| Function | Signature | Description |
|---|---|---|
| `number_to_words` | `number_to_words(amount, currency, currency_map, decimal_mode, decimal_digits)` | Converts number to Vietnamese words. Supports VND, USD, EUR, GBP, JPY, CNY, KRW, SGD, AUD, CAD, CHF, HKD, THB. Two decimal modes: `"integer"` (reads as whole number) and `"digits"` (digit-by-digit). |

**Example:**
```python
number_to_words(1234567, currency="VND")
# "Một triệu hai trăm ba mươi bốn nghìn năm trăm sáu mươi bảy đồng"
```

---

## 9. API Layer — Backend

> **Location:** `api/` | All endpoints are whitelisted with `@frappe.whitelist()`

### 9.1 `formula_builder.py` — Main API

**Endpoints:**

| Endpoint | Method | Description |
|---|---|---|
| `get_suggestions(scope_context_json)` | Whitelist | Autocomplete suggestions for formula editor |
| `get_child_rows(doctype, docname, child_field)` | Whitelist | Child table rows with line_ref/idx/label |
| `get_doctype_fields(doctype)` | Whitelist | All non-skip fields for a DocType |
| `validate_formula(formula, scope_context_json)` | Whitelist | Full validation pipeline |
| `evaluate_formula(formula, scope_context_json, ...)` | Whitelist | Evaluate formula with full context |
| `evaluate_formula_set(formula_set_code, extra_context_json)` | Whitelist | Evaluate all formulas in a set |
| `get_live_context(scope_context_json)` | Whitelist | Full live context for sidebar |
| `get_global_context_preview()` | Whitelist | Active global variables with values |
| `invalidate_suggestions_cache(...)` | Whitelist | Clear caches (called by hooks) |
| `explain_formula(formula, scope_context_json)` | Whitelist | Step-by-step calculation trace |
| `smart_suggest_formula(doctype, fieldname, field_label, scope)` | Whitelist | Context-aware formula suggestions |
| `ai_suggest_formula(prompt)` | Whitelist | AI-powered formula generation |
| `seed_default_functions()` | Whitelist | Seed settings with 55 default functions |
| `get_all_base_functions()` | Whitelist | List all BASE_FUNCS names |

**Security per endpoint:**
- Permission check (`_assert_read_perm`) for all read/evaluate endpoints
- Rate limiting via Redis atomic counters per user/action
- Input sanitization (`_sanitize_frm_doc`) filters out system fields and non-data fieldtypes
- AI suggest: only user with write access to Formula Builder Settings can use

**Validation pipeline (`validate_formula`):**
1. Permission check
2. Rate limit
3. Empty check
4. Length check (max_formula_length from settings)
5. AST parsing via `FormulaValidator`
6. Function whitelist + disabled function check
7. Scope variable recognition
8. Circular dependency detection via `FormulaEngine`

**Context building (`get_live_context`):**
1. Loads `Formula Variable Binding` records filtered by doctype/field
2. Resolves with topological dependency ordering (`resolve_bindings_with_deps`)
3. Includes current doc scalar fields
4. Builds cross-tables from child table meta (`_build_cross_tables`)
5. Includes legacy global variables (`Formula Global Variable`)
6. Caches with request-level scope (`frappe.local._vr_ctx_*`)

### 9.2 `formula_table_api.py` — Table API

**Endpoints:**

| Endpoint | Description |
|---|---|
| `calc_cell(formula, context, config_doctype, config_name)` | Evaluate single cell formula |
| `calc_table(rows, columns, globals, topo_order, ...)` | Batch evaluate all rows in child table |
| `validate_formula(formula, config_doctype, config_name)` | Validate single formula |
| `scc_check(nodes, edges)` | Detect cycles in dependency graph |

**Engine caching:** `calc_table` caches `FormulaEngine` instances to avoid reinitialization when formula assignments are identical across rows.

**DAG integration:**
- JS provides `topo_order` from client-side Kahn sort
- Server validates with `scc_check` endpoint
- Cross-row references (`items[idx].field`) resolved through shared context with all `items` data

### 9.3 `variable_resolver.py` — Variable Resolution

**Class `ScopeContext`** — Encapsulates the full editing context:
- `current_doctype`, `current_docname`, `child_table_field`, `row_index`, `line_ref`, `local_vars`, `formula_set_code`
- Internal caches: `_doc_cache`, `_meta_cache`, `_global_cache`
- `from_dict(d)` — Deserialize from JSON
- `get_doc(doctype, docname)` — Cached doc retrieval (skips `new-` docs)
- `child_table_fieldnames(doctype)` — Get Table-type fields

**Class `VariableResolver`** — 6-level resolution chain:
1. **`$name` / `$snap.field`** — Global variable or snapshot value
2. **Path with `.` or `[`** — Dispatches to `_resolve_path`
3. **Simple name** — `local_vars` → doc field → global fallback

**Path resolution:**
- `child_table["key"].field` or `child_table[n].field` — Index or line_ref
- `FS-CODE.var` — Formula Set output
- `prefix.field` (2-part) — Child current row or doctype field
- `p0.p1.field` (3-part) — Child line_ref or nested lookup

**Class `SuggestionsBuilder`** — Autocomplete data:
- `_global_vars()` — Active global variables with live values
- `_local_fields()` — DocType scalar + child table fields
- `_child_rows()` — Child table rows by line_ref/idx
- `_linked_doctypes()` — Link fields
- `_formula_sets()` — Active formula sets with variables
- `_functions()` — Allowed functions from settings
- `_snippets()` — Common formula patterns

### 9.4 `data_source_registry.py` — Data Source Registry

**Registry pattern with decorator registration:**

```python
@register_source("my_source_type")
def handle_my_source(binding, doc, resolved_so_far):
    # binding: Formula Variable Binding document
    # doc: current Frappe Document
    # resolved_so_far: dict of already-resolved variables
    return resolved_value
```

**10 Built-in Handlers:**

| Source Type | Description | Config Keys |
|---|---|---|
| `constant` | Static value | `value` |
| `linked_doctype_field` | Follow link → read field | `link_field`, `target_field` |
| `whole_doctype` | Return entire doc as dict | `doctype`, `docname_field`, `include_children` |
| `child_table_aggregate` | Aggregate child table (sum/avg/min/max/count/list) | `child_table_field`, `aggregate_field`, `method`, `filter_expr` |
| `global_default` | Read Global Defaults singleton | `key` |
| `session_variable` | Session info (user, roles, lang, now, today, company) | `key` |
| `doctype_query` | Filter + aggregate query | `doctype`, `field`, `aggregation`, `filters` |
| `custom_function` | Dynamic Python module import + call | `module_path`, `function_name`, `arguments` |
| `dynamic_link` | Follow dynamic link (doctype_field + name_field) | `doctype_field`, `name_field`, `target_field` |
| `computed` | Evaluate formula using resolved vars as context | `formula`, `dependencies` |

**Dependency Resolution:**
- `_get_dependency_graph(bindings)` — Builds adjacency graph
- `_topological_sort(graph)` — Kahn's algorithm
- `resolve_bindings_with_deps(bindings, doc)` — Topological resolution with fallback to priority-based

**Security for custom_function:**
- Reads `custom_function_whitelist` from settings
- Checks module path against whitelist prefixes
- Default whitelist: `formula_builder.custom_functions`, `formula_builder.formula_utils`, `frappe.utils`

### 9.5 `settings_cache.py` — Settings Cache

**Redis-based caching (5-min TTL):**
- `get_settings() → (allowed_funcs, disabled_funcs, max_formula_length)`
- `get_allowed_funcs() → Dict[str, Callable]`
- `get_disabled_funcs() → Set[str]`
- `get_max_formula_length() → int`
- `invalidate_cache()` — Delete Redis key

**Design decisions:**
- Only caches JSON-safe data (function names, not callables) to avoid pickle errors with lambdas
- Reconstructs callable dict from names on every read
- Falls back to full `BASE_FUNCS` if settings are missing or corrupted

---

## 10. Variable Resolution — Hệ thống biến

### Resolution Chain (thứ tự ưu tiên)

```
1. Local variables (từ local_vars parameter)
2. Doc fields (fields của document hiện tại)
3. Child table current row (khi đang edit trong child table)
4. Child table by index/line_ref (items[0].field, items.K1.field)
5. Global variables ($var_name hoặc $snapshot.field)
6. Formula Set outputs (FS-CODE.var_name)
```

### Cross-row Reference Syntax

```
items.K1.qty          → Giá trị qty của row có line_ref="K1"
items[0].qty          → Giá trị qty của row đầu tiên
tableName["key"].field → Line ref lookup
tableName[n].field    → Index-based lookup
```

### Cross-ref DAG Engine

Khi formula chứa cross-row references, engine:
1. Collect tất cả formula expressions từ child table rows (by line_ref)
2. Chuẩn hóa cross-row references: `items.lr.field` → `lr__field`
3. Build một `FormulaEngine` DAG duy nhất
4. Chạy topological sort và evaluate toàn bộ
5. Write-back kết quả vào từng row

---

## 11. Frontend — Giao diện

### 11.1 Formula Builder Dialog

**File:** `public/js/formula_builder.js` (2532 lines)

**Class `AluglassFormulaEditor`:**
- Full Monaco Editor integration (v0.45.0 from jsDelivr CDN)
- Custom "formula-builder" language with Monarch tokenizer
- Syntax highlighting: keywords, builtins, operators, `$variables`, strings, comments, numbers
- Autocomplete: `CompletionProvider v3` with smart triggers (`tableName[N].`, `word.`, `tableName[`)
- Hover provider: Shows function signatures and variable details
- Toolbar: Test, Format, Toggle multiline, Explain, Test with vars, Show context, Reload, Clear, Smart suggest, Copy, Shortcuts, Save template, Find/replace, Diff
- Sidebar: Tabs for Variables, Functions, Snippets, Templates — with search filter and drag-and-drop
- Bottom Panel: Result, Test Vars, Context, Explain, Debug, History tabs — resizable
- Validation: Debounced real-time validation with error/warning markers and chips
- Context caching: 30-second TTL via `ContextCache` class
- Welcome tour: Spotlight + tooltip cards on first use
- Find & Replace panel: In-editor search
- Diff overlay: Character-level diff computation (LCS-based)

**Public API:**
```javascript
// Open full dialog
formula_builder.formula.openDialog({value: "qty * rate", current_doctype: "Quotation Item", ...})

// Attach pill UI to form field
formula_builder.formula.attachToField(frm, "custom_formula", {read_only: false})

// Attach pill UI to child table field
formula_builder.formula.attachToChildField(frm, "items", "row_1", "custom_formula")

// Quick inline edit (returns Promise)
formula_builder.formula.quickEdit("qty * rate", {current_doctype: "Sales Order Item"})

// Sync after server-side changes
formula_builder.formula.syncFieldValue(frm, "custom_formula", newValue)

// Invalidate context cache
formula_builder.formula.invalidateContext("Sales Order")
```

### 11.2 Inline Field Patching

**File:** `public/js/formula_builder_field.js` (1382 lines)

**Features:**
- Replaces standard `<input>`/`<textarea>` with inline Monaco Editor
- Supports both parent doctype fields and child table fields
- Preview bar: shows evaluated result with error states
- "Open dialog" button for full Formula Builder
- Monaco loading fallback: degrades to textarea if CDN fails
- Global patching mode: `enableGlobalPatch()` hooks into `frappe.ui.form.Form.prototype.refresh`

**API:**
```javascript
// Patch single field
formula_builder.formula.patchField(frm, "custom_amount_formula")

// Patch child table field
formula_builder.formula.patchChildField(frm, "items", "row_1", "custom_qty_formula")

// Patch all eligible fields at once
formula_builder.formula.patchFormFields(frm)

// Global auto-patch on every form load
formula_builder.formula.enableGlobalPatch()
```

### 11.3 Grid Cell Editor

**File:** `public/js/formula_builder_field.js` (part of same file)

**Class `initGridField`:**
- **Single click** → Opens inline Monaco editor within cell
- **Double click** → Opens full Formula Builder dialog
- **Float popup mode** (`float_popup: true`) → Floating overlay above cell
- Auto-handles expanded row rendering (`form_render` event)
- Click-outside / Escape → Saves and closes
- `MutationObserver` cleanup on row close
- Independent click/dblclick per column → supports multiple formula columns

```javascript
formula_builder.formula.initGridField(frm, "items", "custom_qty_formula", {
    float_popup: true,
    height: 60
})
```

### 11.4 Declarative Dialog System

**File:** `public/js/formula_builder_dialog.js` (1023 lines)

**Schema DSL for building complex dialogs:**

```javascript
const schema = formula_builder.formulaDialog.define({
    title: "Bảng Tính Giá",
    icon: "calculator",
    width: 900,
    sections: [
        formula_builder.formulaDialog.filterSection({
            label: "Thông số",
            fields: [
                { fieldname: "date", fieldtype: "Date", label: "Ngày" },
                { fieldname: "vat_rate", fieldtype: "Percent", label: "VAT %", default: 10 },
                { fieldname: "discount", fieldtype: "Formula", label: "Công thức CK" }
            ]
        }),
        formula_builder.formulaDialog.tableSection({
            label: "Bảng tính",
            min_rows: 1,
            columns: [
                { fieldname: "description", fieldtype: "Data", label: "Mô tả" },
                { fieldname: "qty_formula", fieldtype: "Formula", label: "Công thức SL" },
                { fieldname: "price_formula", fieldtype: "Formula", label: "Công thức Giá" },
                { fieldname: "amount", fieldtype: "Float", label: "Thành tiền", read_only: true }
            ]
        }),
        formula_builder.formulaDialog.htmlSection({
            label: "Template",
            language: "html"
        })
    ],
    onSave: (data) => console.log("Saved:", data)
})

formula_builder.formulaDialog.open(schema, { initialData: {...} })
```

**Component classes:**
- `MonacoCell` — Mini Monaco editor in table/filter cells
- `TableBuilder` — Editable table with add/delete rows, Monaco cells
- `HTMLBuilder` — Monaco editor for HTML/template with preview toggle
- `DialogBuilder` — Full dialog with overlay, sections, footer, resize

### 11.5 CSS Design Tokens

**File:** `public/css/formula_builder_vars.css`

```css
:root {
  /* Background shades */
  --afb-bg0: #ffffff;
  --afb-bg1: #f9fafb;
  --afb-bg2: #f3f4f6;
  --afb-bg3: #e5e7eb;
  --afb-bg4: #d1d5db;

  /* Text colors */
  --afb-text: #111827;
  --afb-text2: #4b5563;
  --afb-text3: #9ca3af;

  /* Semantic colors */
  --afb-amber: #d97706;   /* Formula color */
  --afb-green: #059669;   /* Success / OK */
  --afb-red: #dc2626;     /* Error */
  --afb-blue: #2563eb;    /* Info */
  --afb-purple: #7c3aed;  /* Functions */
  --afb-cyan: #0891b2;    /* Strings */
  --afb-pink: #db2777;    /* Special */
  --afb-orange: #ea580c;  /* Warnings */

  /* Layout */
  --afb-radius: 6px;
  --afb-mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  --afb-ui: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --afb-shadow-md: 0 4px 6px -1px rgba(0,0,0,0.1);
  --afb-shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.1);
  --afb-tr: 0.15s ease;
}
```

---

## 12. FlexibleFormulaEngine — Multi-table Engine

**File:** `flexible_formula_engine.py`

This is a higher-level engine that orchestrates **multiple child tables + global formulas** in a single DAG calculation. It bridges the raw `FormulaEngine` with real-world ERP documents.

### Data Structures

**`ChildTableConfig`** — Configuration for one child table:

| Field | Type | Description |
|---|---|---|
| `table_key` | `str` | Key in context dict (e.g., `"items"`) |
| `formula_field` | `str` | Field holding raw formula |
| `id_field` | `str` | Row identifier (becomes engine var name, e.g., `K1`) |
| `row_fields` | `List[str]` | Columns whose values get injected as literals (empty = auto-detect) |
| `output_field` | `str` | Where to write back result |
| `prefix` | `str` | Disambiguation prefix (e.g., `TAX_`) |
| `skip_empty_formula` | `bool` | Silent skip for empty formulas |
| `assertions` | `List[Dict]` | Table-specific assertions |

**`EngineConfig`** — Global configuration:

| Field | Type | Description |
|---|---|---|
| `child_tables` | `List[ChildTableConfig]` | Child table configs |
| `global_formulas` | `List[Dict]` | Header-level calculations |
| `extra_context` | `Dict` | Static variables |
| `on_error` | `"raise"` / `"null"` / `"default"` | Error handling mode |
| `deterministic` | `bool` | Block non-deterministic functions |
| `max_operations` | `int` | Operation budget |
| `rounding_policy` | `Dict` | Per-variable rounding |
| `custom_functions` | `Dict` | Extra callables |
| `strict` | `bool` | Raise on unknown vars |

**`CalculationResult`** — Return value:
```python
result = engine.calculate(inputs)
result.values           # All results {name: value}
result.row_results      # {table_key: {row_name: values}}
result.errors           # {name: error_message}
result.warnings         # List of assertion warnings
result.get("K1_net")    # Lookup single value
result.table("taxes")   # Row results for one table
result.to_frappe_update() # Dict ready for frappe.db.set_value
```

### Key Methods

| Method | Description |
|---|---|
| `calculate(inputs)` | Main: build all formulas → one DAG → evaluate |
| `validate_formulas(inputs, extra_known_vars)` | Static AST validation |
| `explain(formula_name, inputs)` | Step-by-step trace for debugging |
| `multi_scenario(base_inputs, scenarios)` | Parallel what-if scenarios |
| `get_dependency_graph(inputs)` | DAG visualization data |
| `preview_resolved_formulas(inputs)` | Before/after injection debug |

### ERPNextAdapter & FrappeERPNextAdapter

**File:** `integration.py`

```python
from formula_builder.integration import (
    FlexibleFormulaEngine, EngineConfig, ChildTableConfig,
    FrappeERPNextAdapter, CalculationResult
)

class FrappeERPNextAdapter(ERPNextAdapter):
    def get_doc(self, doctype, docname):
        return frappe.get_doc(doctype, docname)

    def get_global_vars(self):
        # Queries Formula Global Variable (CONSTANT type only)
        ...

    def rows_to_dicts(self, doc, child_field):
        # Converts child table rows to plain dicts
        ...

# Build inputs from Frappe doc
inputs = build_inputs_from_frappe_doc(doc, child_table_map, scalar_fields, global_vars)
```

---

## 13. Security

### Defense in Depth

| Layer | Implementation | File |
|---|---|---|
| **AST Security** | Forbidden node types, names, dunder attrs | `security.py` |
| **Function Whitelist** | Only functions in `allowed_functions` child table | `settings_cache.py` |
| **Module Whitelist** | Custom function imports restricted to configured prefixes | `data_source_registry.py` |
| **DB Query Whitelist** | Only doctypes in `db_query_allowed_doctypes` can be queried | `variable_resolver.py` |
| **Permission Check** | `frappe.has_permission()` before every read/write | `api/formula_builder.py` |
| **Rate Limiting** | Redis atomic counter per user per action | `api/formula_builder.py` |
| **Input Sanitization** | Filter out system fields and non-data fieldtypes | `api/formula_builder.py` |
| **Formula Length** | `max_formula_length` from settings (default 2000) | `api/formula_builder.py` |
| **Operation Budget** | `max_operations` cap on engine evaluation | `engine_core.py` |
| **Self-reference Detection** | `detect_circular_bindings()` for bindings | `data_source_registry.py` |
| **Deterministic Mode** | Block `now()`, `today()`, `random()` when enabled | `engine_core.py` |
| **Snapshot Integrity** | Dual SHA-256 hash verification | `snapshot.py` |

### Rate Limits (configurable)

| Action | Default Limit | Window |
|---|---|---|
| Validate formula | 40/min | 60s |
| Evaluate formula | 20/min | 60s |
| AI suggestion | 5/min | 60s |

---

## 14. Performance & Caching

### Cache Architecture

| Cache | Store | TTL | Key Pattern | Content |
|---|---|---|---|---|
| **Suggestions** | Redis | 30s | `formula_suggestions:{doctype}:{docname}:...` | Autocomplete data |
| **Settings** | Redis | 5 min | `formula_builder_settings:v3` | Function names, disabled list, max length |
| **Live Context** | Request-local | Request | `frappe.local._vr_ctx_*` | Resolved context dict |
| **FormulaEngine** | Session-local | Session | `_engine_cache` in table API | Engine instances for identical formula sets |
| **Monaco** | Browser | Session | `window.__monacoLoaderPromise` | Monaco Editor CDN asset |
| **Context (JS)** | Browser Map | 30s | `"doctype::docname"` | Live context data from API |

### Optimization Patterns

1. **Incremental Calculation** — Only recompute affected nodes, not entire DAG
2. **Engine Hash** — Detect stale IncrementalContext by comparing formula set hash
3. **Batch Calculation** — `calculate_batch(rows)` reuses compiled bytecode
4. **Lazy DB Queries** — `ScopeContext` caches doc and meta lookups
5. **Batch Field Fetch** — `SuggestionsBuilder._local_fields()` batch-fetches all fields in one query
6. **Background Jobs** — Recommended for heavy tasks (cutting optimization, large formula sets) via `frappe.enqueue`

---

## 15. Integration Guide

### Quick Start — Add Formula Field to a DocType

```python
# In your app's hooks.py
from formula_builder.integration import (
    FlexibleFormulaEngine, EngineConfig, ChildTableConfig,
    FrappeERPNextAdapter, CalculationResult
)

@frappe.whitelist()
def calculate_quotation(doctype, docname):
    adapter = FrappeERPNextAdapter()
    doc = adapter.get_doc(doctype, docname)
    global_vars = adapter.get_global_vars()

    config = EngineConfig(
        child_tables=[
            ChildTableConfig(
                table_key="items",
                formula_field="custom_amount_formula",
                id_field="line_ref",
                row_fields=["qty", "rate", "custom_discount"],
                output_field="amount",
            ),
            ChildTableConfig(
                table_key="taxes",
                formula_field="custom_tax_formula",
                id_field="line_ref",
                row_fields=["charge_type", "rate"],
                output_field="tax_amount",
                prefix="TAX_",
            ),
        ],
        global_formulas=[
            {"name": "subtotal", "formula": "SUM(items.*.amount)"},
            {"name": "total_tax", "formula": "SUM(taxes.*.tax_amount)"},
            {"name": "grand_total", "formula": "subtotal + total_tax"},
        ],
        extra_context={"VAT_RATE": 0.1},
    )

    engine = FlexibleFormulaEngine(config)
    inputs = build_inputs_from_frappe_doc(
        doc, {"items": "items", "taxes": "taxes"},
        ["net_total", "conversion_rate"], global_vars
    )
    result = engine.calculate(inputs)

    # Write back to DB
    frappe.db.set_value(doctype, docname, result.to_frappe_update())

    return result.values
```

### Using the Frontend

```javascript
// In your form's client script
frappe.ui.form.on('Quotation', {
    refresh(frm) {
        // Option 1: Attach formula builder to a specific field
        formula_builder.formula.attachToField(frm, 'custom_amount_formula', {
            current_doctype: 'Quotation',
            current_docname: frm.doc.name
        });

        // Option 2: Open full dialog on button click
        frm.add_custom_button('Formula Builder', () => {
            formula_builder.formula.openDialog({
                value: frm.doc.custom_amount_formula,
                current_doctype: 'Quotation Item',
                current_docname: frm.doc.name,
                child_table_field: 'items',
                row_index: 0,
                onSave: (value) => {
                    frm.set_value('custom_amount_formula', value);
                }
            });
        });
    }
});
```

### Formula Syntax Examples

```
# Basic arithmetic
qty * rate

# With condition
qty * rate * (1 - IF(discount > 0, discount/100, 0))

# Cross-row reference
items.K1.qty + items.K2.qty

# Global variable
qty * rate * $VAT_RATE

# Formula Set
FS-PRICING.base_price * (1 + FS-PRICING.margin_pct/100)

# Cross-table reference
SUM(items.*.amount) * taxes.KVAT.rate / 100

# Array formula
SUMIF(items, ">1000", items.*.amount)

# Safe division
safe_div(amount, qty, 0)

# Lookup
vlookup(item_code, $PRICE_TABLE, 2, 0)
```

---

## 16. Hooks & Lifecycle

**File:** `hooks.py`

| Hook | Value | Description |
|---|---|---|
| `app_name` | `formula_builder` | App identifier |
| `app_title` | `Formula Builder` | Display name |
| `app_include_css` | 4 CSS files (with cache-busting version params) | Loaded on every Frappe page |
| `app_include_js` | 3 JS files (v2.0.1) | Loaded on every Frappe page |
| `doc_events` | `Formula Global Variable`, `Formula Set`, `Formula Builder Settings` → `on_update` → `invalidate_suggestions_cache` | Auto-invalidate caches on settings change |
| `fixtures` | `Formula Builder Settings` (filtered by name) | Auto-installed with app |
| `after_migrate` | `formula_builder.install.after_migrate` | Seed default settings on every migrate |

### Install Lifecycle

```
bench install-app formula_builder
  → Frappe installs app (runs patches, syncs doctypes)
  → after_migrate hook fires
  → install.after_migrate():
      1. Check if Formula Builder Settings exists → skip if yes (idempotent)
      2. Create default settings (max_length=2000, rate limits, AI config)
      3. Import all BASE_FUNCS and append as allowed_function rows
      4. Insert document with ignore_permissions=True
```

---

## 17. Development Guide

### Setup

```bash
# Clone and install
cd ~/frappe-bench
bench get-app https://github.com/your-org/formula_builder --branch develop
bench --site your-site install-app formula_builder

# Enable pre-commit
cd apps/formula_builder
pre-commit install

# Build on changes
bench build --app formula_builder
```

### Code Quality

- **Python:** ruff (line-length 110, Python 3.10 target), tab indentation
- **JS:** eslint, prettier
- **Python upgrade:** pyupgrade

### Testing

```bash
# Run tests
bench --site your-site run-tests --app formula_builder

# Run specific test file
bench --site your-site run-tests \
  --module formula_builder.formula_builder.doctype.formula_set.test_formula_set
```

Note: Test files are currently stubs. Tests should be added for:
- FormulaEngine core operations (parse, compile, evaluate, incremental)
- Security validation (forbidden nodes, names, deep subscript)
- Data source handlers (all 10 types)
- API endpoints (validate, evaluate, context, suggestions)
- Rate limiting behavior

### Adding a New Built-in Function

1. Implement in the appropriate module under `formula_utils/funcs/`
2. Add to `BASE_FUNCS` in `funcs/registry.py`
3. Add to `__all__` in `formula_utils/__init__.py`
4. Run `bench migrate` to auto-seed settings (or manually add via Formula Builder Settings)
5. Add to `FB_FUNCTIONS` in `public/js/formula_builder.js` for autocomplete

### Adding a New Data Source Type

1. Implement handler function in `data_source_registry.py`
2. Register with `@register_source("source_type_name")`
3. Add validation in `validate_binding_source_config()`
4. The new type will appear in `Formula Variable Binding` `source_type` select

### Extending the Frontend

```javascript
// Register custom functions for autocomplete
formula_builder.formula.FunctionRegistry.register('my_func', {
    name: 'MYFUNC',
    sig: 'MYFUNC(x, y)',
    cat: 'Tuy chinh',
    desc: 'My custom function',
    example: 'MYFUNC(1, 2)'
})

// Register custom snippets
formula_builder.formula.FunctionRegistry.addSnippet({
    label: 'My Pattern',
    value: 'my_func(qty, rate)',
    desc: 'Description'
})

// Register custom templates
formula_builder.formula.FunctionRegistry.addTemplate('My Category', {
    label: 'Template Name',
    formula: 'IF(qty > 0, qty * rate, 0)'
})
```

---

## 18. Roadmap / Future Work

- [ ] Add comprehensive test suite for all engine operations
- [ ] DocType client scripts for validation on Formula Global Variable / Formula Set
- [ ] Monaco Editor: Bracket matching, code folding, multi-cursor support
- [ ] Formula versioning and diff visualization
- [ ] Web Workers for heavy calculations to avoid blocking the main thread
- [ ] Real-time collaborative formula editing (CRDT-based)
- [ ] Integration with CAD/BIM dimension extraction
- [ ] Cutting stock optimization algorithm integration (1D/2D FFD/BFD)
- [ ] Cost Bucket integration with financial reports
- [ ] Performance benchmarks and profiling reports
- [ ] GraphQL/WebSocket API for formula evaluation
- [ ] Formula marketplace / sharing between sites
- [ ] Undo/redo stack in the formula editor
- [ ] Multi-language number-to-words (English, Chinese, Korean)

---

## License

MIT

## Author

Lê Ngọc — [lengoc1490@gmail.com](mailto:lengoc1490@gmail.com)

---

🤖 *Documentation generated with [Claude Code](https://claude.com/claude-code)*
