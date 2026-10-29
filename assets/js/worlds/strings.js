(function () {
  "use strict";
  const worlds = window.OpulseWorlds;
  const style = document.createElement("style");
  style.textContent = `
    .op-string-stage{position:relative;display:grid;place-items:center;width:100%;max-width:100%;min-width:0;padding:1rem .25rem}
    .op-string-stage .ow-tiles{grid-area:1/1;width:100%;max-width:100%;min-width:0;flex-wrap:nowrap;gap:.35rem;line-height:1.4}
    .op-string-stage .op-string-old{pointer-events:none;z-index:1}
    .op-string-stage .op-string-new{z-index:2}
    .op-string-stage .ow-tile{box-sizing:border-box;flex:0 0 var(--op-string-size);min-width:0;min-height:2.25rem;padding:0;font-size:clamp(.65rem,2vw,1rem);border-radius:8px;box-shadow:0 2px 6px #0001}
    .op-string-stage .op-string-new .ow-tile{border-color:var(--op-cyan);background:var(--op-bg)}
    .op-string-stage .op-string-old .ow-tile{border-color:var(--op-amber)}
    .op-string-stage .op-string-empty{color:var(--op-muted);font-style:italic}
    .op-string-stage .op-string-note{position:absolute;bottom:.1rem;left:0;right:0;text-align:center;color:var(--op-muted);font-size:.78rem;font-weight:650}
    .op-string-stage:has(.op-string-note){padding-bottom:1.8rem}
    @media(prefers-reduced-motion:reduce){.op-string-stage .ow-tile{animation:none!important}}
  `;
  document.head.append(style);

  function tiles(el, value) {
    if (!value || value.t !== "str") { worlds.fallbackValue(el, value); return; }
    const row = document.createElement("div"); row.className = "ow-tiles";
    if (!value.v.length) { row.classList.add("op-string-empty"); row.textContent = worlds.tr("empty string", "空字符串"); }
    [...value.v].forEach(char => { const tile = document.createElement("span"); tile.className = "ow-tile";
      tile.textContent = char === " " ? "␠" : char; row.append(tile); });
    el.append(row);
    return row;
  }

  function stageFor(step, ctx) {
    const stage = document.createElement("div"); stage.className = "op-string-stage";
    const values = [ctx?.example?.inputs?.[0], ...(ctx?.steps || []).map(item => item.value), step.previous, step.value];
    const count = Math.max(1, ...values.filter(value => value?.t === "str").map(value => [...value.v].length));
    stage.style.setProperty("--op-string-size", `min(2.5rem, calc((100% - ${(count - 1) * .35}rem) / ${count}))`);
    return stage;
  }

  function renderStep(el, step, ctx) {
    const before = step.previous;
    const after = step.value || {t: "str", v: ""};
    if (after.t !== "str" && before?.t === "str" && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const stage = stageFor(step, ctx);
      const oldRow = tiles(stage, before);
      oldRow.classList.add("op-string-old");
      const result = document.createElement("div");
      result.style.cssText = "grid-area:1/1;z-index:2;color:var(--op-cyan);font-size:1.15rem;font-weight:700";
      worlds.fallbackValue(result, after);
      result.style.visibility = "hidden";
      stage.append(result); el.append(stage);
      requestAnimationFrame(() => {
        if (!stage.isConnected) return;
        result.style.visibility = "visible";
        oldRow.animate([{opacity: 1, transform: "scale(1)"}, {opacity: 0, transform: "scale(.7)"}], {duration: 520, fill: "forwards", easing: "ease-in"});
        result.animate([{opacity: 0, transform: "scale(.7)"}, {opacity: 1, transform: "scale(1)"}], {duration: 760, easing: "cubic-bezier(.22,1,.36,1)"});
        setTimeout(() => { if (stage.isConnected) oldRow.remove(); }, 760);
      });
      return;
    }
    if (after.t !== "str" || !before || before.t !== "str" ||
        matchMedia("(prefers-reduced-motion: reduce)").matches || before.v === after.v) {
      if (after.t !== "str") { tiles(el, after); return; }
      const stage = stageFor(step, ctx);
      tiles(stage, after);
      if (before?.t === "str" && before.v === after.v) {
        const note = document.createElement("span"); note.className = "op-string-note";
        note.textContent = worlds.tr("No change", "无变化"); stage.append(note);
      }
      el.append(stage);
      return;
    }
    const stage = stageFor(step, ctx);
    const oldRow = tiles(stage, before);
    const newRow = tiles(stage, after);
    oldRow.classList.add("op-string-old"); newRow.classList.add("op-string-new");
    newRow.style.visibility = "hidden";
    el.append(stage);
    const oldTiles = [...oldRow.querySelectorAll(".ow-tile")];
    const newTiles = [...newRow.querySelectorAll(".ow-tile")];
    const used = new Set();
    const reverse = step.focus?.includes("↶") || step.focus?.includes("reverse");
    const mapping = newTiles.map((tile, index) => {
      const candidates = oldTiles.map((oldTile, oldIndex) => oldTile.textContent === tile.textContent && !used.has(oldIndex) ? oldIndex : -1).filter(oldIndex => oldIndex >= 0);
      const oldIndex = candidates.sort((left, right) =>
        Math.abs((reverse ? oldTiles.length - 1 - index : index) - left) -
        Math.abs((reverse ? oldTiles.length - 1 - index : index) - right))[0];
      if (oldIndex !== undefined) used.add(oldIndex);
      return oldIndex;
    });
    const duration = 760;
    const start = () => {
      if (!stage.isConnected) return;
      const oldRects = oldTiles.map(tile => tile.getBoundingClientRect());
      const newRects = newTiles.map(tile => tile.getBoundingClientRect());
      newRow.style.visibility = "visible";
      mapping.forEach((oldIndex, index) => {
        const tile = newTiles[index];
        if (oldIndex === undefined) {
          tile.animate([{opacity: 0, transform: "scale(.65)"}, {opacity: 1, transform: "scale(1)"}],
            {duration, easing: "cubic-bezier(.22,1,.36,1)"});
        } else {
          oldTiles[oldIndex].style.visibility = "hidden";
          tile.animate([{transform: `translate(${oldRects[oldIndex].left - newRects[index].left}px, ${oldRects[oldIndex].top - newRects[index].top}px)`, backgroundColor: "var(--op-card)"},
            {transform: "translate(0,0)", backgroundColor: "var(--op-bg)"}],
          {duration, easing: "cubic-bezier(.22,1,.36,1)"});
        }
      });
      oldTiles.forEach((tile, index) => { if (!used.has(index)) tile.animate([{opacity: 1}, {opacity: 0, transform: "scale(.7)"}], {duration: 420, fill: "forwards"}); });
      if (!newTiles.length) newRow.animate([{opacity: 0}, {opacity: 1}], {duration, fill: "forwards"});
      setTimeout(() => { if (stage.isConnected) oldRow.remove(); }, duration);
    };
    requestAnimationFrame(start);
  }
  worlds.register("strings", {renderValue: tiles, renderStep});
})();
