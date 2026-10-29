/* Homepage example tabs. The granularity widget in each panel uses its own checked data file. */
(function () {
  "use strict";

  function init() {
    document.querySelectorAll(".op-home-examples:not([data-ready])").forEach(root => {
      root.dataset.ready = "true";
      const tabs = Array.from(root.querySelectorAll(".op-home-tab"));
      const panels = tabs.map(tab => document.getElementById(tab.getAttribute("aria-controls")));
      function select(index, focus) {
        tabs.forEach((tab, i) => {
          const active = i === index;
          tab.setAttribute("aria-selected", String(active));
          tab.tabIndex = active ? 0 : -1;
          panels[i].hidden = !active;
        });
        if (focus) tabs[index].focus();
      }
      tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => select(index, false));
        tab.addEventListener("keydown", event => {
          const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
          const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 :
            step ? (index + step + tabs.length) % tabs.length : null;
          if (next === null) return;
          event.preventDefault();
          select(next, true);
        });
      });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
  if (window.document$) window.document$.subscribe(init);
}());
