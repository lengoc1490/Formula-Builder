/**
 * ═══════════════════════════════════════════════════════════════════════════
 * formula_builder.formulaDialog  –  FORMULA DIALOG / TABLE / HTML BUILDER  v1.0
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Kiến trúc:
 *  §0   CSS Injection
 *  §1   Schema DSL helpers (defineDialog, defineTable, defineHTML)
 *  §2   MonacoCell  – Monaco nhúng trong 1 cell (reuse completionProvider từ formula_builder.js)
 *  §3   TableBuilder – render bảng phụ, bind row add/remove
 *  §4   HTMLBuilder  – render HTML template với Monaco cell
 *  §5   DialogBuilder – render toàn bộ dialog theo schema
 *  §6   Public API   – formula_builder.formulaDialog.*
 *
 * Không import/modify formula_builder.js. Chỉ đọc:
 *   - formula_builder.formula.loadMonaco()         (Monaco loader)
 *   - formula_builder.formula.CompletionRegistry   (register completion model)
 *   - formula_builder.formula.ContextCache         (context TTL cache)
 *   - formula_builder.formula._esc()               (XSS escape)
 *   - formula_builder.formula._serializeDoc()      (doc serializer)
 *   - window._afbPatchedEditors             (editor registry)
 *
 * Thêm vào hooks.py:
 *   app_include_js = [
 *     "/assets/formula_builder/js/formula_builder.js?v=...",
 *     "/assets/formula_builder/js/formula_builder_field.js?v=...",
 *     "/assets/formula_builder/js/formula_builder_dialog.js?v=1.0.0",   ← THÊM
 *   ]
 *
 * @version 1.0.0
 */

frappe.provide("formula_builder.formulaDialog");

// ═══════════════════════════════════════════════════════════════════════════
// §0  CSS INJECTION
// ═══════════════════════════════════════════════════════════════════════════
// ═══════════════════════════════════════════════════════════════════════════
// §0  CSS — now loaded externally via app_include_css (hooks.py)
// ═══════════════════════════════════════════════════════════════════════════
(function _injectDialogCSS() {
  // CSS đã được tách ra file riêng và load qua app_include_css.
  // Giữ guard check để không phá vỡ backward-compat.
  if (document.getElementById("afbd-css-v1")) return;
  const s = document.createElement("style");
  s.id = "afbd-css-v1";
  s.textContent = ""; // CSS moved to public/css/
  document.head.appendChild(s);
})();


// ═══════════════════════════════════════════════════════════════════════════
// §1  SCHEMA DSL HELPERS
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Định nghĩa một dialog schema.
 * @param {object} schema
 * @param {string} schema.title
 * @param {string} [schema.subtitle]
 * @param {string} [schema.icon]          emoji icon
 * @param {string} [schema.width]         default "760px"
 * @param {string} [schema.height]        default auto
 * @param {object} [schema.scope]         { current_doctype, current_docname, ... }
 * @param {Array}  schema.sections        mảng section
 * @param {string} [schema.footer_hint]
 * @returns schema object (pass vào DialogBuilder.open)
 */
formula_builder.formulaDialog.define = function(schema) {
  return Object.assign({
    title: "Dialog",
    icon: "📐",
    width: "760px",
    sections: [],
    footer_hint: "",
  }, schema);
};

/**
 * Tạo một filter row section (Company, From date, To date…).
 * @param {object} opts
 * @param {string} opts.label         Section label
 * @param {Array}  opts.fields        mảng field descriptor
 * @returns section descriptor
 *
 * Field descriptor:
 *   { fieldname, label, fieldtype, value, width, placeholder, formula }
 *   fieldtype: "Data" | "Date" | "Select" | "Formula" | "Int" | "Float"
 *   formula: true  → dùng Monaco cell thay vì input thường
 */
formula_builder.formulaDialog.filterSection = function(opts) {
  return Object.assign({ _type: "filter", label: "", fields: [] }, opts);
};

