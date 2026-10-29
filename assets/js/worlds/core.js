(function () {
  "use strict";
  const script = document.currentScript;
  const dataRoot = new URL("../../data/worlds/", script.src);
  const codeRoot = new URL("./", script.src);
  const renderers = new Map();
  const extensions = new Map();  // world id or "*" -> [{id, label, label_zh, render}]
  const cache = new Map();
  const esc = value => String(value).replace(/[&<>"']/g, ch => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"}[ch]));
  const zh = () => (document.documentElement.lang || "").startsWith("zh");
  const tr = (english, chinese) => zh() ? chinese : english;
  const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  const api = window.OpulseWorlds = window.OpulseWorlds || {};
  const DIMENSIONS = [
    ["number", "Number", "数"], ["text", "Text", "文本"], ["structure", "Structure", "结构"],
    ["logic", "Logic", "逻辑"], ["order", "Order", "顺序"], ["knowledge", "Knowledge", "知识"],
    ["vision", "Vision", "视觉"], ["sound", "Sound", "声音"], ["action", "Action", "行动"]];
  const KIND = {composition: ["Substitution", "代入", "S"], branching: ["Branch", "分支", "B"],
    recursion: ["Recursion", "递归", "R"]};
  const kindLabel = kind => tr(...(KIND[kind] || [kind, kind]).slice(0, 2));
  const SUB = "₀₁₂₃₄₅₆₇₈₉";
  const SCALAR = ["int", "bool", "str", "nan", "entity", "note", "colour", "direction"];
  const scalar = value => !value || SCALAR.includes(value.t);

  api.register = (name, renderer) => renderers.set(name, renderer);
  // Extra tabs inside a world's panel: extend(world or "*", {tabs: [{id, label, label_zh, render(container, data, ctx)}]}).
  api.extend = (name, extension) => {
    extensions.set(name, [...(extensions.get(name) || []), ...((extension && extension.tabs) || [])]);
    document.dispatchEvent(new CustomEvent("opulse-worlds:extend", {detail: name}));
  };
  api.tr = tr;
  api.valueText = function (value) {
    if (!value || value.t === "nan") return "NaN";
    if (value.t === "str") return JSON.stringify(value.v);
    if (value.t === "bool") return value.v ? "true" : "false";
    if (value.t === "list") return "[" + value.v.map(api.valueText).join(", ") + "]";
    if (value.t === "perm") return "[" + value.v.join(", ") + "]";
    if (value.t === "grid") return value.v.length + "×" + (value.v[0]?.length || 0) + " grid";
    if (value.t === "state") return "state";
    if (typeof value.v === "object") return JSON.stringify(value.v);
    return String(value.v);
  };
  api.fallbackValue = function (el, value) {
    const chip = document.createElement("span");
    chip.className = "ow-chip" + (!value || value.t === "nan" ? " ow-nan" : "");
    chip.textContent = api.valueText(value);
    el.append(chip);
  };
  // Operator names and texts as HTML: subscript indices become one tight <sub> run.
  api.rich = text => esc(text).replace(/[₀-₉]+/g, run => '<sub class="ow-sub">' +
    [...run].map(ch => SUB.indexOf(ch)).join("") + "</sub>");
  const rich = api.rich;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  api.element = element;

  async function fetchJSON(path) {
    const response = await fetch(new URL(path, dataRoot));
    if (!response.ok) throw new Error("Could not load " + path);
    return response.json();
  }

  function loadScript(name) {
    return new Promise(resolve => {
      const child = document.createElement("script");
      child.src = new URL(name + ".js", codeRoot);
      child.onload = resolve;
      child.onerror = resolve;
      document.head.append(child);
    });
  }
  const NEEDS = {successor: ["integer"]};
  async function loadRenderer(name) {
    for (const need of NEEDS[name] || []) await loadRenderer(need);
    if (!renderers.has(name)) await loadScript(name);
  }
  let tasksLoaded = null;
  const loadExtensions = () => tasksLoaded || (tasksLoaded = loadScript("tasks").then(() => loadScript("challenge")));

  function loadData(file, world) {
    if (!cache.has(file)) cache.set(file, Promise.all([fetchJSON(file), loadRenderer(world), loadExtensions(), window.OpulseAtoms.load(world)]).then(([data, , , glossary]) => {
      data.atoms = (data.atoms || []).map(atom => {
        const entry = glossary[atom.symbol === "-" && atom.arity === 1 ? "- (unary)" : atom.symbol];
        return {...atom, signature: entry.signature, plain: entry.plain, plain_zh: entry.plain_zh,
          displayName: entry.name};
      });
      return data;
    }));
    return cache.get(file);
  }

  function draw(el, value, renderer, ctx) {
    el.replaceChildren();
    try { (renderer.renderValue || api.fallbackValue)(el, value, ctx); }
    catch (error) { el.replaceChildren(); api.fallbackValue(el, value); }
  }
  api.draw = draw;
  api.renderValue = async function (el, world, value, ctx) {
    await loadRenderer(world);
    draw(el, value, renderers.get(world) || {renderValue: api.fallbackValue}, ctx || {});
  };

  // ---------------------------------------------------------------- atoms
  function atomsBar(data, renderer) {
    const bar = element("section", "ow-atoms");
    bar.append(element("h3", "ow-atoms-heading", tr(`Atoms (${data.atoms.length})`, `原子（${data.atoms.length}）`)));
    const row = element("div", "ow-atom-row");
    const sign = atom => atom.signature || (atom.params || []).map(p => p.type).join(" × ") + " → " + (atom.result_type || "");
    data.atoms.forEach(atom => {
      const chip = element("button", "ow-atom-chip");
      chip.type = "button";
      chip.title = tr(atom.plain, atom.plain_zh || atom.plain);
      chip.innerHTML = '<b></b><span></span>';
      chip.querySelector("b").textContent = atom.symbol;
      chip.querySelector("span").textContent = sign(atom);
      chip.onclick = () => {
        const card = details.querySelectorAll(".ow-atom-grid .ow-atom")[data.atoms.indexOf(atom)];
        if (!card) return;
        card.classList.remove("ow-atom-highlight");
        requestAnimationFrame(() => {
          card.classList.add("ow-atom-highlight");
          card.scrollIntoView({behavior: reduced() ? "auto" : "smooth", block: "center"});
          setTimeout(() => card.classList.remove("ow-atom-highlight"), 1800);
        });
      };
      row.append(chip);
    });
    bar.append(row);
    const details = element("div", "ow-atom-details");
    fillDetails(details, data, renderer, sign);
    bar.append(details);
    return bar;
  }

  function fillDetails(details, data, renderer, sign) {
    const left = element("div", "ow-details-facts");
    if (data.why) left.append(element("p", "ow-why", tr(data.why.en, data.why.zh || data.why.en)));
    if (data.metrics) {
      const metrics = data.metrics;
      const novel = (data.seeds || []).find(item => item.seed === data.seed)?.metrics?.novel ?? metrics.novel;
      left.append(element("h4", "", tr("Counts", "数量")));
      const table = element("table", "ow-settings ow-metric-table");
      const add = (label, value) => {
        const row = element("tr");
        row.append(element("th", "", label), element("td", "ow-setting-value", String(value)));
        table.append(row);
      };
      if (metrics.forms) {
        add(tr("Substitution", "代入"), metrics.forms.composition);
        add(tr("Branch", "分支"), metrics.forms.branching);
        add(tr("Recursion", "递归"), metrics.forms.recursion);
      }
      if (metrics.layers) add(tr("Layers", "各层"), Object.entries(metrics.layers).sort(([a], [b]) => Number(a) - Number(b))
        .map(([layer, count]) => tr("layer ", "第 ") + layer + tr(": ", " 层：") + count).join(zh() ? "，" : ", "));
      if (metrics.behaviours !== undefined) add(tr("Distinct behaviors on test inputs", "测试输入上的不同行为"), metrics.behaviours);
      if (novel !== undefined && (data.seeds || []).length > 1) add(tr("Unique to this seed", "此种子独有"), novel);
      left.append(table, element("p", "ow-metric-note", tr(
        "Counts use fixed test inputs. Operators with the same outputs count as one.",
        "数量基于固定测试输入。输出相同的运算符计为一个。")));
    }
    if (data.domain?.length) {
      left.append(element("h4", "", tr("Values", "取值")));
      data.domain.forEach(item => left.append(element("p", "", tr(item.en, item.zh))));
    }
    if (data.settings?.length) {
      left.append(element("h4", "", tr("Settings", "设置")));
      const list = element("div", "ow-settings-list");
      data.settings.forEach(row => {
        const item = element("div", "ow-setting");
        item.append(element("code", "", row.key), element("span", "ow-setting-value", String(row.value)),
          element("div", "ow-setting-description", tr(row.en, row.zh)));
        list.append(item);
      });
      left.append(list);
    }
    const right = element("div", "ow-atom-grid");
    data.atoms.forEach(atom => {
      const card = element("article", "ow-atom");
      const top = element("div", "ow-atom-top");
      top.append(element("b", "ow-atom-symbol", atom.symbol), element("span", "ow-atom-type", sign(atom)));
      card.append(top, element("strong", "ow-atom-name", atom.displayName || atom.name),
                  element("p", "", tr(atom.plain, atom.plain_zh || atom.plain)));
      if (atom.example) {
        const flow = element("div", "ow-flow");
        if (data.world === "perm" && atom.example.inputs.some(value => value?.t === "perm")) {
          flow.classList.add("ow-perm-flow");
        }
        if (atom.example.inputs.every(scalar)) flow.append(element("code", "", atom.example.expression));
        else atom.example.inputs.forEach((value, i) => {
          const name = atom.params?.[i]?.name || "";
          if (scalar(value)) { flow.append(element("code", "", name + " = " + api.valueText(value))); return; }
          const slot = element("figure", "ow-in"); draw(slot, value, renderer, {...data, compact: true});
          slot.append(element("figcaption", "", name)); flow.append(slot);
        });
        if (flow.classList.contains("ow-perm-flow")) flow.append(element("code", "ow-perm-operation", atom.displayName || atom.name));
        flow.append(element("span", "ow-arrow", "→"));
        const out = element("span", "ow-out"); draw(out, atom.example.output, renderer, {...data, compact: true, atom});
        flow.append(out);
        card.append(flow);
      }
      right.append(card);
    });
    const explanation = element("div", "ow-atom-explanation");
    explanation.append(element("h4", "", tr("What these atoms do", "这些原子操作的含义")), right);
    details.append(explanation, left);
  }

  // ---------------------------------------------------------------- derivation
  function callsTree(data, op) {
    const operators = new Map(data.operators.map(item => [item.name, item]));
    const atoms = new Map();
    for (const atom of data.atoms || []) {
      atoms.set(atom.name, atom);
      if (!atoms.has(atom.symbol)) atoms.set(atom.symbol, atom);
    }
    const names = [...new Set([...operators.keys(), ...atoms.keys()])].sort((a, b) => b.length - a.length);
    const pattern = new RegExp(names.map(name => [...name].map(char => "\\u{" + char.codePointAt(0).toString(16) + "}").join("")).join("|"), "gu");
    const section = element("section", "ow-calls");
    section.append(element("h4", "", tr("Calls", "调用")));
    const tree = element("ul", "ow-call-tree");
    const expanded = new Set();
    function references(current) {
      const body = current.definition.split("=").slice(1).join("=");
      const found = [], direct = new Set();
      for (const match of body.matchAll(pattern)) {
        const name = match[0], before = body[match.index - 1] || "", after = body[match.index + name.length] || "";
        if (/^[A-Za-z_]/.test(name) && (/[A-Za-z0-9_]/.test(before) || /[A-Za-z0-9_]/.test(after))) continue;
        const called = operators.get(name) || atoms.get(name);
        if (!called) continue;
        const key = operators.has(name) ? "operator:" + called.name : "atom:" + called.name;
        if (!direct.has(key)) { found.push({called, operator: operators.has(name)}); direct.add(key); }
      }
      for (const name of current.uses || []) {
        const called = operators.get(name), key = "operator:" + name;
        if (called && !direct.has(key)) { found.push({called, operator: true}); direct.add(key); }
      }
      return found;
    }
    function add(current, depth, isOperator = true) {
      const item = element("li");
      const row = element("div", "ow-call-row");
      row.style.setProperty("--ow-indent", Math.min(depth, 4) + "rem");
      const label = element("span", "ow-call-name");
      label.innerHTML = rich(isOperator ? current.name : current.symbol);
      if (!isOperator) label.classList.add("ow-call-atom");
      const repeated = isOperator && expanded.has(current.name);
      const description = isOperator ? tr(current.plain, current.plain_zh || current.plain) : current.name;
      const detail = element("span", "ow-call-detail", repeated ? tr("(see above)", "（见上文）") : description);
      if (!isOperator || repeated) detail.classList.add("ow-call-muted");
      row.title = isOperator ? description : current.name + " · " + tr(current.plain, current.plain_zh || current.plain);
      row.append(label, detail);
      item.append(row);
      tree.append(item);
      if (isOperator && !repeated) {
        expanded.add(current.name);
        for (const ref of references(current)) add(ref.called, depth + 1, ref.operator);
      }
    }
    add(op, 0);
    section.append(tree);
    return section;
  }

  function makePlayer(pane, data, op, exampleIndex, renderer, startStep = 0) {
    const example = op.examples[exampleIndex];
    const short = text => renderer.shorten ? renderer.shorten(text) : text;
    pane.querySelectorAll(".ow-player").forEach(old => old.dispatchEvent(new Event("ow:close")));
    const body = pane.querySelector(".ow-pane-body");
    body.replaceChildren();
    const counter = pane.querySelector(".ow-counter");
    const panel = element("div", "ow-player");
    const visual = element("div", "ow-step-visual");
    const host = element("div", "ow-step-view");
    panel.append(visual, host, callsTree(data, op)); body.append(panel);
    let viewer = null, steps = [];
    panel.addEventListener("ow:close", () => { if (viewer) viewer.destroy(); visual.replaceChildren(); });
    const formatted = text => { const node = document.createElement("span"); node.innerHTML = rich(short(String(text))); return node; };
    function show(step, position) {
      counter.textContent = tr("step ", "第 ") + (position + 1) + " / " + steps.length + tr("", " 步");
      if (!renderer.persistent) visual.replaceChildren();
      let value = example.inputs[0];
      for (let i = 0; i < position; i++) if (steps[i].value) value = steps[i].value;
      const previous = value;
      if (step.value) value = step.value;
      const style = getComputedStyle(visual);
      // renderStep receives the usable visual-box dimensions in CSS pixels so each world can scale its material.
      const width = visual.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
      const height = visual.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom);
      const ctx = {...data, data, world: data, example, operator: op, steps, index: position, stepIndex: position,
        large: true, width: Math.max(0, width), height: Math.max(0, height)};
      try {
        if (renderer.renderStep) renderer.renderStep(visual, {...step, value, previous}, ctx);
        else draw(visual, position === steps.length - 1 ? example.output : value, renderer, ctx);
      } catch (error) { visual.replaceChildren(); api.fallbackValue(visual, value); }
    }
    fetchJSON((data.steps || data.world + "/steps/") + op._index + ".json").then(all => {
      if (!panel.isConnected) return;
      const record = Array.isArray(all) ? all[exampleIndex] : (all.examples || all.steps || [])[exampleIndex];
      steps = Array.isArray(record) ? record : (record?.steps || []);
      const rows = steps.map((step, i) => ({...step, expr_before: short(i ? steps[i - 1].expression : example.expression),
        expr_after: short(step.expression), redex: typeof step.focus === "string" ? short(step.focus) : step.focus,
        rowTitle: i ? steps[i - 1].expression : example.expression,
        rule: tr(step.note, step.note_zh || step.note)}));
      viewer = window.OpulseStepView.render(host, {steps: rows, page_size: 50, initial: Math.max(0, startStep - 1),
        morph: true, compactRows: true, playInterval: 1400,
        lang: (document.documentElement.lang || "").startsWith("zh") ? "zh" : "en", renderValue: formatted,
        labels: {describe: step => formatted(step.rule), onSelect: (_, i) => show(steps[i], i)}});
      if (renderer.selectExample) renderer.selectExample(example, steps, data);
      if (!steps.length) draw(visual, example.output, renderer, {...data, data, world: data, example});
    }).catch(() => { host.textContent = tr("Derivation unavailable.", "无法加载推导。"); });
  }

  function operatorsTab(container, data, renderer, start) {
    const grid = element("div", "ow-panes");
    grid.innerHTML =
      '<section class="ow-pane ow-list-pane"><header class="ow-pane-head"><span class="ow-pane-title"></span><span class="ow-count"></span></header>' +
      '<div class="ow-filters"><input type="search"><select data-filter="layer"></select><select data-filter="kind"></select></div>' +
      '<button type="button" class="ow-show-all"></button><p class="ow-generator-note" hidden></p>' +
      '<div class="ow-list" role="listbox"></div></section>' +
      '<section class="ow-pane ow-rule-pane"><header class="ow-pane-head ow-rule-head"></header><div class="ow-pane-body"></div></section>' +
      '<section class="ow-pane ow-derive-pane"><header class="ow-pane-head"><span class="ow-pane-title"></span><span class="ow-counter"></span></header>' +
      '<div class="ow-pane-body"></div></section>';
    container.replaceChildren(grid);
    const kindLegend = element("div", "");
    grid.querySelector(".ow-filters").after(kindLegend);
    if (window.KindsLegend) window.KindsLegend.render(kindLegend, {lang: zh() ? "zh" : "en"});
    const [listPane, rulePane, derivePane] = grid.querySelectorAll(".ow-pane");
    listPane.querySelector(".ow-pane-title").textContent = tr("Operators", "运算符");
    derivePane.querySelector(".ow-pane-title").textContent = tr("Derivation", "推导");
    const search = listPane.querySelector("input");
    search.placeholder = tr("Search operators", "搜索运算符");
    search.setAttribute("aria-label", search.placeholder);
    const [layer, kind] = listPane.querySelectorAll("select");
    layer.setAttribute("aria-label", tr("Filter by layer", "按层筛选"));
    kind.setAttribute("aria-label", tr("Filter by form", "按形式筛选"));
    layer.innerHTML = '<option value="all">' + tr("All layers", "所有层") + "</option>" +
      [...new Set(data.operators.map(op => op.layer))].sort().map(v => '<option value="' + v + '">' + tr("Layer ", "第 ") + v + tr("", " 层") + "</option>").join("");
    kind.innerHTML = '<option value="all">' + tr("All forms", "所有形式") + "</option>" +
      Object.keys(KIND).map(k => '<option value="' + k + '">' + kindLabel(k) + "</option>").join("");
    const list = listPane.querySelector(".ow-list");
    list.setAttribute("aria-label", tr("Operators", "运算符"));
    const byName = new Map(data.operators.map((op, index) => [op.name, index]));
    const curated = (data.curated || data.operators.map(op => op.name)).filter(name => byName.has(name));
    const allButton = listPane.querySelector(".ow-show-all");
    const generatorNote = listPane.querySelector(".ow-generator-note");
    const requested = Number.isInteger(start.op) && start.op >= 0 && start.op < data.operators.length;
    let showAll = requested && !curated.includes(data.operators[start.op].name);
    function updateAllButton() {
      allButton.textContent = showAll ? tr("Show curated operators", "显示精选运算符") :
        tr(`Show all ${data.operators.length} grown operators`, `显示全部 ${data.operators.length} 个生成运算符`);
      generatorNote.textContent = tr("Unfiltered generator output. Some rules are redundant or unhelpful.",
        "未筛选的生成结果。部分规则重复或用途不明。");
      generatorNote.hidden = !showAll;
    }
    allButton.hidden = curated.length === data.operators.length;
    allButton.onclick = () => { showAll = !showAll; updateAllButton(); filter(); };
    updateAllButton();
    const ruleHead = rulePane.querySelector(".ow-rule-head"), ruleBody = rulePane.querySelector(".ow-pane-body");
    let selected = -1;

    function choose(index, exampleIndex = 0, startStep = 0) {
      selected = index;
      list.querySelectorAll(".ow-operator").forEach(b => b.setAttribute("aria-selected", Number(b.dataset.index) === index));
      const op = data.operators[index];
      ruleHead.innerHTML = '<strong class="ow-rule-name"></strong><span class="ow-kind ow-' + op.kind + '">' + esc(kindLabel(op.kind)) + '</span>' +
        '<span class="ow-layer">' + tr("layer ", "第 ") + esc(op.layer) + tr("", " 层") + '</span><span class="ow-signature"></span>';
      ruleHead.querySelector(".ow-rule-name").innerHTML = rich(op.name);
      ruleHead.querySelector(".ow-signature").textContent = (op.params || []).map(p => p.type).join(" × ") + (op.result_type ? " → " + op.result_type : "");
      ruleBody.innerHTML = '<pre class="ow-definition"></pre><p class="ow-plain"></p><div class="ow-uses"></div>' +
        '<div class="ow-examples-head"><h4>' + tr("Examples", "示例") + '</h4><div class="ow-amount" role="group" aria-label="' +
        tr("Number of examples", "示例数量") + '"></div></div><div class="ow-examples"></div>';
      ruleBody.querySelector(".ow-definition").innerHTML = rich(renderer.shorten ? renderer.shorten(op.definition) : op.definition);
      ruleBody.querySelector(".ow-plain").innerHTML = rich(tr(op.plain, op.plain_zh || op.plain));
      const uses = ruleBody.querySelector(".ow-uses");
      if (op.uses?.length) {
        uses.append(element("span", "", tr("uses", "调用")));
        op.uses.forEach(name => {
          const target = data.operators.findIndex(other => other.name === name);
          const link = element("button", "ow-use"); link.type = "button"; link.innerHTML = rich(name);
          link.onclick = () => {
            if (target < 0) return;
            const next = data.operators[target];
            const term = search.value.trim().toLowerCase();
            if (term && !(next.name + " " + next.definition + " " + next.plain + " " + (zh() ? next.plain_zh || "" : "")).toLowerCase().includes(term)) search.value = "";
            if (layer.value !== "all" && layer.value !== String(next.layer)) layer.value = "all";
            if (kind.value !== "all" && kind.value !== next.kind) kind.value = "all";
            if (!showAll && !curated.includes(next.name)) { showAll = true; updateAllButton(); }
            filter(); choose(target); reveal(target);
            if (matchMedia("(max-width: 700px)").matches) rulePane.scrollIntoView({behavior: reduced() ? "auto" : "smooth", block: "start"});
          };
          uses.append(link);
        });
      } else uses.remove();
      const amount = ruleBody.querySelector(".ow-amount");
      let shown = Math.min(op.examples.length, 3);
      [3, 6, 10].filter(n => n === 3 || n <= op.examples.length).forEach(n => {
        const button = element("button", "", String(Math.min(n, op.examples.length))); button.type = "button";
        button.setAttribute("aria-pressed", n === shown);
        button.onclick = () => { shown = Math.min(n, op.examples.length); amount.querySelectorAll("button").forEach(b => b.setAttribute("aria-pressed", b === button)); cards(); };
        amount.append(button);
      });
      if (amount.children.length < 2) amount.remove();
      let active = exampleIndex;
      function cards() {
        const box = ruleBody.querySelector(".ow-examples"); box.replaceChildren();
        op.examples.slice(0, shown).forEach((example, i) => {
          const card = element("div", "ow-example");
          card.setAttribute("role", "group");
          const tags = [];
          if (example.case && op.kind !== "composition") tags.push(tr("case ", "情形 ") + example.case);
          if (op.kind === "recursion" && example.depth) tags.push(tr("depth ", "深度 ") + example.depth);
          card.innerHTML = '<button type="button" class="ow-example-inspect" aria-pressed="false"><span class="ow-example-expression"></span><span class="ow-inspect-label"></span></button><div class="ow-example-visual"></div><div class="ow-example-foot"><span class="ow-example-tags"></span></div>';
          const inspect = card.querySelector(".ow-example-inspect");
          inspect.setAttribute("aria-pressed", i === active);
          card.querySelector(".ow-inspect-label").textContent = tr("Inspect", "查看推导");
          const expr = card.querySelector(".ow-example-expression");
          expr.innerHTML = rich(renderer.shorten ? renderer.shorten(example.expression) : example.expression);
          expr.title = example.expression;
          const visual = card.querySelector(".ow-example-visual");
          const ctx = {...data, compact: true, mini: true, operator: op, example};
          const valueSlot = (value, role) => {
            const slot = element("span", "ow-example-value ow-example-" + role);
            draw(slot, value, renderer, scalar(value) ? {...ctx, mini: false} : ctx);
            visual.append(slot);
          };
          example.inputs.forEach((value, inputIndex) => {
            if (inputIndex) visual.append(element("span", "ow-example-separator", ","));
            valueSlot(value, "input");
          });
          visual.append(element("span", "ow-arrow", "→"));
          valueSlot(example.output, "output");
          if (tags.length) card.querySelector(".ow-example-tags").textContent = tags.join(" · ");
          else card.querySelector(".ow-example-foot").remove();
          inspect.onclick = () => {
            active = i;
            box.querySelectorAll(".ow-example-inspect").forEach(b => b.setAttribute("aria-pressed", b === inspect));
            makePlayer(derivePane, data, op, i, renderer);
            if (matchMedia("(max-width: 700px)").matches) derivePane.scrollIntoView({behavior: reduced() ? "auto" : "smooth", block: "start"});
          };
          box.append(card);
        });
      }
      cards();
      if (op.examples.length) makePlayer(derivePane, data, op, active, renderer, startStep);
      else derivePane.querySelector(".ow-pane-body").replaceChildren();
      if (start.track && history.replaceState) history.replaceState(null, "", "#" + data.world + "/" + index);
    }
    function reveal(index) {
      const button = list.querySelector('[data-index="' + index + '"]');
      if (button) list.scrollTop = Math.max(0, button.offsetTop - list.offsetTop - list.clientHeight / 3);
    }
    function filter() {
      const term = search.value.trim().toLowerCase();
      list.replaceChildren();
      let count = 0;
      const indices = showAll ? data.operators.map((_, index) => index) : curated.map(name => byName.get(name));
      indices.forEach(index => {
        const op = data.operators[index];
        if (layer.value !== "all" && String(op.layer) !== layer.value) return;
        if (kind.value !== "all" && op.kind !== kind.value) return;
        const sentence = tr(op.plain, op.plain_zh || op.plain);
        if (term && !(op.name + " " + op.definition + " " + op.plain + " " + (zh() ? op.plain_zh || "" : "")).toLowerCase().includes(term)) return;
        const button = element("button", "ow-operator ow-" + op.kind); button.type = "button"; button.dataset.index = index;
        button.setAttribute("role", "option"); button.setAttribute("aria-selected", index === selected);
        button.title = kindLabel(op.kind) + ": " + sentence;
        button.setAttribute("aria-label", op.name + ": " + sentence);
        button.innerHTML = '<span class="ow-form" aria-label="' + esc(kindLabel(op.kind)) + '">' + (KIND[op.kind] || ["", "", "?"])[2] + '</span>' +
          '<span class="ow-op-name">' + rich(op.name) + '</span><span class="ow-op-plain"></span>' + (curated.slice(0, 5).includes(op.name) ? '<span class="ow-star" title="' + tr("Featured", "精选") + '">★</span>' : "");
        button.querySelector(".ow-form").title = kindLabel(op.kind) + ": " + (window.KindsLegend ? window.KindsLegend.copy[zh() ? "zh" : "en"].kinds[{composition:0, branching:1, recursion:2}[op.kind]][1] : sentence);
        button.querySelector(".ow-op-plain").innerHTML = rich(sentence);
        button.onclick = () => {
          choose(index);
          if (matchMedia("(max-width: 700px)").matches) rulePane.scrollIntoView({behavior: reduced() ? "auto" : "smooth", block: "start"});
        }; list.append(button); count++;
      });
      listPane.querySelector(".ow-count").textContent = count;
    }
    search.oninput = filter; layer.onchange = filter; kind.onchange = filter;
    list.addEventListener("keydown", event => {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      const buttons = [...list.querySelectorAll(".ow-operator")];
      const next = buttons[Math.max(0, Math.min(buttons.length - 1, buttons.indexOf(document.activeElement) + (event.key === "ArrowDown" ? 1 : -1)))];
      if (next) { event.preventDefault(); next.focus(); next.click(); }
    });
    filter();
    const first = requested ? start.op : byName.get(curated[0]) ?? 0;
    choose(first, Math.min(start.example || 0, Math.max(0, data.operators[first].examples.length - 1)), start.step || 0);
    reveal(first);
    start.track = true;
  }

  // ---------------------------------------------------------------- one world
  function metricsLine(data) {
    const m = data.metrics;
    if (!m) return "";
    const selected = data.curated?.length || m.operators;
    return tr("seed ", "种子 ") + data.seed + " · " +
      tr(`${selected} curated of ${m.operators} grown operators`, `精选 ${selected} 个，共生成 ${m.operators} 个运算符`);
  }

  function showWorld(view, data, text, switchSeed, start = {}) {
    data.operators.forEach((op, index) => {
      op._index ??= index;
      op.examples ||= (data.examples || []).filter(example => example.operator === op.name);
      op.layer ??= op.recursive_layer ?? 0;
      if (op.kind === "branch") op.kind = "branching";
    });
    const renderer = renderers.get(data.world) || {renderValue: api.fallbackValue};
    const shell = element("div", "ow-shell");
    shell.innerHTML = '<header class="ow-heading"><div class="ow-heading-main"><h2></h2><p class="ow-world-text"></p>' +
      '<div class="ow-seed"><button type="button" class="ow-new-seed"></button><span class="ow-metrics"></span></div></div>' +
      '</header><div class="ow-context"></div><div class="ow-atoms-slot"></div>' +
      '<section class="ow-app"><nav class="ow-tabs" role="tablist"></nav><div class="ow-tab-body"></div></section>';
    view.replaceChildren(shell);
    shell.querySelector("h2").textContent = tr(data.title, data.title_zh || data.title);
    const paragraphs = text ? [...text.querySelectorAll("p")] : [];
    if (paragraphs.length) shell.querySelector(".ow-world-text").innerHTML = paragraphs[0].innerHTML;
    const seedButton = shell.querySelector(".ow-new-seed");
    const seeds = data.seeds || [];
    if (seeds.length > 1) {
      const position = seeds.findIndex(item => item.seed === data.seed);
      seedButton.textContent = tr("Next seed ↻", "下一个种子 ↻");
      seedButton.title = tr("Show the next saved seed.", "显示下一个保存的种子。");
      seedButton.onclick = () => switchSeed(seeds[(position + 1) % seeds.length].file);
      shell.querySelector(".ow-metrics").textContent = metricsLine(data);
    } else { seedButton.remove(); shell.querySelector(".ow-metrics").textContent = metricsLine(data); }
    const context = shell.querySelector(".ow-context");
    if (renderer.renderContext) { try { renderer.renderContext(context, data); } catch (error) { /* optional */ } }
    if (!context.childNodes.length) context.remove();
    if (data.atoms?.length) shell.querySelector(".ow-atoms-slot").append(atomsBar(data, renderer));
    const tabs = shell.querySelector(".ow-tabs"), body = shell.querySelector(".ow-tab-body");
    function renderTabs() {
      const all = [{id: "operators", label: "Operators", label_zh: "运算符", render: c => operatorsTab(c, data, renderer, start)},
        ...(extensions.get("*") || []), ...(extensions.get(data.world) || [])]
        .filter(tab => !tab.available || tab.available(data));
      const current = tabs.querySelector('[aria-selected="true"]')?.dataset.tab || "operators";
      tabs.replaceChildren();
      all.forEach(tab => {
        const button = element("button", "ow-tab", tr(tab.label, tab.label_zh || tab.label)); button.type = "button";
        button.setAttribute("role", "tab"); button.dataset.tab = tab.id;
        button.onclick = () => {
          tabs.querySelectorAll(".ow-tab").forEach(b => b.setAttribute("aria-selected", b === button));
          body.replaceChildren();
          try { tab.render(body, data, {tr, renderer, draw, element, rich, lang: zh() ? "zh" : "en", dataRoot: dataRoot.href}); }
          catch (error) { body.replaceChildren(element("p", "ow-status", error.message)); }
        };
        tabs.append(button);
      });
      tabs.hidden = all.length < 2;
      (tabs.querySelector('[data-tab="' + current + '"]') || tabs.firstChild).click();
    }
    renderTabs();
    fetchJSON(data.world + "/challenge.json").then(challenge => {
      if (!shell.isConnected || challenge.schema !== "opulse.world-challenge/1" ||
          challenge.world !== data.world || !Array.isArray(challenge.challenges) || !challenge.challenges.length) return;
      data.challenge = challenge;
      renderTabs();
    }).catch(() => { /* a world without challenge data has no Challenge tab */ });
    const onExtend = event => { if (!shell.isConnected) { document.removeEventListener("opulse-worlds:extend", onExtend); return; }
      if (event.detail === "*" || event.detail === data.world) renderTabs(); };
    document.addEventListener("opulse-worlds:extend", onExtend);
  }

  // ---------------------------------------------------------------- page
  // Move each design and its details into one card.
  function groupUses(scope) {
    const intro = scope.querySelector(".ow-intro");
    if (!intro || intro.dataset.grouped) return;
    intro.dataset.grouped = "1";
    const isLead = node => node.tagName === "P" && node.firstElementChild?.tagName === "STRONG" &&
      node.textContent.trim().startsWith(node.firstElementChild.textContent.trim());
    const isDetail = node => node.tagName === "P" && node.firstElementChild?.tagName === "EM" &&
      node.textContent.trim().startsWith(node.firstElementChild.textContent.trim());
    const nodes = [...intro.children];
    const first = nodes.findIndex(isLead);
    if (first < 0) return;
    const cards = element("div", "ow-use-cards");
    intro.insertBefore(cards, nodes[first]);
    let card = null, more = null;
    for (const node of nodes.slice(first)) {
      if (isLead(node)) {
        card = element("article", "ow-use-card"); cards.append(card);
        const title = element("h3", "", node.firstElementChild.textContent.replace(/\.$/, ""));
        node.firstElementChild.remove();
        node.classList.add("ow-use-summary");
        more = element("details", "ow-use-more");
        more.append(element("summary", "", tr("More", "更多")));
        card.append(title, node, more);
      } else if (card && isDetail(node)) {
        more.append(node);
      } else card = null;
    }
  }

  async function init(root) {
    root.classList.add("opulse-worlds");
    const scope = root.closest(".md-content") || document;
    groupUses(scope);
    const texts = new Map();
    root.querySelectorAll("[data-world-text]").forEach(node => { texts.set(node.dataset.worldText, node); node.remove(); });
    const status = element("p", "ow-status", tr("Loading worlds…", "正在加载世界……"));
    root.append(status);
    try {
      const fixed = root.dataset.world;
      let index = await fetchJSON("index.json");
      index = index.map(item => typeof item === "string" ? {world: item, title: item, dimension: ""} : item);
      if (fixed) index = index.filter(item => item.world === fixed);
      status.remove();
      const picker = element("nav", "ow-picker"); picker.setAttribute("aria-label", tr("Worlds", "世界"));
      const view = element("div", "ow-view");
      if (!fixed) root.append(picker);
      root.append(view);
      const buttons = new Map();
      DIMENSIONS.forEach(([dimension, english, chinese]) => {
        const members = index.filter(item => item.dimension === dimension);
        if (!members.length) return;
        const group = element("div", "ow-group");
        group.append(element("span", "ow-group-label", tr(english, chinese)));
        members.forEach(item => {
          const button = element("button", "ow-world-tab"); button.type = "button";
          button.setAttribute("aria-pressed", "false");
          button.textContent = tr(item.title, item.title_zh || item.title);
          button.title = tr(item.summary || "", item.summary_zh || item.summary || "");
          button.onclick = () => select(item.world);
          buttons.set(item.world, button);
          group.append(button);
        });
        picker.append(group);
      });
      let request = 0;
      async function select(world, start = {}) {
        const current = ++request;
        const item = index.find(entry => entry.world === world) || index[0];
        buttons.forEach((button, name) => button.setAttribute("aria-pressed", name === item.world));
        view.querySelectorAll(".ow-player").forEach(player => player.dispatchEvent(new Event("ow:close")));
        view.replaceChildren(element("p", "ow-status", tr("Loading ", "正在加载") + tr(item.title, item.title_zh || item.title) + "…"));
        if (!fixed && history.replaceState) history.replaceState(null, "", "#" + item.world);
        const open = async file => {
          try {
            const data = await loadData(file, item.world);
            if (current !== request) return;
            showWorld(view, data, texts.get(item.world)?.cloneNode(true) || null, next => open(next), {...start, track: false});
          } catch (error) { if (current === request) view.replaceChildren(element("p", "ow-status", error.message)); }
        };
        await open(item.world + ".json");
      }
      // #world, or #world/operator/example/step to open a given derivation step
      const [wanted, op, example, step] = decodeURIComponent((location.hash || "").slice(1)).split("/");
      select(index.some(item => item.world === wanted) ? wanted : index[0].world,
        {op: op ? Number(op) : undefined, example: Number(example) || 0, step: Number(step) || 0});
    } catch (error) { status.textContent = error.message; }
  }

  const start = () => document.querySelectorAll("[data-opulse-worlds]:not([data-ready])").forEach(root => { root.dataset.ready = "1"; init(root); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else start();
  if (window.document$) window.document$.subscribe(start);
})();
