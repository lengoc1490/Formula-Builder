#!/usr/bin/env node
/**
 * Test Node thuần cho hộp xác nhận của Formula Builder
 * (`formula_builder/public/js/formula_builder.js` §9.1).
 *
 * KHÔNG cần site, KHÔNG cần npm/cài package — chạy:
 *     node formula_builder/tests/js/test_confirm_zindex.js
 *
 * Bối cảnh (lỗi giao diện): giao diện Formula Builder tự dựng overlay riêng
 * (dialog chính z-index 1100, suggest/shortcuts/diff/save-template 1000010).
 * `frappe.confirm` dựng modal Bootstrap chuẩn (z-index ~1040/1050) ⇒ nằm DƯỚI
 * overlay, người dùng chỉ thấy màn tối và ⛔ bấm được nút.
 *
 * Tệp này nạp CHÍNH khối JS thật vào Node bằng `new Function` + stub
 * `frappe`/`document`/`window` (cùng khuôn `eupapp/tests/*_client_sim.js`),
 * rồi kiểm:
 *   • hàm THUẦN `_computeConfirmZIndex` — mọi ca biên;
 *   • hành vi `formula_builder.confirm` — ngoài overlay dùng `frappe.confirm`,
 *     trong overlay dựng Dialog và nâng z-index modal/backdrop;
 *   • nút chính/phụ và Esc đóng mà ⛔ xóa.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const JS_PATH = path.join(
	__dirname, "..", "..", "public", "js", "formula_builder.js"
);

// ─────────────────────────────────────────────────────────── đếm PASS/FAIL
let passed = 0;
const failed = [];

function check(name, fn) {
	try {
		fn();
		passed += 1;
		console.log("  PASS  " + name);
	} catch (err) {
		failed.push(name);
		console.log("  FAIL  " + name);
		console.log("        " + (err && err.message ? err.message : err));
	}
}

function eq(actual, expected, msg) {
	const a = JSON.stringify(actual);
	const e = JSON.stringify(expected);
	if (a !== e) {
		throw new Error(
			(msg || "không khớp") + "\n        thực tế: " + a + "\n        mong đợi: " + e
		);
	}
}

function assert(cond, msg) {
	if (!cond) throw new Error(msg || "assert thất bại");
}

// ─────────────────────────────────────────────────────────── DOM giả tối thiểu
function makeElement(tag) {
	const el = {
		nodeType: 1,
		tagName: String(tag || "div").toUpperCase(),
		style: {},
		dataset: {},
		className: "",
		id: "",
		innerHTML: "",
		textContent: "",
		value: "",
		hidden: false,
		isConnected: true,
		parentNode: null,
		children: [],
		__computed: null,
		appendChild(c) {
			this.children.push(c);
			if (c) c.parentNode = this;
			return c;
		},
		insertBefore(c) {
			return this.appendChild(c);
		},
		removeChild() {},
		remove() {
			this.isConnected = false;
			this.parentNode = null;
		},
		setAttribute() {},
		getAttribute() {
			return null;
		},
		addEventListener() {},
		removeEventListener() {},
		querySelector() {
			return null;
		},
		querySelectorAll() {
			return [];
		},
		getClientRects() {
			return [{}];
		},
		getBoundingClientRect() {
			return { top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0 };
		},
		classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
		focus() {},
		click() {},
		contains() {
			return false;
		},
		closest() {
			return null;
		},
	};
	return el;
}

function makeOverlayNode(z, opts) {
	const el = makeElement("div");
	el.className = "afb-test-overlay";
	const zs = String(z);
	el.style.zIndex = zs;
	el.__computed = {
		display: opts && opts.hiddenDisplay ? "none" : "flex",
		visibility: "visible",
		zIndex: zs,
	};
	return el;
}

function makeDocument(state) {
	const doc = {
		_overlays: [],
		_backdrops: [],
		_modals: [],
		readyState: "complete",
		getElementById() {
			return null;
		},
		createElement(tag) {
			return makeElement(tag);
		},
		createTextNode() {
			return {};
		},
		querySelector(sel) {
			const s = String(sel || "");
			// `_isAnyModalOpen` hỏi ".modal.in, .modal.show, .modal[style*=...]".
			// So khớp THẬT từng vế để test bắt được việc chỉ phủ 1 đời Bootstrap.
			if (s.indexOf(".modal") === -1) return null;
			const hasClass = (el, name) =>
				new RegExp("(^|\\s)" + name + "(\\s|$)").test(el.className || "");
			for (const el of doc._modals) {
				if (s.indexOf(".modal.in") !== -1 && hasClass(el, "in")) return el;
				if (s.indexOf(".modal.show") !== -1 && hasClass(el, "show")) return el;
				if (
					s.indexOf(".modal[style*='display: block']") !== -1 &&
					String(el.style.display || "").indexOf("block") !== -1
				) {
					return el;
				}
			}
			return null;
		},
		querySelectorAll(sel) {
			const s = String(sel || "");
			if (s.indexOf(".modal-backdrop") !== -1) return doc._backdrops.slice();
			if (s.indexOf("afb-") !== -1) return doc._overlays.slice();
			return [];
		},
		addEventListener() {},
		removeEventListener() {},
		head: makeElement("head"),
		body: makeElement("body"),
		documentElement: makeElement("html"),
	};
	return doc;
}

/** Node modal Frappe giả: bsClass = "in" (v14) | "show" (v15) | fade-out. */
function makeModalNode(kind) {
	const el = makeElement("div");
	el.className = "modal";
	if (kind === "in") el.className = "modal fade in";
	if (kind === "show") el.className = "modal fade show";
	if (kind === "fading") el.style.display = "block"; // đang fade-out
	return el;
}