/**
 * Tạo một table section (Items, Accounts…).
 * @param {object} opts
 * @param {string} opts.label           Section label
 * @param {string} opts.key             key trong data object (vd: "items")
 * @param {Array}  opts.columns         mảng column descriptor
 * @param {Array}  [opts.rows]          initial rows
 * @param {boolean}[opts.show_idx]      hiển thị cột Idx (default true)
 * @param {boolean}[opts.allow_add]     cho phép thêm row (default true)
 * @param {boolean}[opts.allow_delete]  cho phép xóa row (default true)
 * @param {number} [opts.min_rows]      số row tối thiểu (default 3)
 * @returns section descriptor
 *
 * Column descriptor:
 *   { fieldname, label, fieldtype, width, placeholder, options, formula }
 *   fieldtype: "Data" | "Int" | "Float" | "Date" | "Select" | "Formula"
 *   formula: true  → Monaco cell
 *   width: CSS width string, ví dụ "120px", "1fr"
 */
formula_builder.formulaDialog.tableSection = function(opts) {
  return Object.assign({
    _type: "table", label: "", key: "rows",
    columns: [], rows: [], show_idx: true,
    allow_add: true, allow_delete: true, min_rows: 3,
  }, opts);
};

/**
 * Tạo một HTML / Monaco section dùng để soạn template hoặc công thức dài.
 * @param {object} opts
 * @param {string} opts.label
 * @param {string} opts.key             key trong data object
 * @param {string} [opts.language]      "formula-builder" | "html" | "python" | ...
 * @param {string} [opts.height]        default "120px"
 * @param {boolean}[opts.show_preview]  preview HTML output (chỉ khi language=html)
 * @param {string} [opts.value]         initial value
 * @returns section descriptor
 */
formula_builder.formulaDialog.htmlSection = function(opts) {
  return Object.assign({
    _type: "html", 
    label: "", 
    key: "html_content",
    language: "formula-builder", 
    height: "120px",
    show_preview: false, 
    value: "",
  }, opts);
};


// ═══════════════════════════════════════════════════════════════════════════
// §2  MONACO CELL (nhúng Monaco nhỏ vào 1 cell)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * MonacoCell – Monaco editor nhỏ trong một cell/field.
 * Tái dùng toàn bộ completion provider từ formula_builder.js.
 */
class MonacoCell {
  /**
   * @param {HTMLElement} container
   * @param {object} opts
   * @param {string}  opts.value
   * @param {string}  opts.language         default "formula-builder"
   * @param {string}  opts.height           default "28px"
   * @param {boolean} opts.word_wrap        default false
   * @param {object}  opts.scope            { current_doctype, current_docname, ... }
   * @param {function}opts.onChange
   * @param {string}  [opts.cellKey]        unique key để register editor
   */
  constructor(container, opts = {}) {
    this._container = container;
    this._opts      = Object.assign({
      value: "", 
      language: "formula-builder", 
      height: "28px",
      word_wrap: false, 
      scope: {}, 
      onChange: null, 
      cellKey: null,
    }, opts);
    this._editor    = null;
    this._disposed  = false;
    this._init();
  }

  _init() {
    // Placeholder loading
    const loading = document.createElement("div");
    loading.className = "afbd-mono-loading";
    loading.textContent = "Monaco…";
    this._container.appendChild(loading);

    // Đảm bảo loadMonaco được gọi
    const monacoLoader = formula_builder?.formula?.loadMonaco;
    if (typeof monacoLoader !== "function") {
      loading.textContent = "⚠ formula_builder.js chưa tải";
      console.error("[FormulaDialog] formula_builder.formula.loadMonaco not found. Load formula_builder.js trước.");
      return;
    }

    monacoLoader().then(() => {
      if (this._disposed || typeof monaco === "undefined") return;
      loading.remove();

      const language = this._opts.language || "formula-builder";

      // Tạo model Monaco
      this._model = monaco.editor.createModel(this._opts.value || "", language);

      // Container div
      const edDiv = document.createElement("div");
      edDiv.style.cssText = `height:${this._opts.height};min-height:22px;`;
      this._container.appendChild(edDiv);

      // Tạo editor
      this._editor = monaco.editor.create(edDiv, {
        model              : this._model,
        language           : language,
        theme              : "vs",
        fontSize           : 12,
        fontFamily         : "'JetBrains Mono','Fira Code',monospace",
        lineNumbers        : "off",
        glyphMargin        : false,
        folding            : false,
        lineDecorationsWidth: 0,
        lineNumbersMinChars: 0,
        minimap            : { enabled: false },
        scrollbar          : { vertical:"hidden", horizontal:"hidden", useShadows:false },
        overviewRulerLanes : 0,
        hideCursorInOverviewRuler: true,
        scrollBeyondLastLine: false,
        wordWrap           : this._opts.word_wrap ? "on" : "off",
        quickSuggestions   : true,
        suggestOnTriggerCharacters: true,
        tabSize            : 2,
        renderLineHighlight: "none",
        contextmenu        : false,
        fixedOverflowWidgets: true,
        padding            : { top: 4, bottom: 16 },
      });

      // Đăng ký completion model vào CompletionRegistry của formula_builder.js
      if (formula_builder?.formula?.CompletionRegistry?.register) {
        formula_builder.formula.CompletionRegistry.register(this._model, this._opts.scope || {});
        this._registeredModel = this._model;
      }

      // onChange callback
      this._changeDisposable = this._model.onDidChangeContent(() => {
        if (typeof this._opts.onChange === "function") {
          this._opts.onChange(this._model.getValue());
        }
      });

      // Đăng ký vào global registry nếu có cellKey
      if (this._opts.cellKey) {
        window._afbPatchedEditors = window._afbPatchedEditors || {};
        window._afbPatchedEditors[this._opts.cellKey] = {
          getValue: () => this._model?.getValue() || "",
          setValue: (v) => this._model?.setValue(v || ""),
          dispose : () => this.dispose(),
          getEditor: () => this._editor,
        };
      }

      this._editorReady = true;
    });
  }

