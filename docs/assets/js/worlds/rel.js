(function () {
  "use strict";

  const palette = { parent: "var(--op-cyan)", colleague: "var(--op-amber)", neighbour: "var(--op-magenta)" };
  const symbols = { "↟": "parent", "↝": "colleague", "↔": "neighbour" };
  const tr = window.OpulseWorlds.tr;
  const relationLabel = name => ({parent: tr("parent", "父母"), colleague: tr("colleague", "同事"),
    neighbour: tr("neighbour", "邻居")})[name] || name;
  let graph = null;
  let template = null;  // the table drawn once; each derivation step shows a copy with its path
  let active = [];
  let history = [];
  let seenSteps = new Map();
  let previousExampleKey = null;

  function svg(name, attributes) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attributes || {}).forEach(([key, value]) => el.setAttribute(key, String(value)));
    return el;
  }

  function text(tag, content) {
    const el = document.createElement(tag);
    el.textContent = content;
    return el;
  }

  function valueLabel(value) {
    if (!value || value.t === "nan") return tr("No relation", "没有关系");
    if (value.t === "entity" || value.t === "str") return value.v;
    if (value.t === "int") return String(value.v);
    if (value.t === "bool") return value.v ? tr("True", "真") : tr("False", "假");
    return String(value.v);
  }

  function renderValue(el, value, ctx) {
    if (ctx && ctx.large && template) { renderStep(el, {value, focus: ""}, {steps: [], index: -1}); return; }
    el.replaceChildren();
    const chip = text("span", valueLabel(value));
    chip.style.cssText = "display:inline-flex;align-items:center;min-height:2rem;padding:.28rem .8rem;border:1px solid var(--op-line);border-radius:999px;background:var(--op-card);color:var(--op-fg);font-weight:650;letter-spacing:.01em";
    if (!value || value.t === "nan") chip.style.color = "var(--op-muted)";
    el.append(chip);
  }

  function highlight(source, target, relation) {
    if (!graph) return;
    graph.querySelectorAll("[data-edge]").forEach((edge) => {
      const hit = edge.dataset.source === source && edge.dataset.target === target && edge.dataset.relation === relation;
      if (hit && !active.includes(edge)) active.push(edge);
      edge.setAttribute("stroke-width", hit ? "5" : active.includes(edge) ? "3" : "1.7");
      edge.setAttribute("opacity", hit ? "1" : active.includes(edge) ? ".8" : ".5");
    });
    graph.querySelectorAll("[data-node]").forEach((node) => {
      const hit = node.dataset.node === source || node.dataset.node === target;
      node.setAttribute("stroke-width", hit ? "3.5" : "1.4");
    });
  }

  function edgeFromStep(step) {
    const relation = Object.keys(symbols).find((symbol) => step.focus.includes(symbol));
    const quoted = step.focus.match(/"([^"]+)"/);
    const source = quoted && quoted[1];
    const target = step.value && step.value.t === "entity" && step.value.v;
    return relation && source && target ? [source, target, symbols[relation]] : null;
  }

  function resetEdges() {
    active = [];
    graph.querySelectorAll("[data-edge]").forEach((edge) => {
      edge.setAttribute("stroke-width", "1.7");
      edge.setAttribute("opacity", ".5");
    });
  }

  function renderStep(el, step, ctx) {
    el.replaceChildren();
    const moving = step.previous && step.value && valueLabel(step.previous) !== valueLabel(step.value) &&
      !matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (template) {
      graph = template.cloneNode(true);
      graph.style.maxWidth = "min(100%, 21rem)";
      el.style.flexDirection = "column";
      el.append(graph);
    }
    // The lookups made so far, as a path: Bo -neighbour-> Ana -parent-> Cora.
    const done = (ctx && Array.isArray(ctx.steps) && typeof ctx.index === "number")
      ? ctx.steps.slice(0, ctx.index + 1).map(edgeFromStep).filter(Boolean) : [];
    const path = document.createElement("div");
    path.className = "op-rel-step-path";
    path.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;gap:.35rem;justify-content:center";
    const node = name => { const chip = text("span", name); chip.style.cssText = "padding:.25rem .7rem;border:1px solid var(--op-line);border-radius:999px;background:var(--op-card);font-weight:650"; return chip; };
    done.forEach(([source, target, relation], i) => {
      if (i === 0 || done[i - 1][1] !== source) path.append(node(source));
      const arrow = text("span", relationLabel(relation) + " →");
      arrow.style.cssText = "font-size:.82rem;font-weight:650;color:" + palette[relation];
      path.append(arrow, node(target));
    });
    if (done.length && step.value && valueLabel(step.value) !== done[done.length - 1][1]) {
      const arrow = text("span", "→");
      arrow.style.color = "var(--op-amber)";
      path.append(arrow, node(valueLabel(step.value)));
    }
    if (!done.length) renderValue(path, step.value);
    el.append(path);
    if (moving) {
      const chips = [...path.querySelectorAll("span")].filter(chip => !chip.textContent.endsWith(" →"));
      const last = chips[chips.length - 1];
      const from = chips[chips.length - 2];
      if (last) {
        last.style.borderColor = "var(--op-cyan)";
        last.style.color = "var(--op-cyan)";
        last.style.visibility = "hidden";
        requestAnimationFrame(() => {
          if (!last.isConnected) return;
          const target = last.getBoundingClientRect();
          const start = from?.getBoundingClientRect();
          last.style.visibility = "visible";
          last.animate([{opacity: 0, transform: start ? `translate(${start.left - target.left}px, ${start.top - target.top}px) scale(.85)` : "scale(.7)"},
            {opacity: 1, transform: "translate(0,0) scale(1)"}],
          {duration: 760, easing: "cubic-bezier(.22,1,.36,1)"});
        });
      }
    }
    if (!graph) return;
    const index = ctx && (ctx.stepIndex ?? ctx.index);
    const sequence = ctx && (ctx.steps || (ctx.example && ctx.example.steps));
    const exampleKey = ctx && ctx.example && `${ctx.example.operator}|${ctx.example.expression}`;
    if (exampleKey && exampleKey !== previousExampleKey) {
      seenSteps = new Map();
      previousExampleKey = exampleKey;
    }
    resetEdges();
    if (Array.isArray(sequence) && typeof index === "number") {
      history = sequence.slice(0, index + 1).map(edgeFromStep).filter(Boolean);
    } else {
      const edge = edgeFromStep(step);
      if (index === 0) seenSteps = new Map();
      if (typeof index === "number") {
        seenSteps.set(index, edge);
        history = [...seenSteps].filter(([position, value]) => position <= index && value)
          .sort(([left], [right]) => left - right).map(([, value]) => value);
      } else if (edge) {
        history.push(edge);
      }
    }
    history.forEach(([source, target, relation]) => highlight(source, target, relation));
    if (moving) {
      const edge = edgeFromStep(step);
      if (edge) {
        const line = [...graph.querySelectorAll("[data-edge]")].find(item =>
          item.dataset.source === edge[0] && item.dataset.target === edge[1] && item.dataset.relation === edge[2]);
        if (line) {
          const length = line.getTotalLength();
          line.animate([{strokeDasharray: `${length} ${length}`, strokeDashoffset: length, opacity: .15, strokeWidth: 2},
            {strokeDasharray: `${length} ${length}`, strokeDashoffset: 0, opacity: 1, strokeWidth: 5}],
          {duration: 760, easing: "cubic-bezier(.22,1,.36,1)"});
          const targetNode = [...graph.querySelectorAll("[data-node]")].find(item => item.dataset.node === edge[1]);
          targetNode?.querySelector("circle")?.animate([{stroke: "var(--op-amber)", strokeWidth: 4},
            {stroke: "var(--op-cyan)", strokeWidth: 3.5}], {duration: 760, easing: "ease-out"});
        }
      }
    }
  }

  function renderContext(el, data) {
    el.replaceChildren();
    const context = data.context || data;
    const entities = context.entities || [];
    const relations = context.relations || {};
    const disclosure = document.createElement("details");
    const summary = text("summary", data.edit ? tr(
      `Example edit: ${data.edit.source}'s ${data.edit.relation} changes from ${data.edit.old} to ${data.edit.new}`,
      `示例修改：${data.edit.source} 的${relationLabel(data.edit.relation)}由 ${data.edit.old} 改为 ${data.edit.new}`
    ) : tr("Relation table", "关系表"));
    disclosure.append(summary);
    const wrap = document.createElement("section");
    wrap.style.cssText = "padding:clamp(10px,2vw,20px);color:var(--op-fg);overflow:hidden";
    const title = text("strong", tr("Table edit", "关系表的一处修改示例"));
    title.style.cssText = "display:block;font-size:1rem;margin-bottom:.55rem";
    wrap.append(title);
    const legend = document.createElement("div");
    legend.style.cssText = "display:flex;flex-wrap:wrap;gap:.4rem .9rem;font-size:.8rem;color:var(--op-muted)";
    Object.entries(palette).forEach(([name, color]) => {
      const item = text("span", "● " + relationLabel(name));
      item.style.color = color;
      legend.append(item);
    });
    wrap.append(legend);
    const canvas = svg("svg", { viewBox: "0 0 420 420", role: "img", "aria-label": tr("Twelve people linked by coloured relations", "十二个实体及彩色关系连线") });
    canvas.style.cssText = "display:block;width:100%;max-width:22rem;margin:.45rem auto 0;height:auto";
    const positions = {};
    entities.forEach((name, index) => {
      const angle = Math.PI * 2 * index / entities.length - Math.PI / 2;
      positions[name] = [210 + 160 * Math.cos(angle), 210 + 160 * Math.sin(angle)];
    });
    Object.entries(relations).forEach(([relation, edges]) => {
      Object.entries(edges).forEach(([source, target]) => {
        const from = positions[source], to = positions[target];
        if (!from || !to) return;
        const line = svg("line", { x1: from[0], y1: from[1], x2: to[0], y2: to[1], stroke: palette[relation],
          "stroke-width": "1.7", opacity: ".5", "stroke-linecap": "round", "data-edge": "" });
        line.dataset.source = source;
        line.dataset.target = target;
        line.dataset.relation = relation;
        canvas.append(line);
      });
    });
    entities.forEach((name) => {
      const [x, y] = positions[name];
      const group = svg("g", { "data-node": name });
      const circle = svg("circle", { cx: x, cy: y, r: 25, fill: "var(--op-bg)", stroke: "var(--op-line)", "stroke-width": "1.4" });
      const label = svg("text", { x, y: y + 4.5, "text-anchor": "middle", fill: "var(--op-fg)",
        "font-size": "14", "font-family": "system-ui,sans-serif", "font-weight": "650" });
      label.textContent = name;
      group.append(circle, label);
      canvas.append(group);
    });
    if (data.edit) {
      const edit = document.createElement("div");
      edit.style.cssText = "border-top:1px solid var(--op-line);padding-top:.7rem;font-size:.84rem;color:var(--op-muted);line-height:1.5";
      const list = document.createElement("div");
      list.style.cssText = "display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.35rem;margin-top:.5rem";
      (data.edit.changes || [data.edit]).forEach((change) => {
        const item = text("span", `${change.operator}("${change.input.v}"): ${valueLabel(change.before)} → ${valueLabel(change.after)}`);
        item.style.cssText = "padding:.35rem .5rem;border:1px solid var(--op-line);border-radius:8px;background:var(--op-bg);color:var(--op-fg)";
        list.append(item);
      });
      edit.append(list);
      wrap.append(edit);
    }
    disclosure.append(wrap);
    el.append(disclosure);
    template = canvas;
    graph = null;
    active = [];
    history = [];
    seenSteps = new Map();
    previousExampleKey = null;
  }

  function selectExample(example, steps) {
    history = [];
    seenSteps = new Map();
    previousExampleKey = example ? `${example.expression}` : null;
  }

  window.OpulseWorlds.register("rel", { renderValue, renderStep, renderContext, selectExample });
}());