// ─────────────────────────────────────────────────────────── stub frappe/DOM
const state = {
	timers: [],
	dialogs: [],
	confirmCalls: [],
	focused: [],
	lastBackdrop: null,
	doc: null,
};

state.doc = makeDocument(state);

const win = {
	document: state.doc,
	navigator: { userAgent: "node" },
	location: { href: "http://localhost" },
	localStorage: {
		getItem() {
			return null;
		},
		setItem() {},
	},
	addEventListener() {},
	removeEventListener() {},
	setTimeout(fn) {
		state.timers.push(fn);
		return state.timers.length;
	},
	clearTimeout() {},
	getComputedStyle(node) {
		const cs = Object.assign(
			{ display: "block", visibility: "visible", zIndex: "auto" },
			(node && node.__computed) || {}
		);
		if (node && node.style && node.style.zIndex) cs.zIndex = node.style.zIndex;
		return cs;
	},
};

function flushTimers() {
	const list = state.timers.slice();
	state.timers.length = 0;
	list.forEach((fn) => fn());
}

/** Dialog giả — ghi lại opts, show tạo backdrop giống Bootstrap. */
function makeFakeDialogClass() {
	return class FakeDialog {
		constructor(opts) {
			this.opts = opts || {};
			this.shown = false;
			this.hidden = false;
			this.on_hide = null;
			this.wrapperEl = makeElement("div");
			this.wrapperEl.className = "modal fade";
			// Frappe v14: .modal { z-index: 1040 } (Bootstrap 3)
			this.wrapperEl.__computed = {
				display: "block",
				visibility: "visible",
				zIndex: "1040",
			};
			this.secondaryEl = makeElement("button");
			this.secondaryEl.focus = () => state.focused.push(this.secondaryEl);
			this.$wrapper = {
				get: () => this.wrapperEl,
				on: () => this.$wrapper,
			};
			state.dialogs.push(this);
		}
		get_secondary_btn() {
			return { get: () => this.secondaryEl };
		}
		show() {
			this.shown = true;
			const bd = makeElement("div");
			bd.className = "modal-backdrop";
			bd.__computed = { display: "block", visibility: "visible", zIndex: "1030" };
			state.doc._backdrops.push(bd);
			state.lastBackdrop = bd;
		}
		hide() {
			this.hidden = true;
			if (typeof this.on_hide === "function") this.on_hide();
		}
	};
}