  getValue() {
    return this._model?.getValue() || "";
  }

  setValue(val) {
    if (this._model) this._model.setValue(val || "");
  }

  layout() {
    if (this._editor) this._editor.layout();
  }

  dispose() {
    this._disposed = true;
    this._changeDisposable?.dispose?.();
    if (this._registeredModel && formula_builder?.formula?.CompletionRegistry?.unregister) {
      formula_builder.formula.CompletionRegistry.unregister(this._registeredModel);
    }
    this._editor?.dispose?.();
    this._model?.dispose?.();
    if (this._opts.cellKey && window._afbPatchedEditors?.[this._opts.cellKey]) {
      delete window._afbPatchedEditors[this._opts.cellKey];
    }
    this._editor = null;
    this._model  = null;
  }
}


// ═══════════════════════════════════════════════════════════════════════════
// §3  TABLE BUILDER
// ═══════════════════════════════════════════════════════════════════════════

class TableBuilder {
  /**
   * @param {HTMLElement} container
   * @param {object}      sectionDef   tableSection descriptor
   * @param {object}      scope        { current_doctype, current_docname, ... }
   */
  constructor(container, sectionDef, scope) {
    this._container = container;
    this._def       = sectionDef;
    this._scope     = scope || {};
    this._rows      = [];           // array of { _id, [fieldname]: value }
    this._cells     = new Map();    // _id+fieldname → MonacoCell
    this._uid       = 0;

    // Seed initial rows + min_rows blank
    const initRows  = sectionDef.rows || [];
    const minRows   = sectionDef.min_rows ?? 3;
    const seed      = initRows.length > 0 ? initRows : [];
    seed.forEach(r => this._pushRow(r));
    while (this._rows.length < minRows) this._pushRow({});

    this._render();
  }

  // ── Internal helpers ────────────────────────────────────────────────────

  _nextId() { return `r${++this._uid}`; }

  _pushRow(data = {}) {
    const row = Object.assign({ _id: this._nextId() }, data);
    this._rows.push(row);
    return row;
  }

  _cellKey(rowId, fieldname) {
    return `afbd::${this._def.key}::${rowId}::${fieldname}`;
  }

