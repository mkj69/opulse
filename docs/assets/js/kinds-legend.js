/* Shared explanation of definition kinds and rule notation. */
(function () {
  "use strict";
  const COPY = {
    en: {
      title: "Kinds of definitions", read: "How to read a rule",
      kinds: [
        ["Substitution", "Calls atoms or other operators to combine their results.", "a ◆ b = { (a + b) * 2 }"],
        ["Branch", "A test selects the first matching body.", "a ◆ b = { a, if a > b; b, else }"],
        ["Recursion", "Calls itself with a smaller argument until a base case.", "a ◆ b = { 0, if b <= 0; (a ◆ (b - 1)) + a, else }"]
      ],
      forms: [
        ["a ◆ b", "Binary infix: ◆ takes a left and a right input."],
        ["a △ / ■ a", "Unary postfix / prefix: one input goes before / after the symbol."],
        ["◆(a, b, c)", "Call form: inputs appear inside parentheses, in order."],
        ["{ x, if c; y, else }", "Multi-branch form: use x when c holds; otherwise use y."]
      ]
    },
    zh: {
      title: "定义的类型", read: "怎样读规则",
      kinds: [
        ["代入", "调用原子操作或其他运算符，组合它们的结果。", "a ◆ b = { (a + b) * 2 }"],
        ["分支", "条件决定使用第一个匹配的定义体。", "a ◆ b = { a, if a > b; b, else }"],
        ["递归", "用更小的参数调用自身，直到遇到基础情形。", "a ◆ b = { 0, if b <= 0; (a ◆ (b - 1)) + a, else }"]
      ],
      forms: [
        ["a ◆ b", "二元中缀：◆ 接收左、右两个输入。"],
        ["a △ / ■ a", "一元后缀／前缀：一个输入写在符号前／后。"],
        ["◆(a, b, c)", "调用式：输入按顺序写在括号内。"],
        ["{ x, if c; y, else }", "多分支：c 成立时用 x，否则用 y。"]
      ]
    }
  };
  const esc = value => String(value).replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch]));
  function language(value) {
    return value === "zh" || (!value && (document.documentElement.lang || "").startsWith("zh")) ? "zh" : "en";
  }
  let nextId = 0;
  function render(target, options) {
    if (!target) return null;
    options = options || {};
    const lang = language(options.lang || target.dataset.lang);
    const copy = COPY[lang];
    if (!target.id) target.id = "kl-widget-" + (++nextId);
    const rows = copy.kinds.map(([name, meaning, example], i) =>
      `<div class="kl-kind kl-${["simple","branch","recursive"][i]}" id="${target.id}-${["substitution","branch","recursion"][i]}">` +
      `<span class="kl-chip">${esc(name)}</span><span class="kl-meaning">${esc(meaning)}</span>` +
      `<code>${esc(example)}</code></div>`).join("");
    const forms = copy.forms.map(([form, meaning]) => `<div><code>${esc(form)}</code><span>${esc(meaning)}</span></div>`).join("");
    target.classList.add("kinds-legend");
    target.innerHTML = (options.collapsed ? `<details class="kl-shell"><summary>${esc(copy.title)}</summary>` : `<div class="kl-shell"><strong class="kl-title">${esc(copy.title)}</strong>`) +
      `<div class="kl-kinds">${rows}</div><details class="kl-read"><summary>${esc(copy.read)}</summary><div class="kl-forms">${forms}</div></details>` +
      (options.collapsed ? "</details>" : "</div>");
    return target;
  }
  function init() {
    document.querySelectorAll("[data-kinds-legend]:not([data-kinds-ready])").forEach(target => {
      target.dataset.kindsReady = "1";
      render(target, {collapsed: target.hasAttribute("data-kinds-collapsed")});
    });
  }
  window.KindsLegend = {render, init, copy: COPY};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
  if (window.document$) window.document$.subscribe(init);
}());