const frappe = {
	ui: {},
	provide(ns) {
		const parts = String(ns).split(".");
		let o = globalThis;
		parts.forEach((k, i) => {
			if (i === 0) {
				o = globalThis[k] = globalThis[k] || {};
			} else {
				o = o[k] = o[k] || {};
			}
		});
		return o;
	},
	boot: { user: "Administrator", user_fullname: "Admin", lang: "vi" },
	call() {
		return Promise.resolve({ message: {} });
	},
	msgprint() {},
	show_alert() {},
	confirm() {
		state.confirmCalls.push(Array.prototype.slice.call(arguments));
	},
	utils: {},
	model: {},
	get_meta() {
		return null;
	},
	get_route() {
		return "";
	},
	session: {},
	xcall() {
		return Promise.resolve();
	},
	datetime: {
		now() {
			return "";
		},
		str_to_user() {
			return "";
		},
	},
};
state.frappe = frappe;

function makeJQueryStub() {
	const stub = function () {
		const o = makeElement("div");
		o.ready = (f) => f();
		o.on = () => o;
		o.off = () => o;
		o.append = () => o;
		o.html = () => o;
		o.text = () => o;
		o.val = () => o;
		o.attr = () => o;
		o.css = () => o;
		o.find = () => o;
		o.each = () => o;
		o.get = () => undefined;
		o.data = () => undefined;
		o.trigger = () => o;
		o.remove = () => o;
		o.parent = () => o;
		o.addClass = () => o;
		o.removeClass = () => o;
		o.toggleClass = () => o;
		o.hasClass = () => false;
		o.is = () => false;
		o.prop = () => o;
		o.hide = () => o;
		o.show = () => o;
		o.length = 0;
		return o;
	};
	stub.fn = {};
	stub.extend = Object.assign;
	stub.map = (a, f) => Array.prototype.map.call(a, f);
	return stub;
}

// ─────────────────────────────────────────────────────────── nạp JS THẬT
const $stub = makeJQueryStub();
const source = fs.readFileSync(JS_PATH, "utf8");

let fb;
const origLog = console.log;
try {
	console.log = () => {}; // tắt banner load của formula_builder.js
	const factory = new Function(
		"frappe",
		"$",
		"jQuery",
		"window",
		"document",
		"localStorage",
		"navigator",
		"self",
		"globalThis",
		source + "\n;return { fb: formula_builder, formula: formula_builder.formula };"
	);
	const out = factory(
		frappe,
		$stub,
		$stub,
		win,
		state.doc,
		win.localStorage,
		win.navigator,
		win,
		globalThis
	);
	fb = out.fb;
} catch (err) {
	origLog("KHÔNG nạp được formula_builder.js: " + (err && err.message));
	origLog((err && err.stack) || "");
	process.exit(1);
} finally {
	console.log = origLog;
}

if (!fb || typeof fb.confirm !== "function") {
	console.log("KHÔNG có formula_builder.confirm — dừng.");
	process.exit(1);
}

function resetWorld() {
	// Đóng mọi dialog còn mở để nhả bộ đếm modal của helper
	state.dialogs.forEach((d) => {
		try {
			if (typeof d.on_hide === "function") d.on_hide();
		} catch (e) { /* ignore */ }
	});
	flushTimers();
	state.doc._overlays = [];
	state.doc._backdrops = [];
	state.doc._modals = [];
	state.timers.length = 0;
	state.dialogs.length = 0;
	state.confirmCalls.length = 0;
	state.focused.length = 0;
	state.lastBackdrop = null;
	frappe.ui.Dialog = makeFakeDialogClass();
}

// ══════════════════════════════════════════════════════ A. HÀM THUẦN z-index
const calc = fb._computeConfirmZIndex;

console.log("\nA. _computeConfirmZIndex (hàm thuần)");

check("overlay 1000010 ⇒ modal phải cao hơn 1000010, backdrop nằm giữa", () => {
	const z = calc([1000010], 1040);
	eq(z, { modal: 1000030, backdrop: 1000020 });
	assert(z.modal > 1000010, "modal phải > overlay");
	assert(z.backdrop > 1000010, "backdrop phải > overlay");
	assert(z.backdrop < z.modal, "backdrop phải dưới modal");
});

