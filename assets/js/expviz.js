(() => {
  "use strict";

  const copy = {
    en: { vary: "What we vary", fixed: "What stays fixed", measure: "What we measure", arms: "Arms", record: "Generated data", outcomes: "Possible outcomes, not results", steps: "reference rewrites", transfer: "transfer" },
    zh: { vary: " ", fixed: " ", measure: " ", arms: " ", record: " ", outcomes: " ", steps: " ", transfer: " ", headerTag: " " }
  };
  const svgNS = "http://www.w3.org/2000/svg";

  function el(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = String(value);
    return node;
  }
  function svg(tag, attributes) {
    const node = document.createElementNS(svgNS, tag);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  }
  function values(vary) {
    const quantities = (vary.values || []).map(value => /^\d+/.exec(String(value))?.[0]).map(value => value === undefined ? null : Number(value));
    const measured = quantities.length > 0 && quantities.every(value => value !== null);
    const maximum = measured ? Math.max(...quantities) : 0;
    const shape = measured && ["stack", "bars"].includes(vary.shape)
      ? (vary.shape === "stack" && maximum > 4 ? "bars" : vary.shape) : "chips";
    const row = el("div", `op-xp-values op-xp-values-${shape}`);
    (vary.values || []).forEach((value, index) => {
      const item = el("span", "op-xp-value");
      if (shape === "stack") {
        const stack = el("span", "op-xp-stack");
        for (let n = 0; n < quantities[index]; n++) stack.append(el("i"));
        item.append(stack);
      } else if (shape === "bars") {
        const bar = el("span", "op-xp-bar");
        bar.style.setProperty("--xp-width", `${100 * quantities[index] / Math.max(1, maximum)}%`);
        if (quantities[index] === 0) bar.style.minWidth = "0";
        item.append(bar);
      }
      item.append(el("span", "op-xp-value-label", value));
      row.append(item);
    });
    return row;
  }
  function column(title, type, items, knob) {
    const col = el("div", `op-xp-col op-xp-col-${type}`);
    col.append(el("div", "op-xp-heading", title));
    if (knob) col.append(el("strong", "op-xp-knob", knob));
    if (type === "vary") col.append(values(items));
    else {
      const list = el("div", "op-xp-chips");
      items.forEach(item => list.append(el("span", `op-xp-chip op-xp-chip-${type}`, item)));
      col.append(list);
    }
    return col;
  }
  function design(spec, t) {
    const wrap = el("div", "op-xp-design");
    const grid = el("div", "op-xp-grid");
    grid.append(column(t.vary, "vary", spec.vary, spec.vary.knob));
    grid.append(column(t.fixed, "fixed", spec.fixed));
    grid.append(column(t.measure, "measure", spec.measure));
    wrap.append(grid);
    if (Array.isArray(spec.lanes) && spec.lanes.length) {
      const arms = el("div", "op-xp-arms");
      arms.append(el("span", "op-xp-arms-label", t.arms));
      spec.lanes.forEach(lane => {
        const line = el("div", "op-xp-lane");
        line.append(el("strong", "op-xp-lane-name", lane.name));
        (lane.steps || []).forEach((step, index) => {
          if (index) line.append(el("span", "op-xp-step-arrow", "→"));
          line.append(el("span", "op-xp-step", step));
        });
        arms.append(line);
      });
      wrap.append(arms);
    }
    if (spec.arrow) {
      const arrow = el("div", "op-xp-transfer");
      arrow.append(el("span", "", spec.arrow.from), el("b", "", "→"), el("span", "", spec.arrow.to), el("small", "", spec.arrow.label || t.transfer));
      wrap.append(arrow);
    }
    return wrap;
  }
  function recordStrip(peek, t) {
    if (!peek || !Array.isArray(peek.records) || !peek.records.length) return null;
    const translated = t === copy.zh;
    const wrap = el("div", "op-xp-records");
    wrap.append(el("div", "op-xp-heading", t.record));
    const note = translated ? (peek.note_zh || peek.note) : peek.note;
    if (note) wrap.append(el("div", "op-xp-note", note));
    if (peek.command && !peek.records.some(record => record.command)) wrap.append(el("code", "op-xp-command", peek.command));
    const list = el("div", "op-xp-record-list");
    peek.records.forEach((record, index) => {
      const card = el("div", "op-xp-record");
      const label = translated ? (record.label_zh || record.label) : record.label;
      const tag = translated ? (record.tag_zh || record.tag) : record.tag;
      if (label || tag) {
        const head = el("div", "op-xp-record-head");
        if (label) head.append(el("strong", "op-xp-record-label", label));
        if (tag) head.append(el("span", "op-xp-record-tag", tag));
        card.append(head);
      }
      if (record.command || peek.command) card.append(el("code", "op-xp-command", record.command || peek.command));
      if (Array.isArray(record.operators) && record.operators.length) {
        const ops = el("div", "op-xp-operators");
        record.operators.forEach(op => ops.append(el("code", "", op)));
        card.append(ops);
      }
      if (record.expression !== undefined || record.answer !== undefined) {
        const expression = el("div", "op-xp-expression");
        if (record.expression !== undefined) expression.append(el("code", "", record.expression));
        if (record.expression !== undefined && record.answer !== undefined) expression.append(el("span", "", "="));
        if (record.answer !== undefined) expression.append(el("code", "", record.answer));
        card.append(expression);
      }
      if (Array.isArray(record.lines) && record.lines.length) {
        const lines = el("div", "op-xp-lines");
        record.lines.slice(0, 8).forEach(line => lines.append(el("code", "", line)));
        card.append(lines);
      }
      const meta = el("div", "op-xp-meta");
      if (record.steps !== undefined) meta.append(el("span", "", t === copy.zh ? `${t.steps} ${record.steps}  ` : `${record.steps} ${t.steps}`));
      if (record.fields && typeof record.fields === "object") {
        Object.entries(record.fields).forEach(([key, value]) => meta.append(el("span", "", `${key.replaceAll("_", " ")}: ${value}`)));
      }
      if (meta.childNodes.length) card.append(meta);
      list.append(card);
    });
    wrap.append(list);
    return wrap;
  }
  function sketch(spec, t) {
    const fig = el("figure", "op-xp-sketch");
    fig.append(el("figcaption", "op-xp-heading", t.outcomes));
    const plot = svg("svg", { viewBox: "0 0 500 160", role: "img", "aria-label": t === copy.zh ? `${t.outcomes} ${spec.y} ${spec.x} ` : `${t.outcomes}: ${spec.y} by ${spec.x}` });
    plot.append(svg("line", { x1: 46, y1: 125, x2: 470, y2: 125, class: "op-xp-axis" }));
    plot.append(svg("line", { x1: 46, y1: 125, x2: 46, y2: 14, class: "op-xp-axis" }));
    const xl = svg("text", { x: 260, y: 153, "text-anchor": "middle", class: "op-xp-axis-label" }); xl.textContent = spec.x;
    const yl = svg("text", { x: 17, y: 72, transform: "rotate(-90 17 72)", "text-anchor": "middle", class: "op-xp-axis-label" }); yl.textContent = spec.y;
    plot.append(xl, yl);
    (spec.shapes || []).forEach((shape, index) => {
      const points = (shape.points || []).map(([x, y]) => `${46 + x * 424},${125 - y * 111}`).join(" ");
      plot.append(svg("polyline", { points, fill: "none", class: `op-xp-curve op-xp-curve-${index % 3}` }));
    });
    fig.append(plot);
    const legend = el("div", "op-xp-legend");
    (spec.shapes || []).forEach((shape, index) => {
      const item = el("div", "op-xp-legend-item");
      item.append(el("i", `op-xp-swatch op-xp-curve-${index % 3}`), el("strong", "", shape.name), el("span", "", `→ ${shape.decision}`));
      legend.append(item);
    });
    fig.append(legend);
    return fig;
  }
  function render(node) {
    if (node.dataset.opXpReady === "1") return;
    const script = node.querySelector(".op-xp-spec");
    if (!script) return;
    let spec;
    try { spec = JSON.parse(script.textContent); } catch (_) { return; }
    if (!spec.vary || !Array.isArray(spec.fixed) || !Array.isArray(spec.measure)) return;
    const t = document.documentElement.lang.toLowerCase().startsWith("zh") ? copy.zh : copy.en;
    const output = el("div", "op-xp-rendered");
    output.append(design(spec, t));
    const peekScript = node.querySelector(".op-xp-peek");
    if (peekScript) {
      try {
        const strip = recordStrip(JSON.parse(peekScript.textContent), t);
        if (strip) output.append(strip);
      } catch (_) { /* A missing or malformed peek leaves the design visible. */ }
    }
    if (spec.sketch) output.append(sketch(spec.sketch, t));
    node.append(output);
    node.dataset.opXpReady = "1";
  }
  function flash(id) {
    const target = id && document.getElementById(id);
    if (!target) return;
    target.classList.remove("op-xmap-flash");
    void target.offsetWidth;
    target.classList.add("op-xmap-flash");
  }
  function mapInit() {
    document.querySelectorAll(".op-xmap").forEach(map => {
      if (map.dataset.opXmapReady === "1") return;
      map.addEventListener("click", event => {
        const link = event.target.closest("a[href^='#']");
        if (link) flash(decodeURIComponent(link.getAttribute("href").slice(1)));
      });
      map.dataset.opXmapReady = "1";
    });
  }
  function init() {
    if (document.documentElement.lang.toLowerCase().startsWith("zh")) {
      document.documentElement.style.setProperty("--op-header-tag", JSON.stringify(copy.zh.headerTag));
    }
    document.querySelectorAll(".op-xp").forEach(render);
    mapInit();
  }
  if (window.document$ && typeof window.document$.subscribe === "function") window.document$.subscribe(init);
  else if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
