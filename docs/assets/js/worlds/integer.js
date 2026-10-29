(function () {
  "use strict";
  const worlds = window.OpulseWorlds;
  const NS = "http://www.w3.org/2000/svg";
  const running = new WeakMap();
  const reduced = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function svg(tag, attributes, text) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function interval(start, end, floor, divisions) {
    const distance = Math.max(1, Math.abs(end - start));
    const padding = Math.max(2, distance * .16);
    const min = Math.max(floor ?? -Infinity, Math.min(start, end) - padding);
    const max = Math.max(start, end) + padding;
    const raw = (max - min) / divisions;
    const power = 10 ** Math.floor(Math.log10(raw));
    const tick = Math.max(1, [1, 2, 5, 10].find(unit => unit * power >= raw) * power);
    let low = Math.floor(min / tick) * tick;
    if (floor !== undefined) low = Math.max(floor, low);
    const high = Math.max(low + tick, Math.ceil(max / tick) * tick);
    return {low, high, tick};
  }
  function operation(step) {
    if (step.kind === "expand") return worlds.tr("Unfold ", "展开 ") + (step.gate || "");
    if (step.gate === "@") return worlds.tr("reverse digits", "反转数字");
    const product = step.focus && step.focus.match(/\*\s*(\(?-?\d+\)?)/);
    if (product) return "× " + product[1];
    return step.focus || step.gate || worlds.tr("Compute", "计算");
  }
  function numberLine(el, value, ctx, previous, floor, step) {
    const old = running.get(el);
    if (old !== undefined) cancelAnimationFrame(old);
    running.delete(el);
    if (!value || value.t !== "int" || !Number.isFinite(value.v)) { worlds.fallbackValue(el, value); return; }
    const target = value.v;
    const source = previous || (ctx && ctx.mini && ctx.example && ctx.example.inputs[0]);
    const start = source && source.t === "int" && Number.isFinite(source.v) ? source.v : target;
    const compact = ctx && ctx.mini;
    if (compact) el.style.width = "100%";
    const available = Math.max(compact ? 280 : 140, el.clientWidth - 28);
    const {low, high, tick} = interval(start, target, floor, available < 310 ? 2 : 4);
    const left = 7, right = 93;
    const x = number => left + (number - low) / (high - low) * (right - left);
    const box = document.createElement("div");
    box.className = "ow-numberline" + (compact ? " mini" : "");
    box.style.cssText = "width:100%;max-width:none;box-sizing:border-box;min-width:0;gap:.2rem;justify-content:center";
    if (compact) box.style.minHeight = "0";
    const heading = document.createElement("div");
    heading.style.cssText = "min-height:1.35rem;text-align:center;font:700 .85rem var(--op-mono);color:var(--op-amber);overflow-wrap:anywhere;line-height:1.4";
    if (step) heading.textContent = operation(step);
    else if (start !== target) heading.textContent = worlds.tr("Input → output", "输入 → 输出");
    if (heading.textContent) box.append(heading);
    const plot = document.createElement("div");
    plot.style.cssText = "position:relative;width:100%;height:" + (compact ? "5.8rem" : "8.2rem") + ";min-width:0;flex:none";
    const drawing = svg("svg", {viewBox: "0 0 100 100", preserveAspectRatio: "none", role: "img",
      "aria-label": (start === target ? "" : start + " → ") + target});
    drawing.style.cssText = "position:absolute;inset:0;width:100%;height:100%;overflow:visible";
    drawing.append(svg("line", {x1: left, x2: right, y1: 69, y2: 69, stroke: "var(--op-line)", "stroke-width": 2, "vector-effect": "non-scaling-stroke"}));
    const first = Math.ceil(low / tick) * tick;
    let lastLabel = -Infinity;
    for (let index = 0; index < 20; index++) {
      const number = first + index * tick;
      if (number > high + tick / 100) break;
      const position = x(number);
      drawing.append(svg("line", {x1: position, x2: position, y1: 65, y2: 73,
        stroke: "var(--op-muted)", "stroke-width": number === 0 ? 2 : 1, "vector-effect": "non-scaling-stroke"}));
      const tickText = String(Number(number.toPrecision(10)));
      const halfLabel = tickText.length * 4;
      if (position / 100 * available < halfLabel || (100 - position) / 100 * available < halfLabel ||
          (position - lastLabel) / 100 * available < (compact ? 65 : 72)) continue;
      const tickLabel = document.createElement("span");
      tickLabel.textContent = tickText;
      tickLabel.style.cssText = "position:absolute;top:77%;left:" + position + "%;transform:translateX(-50%);font:500 13px var(--op-mono);white-space:nowrap;color:var(--op-muted)";
      plot.append(tickLabel);
      lastLabel = position;
    }
    if (start !== target) {
      const midpoint = (x(start) + x(target)) / 2;
      drawing.append(svg("path", {d: `M ${x(start)} 68 Q ${midpoint} 0 ${x(target)} 68`,
        fill: "none", stroke: "var(--op-amber)", "stroke-width": 2, "stroke-dasharray": "4 3", "vector-effect": "non-scaling-stroke"}));
    }
    const origin = document.createElement("span");
    origin.style.cssText = "position:absolute;top:69%;left:" + x(start) + "%;transform:translate(-50%,-50%);width:12px;height:12px;border:2px solid var(--op-amber);border-radius:50%;background:var(--op-card);box-sizing:border-box";
    if (start !== target) plot.append(origin);
    const dot = document.createElement("span");
    dot.style.cssText = "position:absolute;width:" + (compact ? 14 : 18) + "px;height:" + (compact ? 14 : 18) + "px;left:" + x(target) + "%;top:69%;transform:translate(-50%,-50%);border:2px solid var(--op-bg);border-radius:50%;background:var(--op-cyan);box-shadow:0 0 0 2px var(--op-cyan)";
    const label = document.createElement("span");
    label.style.cssText = "position:absolute;top:42%;transform:translateX(-50%);font:750 " + (compact ? 14 : 19) + "px var(--op-mono);color:var(--op-cyan);white-space:nowrap";
    const labelAt = position => { label.style.left = Math.max(12, Math.min(88, position)) + "%"; };
    labelAt(x(target)); label.textContent = target;
    plot.prepend(drawing); plot.append(dot, label); box.append(plot);
    let caption = null;
    if (start !== target) {
      caption = document.createElement("span");
      caption.textContent = start + " → " + target;
      caption.style.cssText = "font:700 .88rem var(--op-mono);color:var(--op-cyan);white-space:nowrap";
      box.append(caption);
    }
    el.append(box);
    if (!step || start === target || reduced()) return;
    if (caption) caption.style.opacity = "0";
    const move = (time, began) => {
      if (!box.isConnected) { running.delete(el); return; }
      const progress = Math.min(1, (time - began) / 750);
      const ease = progress * progress * (3 - 2 * progress);
      dot.style.left = x(start + (target - start) * ease) + "%";
      dot.style.top = (69 - 34 * Math.sin(Math.PI * ease)) + "%";
      labelAt(x(start + (target - start) * ease));
      label.style.top = (42 - 26 * Math.sin(Math.PI * ease)) + "%";
      label.textContent = progress < .55 ? start : target;
      if (caption) caption.style.opacity = String(Math.min(1, Math.max(0, (progress - .52) / .34)));
      if (progress < 1) running.set(el, requestAnimationFrame(next => move(next, began)));
      else running.delete(el);
    };
    dot.style.left = x(start) + "%"; labelAt(x(start)); label.textContent = start;
    running.set(el, requestAnimationFrame(time => move(time, time)));
  }
  worlds.numberLine = numberLine;
  worlds.register("integer", {
    renderValue(el, value, ctx) { numberLine(el, value, ctx); },
    renderStep(el, step, ctx) {
      const changed = !ctx.steps || !ctx.steps[ctx.index] || ctx.steps[ctx.index].value;
      numberLine(el, step.value, ctx, changed ? step.previous : null, undefined, step);
    }
  });
})();
