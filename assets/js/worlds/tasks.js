/* Task tabs for every world: compound expressions, solving for x, laws and equivalence, and
   contrast, edit and simplify. Data: data/worlds/<world>/tasks.json, details loaded on demand
   from data/worlds/<world>/tasks/*.json. Values are drawn with the world's own renderer. */
(function () {
  "use strict";
  const W = window.OpulseWorlds;
  if (!W || !W.extend) return;
  const tr = (en, zh) => W.tr(en, zh);
  const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  const LAW_NAMES = {
    commutative: ["commutative", "交换律"], associative: ["associative", "结合律"], idempotent: ["idempotent", "幂等"],
    left_identity: ["left identity", "左单位元"], right_identity: ["right identity", "右单位元"],
    involution: ["involution", "对合"]};
  const LAW_FORMS = {
    commutative: "a ◇ b = b ◇ a", associative: "(a ◇ b) ◇ c = a ◇ (b ◇ c)", left_identity: "e ◇ a = a",
    right_identity: "a ◇ e = a", involution: "◇(◇(a)) = a"};
  const files = new Map();

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }
  function hint(en, zh) { return el("p", "ow-hint", tr(en, zh)); }
  function load(path, root) {
    const url = new URL(path, root).href;
    if (!files.has(url)) files.set(url, fetch(url).then(response => {
      if (!response.ok) throw new Error("Could not load " + path);
      return response.json();
    }).catch(error => { files.delete(url); throw error; }));
    return files.get(url);
  }
  const SCALAR = ["int", "bool", "str", "nan", "entity", "note", "colour", "skill", "direction"];
  // A short label for a value: the literal for small values, a summary for pictures.
  function label(value, index) {
    if (!value) return "?";
    if (value.t === "grid") return (value.v?.length || 0) + "×" + (value.v?.[0]?.length || 0);
    if (value.t === "state") return "#" + (index + 1);
    if (value.t === "skill") return value.v;
    const text = W.valueText(value);
    return text.length > 18 ? (index !== undefined ? "#" + (index + 1) : text.slice(0, 16) + "…") : text;
  }
  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function checkText(check) {
    if (!check) return "";
    const unit = check.unit === "states" ? tr("start states", "个起始状态") : check.unit === "skills" ? tr("skills", "个技能") : tr("sampled values", "个取样值");
    if (check.method === "z3") return tr("proved by z3", "由 z3 证明");
    if (check.method === "range" && check.range) return tr("checked in [" + check.range[0] + ", " + check.range[1] + "]", "在 [" + check.range[0] + ", " + check.range[1] + "] 上逐个检查");
    if (check.method === "all") return tr("all " + check.size + " " + (check.unit === "skills" ? "skills" : "values") + " checked", "全部 " + check.size + (check.unit === "skills" ? " 个技能" : " 个取值") + "都检查过");
    if (check.method === "sample") return tr("checked on " + check.size + " " + unit, "在 " + check.size + " " + unit + "上检查");
    return tr("undecided", "未判定");
  }
  function badge(check, extra) {
    const node = el("span", "owt-badge owt-" + (check?.method || "none"), (extra ? extra + " · " : "") + checkText(check));
    return node;
  }
  function holeResult(item) {
    const count = (item.solutions || []).length;
    if (["z3", "range", "all"].includes(item.check?.method)) {
      return count === 1 ? tr("unique", "唯一解") : tr(count + " solutions", count + " 个解");
    }
    const size = item.domain?.size ?? "?";
    const state = item.domain?.kind === "state";
    return tr(count + (count === 1 ? " solution among the " : " solutions among the ") + size + (state ? " tested start states" : " tested values"),
      count + " 个解，来自 " + size + (state ? " 个检查过的起始状态" : " 个检查过的取值"));
  }
  function lawResult(cell) {
    if (cell.none) return tr("no identity in the tested set", "检查过的取值里没有单位元");
    if (cell.holds) return tr("holds", "成立") + " · " + checkText(cell.check);
    const check = cell.check || {};
    if (check.method === "z3") return tr("z3 found a counterexample", "z3 找到了反例");
    if (check.method === "range" && check.range) return tr("counterexample found in [" + check.range.join(", ") + "]", "在 [" + check.range.join(", ") + "] 中找到了反例");
    if (check.method === "sample") return tr("counterexample among " + check.size + " sampled values", "在 " + check.size + " 个取样值中找到了反例");
    if (check.method === "all") return tr("counterexample among " + check.size + " values", "在全部 " + check.size + " 个检查过的取值中找到了反例");
    return tr("counterexample found", "找到了反例");
  }

  function renderTaskView(key, container, data, ctx) {
      const renderer = ctx.renderer;
      const short = text => renderer.shorten ? renderer.shorten(String(text)) : String(text);
      const valueText = value => renderer.valueText ? renderer.valueText(value) : W.valueText(value);
      const draw = (host, value, options) => ctx.draw(host, value, renderer, {...data, ...(options || {})});
      const tr = ctx.tr;
      const tasksReady = load(data.world + "/tasks.json", ctx.dataRoot);
      const view = el("section", "owt owt-panel");
      container.replaceChildren(view);
      view.append(el("p", "ow-status", tr("Loading…", "正在加载……")));
      let tasks = null;
      tasksReady.then(value => {
        if (!view.isConnected) return;
        tasks = value && typeof value === "object" ? value : {};
        view.replaceChildren();
        view.append(hint("Use the tabs to explore operators and tasks. Press ← or → to change tabs.",
          "切换视图：看运算符本身，或者看库拿它们做什么。← 和 → 在标签之间移动。"));
        if (tasks.seed !== undefined && data.seed !== undefined && tasks.seed !== data.seed) {
          view.append(el("p", "owt-note", tr("These tasks use seed " + tasks.seed + ". Select it to compare definitions.",
            "这些任务使用本世界的默认种子 " + tasks.seed + "。切回这个种子，就能对照运算符的定义。")));
        }
        ({expressions, solve, laws, more})[key](view);
      }).catch(() => {
        if (view.isConnected) view.replaceChildren(el("p", "ow-status", tr("Tasks are unavailable for this world.", "这个世界暂时没有这些视图。")));
      });

      function makeTaskPlayer(host, item, level) {
        const panel = el("div", "ow-player");
        const visual = el("div", "ow-step-visual");
        const stepHost = el("div", "ow-step-view");
        panel.append(visual, stepHost); host.replaceChildren(panel);
        let viewer = null, steps = [];
        panel.addEventListener("ow:close", () => { if (viewer) viewer.destroy(); });
        const formatted = text => { const node = document.createElement("span"); node.innerHTML = ctx.rich(short(String(text))); return node; };
        function show(step, position) {
          if (!renderer.persistent) visual.replaceChildren();
          let value = item.first, previous = null;
          for (let i = 0; i <= position; i++) if (steps[i].value) { previous = value; value = steps[i].value; }
          const renderCtx = {...data, data, world: data, example: {expression: item.expression, inputs: [item.first], output: item.value},
            steps, index: position, stepIndex: position, large: true};
          try {
            if (renderer.renderStep) renderer.renderStep(visual, {...step, value, previous}, renderCtx);
            else draw(visual, position === steps.length - 1 ? item.value : value, renderCtx);
          } catch (error) { draw(visual, value, renderCtx); }
        }
        load((tasks.files || data.world + "/tasks/") + item.id + ".json", ctx.dataRoot).then(all => {
          if (!panel.isConnected) return;
          steps = Array.isArray(all) ? all[level] || [] : (all.examples || all.steps || [])[level] || [];
          const rows = steps.map((step, i) => ({...step, expr_before: i ? steps[i - 1].expression : item.expression,
            expr_after: step.expression, redex: step.focus,
            rule: tr(step.note, step.note_zh || step.note)}));
          viewer = window.OpulseStepView.render(stepHost, {steps: rows, page_size: 50,
            lang: (document.documentElement.lang || "").startsWith("zh") ? "zh" : "en", renderValue: formatted,
            labels: {describe: step => formatted(step.rule), onSelect: (_, i) => show(steps[i], i)}});
          if (renderer.selectExample) renderer.selectExample({expression: item.expression, inputs: [item.first], output: item.value}, steps, data);
          if (!steps.length) draw(visual, item.value, {...data, data, world: data});
        }).catch(() => { stepHost.textContent = tr("Derivation unavailable.", "无法加载推导。"); });
      }

      // ------------------------------------------------------------ expressions
      function expressions(panel) {
        const items = tasks.expressions || [];
        if (!items.length) { panel.append(el("p", "owt-note", tr("No compound expressions are available.", "这个世界没有复合算式。"))); return; }
        const layout = el("div", "owt-split");
        const list = el("div", "owt-list"); list.setAttribute("role", "listbox");
        list.setAttribute("aria-label", tr("Expressions", "算式"));
        const detail = el("div", "owt-detail");
        layout.append(list, detail);
        panel.append(hint("Choose an expression to see its value and derivation. Press ↑ or ↓ to browse.",
          "每个算式组合了这个世界的两到四个运算符。选一个查看结果和推导。在列表里用 ↑ 和 ↓ 切换。"), layout);
        let level = 2;
        function open(index) {
          const item = items[index];
          list.querySelectorAll(".owt-item").forEach((b, i) => b.setAttribute("aria-selected", i === index));
          detail.querySelectorAll(".ow-player").forEach(p => p.dispatchEvent(new Event("ow:close")));
          detail.replaceChildren();
          const head = el("div", "owt-expr-head");
          head.append(el("code", "owt-expr", short(item.expression)));
          const result = el("div", "owt-result"); result.append(el("span", "owt-eq", "="));
          const value = el("div", "owt-value"); draw(value, item.value); result.append(value);
          head.append(result);
          detail.append(head);
          const defs = el("details", "owt-defs");
          defs.append(el("summary", "", tr("Definitions used", "用到的定义") + " · " + (item.definitions || []).length));
          (item.definitions || []).forEach(d => defs.append(el("pre", "owt-def", short(d.definition))));
          detail.append(defs);
          detail.append(hint("Open to see the rules used here.",
            "展开“用到的定义”，查看这个算式用到了哪些规则。"));
          const grains = el("div", "owt-seg"); grains.setAttribute("role", "group");
          grains.setAttribute("aria-label", tr("Granularity", "粒度"));
          const host = el("div", "owt-player");
          (tasks.granularities || []).forEach((g, gi) => {
            const b = el("button", "", tr(g.en, g.zh) + " · " + (item.steps?.[gi] ?? "?")); b.type = "button";
            b.setAttribute("aria-pressed", gi === level);
            b.onclick = () => { level = gi; grains.querySelectorAll("button").forEach((x, xi) => x.setAttribute("aria-pressed", xi === gi)); play(); };
            grains.append(b);
          });
          detail.append(el("h4", "owt-sub", tr("Derivation", "推导")), grains,
            hint("Choose one step per operator, unfolded written operators, or every step. Each button shows its step count.",
              "选择推导的粗细：每个运算符一步、只展开写出的运算符，或者每一步。数字是步数。"), host);
          function play() {
            host.querySelectorAll(".ow-player").forEach(p => p.dispatchEvent(new Event("ow:close")));
            if ((tasks.granularities || []).length) makeTaskPlayer(host, item, Math.min(level, tasks.granularities.length - 1));
          }
          play();
        }
        items.forEach((item, index) => {
          const b = el("button", "owt-item"); b.type = "button"; b.setAttribute("role", "option");
          b.append(el("code", "owt-item-text", short(item.expression)));
          const meta = el("span", "owt-item-meta", tr("depth ", "深度 ") + item.depth + " · " + (item.operators || []).length + tr(" operators", " 个运算符"));
          b.append(meta);
          b.onclick = () => open(index);
          list.append(b);
        });
        listKeys(list, ".owt-item");
        open(0);
      }

      // ------------------------------------------------------------ solve
      function solve(panel) {
        const items = tasks.holes || [];
        if (!items.length) { panel.append(el("p", "owt-note", tr("No equations are available.", "这个世界没有求解任务。"))); return; }
        const layout = el("div", "owt-split");
        const list = el("div", "owt-list"); list.setAttribute("role", "listbox");
        list.setAttribute("aria-label", tr("Equations", "方程"));
        const detail = el("div", "owt-detail");
        layout.append(list, detail);
        panel.append(hint("Choose an equation to see candidate values tested for x. Press ↑ or ↓ to browse.",
          "每个方程把一个值藏成 x。选一个，看搜索逐个试候选值。在列表里用 ↑ 和 ↓ 切换。"), layout);
        function open(index) {
          const item = items[index];
          list.querySelectorAll(".owt-item").forEach((b, i) => b.setAttribute("aria-selected", i === index));
          detail.querySelectorAll(".owt-solve-stage").forEach(p => p.dispatchEvent(new Event("ow:close")));
          detail.replaceChildren();
          const equation = el("div", "owt-equation");
          const lhs = el("code", "owt-expr");
          lhs.innerHTML = esc(short(item.expression)).replace(/(^|[^\w])x(?=$|[^\w])/g, "$1<mark>x</mark>");
          equation.append(lhs, el("span", "owt-eq", "="));
          const target = el("div", "owt-value"); draw(target, item.target); equation.append(target);
          detail.append(equation);
          if (item.start) {
            const start = el("div", "owt-facts");
            start.append(el("span", "owt-fact-label", tr("start state s", "起始状态 s")));
            const s = el("div", "owt-value"); draw(s, item.start, {compact: true}); start.append(s);
            detail.append(start);
          }
          detail.append(el("p", "owt-domain", domainText(item)));
          const stage = el("section", "owt-solve-stage"); stage.tabIndex = 0;
          const show = el("div", "owt-try");
          const xBox = el("figure", "owt-slot"), outBox = el("figure", "owt-slot");
          const verdict = el("span", "owt-verdict");
          show.append(xBox, el("span", "ow-arrow", "→"), outBox, verdict);
          const controls = el("div", "ow-controls");
          const playButton = el("button", "ow-play", tr("Play", "播放")); playButton.type = "button";
          const back = el("button", "", "←"); back.type = "button"; back.setAttribute("aria-label", tr("Previous candidate", "上一个候选"));
          const next = el("button", "", "→"); next.type = "button"; next.setAttribute("aria-label", tr("Next candidate", "下一个候选"));
          const jump = el("button", "", tr("Result", "结果")); jump.type = "button";
          controls.append(back, playButton, next, jump);
          const counter = el("span", "owt-counter");
          const strip = el("div", "owt-strip"); strip.setAttribute("aria-label", tr("Candidates", "候选"));
          const stripHint = el("p", "owt-strip-hint ow-hint");
          const stripToggle = el("button", "owt-strip-toggle"); stripToggle.type = "button";
          const final = el("div", "owt-final");
          stage.append(show, controls, counter, hint("Play tries candidates in order. Press ← or →, or select a candidate to inspect it. Solutions light up.",
            "播放会按顺序试每个候选。← 和 → 逐个前后，点一个候选可以单独查看。不对的变灰，解会亮起来。"), stripHint, strip, stripToggle, final);
          detail.append(stage);
          if (item.summary) detail.append(el("p", "owt-note", tr(
            "z3 searched all " + (item.domain?.size ?? "?").toLocaleString("en") + " integers; the strip shows " + item.tried + " values nearest the answer, computed by the interpreter.",
            "z3 一次搜索了全部 " + (item.domain?.size ?? "?").toLocaleString("en") + " 个整数；下方列出最接近答案的 " + item.tried + " 个值，每个结果都由解释器算出。")));
          let rows = [], at = -1, timer = null, closed = false;
          const stop = () => { clearInterval(timer); timer = null; playButton.textContent = tr("Play", "播放"); };
          stage.addEventListener("ow:close", () => { closed = !stage.isConnected; stop(); });
          function isHit(row) { return (item.solutions || []).some(s => same(s, row[0])); }
          function render(position) {
            if (!rows.length) return;
            at = position;
            const row = rows[at];
            [...strip.children].forEach((chip, i) => {
              chip.classList.toggle("tried", i <= at);
              chip.classList.toggle("current", i === at);
            });
            counter.textContent = tr("candidate ", "第 ") + (at + 1) + " / " + rows.length + tr("", " 个候选");
            xBox.replaceChildren(); outBox.replaceChildren();
            if (!row) return;
            const xv = el("div", "owt-value"); draw(xv, row[0], {compact: row[0]?.t === "state"});
            xBox.append(el("figcaption", "", "x ="), xv);
            const ov = el("div", "owt-value"); draw(ov, row[1], {compact: row[1]?.t === "state"});
            outBox.append(el("figcaption", "", tr("gives", "得到")), ov);
            const hit = isHit(row);
            verdict.textContent = hit ? tr("solution", "是解") : tr("miss", "不对");
            verdict.className = "owt-verdict " + (hit ? "hit" : "miss");
            if (at === rows.length - 1) stop();
          }
          function finish() {
            final.replaceChildren();
            final.append(badge(item.check, holeResult(item)));
            const sols = el("div", "owt-solutions");
            (item.solutions || []).forEach(s => { const v = el("div", "owt-value"); draw(v, s, {compact: true}); sols.append(v); });
            final.append(sols);
          }
          finish();
          function step(delta) { stop(); render(Math.max(0, Math.min(rows.length - 1, at + delta))); }
          back.onclick = () => step(-1); next.onclick = () => step(1);
          jump.onclick = () => { stop(); render(rows.length - 1); };
          playButton.onclick = () => {
            if (!rows.length) return;
            if (reduced()) { stop(); render(rows.length - 1); return; }
            if (timer) { stop(); return; }
            if (at >= rows.length - 1) at = -1;
            playButton.textContent = tr("Pause", "暂停");
            const delay = Math.max(90, Math.min(420, 9000 / Math.max(1, rows.length)));
            timer = setInterval(() => { if (at >= rows.length - 1) stop(); else render(at + 1); }, delay);
          };
          stage.onkeydown = event => {
            if (event.target !== stage && !event.target.classList.contains("owt-chip")) return;
            if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); step(event.key === "ArrowRight" ? 1 : -1); }
            else if (event.key === " " && event.target === stage) { event.preventDefault(); playButton.click(); }
          };
          load((tasks.files || data.world + "/tasks/") + item.id + ".json", ctx.dataRoot).then(detailData => {
            if (closed || !stage.isConnected) return;
            rows = Array.isArray(detailData?.candidates) ? detailData.candidates : [];
            if (!rows.length) { counter.textContent = tr("No candidates available.", "没有可用的候选值。"); return; }
            if (rows.length > 60) {
              strip.classList.add("collapsed");
              stripHint.textContent = tr("The list shows about three rows. Solutions appear below.", "候选列表先显示约三行。解显示在下方。");
              stripToggle.setAttribute("aria-expanded", "false");
              stripToggle.textContent = tr("Show all " + rows.length + " candidates", "显示全部 " + rows.length + " 个候选值");
              stripToggle.onclick = () => {
                const expanded = strip.classList.toggle("expanded");
                stripToggle.setAttribute("aria-expanded", String(expanded));
                stripToggle.textContent = expanded ? tr("Show fewer candidates", "收起候选值") : tr("Show all " + rows.length + " candidates", "显示全部 " + rows.length + " 个候选值");
              };
            } else {
              stripHint.hidden = true;
              stripToggle.hidden = true;
            }
            rows.forEach((row, i) => {
              const pitchValue = data.world === "pitch" && ["note", "melody"].includes(row[0]?.t);
              const chip = el("button", "owt-chip" + (isHit(row) ? " hit" : "") + (!row[1] || row[1].t === "nan" ? " nan" : ""),
                pitchValue ? undefined : label(row[0], i));
              chip.type = "button";
              if (pitchValue) draw(chip, row[0], {mini: true});
              chip.title = valueText(row[0]).slice(0, 80) + " → " + valueText(row[1]).slice(0, 80);
              chip.setAttribute("aria-label", tr("Candidate ", "候选值 ") + (i + 1) + ": " + chip.title);
              chip.onclick = () => { stop(); render(i); };
              strip.append(chip);
            });
            if (reduced()) render(rows.length - 1);
            else { render(0); if (stage.offsetParent !== null) playButton.click(); }
          }).catch(() => { if (stage.isConnected) counter.textContent = tr("Candidates unavailable.", "无法加载候选。"); });
        }
        items.forEach((item, index) => {
          const b = el("button", "owt-item"); b.type = "button"; b.setAttribute("role", "option");
          b.append(el("code", "owt-item-text", short(item.equation)));
          b.append(el("span", "owt-item-meta", holeResult(item) + " · " + checkText(item.check)));
          if (data.world === "action" && item.equation === "x(s) = t") {
            const preview = el("span", "owt-item-preview");
            preview.append(el("span", "owt-fact-label", tr("target", "目标")));
            const value = el("span", "owt-value"); draw(value, item.target, {compact: true}); preview.append(value);
            b.append(preview);
          }
          b.onclick = () => open(index);
          list.append(b);
        });
        listKeys(list, ".owt-item");
        open(0);
      }
      function domainText(item) {
        const d = item.domain || {};
        if (d.kind === "int" && item.check?.method === "z3") return tr("x ranges over every integer in [" + d.lo + ", " + d.hi + "].", "x 取 [" + d.lo + ", " + d.hi + "] 里的每个整数。");
        if (d.kind === "int") return tr("x ranges over the integers " + d.lo + " to " + d.hi + " (" + d.size + " candidates).", "x 取 " + d.lo + " 到 " + d.hi + " 的整数（共 " + d.size + " 个候选）。");
        if (d.kind === "bool") return tr("x is true or false.", "x 取真或假。");
        if (d.kind === "skill") return tr("x ranges over all " + d.size + " skills of the library.", "x 取库里全部 " + d.size + " 个技能。");
        if (d.kind === "state") return tr("x ranges over the " + d.size + " generated start states.", "x 取生成的 " + d.size + " 个起始状态。");
        return tr("x ranges over the world's " + d.size + " sampled " + d.kind + " values.", "x 取这个世界的 " + d.size + " 个 " + d.kind + " 取样值。");
      }

      // ------------------------------------------------------------ laws
      function laws(panel) {
        const table = tasks.laws || {laws: [], rows: []};
        const lawNames = Array.isArray(table.laws) ? table.laws : [];
        const lawRows = Array.isArray(table.rows) ? table.rows : [];
        panel.append(hint("Select a mark to inspect a law. ✓ holds, ✗ has a counterexample, and ∅ means no identity was found in the tested set.",
          "每个运算符列出各条定律。✓ 表示成立，✗ 表示找到了反例，∅ 表示检查过的取值里没有单位元。点标记查看详情。"));
        const scroller = el("div", "owt-scroll");
        const grid = el("table", "owt-laws");
        const mobile = el("div", "owt-law-cards");
        const head = el("tr"); head.append(el("th", "", tr("operator", "运算符")));
        lawNames.forEach(law => {
          const th = el("th"); th.append(el("span", "", tr(...(LAW_NAMES[law] || [law, law]))));
          if (LAW_FORMS[law]) th.append(el("code", "owt-law-form", LAW_FORMS[law]));
          head.append(th);
        });
        const thead = el("thead"); thead.append(head); grid.append(thead);
        const body = el("tbody");
        const detail = el("div", "owt-law-detail");
        function mark(row, law, cell, key) {
          const state = cell.none ? "none" : cell.holds ? "yes" : cell.holds === false ? "no" : "unknown";
          const symbol = cell.none ? "∅" : cell.holds ? "✓" : cell.holds === false ? "✗" : "?";
          const labelText = cell.none ? tr("no identity in the tested set", "检查过的取值里没有单位元") :
            cell.holds ? tr("holds", "成立") : cell.holds === false ? tr("counterexample found", "找到了反例") : tr("undecided", "未判定");
          const b = el("button", "owt-mark " + state, symbol); b.type = "button";
          b.dataset.lawKey = key;
          b.setAttribute("aria-label", row.name + " " + tr(...(LAW_NAMES[law] || [law, law])) + ": " + labelText + "; " + checkText(cell.check));
          const check = cell.check || {};
          b.append(el("span", "owt-mark-how", check.method === "z3" ? "z3" : check.method === "range" && check.range ? "[" + check.range.join(", ") + "]" : check.method === "all" ? tr("all", "全部") : check.size ? "n=" + check.size : "?"));
          b.onclick = event => {
            panel.querySelectorAll(".owt-mark").forEach(m => m.setAttribute("aria-pressed", m.dataset.lawKey === key));
            lawDetail(detail, row, law, cell);
            if (event.isTrusted && matchMedia("(max-width: 599px)").matches) {
              detail.scrollIntoView({behavior: reduced() ? "auto" : "smooth", block: "start"});
            }
          };
          return b;
        }
        lawRows.forEach((row, rowIndex) => {
          const tr_ = el("tr");
          const name = el("th"); name.scope = "row";
          const signature = row.signature || [];
          name.append(el("span", "owt-op", row.name), el("span", "owt-sig", signature.slice(0, -1).join(" × ") + " → " + (signature.at(-1) || "?")));
          tr_.append(name);
          const card = el("section", "owt-law-card");
          card.append(el("span", "owt-op", row.name), el("span", "owt-sig", signature.slice(0, -1).join(" × ") + " → " + (signature.at(-1) || "?")));
          lawNames.forEach(law => {
            const td = el("td");
            const mobileRow = el("div", "owt-law-card-row");
            mobileRow.append(el("span", "owt-law-card-name", tr(...(LAW_NAMES[law] || [law, law]))));
            const cell = row.cells?.[law];
            if (!cell) {
              const na = el("span", "owt-na", tr("not applicable", "不适用"));
              td.append(el("span", "owt-na", "·")); td.title = tr("does not apply to this type", "不适用于这个类型");
              mobileRow.append(na);
            }
            else {
              const key = rowIndex + ":" + law;
              td.append(mark(row, law, cell, key));
              mobileRow.append(mark(row, law, cell, key));
              mobileRow.append(el("span", "owt-law-card-check", (cell.none ? tr("no identity in the tested set", "检查过的取值里没有单位元") + " · " : "") + checkText(cell.check)));
            }
            tr_.append(td);
            card.append(mobileRow);
          });
          body.append(tr_);
          mobile.append(card);
        });
        grid.append(body); scroller.append(grid);
        panel.append(scroller, mobile, detail);
        const firstCross = grid.querySelector(".owt-mark.no") || grid.querySelector(".owt-mark");
        if (firstCross) firstCross.click();
        const eq = tasks.equivalence || [];
        if (eq.length) {
          panel.append(el("h3", "owt-section", tr("Equivalence", "等价")),
            hint("Each card states how it was checked. A counterexample shows where the expressions differ.",
              "每张卡片写明检查方式。反例会显示两个表达式结果不同的输入。"));
          const cards = el("div", "owt-cards");
          eq.forEach(item => cards.append(pairCard(item)));
          panel.append(cards);
        }
      }
      function lawDetail(host, row, law, cell) {
        host.replaceChildren();
        const title = el("div", "owt-law-title");
        title.append(el("strong", "", row.name + " · " + tr(...(LAW_NAMES[law] || [law, law]))),
          el("span", "owt-badge owt-" + (cell.check?.method || "none"), lawResult(cell)));
        host.append(title, el("pre", "owt-def", short(row.definition)));
        if (cell.element) {
          const line = el("div", "owt-facts");
          line.append(el("span", "owt-fact-label", tr("identity element e", "单位元 e")));
          const v = el("div", "owt-value"); draw(v, cell.element, {compact: true}); line.append(v);
          host.append(line);
        }
        if (cell.note) host.append(el("p", "owt-note", tr(cell.note, cell.note_zh || cell.note)));
        if (cell.counterexample) host.append(counterBlock(cell.counterexample));
        else if (cell.holds) host.append(el("p", "owt-note", cell.check?.method === "z3" ?
          tr("z3 found no difference across the value domain.", "z3 在整个取值范围里找不到让两边不同的输入。") :
          tr("The sides agree on every checked input.", "检查过的输入里没有一个让两边不同。")));
      }
      function counterBlock(ce) {
        const box = el("div", "owt-counter-box");
        box.append(el("h4", "owt-sub", tr("Counterexample", "反例")));
        const inputs = el("div", "owt-inputs");
        (ce.inputs || []).forEach(input => {
          const fig = el("figure", "owt-slot");
          fig.append(el("figcaption", "", input.name + " ="));
          const v = el("div", "owt-value"); draw(v, input.value, {compact: input.value?.t === "state"}); fig.append(v);
          inputs.append(fig);
        });
        box.append(inputs);
        const sides = el("div", "owt-sides");
        [["left", ce.left, ce.left_value], ["right", ce.right, ce.right_value]].forEach(([side, text, value]) => {
          const fig = el("figure", "owt-side");
          fig.append(el("figcaption", "", side === "left" ? tr("left side", "左边") : tr("right side", "右边")));
          if (text) fig.append(el("code", "owt-expr small", short(text)));
          const v = el("div", "owt-value"); draw(v, value, {compact: value?.t === "state"}); fig.append(v);
          sides.append(fig);
        });
        sides.insertBefore(el("span", "owt-neq", "≠"), sides.children[1]);
        box.append(sides);
        return box;
      }
      function pairCard(item) {
        const card = el("article", "owt-card " + (item.equal ? "equal" : "differ"));
        const top = el("div", "owt-pair");
        const verified = ["z3", "range", "all"].includes(item.check?.method);
        top.append(el("code", "owt-expr small", short(item.left)), el("span", "owt-eq", item.equal ? (verified ? "≡" : "≈") : "≢"), el("code", "owt-expr small", short(item.right)));
        card.append(top, badge(item.check, item.equal ? (verified ? tr("equal", "等价") : tr("agree on every tested input", "在所有检查过的输入上都相同")) : tr("not equal", "不等价")));
        if (!item.equal) card.querySelector(".owt-badge").textContent = tr("not equal", "不等价") + " · " + lawResult({check: item.check});
        if (item.agreement !== undefined && !item.equal) card.append(el("p", "owt-note", tr(
          "They agree on " + Math.round(item.agreement * 100) + "% of sampled inputs, but not on every input.", "在 " + Math.round(item.agreement * 100) + "% 的取样输入上相同，但不是处处相同。")));
        if (item.agreement === 1 && !item.equal) card.append(el("p", "owt-note", tr("Every sampled input agrees, yet the solver finds an input where they differ.", "所有取样输入都相同，求解器却找到了一个让它们不同的输入。")));
        const defs = el("details", "owt-defs");
        defs.append(el("summary", "", tr("Definitions", "定义")));
        (item.definitions || []).forEach(d => defs.append(el("pre", "owt-def", short(d.definition))));
        card.append(defs, hint("Open to inspect both rules.",
          "展开“定义”，查看两条规则。"));
        if (item.counterexample) card.append(counterBlock({...item.counterexample, left: item.left, right: item.right}));
        return card;
      }

      // ------------------------------------------------------------ more
      function more(panel) {
        const contrast = tasks.contrast || [], edit = tasks.edit || [], simplify = tasks.simplify || [];
        if (contrast.length) {
          panel.append(el("h3", "owt-section", tr("Compare definitions", "对照题")),
            hint("One expression uses two versions of an operator. Their definitions give different answers.",
              "同一个算式出现两次，只有一个运算符的定义不同，所以照着定义算会得到两个不同的答案。"));
          contrast.forEach(item => {
            const box = el("div", "owt-contrast");
            box.append(el("code", "owt-expr", short(item.expression)));
            if (item.start) { const s = el("div", "owt-value"); draw(s, item.start, {compact: true}); box.append(s); }
            const pair = el("div", "owt-two");
            ["a", "b"].forEach(side => {
              const card = el("article", "owt-card");
              card.append(el("span", "owt-tag", side === "a" ? tr("as defined", "原定义") : tr(item.operator + " uses the body of " + item.b.from, item.operator + " 换成 " + item.b.from + " 的定义")));
              card.append(el("pre", "owt-def", short(item[side].definition)));
              const v = el("div", "owt-value"); draw(v, item[side].value); card.append(el("span", "owt-eq", "="), v);
              pair.append(card);
            });
            box.append(pair);
            panel.append(box);
          });
        }
        if (edit.length) {
          const item = edit[0];
          panel.append(el("h3", "owt-section", tr("Edit effects", "改一处，影响一片")),
            hint("One definition changes. Highlighted rows show affected answers.",
              "改了一个定义。建在它上面的运算符都可能变；高亮的行是答案真的变了的。"));
          const box = el("div", "owt-edit");
          const change = el("div", "owt-change");
          change.append(el("span", "owt-tag", tr("edit: ", "改动：") + tr(item.edit_en, item.edit_zh)));
          const [before, after] = diffLines(short(item.before), short(item.after));
          change.append(before, after);
          box.append(change, el("p", "owt-note", tr(item.affected_count + " operators use " + item.operator + " directly or through others.",
            item.affected_count + " 个运算符直接或间接用到 " + item.operator + "。")));
          const rows = el("div", "owt-rows");
          (item.rows || []).forEach(row => {
            const line = el("div", "owt-row" + (row.changed ? " changed" : "") + (row.reaches ? "" : " apart"));
            line.append(el("code", "owt-expr small", short(row.expression)));
            if (row.input) { const s = el("div", "owt-value"); draw(s, row.input, {compact: true}); line.append(s); }
            const b = el("div", "owt-value"); draw(b, row.before, {compact: true});
            const a = el("div", "owt-value"); draw(a, row.after, {compact: true});
            line.append(b, el("span", "ow-arrow", "→"), a,
              el("span", "owt-tag", row.changed ? tr("changed", "变了") : row.reaches ? tr("same answer", "答案没变") : tr("does not use it", "没用到它")));
            rows.append(line);
          });
          box.append(rows);
          panel.append(box);
        }
        if (simplify.length) {
          const item = simplify[0];
          panel.append(el("h3", "owt-section", tr("Simplify", "化简")),
            hint("The long form expands helper definitions. Both forms define the same operator.",
              "长的写法把辅助运算符展开写出，短的是这个运算符本来的定义，两者定义的是同一个运算符。"));
          const box = el("div", "owt-two");
          [["before", item.before_operations, tr("before", "化简前")], ["after", item.after_operations, tr("after", "化简后")]].forEach(([key, count, name]) => {
            const card = el("article", "owt-card");
            card.append(el("span", "owt-tag", name + " · " + count + tr(" operations", " 次运算")), el("pre", "owt-def", short(item[key])));
            box.append(card);
          });
          panel.append(box, badge(item.check, tr("same operator", "同一个运算符")),
            el("p", "owt-note", tr("Expanded helpers: ", "展开的辅助运算符：") + (item.inlined || []).join(", ")));
        }
        const notes = tasks.notes || {};
        for (const [key, items, name, nameZh] of [["contrast", contrast, "comparison", "对照"],
          ["edit", edit, "edit effects", "改动影响"], ["simplify", simplify, "simplification", "化简"]]) {
          if (items.length) continue;
          const note = notes[key];
          panel.append(el("p", "owt-note", note ? tr(note.en, note.zh) :
            tr("No " + name + " example was generated for this world.", "这个世界没有生成" + nameZh + "示例。")));
        }
      }
      function diffLines(a, b) {
        const wa = a.split(/(\s+)/), wb = b.split(/(\s+)/);
        const make = (words, other, cls) => {
          const pre = el("pre", "owt-def " + cls);
          words.forEach((w, i) => { if (w !== other[i] && w.trim()) pre.append(el("mark", "", w)); else pre.append(document.createTextNode(w)); });
          return pre;
        };
        return [make(wa, wb, "before"), make(wb, wa, "after")];
      }
      function listKeys(list, selector) {
        list.addEventListener("keydown", event => {
          if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
          const items = [...list.querySelectorAll(selector)];
          const at = items.indexOf(document.activeElement);
          const next = items[Math.max(0, Math.min(items.length - 1, at + (event.key === "ArrowDown" ? 1 : -1)))];
          if (next) { event.preventDefault(); next.focus(); next.click(); }
        });
      }
      function esc(text) { return String(text).replace(/[&<>"']/g, ch => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"}[ch])); }

  }

  W.extend("*", {tabs: [
    {id: "expressions", label: "Expressions", label_zh: "算式", render: (container, data, ctx) => renderTaskView("expressions", container, data, ctx)},
    {id: "solve", label: "Solve", label_zh: "求解", render: (container, data, ctx) => renderTaskView("solve", container, data, ctx)},
    {id: "laws", label: "Laws", label_zh: "定律", render: (container, data, ctx) => renderTaskView("laws", container, data, ctx)},
    {id: "more", label: "More", label_zh: "更多", render: (container, data, ctx) => renderTaskView("more", container, data, ctx)}
  ]});
  const stopRemoved = new MutationObserver(records => records.forEach(record => record.removedNodes.forEach(node => {
    if (node.nodeType !== 1) return;
    if (node.matches(".ow-player, .owt-solve-stage, .owc")) node.dispatchEvent(new Event("ow:close"));
    node.querySelectorAll(".ow-player, .owt-solve-stage, .owc").forEach(player => player.dispatchEvent(new Event("ow:close")));
  })));
  stopRemoved.observe(document.body, {childList: true, subtree: true});
  const valid = ["operators", "expressions", "solve", "laws", "more", "challenge"];
  let preferred = new URLSearchParams(location.search).get("tab");
  if (!valid.includes(preferred)) {
    try { preferred = localStorage.getItem("ow-task-tab") || "operators"; }
    catch (error) { preferred = "operators"; }
  }
  if (!valid.includes(preferred)) preferred = "operators";
  document.addEventListener("click", event => {
    if (!event.isTrusted) return;
    const tab = event.target.closest(".ow-shell .ow-tabs [data-tab]");
    if (!tab) return;
    preferred = tab.dataset.tab;
    try { localStorage.setItem("ow-task-tab", preferred); } catch (error) { /* storage off */ }
  }, true);
  document.addEventListener("keydown", event => {
    const tab = event.target.closest(".ow-shell .ow-tabs [data-tab]");
    if (!tab || (event.key !== "ArrowRight" && event.key !== "ArrowLeft")) return;
    const tabs = [...tab.parentNode.querySelectorAll("[data-tab]")];
    const next = tabs[(tabs.indexOf(tab) + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    event.preventDefault(); next.click(); next.focus();
    preferred = next.dataset.tab;
    try { localStorage.setItem("ow-task-tab", preferred); } catch (error) { /* storage off */ }
  });
  const mounted = new WeakSet();
  const observer = new MutationObserver(() => {
    document.querySelectorAll(".ow-shell").forEach(shell => {
      if (mounted.has(shell)) return;
      const tab = shell.querySelector('.ow-tabs [data-tab="' + preferred + '"]');
      if (!tab) return;
      mounted.add(shell);
      if (preferred !== "operators") tab.click();
    });
  });
  observer.observe(document.body, {childList: true, subtree: true});
})();
