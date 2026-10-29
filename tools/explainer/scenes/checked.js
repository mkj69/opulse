/* One model trace; the interpreter checks each proposed rewrite. */
(() => {
  'use strict';
  const X = window.OPX;
  const P = X.P;
  const lineY = 420;
  const fontSize = 68;
  const charWidth = fontSize * .6;

  function rewrite(parent, step, progress) {
    const eased = X.ease.inOut(progress);
    const oldLeft = 960 - step.before.length * charWidth / 2;
    const newLeft = 960 - step.after.length * charWidth / 2;
    const oldX = oldLeft + step.focus[0] * charWidth;
    const newX = newLeft + step.new[0] * charWidth;
    const focusX = X.lerp(oldX, newX, eased);
    const width = X.lerp((step.focus[1] - step.focus[0]) * charWidth,
      (step.new[1] - step.new[0]) * charWidth, eased);
    const change = X.reveal(eased, .4, .2);
    X.rect(parent, focusX - 6, lineY - 49, width + 12, 98,
      P.focusBg, 8, 'none', 0, { opacity: 1 - change });
    X.rect(parent, focusX - 6, lineY - 49, width + 12, 98,
      P.newBg, 8, 'none', 0, { opacity: change });
    X.rect(parent, focusX - 6, lineY + 50, width + 12, 3,
      P.amber, 1.5, 'none', 0, { opacity: 1 - change });
    X.rect(parent, focusX - 6, lineY + 50, width + 12, 3,
      P.cyan, 1.5, 'none', 0, { opacity: change });
    const drawText = (expression, span, x, y, opacity, color) => {
      if (opacity <= 0) return;
      const layer = X.group(parent, opacity);
      const line = X.text(layer, '', x, y,
        { size: fontSize, anchor: 'start', mono: true });
      X.el(line, 'tspan', { fill: P.ink }, expression.slice(0, span[0]));
      X.el(line, 'tspan', { fill: color }, expression.slice(...span));
      X.el(line, 'tspan', { fill: P.ink }, expression.slice(span[1]));
    };
    drawText(step.before, step.focus, oldLeft,
      lineY - 42 * X.reveal(eased, .25, .25), 1 - X.reveal(eased, .32, .34), P.amber);
    drawText(step.after, step.new, newLeft,
      lineY + 42 * (1 - X.reveal(eased, .5, .25)), X.reveal(eased, .32, .34), P.cyan);
  }

  function rowText(step) {
    const focus = step.before.slice(...step.focus).replace(/^\((.*)\)$/u, '$1');
    const result = step.after.slice(...step.new).replace(/^\((.*)\)$/u, '$1');
    const condition = step.branches && step.branches.find(branch => branch.condition);
    return `${focus} → ${result}${condition ? `  (${condition.substituted} false)` : ''}`;
  }

  X.scenes.checked = (p, u) => {
    const { steps, wrong, value } = X.D.checked;
    X.heading(p, 7, 'Every step checked', P.indigo);
    X.card(p, 165, 254, 1590, 248);
    X.text(p, 'INTERPRETER', 215, 309,
      { size: 38, anchor: 'start', weight: 750, color: P.muted, spacing: 2 });
    const interval = 1.18;
    const start = .55;
    const lastStart = start + wrong.index * interval;
    const current = Math.min(steps.length - 1, Math.max(0, Math.floor((u - start) / interval)));
    const local = u - start - current * interval;
    if (u < start) X.expr(p, steps[0].before, 960, lineY, { size: fontSize });
    else if (u >= 8.45) {
      const completion = X.reveal(u, 8.45, .55, X.ease.inOut);
      X.expr(p, steps[wrong.index].after, 960, lineY - 90 * completion,
        { size: fontSize, opacity: 1 - completion,
          mark: steps[wrong.index].new, markKind: 'new' });
      X.text(p, `value: ${value}`, 960, lineY,
        { size: 78, weight: 750, color: P.cyan,
          opacity: X.reveal(completion, .78, .22) });
    } else if (current === wrong.index) {
      if (u < 7.45) X.expr(p, steps[current].before, 960, lineY, { size: fontSize });
      else rewrite(p, steps[current], X.reveal(u, 7.45, .55, X.ease.inOut));
    }
    else rewrite(p, steps[current], X.reveal(local, .12, .54));

    const climax = X.reveal(u, 7, .34, X.ease.inOut);
    const history = X.place(p, { opacity: 1 - X.reveal(u, 6.85, .15, X.ease.inOut) });
    X.text(history, "MODEL'S STEPS", 185, 560,
      { size: 38, anchor: 'start', weight: 750, color: P.muted, spacing: 2 });
    steps.slice(0, -1).forEach((step, index) => {
      const elapsed = u - start - index * interval;
      const arrival = X.reveal(elapsed, .42, .35, X.ease.inOut);
      const scroll = Math.min(3, Math.max(0, current - 2 + X.reveal(local, .2, .8, X.ease.inOut)));
      const y = 610 + (index - scroll) * 103;
      const visible = arrival * X.reveal(y, 575, 35) * (1 - X.reveal(y, 780, 38));
      if (visible < .001) return;
      const g = X.place(history, { opacity: visible, dy: 22 * (1 - arrival) });
      X.card(g, 165, y, 1590, 95, { top: false, rx: 13 });
      X.text(g, String(index + 1).padStart(2, '0'), 205, y + 48,
        { size: 38, weight: 750, anchor: 'start', color: P.muted });
      X.text(g, step.kind === 'expand' ? 'UNFOLD' : 'COMPUTE', 295, y + 48,
        { size: 42, anchor: 'start', weight: 750, color: step.kind === 'expand' ? P.amber : P.cyan });
      X.text(g, rowText(step), 570, y + 48,
        { size: 45, anchor: 'start', mono: true, color: P.ink });
      X.text(g, '✓', 1695, y + 48,
        { size: 50, weight: 750, color: P.green });
    });

    const reject = X.reveal(u, lastStart + .65, .52, X.ease.inOut);
    const verdict = X.place(p, { opacity: climax });
    X.text(verdict, 'MODEL PROPOSED', 207, 570,
      { size: 40, anchor: 'start', weight: 750, color: P.red, spacing: 1.4 });
    X.card(verdict, 165, 601, 1590, 127, { accent: P.red });
    const proposal = `${steps[wrong.index].before} = ${wrong.after}`;
    X.text(verdict, proposal, 282, 665,
      { size: 60, anchor: 'start', mono: true, weight: 700, color: P.red });
    X.line(verdict, 285, 666, 285 + X.textWidth(proposal, 60, true), 666,
      P.red, 3.5 * reject);
    X.text(verdict, '×', 1640, 665, { size: 65, color: P.red, weight: 750, opacity: reject });
    const correction = X.place(verdict, { opacity: X.reveal(u, 7.9, .53, X.ease.inOut),
      dy: 36 * (1 - X.reveal(u, 7.9, .53, X.ease.inOut)) });
    X.text(correction, 'INTERPRETER CORRECTS', 207, 769,
      { size: 40, anchor: 'start', weight: 750, color: P.green, spacing: 1.4 });
    X.card(correction, 165, 800, 1590, 125, { accent: P.green });
    X.text(correction, `${steps[wrong.index].before} = ${value}`, 282, 863,
      { size: 61, anchor: 'start', mono: true, weight: 700, color: P.green });
    X.text(correction, '✓', 1640, 863, { size: 65, color: P.green, weight: 750 });
  };
})();
