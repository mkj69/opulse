/* Opulse visual tour components.
 *
 * Each widget reads the JSON written by tools/docs_visuals.py, i.e. from a real run of the
 * library, and replaces the static fallback that follows it:
 *
 *   <div class="opv" data-kind="growth|unfold|contrast|steps|solve|equiv|ripple|freq|induce">
 *     <script type="application/json">{...}</script>
 *     <div class="opv-static">...</div>
 *   </div>
 *
 * No library, no network. With prefers-reduced-motion the widgets open on their last step and
 * do not play by themselves; every step stays reachable with the controls. The induce widget
 * also opens on its complete frame before replaying on view.
 */
(function () {
  "use strict";

  const zh = () => document.documentElement.lang.toLowerCase().startsWith("zh");
  const tr = (en, cn) => zh() ? cn : en;
  const KIND_NAME = { simple: " ", branch: " ", recursive: " ", atom: " " };
  const kindName = (kind) => zh() ? (KIND_NAME[kind] || kind) : kind;
  const REASON_LABELS = {
    en: {
      "wrong layer": "wrong layer", "unused parameter": "unused parameter",
      "single call of the same arity": "just repeats a call", "duplicate branch bodies": "identical branches",
      "duplicate body": "same definition", "compiled code disagrees with reference": "disagrees with reference",
      "disagrees with reference": "disagrees with reference", "undefined on all samples": "undefined for every sample",
      "nearly constant": "nearly constant", "mostly returns an input": "mostly returns an input",
      "defined on too few inputs": "undefined too often", "degenerate subexpression": "constant subexpression",
      "dead branch": "dead branch", "undefined branch": "undefined branch",
      "behavioural duplicate": "same as an existing operator",
      "behavioural duplicate up to argument order": "same after swapping inputs",
      "behavioural duplicate up to negation": "same after negation",
      "behavioural duplicate up to argument order and negation": "same after swapping and negating",
      "draft": "could not make a candidate",
    },
    zh: {
      "wrong layer": " ", "unused parameter": " ",
      "single call of the same arity": " ", "duplicate branch bodies": " ",
      "duplicate body": " ", "compiled code disagrees with reference": " ",
      "disagrees with reference": " ", "undefined on all samples": " ",
      "nearly constant": " ", "mostly returns an input": " ",
      "defined on too few inputs": " ", "degenerate subexpression": " ",
      "dead branch": " ", "undefined branch": " ",
      "behavioural duplicate": " ",
      "behavioural duplicate up to argument order": " ",
      "behavioural duplicate up to negation": " ",
      "behavioural duplicate up to argument order and negation": " ",
      "draft": " ",
    },
  };
  const reasonKey = (reason) => {
    if (reason.startsWith("unused parameter ")) return "unused parameter";
    if (reason.startsWith("disagrees with reference:")) return "disagrees with reference";
    if (/^(dead|undefined) branch \d+$/.test(reason)) return reason.split(" ").slice(0, 2).join(" ");
    if (reason.startsWith("draft: ")) return "draft";
    return reason;
  };
  const reasonName = (reason) => REASON_LABELS[zh() ? "zh" : "en"][reasonKey(reason)] || reason;
  const atomRule = (rule) => {
    if (!zh()) return rule;
    const rules = {
      "a + b is integer addition.": "a + b  ",
      "a - b is integer subtraction.": "a - b  ",
      "a * b is integer multiplication.": "a * b  ",
      "a / b divides and rounds toward zero (-7 / 2 = -3); b = 0 gives NaN.": "a / b  -7 / 2 = -3 b = 0   NaN ",
      "a % b is the remainder a - b * (a / b), with the sign of a (-7 % 2 = -1); b = 0 gives NaN.": "a % b   a - b * (a / b)  a  -7 % 2 = -1 b = 0   NaN ",
      "- a is the negation of a.": "- a   a  ",
      "a @ reverses the decimal digits of |a| and keeps the sign of a (120 @ = 21, -123 @ = -321).": "a @   |a|   a  120 @ = 21 -123 @ = -321 ",
      "# a is sign(a) * |a| * (|a| + 1) / 2, computed exactly; only its result is checked against the bound (# 4 = 10, # -4 = -10).": "# a   sign(a) * |a| * (|a| + 1) / 2 # 4 = 10 # -4 = -10 ",
      "a $ is the number of 1 bits in the binary form of |a| (7 $ = 3).": "a $   |a|   1  7 $ = 3 ",
      "& a is sign(a) times the sum of the decimal digits of |a| (& -123 = -6).": "& a   sign(a)   |a|  & -123 = -6 ",
    };
    return rules[rule] || rule;
  };
  const stepMessage = (message) => zh()
    ? message.replace(/step (\d+) changes the value of a part from (\S+) to (\S+)/,
      (_, line, before, after) => `  ${line}   ${before}   ${after}`)
    : message;
  const rulesText = (rules) => zh() ? `  NaN

  - a + b
  - a - b
  - a * b
  - a % b   a - b * (a / b)  a  -7 % 2 = -1 b = 0   NaN
  - - a   a
  - a @   |a|   a  120 @ = 21 -123 @ = -321
  - # a   sign(a) * |a| * (|a| + 1) / 2 # 4 = 10 # -4 = -10
  - a $   |a|   1  7 $ = 3
  2147483647   NaN
  NaN   NaN
  lhs = { e1, if c1; e2, if c2; ...; e, else }  else
  NaN  NaN   NaN

 ` : rules.join("\n");
  const SVG = "http://www.w3.org/2000/svg";
  const REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ASSET_BASE = new URL("../", document.currentScript.src);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = (v) => (v === null || v === undefined ? "NaN" : String(v));
  const KIND = { simple: "simple", branch: "branch", recursive: "recursive", atom: "atom", num: "num" };

  function svg(tag, attrs, parent) {
    const node = document.createElementNS(SVG, tag);
    for (const k in attrs || {}) node.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(node);
    return node;
  }
  function h(tag, cls, html, parent) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (html !== undefined && html !== null) node.innerHTML = html;
    if (parent) parent.appendChild(node);
    return node;
  }
  const pillWidth = (label, size) => Math.max(size || 30, 14 + [...String(label)].length * 9.2);

  /* ------------------------------------------------------------------ player */
  const ICON = {
    first: '<svg viewBox="0 0 24 24"><path d="M6 5h2v14H6zM20 5v14L9 12z"/></svg>',
    prev: '<svg viewBox="0 0 24 24"><path d="M15.5 5v14L5 12z"/></svg>',
    play: '<svg viewBox="0 0 24 24"><path d="M7 4.5v15L20 12z"/></svg>',
    pause: '<svg viewBox="0 0 24 24"><path d="M6 5h4.5v14H6zM13.5 5H18v14h-4.5z"/></svg>',
    next: '<svg viewBox="0 0 24 24"><path d="M8.5 5v14L19 12z"/></svg>',
  };

  /** Shell with title, body, caption and controls. ``show(i)`` draws step i. */
  function player(root, opts) {
    const count = opts.steps;
    root.classList.add("opv-live");
    root.innerHTML = `
      <div class="opv-head"><span class="opv-title"><i class="opv-dot"></i>${esc(opts.title)}</span>
        <span class="opv-count" aria-live="off"></span></div>
      <div class="opv-body"></div>
      <div class="opv-caption" aria-live="polite"></div>
      <div class="opv-bar">
        <button type="button" data-a="first" aria-label="${tr("First step", " ")}">${ICON.first}</button>
        <button type="button" data-a="prev" aria-label="${tr("Previous step", " ")}">${ICON.prev}</button>
        <button type="button" data-a="play" class="opv-play" aria-label="${tr("Play", " ")}">${ICON.play}</button>
        <button type="button" data-a="next" aria-label="${tr("Next step", " ")}">${ICON.next}</button>
        <input type="range" class="opv-range" min="0" max="${count - 1}" value="0" aria-label="${tr("Step", " ")}">
      </div>`;
    const body = root.querySelector(".opv-body");
    const caption = root.querySelector(".opv-caption");
    const counter = root.querySelector(".opv-count");
    const range = root.querySelector(".opv-range");
    const play = root.querySelector(".opv-play");
    const P = { body, caption, root, i: -1, count, show: null };
    root.__opvPlayer = P;
    let timer = null;
    let observer = null;
    const delay = typeof opts.interval === "function" ? opts.interval : () => opts.interval || 1400;
    P.go = (k) => {
      const prev = P.i;
      P.i = Math.max(0, Math.min(count - 1, k));
      range.value = P.i;
      range.style.setProperty("--opv-fill", `${(100 * P.i) / Math.max(1, count - 1)}%`);
      counter.textContent = `${P.i + 1} / ${count}`;
      P.show(P.i, prev);
    };
    const stop = () => {
      clearTimeout(timer); timer = null;
      play.innerHTML = ICON.play; play.setAttribute("aria-label", tr("Play", " ")); root.classList.remove("opv-playing");
    };
    const tick = () => {
      if (P.i >= count - 1) return stop();
      P.go(P.i + 1);
      timer = setTimeout(tick, delay(P.i));
    };
    const start = () => {
      if (P.i >= count - 1) P.go(0);
      play.innerHTML = ICON.pause; play.setAttribute("aria-label", tr("Pause", " ")); root.classList.add("opv-playing");
      timer = setTimeout(tick, delay(P.i));
    };
    P.stop = stop;
    P.playing = () => timer !== null;
    root.querySelector(".opv-bar").addEventListener("click", (e) => {
      const a = e.target.closest("button")?.dataset.a;
      if (!a) return;
      if (a === "play") return timer ? stop() : start();
      stop();
      if (a === "first") P.go(0);
      if (a === "prev") P.go(P.i - 1);
      if (a === "next") P.go(P.i + 1);
    });
    range.addEventListener("input", () => { stop(); P.go(+range.value); });
    root.tabIndex = 0;
    root.addEventListener("keydown", (e) => {
      if (e.target.closest("input,button") && e.key !== " ") return;
      if (e.key === "ArrowRight") { stop(); P.go(P.i + 1); e.preventDefault(); }
      if (e.key === "ArrowLeft") { stop(); P.go(P.i - 1); e.preventDefault(); }
      if (e.key === " " && !e.target.closest("button")) { timer ? stop() : start(); e.preventDefault(); }
    });
    P.ready = () => {
      P.go(REDUCED || opts.initialFull ? count - 1 : 0);
      if (REDUCED) return;
      if (!("IntersectionObserver" in window)) { start(); return; }
      observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) { observer.disconnect(); if (P.i < count - 1 || opts.initialFull) start(); }
      }, { threshold: 0 });
      observer.observe(root);
    };
    P.jump = (k) => { stop(); P.go(k); };
    P.destroy = () => { stop(); if (observer) observer.disconnect(); };
    return P;
  }

  /** A floating card inside ``root``, used for hover and tap details. */
  function tooltip(root) {
    const tip = h("div", "opv-tip", "", root);
    tip.setAttribute("role", "tooltip");
    return {
      show(html, target) {
        tip.innerHTML = html;
        tip.classList.add("opv-on");
        const r = root.getBoundingClientRect(), t = target.getBoundingClientRect();
        const w = tip.offsetWidth, hgt = tip.offsetHeight;
        let x = t.left - r.left + t.width / 2 - w / 2;
        x = Math.max(8, Math.min(r.width - w - 8, x));
        let y = t.top - r.top - hgt - 10;
        if (y < 8) y = t.bottom - r.top + 10;
        tip.style.transform = `translate(${x}px, ${y}px)`;
      },
      hide() { tip.classList.remove("opv-on"); },
    };
  }

  const kindChip = (kind) => `<span class="opv-chip opv-k-${kind}">${esc(kindName(kind))}</span>`;
  const legend = (kinds) => `<div class="opv-legend">${kinds.map((k) =>
    `<span class="opv-k-${k}"><i></i>${kindName(k)}</span>`).join("")}</div>`;

  /* ================================================================== growth */
  function growth(root, data) {
    const nodes = data.nodes;
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const events = data.events;
    const P = player(root, { title: tr(`Growing an operator set · layers ${data.layers.join(" ")}`, `  · ${data.layers.join(" ")}  `),
      steps: events.length + 1, interval: (i) => (events[i] && events[i].t === "reject" ? 1500 : 1250) });

    const layers = [-1, ...data.layers.map((_, i) => i)];
    const W = 660, rowGap = 84, top = 40, H = top + rowGap * (layers.length - 1) + 44;
    const rowY = (layer) => H - 30 - (layer + 1) * rowGap;
    const rows = {};
    nodes.forEach((n) => (rows[n.layer] = rows[n.layer] || []).push(n));
    const x0 = 70, x1 = W - 14;
    Object.values(rows).forEach((list) => list.forEach((n, k) => {
      n.x = x0 + ((k + 0.5) * (x1 - x0)) / list.length;
      n.y = rowY(n.layer);
      n.w = pillWidth(n.symbol, 34);
      n.slot = k;
    }));

    const wrap = h("div", "opv-growth", "", P.body);
    const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "opv-svg", role: "img",
      "aria-label": tr("Operators of each layer and the operators they call", " ") }, wrap);
    const defs = svg("defs", {}, s);
    ["simple", "branch", "recursive", "atom"].forEach((k) => {
      const m = svg("marker", { id: `opv-arrow-${k}`, viewBox: "0 0 10 10", refX: 8, refY: 5,
        markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" }, defs);
      svg("path", { d: "M0,0 L10,5 L0,10 z", class: `opv-arrowhead opv-k-${k}` }, m);
    });
    layers.forEach((layer) => {
      const y = rowY(layer);
      svg("line", { x1: 10, x2: W - 10, y1: y, y2: y, class: "opv-row-rule" }, s);
      svg("text", { x: 12, y: y - 14, class: "opv-row-label" }, s).textContent = layer < 0 ? tr("atoms", " ") : tr(`layer ${layer}`, `  ${layer}  `);
    });
    const gEdges = svg("g", { class: "opv-edges" }, s);
    const gNodes = svg("g", {}, s);
    const ghost = svg("g", { class: "opv-ghost" }, s);
    const ghostRect = svg("rect", { rx: 13, height: 26 }, ghost);
    const ghostText = svg("text", { "text-anchor": "middle", dy: "0.35em" }, ghost);
    const ghostX = svg("text", { class: "opv-ghost-x", "text-anchor": "middle", dy: "0.35em" }, ghost);
    ghostX.textContent = "✕";

    const edgeEls = [];
    nodes.forEach((n) => n.deps.forEach((d) => {
      const t = byId[d];
      if (!t) return;
      let path;
      if (t === n) {
        const x = n.x + n.w / 2, y = n.y;
        path = `M${x - 2},${y - 9} C${x + 34},${y - 34} ${x + 34},${y + 34} ${x - 2},${y + 9}`;
      } else {
        const ya = n.y + 13, yb = t.y - 13, my = (ya + yb) / 2;
        path = `M${n.x},${ya} C${n.x},${my} ${t.x},${my} ${t.x},${yb}`;
      }
      const el = svg("path", { d: path, class: `opv-edge opv-k-${n.kind}${t === n ? " opv-loop" : ""}`, pathLength: 1,
        "marker-end": `url(#opv-arrow-${n.kind})` }, gEdges);
      edgeEls.push({ el, from: n.id, to: d });
    }));
    nodes.forEach((n) => {
      const g = svg("g", { class: `opv-node opv-k-${n.kind}`, tabindex: 0, role: "button",
        "aria-label": `${n.symbol}: ${n.definition || atomRule(n.rule)}` }, gNodes);
      g.style.transform = `translate(${n.x}px, ${n.y}px)`;
      svg("rect", { x: -n.w / 2, y: -13, width: n.w, height: 26, rx: 13 }, g);
      svg("text", { "text-anchor": "middle", dy: "0.35em" }, g).textContent = n.symbol;
      n.el = g;
    });

    const panel = h("div", "opv-panel", "", wrap);
    const card = h("div", "opv-card opv-cand", "", panel);
    const tally = h("div", "opv-card opv-tally", "", panel);
    const allReasons = [...new Set(events.filter((e) => e.t === "reject").map((e) => reasonKey(e.reason)))];
    const maxReason = Math.max(1, ...allReasons.map((r) => events.filter((e) => e.t === "reject" && reasonKey(e.reason) === r).length));
    tally.innerHTML = `<div class="opv-tally-acc"></div><div class="opv-sub">${tr("rejected candidates by reason", " ")}</div>
      <div class="opv-reasons">${allReasons.map((r) => `<div class="opv-reason" data-r="${esc(r)}" title="${esc([...new Set(events.filter((e) => e.t === "reject" && reasonKey(e.reason) === r).map((e) => e.reason))].join("; "))}"><span>${esc(reasonName(r))}</span>
        <b><i></i></b><em>0</em></div>`).join("")}</div>`;
    P.body.insertAdjacentHTML("beforeend", legend(["atom", "simple", "branch", "recursive"]));

    const tip = tooltip(root);
    const describe = (n) => {
      const samples = n.samples.map((s) => `<tr><td>${esc(s.call)}</td><td>${esc(fmt(s.value))}</td></tr>`).join("");
      return `<div class="opv-tip-head">${esc(n.symbol)} ${kindChip(n.kind)}${n.layer >= 0 ? `<span class="opv-muted">${tr(`layer ${n.layer}`, `  ${n.layer}  `)}</span>` : ""}</div>
        <code class="opv-def">${esc(n.definition || atomRule(n.rule))}</code>
        <table class="opv-samples">${samples}</table>`;
    };
    let hovered = null;
    const focusNode = (n) => {
      hovered = n;
      gNodes.querySelectorAll(".opv-node").forEach((g) => g.classList.remove("opv-hover"));
      edgeEls.forEach((e) => e.el.classList.toggle("opv-hl", !!n && e.from === n.id && e.el.classList.contains("opv-on")));
      if (!n) return tip.hide();
      n.el.classList.add("opv-hover");
      tip.show(describe(n), n.el);
    };
    nodes.forEach((n) => {
      n.el.addEventListener("mouseenter", () => n.el.classList.contains("opv-on") && focusNode(n));
      n.el.addEventListener("mouseleave", () => focusNode(null));
      n.el.addEventListener("focus", () => n.el.classList.contains("opv-on") && focusNode(n));
      n.el.addEventListener("blur", () => focusNode(null));
      n.el.addEventListener("click", (e) => { e.stopPropagation(); P.stop(); hovered === n ? focusNode(null) : focusNode(n); });
    });
    root.addEventListener("click", () => hovered && focusNode(null));

    P.show = (i) => {
      const accepted = { simple: 0, branch: 0, recursive: 0 };
      nodes.filter((n) => n.layer >= 0).forEach((n) => accepted[n.kind]++);
      const reasons = {};
      events.filter((event) => event.t === "reject").forEach((event) => {
        reasons[reasonKey(event.reason)] = (reasons[reasonKey(event.reason)] || 0) + 1;
      });
      const ev = i > 0 ? events[i - 1] : null;
      const current = ev && ev.t === "accept" ? byId[ev.id] : null;
      nodes.forEach((n) => {
        n.el.classList.add("opv-on");
        n.el.classList.toggle("opv-current", n === current);
      });
      edgeEls.forEach((e) => {
        e.el.classList.add("opv-on");
        e.el.classList.toggle("opv-new", !!current && e.from === current.id);
      });
      // a rejected candidate is drawn where the next operator of its layer will go
      if (ev && ev.t === "reject") {
        const slot = events.slice(0, i).filter((event) => event.t === "accept" && byId[event.id].layer === ev.layer).length;
        const target = rows[ev.layer][Math.min(slot, rows[ev.layer].length - 1)];
        const w = pillWidth(ev.symbol || "?", 34);
        ghostRect.setAttribute("x", -w / 2); ghostRect.setAttribute("y", -13); ghostRect.setAttribute("width", w);
        ghostText.textContent = ev.symbol || "?";
        ghostX.setAttribute("x", w / 2 + 2); ghostX.setAttribute("y", -14);
        ghost.style.transform = `translate(${target.x}px, ${target.y}px)`;
        ghost.setAttribute("class", `opv-ghost opv-on opv-k-${ev.kind}`);
        void ghost.getBoundingClientRect();
        ghost.classList.add("opv-shake");
      } else ghost.setAttribute("class", "opv-ghost");

      if (!ev) {
        card.innerHTML = `<div class="opv-cand-head"><span class="opv-badge">${tr("start", " ")}</span></div>
          <p class="opv-muted">${tr(`${nodes.filter((n) => n.layer < 0).length} atoms. Each new operator is a definition over the atoms and the operators below it.`, `  ${nodes.filter((n) => n.layer < 0).length}  `)}</p>`;
      } else if (ev.t === "accept") {
        card.innerHTML = `<div class="opv-cand-head"><span class="opv-badge opv-ok">${tr("accepted", " ")}</span>${kindChip(current.kind)}
          <span class="opv-muted">${tr(`layer ${current.layer}`, `  ${current.layer}  `)}</span></div><code class="opv-def">${esc(current.definition)}</code>
          <div class="opv-muted opv-eval">${current.samples.slice(0, 2).map((s) => `${esc(s.call)} = <b>${esc(fmt(s.value))}</b>`).join(" · ")}</div>`;
      } else {
        card.innerHTML = `<div class="opv-cand-head"><span class="opv-badge opv-bad">${tr("rejected", " ")}</span>${kindChip(ev.kind)}
          <span class="opv-muted">${tr(`layer ${ev.layer}`, `  ${ev.layer}  `)}</span></div>
          <code class="opv-def opv-struck">${esc(ev.definition || tr("(no draft)", " "))}</code>
          <div class="opv-why" title="${esc(ev.reason)}">${esc(reasonName(ev.reason))}</div>`;
      }
      card.classList.remove("opv-enter"); void card.offsetWidth; card.classList.add("opv-enter");
      tally.querySelector(".opv-tally-acc").innerHTML = ["simple", "branch", "recursive"].map((k) =>
        `<span class="opv-acc opv-k-${k}"><b>${accepted[k]}</b>${kindName(k)}</span>`).join("");
      tally.querySelectorAll(".opv-reason").forEach((row) => {
        const n = reasons[row.dataset.r] || 0;
        row.querySelector("em").textContent = n;
        row.querySelector("i").style.width = `${(100 * n) / maxReason}%`;
        row.classList.toggle("opv-hit", !!ev && ev.t === "reject" && reasonKey(ev.reason) === row.dataset.r);
      });
      const total = events.filter((e) => e.t === "reject").length;
      P.caption.innerHTML = i === events.length
        ? tr(`${nodes.length - rows[-1].length} operators accepted, ${total} candidates rejected. Hover or tap an operator.`, `  ${nodes.length - rows[-1].length}   ${total}  `)
        : (ev && ev.t === "reject" ? tr(`Candidate ${ev.symbol || ""} fails a check and is discarded.`, `  ${ev.symbol || ""}  `)
          : ev ? tr(`${current.symbol} joins layer ${current.layer}; its arrows point to the operators it calls.`, `${current.symbol}   ${current.layer}  `)
            : tr("Atoms are the starting point.", " "));
    };
    P.ready();
  }

  /* ================================================================== unfold */
  function layoutTree(tree) {
    const nodes = [], edges = [];
    let leaf = 0;
    (function rec(n, depth, path) {
      const kids = n[2];
      let x;
      if (!kids.length) x = leaf++;
      else {
        const xs = kids.map((c, i) => rec(c, depth + 1, `${path}.${i}`));
        x = (xs[0] + xs[xs.length - 1]) / 2;
      }
      nodes.push({ path, label: n[0], kind: n[1], x, depth, key: `${path}|${n[0]}|${n[1]}` });
      kids.forEach((_, i) => edges.push([path, `${path}.${i}`]));
      return x;
    })(tree, 0, "r");
    return { nodes, edges, leaves: leaf };
  }

  function unfold(root, data) {
    const frames = data.frames;
    const layouts = frames.map((f) => layoutTree(f.tree));
    const maxLeaves = Math.max(...layouts.map((l) => l.leaves));
    const maxDepth = Math.max(...layouts.map((l) => Math.max(...l.nodes.map((n) => n.depth))));
    const UX = 64, UY = 54, W = maxLeaves * UX + 20, H = (maxDepth + 1) * UY + 10;
    const P = player(root, { title: tr(`Unfold to atoms · ${data.title}`, `  · ${data.title}`), steps: frames.length,
      interval: (i) => (frames[i + 1] && frames[i + 1].note.kind === "expand" ? 1500 : 1000) });
    const treeScroll = h("div", "opv-tree-scroll", "", P.body);
    const s = svg("svg", { viewBox: `0 0 ${W} ${UY + 10}`, class: "opv-svg opv-tree", role: "img",
      "aria-label": tr("Call tree of the expression", " ") }, treeScroll);
    s.style.minWidth = `${W}px`;
    const gE = svg("g", { class: "opv-tedges" }, s);
    const gN = svg("g", {}, s);
    const info = h("div", "opv-panel opv-unfold-panel", "", P.body);
    const meter = h("div", "opv-card opv-meter", "", info);
    const note = h("div", "opv-card opv-note", "", info);
    const expr = h("div", "opv-expr", "", P.body);
    P.body.insertAdjacentHTML("beforeend", legend(["simple", "branch", "recursive", "atom"]));
    const live = new Map();
    const pathOf = (focus) => (focus ? "r" + focus.map((k) => `.${k}`).join("") : null);

    P.show = (i) => {
      const L = layouts[i], f = frames[i];
      const offset = ((maxLeaves - L.leaves) * UX) / 2 + 10 + UX / 2;
      const depth = Math.max(...L.nodes.map((n) => n.depth));
      s.setAttribute("viewBox", `0 0 ${W} ${Math.max(2, depth + 1) * UY + 10}`);
      const pos = {};
      L.nodes.forEach((n) => (pos[n.path] = { x: offset + n.x * UX, y: 28 + n.depth * UY }));
      const fresh = pathOf(f.focus);
      const next = frames[i + 1] ? pathOf(frames[i + 1].focus) : null;
      const seen = new Set();
      L.nodes.forEach((n) => {
        let g = live.get(n.key);
        const p = pos[n.path];
        if (!g) {
          g = svg("g", { class: `opv-tnode opv-k-${n.kind}` }, gN);
          const w = n.kind === "num" ? pillWidth(n.label, 30) : pillWidth(n.label, 36);
          svg("rect", { x: -w / 2, y: -14, width: w, height: 28, rx: n.kind === "num" ? 8 : 14 }, g);
          svg("text", { "text-anchor": "middle", dy: "0.35em" }, g).textContent = n.label;
          g.style.transform = `translate(${p.x}px, ${p.y}px) scale(0.4)`;
          g.style.opacity = 0;
          live.set(n.key, g);
          void g.getBoundingClientRect();
        }
        g.style.transform = `translate(${p.x}px, ${p.y}px)`;
        g.style.opacity = 1;
        const inFresh = fresh && (n.path === fresh || n.path.startsWith(fresh + "."));
        g.classList.toggle("opv-fresh", !!inFresh);
        g.classList.toggle("opv-next", n.path === next);
        seen.add(n.key);
      });
      for (const [key, g] of live) {
        if (!seen.has(key)) { g.remove(); live.delete(key); }
      }
      gE.innerHTML = "";
      L.edges.forEach(([a, b]) => {
        const pa = pos[a], pb = pos[b];
        svg("path", { d: `M${pa.x},${pa.y + 14} C${pa.x},${(pa.y + pb.y) / 2} ${pb.x},${(pa.y + pb.y) / 2} ${pb.x},${pb.y - 14}`,
          class: "opv-tedge" }, gE);
      });
      const defined = L.nodes.filter((n) => ["simple", "branch", "recursive"].includes(n.kind)).length;
      const atoms = L.nodes.filter((n) => n.kind === "atom").length;
      meter.innerHTML = `<div class="opv-stat"><b>${defined}</b><span>${tr("defined calls", " ")}</span></div>
        <div class="opv-stat"><b>${atoms}</b><span>${tr("atom calls", " ")}</span></div>
        <div class="opv-stat"><b>${L.nodes.length}</b><span>${tr("nodes", " ")}</span></div>`;
      const n = f.note;
      let text;
      if (!n) text = tr(`<b>Start.</b> Defined calls open into their definitions; atoms fold into numbers.`, `<b> </b> `);
      else if (n.kind === "expand") {
        text = tr(`<b>Open</b> <code>${esc(n.symbol)}</code> ${kindChip(n.op)} on <code>${n.inputs.map(fmt).join(", ")}</code>`, `<b> </b> <code>${esc(n.symbol)}</code> ${kindChip(n.op)}  <code>${n.inputs.map(fmt).join(", ")}</code>`) +
          (n.condition ? tr(`: branch ${n.branch}, since <code>${esc(n.condition)}</code>`, `  ${n.branch}  <code>${esc(n.condition)}</code>  `) : "") +
          `<code class="opv-def">${esc(data.definitions[n.symbol] || "")}</code>`;
      } else if (n.kind === "eval") {
        text = tr(`<b>Fold</b> atom <code>${esc(n.symbol)}</code> on <code>${n.inputs.map(fmt).join(", ")}</code> into <b>${fmt(n.output)}</b>`, `<b> </b>  <code>${esc(n.symbol)}</code>  <code>${n.inputs.map(fmt).join(", ")}</code>  <b>${fmt(n.output)}</b>`);
      } else {
        text = tr(`<b>Undefined</b>: ${n.reason === "nan_condition" ? "a compared value is NaN" : "no branch applies"}, so NaN`, `<b> </b> ${n.reason === "nan_condition" ? "  NaN" : " "}  NaN`);
      }
      note.innerHTML = text;
      expr.textContent = f.text;
      const last = i === frames.length - 1;
      root.classList.toggle("opv-finished", last);
      P.caption.innerHTML = last
        ? tr(`Value <b>${fmt(data.value)}</b>: ${data.expands} definitions opened, ${data.evals} atoms computed, every step re-checked by the reference interpreter.`, `  <b>${fmt(data.value)}</b>  ${data.expands}   ${data.evals}  `)
        : (i === 0 ? tr("The expression as written.", " ") : n.kind === "expand" ? tr("A defined call opens into its body.", " ") : tr("An atom with number arguments folds into its value.", " "));
    };
    P.ready();
  }

  /* ================================================================== contrast */
  function contrast(root, data) {
    const [A, B] = data.variants;
    const P = player(root, { title: tr("In-context test · one definition swapped", "  ·  "), steps: 6, interval: 1700 });
    const grid = h("div", "opv-contrast", "", P.body);
    const prompt = h("div", "opv-card opv-prompt", "", grid);
    const answers = h("div", "opv-answers", "", grid);
    const defsHtml = (variant) => variant.definitions.map((d) => {
      const swapped = d === data.swapped[0] || d === data.swapped[1];
      return `<div class="opv-defline${swapped ? " opv-swap" : ""}"><code>${esc(d)}</code></div>`;
    }).join("");
    prompt.innerHTML = `<div class="opv-sub">${tr("prompt", " ")}</div>
      <div class="opv-rules"><button type="button" aria-expanded="false">${tr(`Rules: ${data.rules.filter((r) => r.trim().startsWith("- ")).length} base operations and NaN`, ` ${data.rules.filter((r) => r.trim().startsWith("- ")).length}   NaN`)}</button>
        <pre hidden>${esc(rulesText(data.rules))}</pre></div>
      <div class="opv-sub">${tr("Definitions", " ")}</div><div class="opv-defs"></div>
      <div class="opv-question">${tr(`What is the value of <code>${esc(data.expression)}</code>?`, `<code>${esc(data.expression)}</code>  `)}</div>`;
    const defs = prompt.querySelector(".opv-defs");
    const rulesBtn = prompt.querySelector(".opv-rules button");
    rulesBtn.addEventListener("click", () => {
      const pre = rulesBtn.nextElementSibling;
      pre.hidden = !pre.hidden;
      rulesBtn.setAttribute("aria-expanded", String(!pre.hidden));
    });
    const question = prompt.querySelector(".opv-question");
    answers.innerHTML = [A, B].map((v, k) => `<div class="opv-card opv-answer" data-k="${k}">
        <div class="opv-sub">${k ? tr("with the swapped definition", " ") : tr("as given", " ")}</div>
        <div class="opv-big">${esc(v.answer)}</div>
        <div class="opv-muted">${tr(`reference answer from the interpreter; the prompt text alone gives ${esc(v.rederived)}`, `  ${esc(v.rederived)}`)}</div></div>`).join("");
    const cards = answers.querySelectorAll(".opv-answer");
    let shownVariant = null;
    P.show = (i) => {
      const variant = i >= 3 ? B : A;
      if (shownVariant !== variant) {
        defs.innerHTML = defsHtml(variant);
        if (i >= 3) defs.querySelectorAll(".opv-swap").forEach((d) => d.classList.add("opv-flash"));
        shownVariant = variant;
      }
      defs.classList.add("opv-on");
      question.classList.add("opv-on");
      defs.querySelectorAll(".opv-swap").forEach((d) => d.classList.toggle("opv-marked", i >= 2));
      cards[0].classList.toggle("opv-on", i >= 2);
      cards[1].classList.toggle("opv-on", i >= 4);
      cards[0].classList.toggle("opv-dim", i >= 4);
      answers.classList.toggle("opv-differ", i >= 5);
      P.caption.innerHTML = [
        tr("The prompt holds the definitions the question needs, and nothing that gives away the answer.", " "),
        tr(`The question: the value of <code>${esc(data.expression)}</code>.`, ` <code>${esc(data.expression)}</code>  `),
        tr(`The interpreter computes the reference answer <b>${esc(A.answer)}</b>.`, `  <b>${esc(A.answer)}</b> `),
        tr("One definition is replaced by another one of the same shape, under the same symbol.", " "),
        tr(`Same symbols, same question: the reference answer is now <b>${esc(B.answer)}</b>.`, `  <b>${esc(B.answer)}</b> `),
        tr("A model that reads the definitions gets both; one that guesses from the symbols cannot.", " "),
      ][i];
    };
    P.ready();
  }

  /* ================================================================== steps */
  function steps(root, data) {
    const runs = data.runs;
    const plan = [];
    runs.forEach((run, r) => {
      for (let k = 0; k <= run.rows.length; k++) plan.push([r, k]);
    });
    const P = player(root, { title: tr("Step grading · line by line", " "), steps: plan.length, interval: 1100 });
    const runName = (run) => {
      if (!zh()) return run.label;
      const slip = /^one slip on line (\d+)$/.exec(run.label);
      if (slip) return `  ${slip[1]}  `;
      return ({ "correct derivation": " ", "reference derivation": " ",
        "recursion count written wrong on line 2": "  2  " }[run.label] || run.label);
    };
    const tabs = h("div", "opv-tabs", runs.map((run, r) => `<button type="button" data-r="${r}">${esc(runName(run))}</button>`).join(""), P.body);
    const sheet = h("div", "opv-card opv-sheet", "", P.body);
    const summary = h("div", "opv-summary", "", P.body);
    tabs.addEventListener("click", (e) => {
      const r = e.target.closest("button")?.dataset.r;
      if (r === undefined) return;
      P.jump(plan.findIndex(([x]) => x === +r) + runs[+r].rows.length);
    });
    let drawn = -1;
    P.show = (i) => {
      const [r, k] = plan[i];
      const run = runs[r];
      tabs.querySelectorAll("button").forEach((b) => b.classList.toggle("opv-active", +b.dataset.r === r));
      if (drawn !== r) {
        sheet.innerHTML = `<div class="opv-line opv-q"><span class="opv-mark"></span><code>${esc(data.question)}</code></div>` +
          run.rows.map((row, n) => `<div class="opv-line opv-${row.status}"><span class="opv-mark"></span>
            <code>= ${esc(row.line)}</code>
            <span class="opv-tag">${row.status === "single" ? tr("one rewrite", " ") : row.status === "jump" ? tr("jump", " ") : row.status === "error" ? tr("first error", " ") : tr("not graded", " ")}</span>${row.message ? `<span class="opv-why">${esc(stepMessage(row.message))}</span>` : ""}</div>`).join("");
        drawn = r;
      }
      sheet.querySelectorAll(".opv-line:not(.opv-q)").forEach((el, n) => {
        el.classList.add("opv-on");
        el.classList.toggle("opv-cur", n === k - 1);
      });
      const current = sheet.querySelector(".opv-cur");
      if (current) {
        const top = current.offsetTop - sheet.offsetTop;
        if (top < sheet.scrollTop) sheet.scrollTop = top;
        else if (top + current.offsetHeight > sheet.scrollTop + sheet.clientHeight)
          sheet.scrollTop = top + current.offsetHeight - sheet.clientHeight;
      } else if (k === 0) sheet.scrollTop = 0;
      const done = k === run.rows.length;
      const rep = run.report;
      const lastLine = run.rows[run.rows.length - 1].line;
      summary.innerHTML = `<span class="opv-badge ${rep.first_error === null ? "opv-ok" : "opv-bad"}">${rep.first_error === null ? tr("all lines valid", " ") : tr(`first error on line ${rep.first_error + 1}`, `  ${rep.first_error + 1}  `)}</span>
        <span>${tr("last value", " ")} <b>${rep.final_value_correct ? tr("correct", " ") : tr("incorrect", " ")}</b></span>
        <span>${tr("derivation", " ")} <b>${rep.derivation_correct ? tr("correct", " ") : tr("incorrect", " ")}</b></span>
        <span>${tr(`${rep.single_steps} of ${rep.steps} lines are checked single rewrites`, `${rep.steps}   ${rep.single_steps}  `)}</span>
        <span>${tr("credit", " ")} <b>${rep.credit.toFixed(2)}</b></span>`;
      summary.classList.add("opv-on");
      const row = run.rows[k - 1];
      P.caption.innerHTML = k === 0
        ? (r === 0 ? tr("A derivation of the question, one rewrite per line.", " ") : tr("The same derivation with one value written wrong, continued from the slip.", " "))
        : done ? (r === 0 ? tr("Every line checks out and the last line is the answer.", " ")
          : tr(`Line ${rep.first_error + 1} is flagged${rep.final_value_correct ? `, although the last line, ${esc(lastLine)}, is still the right answer` : ""}. Lines after it earn nothing.`, `  ${rep.first_error + 1}  ${rep.final_value_correct ? `  ${esc(lastLine)}  ` : ""} `))
          : row.status === "error" ? tr(`Line ${k}: ${esc(row.message)}.`, `  ${k}  ${esc(stepMessage(row.message))} `) : row.status === "skipped" ? tr(`Line ${k} comes after the error.`, `  ${k}  `)
            : tr(`Line ${k} is one allowed rewrite of ${k === 1 ? "the question" : `line ${k - 1}`}.`, `  ${k}  ${k === 1 ? " " : `  ${k - 1}  `} `);
    };
    P.ready();
  }

  /* ================================================================== solve */
  function solve(root, data) {
    const scan = data.scan;
    const methodEn = data.method === "exhaustive" ? "exhaustive search" : data.method;
    const methodZh = data.method === "exhaustive" ? " " : data.method;
    const chunk = 10;
    const scanSteps = Math.ceil(scan.length / chunk);
    const total = 1 + scanSteps + data.reverse.length + 1;
    const P = player(root, { title: tr("Solving for x · fill in the blank", "  x ·  "), steps: total, interval: (i) => (i < scanSteps ? 420 : 1600) });
    const eq = h("div", "opv-equation", `<code>${esc(data.expression).replace(/\bx\b/g, '<span class="opv-x">x</span>')}</code> = <b>${esc(data.target)}</b>`, P.body);
    const strip = h("div", "opv-strip", "", P.body);
    const cells = scan.map((c) => {
      const cell = h("span", `opv-cell${c.value === null ? " opv-nan" : ""}${data.hits.includes(c.x) ? " opv-hitcell" : ""}`, "", strip);
      cell.title = `x = ${c.x}: ${fmt(c.value)}`;
      cell.tabIndex = -1;
      return cell;
    });
    const axis = h("div", "opv-axis", `<span>${data.window[0]}</span><span>0</span><span>${data.window[1]}</span>`, P.body);
    const readout = h("div", "opv-readout", "", P.body);
    const peel = h("div", "opv-peel", "", P.body);
    const tip = tooltip(root);
    strip.addEventListener("mouseover", (e) => {
      const k = cells.indexOf(e.target);
      if (k >= 0) tip.show(tr(`x = <b>${scan[k].x}</b> gives <b>${fmt(scan[k].value)}</b>${scan[k].value === data.target ? " ✓" : ""}`, `x = <b>${scan[k].x}</b>   <b>${fmt(scan[k].value)}</b>${scan[k].value === data.target ? " ✓" : ""}`), e.target);
    });
    strip.addEventListener("mouseleave", () => tip.hide());
    P.show = (i) => {
      const scanned = Math.min(scan.length, Math.max(0, i) * chunk);
      cells.forEach((c, k) => {
        c.classList.add("opv-on");
        c.classList.toggle("opv-cursor", k === scanned - 1 && i <= scanSteps);
      });
      const last = scan[scanned - 1];
      readout.innerHTML = i === 0
        ? tr(`Try every x in [${data.window[0]}, ${data.window[1]}] forward with the interpreter.`, `  [${data.window[0]}, ${data.window[1]}]   x `)
        : i <= scanSteps ? tr(`x = <b>${last.x}</b> gives ${fmt(last.value)}${last.value === data.target ? ` <span class="opv-badge opv-ok">= ${data.target}</span>` : ""}`, `x = <b>${last.x}</b>   ${fmt(last.value)}${last.value === data.target ? ` <span class="opv-badge opv-ok">= ${data.target}</span>` : ""}`)
          : tr(`In this window only x = <b>${data.hits.join(", ")}</b> gives ${data.target}.`, `  x = <b>${data.hits.join(", ")}</b>   ${data.target} `);
      const shown = Math.max(0, i - scanSteps);
      peel.innerHTML = data.reverse.slice(0, Math.min(shown, data.reverse.length)).map((st, k) => {
        const known = Object.entries(st.known).map(([p, v]) => tr(`argument ${+p + 1} = ${fmt(v)}`, `  ${+p + 1} = ${fmt(v)}`)).join(", ");
        return `<div class="opv-peelrow${k === shown - 1 && i <= scanSteps + data.reverse.length ? " opv-newrow" : ""}" style="--k:${k}">${tr(`<code>${esc(st.symbol)}</code> must give <b>${esc(st.target)}</b>${known ? ` with ${esc(known)}` : ""}`, `<code>${esc(st.symbol)}</code>${known ? `   ${esc(known)}  ` : ""}  <b>${esc(st.target)}</b>`)}
          <span class="opv-arrow">→</span> ${tr("unknown", " ")} ∈ <b>{${st.candidates.join(", ")}}</b></div>`;
      }).join("") + (i === total - 1
        ? `<div class="opv-solved"><span class="opv-badge opv-ok">x = ${data.answer}</span> ${tr(`unique over [${data.domain.map((d) => d.toLocaleString("en-US")).join(", ")}] by ${esc(methodEn)}; forward check: ${data.check_steps} steps give ${data.check_value}`, `  ${esc(methodZh)}   [${data.domain.map((d) => d.toLocaleString("zh-CN")).join(" ")}]   ${data.check_steps}   ${data.check_value}`)}</div>`
        : "");
      strip.classList.remove("opv-done");
      P.caption.innerHTML = i === 0 ? tr("One number is blank. Which x makes the equation true?", "  x  ")
        : i <= scanSteps ? tr("Scanning a window of candidates.", " ")
          : i < total - 1 ? tr("The solver works from the outside in: each step leaves one possible value for the inside.", " ")
            : tr("The solution set is complete, so x is unique; the answer is checked forward.", "  x  ");
    };
    P.ready();
  }

  /* ================================================================== equivalence */
  function equiv(root, data) {
    const pairs = data.pairs;
    const per = 9 + 2; // intro, 9 rows of the grid, verdict
    const P = player(root, { title: tr("Equivalence · proved or refuted", "  ·  "), steps: per * pairs.length, interval: (i) => (i % per === per - 1 ? 2200 : 380) });
    const wrap = h("div", "opv-equiv", "", P.body);
    const cards = pairs.map((p) => {
      const card = h("div", "opv-card opv-pair", "", wrap);
      card.innerHTML = `<div class="opv-pairkind"><b>${esc(tr(p.kind, p.kind_zh))}</b><span>${esc(tr(p.method, p.status === "proved" ? "z3  " : p.status === "checked" ? " " : " "))}${p.range ? ` [${p.range.join(", ")}]` : ""}</span></div>
        <div class="opv-sides"><code>${esc(p.left)}</code><span class="opv-eqsign">≟</span><code>${esc(p.right)}</code></div>
        ${p.rules.length ? `<details class="opv-pairrules"><summary>${tr("Definitions", " ")}</summary>${p.rules.map(rule => `<code>${esc(rule)}</code>`).join("")}</details>` : ""}
        <div class="opv-gridwrap"><div class="opv-grid9">${p.grid.map((g) => {
          const same = g[2] === g[3];
          const witness = p.counterexample && g[0] === p.counterexample.a && g[1] === p.counterexample.b;
          return `<span class="opv-g ${same ? "opv-same" : "opv-diff"}${witness ? " opv-witness" : ""}" title="${tr(`a = ${g[0]}, b = ${g[1]}: ${fmt(g[2])} vs ${fmt(g[3])}`, `a = ${g[0]} b = ${g[1]} ${fmt(g[2])}   ${fmt(g[3])}`)}"></span>`;
        }).join("")}</div><div class="opv-gridnote opv-muted">${p.range
          ? tr(`a ∈ [${p.axes.join(", ")}]; b unused`, `a ∈ [${p.axes.join(", ")}];   b`)
          : "a, b ∈ [-4, 4]"}${p.counterexample && !p.grid.some((g) => g[0] === p.counterexample.a && g[1] === p.counterexample.b)
          ? `<span class="opv-outside-witness"><i class="opv-g opv-diff opv-witness"></i>${tr("counterexample outside grid", "\u53cd\u4f8b\u5728\u56fe\u793a\u8303\u56f4\u5916")}</span>` : ""}</div></div>
        <div class="opv-verdict"></div>`;
      return card;
    });
    P.show = (i) => {
      const active = Math.floor(i / per), k = i % per;
      cards.forEach((card, c) => {
        card.classList.toggle("opv-active", c === active);
        card.querySelectorAll(".opv-grid9 .opv-g").forEach((g, n) => g.classList.toggle("opv-row-current", c === active && k > 0 && k < per - 1 && Math.floor(n / 9) === k - 1));
        const p = pairs[c];
        const v = card.querySelector(".opv-verdict");
        v.innerHTML = p.status === "proved" || p.status === "checked"
          ? `<span class="opv-badge opv-ok">${p.status === "proved" ? tr("proved", " ") : tr("checked", " ")}</span> ${p.status === "proved"
            ? tr(`equal for every a, b within ±${data.bound.toLocaleString("en-US")} (z3)`, `z3   ±${data.bound.toLocaleString("zh-CN")}  `)
            : tr(`equal for every a in [${p.range.join(", ")}] (exhaustive interpreter check)`, `  a ∈ [${p.range.join(", ")}]`)}`
          : `<span class="opv-badge opv-bad">${tr("refuted", " ")}</span> ${tr(`at ${Object.entries(p.counterexample).map(([n, x]) => `${n} = ${x.toLocaleString("en-US")}`).join(", ")}: left gives <b>${fmt(p.left_value)}</b>, right gives <b>${fmt(p.right_value)}</b>`, `  ${Object.entries(p.counterexample).map(([n, x]) => `${n} = ${x.toLocaleString("zh-CN")}`).join(" ")}   <b>${fmt(p.left_value)}</b>  <b>${fmt(p.right_value)}</b>`)}`;
        card.classList.add("opv-decided");
        card.classList.toggle("opv-refuted", p.status === "refuted");
      });
      const p = pairs[active];
      P.caption.textContent = k === 0 ? tr(p.explanation, p.explanation_zh)
        : k < per - 1 ? tr("Compare each row of values.", " ")
          : p.status === "proved" ? tr("z3 proves equality throughout the value bound.", "z3  ")
            : p.status === "checked" ? tr(`The interpreter checked every input in [${p.range.join(", ")}].`, `  [${p.range.join(", ")}]  `)
              : tr("The interpreter confirms the counterexample.", " ");
    };
    P.ready();
  }

  /* ================================================================== ripple */
  function ripple(root, data) {
    const nodes = data.nodes;
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const maxD = Math.max(...nodes.map((n) => n.distance));
    const P = player(root, { title: tr("Edit propagation · change one operator", "  ·  "), steps: maxD + 3, interval: 1500 });
    const edit = h("div", "opv-card opv-edit", "", P.body);
    const levels = {};
    nodes.forEach((n) => (levels[n.distance] = levels[n.distance] || []).push(n));
    const W = 660, rowH = 84, H = (maxD + 1) * rowH + 16;
    const graph = h("div", "opv-ripple-scroll", "", P.body);
    const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "opv-svg opv-ripple", role: "img",
      "aria-label": tr("Operators that depend on the edited one", " ") }, graph);
    const gE = svg("g", {}, s), gN = svg("g", {}, s);
    Object.entries(levels).forEach(([d, list]) => list.forEach((n, k) => {
      n.x = 20 + ((k + 0.5) * (W - 40)) / list.length;
      n.y = H - 46 - d * rowH;
    }));
    nodes.forEach((n) => n.deps.forEach((d) => {
      const t = byId[d];
      if (!t) return;
      const e = svg("path", { d: `M${n.x},${n.y + 24} C${n.x},${(n.y + t.y) / 2} ${t.x},${(n.y + t.y) / 2} ${t.x},${t.y - 24}`,
        class: "opv-redge" }, gE);
      (n.edges = n.edges || []).push(e);
    }));
    const cardW = Math.min(150, (W - 40) / Math.max(...Object.values(levels).map((l) => l.length)) - 10);
    nodes.forEach((n) => {
      const g = svg("g", { class: `opv-rnode opv-k-${n.kind}`, tabindex: 0 }, gN);
      g.style.transform = `translate(${n.x}px, ${n.y}px)`;
      svg("rect", { x: -cardW / 2, y: -24, width: cardW, height: 48, rx: 10 }, g);
      svg("text", { "text-anchor": "middle", y: -6, class: "opv-rcall" }, g).textContent = n.call;
      const v = svg("text", { "text-anchor": "middle", y: 14, class: "opv-rval" }, g);
      n.el = g; n.val = v;
    });
    const tip = tooltip(root);
    nodes.forEach((n) => {
      n.el.addEventListener("mouseenter", () => tip.show(`<code class="opv-def">${esc(n.definition)}</code>
        <div class="opv-muted">${esc(n.call)} ${tr(`${fmt(n.old)} before, ${fmt(n.new)} after`, `  ${fmt(n.old)}  ${fmt(n.new)}`)}</div>`, n.el));
      n.el.addEventListener("mouseleave", () => tip.hide());
    });
    const changed = nodes.filter((n) => n.changed).length;
    P.show = (i) => {
      const edited = i >= 1;
      edit.innerHTML = `<div class="opv-sub">${edited ? tr("edited definition", " ") : tr("definition", " ")}</div>
        <code class="opv-def${edited ? " opv-struck" : ""}">${esc(data.before)}</code>
        ${edited ? `<code class="opv-def opv-newdef">${esc(data.after)}</code>` : ""}`;
      const reach = i - 1; // distances reached by the wave
      nodes.forEach((n) => {
        const hit = edited && n.distance <= reach;
        n.el.classList.toggle("opv-hit", hit);
        n.el.classList.toggle("opv-changed", hit && n.changed);
        n.el.classList.toggle("opv-same", hit && !n.changed);
        n.el.classList.toggle("opv-front", edited && n.distance === reach);
        n.val.textContent = hit ? (n.changed ? `${fmt(n.old)} → ${fmt(n.new)}` : `${fmt(n.new)} ${tr("(same)", " ")}`) : fmt(n.old);
        (n.edges || []).forEach((e) => e.classList.toggle("opv-on", hit && n.distance <= reach));
      });
      P.caption.innerHTML = i === 0 ? tr(`Every operator that depends on <code>${esc(nodes[0].symbol)}</code>, with its value at a = ${data.point[0]}, b = ${data.point[1]}.`, `  <code>${esc(nodes[0].symbol)}</code>   a = ${data.point[0]} b = ${data.point[1]}  `)
        : i === 1 ? tr("One symbol of the definition changes.", " ")
          : i < maxD + 2 ? tr(`Recomputed from the edited text: operators ${reach} call${reach > 1 ? "s" : ""} away.`, `  ${reach}  `)
            : tr(`${changed} of ${nodes.length} values change; the others depend on it but keep their value.`, `${nodes.length}   ${changed}  `);
    };
    P.ready();
  }

  /* ================================================================== frequency */
  function freq(root, data) {
    const ops = data.operators, series = data.series;
    const snaps = series[0].snapshots.length;
    const plan = [];
    series.forEach((s, k) => { for (let t = 0; t < snaps; t++) plan.push([k, t]); });
    const P = player(root, { title: tr("Operator frequency · uniform or Zipf", "  ·  "), steps: plan.length, interval: (i) => ((i + 1) % snaps === 0 ? 1800 : 140) });
    const dial = h("div", "opv-tabs opv-dial", series.map((s, k) => `<button type="button" data-k="${k}">${esc(zh() && s.spec === "uniform" ? " " : zh() && s.spec.startsWith("zipf:") ? `  ${s.spec.split(":")[1]}` : s.spec)}</button>`).join(""), P.body);
    dial.addEventListener("click", (e) => {
      const k = e.target.closest("button")?.dataset.k;
      if (k !== undefined) P.jump(+k * snaps + snaps - 1);
    });
    const max = Math.max(...series.map((s) => Math.max(...s.snapshots[snaps - 1])));
    const W = 660, H = 230, padL = 34, padB = 46, bw = (W - padL - 10) / ops.length;
    const chart = h("div", "opv-freq-scroll", "", P.body);
    const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "opv-svg opv-freq", role: "img",
      "aria-label": tr("Uses of each defined operator in sampled expressions", " ") }, chart);
    const plotH = H - padB - 10;
    [0, 0.5, 1].forEach((f) => {
      const y = 10 + plotH * (1 - f);
      svg("line", { x1: padL, x2: W - 6, y1: y, y2: y, class: "opv-gridline" }, s);
      svg("text", { x: padL - 6, y: y + 4, "text-anchor": "end", class: "opv-tick" }, s).textContent = Math.round(max * f);
    });
    const groups = [];
    ops.forEach((o, k) => {
      if (!groups.length || groups[groups.length - 1].name !== o.group) groups.push({ name: o.group, from: k, to: k });
      groups[groups.length - 1].to = k;
    });
    groups.forEach((g) => {
      const xa = padL + g.from * bw + 3, xb = padL + (g.to + 1) * bw - 3;
      svg("line", { x1: xa, x2: xb, y1: H - 14, y2: H - 14, class: "opv-group-rule" }, s);
      svg("text", { x: (xa + xb) / 2, y: H - 2, "text-anchor": "middle", class: "opv-tick" }, s).textContent = zh() ? ({ binary: " ", prefix: " ", postfix: " " }[g.name] || g.name) : g.name;
    });
    const bars = ops.map((o, k) => {
      const x = padL + k * bw;
      const r = svg("rect", { x: x + bw * 0.16, width: bw * 0.68, y: 10 + plotH, height: 0, rx: 3, class: "opv-bar-rect" }, s);
      svg("text", { x: x + bw / 2, y: H - padB + 16, "text-anchor": "middle", class: "opv-barlabel" }, s).textContent = o.symbol;
      const v = svg("text", { x: x + bw / 2, y: 10 + plotH - 4, "text-anchor": "middle", class: "opv-barval" }, s);
      return { r, v };
    });
    const stats = h("div", "opv-panel opv-freqstats", "", P.body);
    P.show = (i) => {
      const [k, t] = plan[i];
      const row = series[k].snapshots[t];
      dial.querySelectorAll("button").forEach((b) => b.classList.toggle("opv-active", +b.dataset.k === k));
      row.forEach((c, n) => {
        const hgt = (plotH * c) / max;
        bars[n].r.style.y = `${10 + plotH - hgt}px`;
        bars[n].r.style.height = `${hgt}px`;
        bars[n].v.setAttribute("y", 10 + plotH - hgt - 4);
        bars[n].v.textContent = c || "";
      });
      const sum = row.reduce((a, b) => a + b, 0) || 1;
      const top = [...row].sort((a, b) => b - a);
      const share = (100 * (top[0] + top[1] + top[2])) / sum;
      const unused = row.filter((c) => c === 0).length;
      stats.innerHTML = `<div class="opv-stat"><b>${(t + 1) * data.every}</b><span>${tr("expressions sampled", " ")}</span></div>
        <div class="opv-stat"><b>${share.toFixed(0)}%</b><span>${tr("of defined calls go to the top 3", " ")}</span></div>
        <div class="opv-stat"><b>${unused}</b><span>${tr("operators not used yet", " ")}</span></div>
        <div class="opv-stat"><b>${Math.round(series[k].base_share * 100)}%</b><span>${tr("of all calls are atoms", " ")}</span></div>`;
      P.caption.innerHTML = series[k].spec === "uniform"
        ? tr("Uniform: every defined operator is about equally common.", " ")
        : tr(`${esc(series[k].spec)}: operators ranked in a seeded order; rank r is drawn with weight r^-${esc(series[k].spec.split(":")[1])}. A few are common, most are rare.`, `  ${esc(series[k].spec.split(":")[1])}  r   r^-${esc(series[k].spec.split(":")[1])}  `);
    };
    P.ready();
  }

  /* -------------------------------------------------------------- induce */
  function induce(root, data) {
    root.classList.add("opv-live");
    const chooser = h("div", "opv-chooser", "", root);
    const label = h("label", "", tr("Example", " "), chooser);
    const select = h("select", "", "", label);
    data.puzzles.forEach((p, index) => {
      h("option", "", esc(tr(p.label, p.label_zh)), select).value = index;
    });
    const description = h("p", "opv-example-description", "", chooser);
    const stage = h("div", "opv-stage", "", root);
    const point = (values) => `(${values.join(", ")})`;
    function choose(index) {
      if (stage.__opvPlayer) stage.__opvPlayer.destroy();
      stage.innerHTML = "";
      const puzzle = data.puzzles[index];
      description.textContent = tr(puzzle.why, puzzle.why_zh);
      const n = puzzle.examples.length;
      const P = player(stage, { title: tr("Guess the rule", " "), steps: n + 3,
        interval: 1900, initialFull: true });
      const atoms = h("div", "opv-induce-atoms", "", P.body);
      const grid = h("div", "opv-induce-grid", "", P.body);
      const left = h("div", "opv-induce-examples", "", grid);
      const right = h("div", "opv-induce-candidates", "", grid);
      const end = h("div", "opv-induce-end", "", P.body);
      P.show = (frame) => {
        const visible = Math.min(n, frame);
        const removed = new Set(puzzle.examples.slice(0, visible).flatMap((row) => row.eliminated));
        atoms.innerHTML = `<div class="opv-sub">${tr("Atoms", " ")}</div>` + puzzle.atoms.map((atom) =>
          `<code>${esc(atom.symbol)}</code> ${esc(tr(atom.plain, atom.plain_zh))}`).join(" · ") +
          `<div class="opv-muted">${tr("Comparisons choose the first matching branch.", " ")}</div>`;
        left.innerHTML = `<div class="opv-sub">${tr("Examples", " ")}</div>` + puzzle.examples.map((row, i) =>
          `<div class="opv-induce-row${i >= visible ? " opv-induce-pending" : ""}"><span>${i + 1}. ${point(row.inputs)}</span><b>${i < visible ? `→ ${row.output}` : "→ ?"}</b></div>`).join("");
        right.innerHTML = `<div class="opv-sub">${tr("Candidate rules", " ")}</div>` + puzzle.candidates.map((candidate, i) => {
          const first = puzzle.examples.slice(0, visible).findIndex((row) => row.eliminated.includes(i));
          const reason = first < 0 ? "" : tr(`example ${first + 1} gives ${puzzle.examples[first].candidate_outputs[i]}`,
            `  ${first + 1}   ${puzzle.examples[first].candidate_outputs[i]}`);
          return `<div class="opv-induce-rule${removed.has(i) ? " opv-induce-out" : ""}${frame >= n && i === 0 ? " opv-induce-winner" : ""}"><span>${i + 1}.</span><code>${esc(candidate)}</code>${removed.has(i) ? `<span>${esc(reason)}</span>` : ""}</div>`;
        }).join("");
        end.innerHTML = frame > n ? `<div class="opv-sub">${tr("Query predictions", " ")}</div><div class="opv-induce-queries">${puzzle.queries.map((q) =>
          `<span><code>${point(q.inputs)}</code> → <b>${q.output}</b></span>`).join("")}</div>` : "";
        if (frame > n + 1) end.innerHTML += `<div class="opv-induce-check"><strong>${tr("Stated rule", " ")}</strong> <code>${esc(puzzle.answer)}</code><span class="opv-badge opv-ok">${tr("checked on the range", " ")}</span> <span>${tr(`each input in [${puzzle.range.join(", ")}]`, `  [${puzzle.range.join(" ")}]  `)}</span></div>`;
        P.caption.textContent = frame === 0 ? tr("Compare each candidate with the examples.", " ")
          : frame <= n ? tr(`${puzzle.examples[frame - 1].eliminated.length} candidates ruled out; ${puzzle.examples[frame - 1].remaining} remain.`,
            `  ${puzzle.examples[frame - 1].eliminated.length}   ${puzzle.examples[frame - 1].remaining}  `)
            : frame === n + 1 ? tr("The surviving rule predicts both queries.", " ")
              : tr("The reference interpreter checked every input pair in the stated range.", "  ");
      };
      P.ready();
    }
    select.addEventListener("change", () => choose(+select.value));
    choose(0);
  }

  /* ------------------------------------------------------------------ boot */
  const KINDS = { growth, unfold, contrast, steps, solve, equiv, ripple, freq, induce };
  function examples(root, build, data) {
    root.classList.add("opv-live");
    const chooser = h("div", "opv-chooser", "", root);
    chooser.classList.toggle("opv-single", data.examples.length === 1);
    const label = h("label", "", tr("Example", " "), chooser);
    const select = h("select", "", "", label);
    data.examples.forEach((entry, i) => {
      const name = zh() ? ({ "Easy 1": "  1", "Easy 2": "  2", Hard: " ", Long: " " }[entry.label] || entry.label) : entry.label;
      h("option", "", `${name} · ${entry.operators} ${tr("operators", " ")} · ${entry.steps} ${tr("steps", " ")}`, select).value = i;
    });
    h("p", "opv-example-hint", tr("Pick an example; harder ones use more operators and longer derivations.", " "), chooser);
    const description = h("p", "opv-example-description", "", chooser);
    const stage = h("div", "opv-stage", "", root);
    let request = 0;
    async function choose(i) {
      const token = ++request;
      if (stage.__opvPlayer) stage.__opvPlayer.destroy();
      stage.innerHTML = `<p class="opv-muted">${tr("Loading example…", " …")}</p>`;
      try {
        const entry = data.examples[i];
        description.textContent = zh() ? entry.description.zh : entry.description.en;
        const payload = entry.data || await fetch(new URL(entry.url, ASSET_BASE)).then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.json();
        });
        if (token !== request) return;
        build(stage, payload);
        const atomLegend = h("div", "opv-atoms-legend");
        stage.prepend(atomLegend);
        window.OpulseAtoms.legend(atomLegend, payload.world || data.world || "integer", JSON.stringify(payload));
      } catch (err) {
        if (token === request) stage.innerHTML = `<p class="opv-muted">${tr("Example unavailable", " ")} ${esc(err.message)}</p>`;
      }
    }
    select.addEventListener("change", () => choose(+select.value));
    choose(0);
  }
  function init() {
    document.querySelectorAll(".opv:not([data-ready])").forEach((root) => {
      const script = root.querySelector('script[type="application/json"]');
      const build = KINDS[root.dataset.kind];
      if (!script || !build) return;
      root.dataset.ready = "1";
      try {
        const data = JSON.parse(script.textContent);
        if (data.examples) examples(root, build, data);
        else {
          build(root, data);
          const atomLegend = h("div", "opv-atoms-legend");
          root.prepend(atomLegend);
          window.OpulseAtoms.legend(atomLegend, data.world || "integer", JSON.stringify(data));
        }
      } catch (err) {
        root.classList.remove("opv-live");
        root.insertAdjacentHTML("afterbegin", `<p class="opv-muted">${tr("Animation unavailable", " ")} ${esc(err.message)}</p>`);
        if (window.console) console.error(err);
      }
    });
  }
  if (document.readyState !== "loading") init(); else document.addEventListener("DOMContentLoaded", init);
  if (window.document$) window.document$.subscribe(init);
})();
