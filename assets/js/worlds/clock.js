(function () {
  "use strict";
  const worlds = window.OpulseWorlds;
  const running = new WeakMap();
  function clock(el, value, ctx, previous, step) {
    const old = running.get(el);
    if (old !== undefined) cancelAnimationFrame(old);
    running.delete(el);
    if (!value || value.t !== "int") { worlds.fallbackValue(el, value); return; }
    const modulus = (ctx && ctx.modulus) || 12;
    const source = previous || (ctx && ctx.mini && ctx.example && ctx.example.inputs[0]);
    const start = source && source.t === "int" ? source.v : value.v;
    const dialValue = number => {
      const residue = ((number % modulus) + modulus) % modulus;
      return number === residue ? String(number) : number + " ≡ " + residue;
    };
    const dial = document.createElement("div");
    dial.className = "ow-clock" + (ctx && ctx.compact ? " compact" : "");
    dial.setAttribute("role", "img");
    dial.setAttribute("aria-label", (start === value.v ? "" : start + " → ") + value.v + worlds.tr(" on a dial of ", "，表盘共 ") + modulus + worlds.tr("", " 格"));
    const hand = document.createElement("span"); hand.className = "ow-clock-hand";
    hand.style.transition = "none";
    hand.style.transform = "rotate(" + (step ? start : value.v) / modulus * 360 + "deg)";
    if ((step || ctx && ctx.mini) && start !== value.v) {
      const ghost = document.createElement("span"); ghost.className = "ow-clock-hand";
      ghost.style.cssText = "background:var(--op-amber);opacity:.8;transition:none;transform:rotate(" + start / modulus * 360 + "deg)";
      dial.append(ghost);
    }
    dial.append(hand);
    for (let n = 0; n < modulus; n += modulus % 3 === 0 ? modulus / 4 : 1) {
      const angle = n / modulus * 2 * Math.PI;
      const label = document.createElement("span"); label.className = "ow-clock-label";
      label.textContent = Math.round(n);
      label.style.left = (50 + 40 * Math.sin(angle)) + "%";
      label.style.top = (50 - 40 * Math.cos(angle)) + "%";
      dial.append(label);
    }
    const number = document.createElement("span"); number.className = "ow-clock-value";
    number.textContent = dialValue(value.v);
    number.style.cssText = "white-space:nowrap;font-size:.88rem;top:64%";
    dial.append(number);
    const wrapper = document.createElement("div");
    wrapper.style.cssText = "display:flex;flex-direction:column;align-items:center;gap:.5rem;min-width:0";
    wrapper.append(dial);
    if (step || ctx && ctx.mini && start !== value.v) {
      const caption = document.createElement("span");
      caption.style.cssText = "font:650 .78rem var(--op-mono);color:var(--op-cyan);text-align:center;overflow-wrap:anywhere";
      caption.textContent = (start === value.v ? "" : start + " → " + value.v + "  ") +
        (step ? worlds.tr("mod ", "模 ") + modulus : "");
      wrapper.append(caption);
    }
    el.append(wrapper);
    if (!step || start === value.v || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) {
      hand.style.transform = "rotate(" + (value.v / modulus * 360) + "deg)";
      return;
    }
    let difference = ((value.v - start) % modulus + modulus) % modulus;
    if (difference > modulus / 2) difference -= modulus;
    const origin = start / modulus * 360;
    const duration = 750;
    const move = (time, began) => {
      if (!wrapper.isConnected) { running.delete(el); return; }
      const progress = Math.min(1, (time - began) / duration);
      const eased = progress * progress * (3 - 2 * progress);
      hand.style.transform = "rotate(" + (origin + difference / modulus * 360 * eased) + "deg)";
      number.textContent = dialValue(progress < .6 ? start : value.v);
      if (progress < 1) running.set(el, requestAnimationFrame(next => move(next, began)));
      else running.delete(el);
    };
    number.textContent = dialValue(start);
    running.set(el, requestAnimationFrame(time => move(time, time)));
  }
  worlds.register("clock", {
    renderValue: clock,
    renderStep(el, step, ctx) {
      const changed = !ctx.steps || !ctx.steps[ctx.index] || ctx.steps[ctx.index].value;
      clock(el, step.value, ctx, changed ? step.previous : null, step);
    },
    renderContext(el, data) {
      const note = document.createElement("p");
      note.className = "ow-chip";
      note.textContent = worlds.tr("Atom results are taken modulo ", "每个原子结果都取模 ") + (data.modulus || 12);
      el.append(note);
    }
  });
})();
