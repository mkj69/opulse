(() => {
  'use strict';
  const X = window.OPX;
  const P = X.P;

  X.scenes.branch = (p, u) => {
    X.heading(p, 4, 'Choice', P.amber);
    const runs = X.D.branch;
    const enter = X.reveal(u, .12, .65, X.ease.out);
    const rule = X.place(p, { opacity: enter, dy: 18 * (1 - enter) });
    X.card(rule, 190, 240, 1540, 240);
    X.chip(rule, 'branch', 352, 288, 'branch', 34);
    X.text(rule, 'distance between a and b', 1455, 288,
      { size: 34, color: P.muted, weight: 600 });
    X.text(rule, 'a ▲ b =', 520, 395, { size: 60, mono: true, weight: 750 });
    const firstCase = X.window(u, 1.75, 4.5, .35, .42);
    const secondCase = X.reveal(u, 5.65, .38);
    X.rect(rule, 690, 342, 850, 61, P.focusBg, 12, P.amber, 2,
      { opacity: firstCase });
    X.rect(rule, 690, 408, 850, 61, P.focusBg, 12, P.amber, 2,
      { opacity: secondCase });
    X.text(rule, 'a - b', 723, 372, { size: 48, mono: true, anchor: 'start', weight: 700 });
    X.text(rule, 'if a >= b', 1034, 372, { size: 44, mono: true, anchor: 'start' });
    X.text(rule, 'b - a', 723, 438, { size: 48, mono: true, anchor: 'start', weight: 700 });
    X.text(rule, 'otherwise', 1034, 438, { size: 44, mono: true, anchor: 'start' });

    runs.forEach((run, index) => {
      const start = index ? 4.48 : .78;
      const center = index ? 1350 : 570;
      const appeared = X.reveal(u, start, .48, X.ease.out);
      if (!appeared) return;
      const selected = run.steps[0].branch_index - 1;
      const caseBox = X.place(p, { opacity: appeared, dy: 13 * (1 - appeared) });
      X.card(caseBox, center - 337, 777, 674, 143, { top: false });
      X.rect(caseBox, center - 337, 777, 674, 143, 'none', 19, P.amber, 3,
        { opacity: X.reveal(u, start + 2, .55) });
      X.text(caseBox, selected ? 'otherwise: b - a' : 'if a >= b: a - b', center, 816,
        { size: 37, mono: true, color: P.muted });
      X.expr(caseBox, run.expression, center, 874,
        { size: 52, color: P.amber, opacity: 1 - X.reveal(u, start + 2.15, .22) });
      X.expr(caseBox, run.steps[0].after, center, 874,
        { size: 52, color: P.amber,
          opacity: X.window(u, start + 2.46, start + 3.13, .22, .2) });
      X.expr(caseBox, `${run.expression} = ${run.value}`, center, 874,
        { size: 55, weight: 800, opacity: X.reveal(u, start + 3.18, .34) });
    });

    const second = X.reveal(u, 4.17, .24, X.ease.inOut);
    runs.forEach((run, index) => {
      const start = index ? 4.48 : .78;
      const visible = (index ? second : 1 - second) * X.reveal(u, start, .48);
      if (visible < .001) return;
      const live = X.group(p, visible);
      const condition = run.steps[0].branches[0];
      const selected = run.steps[0].branch_index - 1;
      const center = selected ? 1350 : 570;
      const substitution = X.reveal(u, start + 1.14, .28);
      X.expr(live, run.expression, 960, 519, { size: 52, color: P.amber,
        opacity: 1 - X.reveal(u, start + .47, .4) });
      X.path(live, 'M 960 557 L 1130 647 L 960 737 L 790 647 Z',
        P.lineStrong, 3, P.panel);
      X.text(live, condition.condition, 960, 632,
        { size: 44, mono: true,
          opacity: 1 - X.reveal(u, start + .32, .15) });
      X.text(live, condition.substituted, 960, 632,
        { size: 46, mono: true, color: P.amber, weight: 750, opacity: substitution });
      X.text(live, condition.truth ? 'TRUE' : 'FALSE', 960, 691,
        { size: 36, color: P.amber, weight: 800,
          opacity: X.reveal(u, start + 1.45, .38) });
      const travel = X.reveal(u, start + .49, .61);
      if (travel > 0 && travel < 1) {
        run.expression.split(' ▲ ').forEach((operand, side) => {
          const point = X.qpoint([side ? 1048 : 872, 517],
            [side ? 1085 : 835, 556], [side ? 1038 : 882, 634], travel);
          X.token(live, operand, point[0], point[1], P.amber,
            { size: 38, opacity: Math.sin(Math.PI * travel) });
        });
      }
      const routing = X.reveal(u, start + 1.72, .67);
      if (routing > .01) {
        X.arrow(live, selected ? 1130 : 790, 647, center, 771,
          { color: P.amber, sw: 5, opacity: routing, head: 13 });
      }
      const resultTravel = X.reveal(u, start + 2.24, .67);
      if (resultTravel > 0 && resultTravel < 1) {
        const from = [selected ? 1130 : 790, 647];
        const to = [center, 773];
        const point = X.qpoint(from, [(from[0] + center) / 2, 731], to, resultTravel);
        X.token(live, run.steps[0].after, point[0], point[1], P.amber,
          { size: 36, opacity: Math.sin(Math.PI * resultTravel) });
      }
    });
  };
})();
