/* Shared derivation viewer. steps is an array or {count, load(offset, size)}.
 * renderValue(text) may return a DOM node; labels.describe(step) may return a
 * node or text. Selection is zero based; goToStep is one based. */
(function () {
  "use strict";
  let sequence = 0;
  const defaults = {
    en: {before: "Before", after: "After", first: "First step", previous: "Previous step", play: "Play", pause: "Pause",
      next: "Next step", last: "Last step", step: "Step", go: "Go to step", goButton: "Go", loading: "Loading steps…",
      error: "Could not load steps", empty: "The expression is already a value.", unfold: "Unfold", compute: "Compute", undefined: "Undefined"},
    zh: {before: "改写前", after: "改写后", first: "第一步", previous: "上一步", play: "播放", pause: "暂停",
      next: "下一步", last: "最后一步", step: "步骤", go: "跳转到步骤", goButton: "跳转", loading: "正在加载步骤…",
      error: "无法加载步骤", empty: "算式已是值。", unfold: "展开", compute: "计算", undefined: "未定义"}
  };
  function node(tag, className, parent, value) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (value !== undefined) el.textContent = String(value);
    if (parent) parent.appendChild(el);
    return el;
  }
  function span(value, explicit, fallback) {
    if (Array.isArray(explicit) && explicit.length === 2 && Number.isInteger(explicit[0]) &&
        Number.isInteger(explicit[1]) && explicit[0] >= 0 && explicit[1] <= value.length && explicit[0] < explicit[1]) return explicit;
    if (typeof explicit === "string" && explicit) {
      const i = value.indexOf(explicit);
      if (i >= 0) return [i, i + explicit.length];
    }
    return fallback;
  }
  function difference(before, after) {
    let start = 0, a = before.length, b = after.length;
    while (start < a && start < b && before[start] === after[start]) start++;
    while (a > start && b > start && before[a - 1] === after[b - 1]) { a--; b--; }
    return [[start, a], [start, b]];
  }
  function render(container, options) {
    options = options || {};
    const lang = options.lang || ((document.documentElement.lang || "en").startsWith("zh") ? "zh" : "en");
    const labels = Object.assign({}, defaults[lang === "zh" ? "zh" : "en"], options.labels || {});
    const size = Math.max(1, Math.min(200, Number(options.page_size) || 50));
    const id = "opg-view-" + (++sequence);
    let source = options.steps || [], total = Array.isArray(source) ? source.length : Number(source.count) || 0;
    let selected = Math.max(0, Math.min(total - 1, Number(options.initial) || 0));
    let page = -1, rows = [], ticket = 0, timer = null, morphTimer = null, drawn = false, destroyed = false;
    container.replaceChildren();
    const view = node("div", "opg-stepview", container);
    const head = node("div", "opg-stepview-head", view);
    const counter = node("span", "opg-counter", head);
    const detail = node("div", "opg-detail", view);
    const nav = node("div", "opg-nav", view);
    function control(symbol, label, action) {
      const b = node("button", "opg-btn", nav, symbol);
      b.type = "button"; b.setAttribute("aria-label", label); b.addEventListener("click", action); return b;
    }
    const first = control("⏮", labels.first, () => { stop(); select(0); });
    const prev = control("◀", labels.previous, () => { stop(); select(selected - 1); });
    const play = control("▶", labels.play, () => togglePlay());
    const range = node("input", "opg-range", nav);
    range.type = "range"; range.min = "1"; range.setAttribute("aria-label", labels.step);
    const next = control("▶", labels.next, () => { stop(); select(selected + 1); });
    const last = control("⏭", labels.last, () => { stop(); select(total - 1); });
    const list = node("ol", "opg-steps", view);
    list.setAttribute("role", "listbox"); list.setAttribute("tabindex", "0"); list.setAttribute("aria-label", labels.step);
    const jump = node("div", "opg-jump", view);
    const jumpLabel = node("label", "", jump, labels.go);
    const input = node("input", "", jumpLabel);
    input.type = "number"; input.min = "1"; input.step = "1"; input.setAttribute("aria-label", labels.go);
    const go = node("button", "opg-btn", jump, labels.goButton); go.type = "button";
    function stop() { if (timer !== null) { clearInterval(timer); timer = null; } play.setAttribute("aria-label", labels.play); play.textContent = "▶"; }
    function togglePlay() {
      if (timer !== null) { stop(); return; }
      if (!total) return;
      if (selected === total - 1) select(0);
      play.setAttribute("aria-label", labels.pause); play.textContent = "⏸";
      const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      timer = setInterval(() => {
        if (!view.isConnected || selected >= total - 1) { stop(); return; }
        select(selected + 1);
        if (selected >= total - 1) stop();
      }, options.playInterval || (reduced ? 1500 : 900));
    }
    function appendValue(parent, text) {
      const result = options.renderValue ? options.renderValue(String(text)) : String(text);
      if (result instanceof Node) parent.appendChild(result);
      else parent.appendChild(document.createTextNode(String(result ?? "")));
    }
    function marked(parent, value, part, cls) {
      if (!part || part[0] >= part[1]) { appendValue(parent, value); return; }
      appendValue(parent, value.slice(0, part[0]));
      appendValue(node("mark", cls, parent), value.slice(part[0], part[1]));
      appendValue(parent, value.slice(part[1]));
    }
    function normalized(raw) {
      const before = String(raw.expr_before ?? raw.before ?? raw.expression_before ?? raw.expr ?? raw.expression ?? "");
      const after = String(raw.expr_after ?? raw.after ?? raw.expression_after ?? raw.expression ?? raw.expr ?? before);
      const diff = difference(before, after);
      return {raw, before, after, focus: span(before, raw.redex_span || raw.focus || raw.redex, diff[0]),
        result: span(after, raw.result_span || raw.new, diff[1]), kind: raw.kind || "compute"};
    }
    function kindName(kind) { return kind === "expand" || kind === "unfold" ? labels.unfold :
      kind === "eval" || kind === "compute" ? labels.compute : kind === "undefined" ? labels.undefined : String(kind).toUpperCase(); }
    function accent(step) { return step.raw.operator_kind || (step.kind === "undefined" ? "nan" : step.kind === "expand" ? "simple" : "atom"); }
    function draw() {
      if (destroyed) return;
      if (morphTimer !== null) { clearTimeout(morphTimer); morphTimer = null; }
      const local = selected - page * size, step = rows[local];
      counter.textContent = total ? `${labels.step} ${selected + 1} / ${total}` : "";
      range.max = String(Math.max(1, total)); range.value = String(selected + 1);
      range.disabled = total < 2;
      input.max = String(total); jump.hidden = total <= size;
      nav.hidden = !total; list.hidden = !total;
      first.disabled = prev.disabled = selected <= 0;
      next.disabled = last.disabled = selected >= total - 1;
      if (!step) { detail.textContent = total ? labels.loading : labels.empty; return; }
      const s = normalized(step);
      detail.className = `opg-detail opg-a-${accent(s)}`;
      detail.replaceChildren();
      if (options.morph) {
        const line = node("div", "opg-expr-line opg-morph-line", detail);
        const code = node("code", "", line);
        const after = () => {
          if (destroyed || !line.isConnected) return;
          code.replaceChildren(); marked(code, s.after, s.result, "opg-new");
          line.classList.remove("opg-morph-before"); line.classList.add("opg-morph-after");
        };
        marked(code, s.before, s.focus, "opg-focus");
        if (!drawn || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)) after();
        else {
          line.classList.add("opg-morph-before");
          morphTimer = setTimeout(() => { morphTimer = null; after(); }, 390);
        }
      } else {
        [[labels.before, s.before, s.focus, "opg-focus"], [labels.after, s.after, s.result, "opg-new"]].forEach(parts => {
          const line = node("div", "opg-expr-line", detail);
          node("span", "opg-tag", line, parts[0]);
          marked(node("code", "", line), parts[1], parts[2], parts[3]);
        });
      }
      const why = node("div", "opg-why", detail);
      node("span", "opg-kind-chip", why, kindName(s.kind));
      const body = node("div", "opg-why-body", why);
      const description = labels.describe ? labels.describe(step, selected) : (step.note || step.rule ||
        (s.kind === "expand" ? labels.unfold : labels.compute) + ".");
      if (description instanceof Node) body.appendChild(description);
      else body.textContent = String(description ?? "");
      list.querySelectorAll('[aria-selected="true"]').forEach(row => row.setAttribute("aria-selected", "false"));
      const current = list.querySelector(`[data-index="${selected}"]`);
      if (current) {
        current.setAttribute("aria-selected", "true"); list.setAttribute("aria-activedescendant", current.id);
        if (current.offsetTop < list.scrollTop) list.scrollTop = current.offsetTop;
        else if (current.offsetTop + current.offsetHeight > list.scrollTop + list.clientHeight)
          list.scrollTop = current.offsetTop + current.offsetHeight - list.clientHeight;
      }
      if (labels.onSelect) labels.onSelect(step, selected);
      drawn = true;
    }
    async function loadPage(number) {
      const request = ++ticket;
      page = number; rows = []; list.replaceChildren(); detail.textContent = labels.loading;
      try {
        const offset = number * size;
        rows = Array.isArray(source) ? source.slice(offset, offset + size) : await source.load(offset, size);
        if (destroyed || request !== ticket) return;
        rows.forEach((raw, i) => {
          const s = normalized(raw), index = offset + i;
          const row = node("li", `opg-row opg-a-${accent(s)}`, list);
          row.id = `${id}-step-${index}`; row.dataset.index = String(index);
          row.setAttribute("role", "option"); row.setAttribute("aria-selected", "false");
          if (options.compactRows) row.title = String(raw.rowTitle ?? s.before);
          node("span", "opg-idx", row, index + 1);
          node("span", "opg-kind", row, kindName(s.kind));
          const line = node("code", "opg-line", row);
          if (options.compactRows) {
            if (s.focus[0] < s.focus[1]) {
              const [start, end] = s.focus;
              const focus = s.before.slice(start, end);
              node("span", "opg-row-prefix", line, s.before.slice(0, start));
              node("mark", "opg-focus opg-row-focus", line,
                focus.length > 26 ? focus.slice(0, 15) + "…" + focus.slice(-10) : focus);
              node("span", "opg-row-suffix", line, s.before.slice(end));
            } else line.textContent = s.before;
          } else marked(line, s.before, s.focus, "opg-focus");
        });
        draw();
      } catch (error) { if (!destroyed && request === ticket) detail.textContent = `${labels.error}: ${error.message}`; }
    }
    function select(index) {
      if (destroyed || !total) return;
      selected = Math.max(0, Math.min(total - 1, Math.trunc(Number(index) || 0)));
      const wanted = Math.floor(selected / size);
      if (wanted !== page) loadPage(wanted); else draw();
    }
    function setSteps(nextSteps, initial) {
      stop(); ticket++; source = nextSteps || []; total = Array.isArray(source) ? source.length : Number(source.count) || 0;
      page = -1; selected = Math.max(0, Math.min(total - 1, Number(initial) || 0));
      if (total) select(selected); else { list.replaceChildren(); draw(); }
    }
    list.addEventListener("click", e => { const row = e.target.closest("[data-index]"); if (row && list.contains(row)) { stop(); select(Number(row.dataset.index)); list.focus({preventScroll: true}); } });
    list.addEventListener("keydown", e => {
      const moves = {ArrowDown: selected + 1, ArrowUp: selected - 1, ArrowRight: selected + 1, ArrowLeft: selected - 1,
        Home: 0, End: total - 1, PageDown: selected + size, PageUp: selected - size};
      if (e.key in moves) { e.preventDefault(); stop(); select(moves[e.key]); }
    });
    range.addEventListener("input", () => { stop(); select(Number(range.value) - 1); });
    go.addEventListener("click", () => { const n = Number(input.value); if (Number.isInteger(n) && n >= 1 && n <= total) { stop(); select(n - 1); } });
    input.addEventListener("keydown", e => { if (e.key === "Enter") go.click(); });
    if (total) select(selected); else draw();
    return {select, goToStep(n) { select(n - 1); }, setSteps, destroy() { destroyed = true; ticket++; stop(); clearTimeout(morphTimer); container.replaceChildren(); },
      get selected() { return selected; }};
  }
  window.OpulseStepView = {render, difference};
})();
