(function () {
  "use strict";

  const STR = {
    en: {
      example: "Example", granularity: "Granularity", graph: "Dependency graph", derivation: "Derivation",
      knownLayers: "Known layers: below", finest: "Finest", coarsest: "Coarsest", custom: "custom",
      steps: "steps", expand: "expand", eval: "eval", atom: "atom", undefined: "undefined",
      branch: "branch", else: "else", if: "if", inlined: "inlined", sympy: "SymPy",
      proved: "proved by z3", refuted: "refuted at", bounded: "undecided by z3, equal on",
      recursive: "uses recursion: no SymPy form", formula: "Formula", behaviour: "Behaviour", uses: "Uses",
      unfolded: "unfolded", known: "known", layer: "layer", operator: "Operator", values: "values",
      branchPath: "branch path", self: "self", above: "above", loading: "Loading",
      error: "Could not load this example.", range: "from", to: "to", nanCondition: "NaN condition",
      noBranch: "no matching branch", open: "Open derivation", close: "Close derivation",
      simple: "Substitution", recursiveKind: "Recursion", branchKind: "Branch", vs: "vs",
      value: "value", inRange: "in",
      hintSlider: "Drag to make whole layers known at once. Finest unfolds everything; Coarsest computes each application in one step.",
      hintGraph: "Click an operator to switch it between known (dashed, one step) and unfolded (filled). Any combination gives a checked derivation."
    },
    zh: {
      example: " ", granularity: " ", graph: " ", derivation: " ",
      knownLayers: " ", finest: " ", coarsest: " ", custom: " ",
      steps: " ", expand: " ", eval: " ", atom: " ", undefined: " ",
      branch: " ", else: " ", if: " ", inlined: " ", sympy: "SymPy",
      proved: "z3  ", refuted: " ", bounded: "z3  ",
      recursive: "  SymPy  ", formula: " ", behaviour: " ", uses: " ",
      unfolded: " ", known: " ", layer: " ", operator: " ", values: " ",
      branchPath: " ", self: " ", above: " ", loading: " ",
      error: " ", range: " ", to: " ", nanCondition: "NaN  ",
      noBranch: " ", open: " ", close: " ",
      simple: " ", recursiveKind: " ", branchKind: " ", vs: " ",
      value: " ", inRange: " ",
      hintSlider: " ",
      hintGraph: " "
    }
  };

  const escape = value => String(value).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  })[c]);
  const safeKind = kind => ["base", "simple", "branch", "recursive"].includes(kind) ? kind : "base";
  const valueText = (value, symbols) => value === null ? symbols.nan : String(value);

  // The same bracket decision as ExpressionRenderer.minimal.
  function needsBrackets(child, parent, side) {
    if (parent.n_ary !== 2) return true;
    if (child.priority === null || parent.priority === null) return true;
    if (child.priority !== parent.priority) return child.priority < parent.priority;
    if (parent.associativity === "left") return side === "right";
    if (parent.associativity === "right") return side === "left";
    return true;
  }

  function renderTree(node, operators, symbols, hitPath, html) {
    const put = html ? escape : String;
    function walk(part, parent, side, path) {
      let out;
      if (Object.prototype.hasOwnProperty.call(part, "num")) {
        out = put(valueText(part.num, symbols));
        if (part.num !== null && part.num < 0 && parent) {
          out = put(symbols.left_paren) + out + put(symbols.right_paren);
        }
      } else if (Object.prototype.hasOwnProperty.call(part, "var")) {
        out = put(part.var);
      } else {
        const op = operators[part.op];
        if (!op) throw new Error("Unknown operator: " + part.op);
        if (op.n_ary === 2) {
          out = walk(part.args[0], op, "left", path.concat(0)) + " " + put(op.symbol) + " " +
            walk(part.args[1], op, "right", path.concat(1));
        } else {
          const arg = walk(part.args[0], op, null, path.concat(0));
          out = op.position === "postfix" ? arg + " " + put(op.symbol) : put(op.symbol) + " " + arg;
        }
        if (parent && (op.n_ary !== 2 || needsBrackets(op, parent, side))) {
          out = put(symbols.left_paren) + out + put(symbols.right_paren);
        }
      }
      if (html && hitPath && path.length === hitPath.length && path.every((v, i) => v === hitPath[i])) {
        out = '<span class="og-hit">' + out + "</span>";
      }
      return out;
    }
    return walk(node, null, null, []);
  }

  // Return a new tree, preserving the expression outside the rewrite path.
  function replaceAt(node, path, replacement) {
    if (!path.length) return replacement;
    if (!node.args) throw new Error("Invalid rewrite path");
    const args = node.args.slice();
    args[path[0]] = replaceAt(args[path[0]], path.slice(1), replacement);
    return { op: node.op, args: args };
  }

  // Port of flatten_view: splice child steps, then replay on the root source.
  function flatten(data, unfolded, nodeId) {
    const nodes = data.tree.nodes;
    const root = nodes[nodeId || data.tree.root];
    const collected = [];
    function collect(node, prefix, base) {
      node.steps.forEach(step => {
        const path = prefix.concat(step.path);
        const depth = base + step.depth;
        if (step.kind === "eval" && step.child !== null && unfolded.has(step.operator)) {
          const child = nodes[step.child];
          if (!child) throw new Error("Missing child: " + step.child);
          collect(child, path, depth);
        } else {
          collected.push({ step: step, path: path, depth: depth, child: step.child });
        }
      });
    }
    collect(root, [], 0);
    let current = root.source;
    return collected.map(item => {
      current = replaceAt(current, item.path, item.step.after);
      return Object.assign({}, item, { expressionAfter: current });
    });
  }

  function cutSet(data, level) {
    return new Set(data.graph.filter(op => op.layer >= level).map(op => op.id));
  }

  function cutLevel(data, unfolded) {
    for (let level = 0; level <= data.top_layer + 1; level++) {
      const expected = cutSet(data, level);
      if (expected.size === unfolded.size && [...expected].every(id => unfolded.has(id))) return level;
    }
    return null;
  }

  function checkCut(data, level) {
    const view = flatten(data, cutSet(data, level));
    const check = data.checks.find(item => item.known_layers === level);
    if (!check || check.lines.length !== view.length) return false;
    return view.every((item, i) => item.step.kind === check.kinds[i] &&
      renderTree(item.expressionAfter, data.tree.operators, data.symbols, null, false) === check.lines[i]);
  }

  function section(title, content, extra) {
    return '<section class="og-section ' + (extra || "") + '"><h3 class="og-heading">' +
      escape(title) + "</h3>" + content + "</section>";
  }

  function stepKind(step, data) {
    return step.kind === "eval" && data.tree.operators[step.operator].kind === "base" ? "atom" : step.kind;
  }

  function stepRows(data, view, state, prefix) {
    const t = state.t;
    const operators = data.tree.operators;
    const symbols = data.symbols;
    return view.map((item, index) => {
      const step = item.step;
      const kind = stepKind(step, data);
      const op = operators[step.operator];
      const key = prefix + "/" + index;
      const open = state.open.has(key);
      const hasChild = step.kind === "eval" && item.child !== null;
      const chip = t[kind] + (hasChild ? " " + op.symbol : "");
      const colorKind = kind === "eval" ? safeKind(op.kind) : kind;
      const condition = step.kind === "expand" && step.condition !== null ?
        '<div class="og-condition">' + escape(t.branch + " " + (step.branch + 1) + ": " + step.condition) + "</div>" : "";
      const expression = renderTree(item.expressionAfter, operators, symbols, item.path, true);
      let nested = "";
      if (hasChild && open) {
        const child = data.tree.nodes[item.child];
        if (!child) throw new Error("Missing child: " + item.child);
        let current = child.source;
        const local = child.steps.map(s => {
          current = replaceAt(current, s.path, s.after);
          return { step: s, path: s.path, depth: s.depth, child: s.child, expressionAfter: current };
        });
        nested = '<div class="og-nested"><div class="og-nested-title">' + escape(child.text) +
          '</div><ol class="og-list">' + stepRows(data, local, state, key) + "</ol></div>";
      }
      const disclose = hasChild ? '<button type="button" class="og-disclose" data-og-open="' +
        escape(key) + '" aria-label="' + escape(open ? t.close : t.open) + '" aria-expanded="' + open +
        '">' + (open ? "▾" : "▸") + "</button>" : "";
      const rowAttrs = hasChild ? ' role="button" tabindex="0" data-og-open="' + escape(key) +
        '" aria-expanded="' + open + '"' : "";
      return '<li class="og-step og-' + colorKind + '"><div class="og-step-row"' + rowAttrs + ">" +
        disclose + '<span class="og-chip">' + escape(chip) + '</span><span class="og-line">= ' +
        expression + "</span></div>" + condition + nested + "</li>";
    }).join("");
  }

  function derivationHtml(data, view, state) {
    const source = data.tree.nodes[data.tree.root].source;
    return '<ol class="og-list"><li class="og-start"><span class="og-line">' +
      renderTree(source, data.tree.operators, data.symbols, null, true) + "</span></li>" +
      stepRows(data, view, state, "root") + "</ol>";
  }

  function graphHtml(data, state) {
    const t = state.t;
    const graph = data.graph;
    const positions = {};
    const width = 600, height = 232;
    for (let layer = data.top_layer; layer >= 0; layer--) {
      const row = graph.filter(op => op.layer === layer);
      const y = 35 + (data.top_layer - layer) * (166 / Math.max(1, data.top_layer));
      row.forEach((op, i) => { positions[op.id] = { x: 68 + (i + 0.5) * 516 / row.length, y: y }; });
    }
    const edges = graph.flatMap(op => (op.uses || []).filter(id => positions[id] && id !== op.id).map(id => {
      const a = positions[op.id], b = positions[id];
      const bend = a.y === b.y ? (a.x < b.x ? -20 : 20) : (b.y - a.y) * 0.48;
      return '<path class="og-edge" d="M ' + a.x + " " + (a.y + 14) + " C " + a.x + " " +
        (a.y + bend) + ", " + b.x + " " + (b.y - bend) + ", " + b.x + " " + (b.y - 14) + '"/>';
    })).join("");
    const labels = Array.from({ length: data.top_layer + 1 }, (_, n) => {
      const layer = data.top_layer - n;
      const y = 35 + n * (166 / Math.max(1, data.top_layer));
      return '<text class="og-layer-label" x="3" y="' + (y + 4) + '">' +
        escape(t.layer + " " + layer) + "</text>";
    }).join("");
    const nodes = graph.map(op => {
      const p = positions[op.id];
      const unfolded = state.unfolded.has(op.id);
      const selected = op.id === state.selected;
      const loop = op.kind === "recursive" ? '<path class="og-loop" d="M ' + (p.x + 24) + " " +
        (p.y - 7) + " C " + (p.x + 42) + " " + (p.y - 38) + ", " + (p.x - 30) + " " +
        (p.y - 37) + ", " + (p.x - 24) + " " + (p.y - 8) + '"/>' : "";
      return '<g class="og-node og-' + safeKind(op.kind) + (unfolded ? " og-unfolded" : " og-known") +
        (selected ? " og-selected" : "") + '" role="button" tabindex="0" data-og-op="' + escape(op.id) +
        '" aria-label="' + escape(op.form + ", " + (unfolded ? t.unfolded : t.known)) + '"><title>' +
        escape(op.form) + '</title><rect x="' + (p.x - 28) + '" y="' + (p.y - 14) +
        '" width="56" height="28" rx="8"/><text x="' + p.x + '" y="' + (p.y + 4) +
        '">' + escape(op.symbol) + "</text>" + loop + "</g>";
    }).join("");
    const kindLabel = { simple: t.simple, branch: t.branchKind, recursive: t.recursiveKind };
    const legend = ["simple", "branch", "recursive"].map(kind =>
      '<span class="og-legend-kind og-' + kind + '">' + escape(kindLabel[kind]) + "</span>").join("");
    return '<svg class="og-graph" viewBox="0 0 ' + width + " " + height + '" role="group" aria-label="' +
      escape(t.graph) + '">' + edges + labels + nodes + '</svg><div class="og-legend">' + legend +
      '<span class="og-legend-state og-legend-unfolded">' + escape(t.unfolded) + '</span>' +
      '<span class="og-legend-state og-legend-known">' + escape(t.known) + "</span></div>";
  }

  function pathText(path, t) {
    return path.map(([item, count]) => {
      const label = typeof item === "number" ? t.branch + " " + item :
        t.undefined + " (" + (item === "nan_condition" ? t.nanCondition :
          item === "no_branch" ? t.noBranch : String(item)) + ")";
      return label + (count > 1 ? " ×" + count : "");
    }).join(", ");
  }

  function valueList(values, symbols) {
    const shown = values.length > 6 ? values.slice(0, 6).map(v => valueText(v, symbols)).concat("…", valueText(values[values.length - 1])) :
      values.map(v => valueText(v, symbols));
    return shown.join(", ");
  }

  function paletteFor(table) {
    const items = table.n_ary === 1 ? table.rows : table.blocks.flatMap(block => block.runs);
    const paths = [];
    items.forEach(item => {
      const key = JSON.stringify(item.path);
      if (!paths.some(p => p.key === key)) paths.push({ key: key, path: item.path });
    });
    return paths;
  }

  function colourClass(path, palette) {
    const index = palette.findIndex(p => p.key === JSON.stringify(path));
    return "og-p" + (index % 12);
  }

  function behaviourHtml(data, explain, t) {
    const table = explain.table, symbols = data.symbols, palette = paletteFor(table);
    let chart;
    if (table.n_ary === 1) {
      const strip = table.rows.map(row => Array.from({ length: row.to - row.from + 1 }, (_, i) =>
        '<span class="og-strip-cell ' + colourClass(row.path, palette) + '" style="flex:1" title="' +
        escape("a = " + (row.from + i) + ": " + pathText(row.path, t)) + '"></span>').join("")).join("");
      const rows = table.rows.map(row => '<tr><td>' + escape(row.from === row.to ? String(row.from) :
        row.from + ".." + row.to) + '</td><td><span class="og-path-dot ' + colourClass(row.path, palette) +
        '"></span>' + escape(pathText(row.path, t)) + '</td><td>' + escape(valueList(row.values, symbols)) +
        "</td></tr>").join("");
      chart = '<div class="og-strip" aria-label="' + escape(t.behaviour) + '">' + strip +
        '</div><div class="og-table-wrap"><table class="og-table"><thead><tr><th>a</th><th>' +
        escape(t.branchPath) + '</th><th>' + escape(t.values) + '</th></tr></thead><tbody>' + rows +
        "</tbody></table></div>";
    } else {
      const rows = table.blocks.map(block => {
        const height = Math.max(3, (block.to - block.from + 1) * 5);
        const cells = block.runs.map(run => {
          const len = run.to - run.from + 1;
          const v = run.distinct === 1 ? t.value + " " + valueText(run.value, symbols) :
            run.distinct + " " + t.values + " " + t.inRange + " [" + valueText(run.min, symbols) +
              ", " + valueText(run.max, symbols) + "]";
          const tip = "a = " + block.from + (block.from === block.to ? "" : ".." + block.to) +
            ", b = " + run.from + (run.from === run.to ? "" : ".." + run.to) + ": " +
            pathText(run.path, t) + ", " + v;
          return '<span class="og-map-cell ' + colourClass(run.path, palette) + '" style="flex:' + len +
            '" title="' + escape(tip) + '"></span>';
        }).join("");
        return '<div class="og-map-row" style="height:' + height + 'px">' + cells + "</div>";
      }).join("");
      chart = '<div class="og-map-layout"><div class="og-axis-a">a<br>' + escape(table.a[0]) +
        '<br>..' + escape(table.a[1]) + '</div><div class="og-map-body"><div class="og-map">' +
        rows + '</div><div class="og-axis-b">b: ' + escape(table.b[0]) + ".." + escape(table.b[1]) +
        "</div></div></div>";
    }
    const legend = palette.map((entry, i) => '<span class="og-map-legend-item"><i class="og-path-dot og-p' +
      (i % 12) + '"></i>' + escape(pathText(entry.path, t)) + "</span>").join("");
    return chart + '<div class="og-map-legend">' + legend + "</div>";
  }

  function checkBadge(check, t, symbols) {
    if (!check) return "";
    let label = "", status = check.status;
    if (status === "proved") label = t.proved;
    else if (status === "bounded") {
      const bounds = check.range || check.bounds || [check.lo, check.hi];
      label = t.bounded + " [" + bounds.map(v => valueText(v, symbols)).join(", ") + "]";
    } else if (status === "refuted") {
      const at = check.counterexample || check.inputs || {};
      const entries = Object.entries(at).map(([key, value]) => key + " = " + valueText(value, symbols));
      const left = check.left_value !== undefined ? check.left_value : check.left;
      const right = check.right_value !== undefined ? check.right_value : check.right;
      label = t.refuted + " " + entries.join(", ") + ": " + valueText(left, symbols) +
        " " + t.vs + " " + valueText(right, symbols);
    } else return "";
    return '<span class="og-check og-check-' + escape(status) + '">' + escape(label) + "</span>";
  }

  function formulaHtml(data, explain, t) {
    const branches = explain.formula.branches;
    const rows = branches.map(branch => {
      const condition = branches.length === 1 ? "" : branch.else ? " " + t.else :
        branch.condition !== null ? " " + t.if + " " + branch.condition : "";
      let lines = '<div class="og-formula-main"><span class="og-branch-label">' +
        escape(t.branch + " " + (branch.index + 1) + condition) + '</span><code>' +
        escape(branch.body) + "</code></div>";
      if (branch.inlined !== null) lines += '<div class="og-formula-sub">' + escape(t.inlined) +
        ': <code>' + escape(branch.inlined) + "</code>" + checkBadge(branch.inlined_check, t, data.symbols) + "</div>";
      if (branch.simplified !== null) lines += '<div class="og-formula-sub">' + escape(t.sympy) +
        ': <code>' + escape(branch.simplified) + "</code>" +
        checkBadge(branch.simplified_check, t, data.symbols) + "</div>";
      return '<div class="og-formula-row">' + lines + "</div>";
    }).join("");
    return rows + (explain.formula.recursive ? '<p class="og-muted">' + escape(t.recursive) + "</p>" : "");
  }

  function outlineHtml(node, t, root) {
    const label = '<span class="og-kind-dot og-' + safeKind(node.kind) + '"></span><span class="' +
      (node.repeat ? "og-repeat" : "") + '">' + escape(node.form) + "</span>" +
      (node.self ? ' <span class="og-muted">(' + escape(t.self) + ")</span>" : "") +
      (node.repeat ? ' <span class="og-muted">(' + escape(t.above) + ")</span>" : "");
    const children = node.uses && node.uses.length ? "<ul>" +
      node.uses.map(child => outlineHtml(child, t, false)).join("") + "</ul>" : "";
    return root ? label + children : "<li>" + label + children + "</li>";
  }

  function explanationHtml(data, state) {
    const t = state.t;
    const explain = data.explain[state.selected];
    if (!explain) return "";
    const form = data.graph.find(op => op.id === state.selected).form;
    const kindLabel = { simple: t.simple, branch: t.branchKind, recursive: t.recursiveKind };
    return '<div class="og-explain-head"><strong>' + escape(form) + '</strong><span class="og-kind-chip og-' +
      safeKind(explain.kind) + '">' + escape(kindLabel[explain.kind]) + '</span><span class="og-muted">' +
      escape(t.layer + " " + explain.layer) + '</span></div><div class="og-definition"><code>' +
      escape(explain.definition) + "</code></div>" +
      section(t.formula, formulaHtml(data, explain, t), "og-subsection") +
      section(t.behaviour, behaviourHtml(data, explain, t), "og-subsection") +
      section(t.uses, '<div class="og-outline">' + outlineHtml(explain.outline, t, true) + "</div>", "og-subsection");
  }

  function initialSelection(data) {
    const source = data.tree.nodes[data.tree.root].source;
    if (source.op && data.explain[source.op]) return source.op;
    return data.graph.find(op => op.layer === data.top_layer).id;
  }

  function shell(root, state) {
    const data = state.data[state.index], t = state.t;
    const tabs = state.data.map((item, index) => '<button type="button" class="og-tab' +
      (index === state.index ? " og-active" : "") + '" data-og-tab="' + index + '" aria-pressed="' +
      (index === state.index) + '">' + escape(item.tree.nodes[item.tree.root].text) + "</button>").join("");
    const options = data.graph.map(op => '<option value="' + escape(op.id) + '"' +
      (op.id === state.selected ? " selected" : "") + ">" + escape(op.form) + "</option>").join("");
    root.innerHTML = section(t.example, '<div class="og-tabs">' + tabs + '</div><div class="og-example-line"><code>' +
      renderTree(data.tree.nodes[data.tree.root].source, data.tree.operators, data.symbols, null, true) +
      " = " + escape(valueText(data.tree.nodes[data.tree.root].value, data.symbols)) + "</code></div>") +
      section(t.granularity, '<div class="og-controls"><label class="og-range-label" for="og-range-' +
        state.uid + '">' + escape(t.knownLayers) + ' <output class="og-level"></output></label>' +
        '<input id="og-range-' + state.uid + '" class="og-range" type="range" min="0" max="' +
        (data.top_layer + 1) + '" step="1" value="' + state.slider + '" data-og-range>' +
        '<button type="button" data-og-finest>' + escape(t.finest) + '</button><button type="button" data-og-coarsest>' +
        escape(t.coarsest) + '</button></div><p class="og-hint">' + escape(t.hintSlider) + '</p>' +
        '<div class="og-summary" aria-live="polite"></div>') +
      section(t.graph, '<p class="og-hint">' + escape(t.hintGraph) + '</p><div class="og-graph-wrap"></div>') +
      section(t.derivation, '<div class="og-derivation"></div>') +
      section(t.operator, '<label class="og-select-label">' + escape(t.operator) +
        ' <select class="og-select" data-og-select>' + options + '</select></label><div class="og-explanation"></div>');
    const kindLegend = document.createElement("div");
    root.querySelector(".og-graph-wrap").before(kindLegend);
    if (window.KindsLegend) window.KindsLegend.render(kindLegend, {lang: root.dataset.lang});
    updateView(root, state);
    const atomLegend = document.createElement("div");
    atomLegend.className = "og-atoms-legend";
    root.querySelector(".og-example-line").after(atomLegend);
    window.OpulseAtoms.legend(atomLegend, "integer", JSON.stringify(data.graph) + JSON.stringify(data.explain));
    root.querySelector(".og-explanation").innerHTML = explanationHtml(data, state);
  }

  function updateView(root, state) {
    const data = state.data[state.index], t = state.t;
    const view = flatten(data, state.unfolded);
    const counts = { expand: 0, eval: 0, atom: 0, undefined: 0 };
    view.forEach(item => { counts[stepKind(item.step, data)]++; });
    const summary = view.length + " " + t.steps + ": " + counts.expand + " " + t.expand + ", " +
      counts.eval + " " + t.eval + ", " + counts.atom + " " + t.atom +
      (counts.undefined ? ", " + counts.undefined + " " + t.undefined : "");
    root.querySelector(".og-summary").textContent = summary;
    root.querySelector(".og-level").textContent = state.cut === null ?
      state.slider + " (" + t.custom + ")" : String(state.cut);
    root.querySelector(".og-graph-wrap").innerHTML = graphHtml(data, state);
    const derivation = root.querySelector(".og-derivation");
    const scroll = derivation.scrollTop;
    derivation.innerHTML = derivationHtml(data, view, state);
    derivation.scrollTop = scroll;
    if (state.cut !== null) {
      const ok = checkCut(data, state.cut);
      root.dataset.check = ok ? "ok" : "mismatch";
      if (!ok) console.warn("Opulse granularity check mismatch", state.index, state.cut);
    } else delete root.dataset.check;
  }

  let nextUid = 0;
  function bind(root, state) {
    const on = (type, handler) => root.addEventListener(type, event => {
      try { handler(event); } catch (error) { state.fail(error); }
    });
    on("click", event => {
      const tab = event.target.closest("[data-og-tab]");
      if (tab) {
        state.index = Number(tab.dataset.ogTab);
        const data = state.data[state.index];
        state.slider = Math.min(state.slider, data.top_layer + 1);
        state.cut = state.slider;
        state.unfolded = cutSet(data, state.cut);
        state.selected = initialSelection(data);
        state.open.clear();
        shell(root, state);
        return;
      }
      const special = event.target.closest("[data-og-finest], [data-og-coarsest]");
      if (special) {
        state.slider = special.hasAttribute("data-og-finest") ? 0 : state.data[state.index].top_layer + 1;
        state.cut = state.slider;
        state.unfolded = cutSet(state.data[state.index], state.cut);
        root.querySelector("[data-og-range]").value = state.slider;
        updateView(root, state);
        return;
      }
      const opener = event.target.closest("[data-og-open]");
      if (opener) {
        const key = opener.dataset.ogOpen;
        if (state.open.has(key)) state.open.delete(key); else state.open.add(key);
        updateView(root, state);
        return;
      }
      const node = event.target.closest("[data-og-op]");
      if (node) {
        const id = node.dataset.ogOp;
        if (state.unfolded.has(id)) state.unfolded.delete(id); else state.unfolded.add(id);
        state.selected = id;
        state.cut = cutLevel(state.data[state.index], state.unfolded);
        if (state.cut !== null) {
          state.slider = state.cut;
          root.querySelector("[data-og-range]").value = state.slider;
        }
        updateView(root, state);
        root.querySelector("[data-og-select]").value = id;
        root.querySelector(".og-explanation").innerHTML = explanationHtml(state.data[state.index], state);
      }
    });
    on("keydown", event => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const target = event.target;
      if (target.matches(".og-node, .og-step-row[data-og-open]")) {
        event.preventDefault();
        target.click();
      }
    });
    on("input", event => {
      if (!event.target.matches("[data-og-range]")) return;
      state.slider = Number(event.target.value);
      state.cut = state.slider;
      state.unfolded = cutSet(state.data[state.index], state.cut);
      updateView(root, state);
    });
    on("change", event => {
      if (!event.target.matches("[data-og-select]")) return;
      state.selected = event.target.value;
      root.querySelector(".og-graph-wrap").innerHTML = graphHtml(state.data[state.index], state);
      root.querySelector(".og-explanation").innerHTML = explanationHtml(state.data[state.index], state);
    });
  }

  async function load(root) {
    root.dataset.ready = "loading";
    const fallback = root.innerHTML;
    const t = STR[root.dataset.lang === "zh" ? "zh" : "en"];
    const files = (root.dataset.files || "").trim().split(/\s+/).filter(Boolean);
    const base = root.dataset.base || "";
    const fail = error => {
      console.warn("Opulse granularity error", error);
      root.innerHTML = '<p class="og-error">' + escape(t.error) + "</p>" + fallback;
      root.dataset.ready = "error";
    };
    try {
      if (!files.length) throw new Error("No granularity files");
      const get = async file => {
        const response = await fetch(base + file);
        if (!response.ok) throw new Error("HTTP " + response.status + ": " + file);
        const data = await response.json();
        if (data.tree.schema !== "opulse.derivation/1") throw new Error("Unsupported derivation schema");
        return data;
      };
      const first = await get(files[0]);
      const state = { uid: ++nextUid, data: [first], index: 0, t: t, slider: first.top_layer + 1,
        cut: first.top_layer + 1, unfolded: new Set(), selected: initialSelection(first), open: new Set(),
        fail: fail };
      bind(root, state);
      shell(root, state);
      root.dataset.ready = "true";
      let allOk = true;
      const verify = (data, file) => {
        for (let level = 0; level <= data.top_layer + 1; level++) {
          if (!checkCut(data, level)) {
            allOk = false;
            console.warn("Opulse granularity check mismatch", file, level);
          }
        }
      };
      verify(first, files[0]);
      for (let i = 1; i < files.length; i++) {
        const data = await get(files[i]);
        state.data.push(data);
        verify(data, files[i]);
        const tabs = root.querySelector(".og-tabs");
        tabs.insertAdjacentHTML("beforeend", '<button type="button" class="og-tab" data-og-tab="' + i +
          '" aria-pressed="false">' + escape(data.tree.nodes[data.tree.root].text) + "</button>");
      }
      root.dataset.checkAll = allOk ? "ok" : "mismatch";
    } catch (error) {
      fail(error);
    }
  }

  function init() {
    document.querySelectorAll(".op-gran:not([data-ready])").forEach(load);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
  if (window.document$) window.document$.subscribe(init);
  window.OpulseGranularity = { renderTree: renderTree, flatten: flatten, checkCut: checkCut };
}());