  _makeCell(td, row, col) {
    const ck  = this._cellKey(row._id, col.fieldname);
    const val = row[col.fieldname] ?? "";

    if (col.formula || col.fieldtype === "Formula") {
      // Monaco cell
      const wrap = document.createElement("div");
      wrap.className = "afbd-mono-cell-wrap";
      wrap.style.cssText = `width:${col.width || "100%"};min-width:80px;`;
      td.appendChild(wrap);

      const cell = new MonacoCell(wrap, {
        value    : String(val),
        language : col.language || "formula-builder",
        height   : col.cell_height || "28px",
        word_wrap: col.word_wrap || false,
        scope    : this._scope,
        cellKey  : ck,
        onChange : (v) => { row[col.fieldname] = v; },
      });
      this._cells.set(ck, cell);
    } else if (col.fieldtype === "Select") {
      const sel = document.createElement("select");
      const options = (col.options || "").split("\n").filter(Boolean);
      options.forEach(o => {
        const opt = document.createElement("option");
        opt.value = opt.textContent = o;
        if (o === val) opt.selected = true;
        sel.appendChild(opt);
      });
      sel.addEventListener("change", () => { row[col.fieldname] = sel.value; });
      td.appendChild(sel);
    } else {
      // Regular input
      const inp = document.createElement("input");
      inp.type  = col.fieldtype === "Date" ? "date"
                : (col.fieldtype === "Int" || col.fieldtype === "Float") ? "number"
                : "text";
      inp.value = val !== "" && val != null ? val : "";
      inp.placeholder = col.placeholder || "";
      if (col.width) inp.style.width = col.width;
      inp.addEventListener("input", () => { row[col.fieldname] = inp.value; });
      td.appendChild(inp);
    }
  }

  _renderRow(row, tbody) {
    const def = this._def;
    const tr  = document.createElement("tr");
    tr.dataset.rowId = row._id;

    // Idx
    if (def.show_idx !== false) {
      const tdIdx = document.createElement("td");
      tdIdx.className = "afbd-td-idx";
      tdIdx.textContent = this._rows.indexOf(row) + 1;
      tr.appendChild(tdIdx);
    }

    // Data columns
    def.columns.forEach(col => {
      const td = document.createElement("td");
      if (col.col_width) td.style.width = col.col_width;
      this._makeCell(td, row, col);
      tr.appendChild(td);
    });

    // Delete button
    if (def.allow_delete !== false) {
      const tdDel = document.createElement("td");
      const btn   = document.createElement("button");
      btn.className   = "afbd-del-btn";
      btn.title       = "Xóa dòng";
      btn.textContent = "✕";
      btn.addEventListener("click", () => this._deleteRow(row._id));
      tdDel.appendChild(btn);
      tr.appendChild(tdDel);
    }

    tbody.appendChild(tr);
  }

  _rebuildIdxColumn() {
    const trs = this._container.querySelectorAll("tbody tr");
    trs.forEach((tr, i) => {
      const tdIdx = tr.querySelector(".afbd-td-idx");
      if (tdIdx) tdIdx.textContent = i + 1;
    });
  }

  _deleteRow(rowId) {
    // Dispose Monaco cells for this row
    this._def.columns.forEach(col => {
      const ck   = this._cellKey(rowId, col.fieldname);
      const cell = this._cells.get(ck);
      if (cell) { cell.dispose(); this._cells.delete(ck); }
    });
    // Remove DOM
    const tr = this._container.querySelector(`tr[data-row-id="${rowId}"]`);
    if (tr) tr.remove();
    // Remove from _rows
    const idx = this._rows.findIndex(r => r._id === rowId);
    if (idx !== -1) this._rows.splice(idx, 1);
    this._rebuildIdxColumn();
  }

