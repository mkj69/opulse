(() => {
  "use strict";

  const styleId = "opulse-perm-style";
  const running = new WeakMap();
  if (!document.getElementById(styleId)) {
    const style = document.createElement("style");
    style.id = styleId;
    style.textContent = `
      .op-perm { display: grid; gap: .55rem; width: 100%; min-width: 0; color: var(--op-fg); }
      .op-perm-board { position: relative; width: 100%; height: 5.2rem; border: 1px solid var(--op-line);
        border-radius: .9rem; background: var(--op-bg); overflow: hidden; }
      .op-perm-board::before { content: ""; position: absolute; inset: .48rem;
        border: 1px dashed var(--op-line); border-radius: .55rem; pointer-events: none; }
      .op-perm-card { position: absolute; top: .52rem; bottom: .52rem;
        width: calc(var(--op-cell) - .38rem); margin-left: .19rem;
        display: grid; place-items: center; border: 1px solid var(--op-line);
        border-radius: .55rem; background: var(--op-card); box-shadow: 0 .18rem .38rem color-mix(in srgb, var(--op-fg) 12%, transparent);
        transition: left .58s cubic-bezier(.2,.8,.2,1); }
      .op-perm-card strong { display: block; font: 700 1.35rem Georgia,serif; line-height: 1;
        color: var(--op-cyan); text-align: center; }
      .op-perm-card small { display: block; margin-top: .1rem; color: var(--op-muted);
        font: 600 .8rem system-ui,sans-serif; letter-spacing: .08em; text-align: center; }
      .op-perm-mapping { display: flex; flex-wrap: wrap; gap: .28rem; color: var(--op-muted);
        font: 600 .8rem system-ui,sans-serif; }
      .op-perm-mapping span { border: 1px solid var(--op-line); border-radius: 999px;
        padding: .16rem .45rem; background: var(--op-card); }
      .op-perm-step { min-width: 0; overflow-wrap: anywhere; font: .84rem ui-monospace,monospace;
        color: var(--op-fg); }
      .op-perm-note { font: .82rem system-ui,sans-serif; color: var(--op-muted); }
      .op-perm.compact { width: min(13rem, 100%); }
      .op-perm.compact .op-perm-board { height: 3.6rem; }
      .op-perm.compact .op-perm-card strong { font-size: 1rem; }
      .op-perm.compact .op-perm-mapping { display: none; }
      .ow-example-visual .ow-in:has(> .op-perm.compact) { flex: 1 1 10rem; width: min(12rem, 100%); }
      .op-perm-card.selected { border: 2px solid var(--op-cyan); box-shadow: 0 0 0 2px var(--op-bg), 0 0 0 4px var(--op-cyan); }
      @media (max-width: 390px) { .op-perm-board { height: 4.5rem; }
        .op-perm-card strong { font-size: 1.08rem; } .op-perm-card small { font-size: .8rem; } }
      @media (prefers-reduced-motion: reduce) { .op-perm-card { transition: none; } }
    `;
    document.head.append(style);
  }

  function board(el, positions) {
    const n = positions.length;
    let root = el.querySelector(":scope > .op-perm");
    if (!root || root.dataset.count !== String(n)) {
      el.replaceChildren();
      root = document.createElement("div");
      root.className = "op-perm";
      root.dataset.count = String(n);
      const field = document.createElement("div");
      field.className = "op-perm-board";
      field.style.setProperty("--op-cell", `${100 / n}%`);
      field.setAttribute("role", "img");
      for (let card = 0; card < n; card++) {
        const tile = document.createElement("div");
        tile.className = "op-perm-card";
        tile.style.left = `${card * 100 / n}%`;
        const face = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = String.fromCharCode(65 + card);
        const caption = document.createElement("small");
        caption.textContent = String(card);
        face.append(title, caption);
        tile.append(face);
        field.append(tile);
      }
      root.append(field);
      const mapping = document.createElement("div");
      mapping.className = "op-perm-mapping";
      root.append(mapping);
      el.append(root);
    }
    const field = root.querySelector(".op-perm-board");
    const update = () => {
      Array.from(field.children).forEach((tile, card) => {
        tile.style.left = `${positions[card] * 100 / n}%`;
      });
      field.setAttribute("aria-label", positions.map((p, i) =>
        `Card ${String.fromCharCode(65 + i)} moves to position ${p}`).join("; "));
    };
    if (root.dataset.ready) update();
    else { root.dataset.ready = "1"; requestAnimationFrame(() => requestAnimationFrame(update)); }
    const mapping = root.querySelector(".op-perm-mapping");
    mapping.replaceChildren(...positions.map((p, i) => {
      const chip = document.createElement("span");
      chip.textContent = `${String.fromCharCode(65 + i)} → ${p}`;
      return chip;
    }));
    return root;
  }

  function renderValue(el, value, ctx) {
    if (value && value.t === "perm" && Array.isArray(value.v)) {
      const root = board(el, value.v);
      root.classList.toggle("compact", Boolean(ctx && ctx.compact));
      return;
    }
    if (ctx?.atom?.name === "perm_apply" && value?.t === "int") {
      const input = ctx.atom.example.inputs;
      const root = board(el, input[0].v);
      root.classList.toggle("compact", Boolean(ctx.compact));
      const card = input[1].v;
      root.querySelectorAll(".op-perm-card")[card]?.classList.add("selected");
      const note = document.createElement("span");
      note.className = "op-perm-note";
      note.textContent = window.OpulseWorlds.tr(
        `Card ${String.fromCharCode(65 + card)} → position ${value.v}`,
        `卡片 ${String.fromCharCode(65 + card)} → 位置 ${value.v}`);
      root.append(note);
      return;
    }
    el.replaceChildren();
    window.OpulseWorlds.fallbackValue(el, value);
  }

  function renderStep(el, step, ctx) {
    (running.get(el) || []).forEach(animation => animation.cancel());
    running.delete(el);
    const before = step.previous?.t === "perm" ? step.previous.v : null;
    const after = step.value?.t === "perm" ? step.value.v : null;
    if (!before || !after || before.length !== after.length) {
      renderValue(el, step.value, ctx);
      return;
    }
    const root = board(el, after);
    root.classList.toggle("compact", Boolean(ctx?.compact));
    const tiles = root.querySelectorAll(".op-perm-card");
    const animations = [];
    tiles.forEach((tile, card) => {
      tile.style.transition = "none";
      tile.style.left = `${after[card] * 100 / after.length}%`;
      if (before[card] === after[card] || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      const distance = (before[card] - after[card]) * root.querySelector(".op-perm-board").clientWidth / after.length;
      animations.push(tile.animate([
        {transform: `translateX(${distance}px) translateY(0)`, borderColor: "var(--op-amber)", zIndex: 2},
        {transform: `translateX(${distance * .46}px) translateY(-9px)`, borderColor: "var(--op-amber)", zIndex: 2, offset: .5},
        {transform: "translateX(0) translateY(0)", borderColor: "var(--op-line)", zIndex: 2}
      ], {duration: 780, easing: "cubic-bezier(.2,.8,.2,1)"}));
    });
    running.set(el, animations);
  }

  window.OpulseWorlds.register("perm", {renderValue, renderStep});
})();
