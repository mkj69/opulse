(() => {
  'use strict';
  const X = window.OPX;
  const P = X.P;

  X.scenes.recursion = (p, u) => {
    X.heading(p, 5, 'Recursion', P.magenta);
    const data = X.D.recursion;
    const expands = data.steps.filter(step => step.kind === 'expand');
    const base = data.expression.split(' ★ ')[0];
    const enter = X.reveal(u, .13, .65, X.ease.out);
    const rule = X.place(p, { opacity: enter, dy: 18 * (1 - enter) });
    X.card(rule, 190, 239, 1540, 227);
    X.chip(rule, 'recursive', 386, 289, 'recursive', 34);
    X.text(rule, 'a to the power b', 1475, 289,
      { size: 34, color: P.muted, weight: 600 });
    X.text(rule, 'a ★ b =', 487, 386,
      { size: 56, mono: true, weight: 750 });
    const baseHighlight = X.window(u, 4.8, 6.2, .38, .4);
    const repeatHighlight = X.window(u, .9, 4.9, .4, .4) +
      X.window(u, 6.15, 10.9, .4, .4);
    X.rect(rule, 689, 336, 840, 58, P.newBg, 11, P.magenta, 2,
      { opacity: baseHighlight });
    X.rect(rule, 689, 398, 840, 58, P.newBg, 11, P.magenta, 2,
      { opacity: repeatHighlight });
    X.text(rule, '1  if b <= 0', 714, 365,
      { size: 43, mono: true, anchor: 'start' });
    X.text(rule, 'a * (a ★ (b - 1))  otherwise', 714, 427,
      { size: 40, mono: true, anchor: 'start' });

    expands.forEach((step, depth) => {
      const call = step.branches[0].substituted.split(' <= ')[0];
      const rowY = 488 + depth * 81;
      const start = .77 + depth * .88;
      const appeared = X.reveal(u, start, .45, X.ease.out);
      if (!appeared) return;
      const foldAt = 5.05 + (4 - depth) * .86;
      const returned = X.reveal(u, foldAt, .43);
      const row = X.place(p, { opacity: appeared, dx: 24 * (1 - appeared) });
      X.card(row, 220, rowY, 1090, 67, { top: false });
      X.rect(row, 220, rowY, 1090, 67, 'none', 16, P.magenta, 3,
        { opacity: (1 - returned) * .72 });
      X.text(row, `${base} ★ ${call}`, 445, rowY + 33,
        { size: 45, mono: true, color: P.magenta, weight: 750 });
      const next = depth < 4
        ? `${base} * (${base} ★ ${expands[depth + 1].branches[0].substituted.split(' <= ')[0]})`
        : step.branches[0].body;
      X.text(row, next, 918, rowY + 33,
        { size: 41, mono: true, color: P.muted,
          opacity: 1 - X.reveal(u, foldAt - .26, .2) });
      const value = data.fold[4 - depth];
      const resolved = depth === 4 ? `= ${value}` :
        `${base} * ${data.fold[3 - depth]} = ${value}`;
      X.text(row, resolved, 918, rowY + 33,
        { size: 43, mono: true, color: P.indigo, weight: 800,
          opacity: X.reveal(u, foldAt, .3) });
      if (depth < 4) {
        const childStart = .77 + (depth + 1) * .88;
        const down = X.reveal(u, childStart - .32, .5);
        if (down > .01) X.arrow(p, 315, rowY + 69, 315, rowY + 80,
          { color: P.magenta, sw: 4, head: 7, k: down });
        const flowing = X.reveal(u, foldAt - .52, .58);
        if (flowing > 0 && flowing < 1) {
          const point = X.qpoint([1324, rowY + 114], [1335, rowY + 72],
            [1324, rowY + 33], flowing);
          X.token(p, data.fold[3 - depth], point[0], point[1], P.indigo,
            { size: 38, opacity: Math.sin(Math.PI * flowing) });
        }
      }
    });

    const enterPanel = X.reveal(u, 1, .55, X.ease.out);
    const panel = X.place(p, { opacity: enterPanel, dx: 18 * (1 - enterPanel) });
    X.card(panel, 1380, 577, 368, 257, { accent: P.magenta });
    const answer = X.reveal(u, 9.08, .65, X.ease.out);
    X.text(panel, data.expression, 1564, 654,
      { size: 62, mono: true, color: P.magenta, weight: 800 });
    X.text(panel, 'unfold', 1564, 735,
      { size: 42, color: P.muted, weight: 650,
        opacity: 1 - X.reveal(u, 4.85, .18) });
    X.text(panel, 'return', 1564, 735,
      { size: 42, color: P.indigo, weight: 700,
        opacity: X.reveal(u, 5.15, .22) * (1 - X.reveal(u, 8.9, .17)) });
    X.text(panel, `= ${data.value}`, 1564, 747,
      { size: 86, mono: true, weight: 800, opacity: answer });
  };
})();