  _addRow() {
    const row  = this._pushRow({});
    const tbody = this._container.querySelector("tbody");
    this._renderRow(row, tbody);
    this._rebuildIdxColumn();
    // Scroll into view
    const newTr = tbody.querySelector(`tr[data-row-id="${row._id}"]`);
    newTr?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // ── Render ──────────────────────────────────────────────────────────────

  _render() {
    const def = this._def;
    const wrap = document.createElement("div");
    wrap.className = "afbd-table-wrap";

    const table = document.createElement("table");
    table.className = "afbd-table";

    // THEAD
    const thead = document.createElement("thead");
    const trHead = document.createElement("tr");
    if (def.show_idx !== false) {
      const th = document.createElement("th");
      th.className = "afbd-th-idx";
      th.textContent = "Idx";
      trHead.appendChild(th);
    }
    def.columns.forEach(col => {
      const th = document.createElement("th");
      th.textContent = col.label || col.fieldname;
      if (col.col_width) th.style.width = col.col_width;
      trHead.appendChild(th);
    });
    if (def.allow_delete !== false) {
      const th = document.createElement("th");
      th.className = "afbd-th-del";
      trHead.appendChild(th);
    }
    thead.appendChild(trHead);
    table.appendChild(thead);

    // TBODY
    const tbody = document.createElement("tbody");
    this._rows.forEach(row => this._renderRow(row, tbody));
    table.appendChild(tbody);

    wrap.appendChild(table);
    this._container.appendChild(wrap);

    // Add row button
    if (def.allow_add !== false) {
      const addBtn = document.createElement("button");
      addBtn.className   = "afbd-add-row-btn";
      addBtn.innerHTML   = "＋ Thêm dòng";
      addBtn.addEventListener("click", () => this._addRow());
      this._container.appendChild(addBtn);
    }
  }

  // ── Public API ──────────────────────────────────────────────────────────

  /** Lấy data hiện tại dưới dạng array */
  getData() {
    return this._rows.map(row => {
      const out = {};
      this._def.columns.forEach(col => {
        const ck   = this._cellKey(row._id, col.fieldname);
        const cell = this._cells.get(ck);
        out[col.fieldname] = cell ? cell.getValue() : (row[col.fieldname] ?? "");
      });
      return out;
    });
  }

  /** Set data (rebuild rows) */
  setData(rows) {
    // Dispose all cells
    this._cells.forEach(c => c.dispose());
    this._cells.clear();
    // Clear DOM
    const tbody = this._container.querySelector("tbody");
    if (tbody) tbody.innerHTML = "";
    this._rows = [];
    this._uid  = 0;
    // Re-seed
    (rows || []).forEach(r => this._pushRow(r));
    while (this._rows.length < (this._def.min_rows ?? 3)) this._pushRow({});
    this._rows.forEach(row => {
      const tbody2 = this._container.querySelector("tbody");
      this._renderRow(row, tbody2);
    });
    this._rebuildIdxColumn();
  }

  dispose() {
    this._cells.forEach(c => c.dispose());
    this._cells.clear();
  }
}


// ═══════════════════════════════════════════════════════════════════════════
// §4  HTML BUILDER (Monaco cho HTML / template / formula dài)
// ═══════════════════════════════════════════════════════════════════════════

class HTMLBuilder {
  constructor(container, sectionDef, scope) {
    this._container = container;
    this._def       = sectionDef;
    this._scope     = scope || {};
    this._cell      = null;
    this._render();
  }

  _render() {
    const def  = this._def;
    const wrap = document.createElement("div");
    wrap.className = "afbd-html-block";

    // Toolbar
    const toolbar = document.createElement("div");
    toolbar.className = "afbd-html-toolbar";
    const badge = document.createElement("span");
    badge.className   = "afbd-html-lang-badge";
    badge.textContent = def.language || "formula";
    toolbar.appendChild(badge);

    // Preview button (HTML only)
    let previewArea = null;
    if (def.show_preview && (def.language === "html" || def.language === "HTML")) {
      const prevBtn = document.createElement("button");
      prevBtn.className   = "afbd-html-preview-btn";
      prevBtn.textContent = "👁 Preview";
      prevBtn.addEventListener("click", () => {
        if (!previewArea) return;
        const visible = previewArea.classList.toggle("visible");
        if (visible) previewArea.innerHTML = this._cell?.getValue() || "";
      });
      toolbar.appendChild(prevBtn);

      previewArea = document.createElement("div");
      previewArea.className = "afbd-html-preview-area";
    }

    wrap.appendChild(toolbar);

    // Monaco container
    const monoWrap = document.createElement("div");
    monoWrap.className = "afbd-mono-cell-wrap";
    monoWrap.style.borderRadius = "0";
    monoWrap.style.borderLeft = monoWrap.style.borderRight = monoWrap.style.borderBottom = "none";
    monoWrap.style.borderTop = "none";
    wrap.appendChild(monoWrap);

    if (previewArea) wrap.appendChild(previewArea);

    this._container.appendChild(wrap);

    // Init Monaco cell
    this._cell = new MonacoCell(monoWrap, {
      value    : def.value || "",
      language : def.language || "formula-builder",
      height   : def.height || "120px",
      word_wrap: true,
      scope    : this._scope,
      cellKey  : `afbd::html::${def.key}`,
      onChange : (v) => {
        if (previewArea && previewArea.classList.contains("visible")) {
          previewArea.innerHTML = v;
        }
      },
    });
  }

