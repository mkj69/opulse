/* Granularity animation (docs/snippets/granularity_anim.html).

   One expression derived at any cut of the same derivation tree. A row of operator chips
   chooses which defined operators are known (computed in one step) and which unfold; the
   side by side view plays that cut in lockstep with the cut where every operator is known and
   the cut where everything unfolds. A zoom view opens every one-step evaluation into its own
   derivation. The data comes from tools/docs_granularity.py
   (docs/assets/data/granularity_anim.json): all 2^k cuts of the k defined operators, every
   step of each one a step of the reference interpreter's trace at that cut.

   URL parameters freeze a state for screenshots and links:
     ?gran-t=<frame>      show frame <frame> and do not autoplay
     ?gran-mode=zoom      start in the zoom view
     ?gran-known=<bits>   the cut: one 0 or 1 per chip, left to right, 1 = known;
                          or all, top (only the top layer unfolds), none
   The same keys also work in the hash (#gran-t=4&gran-known=101). */
(function () {
  "use strict";

  const SCRIPT = document.currentScript && document.currentScript.src;
  const DATA_URL = SCRIPT ? new URL("../data/granularity_anim.json", SCRIPT).href : null;

  const STR = {
    en: {
      lockstep: "Side by side", zoom: "Open a step", play: "Play", pause: "Pause",
      back: "Previous step", forward: "Next step", speed: "Speed", frame: "Position",
      coarse: "All known", medium: "Your cut", fine: "All unfolded",
      coarseSub: "every operator in one step", fineSub: "everything unfolds to atoms",
      subKnown: "known", subUnfolded: "unfolds", subNone: "none",
      steps: n => n === 1 ? "1 step" : n + " steps",
      cutLabel: "Operators", chipKnown: "one step", chipUnfolded: "unfolds",
      atoms: "atoms", atomsState: "always unfolded",
      chipAria: (op, known) => op + ": " + (known ? "known, computed in one step" : "unfolded") + ". Click to switch.",
      atomsAria: "Atoms: base operations, always applied directly",
      presets: "Shortcuts", presetAll: "All known", presetTop: "Only top layer unfolds", presetNone: "All unfolded",
      hint: "Click an operator to choose whether it is known or unfolded. Any combination gives a checked derivation.",
      start: "Start", result: "Result",
      kind: { expand: "expand", branch: "branch", recursion: "recursion", atom: "atom", known: "one step" },
      legendCheck: "matches the reference interpreter",
      verified: "Verified by the reference interpreter",
      otherwise: "otherwise", if: "if",
      capStart: "The middle column is the cut chosen above. Press play to run it side by side with every operator known and with everything unfolded.",
      capBand: (c, op, m, f) => "With every operator known, step " + c + " computes " + op + " at once; your cut takes " +
        m + " for it and full unfolding takes " + f + ".",
      capBandAtom: (c, op) => "Step " + c + " applies the atom " + op + ", so every column takes the same single step.",
      capEnd: (v, c, m, f) => "All three reach " + v + ": " + c + " steps with every operator known, " + m +
        " in your cut, " + f + " with everything unfolded.",
      zoomStart: "Each step computed at once can be opened into the steps it stands for.",
      zoomOpen: (op, src) => "Opening " + src + " shows how " + op + " computes its value.",
      zoomPending: op => "This step computes " + op + " at once; open it to see the steps it stands for.",
      zoomStep: src => "Inside " + src + ", the derivation goes on one step at a time.",
      zoomRootAtom: op => op + " is an atom, so this step has nothing inside to open.",
      zoomClose: v => "Closed again, the whole block is one step with result " + v + ".",
      zoomEnd: (v, n) => "Closed again, the derivation is " + n + " steps long and still ends at " + v + ".",
      open: "Open this step", close: "Close this step",
      load: "The animation could not load its data."
    },
    zh: {
      lockstep: " ", zoom: " ", play: " ", pause: " ",
      back: " ", forward: " ", speed: " ", frame: " ",
      coarse: " ", medium: " ", fine: " ",
      coarseSub: " ", fineSub: " ",
      subKnown: " ", subUnfolded: " ", subNone: " ",
      steps: n => n + "  ",
      cutLabel: " ", chipKnown: " ", chipUnfolded: " ",
      atoms: " ", atomsState: " ",
      chipAria: (op, known) => op + " " + (known ? " " : " ") + " ",
      atomsAria: " ",
      presets: " ", presetAll: " ", presetTop: " ", presetNone: " ",
      hint: " ",
      start: " ", result: " ",
      kind: { expand: " ", branch: " ", recursion: " ", atom: " ", known: " " },
      legendCheck: " ",
      verified: " ",
      otherwise: " ", if: " ",
      capStart: " ",
      capBand: (c, op, m, f) => "  " + c + "   " + op + "   " + m +
        "  " + f + " ",
      capBandAtom: (c, op) => "  " + c + "   " + op + " ",
      capEnd: (v, c, m, f) => "  " + v + "  " + c + "   " + m + "   " + f + "  ",
      zoomStart: " ",
      zoomOpen: (op, src) => "  " + src + "  " + op + "  ",
      zoomPending: op => "  " + op + "  ",
      zoomStep: src => "  " + src + "  ",
      zoomRootAtom: op => op + "  ",
      zoomClose: v => "  " + v + " ",
      zoomEnd: (v, n) => "  " + n + "   " + v + " ",
      open: " ", close: " ",
      load: " "
    }
  };
  const LEVELS = ["coarse", "medium", "fine"];
  const SPEEDS = [0.5, 1, 2];
  const TICK = 1150;           // ms per frame at speed 1
  const BAND_PAUSE = 700;      // extra pause when a coarse step completes
  const END_PAUSE = 4200;      // pause on the final frame before looping

  const reduced = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" })[c]);
  const valueText = value => typeof value === "string" ? JSON.stringify(value) : String(value);

  function urlParams() {
    const q = new URLSearchParams(location.search);
    const h = new URLSearchParams(location.hash.replace(/^#/, ""));
    const get = k => q.has(k) ? q.get(k) : h.get(k);
    return { t: get("gran-t"), mode: get("gran-mode"), known: get("gran-known") };
  }

  // A cut is a bit mask over data.chips: bit i set means chips[i] is known (one step).
  function parseCut(value, data) {
    const full = data.cuts.length - 1;
    if (value === null || value === undefined || value === "") return null;
    if (Object.prototype.hasOwnProperty.call(data.presets, value)) return data.presets[value];
    if (!/^[01]+$/.test(value) || value.length !== data.chips.length) return null;
    let mask = 0;
    for (let i = 0; i < value.length; i++) if (value[i] === "1") mask |= 1 << i;
    return mask & full;
  }

  // ------------------------------------------------------------------ text
  function symbolPattern(data) {
    const names = Object.keys(data.operators).sort((a, b) => b.length - a.length)
      .map(s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    return names.length ? new RegExp("(" + names.join("|") + ")", "g") : null;
  }
  function plain(text, re, data) {
    if (!re) return esc(text);
    return text.split(re).map((part, i) => {
      if (i % 2 === 0) return esc(part);
      const kind = (data.operators[part] || {}).kind || "base";
      return '<span class="ga-sym ga-op-' + kind + '">' + esc(part) + "</span>";
    }).join("");
  }
  function exprHtml(text, hit, cls, re, data) {
    if (!hit) return plain(text, re, data);
    const [a, b] = hit;
    return plain(text.slice(0, a), re, data) + '<span class="ga-hit ga-hit-' + cls + '">' +
      plain(text.slice(a, b), re, data) + "</span>" + plain(text.slice(b), re, data);
  }
  const CHECK = '<svg class="ga-check" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.4l2.9 2.8 6.1-6.4"/></svg>';

  function stepHtml(step, t, re, data, extra) {
    const kind = t.kind[step.cls] || step.cls;
    const cond = step.cond ? '<span class="ga-cond" data-if="' + esc(t.if) + '">' + plain(step.cond, re, data) + "</span>" :
      step.otherwise ? '<span class="ga-cond" data-if="">' + esc(t.otherwise) + "</span>" : "";
    return '<div class="ga-step ga-' + step.cls + (extra || "") + '">' +
      '<span class="ga-tag"><span class="ga-tag-kind">' + esc(kind) + "</span> " + plain(step.op, re, data) + "</span>" +
      '<span class="ga-expr"><span class="ga-eq">=</span> ' + exprHtml(step.text, step.hit, step.cls, re, data) + "</span>" +
      '<span class="ga-ok" title="' + esc(t.verified) + '" aria-label="' + esc(t.verified) + '">' + CHECK + "</span>" +
      cond + "</div>";
  }

  // ------------------------------------------------------------------ lockstep model
  // Three columns: every operator known, the chosen cut, everything unfolded. Each fine step
  // carries owner [coarse step, step of the chosen cut, itself].
  function lockstepModel(data, mask) {
    const cut = data.cuts[mask];
    const coarse = data.coarse, medium = cut.steps;
    const fine = data.fine.map((s, i) => Object.assign({}, s, { owner: [s.owner[0], cut.fine[i], i] }));
    const lastFine = [new Array(coarse.length).fill(-1), new Array(medium.length).fill(-1)];
    const firstFine = [new Array(coarse.length).fill(Infinity), new Array(medium.length).fill(Infinity)];
    fine.forEach((s, i) => {
      for (let k = 0; k < 2; k++) {
        lastFine[k][s.owner[k]] = Math.max(lastFine[k][s.owner[k]], i);
        firstFine[k][s.owner[k]] = Math.min(firstFine[k][s.owner[k]], i);
      }
    });
    const bands = coarse.map((s, c) => ({
      coarse: c,
      medium: medium.map((m, j) => j).filter(j => medium[j].owner[0] === c),
      fineCount: fine.filter(f => f.owner[0] === c).length
    }));
    return { coarse, medium, fine, lastFine, firstFine, bands, frames: fine.length };
  }

  function cutSummary(data, t, re, mask) {
    const known = data.chips.filter((c, i) => mask >> i & 1), unfolded = data.chips.filter((c, i) => !(mask >> i & 1));
    const list = ops => ops.length ? ops.map(op => plain(op, re, data)).join(" ") : esc(t.subNone);
    return esc(t.subKnown) + " " + list(known) + "<span class=\"ga-sep\" aria-hidden=\"true\"> · </span>" +
      esc(t.subUnfolded) + " " + list(unfolded);
  }

  function lockstepHtml(data, t, re, m, mask) {
    const levels = [m.coarse, m.medium, m.fine];
    const headOf = (key, k) => '<div class="ga-colhead ga-colhead-' + key + '">' +
      '<span class="ga-colname">' + esc(t[key]) + "</span>" +
      '<span class="ga-colsub">' + (k === 1 ? cutSummary(data, t, re, mask) : esc(t[key + "Sub"])) + "</span>" +
      '<span class="ga-colcount">' + esc(t.steps(levels[k].length)) + "</span></div>";
    const head = LEVELS.map(headOf).join("");
    const row = (k, i) => {
      const s = levels[k][i];
      return '<div class="ga-cell-step" data-ga="' + k + ":" + i + '">' + stepHtml(s, t, re, data) + "</div>";
    };
    let bands = "";
    m.bands.forEach((band, b) => {
      let rows = "";
      band.medium.forEach((j, r) => {
        const fines = m.fine.map((f, i) => i).filter(i => m.fine[i].owner[1] === j);
        rows += '<div class="ga-sub" style="grid-row:' + (r + 1) + '">' + row(1, j) + "</div>" +
          '<div class="ga-sub ga-sub-fine" style="grid-row:' + (r + 1) + '">' + fines.map(i => row(2, i)).join("") + "</div>";
      });
      bands += '<div class="ga-band" data-band="' + b + '" style="--rows:' + band.medium.length + '">' +
        '<div class="ga-bandno" aria-hidden="true">' + (b + 1) + "</div>" +
        '<div class="ga-coarsecell" style="grid-row:1 / span ' + band.medium.length + '">' + row(0, b) + "</div>" +
        rows + "</div>";
    });
    // Stacked layout for narrow screens: one card per level, bands marked by number.
    let stacked = "";
    LEVELS.forEach((key, k) => {
      let body = "";
      m.bands.forEach((band, b) => {
        const idx = levels[k].map((s, i) => i).filter(i => levels[k][i].owner[0] === b);
        body += '<div class="ga-sband" data-band="' + b + '"><div class="ga-bandno" aria-hidden="true">' + (b + 1) + "</div>" +
          '<div class="ga-sband-steps">' + idx.map(i => row(k, i)).join("") + "</div></div>";
      });
      stacked += '<section class="ga-scol ga-scol-' + key + '">' + headOf(key, k) + body + "</section>";
    });
    return '<div class="ga-start"><span class="ga-start-label">' + esc(t.start) + "</span> " +
      '<span class="ga-expr">' + plain(data.expression, re, data) + "</span></div>" +
      '<div class="ga-grid"><div class="ga-heads">' + head + "</div>" + bands + "</div>" +
      '<div class="ga-stack">' + stacked + "</div>" +
      '<div class="ga-end"><span class="ga-start-label">' + esc(t.result) + "</span> " +
      '<span class="ga-expr ga-final">' + esc(valueText(data.value)) + "</span>" + CHECK + "</div>";
  }

  function renderLockstep(root, st) {
    const m = st.model, t = st.t, f = st.frame;
    const done = (k, i) => k === 2 ? i < f : m.lastFine[k][i] < f;
    const cur = f > 0 ? m.fine[f - 1].owner : null;
    const next = f < m.frames ? m.fine[f].owner : null;
    root.querySelectorAll("[data-ga]").forEach(el => {
      const [k, i] = el.dataset.ga.split(":").map(Number);
      const isDone = done(k, i);
      const isCur = !!cur && cur[k] === i && (k === 2 || m.lastFine[k][i] === f - 1);
      const pending = !isDone && k < 2 && m.firstFine[k][i] < f;
      el.classList.toggle("is-done", isDone);
      el.classList.toggle("is-current", isCur && isDone && f < m.frames);
      el.classList.toggle("is-pending", pending);
    });
    const activeBand = cur ? cur[0] : -1;
    root.querySelectorAll("[data-band]").forEach(el => {
      const b = Number(el.dataset.band);
      el.classList.toggle("is-active", b === activeBand && f < m.frames);
      el.classList.toggle("is-past", m.lastFine[0][b] < f);
    });
    root.querySelector(".ga-end").classList.toggle("is-done", f === m.frames);
    let cap;
    if (f === 0) cap = t.capStart;
    else if (f === m.frames) cap = t.capEnd(valueText(st.data.value), m.coarse.length, m.medium.length, m.fine.length);
    else {
      const band = m.bands[activeBand], c = m.coarse[activeBand];
      cap = c.cls === "atom" ? t.capBandAtom(activeBand + 1, c.op) :
        t.capBand(activeBand + 1, c.op, t.steps(band.medium.length), t.steps(band.fineCount));
    }
    setCaption(root, cap, st);
  }

  // ------------------------------------------------------------------ zoom model
  function zoomModel(data) {
    const nodes = data.zoom.nodes;
    let counter = 0;
    // Instances: a shared node is shown once per place it is opened.
    function inst(id, depth) {
      const node = nodes[id];
      const me = { key: "z" + (counter++), id: id, node: node, depth: depth, steps: [] };
      me.steps = node.steps.map((s, k) => ({ step: s, key: me.key + ":" + k, child: s.child ? inst(s.child, depth + 1) : null }));
      return me;
    }
    const root = inst(data.zoom.root, 0);
    // Frames: a step with a derivation inside first appears pending, then opens, plays its
    // own steps (recursively), and closes again with its result.
    const frames = [{ open: [], focus: null, started: [], seen: [], note: { kind: "start" } }];
    const started = [], seen = [];
    const push = (open, focus, note) => frames.push({ open: open, focus: focus, started: started.slice(),
      seen: seen.slice(), note: note });
    function visit(node, open) {
      node.steps.forEach(s => {
        started.push(s.key);
        if (s.child) {
          push(open, s.key, { kind: "pending", step: s });
          const inner = open.concat(s.child.key);
          push(inner, null, { kind: "open", step: s });
          visit(s.child, inner);
          seen.push(s.key);
          push(open, s.key, { kind: "close", step: s });
        } else {
          seen.push(s.key);
          push(open, s.key, { kind: node === root ? "root" : "inner", step: s, node: node });
        }
      });
    }
    visit(root, []);
    frames.push({ open: [], focus: null, started: started.slice(), seen: seen.slice(), note: { kind: "end" } });
    return { root, frames };
  }

  function zoomHtml(data, t, re, node) {
    let html = "";
    node.steps.forEach(s => {
      const can = !!s.child;
      html += '<div class="ga-zrow" data-z="' + s.key + '"><div class="ga-zrow-inner">' +
        (can ? '<button type="button" class="ga-ztoggle" data-zopen="' + s.child.key + '" aria-expanded="false" aria-label="' +
          esc(t.open) + '"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4l4 4-4 4"/></svg></button>'
          : '<span class="ga-ztoggle-space"></span>') +
        stepHtml(s.step, t, re, data) + "</div></div>";
      if (can) {
        const c = s.child, k = data.operators[c.node.op] ? data.operators[c.node.op].kind : "simple";
        html += '<div class="ga-zkids" data-zkids="' + c.key + '"><div class="ga-zkids-inner ga-zk-' + k + '">' +
          '<div class="ga-zsrc">' + plain(c.node.text, re, data) + "</div>" + zoomHtml(data, t, re, c) + "</div></div>";
      }
    });
    return html;
  }

  function renderZoom(root, st) {
    const fr = st.zmodel.frames[st.frame];
    const manual = st.manual;
    const open = new Set(manual ? st.manualOpen : fr.open);
    const seen = new Set(fr.seen);
    root.querySelectorAll("[data-zkids]").forEach(el => {
      const on = open.has(el.dataset.zkids);
      el.classList.toggle("is-open", on);
      const btn = root.querySelector('[data-zopen="' + el.dataset.zkids + '"]');
      if (btn) {
        btn.setAttribute("aria-expanded", on ? "true" : "false");
        btn.setAttribute("aria-label", on ? st.t.close : st.t.open);
      }
    });
    const started = new Set(fr.started);
    root.querySelectorAll("[data-z]").forEach(el => {
      const key = el.dataset.z;
      const isDone = manual || seen.has(key);
      el.classList.toggle("is-done", isDone);
      el.classList.toggle("is-pending", !isDone && started.has(key));
      el.classList.toggle("is-current", !manual && fr.focus === key);
    });
    const n = fr.note, t = st.t;
    let cap = t.zoomStart;
    if (manual) cap = t.zoomStart;
    else if (n.kind === "pending") cap = t.zoomPending(n.step.step.op);
    else if (n.kind === "open") cap = t.zoomOpen(n.step.step.op, n.step.child.node.text);
    else if (n.kind === "close") cap = t.zoomClose(valueText(n.step.child.node.value));
    else if (n.kind === "inner") cap = t.zoomStep(n.node.node.text);
    else if (n.kind === "root") cap = t.zoomRootAtom(n.step.step.op);
    else if (n.kind === "end") cap = t.zoomEnd(valueText(st.data.value), st.zmodel.root.steps.length);
    setCaption(root, cap, st);
  }

  // ------------------------------------------------------------------ shell
  function setCaption(root, text, st) {
    const el = root.querySelector(".ga-caption");
    if (el.textContent !== text) el.textContent = text;
    const range = root.querySelector(".ga-range");
    range.max = String(st.last());
    range.value = String(st.frame);
    root.querySelector(".ga-pos").textContent = st.frame + " / " + st.last();
    root.style.setProperty("--ga-progress", (st.last() ? st.frame / st.last() : 0).toFixed(4));
  }

  function cutbarHtml(data, t, re) {
    const chips = data.chips.map((op, i) => {
      const kind = (data.operators[op] || {}).kind || "simple";
      return '<button type="button" class="ga-chip ga-chip-' + kind + '" data-chip="' + i + '" aria-pressed="false">' +
        '<span class="ga-chip-op">' + plain(op, re, data) + "</span>" +
        '<span class="ga-chip-state"></span></button>';
    }).join("");
    const atoms = '<span class="ga-chip ga-chip-atoms" role="note" aria-label="' + esc(t.atomsAria) + '" title="' +
      esc(t.atomsAria) + '"><span class="ga-chip-op">' + esc(t.atoms) + "</span>" +
      '<span class="ga-chip-state">' + esc(t.atomsState) + "</span></span>";
    const presets = [["all", t.presetAll], ["top", t.presetTop], ["none", t.presetNone]].map(([key, label]) =>
      '<button type="button" class="ga-preset" data-preset="' + key + '" aria-pressed="false">' + esc(label) + "</button>").join("");
    return '<div class="ga-cutbar">' +
      '<div class="ga-cutrow"><span class="ga-cutlabel">' + esc(t.cutLabel) + "</span>" +
      '<div class="ga-chips" role="group" aria-label="' + esc(t.cutLabel) + '">' + chips + atoms + "</div>" +
      '<span class="ga-cutcount" aria-live="polite"></span></div>' +
      '<div class="ga-presetrow"><span class="ga-cutlabel">' + esc(t.presets) + "</span>" +
      '<div class="ga-presets" role="group" aria-label="' + esc(t.presets) + '">' + presets + "</div></div>" +
      '<p class="ga-hint">' + esc(t.hint) + "</p></div>";
  }

  function shell(root, data, t) {
    const re = symbolPattern(data);
    const legend = ["expand", "branch", "recursion", "atom", "known"].map(k =>
      '<span class="ga-legend-item ga-' + k + '"><i></i>' + esc(t.kind[k]) + "</span>").join("") +
      '<span class="ga-legend-item ga-legend-check">' + CHECK + esc(t.legendCheck) + "</span>";
    root.innerHTML =
      '<div class="ga-top">' +
      '<div class="ga-modes" role="group">' +
      '<button type="button" class="ga-mode" data-mode="lockstep" aria-pressed="true">' + esc(t.lockstep) + "</button>" +
      '<button type="button" class="ga-mode" data-mode="zoom" aria-pressed="false">' + esc(t.zoom) + "</button></div>" +
      '<div class="ga-legend">' + legend + "</div></div>" +
      cutbarHtml(data, t, re) +
      '<p class="ga-caption" aria-live="polite"></p>' +
      '<div class="ga-stage ga-stage-lockstep"></div>' +
      '<div class="ga-stage ga-stage-zoom" hidden><div class="ga-zroot">' +
      '<div class="ga-zsrc ga-zsrc-root">' + plain(data.expression, re, data) + "</div>" +
      zoomHtml(data, t, re, zoomModel(data).root) + "</div></div>" +
      '<div class="ga-controls">' +
      '<button type="button" class="ga-btn ga-play" aria-label="' + esc(t.play) + '">' +
      '<svg class="ga-i-play" viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3.5v9l7.5-4.5z"/></svg>' +
      '<svg class="ga-i-pause" viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 3.5h2.5v9H4.5zM9 3.5h2.5v9H9z"/></svg></button>' +
      '<button type="button" class="ga-btn ga-back" aria-label="' + esc(t.back) + '"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 4L6 8l4 4"/></svg></button>' +
      '<button type="button" class="ga-btn ga-fwd" aria-label="' + esc(t.forward) + '"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4l4 4-4 4"/></svg></button>' +
      '<input class="ga-range" type="range" min="0" max="1" step="1" value="0" aria-label="' + esc(t.frame) + '">' +
      '<span class="ga-pos" aria-hidden="true"></span>' +
      '<button type="button" class="ga-btn ga-speed" aria-label="' + esc(t.speed) + '">1×</button>' +
      "</div>";
  }

  function load(root) {
    root.dataset.ready = "loading";
    const lang = (root.dataset.lang || document.documentElement.lang || "en").toLowerCase().startsWith("zh") ? "zh" : "en";
    const t = STR[lang];
    const src = root.dataset.src ? new URL(root.dataset.src, location.href).href : DATA_URL;
    fetch(src).then(r => {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(data => start(root, data, t)).catch(err => {
      console.warn("Opulse granularity animation:", err);
      root.dataset.ready = "error";
      root.insertAdjacentHTML("beforeend", '<p class="ga-error">' + esc(t.load) + "</p>");
    });
  }

  function start(root, data, t) {
    shell(root, data, t);
    const atomLegend = document.createElement("div");
    atomLegend.className = "ga-atoms-legend";
    root.querySelector(".ga-top").after(atomLegend);
    window.OpulseAtoms.legend(atomLegend, "integer", JSON.stringify(data.operators) + " " + data.expression);
    const p = urlParams();
    const re = symbolPattern(data);
    const given = parseCut(p.known, data);
    const st = {
      data: data, t: t, mode: p.mode === "zoom" ? "zoom" : "lockstep", frame: 0, playing: false, timer: null,
      speed: 1, manual: false, manualOpen: new Set(), mask: given === null ? data.presets.top : given,
      model: null, zmodel: null, visible: false
    };
    // The zoom DOM was built from its own instance tree; rebuild the model so keys match.
    st.zmodel = zoomModel(data);
    st.last = () => st.mode === "zoom" ? st.zmodel.frames.length - 1 : st.model.frames;
    // Build the side by side view of the current cut and show the cut on the chips.
    const setCut = mask => {
      st.mask = mask;
      st.model = lockstepModel(data, mask);
      root.querySelector(".ga-stage-lockstep").innerHTML = lockstepHtml(data, t, re, st.model, mask);
      root.querySelectorAll("[data-chip]").forEach(b => {
        const i = Number(b.dataset.chip), known = !!(mask >> i & 1);
        b.setAttribute("aria-pressed", String(known));
        b.classList.toggle("is-known", known);
        b.setAttribute("aria-label", t.chipAria(data.chips[i], known));
        b.querySelector(".ga-chip-state").textContent = known ? t.chipKnown : t.chipUnfolded;
      });
      root.querySelectorAll("[data-preset]").forEach(b =>
        b.setAttribute("aria-pressed", String(data.presets[b.dataset.preset] === mask)));
      root.querySelector(".ga-cutcount").textContent = t.steps(data.cuts[mask].count);
      root.dataset.cut = data.chips.map((c, i) => mask >> i & 1 ? "1" : "0").join("");
    };
    setCut(st.mask);
    const render = () => {
      root.dataset.mode = st.mode;
      root.querySelector(".ga-stage-lockstep").hidden = st.mode !== "lockstep";
      root.querySelector(".ga-stage-zoom").hidden = st.mode !== "zoom";
      root.querySelectorAll(".ga-mode").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.mode === st.mode)));
      if (st.mode === "zoom") renderZoom(root, st); else renderLockstep(root, st);
      root.classList.toggle("is-playing", st.playing);
      root.querySelector(".ga-play").setAttribute("aria-label", st.playing ? t.pause : t.play);
    };
    const stop = () => { st.playing = false; clearTimeout(st.timer); st.timer = null; render(); };
    const delay = () => {
      let ms = TICK;
      if (st.frame >= st.last()) ms = END_PAUSE;
      else if (st.mode === "lockstep" && st.frame > 0 && st.model.fine[st.frame - 1] &&
        st.model.lastFine[0][st.model.fine[st.frame - 1].owner[0]] === st.frame - 1) ms += BAND_PAUSE;
      return ms / st.speed;
    };
    const tick = () => {
      if (!st.playing) return;
      st.frame = st.frame >= st.last() ? 0 : st.frame + 1;
      render();
      st.timer = setTimeout(tick, delay());
    };
    const play = () => {
      if (st.playing) return;
      st.manual = false;
      st.playing = true;
      if (st.frame >= st.last()) st.frame = 0;
      render();
      st.timer = setTimeout(tick, st.frame === 0 ? 500 / st.speed : delay());
    };
    const go = f => { st.manual = false; st.frame = Math.max(0, Math.min(st.last(), f)); render(); };

    root.querySelector(".ga-play").addEventListener("click", () => { st.userTouched = true; st.playing ? stop() : play(); });
    root.querySelector(".ga-back").addEventListener("click", () => { st.userTouched = true; stop(); go(st.frame - 1); });
    root.querySelector(".ga-fwd").addEventListener("click", () => { st.userTouched = true; stop(); go(st.frame + 1); });
    root.querySelector(".ga-range").addEventListener("input", e => { st.userTouched = true; stop(); go(Number(e.target.value)); });
    root.querySelector(".ga-speed").addEventListener("click", e => {
      st.speed = SPEEDS[(SPEEDS.indexOf(st.speed) + 1) % SPEEDS.length];
      e.currentTarget.textContent = (st.speed === 0.5 ? "½" : st.speed) + "×";
    });
    root.querySelectorAll(".ga-mode").forEach(b => b.addEventListener("click", () => {
      if (st.mode === b.dataset.mode) return;
      const wasPlaying = st.playing;
      stop();
      st.mode = b.dataset.mode;
      st.manual = false;
      st.frame = reduced() ? st.last() : 0;
      render();
      if (wasPlaying && !reduced()) play();
    }));
    // A new cut shows its whole derivation at once; play runs it again step by step.
    const chooseCut = mask => {
      st.userTouched = true;
      stop();
      setCut(mask);
      st.mode = "lockstep";
      st.manual = false;
      st.frame = st.last();
      render();
    };
    root.querySelectorAll("[data-chip]").forEach(b => b.addEventListener("click", () =>
      chooseCut(st.mask ^ (1 << Number(b.dataset.chip)))));
    root.querySelectorAll("[data-preset]").forEach(b => b.addEventListener("click", () =>
      chooseCut(data.presets[b.dataset.preset])));
    root.querySelector(".ga-stage-zoom").addEventListener("click", e => {
      const btn = e.target.closest("[data-zopen]");
      if (!btn) return;
      stop();
      if (!st.manual) {
        st.manual = true;
        st.manualOpen = new Set(st.zmodel.frames[st.frame].open);
      }
      const key = btn.dataset.zopen;
      if (st.manualOpen.has(key)) {
        // Closing a step also closes everything opened inside it.
        root.querySelectorAll('[data-zkids="' + key + '"] [data-zkids]').forEach(el => st.manualOpen.delete(el.dataset.zkids));
        st.manualOpen.delete(key);
      } else st.manualOpen.add(key);
      render();
    });

    const frozen = p.t !== null && p.t !== undefined && p.t !== "";
    if (frozen) {
      root.classList.add("is-frozen");
      st.frame = Math.max(0, Math.min(st.last(), parseInt(p.t, 10) || 0));
      render();
    } else if (reduced()) {
      st.frame = st.last();
      render();
    } else {
      render();
      // Autoplay once the figure is on screen; pause when it leaves.
      if ("IntersectionObserver" in window) {
        new IntersectionObserver(entries => entries.forEach(en => {
          if (en.isIntersecting && !st.userTouched) play();
          else if (!en.isIntersecting && st.playing) stop();
        }), { threshold: 0.35 }).observe(root);
      } else play();
    }
    root.dataset.ready = "true";
  }

  function init() {
    document.querySelectorAll(".op-granim:not([data-ready])").forEach(load);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
  if (window.document$) window.document$.subscribe(init);
}());