check("overlay dialog chính 1100 ⇒ modal 1120 / backdrop 1110", () => {
	eq(calc([1100], 1040), { modal: 1120, backdrop: 1110 });
});

check("nhiều overlay ⇒ lấy lớp cao nhất (1000010)", () => {
	eq(calc([1100, 99994, 1000010], 1040), { modal: 1000030, backdrop: 1000020 });
});

check("không overlay + nền mặc định ⇒ 1050 / 1040 (z-index chuẩn Frappe)", () => {
	eq(calc([], undefined), { modal: 1050, backdrop: 1040 });
});

check("không overlay + nền đo được của Frappe v14 (1040) ⇒ 1040 / 1030", () => {
	eq(calc([], 1040), { modal: 1040, backdrop: 1030 });
});

check("overlay thấp hơn nền ⇒ giữ nền", () => {
	eq(calc([500], 1040), { modal: 1040, backdrop: 1030 });
});

check("overlay bằng đúng nền ⇒ vẫn nâng lên trên", () => {
	eq(calc([1050], 1050), { modal: 1070, backdrop: 1060 });
});

check("giá trị rác không làm hỏng kết quả", () => {
	eq(calc(["auto", null, undefined, NaN, -5, 0, "abc", ""], 1040), {
		modal: 1040,
		backdrop: 1030,
	});
});

check("nền không hợp lệ ⇒ rơi về 1050 / 1040", () => {
	eq(calc([], "auto"), { modal: 1050, backdrop: 1040 });
	eq(calc([], null), { modal: 1050, backdrop: 1040 });
	eq(calc([], -1), { modal: 1050, backdrop: 1040 });
});

check("nhận z-index dạng chuỗi số", () => {
	eq(calc(["1000010"], "1040"), { modal: 1000030, backdrop: 1000020 });
});

check("nền rất nhỏ (1) ⇒ backdrop dương và modal vẫn trên backdrop", () => {
	eq(calc([], 1), { modal: 2, backdrop: 1 });
});

check("danh sách không phải mảng ⇒ coi như rỗng", () => {
	eq(calc(undefined, 1050), { modal: 1050, backdrop: 1040 });
	eq(calc({ a: 1 }, 1050), { modal: 1050, backdrop: 1040 });
});

check("mọi đầu vào kỳ quặc ⇒ kết quả luôn là số nguyên dương", () => {
	const inputs = [
		[],
		[0],
		[-100],
		[NaN],
		[Infinity],
		[-Infinity],
		[""],
		[" "],
		[1.7],
		[999999999],
		[1000010, "auto", null],
	];
	const bases = [undefined, null, 0, -10, "auto", 1040, 1050, 1055];
	inputs.forEach((list) => {
		bases.forEach((base) => {
			const z = calc(list, base);
			assert(Number.isFinite(z.modal), "modal không hữu hạn: " + JSON.stringify([list, base]));
			assert(Number.isFinite(z.backdrop), "backdrop không hữu hạn: " + JSON.stringify([list, base]));
			assert(z.modal > 0 && z.backdrop > 0, "phải là số dương: " + JSON.stringify([list, base]));
			assert(z.backdrop < z.modal, "backdrop phải dưới modal: " + JSON.stringify([list, base]));
		});
	});
});

// ══════════════════════════════════════════════════ B. HÀNH VI HỘP XÁC NHẬN
console.log("\nB. formula_builder.confirm (hành vi)");

check("ngoài overlay ⇒ gọi frappe.confirm, KHÔNG dựng Dialog", () => {
	resetWorld();
	let yes = 0;
	const onNo = () => {};
	const dlg = fb.confirm("Xóa toàn bộ công thức?", () => yes++, { on_no: onNo });
	assert(dlg === null, "phải trả null ở đường frappe.confirm");
	eq(state.dialogs.length, 0, "không được dựng Dialog");
	eq(state.confirmCalls.length, 1, "phải gọi frappe.confirm 1 lần");
	eq(state.confirmCalls[0][0], "Xóa toàn bộ công thức?", "message");
	assert(typeof state.confirmCalls[0][1] === "function", "phải truyền on_yes");
	assert(state.confirmCalls[0][2] === onNo, "phải truyền on_no");
});

