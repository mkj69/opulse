(function () {
  "use strict";

  // Kept pure so the same share-link rules can be checked without a browser.
  function parseShare(search, challenges) {
    var params = new URLSearchParams(search || "");
    var requested = params.get("c");
    var index = challenges.findIndex(function (item) { return item.id === requested; });
    return { mode: params.get("mode") || "compute", index: index < 0 ? 0 : index,
      variant: params.get("v") === "1" ? 1 : 0 };
  }
  if (typeof document === "undefined" && typeof module === "undefined") { return; }
  var script = typeof document !== "undefined" && document.currentScript && document.currentScript.src;
  var scalesPromise;
  function ensureScales() {
    if (window.OpulseScales) { return Promise.resolve(window.OpulseScales); }
    if (!scalesPromise) {
      scalesPromise = new Promise(function (resolve, reject) {
        var loader = document.createElement("script");
        loader.src = new URL("scales-core.js", script).href;
        loader.onload = function () { window.OpulseScales ? resolve(window.OpulseScales) : reject(new Error("Scale loader unavailable")); };
        loader.onerror = function () { reject(new Error("Scale loader unavailable")); };
        document.head.append(loader);
      }).catch(function (error) { scalesPromise = null; throw error; });
    }
    return scalesPromise;
  }
  var words = {
    en: {
      rules: "Rules", hint: "hint", question: "What is the value?", answer: "Your answer",
      check: "Check", show: "Show me", right: "Correct: {answer}. Nice work!", wrong: "You said {guess}. The answer is {answer}.",
      shown: "Here is how it works.", steps: "Step by step", start: "start", was: "was",
      checked: "Checked by the interpreter", changed: "Changed rule", change: "Change one rule",
      predict: "Same question. What is the new answer?", whyLabel: "Why this one",
      model: "Try it on your model", share: "Share", next: "Next challenge", previous: "Previous challenge",
      all: "All challenges", search: "Filter rules by symbol", direct: "In the question", layer: "Layer",
      directChanged: "In the question · changed rule",
      short: "Short", full: "Full unfolding", first: "First", last: "Last", pageNext: "Next", pagePrevious: "Previous", go: "Go to step",
      goAction: "Go",
      promptLong: "This prompt is long: about {count} characters, including every rule.", fromSet: "from a set of {count} operators",
      ruleCount: "{count} rules", fullCount: "{count} steps", stepCounts: "{short} short steps · {full} full steps",
      affected: "Changing this one rule changes {count} of {total} rules.", stepOf: "Step {step} of {total}",
      loadingSteps: "Loading full unfolding…", stepsFail: "Could not load the full unfolding.",
      moreRules: "Show more rules",
      copied: "Copied", copyFail: "Could not copy. Please select and copy the text below.",
      solved: "Solved", of: "of", loadingFail: "The challenges could not load. Please try again later.",
      promptRules: "Rules:", promptQuestion: "Question:", promptEnd: "Answer format:\nAnswer: <integer or NaN>\nPut nothing else on the Answer line.",
      paste: "Paste the model's answer", grade: "Grade", parsed: "Parsed answer", verdict: "Verdict", modelCorrect: "Correct.", modelIncorrect: "Incorrect.",
      puzzle: "Challenge", level: { easy: "Easy", medium: "Medium", hard: "Hard", expert: "Expert", master: "Master", legend: "Legend" }
    },
    zh: {
      rules: "规则", hint: "提示", question: "结果是多少？", answer: "你的答案",
      check: "检查", show: "看看答案", right: "正确：{answer}。做得好！", wrong: "你答的是 {guess}。正确答案是 {answer}。",
      shown: "计算过程如下。", steps: "一步步计算", start: "开始", was: "原来是",
      checked: "参考解释器已核对", changed: "修改后的规则", change: "修改一条规则",
      predict: "题目没变。现在结果是多少？", whyLabel: "这题的看点",
      model: "复制给你的模型", share: "分享", next: "下一题", previous: "上一题",
      all: "所有挑战", search: "按符号筛选规则", direct: "题目直接使用", layer: "第",
      directChanged: "题目直接使用 · 修改的规则",
      short: "简短", full: "完整展开", first: "首页", last: "末页", pageNext: "下一页", pagePrevious: "上一页", go: "跳到步骤",
      goAction: "跳转",
      promptLong: "提示很长，约 {count} 个字符，包含所有规则。", fromSet: "来自 {count} 个算子的集合",
      ruleCount: "{count} 条规则", fullCount: "{count} 步", stepCounts: "简短 {short} 步 · 完整 {full} 步",
      affected: "修改这一条规则会影响 {total} 条规则中的 {count} 条。", stepOf: "第 {step} 步，共 {total} 步",
      loadingSteps: "正在加载完整展开…", stepsFail: "无法加载完整展开。",
      moreRules: "显示更多规则",
      copied: "已复制", copyFail: "无法自动复制，请选中下方文字手动复制。",
      solved: "已解出", of: "/", loadingFail: "题目加载失败，请稍后重试。",
      promptRules: "规则：", promptQuestion: "问题：", promptEnd: "回答格式：\nAnswer: <integer or NaN>\n答案行不要写其他内容。",
      paste: "粘贴模型的回答", grade: "评分", parsed: "解析答案", verdict: "判定", modelCorrect: "答对了。", modelIncorrect: "不正确。",
      puzzle: "第", level: { easy: "简单", medium: "中等", hard: "困难", expert: "专家", master: "大师", legend: "传奇" }
    }
  };

  function computePrompt(item, variant, lang, atomLines) {
    var t = words[lang === "zh" ? "zh" : "en"];
    return (atomLines || "") + t.promptRules + "\n" + item.rules.map(function (rule, i) {
      return variant && i === item.variant.rule_index ? item.variant.after : rule.text;
    }).join("\n") + "\n\n" + t.promptQuestion + " " + item.question + "\n" + t.promptEnd;
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { parseShare: parseShare, computePrompt: computePrompt };
  }
  if (typeof document === "undefined") { return; }

  function make(tag, className, value) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (value !== undefined) { node.textContent = value; }
    return node;
  }

  function init(root, data) {
    if (!data || data.schema !== "opulse.challenge/1" || !Array.isArray(data.challenges) || !data.challenges.length) {
      throw new Error("Invalid challenge data");
    }
    var order = { easy: 0, medium: 1, hard: 2, expert: 3, master: 4, legend: 5 };
    var challenges = data.challenges.slice().sort(function (a, b) { return order[a.level] - order[b.level]; });
    var lang = root.dataset.lang === "zh" ? "zh" : "en";
    var t = words[lang];
    var shared = parseShare(location.search, challenges);
    var index = shared.index;
    var variant = shared.variant;
    var timer = null;
    var copyTimer = null;
    var ruleSearchTimer = null;
    var pickerOpen = !matchMedia("(max-width: 40rem)").matches;
    var stepMode = "short";
    var fullExample = null;
    var fullRequest = 0;
    var seenComplexKind = false;
    var solved = [];
    try {
      var stored = JSON.parse(localStorage.getItem("opulse.challenge.solved") || "[]");
      if (Array.isArray(stored)) { solved = stored.filter(function (id) { return typeof id === "string"; }); }
    } catch (_) { solved = []; }

    function current() { return challenges[index]; }
    function isLegend() { return current().level === "legend"; }
    function isBig() { return current().level === "expert" || current().level === "master" || isLegend(); }
    function steps() {
      var record = variant ? current().variant : current();
      return isLegend() || (isBig() && stepMode === "short") ? record.coarse_steps : record.steps;
    }
    function format(template, values) {
      return template.replace(/\{(count|short|full|total|step)\}/g, function (_, key) { return values[key]; });
    }
    function answer() { return Number(variant ? current().variant.answer : current().answer); }
    function ruleText(ruleIndex) {
      return variant && ruleIndex === current().variant.rule_index ? current().variant.after : current().rules[ruleIndex].text;
    }
    function link() {
      var url = new URL(location.href);
      url.searchParams.set("mode", "compute");
      url.searchParams.set("c", current().id);
      url.searchParams.set("v", String(variant));
      return url.href;
    }
    function updateUrl() {
      try { history.replaceState(null, "", link()); } catch (_) { /* File previews can deny history edits. */ }
    }
    function select(newIndex) {
      index = newIndex;
      variant = 0;
      stepMode = "short";
      fullRequest++;
      fullExample = null;
      updateUrl();
      render();
      root.querySelector(".challenge-input").focus();
    }
    function prompt() {
      return window.OpulseAtoms.promptLines("integer", current().rules.map(function (_, i) { return ruleText(i); })
        .concat([current().question]), lang).then(function (atomLines) {
          return computePrompt(current(), variant, lang, atomLines);
        });
    }
    function message(template, values) {
      return template.replace(/\{(answer|guess)\}/g, function (_, key) { return values[key]; });
    }
    function count() {
      return solved.filter(function (id) { return challenges.some(function (item) { return item.id === id; }); }).length;
    }
    function remember() {
      if (solved.indexOf(current().id) < 0) {
        solved.push(current().id);
        try { localStorage.setItem("opulse.challenge.solved", JSON.stringify(solved)); } catch (_) { /* Storage may be disabled. */ }
      }
    }
    function changedText(node, before, after) {
      var prefix = 0;
      while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) { prefix++; }
      var suffix = 0;
      while (suffix < before.length - prefix && suffix < after.length - prefix &&
             before[before.length - 1 - suffix] === after[after.length - 1 - suffix]) { suffix++; }
      // Include the whole operator when the change inserts a character, as in > to >=.
      if (prefix === before.length - suffix && prefix > 0 && /[<>=!]/.test(before[prefix - 1])) {
        while (prefix > 0 && /[<>=!]/.test(before[prefix - 1])) { prefix--; }
      }
      node.append(document.createTextNode(after.slice(0, prefix)));
      var oldPart = before.slice(prefix, before.length - suffix);
      var newPart = after.slice(prefix, after.length - suffix);
      if (newPart) { node.append(make("ins", "", newPart)); }
      node.append(document.createTextNode(after.slice(after.length - suffix)));
      return oldPart;
    }
    function copy(text, status, fallback) {
      if (copyTimer) { clearTimeout(copyTimer); copyTimer = null; }
      function failed() {
        status.textContent = t.copyFail;
        status.hidden = false;
        fallback.hidden = false;
        fallback.value = text;
        fallback.focus();
        fallback.select();
      }
      if (!navigator.clipboard || !navigator.clipboard.writeText) { failed(); return; }
      try {
        navigator.clipboard.writeText(text).then(function () {
          status.textContent = t.copied;
          status.hidden = false;
          fallback.hidden = true;
          copyTimer = setTimeout(function () { status.hidden = true; copyTimer = null; }, 2500);
        }, failed);
      } catch (_) { failed(); }
    }
    function render() {
      fullRequest++;
      fullExample = null;
      if (ruleSearchTimer) { clearTimeout(ruleSearchTimer); ruleSearchTimer = null; }
      if (timer) { clearTimeout(timer); timer = null; }
      if (copyTimer) { clearTimeout(copyTimer); copyTimer = null; }
      root.replaceChildren();
      var picker = make("section", "challenge-picker");
      var pickerToggle = make("button", "challenge-picker-toggle", t.all + " ▾");
      pickerToggle.type = "button";
      pickerToggle.setAttribute("aria-expanded", String(pickerOpen));
      pickerToggle.setAttribute("aria-controls", "challenge-picker-groups");
      var groups = make("div", "challenge-picker-groups");
      groups.id = "challenge-picker-groups";
      groups.hidden = !pickerOpen;
      ["easy", "medium", "hard", "expert", "master", "legend"].forEach(function (name) {
        var entries = challenges.map(function (item, i) { return { item: item, index: i }; })
          .filter(function (entry) { return entry.item.level === name; });
        if (!entries.length) { return; }
        var group = make("div", "challenge-picker-group");
        group.append(make("h2", "challenge-picker-heading", t.level[name]));
        var grid = make("div", "challenge-picker-grid");
        entries.forEach(function (entry, number) {
          var tile = make("button", "challenge-tile challenge-tile-" + name,
            String(number + 1) + (solved.indexOf(entry.item.id) >= 0 ? " ✓" : ""));
          tile.type = "button";
          tile.title = t.level[name] + " " + (number + 1);
          tile.setAttribute("aria-label", tile.title + (solved.indexOf(entry.item.id) >= 0 ? ", " + t.solved : ""));
          if (entry.index === index) { tile.classList.add("is-current"); tile.setAttribute("aria-current", "true"); }
          tile.addEventListener("click", function () { select(entry.index); });
          grid.append(tile);
        });
        group.append(grid);
        groups.append(group);
      });
      pickerToggle.addEventListener("click", function () {
        pickerOpen = !pickerOpen;
        groups.hidden = !pickerOpen;
        pickerToggle.setAttribute("aria-expanded", String(pickerOpen));
      });
      picker.append(pickerToggle, groups);
      root.append(picker);
      var card = make("section", "challenge-card");
      root.append(card);
      var top = make("div", "challenge-top");
      card.append(top);
      var kicker = make("span", "challenge-kicker");
      kicker.append(make("span", "challenge-kicker-label", t.puzzle + " "));
      kicker.append(make("span", "challenge-kicker-count", (index + 1) + " / " + challenges.length));
      top.append(kicker);
      var level = current().level;
      if (typeof level === "string" && t.level[level.toLowerCase()]) {
        top.append(make("span", "challenge-level challenge-level-" + level.toLowerCase(), t.level[level.toLowerCase()]));
      }
      var headerNav = make("div", "challenge-header-nav");
      var previous = make("button", "challenge-nav-button", "← " + t.previous);
      previous.type = "button";
      var nextHeader = make("button", "challenge-nav-button", t.next + " →");
      nextHeader.type = "button";
      previous.addEventListener("click", function () { select((index + challenges.length - 1) % challenges.length); });
      nextHeader.addEventListener("click", function () { select((index + 1) % challenges.length); });
      headerNav.append(previous, nextHeader);
      top.append(headerNav);
      var counter = make("span", "challenge-counter");
      var counterFull = make("span", "challenge-counter-full");
      var counterCompact = make("span", "challenge-counter-compact");
      counter.append(counterFull, counterCompact);
      function updateCounter() {
        counterFull.textContent = t.solved + " " + count() + " " + t.of + " " + challenges.length;
        counterCompact.textContent = lang === "zh" ? "已解 " + count() : count() + " solved";
      }
      updateCounter();
      top.append(counter);
      if (isBig()) {
        var record = variant ? current().variant : current();
        var metadata = make("p", "challenge-metadata",
          format(t.fromSet, { count: current().set.operators }) + " · " +
          format(t.ruleCount, { count: current().rules.length }) + " · " +
          (isLegend() ? format(t.fullCount, { count: record.step_count.toLocaleString(lang === "zh" ? "zh-CN" : "en-US") }) :
            format(t.stepCounts, { short: record.coarse_step_count, full: record.step_count })));
        card.append(metadata);
        if (variant && isLegend()) {
          card.append(make("p", "challenge-affected", format(t.affected,
            { count: record.affected_rules, total: current().rules.length })));
        }
      }
      card.append(make("h2", "challenge-heading", t.rules));
      var kindLegend = make("div", "");
      card.append(kindLegend);
      if (kindLegend && window.KindsLegend) {
        window.KindsLegend.render(kindLegend, {lang: lang, collapsed: true});
        var complex = current().rules.some(function (rule) {
          return /,\s*(?:if|else)\b/.test(rule.text) || (rule.symbol && rule.text.indexOf(rule.symbol, rule.text.indexOf("{")) >= 0);
        });
        if (complex && !seenComplexKind) { kindLegend.querySelector(".kl-shell").open = true; seenComplexKind = true; }
      }
      var rules = make("div", "challenge-rules");
      card.append(rules);
      var atomLegend = make("div", "challenge-atoms-legend");
      card.append(atomLegend);
      window.OpulseAtoms.legend(atomLegend, "integer", current().rules.map(function (_, i) { return ruleText(i); })
        .concat([current().question]));
      var search;
      if (isBig()) {
        search = make("input", "challenge-rule-search");
        search.type = "search";
        search.placeholder = t.search;
        search.setAttribute("aria-label", t.search);
        card.insertBefore(search, rules);
        rules.classList.add("challenge-rules-large");
      }
      function inQuestion(symbol) {
        var start = 0;
        var at;
        while ((at = current().question.indexOf(symbol, start)) >= 0) {
          var longer = current().rules.some(function (other) {
            return other.symbol.length > symbol.length && current().question.slice(at).indexOf(other.symbol) === 0;
          });
          if (!longer) { return true; }
          start = at + symbol.length;
        }
        return false;
      }
      var direct = current().rules.map(function (rule, i) { return { rule: rule, index: i }; })
        .filter(function (entry) { return inQuestion(entry.rule.symbol); });
      if (isLegend() && variant && !direct.some(function (entry) { return entry.index === current().variant.rule_index; })) {
        direct.push({ rule: current().rules[current().variant.rule_index], index: current().variant.rule_index });
      }
      var directIndexes = direct.map(function (entry) { return entry.index; });
      var orderedRules = isBig() ? direct.concat(current().rules.map(function (rule, i) { return { rule: rule, index: i }; })
        .filter(function (entry) { return directIndexes.indexOf(entry.index) < 0; })
        .sort(function (a, b) { return a.rule.layer - b.rule.layer; })) :
        current().rules.map(function (rule, i) { return { rule: rule, index: i }; });
      function appendRule(ruleGroup, entry) {
        var rule = entry.rule;
        var i = entry.index;
        var row = make("div", "challenge-rule");
        row.dataset.symbol = rule.symbol;
        var main = make("div", "challenge-rule-main");
        var symbol = make("span", "challenge-symbol", rule.symbol);
        symbol.setAttribute("aria-hidden", "true");
        main.append(symbol);
        var content = make("div", "challenge-rule-content");
        var body = make("span", "challenge-rule-text");
        var oldPart = "";
        if (variant && i === current().variant.rule_index) {
          oldPart = changedText(body, current().variant.before, current().variant.after);
          row.classList.add("is-changed");
        } else { body.textContent = ruleText(i); }
        var copy = make("div", "challenge-rule-copy");
        copy.append(body);
        if (oldPart) { copy.append(make("small", "challenge-rule-was", t.was + " " + oldPart)); }
        content.append(copy);
        if (row.classList.contains("is-changed")) { content.append(make("span", "challenge-changed-tag", t.changed)); }
        main.append(content);
        var hint = make("p", "challenge-hint", rule.hint);
        hint.id = "challenge-hint-" + i;
        hint.hidden = true;
        var toggle = make("button", "challenge-hint-toggle", t.hint);
        toggle.type = "button";
        toggle.setAttribute("aria-controls", hint.id);
        toggle.setAttribute("aria-expanded", "false");
        toggle.addEventListener("click", function () {
          hint.hidden = !hint.hidden;
          toggle.setAttribute("aria-expanded", String(!hint.hidden));
        });
        main.append(toggle);
        row.append(main, hint);
        ruleGroup.append(row);
      }
      function layerName(layer) {
        return lang === "zh" ? t.layer + (Number(layer) + 1) + " 层" : t.layer + " " + (Number(layer) + 1);
      }
      if (isLegend()) {
        if (direct.length) {
          var pinned = make("section", "challenge-rule-group");
          pinned.append(make("h3", "challenge-rule-group-heading", variant ? t.directChanged : t.direct));
          direct.forEach(function (entry) { appendRule(pinned, entry); });
          rules.append(pinned);
        }
        var layerGroups = make("div", "challenge-rule-layers");
        var byLayer = new Map();
        orderedRules.slice(direct.length).forEach(function (entry) {
          var layer = entry.rule.layer;
          if (!byLayer.has(layer)) { byLayer.set(layer, []); }
          byLayer.get(layer).push(entry);
        });
        byLayer.forEach(function (entries, layer) {
          var group = make("details", "challenge-rule-layer");
          group.append(make("summary", "challenge-rule-layer-summary", layerName(layer) + " · " + entries.length));
          var contents = make("div", "challenge-rule-group");
          group.append(contents);
          group.addEventListener("toggle", function () {
            if (group.open) {
              layerGroups.querySelectorAll(".challenge-rule-layer[open]").forEach(function (other) {
                if (other !== group) { other.open = false; }
              });
            }
            if (group.open && !contents.hasChildNodes()) {
              var fragment = document.createDocumentFragment();
              entries.forEach(function (entry) { appendRule(fragment, entry); });
              contents.append(fragment);
            } else if (!group.open) { contents.replaceChildren(); }
          });
          layerGroups.append(group);
        });
        rules.append(layerGroups);
        var matches = make("section", "challenge-rule-group challenge-rule-matches");
        matches.hidden = true;
        rules.append(matches);
        search.addEventListener("input", function () {
          clearTimeout(ruleSearchTimer);
          ruleSearchTimer = setTimeout(function () {
            ruleSearchTimer = null;
            var query = search.value.trim().toLocaleLowerCase();
            if (query) {
              layerGroups.querySelectorAll(".challenge-rule-layer[open]").forEach(function (group) { group.open = false; });
            }
            layerGroups.hidden = !!query;
            matches.hidden = !query;
            matches.replaceChildren();
            if (!query) { return; }
            var found = orderedRules.filter(function (entry) {
              return directIndexes.indexOf(entry.index) < 0 && entry.rule.symbol.toLocaleLowerCase().includes(query);
            });
            matches.append(make("h3", "challenge-rule-group-heading", t.search + " · " + found.length));
            var shown = 0;
            var more = make("button", "challenge-button challenge-secondary challenge-more-rules", t.moreRules);
            more.type = "button";
            function addMatches() {
              var fragment = document.createDocumentFragment();
              found.slice(shown, shown + 80).forEach(function (entry) { appendRule(fragment, entry); });
              matches.insertBefore(fragment, more);
              shown += 80;
              more.hidden = shown >= found.length;
            }
            more.addEventListener("click", addMatches);
            matches.append(more);
            addMatches();
          }, 100);
        });
      } else {
        var ruleGroup = rules;
        var groupKey = "";
        orderedRules.forEach(function (entry) {
          if (isBig()) {
            var nextKey = directIndexes.indexOf(entry.index) >= 0 ? "direct" : String(entry.rule.layer);
            if (nextKey !== groupKey) {
              groupKey = nextKey;
              ruleGroup = make("section", "challenge-rule-group");
              ruleGroup.append(make("h3", "challenge-rule-group-heading", nextKey === "direct" ? t.direct : layerName(nextKey)));
              rules.append(ruleGroup);
            }
          }
          appendRule(ruleGroup, entry);
        });
      }
      if (search && !isLegend()) {
        search.addEventListener("input", function () {
          var query = search.value.trim().toLocaleLowerCase();
          rules.querySelectorAll(".challenge-rule").forEach(function (row) {
            row.hidden = !!query && !row.dataset.symbol.toLocaleLowerCase().includes(query);
          });
          rules.querySelectorAll(".challenge-rule-group").forEach(function (group) {
            group.hidden = !group.querySelector(".challenge-rule:not([hidden])");
          });
        });
      }
      card.append(make("h2", "challenge-heading", variant ? t.predict : t.question));
      card.append(make("div", "challenge-question", current().question));
      var form = make("form", "challenge-form");
      var label = make("label", "challenge-label", t.answer);
      var input = make("input", "challenge-input");
      input.type = "number";
      input.step = "1";
      input.inputMode = "numeric";
      input.autocomplete = "off";
      input.id = "challenge-answer";
      label.htmlFor = input.id;
      var check = make("button", "challenge-button challenge-primary", t.check);
      check.type = "submit";
      var show = make("button", "challenge-button challenge-secondary", t.show);
      show.type = "button";
      form.append(label, input, check, show);
      card.append(form);
      var feedback = make("p", "challenge-feedback");
      feedback.setAttribute("role", "status");
      card.append(feedback);
      var reveal = make("section", "challenge-reveal");
      reveal.hidden = true;
      reveal.append(make("h2", "challenge-heading", t.steps));
      var stepModes, stepViewer = null;
      if (isBig()) {
        stepModes = make("div", "challenge-step-modes");
        [["short", t.short], ["full", t.full]].forEach(function (choice) {
          var button = make("button", "challenge-button challenge-secondary", choice[1]);
          button.type = "button";
          button.setAttribute("aria-pressed", String(stepMode === choice[0]));
          button.addEventListener("click", function () {
            stepMode = choice[0];
            stepModes.querySelectorAll("button").forEach(function (other) {
              other.setAttribute("aria-pressed", String(other === button));
            });
            showStepPage(false);
          });
          stepModes.append(button);
        });
        reveal.append(stepModes);
      }
      var list = make("div", "challenge-step-view");
      reveal.append(list);
      card.append(reveal);
      var why = make("p", "challenge-why");
      why.append(make("strong", "challenge-why-label", t.whyLabel + ": "));
      why.append(document.createTextNode(current()[lang === "zh" ? "why_zh" : "why"]));
      why.hidden = true;
      card.append(why);
      var actions = make("div", "challenge-actions");
      actions.hidden = true;
      var change = make("button", "challenge-button challenge-secondary", t.change);
      change.type = "button";
      change.hidden = !!variant;
      var model = make("button", "challenge-button challenge-secondary", t.model);
      model.type = "button";
      var share = make("button", "challenge-button challenge-secondary", t.share);
      share.type = "button";
      var next = make("button", "challenge-button challenge-primary", t.next);
      next.type = "button";
      actions.append(next, change, share);
      card.append(actions);
      if (isBig()) {
        var promptSize = current().rules.reduce(function (sum, _, i) { return sum + ruleText(i).length + 1; }, 0) + current().question.length + 100;
        card.append(make("p", "challenge-prompt-warning", format(t.promptLong,
          { count: (Math.round(promptSize / 1000) * 1000).toLocaleString(lang === "zh" ? "zh-CN" : "en-US") })));
      }
      var copyStatus = make("p", "challenge-copy-status");
      copyStatus.setAttribute("role", "status");
      copyStatus.hidden = true;
      var fallback = make("textarea", "challenge-copy-fallback");
      fallback.readOnly = true;
      fallback.hidden = true;
      card.append(copyStatus, fallback);
      var modelGrade = make("section", "challenge-model-grade");
      modelGrade.append(make("h3", "challenge-model-heading", t.model));
      modelGrade.append(model);
      var modelLabel = make("label", "challenge-label", t.paste);
      var modelText = make("textarea", "challenge-input challenge-model-answer");
      modelLabel.append(modelText);
      var grade = make("button", "challenge-button challenge-primary", t.grade);
      grade.type = "button";
      var modelResult = make("div", "challenge-model-result");
      modelResult.setAttribute("role", "status");
      modelGrade.append(modelLabel, grade, modelResult);
      card.append(modelGrade);
      grade.addEventListener("click", function () {
        var record = variant ? current().variant : current();
        var parsed = window.OpulseChallengeAnswers.parseAnswer("compute", record, modelText.value);
        var verdict = window.OpulseChallengeAnswers.gradeAnswer("compute", record, parsed);
        modelResult.textContent = t.parsed + ": " + (parsed.ok ? String(parsed.value) : parsed.error) +
          "\n" + t.verdict + ": " + (verdict.correct ? t.modelCorrect : t.modelIncorrect) +
          " " + verdict.detail;
        modelResult.classList.toggle("is-right", verdict.correct);
      });

      function markRule(symbol) {
        rules.querySelectorAll(".challenge-rule").forEach(function (item) {
          item.classList.toggle("is-active", !!symbol && item.dataset.symbol === symbol);
        });
      }
      function showStepPage(animate) {
        var ticket = ++fullRequest;
        if (stepViewer) { stepViewer.destroy(); stepViewer = null; }
        if (isLegend() && stepMode === "full") {
          var ref = (variant ? current().variant : current()).steps_ref;
          list.textContent = t.loadingSteps;
          ensureScales().then(function (api) {
            if (!fullExample) {
              if (ref.format !== "opulse.scale-example/1" || !/^legend\/[\w-]+\/(?:variant\/)?$/.test(ref.path)) {
                throw new Error("Invalid trace reference");
              }
              fullExample = api.loadExampleAt(new URL("../data/challenge/" + ref.path + "index.json", script));
            }
            return fullExample;
          }).then(function (example) {
            if (ticket !== fullRequest) return;
            stepViewer = window.OpulseStepView.render(list, {
              steps: {count: ref.count, load: function (offset, size) { return example.fullPage(offset, size); }},
              page_size: 50, lang: lang,
              labels: {describe: function (step) {
                var symbol = step.op && step.op.symbol;
                var label = make("span", "", (symbol || "·") + (step.condition ? " · " + step.condition : ""));
                if (symbol) window.OpulseAtoms.title(label, "integer", symbol, step.op.arity || step.op.n_ary);
                return label; },
                onSelect: function (step) { markRule(step.op && step.op.symbol); }}
            });
            why.hidden = false;
          }).catch(function () { if (ticket === fullRequest) list.textContent = t.stepsFail; });
          return;
        }
        var all = steps();
        var normalized = all.slice(1).map(function (step, i) {
          var rule = step.rule || "·";
          return {expr_before: all[i].expr, expr_after: step.expr,
            kind: current().rules.some(function (entry) { return entry.symbol === rule; }) ? "expand" : "eval", rule: rule};
        });
        stepViewer = window.OpulseStepView.render(list, {
          steps: normalized, page_size: 50, lang: lang,
          labels: {describe: function (step) {
            var label = make("span", "", step.rule);
            if (step.kind !== "expand" && step.rule) window.OpulseAtoms.title(label, "integer", step.rule,
              /^-\s/.test(step.expr_after) ? 1 : 2);
            return label; },
            onSelect: function (step) { markRule(step.rule); }}
        });
        why.hidden = false;
      }
      function begin(guess) {
        form.hidden = true;
        reveal.hidden = false;
        actions.hidden = false;
        if (guess === null) { feedback.textContent = t.shown; }
        else if (guess === answer()) {
          feedback.textContent = message(t.right, { answer: answer(), guess: guess });
          feedback.classList.add("is-right");
          remember();
          updateCounter();
          var currentTile = picker.querySelector(".challenge-tile.is-current");
          if (currentTile && currentTile.textContent.indexOf("✓") < 0) {
            currentTile.textContent += " ✓";
            currentTile.setAttribute("aria-label", currentTile.getAttribute("aria-label") + ", " + t.solved);
          }
        } else { feedback.textContent = message(t.wrong, { answer: answer(), guess: guess }); }
        showStepPage(!isLegend());
      }
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        if (!input.value.trim() || !Number.isInteger(Number(input.value))) {
          input.setCustomValidity(lang === "zh" ? "请输入整数。" : "Enter a whole number.");
          input.reportValidity();
          return;
        }
        input.setCustomValidity("");
        begin(Number(input.value));
      });
      input.addEventListener("input", function () { input.setCustomValidity(""); });
      show.addEventListener("click", function () { begin(null); });
      change.addEventListener("click", function () { variant = 1; updateUrl(); render(); root.querySelector(".challenge-input").focus(); });
      next.addEventListener("click", function () { select((index + 1) % challenges.length); });
      model.addEventListener("click", function () { prompt().then(function (text) { copy(text, copyStatus, fallback); }); });
      share.addEventListener("click", function () { copy(link(), copyStatus, fallback); });
    }
    render();
  }

  function boot() {
    var root = document.getElementById("opulse-challenge");
    if (!root) { return; }
    if (!script) { root.textContent = words[root.dataset.lang === "zh" ? "zh" : "en"].loadingFail; return; }
    function load(file) {
      return fetch(new URL("../data/challenge/" + file, script)).then(function (response) {
        if (!response.ok) { throw new Error("Challenge data unavailable: " + file); }
        return response.json();
      });
    }
    if (!window.OpulseChallengeModes) { root.textContent = words[root.dataset.lang === "zh" ? "zh" : "en"].loadingFail; return; }
    window.OpulseChallengeModes.boot(root, load, init);
  }
  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", boot); }
  else { boot(); }
}());
