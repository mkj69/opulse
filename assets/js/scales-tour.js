/* Three scale tour views. Uses OpulseScales for examples, cuts, and lazy pages. */
(function () {
  "use strict";
  var api = window.OpulseScales;
  if (!api) { return; }
  var keys = ["s10", "s100", "s1000", "s10000"];
  var labels = ["≈10", "≈100", "≈1000", "≈10000"];
  function add(parent, tag, cls, value) {
    var el = document.createElement(tag);
    if (cls) { el.className = cls; }
    if (value !== undefined) { el.textContent = value; }
    parent.appendChild(el);
    return el;
  }
  function rich(node, value, example) { node.replaceChildren(api.richText(value, example)); return node; }
  function revealPressedPreset(strip) {
    if (!window.matchMedia || !window.matchMedia("(max-width: 600px)").matches) { return; }
    var selected = strip.querySelector('button[aria-pressed="true"]');
    if (!selected) { return; }
    var outer = strip.getBoundingClientRect(), inner = selected.getBoundingClientRect();
    if (inner.left < outer.left || inner.right > outer.right) { strip.scrollLeft += inner.left - outer.left; }
  }
  function init(root) {
    if (root.dataset.scalesTourReady) { return; }
    root.dataset.scalesTourReady = "1";
    var zh = root.dataset.lang === "zh";
    var tr = function (en, cn) { return zh ? cn : en; };
    var mode = root.dataset.mode;
    var tabs = root.querySelector(".st-tabs");
    var panel = root.querySelector(".st-panel");
    var active = 0, serial = 0, timer = null, observer = null, handle = null, chips = null, tree = null;
    var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var dataCache = {};
    function stop() { if (timer !== null) { clearInterval(timer); timer = null; } }
    function clear() {
      stop();
      if (observer) { observer.disconnect(); observer = null; }
      [handle, chips, tree].forEach(function (item) { if (item) { item.destroy(); } });
      handle = chips = tree = null;
      panel.replaceChildren();
    }
    keys.forEach(function (key, i) {
      var button = add(tabs, "button", "st-tab", labels[i]);
      button.type = "button";
      button.setAttribute("role", "tab");
      button.id = root.id + "-tab-" + key;
      button.setAttribute("aria-controls", root.id + "-panel");
      button.addEventListener("click", function () { select(i); });
      button.addEventListener("keydown", function (event) {
        var next = event.key === "Home" ? 0 : event.key === "End" ? 3 :
          event.key === "ArrowRight" ? (i + 1) % 4 : event.key === "ArrowLeft" ? (i + 3) % 4 : -1;
        if (next >= 0) { event.preventDefault(); select(next); tabs.children[next].focus(); }
      });
    });
    function choose(index, scale) {
      var options = scale.examples.filter(function (item) { return item.world === "integer"; });
      if (!options.length) { return null; }
      options.sort(function (a, b) {
        return b.layer - a.layer || (scale.key === "s10" ?
          Number(b.kind === "recursive") - Number(a.kind === "recursive") : 0) ||
          b.full_steps - a.full_steps;
      });
      return options[0];
    }
    function select(i) {
      clear(); active = i; var ticket = ++serial;
      Array.prototype.forEach.call(tabs.children, function (button, j) {
        button.setAttribute("aria-selected", j === i ? "true" : "false");
        button.tabIndex = j === i ? 0 : -1;
      });
      panel.setAttribute("aria-labelledby", tabs.children[i].id);
      add(panel, "p", "", tr("Loading scale…", "正在加载规模…"));
      var key = keys[i];
      var pending = dataCache[key];
      if (!pending) {
        pending = mode === "grade" ? fetch(new URL("../scales_grade/" + key + ".json", api.dataRoot())).then(function (response) {
          if (!response.ok) { throw new Error("pending"); }
          return response.json();
        }).then(function (data) {
          return api.loadExample(key, data.example).then(function (example) { data.scaleExample = example; return data; });
        }) : api.loadIndex().then(function (index) {
          var scale = index.scales.filter(function (row) { return row.key === key; })[0];
          if (!scale) { throw new Error("missing scale"); }
          var example = choose(index, scale);
          if (!example) { throw new Error("pending"); }
          return api.loadExample(key, example.id).then(function (loaded) { return { scale: scale, summary: example, example: loaded }; });
        });
        dataCache[key] = pending;
      }
      pending.then(function (data) {
        if (serial !== ticket) { return; }
        clear();
        if (mode === "grade") { renderGrade(data); }
        else { renderGranularity(data); }
      }).catch(function () {
        delete dataCache[key];
        if (serial === ticket) {
          panel.replaceChildren();
          add(panel, "p", "", tr("This scale is available when its operator set finishes.", "该规模的运算符集完成后即可查看。"));
        }
      });
    }
    function stats(data) {
      var set = data.scale.sets.filter(function (item) { return item.name === data.summary.set; })[0];
      var h = data.example.header;
      add(panel, "p", "st-stats", tr("Set", "集合") + ": " + api.fmt(set.size) + " · " +
        tr("Layer", "层") + ": " + api.fmt(h.layer) + " · " + tr("Closure", "依赖闭包") + ": " + api.fmt(h.closure_size));
      rich(add(panel, "p", "st-expression"), h.expression + " → " + h.value, data.example);
    }
    function renderGranularity(data) {
      window.OpulseAtoms.legend(add(panel, "div", "st-atoms-legend"), data.example.header.world,
        window.OpulseAtoms.closureTexts(data.example.operators, data.example.header.target, data.example.header.expression));
      stats(data);
      var example = data.example, h = example.header;
      var coarse = h.cut_table[h.cut_table.length - 1].steps, full = h.cut_table[0].steps;
      var hidden = (100 * (1 - coarse / full)).toFixed(3);
      add(panel, "p", "st-count", tr("All operators known: ", "所有算子已知：") + api.fmt(coarse) +
        tr(" step; fully unfolded: ", " 步；完全展开：") + api.fmt(full) +
        tr(" steps. The coarse cut hides ", " 步。粗粒度隐藏了 ") + hidden + tr("% of steps.", "% 的步骤。"));
      var presets = add(panel, "div", "st-presets");
      presets.setAttribute("role", "group");
      presets.setAttribute("aria-label", tr("Known operator presets", "已知运算符预设"));
      var info = add(panel, "p", "st-cut-count"); info.setAttribute("role", "status");
      var kindLegend = add(panel, "div", "");
      if (window.KindsLegend) window.KindsLegend.render(kindLegend, {lang: zh ? "zh" : "en"});
      var chipBox = add(panel, "div", "st-chipbox");
      var viewTabs = add(panel, "div", "st-view-tabs");
      viewTabs.setAttribute("role", "tablist");
      viewTabs.setAttribute("aria-label", tr("Derivation view", "推导视图"));
      var stepTab = add(viewTabs, "button", "st-view-tab", tr("Steps", "步骤"));
      var treeTab = add(viewTabs, "button", "st-view-tab", tr("Tree", "推导树"));
      var stepBox = add(panel, "div", "st-stepbox");
      var treeBox = add(panel, "div", "st-treebox");
      [stepTab, treeTab].forEach(function (button, index) {
        button.type = "button"; button.id = root.id + "-view-tab-" + index;
        button.setAttribute("role", "tab");
        button.setAttribute("aria-controls", root.id + "-view-" + index);
        button.addEventListener("click", function () { selectView(index); });
        button.addEventListener("keydown", function (event) {
          var next = event.key === "ArrowRight" ? (index + 1) % 2 : event.key === "ArrowLeft" ? (index + 1) % 2 :
            event.key === "Home" ? 0 : event.key === "End" ? 1 : -1;
          if (next >= 0) { event.preventDefault(); selectView(next); [stepTab, treeTab][next].focus(); }
        });
      });
      [stepBox, treeBox].forEach(function (box, index) {
        box.id = root.id + "-view-" + index;
        box.setAttribute("role", "tabpanel");
        box.setAttribute("aria-labelledby", [stepTab, treeTab][index].id);
        box.tabIndex = 0;
      });
      function selectView(index) {
        [stepTab, treeTab].forEach(function (button, i) {
          button.setAttribute("aria-selected", i === index ? "true" : "false");
          button.tabIndex = i === index ? 0 : -1;
        });
        stepBox.hidden = index !== 0; treeBox.hidden = index !== 1;
      }
      selectView(0);
      var known = new Set(), generation = 0;
      chips = api.renderOperatorChips(chipBox, example.operators, { expandedLayers: 1, example: example });
      function mark() {
        Array.prototype.forEach.call(chipBox.querySelectorAll(".os-chip"), function (chip) {
          var selected = known.has(Number(chip.dataset.operatorIndex));
          chip.classList.toggle("st-known", selected);
          var editable = !!example.operators[Number(chip.dataset.operatorIndex)].definition;
          chip.tabIndex = editable ? 0 : -1;
          chip.setAttribute("role", "button");
          chip.setAttribute("aria-disabled", editable ? "false" : "true");
          chip.setAttribute("aria-pressed", selected ? "true" : "false");
        });
      }
      function show() {
        var ticket = ++generation;
        var cut = example.cutFromSet(known);
        if (handle) { handle.destroy(); }
        if (tree) { tree.destroy(); }
        handle = api.renderStepList(stepBox, example, cut, { pageSize: 50 });
        tree = api.renderTree(treeBox, example, cut);
        var matching = h.cut_table.filter(function (row) {
          return example.operators.every(function (op, index) {
            return !op.definition || known.has(index) === (op.layer < row.L);
          });
        })[0];
        Array.prototype.forEach.call(presets.children, function (button, i) {
          button.setAttribute("aria-pressed", matching && h.cut_table[i].L === matching.L ? "true" : "false");
        });
        revealPressedPreset(presets);
        info.textContent = tr("Counting steps…", "正在统计步骤…");
        example.count(cut).then(function (count) {
          if (ticket === generation) { info.textContent = (matching ? tr("This cut: ", "当前粒度：") : tr("Custom cut: ", "自定义粒度：")) +
            api.fmt(count) + tr(count === 1 ? " step" : " steps", " 步"); }
        }).catch(function (error) { if (ticket === generation) { info.textContent = error.message; } });
        mark();
      }
      h.cut_table.forEach(function (row) {
        var label = row.L === 0 ? tr("Fully unfolded", "完全展开") :
          row.L === h.layer + 1 ? tr("All known", "全部已知") :
            tr("Below layer " + row.L + " known", "已知第 " + row.L + " 层以下");
        var button = add(presets, "button", "", label + " · " + api.fmt(row.steps) + tr(row.steps === 1 ? " step" : " steps", " 步"));
        button.type = "button";
        button.setAttribute("aria-pressed", "false");
        button.addEventListener("click", function () {
          known = new Set();
          example.operators.forEach(function (op, index) { if (op.layer < row.L) { known.add(index); } });
          show();
        });
      });
      function toggleChip(target) {
        var chip = target.closest(".os-chip");
        if (!chip || !chipBox.contains(chip)) { return; }
        var index = Number(chip.dataset.operatorIndex);
        if (!example.operators[index].definition) { return; }
        if (known.has(index)) { known.delete(index); } else { known.add(index); }
        show();
      }
      chipBox.addEventListener("click", function (event) { toggleChip(event.target); });
      chipBox.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          if (event.target.closest(".os-chip")) { event.preventDefault(); toggleChip(event.target); }
        }
      });
      chipBox.querySelector(".os-chip-search").addEventListener("input", mark);
      example.operators.forEach(function (op, index) { if (op.layer < h.middle_cut) { known.add(index); } });
      show();
    }
    function renderGrade(data) {
      window.OpulseAtoms.legend(add(panel, "div", "st-atoms-legend"), data.scaleExample.header.world,
        window.OpulseAtoms.closureTexts(data.scaleExample.operators, data.scaleExample.header.target, data.question));
      add(panel, "p", "st-stats", tr("Set", "集合") + ": " + api.fmt(data.set_size) + " · " +
        tr("Layer", "层") + ": " + data.layer + " · " + tr("Closure", "依赖闭包") + ": " +
        api.fmt(data.closure_size) + " · " + tr("Cut below layer", "已知层界") + ": " + data.cut);
      rich(add(panel, "p", "st-expression"), data.question + " → " + data.answer, data.scaleExample);
      var choice = add(panel, "div", "st-controls");
      var list = add(panel, "div", "st-grade-list");
      var jump = add(panel, "button", "", tr("Go to first wrong line", "跳到首个错误行"));
      jump.type = "button";
      var run = 0;
      function paint() {
        var current = data.runs[run], lines = current.lines, report = current.report;
        if (handle) { handle.destroy(); }
        var rows = lines.map(function (line, i) {
          var status = {single: tr("single step", "单步"), jump: tr("valid jump", "有效跳步"),
            repeat: tr("repeat", "重复"), error: tr("wrong", "错误"),
            skipped: tr("not checked", "未检查")}[current.statuses[i]];
          return {expr_before: i ? lines[i - 1] : data.question, expr_after: line, kind: "compute", rule: status};
        });
        handle = window.OpulseStepView.render(list, {steps: rows, page_size: 50, lang: zh ? "zh" : "en",
          renderValue: function (value) { return api.richText(value, data.scaleExample); },
          labels: {describe: function (step) { return step.rule; }}});
        jump.hidden = report.first_error === null;
        jump.onclick = function () { handle.goToStep(report.first_error + 1); };
      }
      [tr("Correct derivation", "正确推导"), tr("One wrong value", "一个错误数值")].forEach(function (label, i) {
        var button = add(choice, "button", "", label);
        button.type = "button";
        button.addEventListener("click", function () { run = i; paint(); });
      });
      add(panel, "p", "st-final", tr("Wrong line ", "错误行 ") + (data.slip + 1) +
        tr(" writes ", " 写成 ") + data.wrong_value + tr("; expected ", "；应为 ") + data.expected_value + ".");
      paint();
    }
    select(0);
  }
  Array.prototype.forEach.call(document.querySelectorAll(".scales-tour"), init);
}());
