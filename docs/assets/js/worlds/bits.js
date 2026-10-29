(function () {
  "use strict";
  const worlds = window.OpulseWorlds;
  const running = new WeakMap();
  function lamps(el, value, ctx, previous = null, step = null) {
    const old = running.get(el);
    if (old !== undefined) cancelAnimationFrame(old);
    running.delete(el);
    if (!value || value.t !== "int" || value.v < 0) { worlds.fallbackValue(el, value); return; }
    if (previous === null && ctx && ctx.mini && ctx.example?.inputs[0]?.t === "int") previous = ctx.example.inputs[0].v;
    if (ctx && ctx.mini) el.style.width = "100%";
    const bits = document.createElement("div"); bits.className = "ow-bits";
    bits.setAttribute("role", "img"); bits.setAttribute("aria-label", (previous !== null ? previous + " → " : "") + value.v + worlds.tr(" in binary", " 的二进制"));
    bits.style.cssText = "width:100%;max-width:100%;gap:" + (ctx && ctx.mini ? ".18rem" : ".32rem");
    const width = Math.max(8, Math.min(32, Math.floor(Math.log2(Math.max(1, value.v, previous || 0))) + 1));
    const changed = [];
    for (let bit = width - 1; bit >= 0; bit--) {
      const lamp = document.createElement("span");
      const on = Math.floor(value.v / 2 ** bit) % 2 === 1;
      const before = previous === null ? on : Math.floor(previous / 2 ** bit) % 2 === 1;
      lamp.className = "ow-lamp" + (before ? " on" : "") + (before !== on ? " changed" : "");
      lamp.style.cssText = "width:" + (ctx && ctx.mini ? "1rem;height:1rem" : "1.5rem;height:1.5rem") + ";flex:none;display:inline-flex;align-items:center;justify-content:center;font:700 .8rem var(--op-mono);color:" + (before ? "var(--op-bg)" : "var(--op-fg)") + ";transition:none";
      lamp.textContent = before ? "1" : "0";
      lamp.title = worlds.tr("Bit ", "位 ") + bit + (on ? worlds.tr(" on", " 开") : worlds.tr(" off", " 关"));
      if (before !== on) changed.push({lamp, on});
      bits.append(lamp);
    }
    const number = document.createElement("span"); number.className = "ow-bit-value";
    number.textContent = "= " + (step && previous !== null ? previous : value.v);
    number.style.cssText = "white-space:nowrap;color:var(--op-cyan)";
    bits.append(number);
    el.append(bits);
    if (!step || previous === null || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) {
      changed.forEach(({lamp, on}) => { lamp.classList.toggle("on", on); lamp.style.color = on ? "var(--op-bg)" : "var(--op-fg)"; lamp.textContent = on ? "1" : "0"; });
      number.textContent = "= " + value.v;
      if (ctx && ctx.mini && previous !== null && previous !== value.v) {
        const caption = document.createElement("span");
        caption.textContent = previous + " → " + value.v;
        caption.style.cssText = "width:100%;text-align:center;font:650 .78rem var(--op-mono);color:var(--op-cyan);white-space:nowrap";
        bits.append(caption);
      }
      return;
    }
    const move = (time, began) => {
      if (!bits.isConnected) { running.delete(el); return; }
      const progress = Math.min(1, (time - began) / 750);
      changed.forEach(({lamp, on}, index) => {
        const phase = Math.max(0, Math.min(1, (progress - index * .3 / Math.max(1, changed.length - 1)) / .7));
        lamp.style.transform = "scaleX(" + Math.max(.05, Math.abs(1 - 2 * phase)) + ")";
        lamp.style.boxShadow = phase > 0 && phase < 1 ? "0 0 0 3px var(--op-amber)" : "";
        if (phase >= .5) { lamp.classList.toggle("on", on); lamp.style.color = on ? "var(--op-bg)" : "var(--op-fg)"; lamp.textContent = on ? "1" : "0"; }
      });
      if (progress >= .6) number.textContent = "= " + value.v;
      if (progress < 1) running.set(el, requestAnimationFrame(next => move(next, began)));
      else { changed.forEach(({lamp}) => { lamp.style.transform = ""; lamp.style.boxShadow = ""; }); running.delete(el); }
    };
    running.set(el, requestAnimationFrame(time => move(time, time)));
  }
  worlds.register("bits", {renderValue: lamps, renderStep(el, step, ctx) {
    const changed = !ctx.steps || !ctx.steps[ctx.index] || ctx.steps[ctx.index].value;
    lamps(el, step.value, ctx, changed && step.previous?.t === "int" ? step.previous.v : null, step);
  }});
})();
