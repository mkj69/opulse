/* Shared scale-example API (ES2017, no dependencies).
 * OpulseScales.dataRoot() -> URL; loadIndex() -> Promise<index> (cached);
 * loadExample(scale, id), loadExampleAt(url) -> Promise<Example>.
 * Example: header, operators, cutTable; cutBelowLayer(L) and cutFromSet(Set)
 * return reusable cut predicates. ensureLayers(layers) -> Promise<void> loads all
 * parts of each requested layer. count(cut) -> Promise<number> counts flattened
 * steps; page(cut, offset, size) and fullPage(offset, size) return slices. node(i)
 * -> Promise<node>; children(i) -> Promise<{stepIndex,node}[]> loads one level.
 * Nodes have {index,op,operator,inputs,value,steps,full}; steps have
 * {index,kind,op,before,after,condition,child,focusPath}. Flattened steps
 * additionally have {depth,path}, where path is the root-to-node index chain.
 * fmt(n), layerLabel(layer), renderStepList(container, example, cut, opts),
 * renderOperatorChips(container, operators, opts), renderTree(container,
 * example, cut) are UI helpers. Renderers return a handle with destroy().
 */
(function () {
  "use strict";
  const scriptURL = document.currentScript && document.currentScript.src;
  // Both builds copy assets beside this script, including builds under /zh/.
  const rootURL = scriptURL ? new URL("../data/scales/", scriptURL) : new URL("assets/data/scales/", document.baseURI);
  const zh = () => (document.documentElement.lang || "").toLowerCase().startsWith("zh");
  const words = {
    en: { first: "First", previous: "Previous", next: "Next", last: "Last", jump: "Go to step", page: "Page", go: "Go",
      steps: (a, b, n) => `Steps ${a}–${b} of ${n}`, search: "Search operators", layer: "Layer", more: "Show more",
      open: "Open derivation", close: "Close derivation", limit: "Collapse branches to open more steps", error: "Could not load steps" },
    zh: { first: "首页", previous: "上一页", next: "下一页", last: "末页", jump: "跳转到步骤", page: "页码", go: "跳转",
      steps: (a, b, n) => `第 ${a} 至 ${b} 步，共 ${n} 步`, search: "搜索算子", layer: "层", more: "显示更多",
      open: "展开推导", close: "收起推导", limit: "请先收起分支，再展开更多步骤", error: "无法加载步骤" }
  };
  const t = () => words[zh() ? "zh" : "en"];
  const kindNames = ["eval", "expand", "undefined"];
  let indexPromise;
  function dataRoot() { return new URL(rootURL.href); }
  async function getJSON(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Scale data: ${response.status} ${url}`);
    return response.json();
  }
  function loadIndex() {
    if (!indexPromise) indexPromise = getJSON(new URL("index.json", rootURL)).catch(error => { indexPromise = null; throw error; });
    return indexPromise;
  }
  function loadExample(scale, id) {
    if (!/^[\w-]+$/.test(scale) || !/^[\w-]+$/.test(id)) return Promise.reject(new Error("Invalid scale or example ID"));
    const url = new URL(`${scale}/${id}.json`, rootURL);
    return getJSON(url).then(data => new Example(data, url));
  }
  function loadExampleAt(url) {
    const indexURL = new URL(url, document.baseURI);
    return getJSON(indexURL).then(data => new Example(data, indexURL));
  }
  function fmt(n) { return Number(n).toLocaleString(zh() ? "zh-CN" : "en-US"); }
  function layerLabel(layer) { return zh() ? `第 ${fmt(layer)} 层` : `${t().layer} ${fmt(layer)}`; }
  function element(tag, className, parent, value) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (value !== undefined) item.textContent = value;
    if (parent) parent.appendChild(item);
    return item;
  }
  function setError(parent, error) { parent.textContent = `${t().error}: ${error.message}`; }
  const symbolPatterns = new WeakMap();
  function richText(value, example) {
    const fragment = document.createDocumentFragment();
    const text = String(value);
    if (!example || !Array.isArray(example.operators)) { fragment.appendChild(document.createTextNode(text)); return fragment; }
    let pattern = symbolPatterns.get(example);
    if (pattern === undefined) {
      const symbols = [...new Set(example.operators.map(op => op.symbol).filter(Boolean))]
        .sort((a, b) => b.length - a.length || a.localeCompare(b));
      pattern = symbols.length ? new RegExp(symbols.map(symbol => symbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "g") : null;
      symbolPatterns.set(example, pattern);
    }
    if (!pattern) { fragment.appendChild(document.createTextNode(text)); return fragment; }
    pattern.lastIndex = 0;
    let cursor = 0, match;
    while ((match = pattern.exec(text))) {
      if (match.index > cursor) fragment.appendChild(document.createTextNode(text.slice(cursor, match.index)));
      element("span", "op-sym", fragment, match[0]);
      cursor = pattern.lastIndex;
    }
    if (cursor < text.length) fragment.appendChild(document.createTextNode(text.slice(cursor)));
    return fragment;
  }

  class Example {
    constructor(data, url) {
      if (data.schema !== "opulse.scale-example/1") throw new Error("Unknown scale example schema");
      this.header = data.header;
      this.operators = data.operators;
      this.cutTable = data.header.cut_table;
      this.root = data.root;
      this.chunks = data.chunks;
      this.strings = data.strings || [];
      this.url = url;
      this._chunks = new Map();
      this._nodes = new Map();
      this._memo = new WeakMap();
    }
    cutBelowLayer(L) {
      if (!Number.isInteger(L) || L < 0) throw new RangeError("Layer must be a nonnegative integer");
      return { known: i => this.operators[i].layer < L, layer: L };
    }
    cutFromSet(indices) {
      const known = new Set(indices);
      return { known: i => known.has(i), indices: known };
    }
    _cut(cut) {
      if (typeof cut === "function") return cut;
      if (cut && typeof cut.known === "function") return cut.known;
      throw new TypeError("Expected a cut from cutBelowLayer or cutFromSet");
    }
    _chunkFor(i) {
      // Chunks are sorted by global node index, including the root as the last chunk.
      let low = 0, high = this.chunks.length - 1;
      while (low <= high) {
        const mid = (low + high) >> 1, part = this.chunks[mid];
        if (i < part.start) high = mid - 1;
        else if (i >= part.end) low = mid + 1;
        else return part;
      }
      throw new RangeError(`Unknown node ${i}`);
    }
    _load(part) {
      if (!this._chunks.has(part.file)) {
        const promise = getJSON(new URL(part.file, this.url)).then(data => {
          const table = Array.isArray(data.strings) ? data.strings : this.strings;
          if (!Array.isArray(data.nodes) || data.nodes.length !== part.end - part.start) throw new Error(`Invalid chunk ${part.file}`);
          data.nodes.forEach((raw, offset) => {
            const index = part.start + offset;
            const steps = raw.steps.map((step, localIndex) => ({
              index: localIndex, kind: kindNames[step[0]], op: this.operators[step[1]], opIndex: step[1], child: step[2],
              before: table[step[3]], after: table[step[4]], condition: step[5] === null ? null : table[step[5]], focusPath: step[6]
            }));
            this._nodes.set(index, { index, op: raw.op, operator: raw.op < 0 ? null : this.operators[raw.op],
              inputs: raw.inputs.map(i => table[i]), value: table[raw.value], steps, full: raw.full });
          });
        }).catch(error => { this._chunks.delete(part.file); throw error; });
        this._chunks.set(part.file, promise);
      }
      return this._chunks.get(part.file);
    }
    async ensureLayers(layers) {
      const wanted = new Set(Array.isArray(layers) ? layers : [layers]);
      await Promise.all(this.chunks.filter(part => wanted.has(part.layer)).map(part => this._load(part)));
    }
    async node(i) {
      if (!this._nodes.has(i)) await this._load(this._chunkFor(i));
      return this._nodes.get(i);
    }
    async children(i) {
      const owner = await this.node(i);
      const result = [];
      for (const step of owner.steps) {
        if (step.child >= 0) result.push({ stepIndex: step.index, node: await this.node(step.child) });
      }
      return result;
    }
    async count(cut) {
      const known = this._cut(cut);
      let memo = this._memo.get(cut);
      if (!memo) { memo = new Map(); this._memo.set(cut, memo); }
      // Iterative postorder. A shared child is counted once in memo and added at every reference.
      const stack = [{ index: this.root, ready: false }];
      while (stack.length) {
        const frame = stack.pop();
        if (memo.has(frame.index)) continue;
        const owner = await this.node(frame.index);
        if (!frame.ready) {
          stack.push({ index: frame.index, ready: true });
          for (const step of owner.steps) {
            if (step.child >= 0 && !known(step.opIndex) && !memo.has(step.child)) stack.push({ index: step.child, ready: false });
          }
        } else {
          let total = 0;
          for (const step of owner.steps) total += step.child >= 0 && !known(step.opIndex) ? memo.get(step.child) : 1;
          memo.set(frame.index, total);
        }
      }
      return memo.get(this.root);
    }
    async page(cut, offset, size) {
      const total = await this.count(cut);
      return this._page(this._cut(cut), this._memo.get(cut), total, offset, size);
    }
    async fullPage(offset, size) {
      // The published DAG stores each node's fully opened length. Reading a
      // page can therefore skip whole branches without loading their chunks.
      const root = await this.node(this.root);
      return this._page(() => false, null, root.full, offset, size);
    }
    async _page(known, memo, total, offset, size) {
      if (!Number.isSafeInteger(offset) || offset < 0 || !Number.isSafeInteger(size) || size < 0) throw new RangeError("Invalid page bounds");
      if (size === 0 || offset >= total) return [];
      const end = Math.min(total, offset + size);
      const rows = [], stack = [{ index: this.root, next: 0, path: [this.root] }];
      let position = 0;
      // Iterative depth-first walk; a memoized subtree count skips pages without building them.
      while (stack.length && position < end) {
        const frame = stack[stack.length - 1], owner = await this.node(frame.index);
        if (frame.next >= owner.steps.length) { stack.pop(); continue; }
        const step = owner.steps[frame.next++];
        if (step.child >= 0 && !known(step.opIndex)) {
          const length = memo ? memo.get(step.child) : (await this.node(step.child)).full;
          if (position + length <= offset) { position += length; continue; }
          stack.push({ index: step.child, next: 0, path: frame.path.concat(step.child) });
        } else {
          if (position >= offset) rows.push({ index: position, kind: step.kind, op: step.op, before: step.before,
            after: step.after, condition: step.condition, depth: frame.path.length - 1, path: frame.path.slice(),
            focusPath: step.focusPath, child: step.child });
          position++;
        }
      }
      return rows;
    }
  }

  function stepRow(parent, step, number, example) {
    const row = element("div", "os-step", parent);
    if (number !== null) element("span", "os-step-number", row, fmt(number));
    const kind = zh() ? { eval: "求值", expand: "展开", undefined: "未定义" }[step.kind] : step.kind;
    const stepKind = element("span", "os-step-kind", row);
    stepKind.appendChild(richText(`${kind} · ${step.op.symbol}`, example));
    if (step.kind === "eval") window.OpulseAtoms.title(stepKind, example.header.world, step.op.symbol, step.op.arity);
    element("code", "os-step-expression", row).appendChild(richText(`${step.before} → ${step.after}`, example));
    if (step.condition) element("span", "os-step-condition", row).appendChild(richText(step.condition, example));
    return row;
  }
  function renderStepList(container, example, cut, opts) {
    opts = opts || {};
    let destroyed = false, viewer = null, pendingStep = 1;
    container.textContent = zh() ? "正在统计步骤…" : "Counting steps…";
    example.count(cut).then(total => {
      if (destroyed) return;
      viewer = window.OpulseStepView.render(container, {
        steps: {count: total, load: (offset, size) => example.page(cut, offset, size)},
        page_size: opts.pageSize || 50, initial: pendingStep - 1, lang: zh() ? "zh" : "en",
        renderValue: value => richText(value, example),
        labels: {describe: step => {
          const line = document.createElement("span");
          line.appendChild(richText((zh() ? {eval: "计算", expand: "展开", undefined: "未定义"}[step.kind] :
            {eval: "Compute", expand: "Unfold", undefined: "Undefined"}[step.kind]) + " · " + step.op.symbol, example));
          if (step.condition) { line.appendChild(document.createTextNode(" · ")); line.appendChild(richText(step.condition, example)); }
          return line;
        }}
      });
    }).catch(error => { if (!destroyed) setError(container, error); });
    return {destroy() { destroyed = true; if (viewer) viewer.destroy(); else container.replaceChildren(); },
      goToStep(n) { pendingStep = n; if (viewer) viewer.goToStep(n); }};
  }

  function renderOperatorChips(container, operators, opts) {
    opts = opts || {};
    container.replaceChildren();
    const search = element("input", "os-chip-search", container);
    search.type = "search"; search.placeholder = t().search; search.setAttribute("aria-label", t().search);
    const groups = element("div", "os-chip-groups", container);
    const byLayer = new Map();
    operators.forEach((op, index) => { if (!byLayer.has(op.layer)) byLayer.set(op.layer, []); byLayer.get(op.layer).push({ op, index }); });
    const layers = [...byLayer.keys()].sort((a, b) => b - a);
    const top = Math.max(1, opts.expandedLayers || 2);
    function paint() {
      const query = search.value.toLocaleLowerCase();
      groups.replaceChildren();
      layers.forEach((layer, rank) => {
        const items = byLayer.get(layer).filter(({ op }) => op.symbol.toLocaleLowerCase().includes(query));
        if (!items.length) return;
        const group = element("details", "os-chip-group", groups);
        group.open = !!query || rank < top;
        element("summary", "", group, `${layerLabel(layer)} · ${fmt(items.length)}`);
        const chips = element("div", "os-chips", group);
        items.forEach(({ op, index }) => {
          const chip = element("span", `os-chip os-kind-${op.kind}`, chips);
          element("span", "op-sym", chip, op.symbol);
          chip.title = `${op.symbol} · ${layerLabel(layer)}`;
          chip.dataset.operatorIndex = String(index);
        });
      });
    }
    search.addEventListener("input", paint); paint();
    return { destroy() { container.replaceChildren(); } };
  }

  function renderTree(container, example, cut) {
    container.replaceChildren();
    let destroyed = false, shown = 0;
    const known = example._cut(cut), maxRows = 250, batch = 50;
    const root = element("div", "os-tree", container);
    async function drawNode(index, target, active) {
      const node = await example.node(index);
      if (destroyed || !active()) return;
      let cursor = 0;
      const rows = element("div", "os-tree-steps", target);
      function append() {
        const end = Math.min(node.steps.length, cursor + batch, cursor + maxRows - shown);
        while (cursor < end) {
          const step = node.steps[cursor++]; shown++;
          const line = element("div", "os-tree-line", rows);
          const row = stepRow(line, step, null, example);
          if (step.child >= 0 && !known(step.opIndex)) {
            const toggle = element("button", "os-tree-toggle", row, t().open);
            toggle.type = "button"; toggle.setAttribute("aria-expanded", "false");
            const branch = element("div", "os-tree-branch", line); branch.hidden = true;
            let loaded = false, token = 0;
            toggle.addEventListener("click", async () => {
              if (!branch.hidden) {
                token++;
                shown -= branch.querySelectorAll(".os-tree-line").length;
                branch.replaceChildren(); branch.hidden = true; loaded = false;
                toggle.textContent = t().open; toggle.setAttribute("aria-expanded", "false"); return;
              }
              if (shown >= maxRows) { element("span", "os-tree-limit", row, t().limit); return; }
              branch.hidden = false; toggle.textContent = t().close; toggle.setAttribute("aria-expanded", "true");
              if (!loaded) {
                loaded = true;
                const request = ++token;
                try { await drawNode(step.child, branch, () => !branch.hidden && token === request); }
                catch (error) { if (!branch.hidden && token === request) setError(branch, error); }
              }
            });
          }
        }
        more.hidden = cursor >= node.steps.length;
        more.textContent = shown >= maxRows ? t().limit : t().more;
        more.disabled = shown >= maxRows;
      }
      const more = element("button", "os-tree-more", target); more.type = "button";
      more.addEventListener("click", append);
      append();
    }
    drawNode(example.root, root, () => true).catch(error => { if (!destroyed) setError(root, error); });
    return { destroy() { destroyed = true; container.replaceChildren(); } };
  }
  window.OpulseScales = { dataRoot, loadIndex, loadExample, loadExampleAt, fmt, layerLabel, richText, renderStepList, renderOperatorChips, renderTree };
}());
