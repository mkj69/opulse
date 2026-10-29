/* Minimal DOM for exercising the shared viewer's lazy paging without a browser dependency. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class Element {
  constructor(tag = "div") {
    this.tagName = tag.toUpperCase(); this.children = []; this.attributes = {}; this.dataset = {};
    this.listeners = {}; this.className = ""; this.scrollTop = 0; this.clientHeight = 500;
    this.offsetHeight = 20; this.offsetTop = 0; this.isConnected = true; this._text = "";
  }
  appendChild(child) { child.offsetTop = this.children.length * 20; this.children.push(child); child.parent = this; return child; }
  replaceChildren(...children) { this.children = []; this._text = ""; children.forEach(child => this.appendChild(child)); }
  set textContent(value) { this.children = []; this._text = String(value); }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(""); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  getAttribute(key) { return this.attributes[key] ?? null; }
  addEventListener(key, handler) { this.listeners[key] = handler; }
  contains(other) { return other === this || this.children.some(child => child.contains(other)); }
  querySelectorAll(selector) {
    const found = [];
    const matches = el => selector === '[aria-selected="true"]' ? el.getAttribute("aria-selected") === "true" :
      selector === ".opg-row" ? el.className.split(" ").includes("opg-row") :
      selector === ".opg-focus" ? el.className === "opg-focus" :
      selector === ".opg-new" ? el.className === "opg-new" :
      selector === '[data-index]' ? el.dataset.index !== undefined :
      selector.startsWith('[data-index="') && el.dataset.index === selector.slice(13, -2);
    const visit = el => { for (const child of el.children) { if (matches(child)) found.push(child); visit(child); } };
    visit(this); return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}
const document = {documentElement: {lang: "en"}, createElement: tag => new Element(tag),
  createTextNode: text => { const node = new Element("#text"); node.textContent = text; return node; }};
const context = {document, window: {matchMedia: () => ({matches: false})}, Node: Element, setInterval, clearInterval, setTimeout, clearTimeout};
vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), context);

(async () => {
  const rows = Array.from({length: 55}, (_, i) => ({expr_before: `a + ${i}`, expr_after: `a * ${i}`, kind: "eval", rule: "compute"}));
  const calls = [];
  const root = new Element();
  const viewer = context.window.OpulseStepView.render(root, {
    steps: {count: rows.length, load: async (offset, size) => { calls.push([offset, size]); return rows.slice(offset, offset + size); }},
    page_size: 50, initial: 0
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(calls, [[0, 50]]);
  assert.equal(root.querySelectorAll(".opg-row").length, 50);
  viewer.goToStep(52);
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(calls, [[0, 50], [50, 50]]);
  assert.equal(root.querySelectorAll(".opg-row").length, 5);
  assert.equal(root.querySelector('[aria-selected="true"]').dataset.index, "51");
  assert.equal(root.querySelectorAll(".opg-focus").length, 6);
  assert.equal(root.querySelectorAll(".opg-new").length, 1);
  viewer.destroy();
  assert.equal(root.children.length, 0);
})().catch(error => { console.error(error); process.exitCode = 1; });