check("overlay ẩn (display:none) ⇒ coi như ngoài overlay", () => {
	resetWorld();
	state.doc._overlays = [makeOverlayNode(1000010, { hiddenDisplay: true })];
	const dlg = fb.confirm("Xóa?", () => {});
	assert(dlg === null, "phải đi đường frappe.confirm");
	eq(state.dialogs.length, 0);
	eq(state.confirmCalls.length, 1);
});

check("trong overlay ⇒ dựng Dialog (không gọi frappe.confirm), đúng title/nhãn/nội dung", () => {
	resetWorld();
	state.doc._overlays = [makeOverlayNode(1100)];
	fb.confirm("Xóa toàn bộ công thức?", () => {}, { yes_label: "Xóa" });
	eq(state.confirmCalls.length, 0, "KHÔNG được gọi frappe.confirm");
	eq(state.dialogs.length, 1, "phải dựng đúng 1 Dialog");
	const opts = state.dialogs[0].opts;
	eq(opts.title, "Xác nhận", "title");
	eq(opts.primary_action_label, "Xóa", "nhãn nút chính");
	eq(opts.secondary_action_label, "Hủy", "nhãn nút phụ");
	assert(Array.isArray(opts.fields) && opts.fields.length === 1, "phải có 1 field nội dung");
	eq(opts.fields[0].options, "Xóa toàn bộ công thức?", "nội dung message");
	eq(opts.no_focus, true, "phải tắt focus tự động của Frappe để tự focus nút Hủy");
	eq(state.focused.length, 1, "phải focus đúng 1 lần");
	assert(state.focused[0] === state.dialogs[0].secondaryEl, "phải focus nút phụ (Hủy)");
});

check("tôn trọng opts.title; không truyền thì mặc định 'Xác nhận'", () => {
	resetWorld();
	state.doc._overlays = [makeOverlayNode(1100)];
	fb.confirm("msg", () => {}, { title: "Xóa nội dung công thức đang soạn?" });
	eq(state.dialogs[0].opts.title, "Xóa nội dung công thức đang soạn?", "title truyền vào");
	resetWorld();
	state.doc._overlays = [makeOverlayNode(1100)];
	fb.confirm("msg", () => {});
	eq(state.dialogs[0].opts.title, "Xác nhận", "title mặc định");
});

check("overlay 1000010 ⇒ modal 1000030, backdrop 1000020", () => {
	resetWorld();
	state.doc._overlays = [makeOverlayNode(1000010)];
	const dlg = fb.confirm("Xóa?", () => {});
	eq(dlg.wrapperEl.style.zIndex, "1000030", "z-index modal");
	eq(state.lastBackdrop.style.zIndex, "1000020", "z-index backdrop");
	assert(Number(dlg.wrapperEl.style.zIndex) > 1000010, "modal phải nổi trên overlay");
});

check("nền Frappe v14 (1040) + overlay dialog chính (1100) ⇒ modal 1120 / backdrop 1110", () => {
	resetWorld();
	state.doc._overlays = [makeOverlayNode(1100)];
	const dlg = fb.confirm("Xóa?", () => {});
	eq(dlg.wrapperEl.style.zIndex, "1120");
	eq(state.lastBackdrop.style.zIndex, "1110");
});

check("nút chính ⇒ chạy on_yes đúng 1 lần, đóng dialog, không chạy on_no", () => {
	resetWorld();
	state.doc._overlays = [makeOverlayNode(1000010)];
	let yes = 0;
	let no = 0;
	const dlg = fb.confirm("Xóa?", () => yes++, { on_no: () => no++ });
	dlg.opts.primary_action();
	eq(yes, 1, "on_yes");
	eq(no, 0, "on_no");
	assert(dlg.hidden, "dialog phải đóng");
	assert(dlg.shown, "dialog đã show trước đó");
});

check("nút phụ ⇒ chạy on_no, KHÔNG chạy on_yes", () => {
	resetWorld();
	state.doc._overlays = [makeOverlayNode(1000010)];
	let yes = 0;
	let no = 0;
	const dlg = fb.confirm("Xóa?", () => yes++, { on_no: () => no++ });
	dlg.opts.secondary_action();
	eq(yes, 0, "on_yes");
	eq(no, 1, "on_no");
	assert(dlg.hidden, "dialog phải đóng");
});

