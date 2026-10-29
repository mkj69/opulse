/* Horizontal overflow cue for tables, code, and benchmark charts. */
(() => {
  const selector = [
    ".md-typeset__table",
    ".md-typeset__scrollwrap",
    ".md-typeset .highlight pre",
    ".md-typeset pre > code",
    ".md-typeset table:not([class])",
    ".op-lineage-viewport",
    ".owt-scroll",
    ".owt-value",
    ".ow-step-visual",
    ".ow-pane-body",
    ".stv-table-wrap",
    '.md-typeset p:has(> img[src*="/assets/benchmark/"])'
  ].join(", ");
  let active = [];
  let resizeTimer;

  function setPageLayout() {
    const main = document.querySelector(".md-main__inner");
    if (!main) return;
    const article = main.querySelector(".md-content__inner");
    const primary = main.querySelector(".md-sidebar--primary");
    if (!article) return;
    main.dataset.opLayout = article.querySelector(".stv-page")
      ? "app"
      : primary && !primary.hidden ? "with-nav"
      : article.querySelector(".op-hero h1#opulse") ? "home" : "single";
  }

  function update(el) {
    const overflowing = el.scrollWidth > el.clientWidth + 2;
    el.classList.toggle("op-overflow", overflowing);
    el.classList.toggle("op-scrolled-end", overflowing &&
      el.scrollLeft + el.clientWidth >= el.scrollWidth - 2);
  }

  function init() {
    setPageLayout();
    active.forEach((el) => {
      el.removeEventListener("scroll", onScroll);
      el.classList.remove("op-overflow", "op-scrolled-end");
    });
    active = Array.from(document.querySelectorAll(selector)).filter((el) => {
      const overflow = getComputedStyle(el).overflowX;
      return (overflow === "auto" || overflow === "scroll") && el.clientWidth > 0;
    });
    active.forEach((el) => {
      el.addEventListener("scroll", onScroll, { passive: true });
      update(el);
    });
  }

  function onScroll(event) { update(event.currentTarget); }
  function schedule() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(init, 120);
  }

  window.addEventListener("resize", schedule, { passive: true });
  document.addEventListener("load", (event) => {
    if (event.target instanceof HTMLImageElement) schedule();
  }, true);
  if (window.document$ && typeof window.document$.subscribe === "function") {
    window.document$.subscribe(init);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
