/* Learn: checked examples are visible before the interpreter is requested. */
(function () {
  "use strict";
  const src = document.currentScript && document.currentScript.src;
  const zh = (document.documentElement.lang || "").toLowerCase().startsWith("zh");
  const tr = (en, cn) => zh ? cn : en;
  const esc = value => String(value).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  let checkerPromise;

  function loadChecker() {
    if (window.OpulseCheck) return Promise.resolve(window.OpulseCheck);
    if (!checkerPromise) checkerPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = new URL("challenge-check.js", src);
      script.onload = () => resolve(window.OpulseCheck);
      script.onerror = () => reject(new Error(tr("Could not load the interpreter helper.", "无法加载解释器组件。")));
      document.head.append(script);
    }).catch(error => { checkerPromise = null; throw error; });
    return checkerPromise;
  }

  function mark(source, span, cls) {
    if (!span || span[1] <= span[0]) return esc(source);
    return esc(source.slice(0, span[0])) + `<mark class="${cls}">${esc(source.slice(span[0], span[1]))}</mark>` + esc(source.slice(span[1]));
  }

  function normalizedSteps(steps, expression) {
    // The current trace renderer shortens a three-input call to "⊙(a)" in
    // its first before line. Keep the exact source expression in this view.
    return steps.map((step, index) => {
      if (index === 0 && step.shape == null && step.kind === "expand") {
        return {...step, before: expression, focus: [0, expression.length]};
      }
      return step;
    });
  }

  function branchDetail(step) {
    if (!step.branches || step.branches.length < 2) return "";
    const rows = step.branches.map(branch => {
      const condition = branch.condition === null ? "else" : branch.substituted;
      const verdict = branch.truth ? tr("true", "成立") : tr("false", "不成立");
      return `<li class="${branch.index === step.branch_index ? "opg-chosen" : ""}">` +
        `<span class="opg-bn">${tr("branch", "分支")} ${branch.index}</span> <code>${esc(condition)}</code> ` +
        `<span class="opg-v ${branch.truth ? "opg-v-true" : "opg-v-false"}">${verdict}</span></li>`;
    }).join("");
    return `<ol class="opg-branches">${rows}</ol>`;
  }

  function typedValue(world, value) {
    try {
      if (world === "strings") return {t: "str", v: JSON.parse(value)};
      if (world === "lists") return {t: "list", v: JSON.parse(value).map(v => ({t: "int", v}))};
      if (world === "grid") return {t: "grid", v: JSON.parse(value)};
    } catch (_) { /* The text result remains available. */ }
    return null;
  }

  function init(host, row) {
    const label = tr("Example", "示例");
    const hasRules = row.id !== "atoms";
    host.className = "ol-example opg";
    host.innerHTML = `<div class="ol-edit ${hasRules ? "" : "ol-edit-atoms"}">` +
      (hasRules ? `<label>${tr("Rules (definitions)", "规则（定义）")}<textarea class="ol-rule opg-defs" rows="${row.rule.includes("\n") ? 3 : 2}" spellcheck="false" aria-describedby="${esc(row.id)}-rule-hint"></textarea>` +
        `<span class="ol-rule-hint" id="${esc(row.id)}-rule-hint">${tr("One rule per line: name the inputs, then the body in braces.", "每行一条规则：先写输入名称，再用花括号写规则内容。")}</span></label>` : "") +
      `<label>${tr("Expression", "表达式")}<input class="ol-input opg-expr" spellcheck="false"></label>` +
      `<button type="button" class="opg-btn ol-run">${tr("Run", "运行")}</button></div>` +
      `<p class="ol-status" role="status" aria-live="polite"></p>` +
      `<div class="ol-result" aria-label="${label}"></div><div class="ol-world"></div>` +
      `<div class="ol-stepview"><div class="opg-nav"><button type="button" class="opg-btn ol-prev" aria-label="${tr("Previous step", "上一步")}">←</button>` +
      `<input class="opg-range ol-range" type="range" min="1" max="1" value="1" aria-label="${tr("Step", "步骤")}">` +
      `<button type="button" class="opg-btn ol-next" aria-label="${tr("Next step", "下一步")}">→</button><span class="ol-count"></span></div>` +
      `<div class="opg-detail ol-detail"></div><ol class="opg-steps ol-steps" role="listbox" tabindex="0" aria-label="${tr("All steps", "所有步骤")}"></ol></div>` +
      `<details class="ol-answer"><summary>${tr("Show exercise answer", "查看练习答案")}</summary><code>${esc(row.exercise.expression)} = ${esc(row.exercise.value)}</code></details>`;

    const rule = host.querySelector(".ol-rule");
    const input = host.querySelector(".ol-input");
    const result = host.querySelector(".ol-result");
    const worldValue = host.querySelector(".ol-world");
    const status = host.querySelector(".ol-status");
    const slider = host.querySelector(".ol-range");
    const count = host.querySelector(".ol-count");
    const detail = host.querySelector(".ol-detail");
    const list = host.querySelector(".ol-steps");
    if (rule) rule.value = row.rule;
    input.value = row.expression;
    let current = {value: row.value, steps: row.steps};
    let selected = 0;

    function showStep(index) {
      const steps = normalizedSteps(current.steps, input.value);
      selected = Math.max(0, Math.min(steps.length - 1, index));
      const step = steps[selected];
      if (!step) { detail.textContent = tr("This input is already a value.", "这个输入已经是一个值。"); return; }
      slider.value = String(selected + 1);
      count.textContent = tr(`${selected + 1} / ${steps.length}`, `第 ${selected + 1} / ${steps.length} 步`);
      const kind = step.kind === "expand" ? tr("unfold", "展开") : step.kind === "eval" ? tr("compute", "计算") : tr("undefined", "未定义");
      detail.className = `opg-detail ol-detail opg-a-${step.kind === "eval" ? "atom" : step.operator_kind || "nan"}`;
      detail.innerHTML = `<div class="opg-expr-line"><span class="opg-tag">${tr("before", "之前")}</span><code>${mark(step.before, step.focus, "opg-focus")}</code></div>` +
        `<div class="opg-expr-line"><span class="opg-tag">${tr("after", "之后")}</span><code>${mark(step.after, step.new, "opg-new")}</code></div>` +
        `<div class="opg-why"><span class="opg-kind-chip">${kind}</span><div class="opg-why-body">${step.branches && step.branches.length > 1 ?
          tr(`Branch ${step.branch_index} of ${step.branch_count} is used.`, `选择了第 ${step.branch_index} / ${step.branch_count} 个分支。`) + branchDetail(step) :
          step.kind === "eval" ? tr("Apply the starting operation.", "应用原子操作。") : tr("Replace the call with its rule.", "用规则替换这个调用。")}</div></div>`;
      list.querySelectorAll("[aria-selected]").forEach(item => item.setAttribute("aria-selected", String(Number(item.dataset.i) === selected)));
    }

    function render() {
      result.innerHTML = `<code>${esc(input.value)}</code><span class="ol-equals"> = </span><strong>${esc(current.value)}</strong>`;
      worldValue.replaceChildren();
      const value = typedValue(row.world, current.value);
      if (value && window.OpulseWorlds) window.OpulseWorlds.renderValue(worldValue, row.world, value, {compact: true});
      const steps = normalizedSteps(current.steps, input.value);
      list.innerHTML = steps.map((step, i) => `<li role="option" tabindex="-1" data-i="${i}" aria-selected="false" class="opg-row opg-a-${step.kind === "eval" ? "atom" : step.operator_kind || "nan"}">` +
        `<span class="opg-idx">${i + 1}</span><span class="opg-kind">${step.kind === "expand" ? tr("unfold", "展开") : tr("compute", "计算")}</span>` +
        `<code class="opg-line">${mark(step.before, step.focus, "opg-focus")}</code></li>`).join("");
      slider.max = String(Math.max(1, steps.length));
      slider.disabled = steps.length < 2;
      showStep(0);
    }

    host.querySelector(".ol-run").addEventListener("click", async () => {
      const button = host.querySelector(".ol-run");
      button.disabled = true;
      status.textContent = tr("Loading the interpreter, then calculating…", "正在加载解释器并计算…");
      try {
        const checker = await loadChecker();
        current = await checker.evaluate(rule && rule.value.trim() ? [rule.value] : [], input.value.trim(), row.world);
        render();
        status.textContent = tr("Calculated by Opulse.", "已由 Opulse 算出。");
      } catch (error) {
        status.textContent = zh ? "无法计算。请检查规则和输入。" : "Could not calculate: " + error.message;
      } finally { button.disabled = false; }
    });
    host.querySelector(".ol-prev").addEventListener("click", () => showStep(selected - 1));
    host.querySelector(".ol-next").addEventListener("click", () => showStep(selected + 1));
    slider.addEventListener("input", () => showStep(Number(slider.value) - 1));
    list.addEventListener("click", event => {
      const item = event.target.closest("[data-i]");
      if (item) showStep(Number(item.dataset.i));
    });
    list.addEventListener("keydown", event => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault(); showStep(selected + (event.key === "ArrowDown" ? 1 : -1));
      }
    });
    [rule, input].filter(Boolean).forEach(field => field.addEventListener("keydown", event => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) host.querySelector(".ol-run").click();
    }));
    render();
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const root = document.querySelector("[data-opulse-learn]");
    if (!root) return;
    try {
      const response = await fetch(new URL("../data/learn.json", src));
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      const byId = new Map(data.map(row => [row.id, row]));
      root.querySelectorAll("[data-learn-example]").forEach(host => {
        const row = byId.get(host.dataset.learnExample);
        if (row) init(host, row);
      });
    } catch (error) {
      root.querySelectorAll("[data-learn-example]").forEach(host => {
        host.textContent = tr("Could not load the checked example.", "无法加载已验证的示例。");
      });
    }
  });
})();
