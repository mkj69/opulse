(function () {
  "use strict";
  var script = typeof document !== "undefined" && document.currentScript && document.currentScript.src;

  var groups = [
    { id: "compute", en: "Compute", zh: "演算", description: ["Follow the rules to the result.", "依照规则求出结果。"], modes: ["compute", "wrongstep"] },
    { id: "invert", en: "Invert", zh: "逆推", description: ["Work back from a result to the input.", "从结果逆推出输入。"], modes: ["hole"] },
    { id: "decide", en: "Decide", zh: "判定", description: ["Prove or refute a claim.", "证明或反驳一个判断。"], modes: ["equiv", "laws", "deadbranch", "ripple"] },
    { id: "describe", en: "Describe", zh: "转述", description: ["Move between a formal rule and plain language.", "在形式规则和日常语言之间转换。"], modes: ["describe"] },
    { id: "induce", en: "Induce", zh: "归纳", description: ["Infer a rule or carry a structure to new material.", "从例子归纳规则，或将结构迁移到新材料。"], modes: ["induce", "translate"] },
    { id: "create", en: "Create", zh: "创造", description: ["Build something new that meets a goal.", "构造满足目标的新表达式或定义。"], modes: ["shorten", "target"] }
  ];
  var modes = {
    compute: ["Follow the rules", "依规演算", "Work out the result by following the rules.", "按照规则算出结果。"],
    wrongstep: ["Find the wrong step", "查找错步", "Find the first wrong step.", "找出第一步错误。"],
    hole: ["Find the unknown", "逆求未知", "Work back from the result to the input.", "从结果逆推输入。"],
    equiv: ["Same or different?", "判定等价", "Decide whether two expressions are always equal.", "判定两个表达式是否始终相等。"],
    laws: ["True or false law", "定律真伪", "Prove a property holds, or give a counterexample.", "证明性质成立，或给出反例。"],
    deadbranch: ["Find the dead end", "找出死路", "Find the branch that can never run.", "找出永远不会执行的分支。"],
    ripple: ["Trace the ripple", "连锁追踪", "Change one rule and see which results change.", "修改一条规则，追踪哪些结果改变。"],
    induce: ["Guess the rule", "归纳规则", "Predict new outputs from examples, then optionally write the rule.", "根据例子预测新输出，也可以写出规则。"],
    translate: ["Cross-world analogy", "跨界类比", "Carry the same structure into a new world.", "将相同结构用到新世界。"],
    shorten: ["Simplify the definition", "精简定义", "Write an equivalent definition within the step budget.", "在总步数预算内写出等价定义。"],
    describe: ["Name it or write it", "转述规则", "Match a rule to plain language, or write a rule from a description.", "选择规则的文字描述，或根据描述写出规则。"],
    target: ["Hit the target", "凑出目标", "Combine the given numbers with the allowed operators.", "用给定数字和算子凑出目标值。"]
  };
  var labels = {
    en: {rules: "Rules", answer: "Your answer", check: "Check", reveal: "Reveal", previous: "Previous challenge",
      next: "Next challenge", share: "Share", model: "Try it on your model", solved: "Solved", why: "Why this one",
      correct: "Correct.", incorrect: "Try again, or reveal the answer.", needCheck: "Checking needs the in-browser interpreter.",
      choose: "Choose an answer.", inputs: "Counterexample inputs (comma separated)", holds: "Holds", fails: "Fails",
      same: "Same", different: "Different", before: "Before", after: "After", unique: "This is the only hit in the domain.",
      proof: "Proof", counterexample: "Counterexample", reference: "Reference", query: "Query", optional: "Optional rule",
      budget: "Step budget", source: "Source", target: "Target", structure: "Shared tree", scan: "Scan",
      correctLine: "Correct line", wrongLine: "First wrong line", replay: "Correct steps", explanation: "Explanation",
      changed: "Changes", unchanged: "Unchanged", waiting: "Checking…", unavailable: "This mode is unavailable.",
      paste: "Paste the model's answer", grade: "Grade", parsed: "Parsed answer", verdict: "Verdict"},
    zh: {rules: "规则", answer: "你的答案", check: "检查", reveal: "公布答案", previous: "上一题",
      next: "下一题", share: "分享", model: "复制给你的模型", solved: "已解出", why: "这题的看点",
      correct: "答对了。", incorrect: "再试一次，或查看答案。", needCheck: "检查答案需要浏览器内解释器。",
      choose: "请选择答案。", inputs: "反例输入（用逗号分隔）", holds: "成立", fails: "不成立",
      same: "相同", different: "不同", before: "修改前", after: "修改后", unique: "这是取值范围内唯一的解。",
      proof: "证明", counterexample: "反例", reference: "参考答案", query: "待预测", optional: "可选：写出规则",
      budget: "步数预算", source: "源世界", target: "目标世界", structure: "共有结构", scan: "逐个检查",
      correctLine: "正确步骤", wrongLine: "第一步错误", replay: "正确推导", explanation: "说明",
      changed: "改变", unchanged: "不变", waiting: "正在检查…", unavailable: "此模式暂不可用。",
      paste: "粘贴模型的回答", grade: "评分", parsed: "解析答案", verdict: "判定"}
  };
  function el(tag, cls, value) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (value !== undefined) { node.textContent = String(value); }
    return node;
  }
  function button(text, cls, click) {
    var node = el("button", cls || "challenge-button challenge-secondary", text);
    node.type = "button";
    if (click) { node.addEventListener("click", click); }
    return node;
  }
  function labelInput(parent, text, kind, name, value) {
    var label = el("label", "challenge-choice");
    var input = el("input"); input.type = kind; input.name = name; input.value = value;
    label.append(input, document.createTextNode(" " + text)); parent.append(label);
    return input;
  }
  function scalar(value) {
    if (value && typeof value === "object" && "t" in value) {
      return typeof window !== "undefined" && window.OpulseWorlds ? window.OpulseWorlds.valueText(value) : JSON.stringify(value);
    }
    return String(value);
  }
  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  // Older fixture group values remain valid; the visible group follows the mode.
  function groupForMode(mode) { return groups.find(function (group) { return group.modes.indexOf(mode) >= 0; }); }
  function domainText(domain, lang) { return (lang === "zh" ? "从 " + domain[0] + " 到 " + domain[1] : "from " + domain[0] + " to " + domain[1]); }
  function code(node, value) { node.append(el("code", "", value)); }
  function rules(item) { return item.rules.map(function (rule) { return rule.text; }); }
  function inputsText(values) { return (values || []).map(scalar).join(", "); }
  function operatorName(symbol, lang) {
    var names = {"+": ["add", "加法"], "-": ["subtract", "减法"], "*": ["multiply", "乘法"],
      "/": ["divide", "除法"], "%": ["remainder", "取余"], "<=": ["at most", "小于等于"],
      ">=": ["at least", "大于等于"], ">": ["greater than", "大于"], "<": ["less than", "小于"],
      "==": ["equal to", "等于"]};
    return names[symbol] ? names[symbol][lang === "zh" ? 1 : 0] : "";
  }
  function inputTuplesText(inputs) { return (inputs || []).map(function (point) { return "(" + inputsText(point) + ")"; }).join(", "); }
  function readInputs(input) {
    var parts = input.value.split(",").map(function (part) { return part.trim(); });
    if (!parts.length || parts.some(function (part) { return !/^-?\d+$/.test(part); })) { return null; }
    return parts.map(Number);
  }
  function instantiate(text, inputs) {
    return String(text).replace(/\b([abcxyz])\b/g, function (symbol) {
      var i = {a: 0, b: 1, c: 2, x: 0, y: 1, z: 2}[symbol];
      return inputs[i] === undefined ? symbol : "(" + inputs[i] + ")";
    });
  }
  function checkApi() {
    return window.OpulseCheck && typeof window.OpulseCheck.ready === "function" ?
      window.OpulseCheck.ready().then(function () { return window.OpulseCheck; }).catch(function () { return null; }) : Promise.resolve(null);
  }
  function evaluatePair(item, left, right, inputs, fallback) {
    return checkApi().then(function (api) {
      if (!api) { return fallback; }
      function sideValue(side) {
        var definition = /\s*=\s*\{/.test(side);
        if (!definition) { return api.evaluate(rules(item), instantiate(side, inputs)); }
        var head = side.split("=")[0].trim().split(/\s+/);
        var symbol = head.filter(function (part) { return !/^[abcxyz]$/.test(part); })[0];
        var expression = inputs.length === 1 ? inputs[0] + " " + symbol : inputs[0] + " " + symbol + " " + inputs[1];
        var source = rules(item).filter(function (rule) { return rule.indexOf(symbol) < 0; });
        return api.evaluate(source.concat([side]), expression);
      }
      return Promise.all([sideValue(left), sideValue(right)])
        .then(function (values) { return !same(values[0].value, values[1].value); }).catch(function () { return fallback; });
    });
  }
  function renderWorldValue(container, world, value) {
    var slot = el("div", "challenge-world-value"); container.append(slot);
    if (window.OpulseWorlds && window.OpulseWorlds.renderValue) {
      window.OpulseWorlds.renderValue(slot, world, value, {compact: false}).catch(function () { slot.textContent = scalar(value); });
    } else { slot.textContent = scalar(value); }
    container.append(el("code", "challenge-encoded-value", scalar(value)));
  }
  function lawQuestion(item, lang) {
    var terms = {
      commutative: ["commutative", "交换律"], associative: ["associative", "结合律"],
      idempotent: ["idempotent", "幂等律"], "left identity": ["a left identity", "左单位元"],
      "right identity": ["a right identity", "右单位元"], involution: ["an involution", "对合律"],
      absorbing: ["an absorbing element", "吸收元"]
    };
    var term = terms[item.law] || [item.law, item.law];
    var match = item.statement.match(item.law === "left identity" || item.law === "absorbing" ? /^(-?\d+)/ : /\s(-?\d+)\s*=/);
    if (lang === "zh") {
      return (match ? "在 " + item.symbol + " 中，" + match[1] + " 是否为" + term[1] + "？" :
        "运算 " + item.symbol + " 是否满足" + term[1] + "？") + "也就是 " + item.statement +
        " 是否对" + domainText(item.domain, lang) + "的所有输入成立？";
    }
    var question = match ? "Is " + match[1] + " " + term[0] + " of " + item.symbol + "?" : "Is " + item.symbol + " " + term[0] + "?";
    var variables = item.statement.includes("c") ? "a, b, and c " : item.statement.includes("b") ? "a and b " : "a ";
    return question + " That is, does " + item.statement + " hold for every " + variables + domainText(item.domain, lang) + "?";
  }
  function translationRules(item) {
    var grid = el("div", "challenge-translation-rules");
    [item.source_world, item.target_world].forEach(function (world) {
      var column = el("section", "challenge-translation-column");
      column.append(el("h3", "challenge-translation-title", world));
      item.rules.filter(function (rule) { return rule.symbol.indexOf(world + " ") === 0; }).forEach(function (rule, i) {
        var row = el("div", i === 0 ? "challenge-translation-definition" : "challenge-translation-atom");
        row.append(el(i === 0 ? "code" : "span", "", rule.text)); column.append(row);
      }); grid.append(column);
    });
    return grid;
  }
  function atomTexts(mode, item) {
    var texts = (item.rules || []).map(function (rule) { return rule.text; });
    [item.question, item.statement, item.left, item.right, item.reference, item.reference_definition,
      item.text, item.skeleton, item.symbol].forEach(function (value) { if (typeof value === "string") texts.push(value); });
    if (item.atoms) texts.push(item.atoms.join(" "));
    if (item.allowed) texts.push(item.allowed.join(" "));
    if (Array.isArray(item.steps)) item.steps.forEach(function (step) { if (typeof step.expr === "string") texts.push(step.expr); });
    if (Array.isArray(item.branches)) item.branches.forEach(function (branch) { if (branch.text) texts.push(branch.text); });
    if (Array.isArray(item.items)) item.items.forEach(function (entry) { if (entry.expr) texts.push(entry.expr); });
    if (item.edit) texts.push(item.edit.before, item.edit.after);
    if (item.reference_definition && item.reference_definition.text) texts.push(item.reference_definition.text);
    if (item.known) texts.push(item.known.join(" "));
    if (item.source) texts.push(item.source.expression);
    if (item.rule && item.rule.text) texts.push(item.rule.text);
    if (item.options) item.options.forEach(function (option) { if (typeof option === "string") texts.push(option); });
    if (item.target && item.target.expression) texts.push(item.target.expression);
    return texts;
  }
  function atomWorld(mode, item) { return mode === "translate" ? item.source_world : (item.world || "integer"); }
  function promptFor(mode, item, lang, atomLines) {
    function numbered(entries, show) { return entries.map(function (entry, i) { return (i + 1) + ". " + show(entry); }).join("\n"); }
    var formats = {
      wrongstep: "Wrong step: <line number>", hole: "x = <integer>",
      equiv: "Verdict: same\nor\nVerdict: different\nCounterexample: a = <int>, b = <int>",
      laws: "Verdict: holds\nor\nVerdict: fails\nCounterexample: " +
        ["a", "b", "c"].filter(function (name) { return new RegExp("\\b" + name + "\\b").test(item.statement); })
          .map(function (name) { return name + " = <int>"; }).join(", "),
      deadbranch: "Dead branch: <branch number>", ripple: "Changes: <comma-separated item numbers>\nor\nChanges: none",
      induce: "Outputs: " + (item.queries || []).map(function (_, i) { return "<v" + (i + 1) + ">"; }).join("; ") +
        "\nOptionally:\nRule: <definition line>", translate: "Option: <number>",
      shorten: mode === "shorten" ? "Rule: <definition line>\n" +
        (lang === "zh" ? "该定义在这些输入上的总步数不得超过 " : "The definition must take at most ") +
        item.budget_steps + (lang === "zh" ? " 步：" : " total steps on these inputs: ") +
        inputTuplesText(item.inputs) + (lang === "zh" ? "。" : ".") : "",
      describe: item.direction === "name" ? "Option: <n>" : "Rule: <definition line>", target: "Expression: <expression>"
    };
    var task = {
      wrongstep: function () { return "Find the first wrong step in this derivation:\n" + numbered(item.steps, function (s) { return s.expr; }); },
      hole: function () { return "Find x: " + item.question + " = " + item.target + ". Find x " + domainText(item.domain, lang); },
      equiv: function () { return "Are these equivalent " + domainText(item.domain, lang) + "? " + item.left + " ; " + item.right + ". Give a counterexample if different."; },
      ripple: function () { return "For inputs " + inputsText(item.input) + ", after changing " + item.edit.before + " to " + item.edit.after +
        ", which expressions change?\n" + numbered(item.items, function (x) { return x.expr; }); },
      laws: function () { return "Does this law hold " + domainText(item.domain, lang) + "? " + item.statement + ". Give a counterexample if it fails."; },
      deadbranch: function () { return "Which branch can never run?\n" + numbered(item.branches, function (x) { return x.text; }); },
      induce: function () { return "Predict the outputs for these queries:\n" + numbered(item.queries, function (x) { return inputsText(x.inputs); }) +
        "\nKnown examples:\n" + item.examples.map(function (x) { return inputsText(x.inputs) + " → " + scalar(x.output); }).join("\n") +
        (item.domain ? "\nRule comparison domain: " + domainText(item.domain, lang) + "." : "") +
        (item.atoms ? "\nAvailable atoms: " + item.atoms.map(function (atom) {
          return typeof atom === "string" ? atom : atom.symbol + " (" + atom.name + ")";
        }).join(", ") + "." : "") +
        (item.known ? "\nKnown definitions: " + item.known.join("; ") + "." : ""); },
      translate: function () { return "Values use t for type and v for value. Use the same tree " + item.skeleton + " in " + item.target_world + ". Source: " + item.source.expression +
        " = " + JSON.stringify(item.source.output) + ". Target: " + item.target.expression + ". Choose from:\n" +
        numbered(item.target.options, JSON.stringify); },
      shorten: function () { return lang === "zh" ?
        "改写 " + item.symbol + "，使它对" + domainText(item.domain, lang) + "的所有输入与 " + item.text +
          " 结果相同，并在这些输入上的总步数不超过 " + item.budget_steps + "（现在是 " + item.steps + " 步）：" + inputTuplesText(item.inputs) + "。" :
        "Write a definition of " + item.symbol + " equivalent to " + item.text + " for every input " + domainText(item.domain, lang) +
          ". It must take at most " + item.budget_steps + " total steps (now " + item.steps + ") on these inputs: " + inputTuplesText(item.inputs) + "."; },
      describe: function () { return item.direction === "name" ? "Which description matches " + item.rule.text + "?\n" +
        numbered(lang === "zh" ? item.options_zh || item.options : item.options, String) : "Write a definition for " + item.symbol + ": " +
        (lang === "zh" ? item.description_zh || item.description : item.description) + " " + domainText(item.domain, lang) + "."; },
      target: function () { return "Use each number at most once: " + item.numbers.join(", ") + ". Allowed operators: " +
        item.allowed.join(", ") + ". Reach " + item.target + "."; }
    };
    if (lang === "zh") Object.assign(task, {
      wrongstep: function () { return "找出推导中第一处错误：\n" + numbered(item.steps, function (s) { return s.expr; }); },
      hole: function () { return "求 x：" + item.question + " = " + item.target + "。x 的范围是" + domainText(item.domain, lang) + "。"; },
      equiv: function () { return "在" + domainText(item.domain, lang) + "的范围内，" + item.left + " 与 " + item.right + " 是否等价？若不等价，请给出反例。"; },
      ripple: function () { return "输入为 " + inputsText(item.input) + "。将 " + item.edit.before + " 改为 " + item.edit.after +
        " 后，哪些表达式的结果改变？\n" + numbered(item.items, function (x) { return x.expr; }); },
      laws: function () { return "在" + domainText(item.domain, lang) + "的范围内，此规律是否成立？" + item.statement + "。若不成立，请给出反例。"; },
      deadbranch: function () { return "哪个分支永远不会执行？\n" + numbered(item.branches, function (x) { return x.text; }); },
      induce: function () { return "预测以下输入的结果：\n" + numbered(item.queries, function (x) { return inputsText(x.inputs); }) +
        "\n已知示例：\n" + item.examples.map(function (x) { return inputsText(x.inputs) + " → " + scalar(x.output); }).join("\n") +
        (item.domain ? "\n规则比较范围：" + domainText(item.domain, lang) + "。" : "") +
        (item.atoms ? "\n可用原子操作：" + item.atoms.join(", ") + "。" : "") +
        (item.known ? "\n已知定义：" + item.known.join("; ") + "。" : ""); },
      translate: function () { return "值中的 t 表示类型，v 表示内容。请在 " + item.target_world + " 中使用相同的结构 " +
        item.skeleton + "。源世界：" + item.source.expression + " = " + JSON.stringify(item.source.output) +
        "。目标世界：" + item.target.expression + "。请从以下选项中选择：\n" + numbered(item.target.options, JSON.stringify); },
      describe: function () { return item.direction === "name" ? "哪个描述符合 " + item.rule.text + "？\n" +
        numbered(item.options_zh || item.options, String) : "请根据描述写出 " + item.symbol + " 的定义：" +
        (item.description_zh || item.description) + "。范围：" + domainText(item.domain, lang) + "。"; },
      target: function () { return "每个数字最多使用一次：" + item.numbers.join(", ") + "。可用算子：" +
        item.allowed.join(", ") + "。目标值：" + item.target + "。"; }
    });
    var shownRules = mode === "translate" ? item.rules.map(function (rule) { return rule.symbol + ": " + rule.text; }) : rules(item);
    return (atomLines || "") + (lang === "zh" ? "规则：\n" : "Rules:\n") + shownRules.join("\n") + "\n\n" + task[mode]() +
      (lang === "zh" ? "\n\n回答格式：\n" : "\n\nAnswer format:\n") + formats[mode] +
      (lang === "zh" ? "\n只填写适用的格式行，不要添加其他内容。" :
        "\nUse only the applicable format lines; put nothing else on those lines.");
  }
  function copy(text, status) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { status.textContent = "Copied"; }, function () { fallback(); });
    } else { fallback(); }
    function fallback() {
      var area = el("textarea", "challenge-copy-fallback", text); area.readOnly = true;
      status.replaceChildren(area); area.focus(); area.select();
    }
  }

  function boot(root, load, initCompute) {
    var lang = root.dataset.lang === "zh" ? "zh" : "en", t = labels[lang];
    var selected = new URLSearchParams(location.search).get("mode") || "compute";
    if (!modes[selected]) { selected = "compute"; }
    var activeGroup = groupForMode(selected).id;
    var cache = {}, available = {}, ticket = 0;
    Object.keys(modes).forEach(function (mode) { available[mode] = true; });
    var solved = [];
    try { solved = JSON.parse(localStorage.getItem("opulse.challenge.modes.solved") || "[]");
      if (!Array.isArray(solved)) { solved = []; }
    } catch (_) { solved = []; }
    root.replaceChildren();
    var tabs = el("div", "challenge-group-tabs"); tabs.setAttribute("role", "tablist");
    var chips = el("div", "challenge-mode-chips");
    var groupDescription = el("p", "challenge-group-description");
    var content = el("div", "challenge-mode-content");
    content.dataset.lang = lang;
    root.append(tabs, groupDescription, chips, content);
    function url(item) {
      var result = new URL(location.href);
      result.searchParams.set("mode", selected);
      if (item) { result.searchParams.set("c", item.id); } else { result.searchParams.delete("c"); }
      result.searchParams.set("v", "0"); return result.href;
    }
    function select(mode) {
      if (!available[mode]) { return; }
      selected = mode; activeGroup = groupForMode(mode).id;
      try { history.replaceState(null, "", url(null)); } catch (_) { /* local preview */ }
      show();
    }
    function renderShell() {
      var focused = document.activeElement && document.activeElement.classList.contains("challenge-group-tab") ?
        Array.prototype.indexOf.call(tabs.children, document.activeElement) : -1;
      tabs.replaceChildren(); chips.replaceChildren();
      content.dataset.group = activeGroup;
      groups.forEach(function (group) {
        var tab = button(lang === "zh" ? group.zh : group.en, "challenge-group-tab", function () {
          activeGroup = group.id;
          if (group.modes.indexOf(selected) < 0) {
            var first = group.modes.find(function (mode) { return available[mode]; });
            if (first) { select(first); } else { renderShell(); content.textContent = t.unavailable; }
          } else { renderShell(); }
        });
        tab.setAttribute("role", "tab"); tab.setAttribute("aria-selected", String(activeGroup === group.id));
        tabs.append(tab);
      });
      if (focused >= 0 && tabs.children[focused]) { tabs.children[focused].focus(); }
      var active = groups.find(function (g) { return g.id === activeGroup; });
      groupDescription.textContent = active.description[lang === "zh" ? 1 : 0];
      groups.find(function (g) { return g.id === activeGroup; }).modes.forEach(function (mode) {
        if (!available[mode]) { return; }
        var chip = button(lang === "zh" ? modes[mode][1] : modes[mode][0], "challenge-mode-chip", function () { select(mode); });
        chip.setAttribute("aria-current", String(selected === mode));
        var row = el("div", "challenge-mode-option");
        row.append(chip, el("span", "challenge-mode-description", lang === "zh" ? modes[mode][3] : modes[mode][2]));
        chips.append(row);
      });
    }
    tabs.addEventListener("keydown", function (event) {
      var current = Array.prototype.indexOf.call(tabs.children, document.activeElement);
      if (current < 0) { return; }
      var next = event.key === "ArrowRight" ? (current + 1) % groups.length :
        event.key === "ArrowLeft" ? (current + groups.length - 1) % groups.length :
        event.key === "Home" ? 0 : event.key === "End" ? groups.length - 1 : -1;
      if (next >= 0) { event.preventDefault(); tabs.children[next].click(); tabs.children[next].focus(); }
    });
    function show() {
      var now = ++ticket;
      renderShell(); content.replaceChildren(el("p", "challenge-loading", lang === "zh" ? "正在加载…" : "Loading…"));
      if (selected === "compute") {
        var compute = cache.compute || (cache.compute = load("challenges.json")
          .then(function (data) { return load("expert.json").then(function (extra) {
            if (extra.schema === "opulse.challenge/1") { data.challenges = data.challenges.concat(extra.challenges); }
            return data;
          }).catch(function () { return data; }); })
          .then(function (data) { return load("legend.json").then(function (extra) {
            if (extra.schema === "opulse.challenge/1") { data.challenges = data.challenges.concat(extra.challenges); }
            return data;
          }).catch(function () { return data; }); }));
        compute.then(function (data) { if (now === ticket) { content.replaceChildren(); initCompute(content, data); } })
          .catch(function () { if (now === ticket) { content.textContent = t.unavailable; } });
        return;
      }
      var mode = selected;
      (cache[mode] || (cache[mode] = load(mode + ".json"))).then(function (data) {
        if (now !== ticket) { return; }
        if (data.schema !== "opulse.challenge-mode/1" || data.mode !== mode || !groupForMode(data.mode) ||
            !Array.isArray(data.challenges) || !data.challenges.length) {
          throw new Error("Invalid mode data");
        }
        content.dataset.group = groupForMode(data.mode).id;
        renderMode(content, mode, data.challenges, lang, t, solved, url);
      }).catch(function () { if (now === ticket) { available[mode] = false; renderShell(); content.textContent = t.unavailable; } });
    }
    // HEAD discovers chips without fetching their JSON bodies. Opening a chip fetches its data.
    Object.keys(modes).filter(function (mode) { return mode !== "compute"; }).forEach(function (mode) {
      fetch(new URL("../data/challenge/" + mode + ".json", script), {method: "HEAD"})
        .then(function (response) { available[mode] = response.ok; renderShell(); })
        .catch(function () { available[mode] = false; renderShell(); });
    });
    if (selected !== "compute") { available[selected] = true; }
    show();
  }

  function renderMode(host, mode, challenges, lang, t, solved, url) {
    var order = {easy: 0, medium: 1, hard: 2};
    challenges = challenges.slice().sort(function (a, b) { return order[a.level] - order[b.level]; });
    var requested = new URLSearchParams(location.search).get("c");
    var index = Math.max(0, challenges.findIndex(function (item) { return item.id === requested; }));
    function count() { return challenges.filter(function (item) { return solved.indexOf(item.id) >= 0; }).length; }
    function remember(item) {
      if (solved.indexOf(item.id) < 0) { solved.push(item.id);
        try { localStorage.setItem("opulse.challenge.modes.solved", JSON.stringify(solved)); } catch (_) { /* storage off */ }
      }
    }
    function select(i) { index = (i + challenges.length) % challenges.length; render(); }
    function render() {
      var item = challenges[index], controls = {};
      try { history.replaceState(null, "", url(item)); } catch (_) { /* local preview */ }
      host.replaceChildren();
      var picker = el("section", "challenge-picker"), toggle = button(lang === "zh" ? "所有挑战 ▾" : "All challenges ▾", "challenge-picker-toggle");
      var grids = el("div", "challenge-picker-groups"); grids.id = "challenge-mode-picker";
      var open = !matchMedia("(max-width: 40rem)").matches; grids.hidden = !open;
      toggle.setAttribute("aria-controls", grids.id); toggle.setAttribute("aria-expanded", String(open));
      toggle.onclick = function () { open = !open; grids.hidden = !open; toggle.setAttribute("aria-expanded", String(open)); };
      ["easy", "medium", "hard"].forEach(function (level) {
        var subset = challenges.map(function (entry, i) { return {entry: entry, i: i}; }).filter(function (entry) { return entry.entry.level === level; });
        if (!subset.length) { return; }
        var section = el("div", "challenge-picker-group"), grid = el("div", "challenge-picker-grid");
        section.append(el("h2", "challenge-picker-heading", level));
        subset.forEach(function (entry, n) {
          var tile = button((n + 1) + (solved.indexOf(entry.entry.id) >= 0 ? " ✓" : ""), "challenge-tile challenge-tile-" + level, function () { select(entry.i); });
          tile.setAttribute("aria-label", level + " " + (n + 1));
          if (entry.i === index) { tile.classList.add("is-current"); tile.setAttribute("aria-current", "true"); }
          grid.append(tile);
        }); section.append(grid); grids.append(section);
      }); picker.append(toggle, grids); host.append(picker);
      var card = el("section", "challenge-card"), top = el("div", "challenge-top");
      top.append(el("strong", "challenge-kicker", (index + 1) + " / " + challenges.length));
      top.append(el("span", "challenge-level challenge-level-" + item.level, item.level));
      top.append(el("span", "challenge-counter", t.solved + " " + count() + " / " + challenges.length));
      var nav = el("div", "challenge-header-nav");
      nav.append(button("← " + t.previous, "challenge-nav-button", function () { select(index - 1); }),
        button(t.next + " →", "challenge-nav-button", function () { select(index + 1); }));
      top.append(nav); card.append(top);
      if (mode === "translate" || item.rules.length) { card.append(el("h2", "challenge-heading", t.rules)); }
      var ruleList = el("div", "challenge-rules");
      (mode === "translate" ? [] : item.rules).forEach(function (rule) {
        var row = el("div", "challenge-rule"), body = el("div", "challenge-rule-main");
        body.append(el("span", "challenge-symbol", rule.symbol), el("span", "challenge-rule-text", rule.text));
        if (rule.hint) {
          var hint = el("span", "challenge-hint", rule.hint); hint.hidden = true;
          var showHint = button(lang === "zh" ? "提示" : "hint", "challenge-hint-toggle", function () {
            hint.hidden = !hint.hidden; showHint.setAttribute("aria-expanded", String(!hint.hidden));
          }); showHint.setAttribute("aria-expanded", "false"); body.append(showHint); row.append(body, hint);
        } else { row.append(body); }
        ruleList.append(row);
      }); card.append(mode === "translate" ? translationRules(item) : ruleList);
      var atomLegend = el("div", "challenge-atoms-legend"); card.append(atomLegend);
      window.OpulseAtoms.legend(atomLegend, atomWorld(mode, item), atomTexts(mode, item));
      if (mode === "translate") {
        var targetLegend = el("div", "challenge-atoms-legend"); card.append(targetLegend);
        window.OpulseAtoms.legend(targetLegend, item.target_world, atomTexts(mode, item));
      }
      var task = el("section", "challenge-mode-task"); card.append(task);
      var feedback = el("p", "challenge-feedback"); feedback.setAttribute("role", "status");
      var reveal = el("section", "challenge-reveal"); reveal.hidden = true;
      var actions = el("div", "challenge-actions");
      var check = button(t.check, "challenge-button challenge-primary"), showAnswer = button(t.reveal, "challenge-button challenge-secondary");
      actions.append(check, showAnswer); card.append(actions, feedback, reveal);
      var why = el("p", "challenge-why"); why.append(el("strong", "challenge-why-label", t.why + ": "),
        document.createTextNode(item[lang === "zh" ? "why_zh" : "why"] || "")); why.hidden = true; card.append(why);
      var footer = el("div", "challenge-actions"); footer.append(
        button(t.next, "challenge-button challenge-primary", function () { select(index + 1); }),
        button(t.share, "challenge-button challenge-secondary", function () { copy(url(item), status); }));
      var status = el("div", "challenge-copy-status"); status.setAttribute("role", "status");
      var modelGrade = el("section", "challenge-model-grade");
      modelGrade.append(el("h3", "challenge-model-heading", t.model));
      modelGrade.append(button(t.model, "challenge-button challenge-secondary", function () {
        var texts = atomTexts(mode, item);
        var worlds = mode === "translate" ? [item.source_world, item.target_world] : [atomWorld(mode, item)];
        Promise.all(worlds.map(function (world) { return window.OpulseAtoms.promptLines(world, texts, lang); }))
          .then(function (parts) { copy(promptFor(mode, item, lang, parts.join("")), status); });
      }));
      var modelLabel = el("label", "challenge-label", t.paste);
      var modelText = el("textarea", "challenge-input challenge-model-answer");
      modelLabel.append(modelText);
      var modelResult = el("div", "challenge-model-result"); modelResult.setAttribute("role", "status");
      modelGrade.append(modelLabel, button(t.grade, "challenge-button challenge-primary", function () {
        var parsed = window.OpulseChallengeAnswers.parseAnswer(mode, item, modelText.value);
        modelResult.textContent = t.parsed + ": " + (parsed.ok ? JSON.stringify(parsed.value) : parsed.error) + "\n" + t.waiting;
        Promise.resolve(window.OpulseChallengeAnswers.gradeAnswer(mode, item, parsed)).then(function (verdict) {
          modelResult.textContent = t.parsed + ": " + (parsed.ok ? JSON.stringify(parsed.value) : parsed.error) +
            "\n" + t.verdict + ": " + (verdict.correct ? t.correct : t.incorrect) + " " + verdict.detail;
          modelResult.classList.toggle("is-right", verdict.correct);
        }).catch(function (error) {
          modelResult.textContent = t.verdict + ": " + t.incorrect + " " + error.message;
          modelResult.classList.remove("is-right");
        });
      }), modelResult);
      card.append(footer, status, modelGrade); host.append(card);
      function result(ok) {
        feedback.textContent = ok ? t.correct : t.incorrect;
        feedback.classList.toggle("is-right", !!ok);
        if (ok) { remember(item); top.querySelector(".challenge-counter").textContent = t.solved + " " + count() + " / " + challenges.length;
          var tile = picker.querySelector(".challenge-tile.is-current"); if (tile && !tile.textContent.includes("✓")) { tile.textContent += " ✓"; } }
      }
      function revealNow() {
        reveal.hidden = false; why.hidden = false;
        if (mode === "describe" && item.direction === "name") {
          task.querySelectorAll(".challenge-description-option").forEach(function (row, i) {
            row.classList.toggle("is-answer", i === item.answer_index);
          });
          task.querySelectorAll(".challenge-description-note").forEach(function (note, i) {
            note.hidden = i === item.answer_index;
          });
        }
        if (mode === "induce") {
          task.querySelectorAll(".challenge-induce-query").forEach(function (box, i) {
            box.value = scalar(item.queries[i].answer);
          });
        }
        if (mode === "wrongstep" || mode === "deadbranch") {
          var target = mode === "wrongstep" ? item.wrong_index : item.branches.findIndex(function (b) { return b.dead; });
          task.querySelectorAll(".challenge-select-row").forEach(function (row, i) { row.classList.toggle("is-answer", i === target); });
        }
        if (mode === "ripple") {
          task.querySelectorAll('input[type="checkbox"]').forEach(function (box, i) {
            var row = box.closest("label"), correct = box.checked === item.items[i].changed;
            row.classList.toggle("is-right", correct);
            row.classList.toggle("is-wrong", !correct);
            var mark = row.querySelector(".challenge-choice-mark");
            if (!mark) { mark = el("strong", "challenge-choice-mark"); row.append(mark); }
            mark.textContent = correct ? "✓" : "✗";
            mark.setAttribute("aria-label", correct ? t.correct : t.incorrect);
          });
        }
        fillReveal(reveal, mode, item, lang, t);
      }
      var handler = renderTask(task, mode, item, lang, t, controls, result, revealNow);
      check.onclick = function () {
        feedback.textContent = t.waiting;
        Promise.resolve(handler()).then(function (outcome) { if (outcome === null) { feedback.textContent = t.needCheck; }
          else { var ok = typeof outcome === "object" ? outcome.ok : outcome;
            result(ok); if (outcome && outcome.message) { feedback.textContent = outcome.message; }
            if (ok) { revealNow(); } } }).catch(function () { feedback.textContent = t.needCheck; });
      };
      task.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && event.target.tagName === "INPUT" && event.target.type !== "checkbox" && event.target.type !== "radio") {
          event.preventDefault(); check.click();
        }
      });
      showAnswer.onclick = function () { revealNow(); feedback.textContent = ""; };
    }
    render();
  }

  function renderTask(task, mode, item, lang, t, controls) {
    var choice, input;
    function heading(text) { task.append(el("h2", "challenge-heading", text)); }
    function textInput(label, multiline) {
      var field = el("label", "challenge-label", label), box = el(multiline ? "textarea" : "input", "challenge-input");
      if (!multiline) { box.type = "text"; box.autocomplete = "off"; }
      field.append(box); task.append(field); return box;
    }
    if (mode === "wrongstep" || mode === "deadbranch") {
      heading(mode === "wrongstep" ? (lang === "zh" ? "找出第一步错误" : "Find the first wrong line") : (lang === "zh" ? "哪条分支不会运行？" : "Which branch cannot run?"));
      if (item.question) { task.append(el("p", "challenge-question", item.question)); }
      var entries = mode === "wrongstep" ? item.steps : item.branches;
      var list = el("div", "challenge-option-list");
      entries.forEach(function (entry, i) {
        var row = button("", "challenge-select-row" + (mode === "wrongstep" ? " challenge-wrongstep-row" : ""),
          function () { choice = i; list.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", String(b === row)); }); });
        row.append(el("span", "challenge-wrongstep-expression", (i + 1) + ". " + (mode === "wrongstep" ? entry.expr : entry.text)));
        if (mode === "wrongstep" && entry.rule) {
          var fired = item.rules.some(function (rule) { return rule.symbol === entry.rule; });
          row.append(el("span", fired ? "challenge-symbol challenge-step-symbol" : "challenge-step-start", entry.rule));
        }
        row.setAttribute("aria-pressed", "false"); list.append(row);
      }); task.append(list);
      return function () { return choice === (mode === "wrongstep" ? item.wrong_index : item.branches.findIndex(function (b) { return b.dead; })); };
    }
    if (mode === "hole") {
      heading(item.question + " = " + item.target);
      task.append(el("p", "challenge-domain", lang === "zh" ? "在" + domainText(item.domain, lang) + "之间求 x。" :
        "Find x between " + item.domain[0] + " and " + item.domain[1] + "."));
      input = textInput("x", false); input.inputMode = "numeric";
      return function () { return input.value.trim() !== "" && Number.isInteger(Number(input.value)) && Number(input.value) === item.answer; };
    }
    if (mode === "ripple") {
      heading(lang === "zh" ? "哪些值会改变？" : "Which values change?");
      if (item.input) { task.append(el("p", "challenge-domain", (lang === "zh" ? "输入：" : "Inputs: ") + inputsText(item.input))); }
      var edit = el("div", "challenge-edit"); edit.append(el("span", "challenge-rule-text", item.edit.before), el("span", "challenge-edit-arrow", "→"));
      var after = el("span", "challenge-rule-text"); highlightChange(after, item.edit.before, item.edit.after); edit.append(after); task.append(edit);
      var checks = [];
      item.items.forEach(function (entry, i) { checks.push(labelInput(task, (i + 1) + ". " + entry.expr, "checkbox", "ripple", entry.expr)); });
      return function () { return checks.every(function (check, i) { return check.checked === item.items[i].changed; }); };
    }
    if (mode === "laws" || mode === "equiv") {
      if (mode === "laws") { heading(lawQuestion(item, lang)); }
      else {
        var question = el("h2", "challenge-heading");
        question.append(document.createTextNode(lang === "zh" ? "对" : "Is "));
        code(question, item.left);
        question.append(document.createTextNode(lang === "zh" ? " 与 " : " always equal to "));
        code(question, item.right);
        question.append(document.createTextNode(lang === "zh" ? "，当 a 和 b 都" + domainText(item.domain, lang) + "时，是否始终相等？" :
          ", for every a and b " + domainText(item.domain, lang) + "?")); task.append(question);
      }
      var choices = el("div", "challenge-choice-row");
      var yes = labelInput(choices, mode === "laws" ? t.holds : t.same, "radio", "decision", "yes");
      var no = labelInput(choices, mode === "laws" ? t.fails : t.different, "radio", "decision", "no"); task.append(choices);
      input = textInput(t.inputs, false); input.placeholder = "1, 2";
      return function () {
        if (!yes.checked && !no.checked) { return false; }
        if (yes.checked) { return mode === "laws" ? item.holds : item.same; }
        if (mode === "laws" ? item.holds : item.same) { return false; }
        var values = readInputs(input); if (!values) { return false; }
        var stored = item.counterexample && same(values, item.counterexample.inputs);
        if (mode === "equiv") { return evaluatePair(item, item.left, item.right, values, !!stored); }
        var sides = item.statement.split(/\s*=\s*/);
        if (sides.length !== 2) { return !!stored; }
        return evaluatePair(item, sides[0], sides[1], values, !!stored);
      };
    }
    if (mode === "translate") {
      heading(t.structure); task.append(el("p", "challenge-question", item.skeleton));
      var source = el("div", "challenge-translation-world"); source.append(el("strong", "", t.source + " · " + item.source_world), el("code", "", item.source.expression));
      renderWorldValue(source, item.source_world, item.source.output); task.append(source);
      task.append(el("h3", "challenge-heading", t.target + " · " + item.target_world + " · " + item.target.expression));
      var options = el("div", "challenge-value-options");
      item.target.options.forEach(function (value, i) {
        var option = button(String(i + 1), "challenge-value-option", function () { choice = i;
          options.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", String(b === option)); }); });
        option.setAttribute("aria-pressed", "false"); renderWorldValue(option, item.target_world, value); options.append(option);
      }); task.append(options);
      return function () { return choice !== undefined && same(item.target.options[choice], item.target.answer); };
    }
    if (mode === "describe") {
      if (item.direction === "name") {
        heading(lang === "zh" ? "哪段话与这条规则相符？" : "Which description matches this rule?");
        task.append(el("code", "challenge-description-rule", item.rule.text));
        var descriptions = el("div", "challenge-description-options");
        (lang === "zh" ? item.options_zh || item.options : item.options).forEach(function (option, i) {
          var card = el("div", "challenge-description-card");
          var row = button((i + 1) + ". " + option, "challenge-select-row challenge-description-option", function () {
            choice = i;
            descriptions.querySelectorAll("button").forEach(function (entry) { entry.setAttribute("aria-pressed", String(entry === row)); });
          });
          row.setAttribute("aria-pressed", "false"); card.append(row);
          var note = el("p", "challenge-description-note", lang === "zh" ?
            (item.option_notes_zh || item.option_notes)[i] : item.option_notes[i]);
          note.hidden = true; card.append(note); descriptions.append(card);
        });
        task.append(descriptions);
        return function () { return choice === item.answer_index; };
      }
      heading(lang === "zh" ? "根据描述写出规则" : "Write the rule from the description");
      task.append(el("p", "challenge-question", lang === "zh" ? item.description_zh || item.description : item.description));
      task.append(el("p", "challenge-domain", (lang === "zh" ? "符号：" : "Symbol: ") + item.symbol +
        (lang === "zh" ? "，元数：" : ", arity: ") + item.arity + "，" + domainText(item.domain, lang)));
      input = textInput(lang === "zh" ? "规则定义" : "Rule definition", false);
      input.placeholder = item.reference.split("=")[0].trim() + " = { … }";
      return function () { return checkApi().then(function (api) {
        if (!api) { return null; }
        return api.equivalent(rules(item).concat([item.reference]), item.symbol, input.value.trim(), item.domain).then(function (proof) {
          return {ok: proof.equivalent, message: proof.equivalent ? (lang === "zh" ? "规则等价：已解出。" : "Equivalent rule: solved") :
            (lang === "zh" ? "规则还不等价。" : "The rule is not equivalent yet.")};
        }).catch(function () { return {ok: false, message: lang === "zh" ? "请写出有效的规则定义。" : "Write a valid rule definition."}; });
      }); };
    }
    if (mode === "target") {
      heading(lang === "zh" ? "凑出 " + item.target : "Reach " + item.target);
      task.append(el("p", "challenge-domain", lang === "zh" ? "每个数字最多使用一次。" : "Use each number at most once."));
      var palette = el("div", "challenge-target-palette");
      var numberRow = el("div", "challenge-target-tiles");
      var operatorRow = el("div", "challenge-target-tiles");
      input = textInput(lang === "zh" ? "表达式" : "Expression", false);
      function appendToken(token) {
        var start = input.selectionStart, end = input.selectionEnd;
        var before = input.value.slice(0, start), after = input.value.slice(end);
        var pad = /[\d\w]$/.test(before) && /^[\d\w]/.test(token) ? " " : "";
        input.value = before + pad + token + after;
        input.dispatchEvent(new Event("input", {bubbles: true}));
        input.focus(); input.setSelectionRange((before + pad + token).length, (before + pad + token).length);
      }
      item.numbers.forEach(function (number, i) {
        var tile = button(String(number), "challenge-target-tile", function () { appendToken(String(number)); });
        tile.setAttribute("aria-label", (lang === "zh" ? "插入数字 " : "Insert number ") + number + " " + (i + 1));
        numberRow.append(tile);
      });
      item.allowed.concat(["(", ")"]).forEach(function (symbol) {
        var tile = button(symbol, "challenge-target-tile challenge-target-operator", function () { appendToken(symbol); });
        var definition = item.rules.find(function (rule) { return rule.symbol === symbol; });
        tile.title = definition ? definition.text : operatorName(symbol, lang) ||
          (symbol === "(" ? (lang === "zh" ? "左括号" : "open parenthesis") : (lang === "zh" ? "右括号" : "close parenthesis"));
        operatorRow.append(tile);
      });
      input.addEventListener("input", function () {
        var used = window.OpulseChallengeAnswers.targetTokens(item, input.value).used;
        numberRow.querySelectorAll("button").forEach(function (tile, i) {
          var occupied = (used[item.numbers[i]] || 0) > item.numbers.slice(0, i + 1).filter(function (n) { return n === item.numbers[i]; }).length - 1;
          tile.disabled = occupied; tile.classList.toggle("is-used", occupied);
        });
      });
      palette.append(numberRow, operatorRow); task.append(palette);
      return function () {
        var parsed = window.OpulseChallengeAnswers.parseAnswer("target", item, "Expression: " + input.value);
        return Promise.resolve(window.OpulseChallengeAnswers.gradeAnswer("target", item, parsed)).then(function (verdict) {
          return {ok: verdict.correct, message: lang === "zh" ? verdict.detail_zh || verdict.detail : verdict.detail};
        });
      };
    }
    if (mode === "induce") {
      heading(lang === "zh" ? "观察例子，预测结果" : "Study the examples and predict the outputs");
      if (item.domain) { task.append(el("p", "challenge-domain", lang === "zh" ? "输入范围：" + domainText(item.domain, lang) :
        "Inputs " + domainText(item.domain, lang))); }
      if (!window.OpulseCheck) { task.append(el("p", "challenge-domain", t.needCheck)); }
      if (item.atoms && item.atoms.length) {
        var atomList = el("div", "challenge-atom-list");
        atomList.append(el("span", "challenge-domain", lang === "zh" ? "原子运算：" : "Atoms:"));
        item.atoms.forEach(function (atom) {
          var symbol = typeof atom === "string" ? atom : atom.symbol;
          var chip = el("span", "challenge-atom-chip");
          chip.append(el("code", "", symbol), document.createTextNode("  " +
            (typeof atom === "string" ? (operatorName(symbol, lang) || symbol) :
              (lang === "zh" ? atom.plain_zh : atom.plain))));
          atomList.append(chip);
        }); task.append(atomList);
      }
      if (item.known) { task.append(el("p", "challenge-domain", (lang === "zh" ? "已知：" : "Known: ") +
        item.known.map(function (entry) { return typeof entry === "string" ? entry : JSON.stringify(entry); }).join(" · "))); }
      var tableWrap = el("div", "challenge-table-scroll"), table = el("table", "challenge-induce-table");
      var head = el("thead"), header = el("tr");
      (item.examples[0].inputs || []).forEach(function (_, i) { var cell = el("th", "", "abcdefghijklmnopqrstuvwxyz"[i] || String(i + 1)); cell.scope = "col"; header.append(cell); });
      var outputHead = el("th", "", lang === "zh" ? "输出" : "Output"); outputHead.scope = "col"; header.append(outputHead);
      head.append(header); table.append(head);
      var body = el("tbody");
      item.examples.forEach(function (example) {
        var row = el("tr"); example.inputs.forEach(function (value) { row.append(el("td", "", scalar(value))); });
        row.append(el("td", "", scalar(example.output))); body.append(row);
      });
      var boxes = [];
      item.queries.forEach(function (query, i) {
        var row = el("tr", "challenge-induce-query-row");
        query.inputs.forEach(function (value) { row.append(el("td", "", scalar(value))); });
        var cell = el("td"), box = el("input", "challenge-input challenge-induce-query");
        box.type = "text"; box.inputMode = "numeric"; box.autocomplete = "off";
        box.setAttribute("aria-label", t.query + " " + (i + 1) + " · " + inputsText(query.inputs));
        cell.append(box); row.append(cell); body.append(row); boxes.push(box);
      });
      table.append(body); tableWrap.append(table); task.append(tableWrap);
      var rule = textInput(t.optional, true);
      var ruleStatus = el("p", "challenge-domain"); ruleStatus.setAttribute("role", "status"); task.append(ruleStatus);
      return function () { return checkApi().then(function (api) {
        if (!api) { return null; }
        var head = item.reference_definition.split("=")[0].trim();
        var symbol = item.symbol || head.split(/\s+/).filter(function (part) { return !/^[abcxyz]$/.test(part); })[0];
        var queryChecks = item.queries.map(function (query, i) {
          var args = query.inputs.map(scalar);
          var expression = query.expression || (args.length === 1 ? args[0] + " " + symbol : args[0] + " " + symbol + " " + args[1]);
          return api.evaluate(rules(item).concat([item.reference_definition]), expression).then(function (result) {
            return scalar(result.value) === boxes[i].value.trim() && scalar(result.value) === scalar(query.answer);
          });
        });
        return Promise.all(queryChecks).then(function (checks) {
          if (!checks.every(Boolean)) { return false; }
          if (!rule.value.trim()) { return true; }
          return api.equivalent(rules(item), symbol, rule.value.trim(), item.domain)
            .then(function (proof) {
              ruleStatus.textContent = proof.equivalent ?
                (lang === "zh" ? "规则也等价。" : "Your rule is equivalent too.") :
                (lang === "zh" ? "预测正确；规则还不等价。" : "Predictions are correct; the rule is not equivalent yet.");
              return true;
            }, function () { ruleStatus.textContent = t.needCheck; return true; });
        });
      }); };
    }
    if (mode === "shorten") {
      heading(lang === "zh" ? "改写 " + item.symbol + "，使它在这几组输入上结果不变，总步数不超过 " + item.budget_steps +
        "（现在是 " + item.steps + " 步）：" + inputTuplesText(item.inputs) + "。" :
        "Rewrite " + item.symbol + " so that it computes the same results in at most " + item.budget_steps +
        " steps. It takes " + item.steps + " steps now on these inputs: " + inputTuplesText(item.inputs) + ".");
      task.append(el("p", "challenge-domain", lang === "zh" ?
        "还须对" + domainText(item.domain, lang) + "的所有输入等价。原定义含 " + item.size + " 个运算符。" :
        "It must also match every input " + domainText(item.domain, lang) + ". Original operator count: " + item.size + "."));
      if (!window.OpulseCheck) { task.append(el("p", "challenge-domain", t.needCheck)); }
      task.append(el("p", "challenge-question", item.text)); input = textInput(t.answer, true);
      return function () { return checkApi().then(function (api) {
        if (!api) { return null; }
        return window.OpulseChallengeAnswers.gradeAnswer("shorten", item, {ok: true, value: input.value.trim()})
          .then(function (verdict) {
            var message = verdict.detail;
            if (lang === "zh") {
              if (verdict.kind === "solved") { message = "结果相同，" + verdict.steps + " 步（预算 " + item.budget_steps + " 步）：已解出"; }
              else if (verdict.kind === "over_budget") { message = "结果相同，但用了 " + verdict.steps + " 步；预算是 " + item.budget_steps + " 步"; }
              else if (verdict.kind === "different" && verdict.counterexample && verdict.counterexample.inputs) {
                var c = verdict.counterexample;
                message = "当 " + c.inputs.map(function (v, i) { return "abcd"[i] + " = " + scalar(v); }).join("，") +
                  " 时结果不同：你的结果是 " + scalar(c.got) + "，规则结果是 " + scalar(c.expected);
              }
            }
            return {ok: verdict.correct, message: message};
          });
      }); };
    }
    return function () { return false; };
  }

  function highlightChange(node, before, after) {
    var start = 0; while (start < before.length && start < after.length && before[start] === after[start]) { start++; }
    var end = 0; while (end < before.length - start && end < after.length - start &&
      before[before.length - 1 - end] === after[after.length - 1 - end]) { end++; }
    node.append(document.createTextNode(after.slice(0, start)), el("ins", "", after.slice(start, after.length - end)),
      document.createTextNode(after.slice(after.length - end)));
  }
  function fillReveal(section, mode, item, lang, t) {
    section.replaceChildren();
    if (!(mode === "describe" && item.direction === "name")) {
      section.append(el("h2", "challenge-heading", t.explanation));
    }
    if (mode === "wrongstep") {
      section.append(el("p", "challenge-reveal-text", lang === "zh" ?
        "第 " + (item.wrong_index + 1) + " 行有误：应为 " + item.correct_expr + "。" :
        "Line " + (item.wrong_index + 1) + " is wrong: it should be " + item.correct_expr + "."));
      section.append(el("p", "challenge-reveal-text", item.wrong_reason.replace(/; -?\d+ reverses the operands\./,
        "; the operands were reversed.")));
      var list = el("div", "challenge-step-view"); section.append(el("h3", "challenge-heading", t.replay), list);
      var viewer = null;
      function addSteps(steps) {
        if (viewer) viewer.destroy();
        var rows = steps.map(function (step) { return typeof step === "string" ? {expr: step} : step; });
        var normalized = rows.length && (rows[0].before !== undefined || rows[0].expr_before !== undefined) ?
          rows.map(function (step) { return {expr_before: step.before || step.expr_before,
            expr_after: step.after || step.expr_after, focus: step.focus, new: step.new,
            kind: step.kind, rule: step.rule || step.symbol || "·"}; }) :
          rows.slice(1).map(function (step, i) {
            return {expr_before: rows[i].expr || rows[i].after || "", expr_after: step.expr || step.after || "",
              kind: step.kind || (step.rule ? "expand" : "eval"), rule: step.rule || "·"};
          });
        viewer = window.OpulseStepView.render(list, {steps: normalized, page_size: 50, lang: lang});
      }
      addSteps(item.correct_steps || item.steps.slice(0, item.wrong_index).concat([{expr: item.correct_expr}]));
      checkApi().then(function (api) { if (api) { return api.evaluate(rules(item), item.question).then(function (result) {
        if (Array.isArray(result.steps) && result.steps.length && list.isConnected) { addSteps(result.steps); }
      }).catch(function () {}); } });
    } else if (mode === "hole") {
      section.append(el("p", "challenge-reveal-text", "x = " + item.answer + ". " + t.unique));
      var strip = el("div", "challenge-scan"); strip.setAttribute("aria-label", t.scan + " " + item.domain.join(" to "));
      (item.scan || []).forEach(function (cell, i) {
        var node = el("div", "challenge-scan-cell", cell.x + " → " + cell.value);
        node.style.setProperty("--scan-hue", String((Math.abs(Number(cell.value)) * 37) % 300));
        if (cell.x === item.answer) { node.classList.add("is-hit"); }
        node.style.setProperty("--scan-order", String(i)); strip.append(node);
      }); section.append(strip);
    } else if (mode === "ripple") {
      item.items.forEach(function (entry) {
        var row = el("div", "challenge-ripple-result"); row.append(el("strong", "", entry.changed ? t.changed + " ✓" : t.unchanged + " ✓"),
          el("code", "", entry.expr), el("span", "", t.before + ": " + scalar(entry.before) + " → " + t.after + ": " + scalar(entry.after)));
        section.append(row);
      });
    } else if (mode === "laws" || mode === "equiv") {
      var isSame = mode === "laws" ? item.holds : item.same;
      var c = item.counterexample;
      section.append(el("p", "challenge-reveal-text", isSame ?
        (lang === "zh" ? "相同：" + (item.proof === "z3" ? "z3 已证明" : "已检查范围内每组输入") :
          "Same: " + (item.proof === "z3" ? "proved by z3" : "checked every input in the range")) :
        (lang === "zh" ? "不同：当 " + c.inputs.map(function (v, i) { return "abc"[i] + " = " + scalar(v); }).join("，") +
          " 时，左边得到 " + scalar(c.left) + "，右边得到 " + scalar(c.right) :
          "Different: at " + c.inputs.map(function (v, i) { return "abc"[i] + " = " + scalar(v); }).join(", ") +
          ", the left side gives " + scalar(c.left) + " and the right side gives " + scalar(c.right))));
    } else if (mode === "deadbranch") {
      section.append(el("p", "challenge-reveal-text", item.branches.find(function (b) { return b.dead; }).text));
      section.append(el("p", "challenge-reveal-text", item.reason + " · " + t.proof + ": " + item.proof));
    } else if (mode === "translate") {
      section.append(el("p", "challenge-reveal-text", t.structure + ": " + item.skeleton));
      section.append(el("p", "challenge-reveal-text", lang === "zh" ?
        "两边在相同的树节点执行运算；叶子值和运算材料换成目标世界。" :
        "Both worlds apply operations at the same tree nodes; the leaves and operations use the target world's material."));
      renderWorldValue(section, item.target_world, item.target.answer);
    } else if (mode === "induce") {
      section.append(el("p", "challenge-reveal-text", t.reference + ": " + item.reference_definition));
    } else if (mode === "describe") {
      if (item.direction !== "name") { section.append(el("p", "challenge-reveal-text", t.reference + ": " + item.reference)); }
    } else if (mode === "target") {
      section.append(el("p", "challenge-reveal-text", (lang === "zh" ? "一种解法：" : "One solution: ") + item.solution));
      section.append(el("p", "challenge-reveal-text", (lang === "zh" ? "在限定大小内找到的不同表达式：" : "Distinct expressions found up to the size limit: ") + item.solutions_count));
    } else if (mode === "shorten") {
      section.append(el("p", "challenge-reveal-text", t.reference + ": " + item.reference));
      section.append(el("p", "challenge-reveal-text", lang === "zh" ?
        "参考定义：" + item.reference_steps + " 步（预算 " + item.budget_steps + " 步）。" :
        "Reference: " + item.reference_steps + " steps (budget " + item.budget_steps + ")."));
      var tableWrap = el("div", "challenge-table-scroll");
      var table = el("table", "challenge-shorten-steps");
      var header = el("tr");
      [lang === "zh" ? "输入" : "Inputs", lang === "zh" ? "原定义步数" : "Original steps",
        lang === "zh" ? "参考定义步数" : "Reference steps"].forEach(function (label, i) {
        var cell = el("th", i ? "challenge-number-cell" : "", label); cell.scope = "col"; header.append(cell);
      });
      var head = el("thead"); head.append(header); table.append(head);
      var body = el("tbody"); table.append(body); tableWrap.append(table); section.append(tableWrap);
      checkApi().then(function (api) {
        if (!api) { return; }
        return Promise.all([api.steps(rules(item), item.text, item.inputs),
          api.steps(rules(item), item.reference, item.inputs)]).then(function (counts) {
          if (counts.some(function (count) { return count.parse_error || !Array.isArray(count.per_input) ||
            count.per_input.length !== item.inputs.length; })) { return; }
          var totals = [0, 0];
          item.inputs.forEach(function (point, i) {
            var row = el("tr");
            var original = counts[0].per_input[i].steps, reference = counts[1].per_input[i].steps;
            totals[0] += original; totals[1] += reference;
            ["(" + inputsText(point) + ")", original, reference].forEach(function (value, j) {
              row.append(el("td", j ? "challenge-number-cell" : "", value));
            });
            body.append(row);
          });
          var foot = el("tfoot"), totalRow = el("tr");
          var totalLabel = el("th", "", lang === "zh" ? "合计" : "Total"); totalLabel.scope = "row";
          totalRow.append(totalLabel);
          totals.forEach(function (value) { totalRow.append(el("td", "challenge-number-cell", value)); });
          foot.append(totalRow); table.append(foot);
        });
      }).catch(function () { body.append(el("tr", "", t.needCheck)); });
    }
  }
  if (typeof module !== "undefined" && module.exports) { module.exports = {promptFor: promptFor, atomTexts: atomTexts, atomWorld: atomWorld}; }
  if (typeof window !== "undefined") { window.OpulseChallengeModes = { boot: boot, renderTask: renderTask }; }
}());
