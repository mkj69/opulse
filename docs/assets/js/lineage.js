(() => {
  "use strict";

  const defaults = {
    idea: "Idea",
    opulse: "Correspondence to Opulse",
    borrow: "What Opulse borrows",
    adds: "What Opulse adds",
    legend: "Filter by topic",
    timeline: "Research lineage timeline",
  };

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function init(container) {
    if (container.dataset.lineageReady === "true") return;
    const source = container.querySelector(":scope > script[type='application/json']");
    if (!source) return;

    let data;
    try {
      data = JSON.parse(source.textContent);
      if (!Array.isArray(data.groups) || !Array.isArray(data.works)) throw new Error("Invalid lineage data");
    } catch (error) {
      console.error("Could not render the lineage timeline", error);
      container.append(element("p", "op-lineage-error", "The timeline could not be loaded."));
      return;
    }
    container.dataset.lineageReady = "true";

    const labels = Object.fromEntries(Object.entries(defaults).map(([key, value]) => [
      key, container.getAttribute(`data-l-${key}`) || value,
    ]));
    const groups = new Map(data.groups.map((group) => [group.id, group]));
    const works = [...data.works].sort((a, b) => a.year - b.year);
    if (!works.length) return;

    const legend = element("div", "op-lineage-legend");
    legend.append(element("span", "op-lineage-legend-label", labels.legend));
    const filters = element("div", "op-lineage-filters");
    legend.append(filters);
    const viewport = element("div", "op-lineage-viewport");
    viewport.setAttribute("role", "group");
    viewport.setAttribute("aria-label", labels.timeline);
    viewport.tabIndex = 0;
    const axis = element("div", "op-lineage-axis");
    viewport.append(axis);
    const card = element("article", "op-lineage-card");
    card.setAttribute("aria-live", "polite");
    container.append(legend, viewport, card);

    const groupButtons = new Map();
    let selectedGroup = null;
    let active = null;
    const entries = [];

    function scrollToButton(button) {
      const left = button.parentElement.offsetLeft + button.offsetLeft - viewport.clientWidth / 2 + button.offsetWidth / 2;
      viewport.scrollTo({ left: Math.max(0, left), behavior: "auto" });
    }

    function addRow(key, value) {
      const row = element("div", "op-lineage-row");
      row.append(element("dt", "", labels[key]), element("dd", "", value));
      return row;
    }

    function open(work, focus = false) {
      active = work;
      for (const entry of entries) {
        const isActive = entry.work === work;
        entry.button.setAttribute("aria-pressed", String(isActive));
        entry.button.tabIndex = isActive ? 0 : -1;
      }
      card.replaceChildren();
      const header = element("div", "op-lineage-card-head");
      const title = element("h3", "op-lineage-title");
      const link = element("a", "", work.title);
      link.href = work.url;
      title.append(link);
      header.append(title);
      const meta = element("div", "op-lineage-meta");
      meta.append(
        element("span", "", String(work.year)),
        element("span", "", groups.get(work.group)?.label || work.group),
        element("span", "op-lineage-strength", work.link),
      );
      header.append(meta);
      card.append(header);
      if (work.note) card.append(element("p", "op-lineage-note", work.note));
      const rows = element("dl", "op-lineage-rows");
      for (const key of ["idea", "opulse", "borrow", "adds"]) {
        rows.append(addRow(key, work[key] || ""));
      }
      card.append(rows);
      const button = entries.find((entry) => entry.work === work)?.button;
      if (button) {
        scrollToButton(button);
        if (focus) button.focus({ preventScroll: true });
      }
    }

    function refresh() {
      let lastYear = null;
      for (const entry of entries) {
        const visible = selectedGroup === null || entry.work.group === selectedGroup;
        entry.item.hidden = !visible;
        if (visible) {
          entry.year.hidden = entry.work.year === lastYear;
          lastYear = entry.work.year;
        }
      }
      for (const [id, button] of groupButtons) {
        button.setAttribute("aria-pressed", String(selectedGroup === id));
      }
      if (!entries.some((entry) => entry.work === active && !entry.item.hidden)) {
        const first = entries.find((entry) => !entry.item.hidden);
        if (first) open(first.work);
      } else {
        const button = entries.find((entry) => entry.work === active).button;
        scrollToButton(button);
      }
    }

    for (const group of data.groups) {
      const button = element("button", `op-lineage-filter op-lineage-group-${group.id}`, group.label);
      button.type = "button";
      button.setAttribute("aria-pressed", "false");
      button.addEventListener("click", () => {
        selectedGroup = selectedGroup === group.id ? null : group.id;
        refresh();
      });
      filters.append(button);
      groupButtons.set(group.id, button);
    }

    for (const work of works) {
      const item = element("div", `op-lineage-item op-lineage-group-${work.group}`);
      const year = element("span", "op-lineage-year", String(work.year));
      const button = element("button", "op-lineage-node");
      button.type = "button";
      button.setAttribute("aria-label", `${work.year}: ${work.label}. ${groups.get(work.group)?.label || work.group}`);
      button.setAttribute("aria-pressed", "false");
      button.tabIndex = -1;
      button.append(element("span", "op-lineage-dot"));
      const nodeLabel = element("span", "op-lineage-node-label", work.label);
      year.addEventListener("click", () => button.click());
      nodeLabel.addEventListener("click", () => button.click());
      item.append(year, button, nodeLabel);
      axis.append(item);
      entries.push({ work, item, year, button });
      button.addEventListener("click", () => open(work));
      button.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
        event.preventDefault();
        const visible = entries.filter((entry) => !entry.item.hidden);
        const index = visible.findIndex((entry) => entry.work === work);
        const next = visible[index + (event.key === "ArrowRight" ? 1 : -1)];
        if (next) open(next.work, true);
      });
    }

    refresh();
    open(works.find((work) => work.id === "kleene") || works[0]);
  }

  const initAll = () => document.querySelectorAll(".op-lineage").forEach(init);
  if (window.document$ && typeof window.document$.subscribe === "function") {
    window.document$.subscribe(initAll);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll, { once: true });
  } else {
    initAll();
  }
})();