check("Esc / bấm ngoài (on_hide không qua nút) ⇒ HỦY, ⛔ xóa", () => {
	resetWorld();
	state.doc._overlays = [makeOverlayNode(1000010)];
	let yes = 0;
	let no = 0;
	const dlg = fb.confirm("Xóa?", () => yes++, { on_no: () => no++ });
	dlg.on_hide(); // Bootstrap đóng modal
	eq(yes, 0, "on_yes KHÔNG được chạy");
	eq(no, 1, "on_no phải chạy");
});

check("đóng dialog ⇒ khôi phục z-index cũ của modal và backdrop", () => {
	resetWorld();
	state.doc._overlays = [makeOverlayNode(1000010)];
	const dlg = fb.confirm("Xóa?", () => {});
	const backdrop = state.lastBackdrop;
	eq(dlg.wrapperEl.style.zIndex, "1000030");
	assert(typeof backdrop.style.zIndex === "string", "backdrop phải có z-index tạm");
	dlg.opts.secondary_action();
	flushTimers();
	eq(dlg.wrapperEl.style.zIndex, "", "modal trả về z-index cũ (rỗng)");
	eq(backdrop.style.zIndex, "", "backdrop trả về z-index cũ (rỗng)");
});

check("không tự chạy on_yes/on_no khi chỉ dựng dialog", () => {
	resetWorld();
	state.doc._overlays = [makeOverlayNode(1000010)];
	let yes = 0;
	let no = 0;
	fb.confirm("Xóa?", () => yes++, { on_no: () => no++ });
	eq(yes, 0);
	eq(no, 0);
});

// ═══════════════════════════════════ D. ESC KHÔNG ĐƯỢC ĐÓNG BUILDER KHI CÓ MODAL
console.log("\nD. Guard Esc — không mất công thức đang gõ");

check("Esc khi đang mở hộp xác nhận ⇒ builder KHÔNG đóng, chưa chạy gì", () => {
	resetWorld();
	state.doc._overlays = [makeOverlayNode(1000010)];
	let yes = 0;
	let no = 0;
	const dlg = fb.confirm("Xóa?", () => yes++, { on_no: () => no++ });
	assert(fb._isAnyModalOpen() === true, "bộ đếm hộp xác nhận phải báo có modal mở");
	let closed = 0;
	const didClose = fb._runEscapeClose(() => closed++);
	eq(didClose, false, "guard phải chặn");
	eq(closed, 0, "⛔ được đóng builder");
	eq(yes, 0, "⛔ được chạy hành động xóa");
	// Bootstrap tự đóng modal khi Esc (handler của nó gắn trên chính modal)
	dlg.on_hide();
	eq(no, 1, "Esc do modal xử lý ⇒ Hủy");
	eq(yes, 0, "vẫn ⛔ chạy hành động xóa");
});

check("Esc khi có .modal.in (Frappe v14) ⇒ builder KHÔNG đóng", () => {
	resetWorld();
	state.doc._modals = [makeModalNode("in")];
	let closed = 0;
	eq(fb._runEscapeClose(() => closed++), false, "guard phải chặn");
	eq(closed, 0, "⛔ được đóng builder");
});

check("Esc khi có .modal.show (Frappe v15) ⇒ builder KHÔNG đóng", () => {
	resetWorld();
	state.doc._modals = [makeModalNode("show")];
	let closed = 0;
	eq(fb._runEscapeClose(() => closed++), false, "guard phải chặn");
	eq(closed, 0, "⛔ được đóng builder");
});

check("Esc lúc modal đang fade-out (còn display:block) ⇒ builder KHÔNG đóng", () => {
	resetWorld();
	state.doc._modals = [makeModalNode("fading")];
	let closed = 0;
	eq(fb._runEscapeClose(() => closed++), false, "guard phải chặn");
	eq(closed, 0, "⛔ được đóng builder");
});

