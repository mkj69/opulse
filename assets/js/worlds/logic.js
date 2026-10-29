(function () {
  "use strict";

  let worldData = null;
  const NS = "http://www.w3.org/2000/svg";

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function svg(tag, attributes) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    return node;
  }

  function textOf(value) {
    if (!value || value.t === "nan") return "NaN";
    if (value.t === "bool") return value.v ? "TRUE" : "FALSE";
    return String(value.v);
  }

  function sameValue(left, right) {
    return left && right && left.t === right.t && left.v === right.v;
  }

  function renderValue(el, value) {
    el.replaceChildren();
    const chip = element("span", "op-logic-value " + (value.t === "bool" ?
      (value.v ? "is-true" : "is-false") : "is-number"), textOf(value));
    el.append(chip);
  }

  function locate(step, ctx) {
    const data = (ctx && (ctx.data || ctx.world)) || worldData;
    if (!data || !data.operators) return {};
    const example = (ctx && ctx.example) || null;
    const name = example && example.operator || (ctx && ctx.operator &&
      (ctx.operator.name || ctx.operator)) || (step && step.gate);
    return { example, operator: data.operators.find(item => item.name === name) };
  }

  function table(operator, example) {
    const section = element("section", "op-logic-panel op-logic-table-panel");
    section.append(element("h4", "", "Truth table"));
    const scroller = element("div", "op-logic-table-scroll");
    const tableNode = element("table", "op-logic-table");
    const head = element("thead");
    const heading = element("tr");
    operator.params.forEach(param => heading.append(element("th", "", param.name)));
    heading.append(element("th", "", operator.name));
    head.append(heading);
    tableNode.append(head);
    const body = element("tbody");
    operator.truth_table.forEach(row => {
      const selected = example && row.inputs.every((value, index) => sameValue(value, example.inputs[index]));
      const tr = element("tr", selected ? "is-current" : "");
      if (selected) tr.setAttribute("aria-current", "true");
      [...row.inputs, row.output].forEach(value => {
        const cell = element("td");
        renderValue(cell, value);
        tr.append(cell);
      });
      body.append(tr);
    });
    tableNode.append(body);
    scroller.append(tableNode);
    section.append(scroller);
    return section;
  }

  function circuit(operator, step) {
    const section = element("section", "op-logic-panel op-logic-circuit-panel");
    section.append(element("h4", "", "Circuit"));
    const graph = operator.circuit;
    const nodes = graph.nodes;
    const byId = new Map(nodes.map(node => [node.id, node]));
    const depth = new Map();
    function level(id) {
      if (depth.has(id)) return depth.get(id);
      const node = byId.get(id);
      const result = node.inputs.length ? 1 + Math.max(...node.inputs.map(level)) : 0;
      depth.set(id, result);
      return result;
    }
    nodes.forEach(node => level(node.id));
    const columns = new Map();
    nodes.forEach(node => {
      const d = depth.get(node.id);
      if (!columns.has(d)) columns.set(d, []);
      columns.get(d).push(node);
    });
    const width = Math.max(360, (Math.max(...columns.keys()) + 1) * 95 + 40);
    const height = Math.max(210, Math.max(...[...columns.values()].map(col => col.length)) * 52 + 42);
    const coords = new Map();
    columns.forEach((col, d) => col.forEach((node, index) => {
      coords.set(node.id, { x: 48 + d * 95, y: (index + 1) * height / (col.length + 1) });
    }));
    const drawing = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img",
      "aria-label": `Logic circuit for ${operator.name}`, class: "op-logic-svg" });
    const selected = step && step.gate === operator.name && graph.branches[step.branch];
    const activeNodes = new Set(selected ? [graph.output, selected.root, selected.guard] : []);
    nodes.forEach(node => node.inputs.forEach(input => {
      const from = coords.get(input);
      const to = coords.get(node.id);
      if (!from || !to) return;
      const line = svg("path", { d: `M ${from.x + 24} ${from.y} C ${from.x + 54} ${from.y}, ${to.x - 54} ${to.y}, ${to.x - 24} ${to.y}`,
        class: "op-logic-wire" });
      if (step && (node.label === step.gate || byId.get(input).label === step.gate ||
          activeNodes.has(node.id) && activeNodes.has(input))) {
        line.classList.add("is-active");
      }
      drawing.append(line);
    }));
    nodes.forEach(node => {
      const { x, y } = coords.get(node.id);
      const active = step && (node.label === step.gate || activeNodes.has(node.id));
      const group = svg("g", { class: `op-logic-gate kind-${node.kind}` +
        (active ? " is-active" : "") +
        (active && step.signal && step.signal.t === "bool" && !step.signal.v ? " is-low" : "") });
      group.append(svg("rect", { x: x - 24, y: y - 19, width: 48, height: 38, rx: 11 }));
      const label = svg("text", { x, y: y + 5, "text-anchor": "middle" });
      label.textContent = node.label;
      group.append(label);
      drawing.append(group);
    });
    const wrap = element("div", "op-logic-circuit-scroll");
    wrap.append(drawing);
    section.append(wrap);
    const signal = step && step.signal ? ` • ${textOf(step.signal)}` : "";
    section.append(element("p", "op-logic-signal", step ? `Active: ${step.gate}${signal}` : "Select a step to see its signal."));
    return section;
  }

  function renderStep(el, step, ctx) {
    el.replaceChildren();
    const { operator, example } = locate(step, ctx);
    if (!operator) return;
    const before = step.previous || example?.inputs?.[0] || step.value;
    const after = step.value;
    const strip = element("div", "op-logic-step");
    strip.setAttribute("role", "img");
    strip.setAttribute("aria-label", `${textOf(before)} → ${textOf(after)}`);
    function lamp(value, className) {
      const cell = element("span", `op-logic-step-cell ${className}`);
      const light = element("span", "op-logic-step-light" + (value && value.t === "bool" && value.v ? " is-lit" : ""));
      cell.append(light, element("strong", "", textOf(value)));
      return cell;
    }
    const from = lamp(before, "op-logic-step-from");
    const to = lamp(after, "op-logic-step-to");
    strip.append(from, element("span", "op-logic-step-arrow", "→"), to);
    el.append(strip);
    const details = element("details", "op-logic-step-details");
    details.append(element("summary", "", window.OpulseWorlds.tr("Truth table & circuit", "真值表与电路")));
    const layout = element("div", "op-logic-layout");
    layout.append(table(operator, example), circuit(operator, step));
    details.append(layout);
    el.append(details);
    if (before && after && (before.t !== after.t || before.v !== after.v) &&
        !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      requestAnimationFrame(() => {
        if (!strip.isConnected) return;
        const first = from.getBoundingClientRect();
        const last = to.getBoundingClientRect();
        to.animate([{opacity: 0, transform: `translateX(${first.left - last.left}px) scale(.8)`},
          {opacity: 1, transform: "translateX(0) scale(1)"}],
        {duration: 760, easing: "cubic-bezier(.22,1,.36,1)"});
        from.animate([{opacity: 1}, {opacity: .55}], {duration: 760, fill: "forwards"});
        strip.querySelectorAll(".op-logic-step-light.is-lit").forEach(light =>
          light.animate([{boxShadow: "0 0 0 var(--op-cyan)"}, {boxShadow: "0 0 18px var(--op-cyan)"}, {boxShadow: "0 0 8px var(--op-cyan)"}],
            {duration: 760, easing: "ease-out"}));
      });
    }
  }

  function renderContext(el, data) {
    worldData = data;
    el.replaceChildren();
    const legend = element("div", "op-logic-legend");
    legend.append(element("strong", "", "Atomic gates"));
    data.atoms.forEach(atom => {
      const item = element("span", "op-logic-atom", atom.symbol);
      item.title = atom.rule;
      legend.append(item);
    });
    el.append(legend);
  }

  const style = element("style");
  style.textContent = `
    .op-logic-step{display:flex;align-items:center;justify-content:center;gap:clamp(.25rem,1.5vw,.7rem);width:100%;min-width:0;min-height:8.5rem;padding:.5rem .1rem;font-variant-numeric:tabular-nums}
    .op-logic-step-cell{display:flex;align-items:center;justify-content:center;gap:.35rem;min-width:0;border:1px solid var(--op-line);border-radius:12px;padding:.5rem clamp(.25rem,1vw,.65rem);background:var(--op-bg);color:var(--op-fg)}
    .op-logic-step-cell strong{font-size:clamp(.8rem,1.6vw,1.05rem);overflow-wrap:anywhere}
    .op-logic-step-to{border-color:var(--op-cyan);color:var(--op-cyan)}
    .op-logic-step-from{border-color:var(--op-amber)}
    .op-logic-step-arrow{font-size:1.4rem;color:var(--op-cyan);flex:none}
    .op-logic-step-light{width:1.8rem;height:1.8rem;flex:none;border-radius:50%;background:var(--op-card);border:2px solid var(--op-muted);box-shadow:inset 0 2px 4px #0003}
    .op-logic-step-light.is-lit{background:var(--op-cyan);border-color:var(--op-cyan);box-shadow:0 0 8px var(--op-cyan)}
    .ow-step-visual:has(.op-logic-step){display:block;min-width:0;overflow:hidden}
    .op-logic-step-details{width:100%;border-top:1px solid var(--op-line);color:var(--op-fg);font-size:.85rem}
    .op-logic-step-details summary{cursor:pointer;padding:.45rem .25rem;color:var(--op-muted);font-weight:650}
    .op-logic-step-details summary:hover{color:var(--op-cyan)}
    .ow-step-visual .op-logic-layout{margin:.25rem 0;min-width:0;width:100%}
    .ow-step-visual .op-logic-svg{min-width:0}
    .op-logic-layout{display:grid;grid-template-columns:minmax(0,1fr);gap:.7rem;margin:.5rem 0}
    .op-logic-panel{min-width:0;padding:1rem;border:1px solid var(--op-line);border-radius:16px;background:var(--op-card);color:var(--op-fg)}
    .op-logic-panel h4{margin:0 0 .75rem;font-size:.9rem;letter-spacing:.025em}
    .op-logic-table-scroll{max-height:340px;overflow:auto}
    .op-logic-table{width:100%;border-collapse:collapse;text-align:center;font-variant-numeric:tabular-nums}
    .op-logic-table th{position:sticky;top:0;background:var(--op-card);color:var(--op-muted);font-size:.8rem;padding:.45rem}
    .op-logic-table td{padding:.32rem .2rem;border-top:1px solid var(--op-line)}
    .op-logic-table tr.is-current{background:var(--op-bg);outline:2px solid var(--op-amber);outline-offset:-2px}
    .op-logic-value{display:inline-flex;align-items:center;justify-content:center;min-width:3.7rem;padding:.18rem .4rem;border:1px solid var(--op-line);border-radius:99px;font-size:.8rem;font-weight:700;letter-spacing:.06em;color:var(--op-muted)}
    .op-logic-value.is-true{color:var(--op-cyan);border-color:var(--op-cyan)}
    .op-logic-value.is-number{min-width:2rem;color:var(--op-fg)}
    .op-logic-circuit-scroll{overflow:auto}
    .op-logic-svg{display:block;width:100%;min-width:360px;max-height:350px}
    .op-logic-wire{fill:none;stroke:var(--op-line);stroke-width:2.2;transition:stroke .2s,stroke-width .2s}
    .op-logic-wire.is-active{stroke:var(--op-cyan);stroke-width:3.5}
    .op-logic-gate rect{fill:var(--op-bg);stroke:var(--op-line);stroke-width:2;transition:stroke .2s,fill .2s}
    .op-logic-gate text{fill:var(--op-fg);font-size:15px;font-weight:700}
    .op-logic-gate.kind-choice rect,.op-logic-gate.kind-guard rect{stroke:var(--op-amber)}
    .op-logic-gate.kind-feedback rect{stroke:var(--op-magenta)}
    .op-logic-gate.is-active rect{stroke:var(--op-cyan);stroke-width:3.5}
    .op-logic-gate.is-low rect{stroke:var(--op-amber)}
    .op-logic-gate.kind-feedback.is-active rect{stroke:var(--op-magenta)}
    .op-logic-signal{margin:.5rem 0 0;color:var(--op-muted);font-size:.82rem}
    .op-logic-legend{display:flex;align-items:center;flex-wrap:wrap;gap:.45rem;margin:.5rem 0;color:var(--op-muted);font-size:.8rem}
    .op-logic-legend strong{margin-right:.3rem;color:var(--op-fg)}
    .op-logic-atom{display:inline-grid;place-items:center;width:1.8rem;height:1.8rem;border:1px solid var(--op-line);border-radius:.5rem;background:var(--op-card);color:var(--op-cyan);font-weight:700}
    @media(max-width:700px){.op-logic-layout{grid-template-columns:minmax(0,1fr)}.op-logic-table-scroll{max-height:220px}.op-logic-panel{padding:.8rem}}
    @media(prefers-reduced-motion:reduce){.op-logic-wire,.op-logic-gate rect{transition:none}}
  `;
  document.head.append(style);
  window.OpulseWorlds.register("logic", { renderValue, renderStep, renderContext });
}());
