/* Opulse documentation animations.
 *
 * Every widget reads its data from an inline <script type="application/json"> produced by
 * tools/docs_examples.py, i.e. from a real run of the engine. Markup:
 *
 *   <div class="opulse-anim" data-kind="trace|layers|holes">
 *     <script type="application/json">{...}</script>
 *   </div>
 */
(function () {
  "use strict";

  const zh = () => document.documentElement.lang.toLowerCase().startsWith("zh");
  const tr = (en, cn) => zh() ? cn : en;
  const kindName = (kind) => ({ simple: tr("simple", " "), branch: tr("branch", " "), recursive: tr("recursive", " ") })[kind] || kind;
  const reasonName = (reason) => zh() ? reason.replace(/degenerate subexpression/, " ")
    .replace(/unused parameter/, " ").replace(/duplicate branch bodies/, " ")
    .replace(/undefined on all samples/, " ") : reason;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const highlight = (text, cls) => esc(text).replace(/\[\[(.*?)\]\]/g, `<span class="${cls}">$1</span>`);
  const fmt = (v) => (v === null || v === undefined ? "NaN" : String(v));

  function player(root, title, count, render, interval) {
    root.innerHTML = `
      <div class="oa-head"><span class="oa-title">${esc(title)}</span><span class="oa-counter"></span></div>
      <div class="oa-stage"></div>
      <div class="oa-controls">
        <button data-a="first" title="${tr("First", " ")}">&#9198;</button>
        <button data-a="prev" title="${tr("Previous", " ")}">&#9664;</button>
        <button data-a="play" class="oa-play" title="${tr("Play / pause", " ")}">&#9654;</button>
        <button data-a="next" title="${tr("Next", " ")}">&#9654;&#9654;</button>
        <button data-a="last" title="${tr("Last", " ")}">&#9197;</button>
        <input type="range" min="0" max="${count - 1}" value="0" class="oa-range" aria-label="${tr("Step", " ")}">
      </div>`;
    const stage = root.querySelector(".oa-stage");
    const counter = root.querySelector(".oa-counter");
    const range = root.querySelector(".oa-range");
    const play = root.querySelector(".oa-play");
    let i = 0, timer = null;
    const show = (k) => {
      i = Math.max(0, Math.min(count - 1, k));
      range.value = i;
      counter.textContent = tr(`step ${i + 1} / ${count}`, `  ${i + 1} / ${count}  `);
      stage.classList.remove("oa-enter");
      void stage.offsetWidth; // restart the CSS transition
      stage.innerHTML = render(i);
      stage.classList.add("oa-enter");
    };
    const stop = () => { clearInterval(timer); timer = null; play.innerHTML = "&#9654;"; };
    const start = () => {
      if (i >= count - 1) show(0);
      play.innerHTML = "&#10074;&#10074;";
      timer = setInterval(() => (i >= count - 1 ? stop() : show(i + 1)), interval);
    };
    root.querySelector(".oa-controls").addEventListener("click", (e) => {
      const a = e.target.closest("button")?.dataset.a;
      if (!a) return;
      if (a !== "play") stop();
      if (a === "first") show(0);
      if (a === "prev") show(i - 1);
      if (a === "next") show(i + 1);
      if (a === "last") show(count - 1);
      if (a === "play") (timer ? stop() : start());
    });
    range.addEventListener("input", () => { stop(); show(+range.value); });
    show(0);
    // Start playing once the widget scrolls into view.
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) { io.disconnect(); start(); }
      }, { threshold: 0.6 });
      io.observe(root);
    }
  }

  /* ---------------------------------------------------------- trace */
  function trace(root, data) {
    const frames = data.frames;
    const final = frames.length ? frames[frames.length - 1].after.replace(/\[\[|\]\]/g, "") : "";
    player(root, data.title, frames.length + 1, (i) => {
      if (i === frames.length) {
        return `<div class="oa-expr oa-final">${esc(final)}</div>
                <div class="oa-note oa-done">${tr("Every step above was re-evaluated by the reference interpreter.", " ")}</div>`;
      }
      const f = frames[i];
      let note;
      if (f.kind === "expand") {
        note = zh()
          ? `<b> </b> <code>${esc(f.symbol)}</code>  <code>${f.inputs.map(fmt).join(", ")}</code> ` +
            (f.condition ? `  ${f.branch}  <code>${esc(f.condition)}</code>  ` : `  ${f.branch}`)
          : `<b>Unfold</b> <code>${esc(f.symbol)}</code> on <code>${f.inputs.map(fmt).join(", ")}</code>: ` +
            (f.condition ? `branch ${f.branch} because <code>${esc(f.condition)}</code> holds` : `branch ${f.branch} (unconditional)`);
      } else if (f.kind === "eval") {
        note = zh()
          ? `<b> </b>  <code>${esc(f.symbol)}</code>  <code>${f.inputs.map(fmt).join(", ")}</code>  <code>${fmt(f.output)}</code>`
          : `<b>Compute</b> base operation <code>${esc(f.symbol)}</code> on <code>${f.inputs.map(fmt).join(", ")}</code> = <code>${fmt(f.output)}</code>`;
      } else {
        note = `<b>${tr("Undefined", " ")}</b>: ` + (f.reason === "nan_condition" ? tr("a compared value is NaN", "  NaN") : tr("no branch condition holds", " ")) +
          ` &rarr; NaN`;
      }
      return `<div class="oa-expr">${highlight(f.before, "oa-focus")}</div>
              <div class="oa-arrow oa-${f.kind}">&#8595; ${note}</div>
              <div class="oa-expr">${highlight(f.after, "oa-new")}</div>`;
    }, 1600);
  }

  /* --------------------------------------------------------- layers */
  function layers(root, data) {
    const ops = data.operators;
    const byLayer = {};
    ops.forEach((op) => (byLayer[op.layer] = byLayer[op.layer] || []).push(op));
    const L = Object.keys(byLayer).map(Number).sort((a, b) => a - b);
    const W = 760, colW = W / L.length, rowH = 34;
    const H = Math.max(...L.map((l) => byLayer[l].length)) * rowH + 40;
    const pos = {};
    L.forEach((l, c) => byLayer[l].forEach((op, r) => (pos[op.id] = { x: c * colW + colW / 2, y: 40 + r * rowH })));
    const rejected = Object.entries(data.rejected).map(([k, v]) => `<li><code>${esc(reasonName(k))}</code> &times; ${v}</li>`).join("");
    player(root, tr("Growing an operator set layer by layer", " "), ops.length, (i) => {
      const shown = new Set(ops.slice(0, i + 1).map((o) => o.id));
      const cur = ops[i];
      let svg = `<svg viewBox="0 0 ${W} ${H}" class="oa-svg" role="img" aria-label="${tr("Operator dependency graph", " ")}">`;
      L.forEach((l, c) => (svg += `<text x="${c * colW + colW / 2}" y="18" class="oa-col">${tr(`layer ${l}`, `  ${l}  `)}</text>`));
      ops.slice(0, i + 1).forEach((op) => op.deps.forEach((d) => {
        if (!shown.has(d)) return;
        const a = pos[op.id], b = pos[d];
        svg += `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" class="oa-edge${op === cur ? " oa-edge-new" : ""}"/>`;
      }));
      ops.slice(0, i + 1).forEach((op) => {
        const p = pos[op.id];
        svg += `<g class="oa-node oa-${op.kind}${op === cur ? " oa-current" : ""}"><circle cx="${p.x}" cy="${p.y}" r="11"/>` +
          `<text x="${p.x + 16}" y="${p.y + 4}">${esc(op.symbol)}</text></g>`;
      });
      svg += "</svg>";
      return `${svg}<div class="oa-note">${tr(`<b>${esc(kindName(cur.kind))}</b> operator on layer ${cur.layer}:`, `  ${cur.layer}  <b>${esc(kindName(cur.kind))}</b> `)} <code>${esc(cur.definition)}</code></div>
        <div class="oa-legend"><span class="oa-simple">${kindName("simple")}</span><span class="oa-branch">${kindName("branch")}</span><span class="oa-recursive">${kindName("recursive")}</span></div>
        ${i === ops.length - 1 ? `<details class="oa-rejected"><summary>${tr("Drafts rejected by the acceptance checks", " ")}</summary><ul>${rejected}</ul></details>` : ""}`;
    }, 900);
  }

  /* ---------------------------------------------------------- holes */
  function holes(root, data) {
    const steps = data.steps;
    player(root, `${data.expression} = ${data.target}`, steps.length + 1, (i) => {
      const rows = steps.slice(0, Math.min(i + 1, steps.length)).map((s, k) => {
        const known = Object.entries(s.known).map(([p, v]) => tr(`arg ${p} = ${fmt(v)}`, `  ${p} = ${fmt(v)}`)).join(", ") || tr("no other argument", " ");
        const target = Array.isArray(s.target) ? `{${s.target.join(", ")}}` : s.target;
        return `<div class="oa-peel${k === i ? " oa-current-row" : ""}" style="margin-left:${k * 1.6}em">
          ${tr(`<code>${esc(s.symbol)}</code> must give <b>${esc(target)}</b> with ${esc(known)}`, `<code>${esc(s.symbol)}</code>   ${esc(known)}   <b>${esc(target)}</b>`)}
          &rarr; ${tr("unknown argument", " ")} &isin; <b>{${s.candidates.join(", ")}}</b>
          <span class="oa-tag">${s.complete ? tr("complete", " ") : tr("partial", " ")}</span></div>`;
      }).join("");
      const done = i === steps.length
        ? `<div class="oa-note oa-done">x &isin; {${data.solutions.join(", ")}} &mdash; ${data.unique ? tr("unique", " ") : tr("not unique", " ")} ${tr(`in [${data.domain.join(", ")}]; every candidate was checked forward.`, `  [${data.domain.join(", ")}] `)}</div>`
        : "";
      return `<div class="oa-expr">${esc(data.expression)} = ${esc(data.target)}</div>${rows}${done}`;
    }, 1800);
  }

  const KINDS = { trace, layers, holes };
  function init() {
    document.querySelectorAll(".opulse-anim:not([data-ready])").forEach((root) => {
      const script = root.querySelector('script[type="application/json"]');
      const kind = KINDS[root.dataset.kind];
      if (!script || !kind) return;
      root.dataset.ready = "1";
      const data = JSON.parse(script.textContent);
      try {
        kind(root, data);  // replaces the static fallback rendered into the page
      } catch (err) {
        root.insertAdjacentHTML("afterbegin", `<p class="oa-note">${tr("Animation unavailable", " ")} ${esc(err.message)}</p>`);
      }
    });
  }
  // Run now, after the DOM is ready, and after every instant-navigation page swap (Material).
  if (document.readyState !== "loading") init(); else document.addEventListener("DOMContentLoaded", init);
  if (window.document$) window.document$.subscribe(init);
})();
