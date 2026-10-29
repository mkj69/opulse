/* Blog figures: the step checker in a blog figure has a sheet of fixed height
   (docs/assets/css/blogfig.css). Keep the current line in view inside that sheet without
   scrolling the page. */
(function () {
  function follow(sheet) {
    const update = () => {
      const cur = sheet.querySelector(".opv-cur");
      if (!cur) return;
      const top = cur.getBoundingClientRect().top - sheet.getBoundingClientRect().top + sheet.scrollTop;
      const want = top - sheet.clientHeight / 2 + cur.offsetHeight / 2;
      sheet.scrollTop = Math.max(0, want);
    };
    new MutationObserver(update).observe(sheet, { subtree: true, attributes: true, attributeFilter: ["class"] });
  }
  function init() {
    document.querySelectorAll("figure.op-blogfig .opv").forEach((root) => {
      const wait = new MutationObserver(() => {
        const sheet = root.querySelector(".opv-sheet");
        if (sheet && !sheet.dataset.follow) { sheet.dataset.follow = "1"; follow(sheet); wait.disconnect(); }
      });
      wait.observe(root, { childList: true, subtree: true });
      const sheet = root.querySelector(".opv-sheet");
      if (sheet && !sheet.dataset.follow) { sheet.dataset.follow = "1"; follow(sheet); wait.disconnect(); }
    });
  }
  if (typeof document$ !== "undefined") document$.subscribe(init);
  else document.addEventListener("DOMContentLoaded", init);
})();
