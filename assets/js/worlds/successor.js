(function () {
  "use strict";
  // The number line comes from integer.js, which the page loads before this file.
  const worlds = window.OpulseWorlds;
  function draw(el, value, ctx, previous, step) {
    if (worlds.numberLine) worlds.numberLine(el, value, ctx, previous, 0, step);
    else worlds.fallbackValue(el, value);
  }
  worlds.register("successor", {
    renderValue(el, value, ctx) { draw(el, value, ctx); },
    renderStep(el, step, ctx) {
      const changed = !ctx.steps || !ctx.steps[ctx.index] || ctx.steps[ctx.index].value;
      draw(el, step.value, ctx, changed ? step.previous : null, step);
    }
  });
})();