  getValue() { return this._cell?.getValue() || ""; }
  setValue(v){ this._cell?.setValue(v); }
  dispose()  { this._cell?.dispose(); }
}


// ═══════════════════════════════════════════════════════════════════════════
// §5  DIALOG BUILDER
// ═══════════════════════════════════════════════════════════════════════════

class DialogBuilder {
  /**
   * @param {object} schema   formula_builder.formulaDialog.define(...)
   */
  constructor(schema) {
    this._schema    = schema;
    this._overlay   = null;
    this._dialog    = null;
    this._scope     = schema.scope || {};
    this._filterData= {};       // flat key→value cho filter section
    this._tables    = new Map();// key → TableBuilder
    this._htmlBlocks= new Map();// key → HTMLBuilder
    this._filterCells = new Map(); // key → MonacoCell (filter formula fields)
    this._onSave    = schema.onSave || null;
    this._onCancel  = schema.onCancel || null;
  }

  // ── Open ────────────────────────────────────────────────────────────────

  open() {
    if (this._overlay) return;
    this._buildDOM();
    document.body.appendChild(this._overlay);

    // Esc to close
    this._escHandler = (e) => { if (e.key === "Escape") this.close(); };
    document.addEventListener("keydown", this._escHandler);

    // Layout Monaco editors after mount
    setTimeout(() => this._layoutAll(), 120);
    return this;
  }

  close() {
    document.removeEventListener("keydown", this._escHandler);
    this._tables.forEach(t => t.dispose());
    this._htmlBlocks.forEach(h => h.dispose());
    this._filterCells.forEach(c => c.dispose());
    this._tables.clear();
    this._htmlBlocks.clear();
    this._filterCells.clear();
    if (this._overlay) { this._overlay.remove(); this._overlay = null; }
    if (typeof this._onCancel === "function") this._onCancel();
  }

  /** Lấy toàn bộ data từ dialog */
  getData() {
    const result = Object.assign({}, this._filterData);

    // Filter monaco cells
    this._filterCells.forEach((cell, key) => {
      result[key] = cell.getValue();
    });

    // Tables
    this._tables.forEach((tb, key) => {
      result[key] = tb.getData();
    });

    // HTML blocks
    this._htmlBlocks.forEach((hb, key) => {
      result[key] = hb.getValue();
    });

    return result;
  }

  /** Set data vào dialog */
  setData(data = {}) {
    // Filter fields
    this._schema.sections
      .filter(s => s._type === "filter")
      .forEach(sec => {
        sec.fields.forEach(f => {
          if (data[f.fieldname] === undefined) return;
          if (f.formula || f.fieldtype === "Formula") {
            this._filterCells.get(f.fieldname)?.setValue(String(data[f.fieldname]));
          } else {
            const inp = this._dialog?.querySelector(
              `[data-filter-field="${f.fieldname}"]`
            );
            if (inp) inp.value = data[f.fieldname];
            this._filterData[f.fieldname] = data[f.fieldname];
          }
        });
      });

    // Tables
    this._schema.sections
      .filter(s => s._type === "table")
      .forEach(sec => {
        if (data[sec.key] !== undefined) {
          this._tables.get(sec.key)?.setData(data[sec.key]);
        }
      });

    // HTML blocks
    this._schema.sections
      .filter(s => s._type === "html")
      .forEach(sec => {
        if (data[sec.key] !== undefined) {
          this._htmlBlocks.get(sec.key)?.setValue(data[sec.key]);
        }
      });
  }

  // ── DOM builders ────────────────────────────────────────────────────────

  _buildDOM() {
    const schema = this._schema;

    // Overlay
    this._overlay = document.createElement("div");
    this._overlay.className = "afbd-overlay";
    this._overlay.addEventListener("mousedown", (e) => {
      if (e.target === this._overlay) this.close();
    });

    // Dialog
    const dlg = document.createElement("div");
    dlg.className = "afbd-dialog";
    dlg.style.width = schema.width || "760px";
    if (schema.height) dlg.style.height = schema.height;
    dlg.style.maxWidth = "98vw";
    this._dialog = dlg;

    // Header
    dlg.appendChild(this._buildHeader());

    // Body
    const body = document.createElement("div");
    body.className = "afbd-body";

    schema.sections.forEach(sec => {
      body.appendChild(this._buildSection(sec));
    });

    dlg.appendChild(body);

    // Footer
    dlg.appendChild(this._buildFooter());

    // Resize handle
    const resizeHandle = document.createElement("div");
    resizeHandle.className = "afbd-resize-handle";
    resizeHandle.textContent = "⤡";
    resizeHandle.title = "Kéo để thay đổi kích thước";
    this._initResize(dlg, resizeHandle);
    dlg.appendChild(resizeHandle);

    this._overlay.appendChild(dlg);
  }

