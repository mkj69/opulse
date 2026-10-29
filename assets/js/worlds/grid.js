(function () {
  "use strict";
  const palette = ["#111111", "#0074d9", "#ff4136", "#2ecc40", "#ffdc00",
    "#aaaaaa", "#f012be", "#ff851b", "#7fdbff", "#870c25"];
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const worlds = window.OpulseWorlds;
  const running = new WeakMap();

  // Cells shrink with the grid so that a 10 by 10 grid and a 3 by 3 grid take similar space.
  function board(rows, budget, previous) {
    const width = rows[0].length, height = rows.length;
    const size = Math.max(budget < 70 ? 5 : 9, Math.min(30, Math.floor(budget / Math.max(width, height))));
    const node = document.createElement("div");
    node.setAttribute("role", "img");
    node.setAttribute("aria-label", height + "×" + width + worlds.tr(" grid. Rows: ", " 网格。每行：") +
      rows.map(row => row.join("")).join(", "));
    node.style.cssText = "display:grid;grid-template-columns:repeat(" + width + "," + size + "px);gap:1px;padding:3px;" +
      "border:1px solid var(--op-line);border-radius:6px;background:var(--op-line);width:max-content";
    rows.forEach((row, y) => row.forEach((colour, x) => {
      const cell = document.createElement("span");
      const changed = previous && (!previous[y] || previous[y][x] === undefined || previous[y][x] !== colour);
      cell.style.cssText = "display:block;width:" + size + "px;height:" + size + "px;border-radius:2px;background:" +
        (colour === 0 ? "var(--op-bg)" : palette[colour]) + (changed ? ";outline:2px solid var(--op-amber);outline-offset:-2px" : "");
      node.appendChild(cell);
    }));
    return node;
  }

  function renderValue(el, value, ctx, previous) {
    if (!value || value.t !== "grid") { worlds.fallbackValue(el, value); return; }
    const compact = ctx && ctx.compact;
    const block = document.createElement("div");
    block.style.cssText = "display:inline-flex;flex-direction:column;align-items:center;gap:4px;max-width:100%";
    const grid = board(value.v, ctx && ctx.mini ? 58 : compact ? 84 : (ctx && (ctx.step || ctx.large) ? 240 : 150), previous);
    block.append(grid);
    if (!(ctx && ctx.mini)) {
      const size = document.createElement("span");
      size.textContent = value.v.length + " × " + value.v[0].length;
      size.style.cssText = "color:var(--op-muted);font:.8rem var(--op-mono)";
      block.append(size);
    }
    el.appendChild(block);
    if (!reduced.matches && !compact) {
      grid.animate([{opacity: .5, transform: "scale(.97)"}, {opacity: 1, transform: "scale(1)"}], {duration: 240, easing: "ease-out"});
    }
  }

  function renderStep(el, step, ctx) {
    (running.get(el) || []).forEach(animation => animation.cancel());
    running.delete(el);
    const previous = step.previous?.t === "grid" ? step.previous.v : null;
    const next = step.value?.t === "grid" ? step.value.v : null;
    el.replaceChildren();
    if (!previous && !next || !step.previous) { renderValue(el, step.value, {...ctx, step: true}); return; }
    const stage = document.createElement("div");
    stage.className = "op-grid-transition";
    stage.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:12px;max-width:100%;padding:10px;box-sizing:border-box";
    const display = value => {
      const node = document.createElement("span");
      worlds.fallbackValue(node, value);
      return node;
    };
    const from = previous ? board(previous, 168) : display(step.previous);
    const to = next ? board(next, 168, previous) : display(step.value);
    const arrow = document.createElement("span");
    arrow.textContent = "→";
    arrow.setAttribute("aria-hidden", "true");
    arrow.style.cssText = "color:var(--op-amber);font:700 1.3rem system-ui,sans-serif";
    const label = (text, grid) => {
      const block = document.createElement("div");
      block.style.cssText = "display:grid;justify-items:center;gap:7px;min-width:0";
      const heading = document.createElement("span");
      heading.textContent = text;
      heading.style.cssText = "color:var(--op-muted);font:600 .76rem system-ui,sans-serif;letter-spacing:.05em";
      block.append(heading, grid);
      return block;
    };
    const afterFrame = document.createElement("div");
    afterFrame.style.cssText = "position:relative;display:grid;place-items:center";
    afterFrame.append(to);
    stage.append(label(worlds.tr("BEFORE", "之前"), from), arrow, label(worlds.tr("AFTER", "之后"), afterFrame));
    el.append(stage);
    if (reduced.matches) return;
    const animations = [];
    if (!previous || !next) {
      animations.push(to.animate([{opacity:.2,transform:"scale(.94)"}, {opacity:1,transform:"scale(1)"}],
        {duration:780,easing:"cubic-bezier(.2,.8,.2,1)"}));
      running.set(el, animations);
      return;
    }
    const height = previous.length, width = previous[0].length;
    const sameShape = height === next.length && width === next[0].length;
    const changed = !sameShape || next.some((row, y) => row.some((colour, x) => colour !== previous[y][x]));
    if (!changed) return;
    const movingBoard = board(previous, 168);
    movingBoard.setAttribute("aria-hidden", "true");
    movingBoard.removeAttribute("role");
    movingBoard.style.cssText += ";position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);pointer-events:none;z-index:1";
    afterFrame.append(movingBoard);
    let transform = "none";
    if (changed && sameShape && next.every((row, y) => row.every((colour, x) => colour === previous[y][width - x - 1]))) transform = "scaleX(-1)";
    else if (changed && sameShape && next.every((row, y) => row.every((colour, x) => colour === previous[height - y - 1][x]))) transform = "scaleY(-1)";
    else if (changed && next.length === width && next[0].length === height && next.every((row, y) => row.every((colour, x) => colour === previous[height - x - 1][y]))) transform = "rotate(90deg)";
    else if (changed && next.length === width && next[0].length === height && next.every((row, y) => row.every((colour, x) => colour === previous[x][width - y - 1]))) transform = "rotate(-90deg)";
    if (transform !== "none") {
      const movement = movingBoard.animate([
        {transform: "translate(-50%,-50%)", opacity: 1, borderColor: "var(--op-amber)"},
        {transform: `translate(-50%,-50%) ${transform}`, opacity: 1, borderColor: "var(--op-amber)", offset: .68},
        {transform: `translate(-50%,-50%) ${transform}`, opacity: 0}
      ], {duration: 780, easing: "cubic-bezier(.2,.8,.2,1)"});
      movement.onfinish = () => movingBoard.remove();
      animations.push(movement);
    } else if (sameShape) {
      const oldCells = [...movingBoard.children], newCells = [...to.children];
      const used = new Set();
      let shift = -1;
      for (let amount = 1; changed && amount < width; amount++) {
        if (next.every((row, y) => row.every((colour, x) => colour === previous[y][(x - amount + width) % width]))) {
          shift = amount;
          break;
        }
      }
      oldCells.forEach((cell, index) => {
        const colour = previous[Math.floor(index / width)][index % width];
        if (!colour) return;
        const destination = shift >= 0 ? Math.floor(index / width) * width + (index % width + shift) % width :
          next.flat().findIndex((item, offset) => item === colour && !used.has(offset) &&
          (offset === index || item !== previous[Math.floor(offset / width)][offset % width]));
        if (destination < 0 || destination === index) return;
        used.add(destination);
        const first = cell.getBoundingClientRect(), last = newCells[destination].getBoundingClientRect();
        animations.push(cell.animate([{transform: "translate(0,0)", outline: "2px solid var(--op-amber)"},
          {transform: `translate(${last.left - first.left}px,${last.top - first.top}px)`, outline: "2px solid var(--op-cyan)"}],
        {duration: 780, easing: "cubic-bezier(.2,.8,.2,1)"}));
      });
    }
    if (transform === "none") {
      const fade = movingBoard.animate([{opacity:1},{opacity:1,offset:.58},{opacity:0}],
        {duration:780,easing:"ease-out"});
      fade.onfinish = () => movingBoard.remove();
      animations.push(fade);
    }
    [...to.children].forEach((cell, index) => {
      const y = Math.floor(index / next[0].length), x = index % next[0].length;
      if (previous[y]?.[x] === next[y][x]) return;
      animations.push(cell.animate([{outlineColor: "var(--op-amber)", filter: "brightness(1.7)"},
        {outlineColor: "var(--op-cyan)", filter: "brightness(1)"}],
      {duration: 780, easing: "ease-out"}));
    });
    animations.push(to.animate([{opacity: .3}, {opacity: 1}], {duration: 780, easing: "ease-out"}));
    running.set(el, animations);
  }

  // Grid literals in expressions and notes read as "▦3×3"; the picture shows the cells.
  function shorten(text) {
    return String(text).replace(/\[\[[\d, ]*\](?:, \[[\d, ]*\])*\]/g, literal => {
      const rows = literal.slice(1, -1).split("], [");
      return "▦" + rows.length + "×" + rows[0].replace(/[\[\]]/g, "").split(",").length;
    });
  }

  worlds.register("grid", {renderValue, renderStep, shorten});
}());
