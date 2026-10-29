/* Layer-0 glossary shared by the site widgets and copied prompts. */
(function (root) {
  "use strict";
  const cache = new Map();
  const browser = typeof document !== "undefined";
  const dataRoot = browser ? new URL("../data/atoms/", document.currentScript.src) : null;
  const language = () => browser && (document.documentElement.lang || "").startsWith("zh") ? "zh" : "en";

  function load(world) {
    world = world || "integer";
    if (!cache.has(world)) {
      if (browser) cache.set(world, fetch(new URL(world + ".json", dataRoot)).then(response => {
        if (!response.ok) throw new Error("Atom glossary unavailable: " + world);
        return response.json();
      }));
      else cache.set(world, Promise.resolve(require("../data/atoms/" + world + ".json")));
    }
    return cache.get(world);
  }

  function used(data, texts) {
    const source = (Array.isArray(texts) ? texts : [texts]).filter(Boolean).join("\n");
    return Object.entries(data).filter(([symbol]) => {
      if (symbol === "- (unary)") return /(^|[({;=\n])\s*-\s*(?=[a-zA-Z(&#])/.test(source);
      if (symbol === "-") return /(?:[a-zA-Z0-9)]\s+-\s+(?:[a-zA-Z0-9(]|-\s))/.test(source);
      if (symbol === "+" || symbol === "*" || symbol === "/" || symbol === "%") {
        return new RegExp("(?:[a-zA-Z0-9)]\\s*" + (symbol === "*" || symbol === "+" ? "\\" : "") + symbol + "\\s*[a-zA-Z0-9(-])").test(source);
      }
      return new RegExp(symbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "(?![₀-₉])").test(source);
    });
  }

  function lines(data, texts, lang) {
    const entries = used(data, texts);
    if (!entries.length) return "";
    const heading = lang === "zh" ? "原子操作：" : "Atoms used:";
    return heading + "\n" + entries.map(([symbol, atom]) =>
      "- " + (symbol === "- (unary)" ? "- (prefix)" : symbol) + ": " +
      (lang === "zh" ? atom.plain_zh : atom.plain) + " " + atom.example).join("\n") + "\n\n";
  }

  async function promptLines(world, texts, lang) { return lines(await load(world), texts, lang || language()); }

  async function legend(container, world, texts) {
    if (!container || !browser) return;
    const data = await load(world);
    if (!container.isConnected) return;
    const entries = used(data, texts);
    container.replaceChildren();
    if (!entries.length) return;
    const details = document.createElement("details");
    details.className = "atoms-legend";
    const summary = document.createElement("summary");
    summary.textContent = language() === "zh" ? "用到的原子操作" : "Atoms used";
    const preview = document.createElement("span");
    preview.className = "atoms-legend-preview";
    preview.textContent = entries.map(([symbol]) => symbol === "- (unary)" ? "−a" : symbol).join("  ");
    summary.append(preview);
    details.append(summary);
    const chips = document.createElement("div");
    chips.className = "atoms-legend-chips";
    entries.forEach(([symbol, atom]) => {
      const chip = document.createElement("span");
      chip.className = "atoms-legend-chip";
      const mark = document.createElement("strong");
      mark.textContent = symbol === "- (unary)" ? "−a" : symbol;
      const meaning = document.createElement("span");
      meaning.textContent = language() === "zh" ? atom.plain_zh : atom.plain;
      const example = document.createElement("code");
      example.textContent = atom.example;
      chip.append(mark, meaning, example);
      chip.title = meaning.textContent + " " + atom.example;
      chip.tabIndex = 0;
      chip.setAttribute("role", "button");
      chip.setAttribute("aria-expanded", "false");
      function toggle() {
        const open = chip.classList.toggle("is-open");
        chip.setAttribute("aria-expanded", String(open));
      }
      chip.addEventListener("click", toggle);
      chip.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(); }
      });
      chips.append(chip);
    });
    details.append(chips);
    container.append(details);
  }

  async function title(node, world, symbol, arity) {
    const data = await load(world);
    if (!node.isConnected) return;
    const atom = data[symbol === "-" && arity === 1 ? "- (unary)" : symbol];
    if (atom) node.title = (language() === "zh" ? atom.plain_zh : atom.plain) + " " + atom.example;
  }

  function closureTexts(operators, target, expression) {
    const names = operators.filter(op => op.definition);
    const seen = new Set(), texts = [expression || ""];
    function visit(op) {
      if (!op || seen.has(op.id || op.symbol)) return;
      seen.add(op.id || op.symbol);
      texts.push(op.definition);
      names.forEach(other => { if (op.definition.includes(other.symbol)) visit(other); });
    }
    visit(names.find(op => op.symbol === target));
    return texts;
  }

  const api = {load, used, lines, promptLines, legend, title, closureTexts};
  if (browser) root.OpulseAtoms = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window === "undefined" ? globalThis : window);