  _buildHeader() {
    const schema = this._schema;
    const header = document.createElement("div");
    header.className = "afbd-header";

    const iconEl = document.createElement("div");
    iconEl.className   = "afbd-header-icon";
    iconEl.textContent = schema.icon || "📐";
    header.appendChild(iconEl);

    const titleWrap = document.createElement("div");
    titleWrap.style.flex = "1";
    const titleEl = document.createElement("div");
    titleEl.className   = "afbd-header-title";
    titleEl.textContent = schema.title || "Dialog";
    titleWrap.appendChild(titleEl);
    if (schema.subtitle) {
      const sub = document.createElement("div");
      sub.className   = "afbd-header-sub";
      sub.textContent = schema.subtitle;
      titleWrap.appendChild(sub);
    }
    header.appendChild(titleWrap);

    const closeBtn = document.createElement("button");
    closeBtn.className   = "afbd-header-close";
    closeBtn.textContent = "✕";
    closeBtn.title       = "Đóng (Esc)";
    closeBtn.addEventListener("click", () => this.close());
    header.appendChild(closeBtn);

    return header;
  }

  _buildFooter() {
    const schema = this._schema;
    const footer = document.createElement("div");
    footer.className = "afbd-footer";

    const hint = document.createElement("span");
    hint.className   = "afbd-footer-hint";
    hint.textContent = schema.footer_hint || "Ctrl+Space: gợi ý • Esc: đóng";
    footer.appendChild(hint);

    // Custom buttons
    const extraBtns = schema.extra_buttons || [];
    extraBtns.forEach(eb => {
      const btn = document.createElement("button");
      btn.className   = "afbd-action-btn " + (eb.type || "");
      btn.textContent = eb.label || "Action";
      btn.addEventListener("click", () => {
        if (typeof eb.onClick === "function") eb.onClick(this.getData(), this);
      });
      footer.appendChild(btn);
    });

    // Cancel
    const cancelBtn = document.createElement("button");
    cancelBtn.className   = "afbd-action-btn";
    cancelBtn.textContent = "✕ Hủy";
    cancelBtn.addEventListener("click", () => this.close());
    footer.appendChild(cancelBtn);

    // Save
    const saveBtn = document.createElement("button");
    saveBtn.className   = "afbd-action-btn primary";
    saveBtn.textContent = schema.save_label || "💾 Lưu";
    saveBtn.addEventListener("click", () => this._onSaveClick());
    footer.appendChild(saveBtn);

    return footer;
  }

  _buildSection(sec) {
    const wrap = document.createElement("div");
    wrap.className = "afbd-section";

    if (sec.label) {
      const title = document.createElement("div");
      title.className   = "afbd-section-title";
      title.textContent = sec.label;
      wrap.appendChild(title);
    }

    switch (sec._type) {
      case "filter": this._buildFilterSection(wrap, sec); break;
      case "table":  this._buildTableSection(wrap, sec);  break;
      case "html":   this._buildHTMLSection(wrap, sec);   break;
      default:
        wrap.innerHTML += `<div style="color:#ef4444;font-size:11px;">Unknown section type: ${sec._type}</div>`;
    }

    return wrap;
  }