check("Esc khi KHÔNG có modal ⇒ builder đóng như cũ", () => {
	resetWorld();
	let closed = 0;
	eq(fb._runEscapeClose(() => closed++), true, "phải cho đóng");
	eq(closed, 1, "closeDialog phải chạy đúng 1 lần");
});

check("đóng hộp xác nhận ⇒ nhả bộ đếm modal (Esc sau đó lại đóng được builder)", () => {
	resetWorld();
	state.doc._overlays = [makeOverlayNode(1000010)];
	const dlg = fb.confirm("Xóa?", () => {});
	assert(fb._isAnyModalOpen() === true, "đang mở");
	dlg.opts.secondary_action();
	flushTimers();
	assert(fb._isAnyModalOpen() === false, "phải nhả bộ đếm sau khi đóng");
	let closed = 0;
	eq(fb._runEscapeClose(() => closed++), true);
	eq(closed, 1);
});

check("mọi handler Esc cấp `document` đều đi qua _runEscapeClose", () => {
	const badDocHandlers = [
		'document.addEventListener("keydown",e=>{ if(e.key==="Escape") close(); },{once:true})',
		'document.addEventListener("keydown",e=>{ if(e.key==="Escape") closeDialog(); })',
	];
	badDocHandlers.forEach((bad) => {
		assert(source.indexOf(bad) === -1, "còn handler Esc chưa có guard: " + bad);
	});
	assert(
		source.indexOf('const escHandler = (e) => { if (e.key === "Escape") _runEscapeClose(closeDialog); };') !== -1,
		"escHandler của dialog chính chưa dùng guard"
	);
	assert(
		source.indexOf('this._tourEscHandler = e => { if(e.key==="Escape") _runEscapeClose(abort); };') !== -1,
		"tour Esc chưa dùng guard"
	);
});

// ══════════════════════════════════════════════════ C. CHỖ GỌI TRONG TOÀN APP
console.log("\nC. Chỗ gọi `_actClear` dùng helper");

check("_actClear không còn gọi thẳng frappe.confirm, dùng helper có title", () => {
	assert(
		source.indexOf('frappe.confirm("Xóa toàn bộ công thức?"') === -1,
		"vẫn còn frappe.confirm trực tiếp cho nút Xóa"
	);
	assert(
		source.indexOf("formula_builder.confirm(") !== -1,
		"_actClear chưa chuyển sang formula_builder.confirm"
	);
	assert(
		source.indexOf('title: "Xóa nội dung công thức đang soạn?"') !== -1,
		"thiếu tiêu đề hộp xác nhận mới"
	);
});

check("tooltip nút ✕ nói rõ xóa NỘI DUNG đang soạn", () => {
	assert(
		source.indexOf('title="Xóa toàn bộ nội dung đang soạn"') !== -1,
		"tooltip nút Xóa chưa đổi"
	);
	assert(source.indexOf('afb-act-clear"         title="Xóa"') === -1, "tooltip cũ vẫn còn");
});

check("nội dung xác nhận mới nói rõ không đụng mẫu đã lưu / dữ liệu chứng từ", () => {
	assert(
		source.indexOf(
			"Toàn bộ nội dung trong ô công thức sẽ bị xóa. Mẫu đã lưu và dữ liệu chứng từ không bị ảnh hưởng."
		) !== -1,
		"thiếu câu nội dung mới"
	);
	assert(
		source.indexOf('"Xóa toàn bộ công thức?"') === -1,
		"câu cũ mơ hồ vẫn còn trong file"
	);
});

check("⛔ KHÔNG bật confirm_dialog (Enter không được kích hoạt Xóa)", () => {
	assert(source.indexOf("confirm_dialog: true") === -1, "phát hiện confirm_dialog: true");
	assert(source.indexOf("confirm_dialog:true") === -1, "phát hiện confirm_dialog:true");
});

// ══════════════════════════════════════════════════════════════ KẾT QUẢ
console.log("\n──────────────────────────────────────────────");
console.log("Tổng: " + (passed + failed.length) + " ca · PASS " + passed + " · FAIL " + failed.length);
if (failed.length) {
	console.log("Ca hỏng: " + failed.join(" | "));
	process.exit(1);
}
