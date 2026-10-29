/* Figures of the stitching essay (docs/stitching/index.md).
 *
 * Every figure is a <div class="stv" data-stv="KIND" data-src="...json">. The JSON files are
 * written by tools/stitch_visuals.py from real runs; nothing here computes a result, it only
 * draws what the files hold. Plain JS and SVG, theme colours from CSS variables.
 */
(function () {
  "use strict";

  const SVGNS = "http://www.w3.org/2000/svg";
  const reduced = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const lang = () => ((document.documentElement.lang || "en").toLowerCase().startsWith("zh") ? "zh" : "en");

  const TEXT = {
    en: {
      table_a: "a", table_mod: "a % 5", table_out: "a ◆₁", check: "check",
      in_slot: "input slot a", units: "units", slot_mod: "slot a % 5", slot_out: "slot a ◆₁",
      layer: "layer", tokens: "tokens",
      op_caption: (a, u1, p1, q1, m, u2, out, ref, ok) =>
        `a = <b>${a}</b>. Layer 1: unit ${u1} reads the token <code>${a}</code> with weight 2 and bias −1, so it gets ` +
        `<code>${p1}</code> and passes it through the ReLU. Every other unit gets <code>${q1}</code> and passes 0. ` +
        `The unit writes token <code>${m}</code> into slot <code>a % 5</code>. Layer 2: unit ${u2} fires the same way and ` +
        `writes <code>${out}</code>. The interpreter gives <code>${ref}</code> ${ok ? '<span class="stv-ok">✓</span>' : '<span class="stv-bad">✗</span>'}.`,
      op_outside: "outside the inputs 0 to 15; the table still has a row for it",
      slot: "slot", after: "after layer", input_col: "input", ok_title: "matches the interpreter",
      skip_title: "branch not taken: the verifier does not check this slot for this input",
      wired: "▲₂ reads this slot as its a", coords: (s, e) => `coords ${s} to ${e}`,
      run: "Run", step: "Step", reset: "Reset",
      flow_start: (a, b) => `Input a = ${a}, b = ${b}. The residual stream holds only the two input slots.`,
      flow_layer: (k, blocks) => `Layer ${k} reads the slots its blocks need and writes ${blocks}.`,
      flow_done: (out, ref, n, m) =>
        `Output <code>${out}</code>; the interpreter gives <code>${ref}</code>. ${n} of ${n} checked slots match. ` +
        (m ? `${m} slot is not checked because its branch is not taken.` : ""),
      units_n: (n) => `${n} units`,
      layer_chip: (k, ops, n) => `layer ${k}: ${ops} (${n} units)`,
      whole: "whole compile", stitched: "stitched", compact: "stitched, then compacted",
      st_layers: "layers", st_dmodel: "residual width", st_max: "widest layer", st_nonzero: "nonzero weights",
      st_exact: "exact outputs", st_slots: "slot checks failed",
      verdict: (e) =>
        `Same outputs on all ${e.rows} inputs: <b>${e.same_outputs ? "yes" : "no"}</b>. ` +
        `Same weight blocks: <b>${e.same_blocks ? "yes" : "no"}</b>. ` +
        (e.same_blocks
          ? "Every block of one network appears in the other with equal weights. Slot placement differs, and stitching may stack blocks that the whole compile runs side by side."
          : `The whole compile knows that b is 7 and turns each ▲₂ table into a unary one, so its widest layer is ` +
            `<b>${e.narrower}</b> times narrower. Stitching copies ▲₂ as it is.`),
      key_a: "◆₁ blocks", key_b: "▲₂ blocks", key_sel: "select blocks", unit_scale: "bar length: hidden units",
      sigma: "weight noise σ", acc: "accuracy",
      series: { a: "◆₁ alone", b: "▲₂ alone", product: "product", stitched: "stitched", snap: "stitched + snap",
        snap_noisy: "stitched + noisy snap" },
      compiled: "compiled parts", trained: "trained parts", noisy_snap: "noise on the snap layer too",
      chart_note: (t) => `Mean over ${t} trials per σ; bands are 95% intervals (1.96 standard errors).`,
      kinds: { simple: "simple", branch: "branch", recursive: "recursive" },
      layers_n: (n) => `${n} ${n === 1 ? "layer" : "layers"}`, blocks_n: (n) => `${n} ${n === 1 ? "block" : "blocks"}`,
      mini_detail: (o) => `${o.symbol} (${o.kind}): <code>${o.definition}</code><br>` +
        `${o.layers} layers, ${o.blocks} blocks, ${o.nonzero} nonzero weights. Of ${o.rows} outputs: ` +
        `${o.exact - o.ref_out_of_range} exact values, ${o.ref_out_of_range} correct OOV, ${o.oov} OOV from an intermediate value; ` +
        `${o.slot_checks} slot checks, ${o.slot_wrong} wrong.`,
      key_exact: "exact value", key_ref: "correct OOV (answer out of range)", key_oov: "OOV from an intermediate value",
      key_depth: "depth (log scale)",
      mini_hint: "Hover or focus an operator to see its definition.",
    },
    zh: {
      table_a: "a", table_mod: "a % 5", table_out: "a ◆₁", check: " ",
      in_slot: "  a", units: " ", slot_mod: "  a % 5", slot_out: "  a ◆₁",
      layer: " ", tokens: " ",
      op_caption: (a, u1, p1, q1, m, u2, out, ref, ok) =>
        `a = <b>${a}</b>  1   ${u1}   2  −1   <code>${a}</code>  <code>${p1}</code> ` +
        `  ReLU   <code>${q1}</code>  0  <code>${m}</code>   <code>a % 5</code> ` +
        `  2   ${u2}   <code>${out}</code>  <code>${ref}</code> ` +
        `${ok ? '<span class="stv-ok">✓</span>' : '<span class="stv-bad">✗</span>'} `,
      op_outside: "  0   15  ",
      slot: " ", after: " ", input_col: " ", ok_title: " ",
      skip_title: " ",
      wired: "▲₂   a", coords: (s, e) => `  ${s}   ${e}`,
      run: " ", step: " ", reset: " ",
      flow_start: (a, b) => `  a = ${a} b = ${b} `,
      flow_layer: (k, blocks) => `  ${k}   ${blocks} `,
      flow_done: (out, ref, n, m) =>
        `  <code>${out}</code>  <code>${ref}</code>  ${n}  ` +
        (m ? `  ${m}  ` : ""),
      units_n: (n) => `${n}  `,
      layer_chip: (k, ops, n) => `  ${k}  ${ops} ${n}  `,
      whole: " ", stitched: " ", compact: " ",
      st_layers: " ", st_dmodel: " ", st_max: " ", st_nonzero: " ",
      st_exact: " ", st_slots: " ",
      verdict: (e) =>
        `${e.rows}  <b>${e.same_outputs ? " " : " "}</b> ` +
        ` <b>${e.same_blocks ? " " : " "}</b> ` +
        (e.same_blocks
          ? " "
          : `  b   7  ▲₂   <b>${e.narrower}</b>   ▲₂ `),
      key_a: "◆₁  ", key_b: "▲₂  ", key_sel: " ", unit_scale: " ",
      sigma: "  σ", acc: " ",
      series: { a: "◆₁  ", b: "▲₂  ", product: " ", stitched: " ", snap: "  +  ",
        snap_noisy: "  +  " },
      compiled: " ", trained: " ", noisy_snap: " ",
      chart_note: (t) => `  σ   ${t}   1.96   95%  `,
      kinds: { simple: " ", branch: " ", recursive: " " },
      layers_n: (n) => `${n}  `, blocks_n: (n) => `${n}  `,
      mini_detail: (o) => `${o.symbol} ${({ simple: " ", branch: " ", recursive: " " })[o.kind]} <code>${o.definition}</code><br>` +
        `${o.layers}  ${o.blocks}  ${o.nonzero}  ${o.rows}  ${o.exact - o.ref_out_of_range}  ` +
        `${o.ref_out_of_range}   OOV ${o.oov}   OOV  ${o.slot_checks}   ${o.slot_wrong}  `,
      key_exact: " ", key_ref: "  OOV ", key_oov: "  OOV", key_depth: " ",
      mini_hint: " ",
    },
  };
  const T = () => TEXT[lang()];

  // ------------------------------------------------------------------ helpers
  function el(tag, attrs, parent) {
    const node = tag.startsWith("svg:") ? document.createElementNS(SVGNS, tag.slice(4)) : document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "text") node.textContent = v;
      else if (k === "html") node.innerHTML = v;
      else if (k === "class") node.setAttribute("class", v);
      else node.setAttribute(k, v);
    }
    if (parent) parent.appendChild(node);
    return node;
  }
  function onResize(target, draw) {
    let last = 0;
    const run = () => {
      const w = Math.round(target.clientWidth);
      if (w && w !== last) { last = w; draw(w); }
    };
    if (window.ResizeObserver) new ResizeObserver(run).observe(target);
    else window.addEventListener("resize", run);
    run();
  }
  const cache = {};
  function load(src) {
    if (!cache[src]) cache[src] = fetch(src).then((r) => { if (!r.ok) throw new Error(src); return r.json(); });
    return cache[src];
  }
  function fmt(x, d) { return Number(x).toFixed(d === undefined ? 3 : d); }

  // ------------------------------------------------------- (a) an operator as weights
  function operator(root, data) {
    const t = T();
    const wrap = el("div", { class: "stv-op" }, root);
    const tableWrap = el("div", { class: "stv-table-wrap" }, wrap);
    const table = el("table", { class: "stv-table" }, tableWrap);
    const head = el("tr", {}, el("thead", {}, table));
    for (const h of [t.table_a, t.table_mod, t.table_out, t.check]) el("th", { text: h }, head);
    const body = el("tbody", {}, table);
    const netBox = el("div", { class: "stv-net" }, wrap);
    const caption = el("div", { class: "stv-caption", "aria-live": "polite" }, root);
    const rowsByInput = {};
    data.rows.forEach((r) => { rowsByInput[r.input] = r; });
    const domainRows = data.rows.filter((r) => r.in_domain);
    const trs = {};
    for (const r of domainRows) {
      const ok = r.labels[2] === r.ref[2];
      const tr = el("tr", { tabindex: "0" }, body);
      el("td", { text: r.labels[0] }, tr);
      el("td", { text: r.labels[1] }, tr);
      el("td", { text: r.labels[2] }, tr);
      el("td", { html: ok ? '<span class="stv-ok">✓</span>' : '<span class="stv-bad">✗</span>' }, tr);
      tr.addEventListener("mouseenter", () => select(r.input));
      tr.addEventListener("focus", () => select(r.input));
      tr.addEventListener("click", () => select(r.input));
      trs[r.input] = tr;
    }
    let current = domainRows[7].input;
    let svgParts = null;
    const V = data.tokens.length;

    function draw(width) {
      netBox.innerHTML = "";
      const W = Math.max(300, width);
      const rowH = 7, top = 46, H = top + V * rowH + 8;
      const xs = [0.12, 0.31, 0.53, 0.72, 0.93].map((f) => Math.round(f * W));
      const svg = el("svg:svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img",
        "aria-label": "◆₁ network: input slot, 50 units, slot a % 5, 50 units, output slot" }, netBox);
      const narrow = W < 560;
      const L1 = lang() === "zh" ? "  1  " : "layer 1", L2 = lang() === "zh" ? "  2  " : "layer 2";
      const heads = narrow
        ? [["a", `${V}`], [L1, `${data.blocks[0].units.length}`], ["a % 5", `${V}`], [L2, `${data.blocks[1].units.length}`], ["a ◆₁", `${V}`]]
        : [[t.in_slot, `${V} ${t.tokens}`], [L1, `${data.blocks[0].units.length} ${t.units}`],
          [t.slot_mod, `${V} ${t.tokens}`], [L2, `${data.blocks[1].units.length} ${t.units}`], [t.slot_out, `${V} ${t.tokens}`]];
      heads.forEach(([a, b], i) => {
        el("svg:text", { x: xs[i], y: 14, "text-anchor": "middle", class: "stv-col-head", text: a }, svg);
        el("svg:text", { x: xs[i], y: 28, "text-anchor": "middle", class: "stv-col-sub", text: b }, svg);
      });
      const y = (i) => top + i * rowH;
      const wires = [[], []];
      const g = el("svg:g", {}, svg);
      data.blocks.forEach((block, k) => {
        const xin = xs[2 * k], xu = xs[2 * k + 1], xout = xs[2 * k + 2];
        block.units.forEach((u, ui) => {
          const p1 = el("svg:path", { class: "stv-wire", d: `M${xin + 6},${y(u.in) + rowH / 2} L${xu - 4},${y(ui) + rowH / 2}` }, g);
          const p2 = el("svg:path", { class: "stv-wire", d: `M${xu + 4},${y(ui) + rowH / 2} L${xout - 6},${y(u.out) + rowH / 2}` }, g);
          wires[k][ui] = [p1, p2];
        });
      });
      const cells = [[], [], []];
      const units = [[], []];
      for (let c = 0; c < 3; c++) {
        for (let i = 0; i < V; i++) {
          const v = data.tokens[i];
          const inDom = c === 0 && /^\d+$/.test(v) && +v >= data.domain[0] && +v <= data.domain[1];
          cells[c][i] = el("svg:rect", { class: "stv-cell" + (inDom ? " stv-dom" : ""), x: xs[2 * c] - 6, y: y(i) + 0.5,
            width: 12, height: rowH - 1, rx: 1.5 }, svg);
        }
      }
      for (let k = 0; k < 2; k++) {
        data.blocks[k].units.forEach((u, ui) => {
          units[k][ui] = el("svg:circle", { class: "stv-unit", cx: xs[2 * k + 1], cy: y(ui) + rowH / 2, r: 2.6 }, svg);
        });
      }
      // token ticks on the input column
      [["-16", 0], ["0", 0], ["15", 0], ["31", -3], ["NaN OOV", 6]].forEach(([lab, dy]) => {
        const i = data.tokens.indexOf(lab.split(" ")[0]);
        if (i >= 0) el("svg:text", { x: xs[0] - 10, y: y(i) + rowH - 0.5 + dy, "text-anchor": "end", class: "stv-tick", text: lab }, svg);
      });
      const vals = [0, 1, 2].map((c) => el("svg:text", { x: xs[2 * c] + 10, y: 0, class: "stv-val", text: "" }, svg));
      // hit areas on the input column
      for (let i = 0; i < V; i++) {
        const hit = el("svg:rect", { class: "stv-hit", x: 0, y: y(i), width: xs[0] + 8, height: rowH }, svg);
        hit.addEventListener("mouseenter", () => select(i));
        hit.addEventListener("click", () => select(i));
      }
      svgParts = { cells, units, wires, vals, y, rowH };
      select(current);
    }

    function select(input) {
      current = input;
      const r = rowsByInput[input];
      for (const [k, tr] of Object.entries(trs)) tr.classList.toggle("stv-on", +k === input);
      if (svgParts) {
        const { cells, units, wires, vals, y, rowH } = svgParts;
        svg_clear(cells, units, wires);
        r.tokens.forEach((tok, c) => {
          cells[c][tok].classList.add("stv-on");
          vals[c].setAttribute("y", y(tok) + rowH);
          vals[c].textContent = r.labels[c];
        });
        r.fired.forEach((f, k) => {
          units[k][f.unit].classList.add("stv-on");
          wires[k][f.unit].forEach((p) => { p.classList.add("stv-on"); p.parentNode.appendChild(p); });
        });
      }
      const ok = r.labels[2] === r.ref[2];
      const fmtPre = (x) => (x < 0 ? "−" + Math.abs(x) : String(x));
      let html = t.op_caption(r.labels[0], r.fired[0].unit, fmtPre(r.fired[0].pre_max), fmtPre(r.fired[0].pre_second),
        r.labels[1], r.fired[1].unit, r.labels[2], r.ref[2], ok);
      if (!r.in_domain) html += ` <span class="stv-muted">(${t.op_outside})</span>`;
      caption.innerHTML = html;
    }
    function svg_clear(cells, units, wires) {
      cells.forEach((col) => col.forEach((c) => c.classList.remove("stv-on")));
      units.forEach((col) => col.forEach((c) => c.classList.remove("stv-on")));
      wires.forEach((col) => col.forEach((pair) => pair.forEach((p) => p.classList.remove("stv-on"))));
    }
    onResize(netBox, draw);
  }

  // ------------------------------------------------------- (b) slots in the residual stream
  function flow(root, data) {
    const t = T();
    const bar = el("div", { class: "stv-bar" }, root);
    const field = (name, value) => {
      const f = el("label", { class: "stv-field" }, bar);
      el("span", { text: name + " =" }, f);
      const input = el("input", { type: "range", min: 0, max: 15, value, "aria-label": name }, f);
      const out = el("output", { text: value }, f);
      return [input, out];
    };
    const [ia, oa] = field("a", 5);
    const [ib, ob] = field("b", 9);
    const run = el("button", { class: "stv-btn", type: "button", text: t.run }, bar);
    const stepB = el("button", { class: "stv-btn", type: "button", text: t.step }, bar);
    const reset = el("button", { class: "stv-btn", type: "button", text: t.reset }, bar);
    const L = data.layers.length;
    const table = el("table", { class: "stv-flow" }, root);
    const colgroup = el("colgroup", {}, table);
    el("col", { style: (root.clientWidth || 600) < 560 ? "width:31%" : "width:34%" }, colgroup);
    for (let k = 0; k <= L; k++) el("col", {}, colgroup);
    el("col", { style: "width:2.2rem" }, colgroup);
    const hr = el("tr", {}, el("thead", {}, table));
    el("th", { text: t.slot, style: "text-align:left" }, hr);
    const heads = [];
    const narrowFlow = (root.clientWidth || 600) < 560;
    if (narrowFlow) table.classList.add("stv-narrow");
    for (let k = 0; k <= L; k++) {
      const long = k === 0 ? t.input_col : (lang() === "zh" ? `  ${k}  ` : `after ${k}`);
      heads.push(el("th", { text: narrowFlow ? (k === 0 ? (lang() === "zh" ? " " : "in") : `L${k}`) : long, title: long }, hr));
    }
    el("th", { text: "✓" }, hr);
    const body = el("tbody", {}, table);
    const rows = data.slots.map((s) => {
      const tr = el("tr", {}, body);
      const part = s.part === "◆₁" ? "stv-part-a" : s.part === "▲₂" ? "stv-part-b" : "stv-part-in";
      const td = el("td", { class: "stv-slot " + part }, tr);
      el("span", { text: s.text }, td);
      el("small", { text: t.coords(s.start, s.start + s.size - 1) }, td);
      if (Object.values(data.wired).includes(s.name)) el("span", { class: "stv-wire-note", text: t.wired }, td);
      const cells = [];
      for (let k = 0; k <= L; k++) cells.push(el("td", { class: "stv-v stv-empty" }, tr));
      const check = el("td", { class: "stv-check" }, tr);
      return { s, cells, check };
    });
    const chips = el("div", { class: "stv-layers" }, root);
    const chipEls = data.layers.map((layer, i) => {
      const ops = layer.blocks.map((b) => (b.op === "select" && lang() === "zh" ? " " : b.op)).join(", ");
      return el("span", { class: "stv-layer", text: t.layer_chip(i + 1, ops, layer.hidden) }, chips);
    });
    const caption = el("div", { class: "stv-caption", "aria-live": "polite" }, root);
    let step = 0, timer = null, touched = false;
    bar.addEventListener("pointerdown", () => { touched = true; });
    bar.addEventListener("click", () => { touched = true; });
    bar.addEventListener("input", () => { touched = true; });

    function row() { return data.rows[+ia.value * 16 + +ib.value]; }
    function render(animate) {
      const r = row();
      rows.forEach(({ s, cells, check }, i) => {
        const [shown, ref, status] = r.slots[i];
        cells.forEach((td, k) => {
          const visible = k >= s.layer && k <= step;
          td.className = "stv-v" + (visible ? "" : " stv-empty") + (visible && k === s.layer && k === step ? " stv-new" : "");
          td.innerHTML = visible ? `<span>${shown}</span>` : "·";
          if (animate && visible && k === step && k === s.layer && !reduced()) td.firstChild.classList.add("stv-appear");
        });
        if (step >= s.layer) {
          if (status === "exact") check.innerHTML = `<span class="stv-ok" title="${t.ok_title}: ${ref}">✓</span>`;
          else if (status === "dont_care") check.innerHTML = `<span class="stv-skip" title="${t.skip_title}">○</span>`;
          else if (status === "input") check.innerHTML = "";
          else check.innerHTML = `<span class="stv-bad">✗</span>`;
        } else check.innerHTML = "";
      });
      heads.forEach((h, k) => h.classList.toggle("stv-now", k === step));
      chipEls.forEach((c, k) => c.classList.toggle("stv-now", k + 1 === step));
      if (step === 0) caption.innerHTML = t.flow_start(ia.value, ib.value);
      else if (step < L) {
        const written = data.slots.filter((s) => s.layer === step).map((s) => `<code>${s.text}</code>`).join(", ");
        caption.innerHTML = t.flow_layer(step, written);
      } else {
        const checked = r.slots.filter((x) => x[2] === "exact").length;
        const skipped = r.slots.filter((x) => x[2] === "dont_care").length;
        const outIdx = data.slots.length - 1;
        caption.innerHTML = t.flow_done(r.slots[outIdx][0], r.slots[outIdx][1], checked, skipped);
      }
    }
    function stop() { if (timer) { clearInterval(timer); timer = null; } }
    function play() {
      stop();
      if (reduced()) { step = L; render(false); return; }
      step = 0; render(true);
      timer = setInterval(() => { step += 1; render(true); if (step >= L) stop(); }, 900);
    }
    const changed = () => { oa.textContent = ia.value; ob.textContent = ib.value; stop(); step = L; render(false); };
    ia.addEventListener("input", changed);
    ib.addEventListener("input", changed);
    run.addEventListener("click", play);
    stepB.addEventListener("click", () => { stop(); step = step >= L ? 0 : step + 1; render(true); });
    reset.addEventListener("click", () => { stop(); step = 0; render(false); });
    step = 0; render(false);
    if (reduced()) { step = L; render(false); }
    else if (window.IntersectionObserver) {
      const io = new IntersectionObserver((entries) => {
        if (entries.some((e) => e.isIntersecting)) { io.disconnect(); if (!touched) play(); }
      }, { threshold: 0.4 });
      io.observe(root);
    } else play();
  }

  // ------------------------------------------------------- (c) whole versus stitched
  const OP_GROUP = { "%": "a", "*": "a", ">": "b", "-": "b", select: "sel" };
  const opName = (op) => (op === "select" && lang() === "zh" ? " " : op);
  function wholeStitched(root, data) {
    const t = T();
    const bar = el("div", { class: "stv-bar", role: "group" }, root);
    const symbols = Object.keys(data);
    const pair = el("div", { class: "stv-pair" }, root);
    const verdict = el("div", { class: "stv-verdict", "aria-live": "polite" }, root);
    const key = el("div", { class: "stv-key" }, root);
    for (const [k, lab] of [["a", t.key_a], ["b", t.key_b], ["sel", t.key_sel]]) {
      const s = el("span", {}, key);
      el("i", { style: `--k: var(--stv-${k === "sel" ? "sel" : k})` }, s);
      s.appendChild(document.createTextNode(lab));
    }
    el("span", { text: t.unit_scale }, key);
    let current = (root.closest(".stv") && root.closest(".stv").dataset.start) || "★₃";
    const buttons = symbols.map((sym) => {
      const b = el("button", { class: "stv-btn", type: "button", text: `${sym}  ${data[sym].definition}` }, bar);
      b.addEventListener("click", () => { current = sym; show(); });
      return [sym, b];
    });
    const cards = ["whole", "stitched"].map((form) => {
      const card = el("div", { class: "stv-net-card" }, pair);
      const h = el("h4", {}, card);
      const svgBox = el("div", { class: "stv-blocks" }, card);
      const stats = el("div", { class: "stv-stats" }, card);
      return { form, card, h, svgBox, stats };
    });
    function drawCard(c, width) {
      const e = data[current];
      const net = e[c.form];
      const scale = Math.max(e.whole.max_hidden, e.stitched.max_hidden);
      const W = Math.max(240, width), rowH = 26, labelW = 22, top = 2;
      const H = top + net.layers.length * rowH + 4;
      c.svgBox.innerHTML = "";
      const svg = el("svg:svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img",
        "aria-label": `${t[c.form]}: ${net.layers.length} ${t.st_layers}` }, c.svgBox);
      const trackW = W - labelW - 4;
      net.layers.forEach((layer, k) => {
        const y = top + k * rowH;
        el("svg:text", { x: 0, y: y + 15, class: "stv-row-label", text: `L${k + 1}` }, svg);
        el("svg:rect", { class: "stv-track", x: labelW, y: y + 3, width: trackW, height: rowH - 8, rx: 3 }, svg);
        let x = labelW;
        const spots = [];
        layer.blocks.forEach((b) => {
          const w = Math.max(3, (b.hidden / scale) * trackW);
          const grp = OP_GROUP[b.op] || "sel";
          const r = el("svg:rect", { class: `stv-blk k-${grp}`, x, y: y + 3, width: w, height: rowH - 8, rx: 2 }, svg);
          el("svg:title", { text: `${b.op}: ${b.hidden} ${t.units}${b.text ? " (" + b.text + ")" : ""}` }, r);
          spots.push([x, w, `${opName(b.op)} ${b.hidden}`]);
          x += w;
        });
        if (spots.every(([, w, lab]) => w > lab.length * 6.2 + 8)) {
          spots.forEach(([x0, , lab]) => el("svg:text", { x: x0 + 5, y: y + 15, class: "stv-blk-label stv-in", text: lab }, svg));
        } else {
          const label = layer.blocks.map((b) => `${opName(b.op)} ${b.hidden}`).join(", ");
          el("svg:text", { x: x + 5, y: y + 15, class: "stv-blk-label", text: label }, svg);
        }
      });
    }
    function show() {
      const e = data[current];
      buttons.forEach(([sym, b]) => b.setAttribute("aria-pressed", String(sym === current)));
      cards.forEach((c) => {
        const net = e[c.form];
        c.h.textContent = `${current} ${t[c.form]}`;
        c.stats.innerHTML = "";
        for (const [lab, v] of [[t.st_layers, net.layers.length], [t.st_dmodel, net.d_model], [t.st_max, net.max_hidden],
          [t.st_nonzero, net.nonzero_params], [t.st_exact, `${net.exact}/${e.rows}`],
          [t.st_slots, `${net.slot_wrong}/${net.slot_checks}`]]) {
          el("span", { html: `${lab} <b>${v}</b>` }, c.stats);
        }
        drawCard(c, c.svgBox.clientWidth || 300);
      });
      verdict.innerHTML = t.verdict(e);
    }
    show();
    cards.forEach((c) => onResize(c.svgBox, (w) => drawCard(c, w)));
  }

  // ------------------------------------------------------- (d) how errors compose
  const SERIES = [
    ["a", "--stv-s-a", false], ["b", "--stv-s-b", false], ["product", "--stv-s-prod", true],
    ["stitched", "--stv-s-stitched", false], ["snap", "--stv-s-snap", false], ["snap_noisy", "--stv-s-snap", true],
  ];
  function noise(root, data) {
    const t = T();
    const bar = el("div", { class: "stv-bar" }, root);
    const toggle = el("button", { class: "stv-btn", type: "button", "aria-pressed": "false", text: t.noisy_snap }, bar);
    const key = el("div", { class: "stv-key" }, root);
    const charts = el("div", { class: "stv-charts" }, root);
    el("div", { class: "stv-note", text: t.chart_note(data.trials) }, root);
    const tip = el("div", { class: "stv-tip", role: "tooltip" }, root);
    let showNoisy = false;
    function drawKey() {
      key.innerHTML = "";
      for (const [name, color, dashed] of SERIES) {
        if (name === "snap_noisy" && !showNoisy) continue;
        const s = el("span", {}, key);
        el("i", { class: dashed ? "stv-dash" : "", style: `--k: var(${color})` }, s);
        s.appendChild(document.createTextNode(t.series[name]));
      }
    }
    const panels = ["compiled", "trained"].map((kind) => {
      const box = el("div", { class: "stv-chart" }, charts);
      el("h4", { text: t[kind] }, box);
      const svgBox = el("div", {}, box);
      return { kind, svgBox };
    });
    function draw(p, width) {
      const W = Math.max(260, width), H = Math.round(Math.min(260, Math.max(200, W * 0.62)));
      const m = { l: 34, r: 10, t: 8, b: 34 };
      const sig = data.sigmas, xmax = sig[sig.length - 1];
      const X = (s) => m.l + (s / xmax) * (W - m.l - m.r);
      const Y = (v) => m.t + (1 - v) * (H - m.t - m.b);
      p.svgBox.innerHTML = "";
      const svg = el("svg:svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img",
        "aria-label": `${t[p.kind]}: ${t.acc} / ${t.sigma}` }, p.svgBox);
      for (const v of [0, 0.25, 0.5, 0.75, 1]) {
        el("svg:line", { class: "stv-grid", x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v) }, svg);
        el("svg:text", { class: "stv-tickl", x: m.l - 5, y: Y(v) + 3, "text-anchor": "end", text: v.toFixed(2) }, svg);
      }
      for (const s of [0, 0.1, 0.2, 0.3]) {
        el("svg:text", { class: "stv-tickl", x: X(s), y: H - m.b + 14, "text-anchor": "middle", text: s.toFixed(1) }, svg);
      }
      el("svg:line", { class: "stv-axis", x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0) }, svg);
      el("svg:text", { class: "stv-axis-label", x: (m.l + W - m.r) / 2, y: H - 4, "text-anchor": "middle",
        "font-size": 11, text: t.sigma }, svg);
      const series = data.series[p.kind];
      for (const [name, color, dashed] of SERIES) {
        if (name === "snap_noisy" && !showNoisy) continue;
        const pts = series[name];
        const band = pts.map((v, i) => `${X(sig[i])},${Y(v[2])}`).concat(pts.slice().reverse().map((v, j) => {
          const i = pts.length - 1 - j; return `${X(sig[i])},${Y(v[1])}`;
        }));
        el("svg:polygon", { class: "stv-band", points: band.join(" "), style: `fill: var(${color})` }, svg);
        el("svg:polyline", { class: "stv-line", points: pts.map((v, i) => `${X(sig[i])},${Y(v[0])}`).join(" "),
          style: `stroke: var(${color})`, "stroke-dasharray": dashed ? "5 4" : "" }, svg);
      }
      const cross = el("svg:line", { class: "stv-cross", y1: m.t, y2: Y(0), x1: -10, x2: -10, visibility: "hidden" }, svg);
      const dots = el("svg:g", {}, svg);
      const hit = el("svg:rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: Y(0) - m.t, fill: "transparent" }, svg);
      const move = (ev) => {
        const rect = svg.getBoundingClientRect();
        const px = ((ev.touches ? ev.touches[0].clientX : ev.clientX) - rect.left) * (W / rect.width);
        let best = 0;
        sig.forEach((s, i) => { if (Math.abs(X(s) - px) < Math.abs(X(sig[best]) - px)) best = i; });
        cross.setAttribute("x1", X(sig[best])); cross.setAttribute("x2", X(sig[best])); cross.setAttribute("visibility", "visible");
        dots.innerHTML = "";
        let rowsHtml = "";
        for (const [name, color] of SERIES) {
          if (name === "snap_noisy" && !showNoisy) continue;
          const v = series[name][best];
          el("svg:circle", { class: "stv-dot", cx: X(sig[best]), cy: Y(v[0]), r: 3.5, style: `fill: var(${color})` }, dots);
          rowsHtml += `<tr><td><i style="--k: var(${color})"></i>${t.series[name]}</td><td>${fmt(v[0], 4)} <span class="stv-muted">[${fmt(v[1], 3)}, ${fmt(v[2], 3)}]</span></td></tr>`;
        }
        tip.innerHTML = `<b>${t[p.kind]}, σ = ${sig[best]}</b><table class="stv-tiptable">${rowsHtml}</table>`;
        const host = root.getBoundingClientRect();
        let left = rect.left - host.left + (X(sig[best]) / W) * rect.width + 12;
        const tw = tip.offsetWidth || 200;
        if (left + tw > host.width) left = Math.max(4, left - tw - 24);
        if (left + tw > host.width) left = Math.max(0, host.width - tw);
        if (host.width < 500) {
          tip.style.left = "0px";
          tip.style.top = (rect.bottom - host.top + 4) + "px";
        } else {
          tip.style.left = Math.max(4, left) + "px";
          tip.style.top = (rect.top - host.top + 10) + "px";
        }
        tip.classList.add("stv-show");
      };
      const leave = () => { tip.classList.remove("stv-show"); dots.innerHTML = ""; cross.setAttribute("visibility", "hidden"); };
      hit.addEventListener("mousemove", move);
      hit.addEventListener("touchstart", move, { passive: true });
      hit.addEventListener("touchmove", move, { passive: true });
      hit.addEventListener("mouseleave", leave);
    }
    toggle.addEventListener("click", () => {
      showNoisy = !showNoisy;
      toggle.setAttribute("aria-pressed", String(showNoisy));
      drawKey();
      panels.forEach((p) => draw(p, p.svgBox.clientWidth));
    });
    drawKey();
    panels.forEach((p) => onResize(p.svgBox, (w) => draw(p, w)));
  }

  // ------------------------------------------------------- (e) generated operators
  function generated(root, data) {
    const t = T();
    const key = el("div", { class: "stv-key" }, root);
    for (const [k, c] of [["simple", "--stv-a"], ["branch", "--stv-b"], ["recursive", "--stv-sel"]]) {
      const s = el("span", {}, key);
      el("i", { style: `--k: var(${c})` }, s);
      s.appendChild(document.createTextNode(t.kinds[k]));
    }
    for (const [lab, c, op] of [[t.key_exact, "--stv-ok", 1], [t.key_ref, "--stv-ok", 0.45], [t.key_oov, "--stv-muted", 0.45]]) {
      const s = el("span", {}, key);
      el("i", { style: `--k: var(${c}); opacity:${op}` }, s);
      s.appendChild(document.createTextNode(lab));
    }
    el("span", { text: `▬ ${t.key_depth}` }, key);
    const grid = el("div", { class: "stv-multi", style: "margin-top:0.5rem" }, root);
    const detail = el("div", { class: "stv-def", "aria-live": "polite", text: t.mini_hint }, root);
    const order = { simple: 0, branch: 1, recursive: 2 };
    const ops = data.operators.slice().sort((x, y) => order[x.kind] - order[y.kind] || x.layers - y.layers);
    const maxL = Math.log(1 + Math.max(...ops.map((o) => o.layers)));
    for (const o of ops) {
      const card = el("div", { class: `stv-mini k-${o.kind}`, tabindex: "0", role: "button",
        "aria-label": `${o.symbol}: ${t.layers_n(o.layers)}` }, grid);
      el("b", { text: o.symbol }, card);
      const depth = el("div", { class: "stv-depth" }, card);
      el("i", { style: `width:${(100 * Math.log(1 + o.layers) / maxL).toFixed(1)}%` }, depth);
      el("small", { text: `${t.layers_n(o.layers)}, ${t.blocks_n(o.blocks)}` }, card);
      const share = el("div", { class: "stv-share", style: "margin-top:0.25rem" }, card);
      const inRange = o.exact - o.ref_out_of_range;
      if (inRange) el("i", { class: "ex", style: `flex:${inRange}` }, share);
      if (o.ref_out_of_range) el("i", { class: "ref", style: `flex:${o.ref_out_of_range}` }, share);
      if (o.oov) el("i", { class: "oov", style: `flex:${o.oov}` }, share);
      el("small", { text: `${inRange}/${o.rows}` }, card);
      const showIt = () => { detail.innerHTML = t.mini_detail(o); };
      card.addEventListener("mouseenter", showIt);
      card.addEventListener("focus", showIt);
      card.addEventListener("click", showIt);
    }
  }

  const KINDS = { operator, flow, whole: wholeStitched, noise, generated };

  function init() {
    document.querySelectorAll(".stv[data-stv]").forEach((root) => {
      if (root.dataset.stvDone) return;
      root.dataset.stvDone = "1";
      const draw = KINDS[root.dataset.stv];
      if (!draw) return;
      load(root.dataset.src).then((data) => {
        const mount = el("div", { class: "stv-mount" }, root);
        draw(mount, data);
        root.classList.add("stv-ready");
      }).catch(() => { /* the static text stays */ });
    });
  }
  if (document.readyState !== "loading") init(); else document.addEventListener("DOMContentLoaded", init);
  if (window.document$) window.document$.subscribe(init);
})();