  _buildFilterSection(wrap, sec) {
    const row = document.createElement("div");
    row.className = "afbd-filter-row";

    sec.fields.forEach(f => {
      const fieldWrap = document.createElement("div");
      fieldWrap.className = "afbd-filter-field";
      if (f.width) fieldWrap.style.flexBasis = f.width;
      if (f.max_width) fieldWrap.style.maxWidth = f.max_width;

      const label = document.createElement("label");
      label.textContent = f.label || f.fieldname;
      fieldWrap.appendChild(label);

      if (f.formula || f.fieldtype === "Formula") {
        // Monaco cell
        const cellWrap = document.createElement("div");
        cellWrap.className = "afbd-mono-cell-wrap";
        fieldWrap.appendChild(cellWrap);

        const cell = new MonacoCell(cellWrap, {
          value    : String(f.value || ""),
          language : f.language || "formula-builder",
          height   : f.height || "28px",
          word_wrap: f.word_wrap || false,
          scope    : this._scope,
          cellKey  : `afbd::filter::${f.fieldname}`,
          onChange : (v) => { this._filterData[f.fieldname] = v; },
        });
        this._filterCells.set(f.fieldname, cell);
      } else if (f.fieldtype === "Select") {
        const sel = document.createElement("select");
        sel.dataset.filterField = f.fieldname;
        const opts = (f.options || "").split("\n").filter(Boolean);
        opts.forEach(o => {
          const opt = document.createElement("option");
          opt.value = opt.textContent = o;
          if (o === f.value) opt.selected = true;
          sel.appendChild(opt);
        });
        sel.addEventListener("change", () => { this._filterData[f.fieldname] = sel.value; });
        this._filterData[f.fieldname] = f.value || (opts[0] || "");
        fieldWrap.appendChild(sel);
      } else {
        const inp = document.createElement("input");
        inp.type  = f.fieldtype === "Date" ? "date"
                  : (f.fieldtype === "Int" || f.fieldtype === "Float") ? "number"
                  : "text";
        inp.value = f.value !== undefined ? f.value : "";
        inp.placeholder   = f.placeholder || "";
        inp.dataset.filterField = f.fieldname;
        inp.addEventListener("input", () => { this._filterData[f.fieldname] = inp.value; });
        this._filterData[f.fieldname] = f.value ?? "";
        fieldWrap.appendChild(inp);
      }

      row.appendChild(fieldWrap);
    });

    wrap.appendChild(row);
  }

  _buildTableSection(wrap, sec) {
    const tb = new TableBuilder(wrap, sec, this._scope);
    this._tables.set(sec.key, tb);
  }

  _buildHTMLSection(wrap, sec) {
    const hb = new HTMLBuilder(wrap, sec, this._scope);
    this._htmlBlocks.set(sec.key, hb);
  }

  // ── Save ────────────────────────────────────────────────────────────────

  _onSaveClick() {
    const data = this.getData();
    if (typeof this._onSave === "function") {
      const result = this._onSave(data, this);
      // Nếu onSave trả về false → không đóng
      if (result === false) return;
    }
    this.close();
  }

  // ── Layout ──────────────────────────────────────────────────────────────

  _layoutAll() {
    this._filterCells.forEach(c => c.layout());
    this._tables.forEach(tb => {
      tb._cells.forEach(c => c.layout());
    });
    this._htmlBlocks.forEach(hb => hb._cell?.layout());
  }

  // ── Resize ──────────────────────────────────────────────────────────────

  _initResize(dlg, handle) {
    let startX, startY, startW, startH;
    handle.addEventListener("mousedown", (e) => {
      e.preventDefault();
      startX = e.clientX;
      startY = e.clientY;
      const rect = dlg.getBoundingClientRect();
      startW = rect.width;
      startH = rect.height;

      const onMove = (ev) => {
        const dx = ev.clientX - startX;
        const dy = ev.clientY - startY;
        dlg.style.width  = Math.max(400, startW + dx) + "px";
        dlg.style.height = Math.max(300, startH + dy) + "px";
        this._layoutAll();
      };
      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup",   onUp);
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup",   onUp);
    });
  }
}


// ═══════════════════════════════════════════════════════════════════════════
// §6  PUBLIC API
// ═══════════════════════════════════════════════════════════════════════════

/** Mở một dialog từ schema, trả về DialogBuilder instance */
formula_builder.formulaDialog.open = function(schema, opts = {}) {
  const merged = Object.assign({}, schema, {
    onSave  : opts.onSave   || schema.onSave,
    onCancel: opts.onCancel || schema.onCancel,
    scope   : opts.scope    || schema.scope || {},
  });
  const builder = new formula_builder.formulaDialog.Builder(merged);
  builder.open();
  return builder;
};

/** Expose class để advanced use */
formula_builder.formulaDialog.Builder   = DialogBuilder;
formula_builder.formulaDialog.MonacoCell = MonacoCell;
formula_builder.formulaDialog.TableBuilder = TableBuilder;
formula_builder.formulaDialog.HTMLBuilder  = HTMLBuilder;

console.info("[Formula Dialog Builder v1.0] Loaded — DialogBuilder, TableBuilder, HTMLBuilder, MonacoCell");