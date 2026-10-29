/* Homepage scale examples. The shared library decodes only the requested chunks. */
(function () {
  "use strict";
  let api = window.OpulseScales;
  const words = {
    en: {
      scales: "Operator set size", examples: "Examples", pending: "No checked example is available for this size yet.",
      morePending: "More checked examples will appear when the remaining sets finish.",
      loading: "Loading example…", counting: "Loading the selected cut…", failed: "Could not load the example.",
      kinds: { simple: "Composition", branch: "Branching", recursive: "Recursion", typed: "Typed world" },
      summary: (size, symbol, layer, closure, coarse, middle, L, full) =>
        `Set of ${size} operators. ${symbol} sits on layer ${layer} and reaches ${closure} defined operators. ${coarse} ${coarse === "1" ? "step" : "steps"} with all operators known, ${middle} ${middle === "1" ? "step" : "steps"} with layers below ${L} known, ${full} ${full === "1" ? "step" : "steps"} fully unfolded.`,
      definition: "Definition", expression: "Expression", known: "Known below layer", all: "All known",
      unfolded: "Fully unfolded", steps: n => n === 1 ? "step" : "steps", customCut: "Custom cut", custom: "Choose individual operators", tree: "Derivation tree",
      list: "Steps", operators: "Known operators in this cut"
    },
    zh: {
      scales: "运算符集规模", examples: "示例", pending: "这一规模尚无已检查的示例。",
      morePending: "其余运算符集完成后，会显示更多已检查的示例。",
      loading: "正在加载示例…", counting: "正在加载所选粒度…", failed: "无法加载示例。",
      kinds: { simple: "组合", branch: "分支", recursive: "递归", typed: "类型化世界" },
      summary: (size, symbol, layer, closure, coarse, middle, L, full) =>
        `此集合有 ${size} 个运算符。${symbol} 位于第 ${layer} 层，依赖闭包包含 ${closure} 个已定义运算符。全部运算符已知时为 ${coarse} 步，第 ${L} 层以下已知时为 ${middle} 步，完全展开时为 ${full} 步。`,
      definition: "定义", expression: "算式", known: "已知第几层以下", all: "全部已知",
      unfolded: "完全展开", steps: () => "步", customCut: "自定义粒度", custom: "逐个选择运算符", tree: "推导树",
      list: "步骤", operators: "当前粒度的已知运算符"
    }
  };
  function make(tag, className, parent, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    if (parent) parent.appendChild(node);
    return node;
  }
  function rich(node, value, example) { node.replaceChildren(api.richText(value, example)); return node; }
  function revealPressedPreset(strip) {
    if (!window.matchMedia || !window.matchMedia("(max-width: 600px)").matches) return;
    const selected = strip.querySelector('button[aria-pressed="true"]');
    if (!selected) return;
    const outer = strip.getBoundingClientRect(), inner = selected.getBoundingClientRect();
    if (inner.left < outer.left || inner.right > outer.right) strip.scrollLeft += inner.left - outer.left;
  }
  function tabs(container, items, label, onChoose, panel) {
    container.setAttribute("role", "tablist");
    container.setAttribute("aria-label", label);
    const buttons = items.map((item, index) => {
      const button = make("button", "oh-tab", container, item.label);
      button.type = "button"; button.setAttribute("role", "tab");
      button.id = `${panel.id}-tab-${index}`;
      button.setAttribute("aria-controls", panel.id);
      button.setAttribute("aria-selected", index === 0 ? "true" : "false");
      button.tabIndex = index === 0 ? 0 : -1;
      button.addEventListener("click", () => choose(index));
      return button;
    });
    function choose(index) {
      buttons.forEach((button, i) => {
        button.setAttribute("aria-selected", i === index ? "true" : "false");
        button.tabIndex = i === index ? 0 : -1;
      });
      panel.setAttribute("aria-labelledby", buttons[index].id);
      onChoose(index);
    }
    container.addEventListener("keydown", event => {
      const current = buttons.indexOf(document.activeElement);
      if (current < 0) return;
      let next = current;
      if (event.key === "ArrowRight") next = (current + 1) % buttons.length;
      else if (event.key === "ArrowLeft") next = (current - 1 + buttons.length) % buttons.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = buttons.length - 1;
      else return;
      event.preventDefault(); buttons[next].focus(); choose(next);
    });
    return buttons;
  }
  function init(root) {
    const lang = root.dataset.lang === "zh" ? "zh" : "en", t = words[lang];
    const status = root.querySelector(".oh-status"), content = root.querySelector(".oh-content");
    let serial = 0, cutSerial = 0, listHandle, treeHandle, started = false;
    const fmt = api.fmt;
    function clearViews() {
      cutSerial++;
      if (listHandle) listHandle.destroy();
      if (treeHandle) treeHandle.destroy();
      listHandle = treeHandle = null;
    }
    async function start() {
      if (started) return;
      started = true;
      try {
        const index = await api.loadIndex();
        const scales = index.scales;
        content.hidden = false; status.hidden = true;
        const scaleTabs = make("div", "oh-tabs", content);
        const scalePanel = make("section", "oh-scale-panel", content);
        scalePanel.id = `oh-scale-panel-${lang}`;
        scalePanel.setAttribute("role", "tabpanel");
        function selectScale(position) {
          const scale = scales[position];
          serial++;
          clearViews(); scalePanel.replaceChildren();
          const examples = scale.examples || [];
          if (!examples.length) { make("p", "oh-pending", scalePanel, t.pending); return; }
          if (examples.length < 2) make("p", "oh-pending", scalePanel, t.morePending);
          const exampleTabs = make("div", "oh-tabs oh-example-tabs", scalePanel);
          const examplePanel = make("section", "oh-example-panel", scalePanel);
          examplePanel.id = `oh-example-panel-${lang}`;
          examplePanel.setAttribute("role", "tabpanel");
          const items = examples.map(row => ({ label: `${t.kinds[row.kind] || row.kind} · ${row.target}` }));
          const choices = tabs(exampleTabs, items, t.examples, i => selectExample(scale, examples[i], examplePanel), examplePanel);
          examplePanel.setAttribute("aria-labelledby", choices[0].id);
          selectExample(scale, examples[0], examplePanel);
        }
        const choices = tabs(scaleTabs, scales.map(scale => ({ label: scale.label })), t.scales, selectScale, scalePanel);
        scalePanel.setAttribute("aria-labelledby", choices[0].id);
        selectScale(0);
      } catch (error) { status.hidden = false; status.textContent = `${t.failed} ${error.message}`; }
    }
    async function selectExample(scale, row, panel) {
      const request = ++serial;
      clearViews(); panel.replaceChildren();
      make("p", "oh-loading", panel, t.loading);
      try {
        const example = await api.loadExample(scale.key, row.id);
        if (request !== serial) return;
        panel.replaceChildren();
        const h = example.header;
        const set = scale.sets.find(item => item.name === h.set);
        const table = example.cutTable, coarse = table[table.length - 1], middle = table.find(item => item.L === h.middle_cut), full = table[0];
        rich(make("p", "oh-summary", panel), t.summary(fmt(set.size), h.target, fmt(h.layer), fmt(h.closure_size),
          fmt(coarse.steps), fmt(middle.steps), fmt(middle.L), fmt(full.steps)), example);
        rich(make("p", "oh-sentence", panel), lang === "zh" ? h.sentence_zh : h.sentence, example);
        make("h3", "oh-subhead", panel, t.definition);
        const target = example.operators.find(op => op.symbol === h.target && op.layer === h.layer && op.definition);
        rich(make("code", "oh-definition", panel), target ? target.definition : h.target, example);
        const atomLegend = make("div", "oh-atoms-legend", panel);
        window.OpulseAtoms.legend(atomLegend, h.world,
          window.OpulseAtoms.closureTexts(example.operators, h.target, h.expression));
        const expression = make("p", "oh-expression", panel);
        make("strong", "", expression, `${t.expression}: `);
        rich(make("code", "", expression), h.expression, example);
        make("span", "", expression, " = ");
        rich(make("code", "", expression), h.value, example);
        const heading = make("h3", "oh-subhead", panel, t.known);
        heading.id = `oh-cut-${row.id}`;
        const presets = make("div", "oh-presets", panel);
        presets.setAttribute("role", "group"); presets.setAttribute("aria-labelledby", heading.id);
        const count = make("p", "oh-count", panel);
        count.setAttribute("role", "status");
        const custom = make("details", "oh-custom", panel);
        make("summary", "", custom, t.custom);
        make("p", "oh-chip-hint", custom, t.operators);
        const chipBox = make("div", "oh-chip-box", custom);
        const listHeading = make("h3", "oh-subhead", panel, t.list);
        const listBox = make("div", "oh-list", panel);
        listBox.setAttribute("aria-labelledby", listHeading.id = `oh-steps-${row.id}`);
        const tree = make("details", "oh-tree-section", panel);
        tree.open = true; make("summary", "", tree, t.tree);
        const treeBox = make("div", "oh-tree-box", tree);
        let chipHandle, activeL = h.middle_cut, known = null;
        const buttons = [...table].reverse().map(entry => {
          const label = entry.L === h.layer + 1 ? t.all :
            entry.L === 0 ? t.unfolded : lang === "zh" ? `已知第 ${entry.L} 层以下` : `Below layer ${entry.L} known`;
          const button = make("button", "oh-preset", presets, `${label} · ${fmt(entry.steps)} ${t.steps(entry.steps)}`);
          button.type = "button"; button.setAttribute("aria-pressed", entry.L === activeL ? "true" : "false");
          button.addEventListener("click", () => {
            activeL = entry.L; known = null; updateChips(); showCut(example.cutBelowLayer(activeL), entry.steps);
          });
          return button;
        });
        function updateChips() {
          if (!chipHandle) return;
          chipBox.querySelectorAll(".os-chip").forEach(chip => {
            const i = Number(chip.dataset.operatorIndex), op = example.operators[i];
            chip.setAttribute("role", "checkbox"); chip.tabIndex = op.definition ? 0 : -1;
            chip.setAttribute("aria-disabled", op.definition ? "false" : "true");
            chip.setAttribute("aria-checked", (!op.definition || (known ? known.has(i) : op.layer < activeL)) ? "true" : "false");
          });
        }
        custom.addEventListener("toggle", () => {
          if (custom.open && !chipHandle) {
            chipHandle = api.renderOperatorChips(chipBox, example.operators, { expandedLayers: 2, example });
            updateChips();
          }
        });
        chipBox.addEventListener("input", () => { window.setTimeout(updateChips, 0); });
        function toggleChip(event) {
          const chip = event.target.closest(".os-chip");
          if (!chip || (event.type === "keydown" && event.key !== "Enter" && event.key !== " ")) return;
          const i = Number(chip.dataset.operatorIndex);
          if (!example.operators[i].definition) return;
          event.preventDefault();
          if (!known) {
            known = new Set();
            example.operators.forEach((op, n) => { if (op.definition && op.layer < activeL) known.add(n); });
          }
          if (known.has(i)) known.delete(i); else known.add(i);
          updateChips(); showCut(example.cutFromSet(known));
        }
        chipBox.addEventListener("click", toggleChip);
        chipBox.addEventListener("keydown", toggleChip);
        function showCut(cut, precomputed) {
          clearViews();
          const ticket = cutSerial;
          const matching = known ? table.find(entry => example.operators.every((op, i) =>
            !op.definition || known.has(i) === (op.layer < entry.L))) : table.find(entry => entry.L === activeL);
          buttons.forEach((button, i) => button.setAttribute("aria-pressed",
            matching && table[table.length - 1 - i].L === matching.L ? "true" : "false"));
          revealPressedPreset(presets);
          const countText = total => `${matching ? "" : `${t.customCut} · `}${fmt(total)} ${t.steps(total)}`;
          count.textContent = precomputed === undefined ? t.counting : countText(precomputed);
          listBox.textContent = t.counting; treeBox.textContent = "";
          // Let the loading state paint before a custom count traverses the DAG.
          window.setTimeout(async () => {
            if (ticket !== cutSerial) return;
            try {
              const total = precomputed === undefined ? await example.count(cut) : precomputed;
              if (ticket !== cutSerial) return;
              count.textContent = countText(total);
              listHandle = api.renderStepList(listBox, example, cut, { pageSize: 50 });
              treeHandle = api.renderTree(treeBox, example, cut);
            } catch (error) { if (ticket === cutSerial) count.textContent = `${t.failed} ${error.message}`; }
          }, 0);
        }
        showCut(example.cutBelowLayer(activeL), middle.steps);
      } catch (error) {
        if (request === serial) { panel.replaceChildren(); make("p", "oh-error", panel, `${t.failed} ${error.message}`); }
      }
    }
    if ("IntersectionObserver" in window) {
      const observer = new IntersectionObserver(entries => {
        if (entries.some(entry => entry.isIntersecting)) { observer.disconnect(); start(); }
      }, { rootMargin: "200px" });
      observer.observe(root);
      root.addEventListener("pointerdown", () => { observer.disconnect(); start(); }, { once: true });
    } else start();
  }
  function boot() {
    api = window.OpulseScales;
    if (!api) return;
    document.querySelectorAll(".op-home-scales:not([data-ready])").forEach(root => {
      root.dataset.ready = "true";
      init(root);
    });
  }
  boot();
  if (window.document$ && typeof window.document$.subscribe === "function") window.document$.subscribe(boot);
}());
