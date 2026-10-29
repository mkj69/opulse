/* Six reasoning tasks: a compact overview, each example brought into focus. */
(() => {
  'use strict';
  const X = window.OPX;
  const P = X.P;
  const positions = [[155, 253], [705, 253], [1255, 253],
    [155, 575], [705, 575], [1255, 575]];
  const names = ['Compute', 'Invert', 'Decide', 'Describe', 'Induce', 'Create'];
  const first = .72;
  const interval = 1.61;
  const end = first + 6 * interval;

  function line(p, text, x, y, size = 58, color = P.ink, mono = true) {
    X.text(p, text, x, y, { size, color, mono, weight: 650 });
  }

  function subtitle(p, words, x, y) {
    const parts = words.split(' ');
    const lines = [''];
    parts.forEach(word => {
      const last = lines.length - 1;
      const joined = `${lines[last]} ${word}`.trim();
      if (X.textWidth(joined, 36) > 420 && lines[last]) lines.push(word);
      else lines[last] = joined;
    });
    lines.forEach((text, index) => X.text(p, text, x, y + 39 * index,
      { size: 36, color: P.muted, anchor: 'start' }));
  }

  function play(p, angle, index, local) {
    const go = (at, span) => X.reveal(local, at, span, X.ease.inOut);
    if (index === 0) {
      line(p, `${angle.expression} =`, 875, 597, 68);
      const progress = go(.3, .6);
      line(X.place(p, { opacity: progress }), angle.result,
        X.lerp(1095, 1050, progress), X.lerp(712, 597, progress), 72, P.cyan);
    } else if (index === 1) {
      line(p, `${angle.symbol} ${angle.given} = ${angle.target}`, 990, 595, 68);
      const progress = go(.63, .47);
      line(X.place(p, { opacity: 1 - go(.45, .18) }), '?', 751, 595, 70, P.amber);
      line(X.place(p, { opacity: progress }), angle.candidate,
        X.lerp(786, 751, progress), X.lerp(700, 595, progress), 70, P.cyan);
    } else if (index === 2) {
      line(p, angle.claim, 960, 520, 61);
      const checks = angle.checks;
      line(p, `${checks[0].expression} = ${checks[0].value}`, 660, 642, 54, P.muted);
      line(p, `${checks[1].expression} =`, 1250, 642, 54, P.muted);
      const progress = go(.48, .57);
      X.text(X.place(p, { opacity: progress }), checks[1].value,
        X.lerp(1420, 1380, progress), X.lerp(722, 642, progress),
        { size: 54, color: P.cyan, mono: true, anchor: 'start', weight: 650 });
      X.text(p, 'TRUE for every a, b', 960, 779,
        { size: 51, color: P.green, weight: 750, opacity: go(1.04, .25) });
    } else if (index === 3) {
      line(p, angle.rule, 960, 551, 52);
      const progress = go(.45, .65);
      const gloss = X.place(p, { opacity: progress, dy: 35 * (1 - progress) });
      X.text(gloss, angle.words[0], 960, 671, { size: 55, color: P.cyan, weight: 700 });
      X.text(gloss, angle.words[1], 960, 743, { size: 55, color: P.cyan, weight: 700 });
    } else if (index === 4) {
      angle.examples.forEach((example, row) => {
        const progress = go(.18 + row * .19, .35);
        const entry = X.place(p, { opacity: progress, dy: 36 * (1 - progress) });
        line(entry, `${example.expression} = ${example.value}`, 518 + row * 441, 601, 52,
          row === 2 ? P.cyan : P.ink);
      });
      X.text(p, angle.words, 960, 755,
        { size: 56, color: P.cyan, weight: 700, opacity: go(.85, .4) });
    } else {
      X.text(p, `TARGET  ${angle.target}`, 960, 534,
        { size: 56, color: P.amber, weight: 750 });
      const words = angle.expression.split(' ');
      words.forEach((word, part) => {
        const progress = go(.22 + part * .16, .45);
        line(X.place(p, { opacity: progress }), word,
          758 + part * 137, X.lerp(739, 663, progress), 70, P.cyan);
      });
      const progress = go(.84, .4);
      line(X.place(p, { opacity: progress }), `= ${angle.target}`,
        1177, X.lerp(739, 663, progress), 63, P.green);
    }
  }

  X.scenes.six_angles = (p, u) => {
    X.heading(p, 8, 'Six angles on reasoning', P.indigo);
    const angles = X.D.six_angles.angles;
    const activeIndex = u >= first && u < end ? Math.floor((u - first) / interval) : -1;
    const local = activeIndex < 0 ? 0 : u - first - activeIndex * interval;
    const expand = activeIndex < 0 ? 0 : X.reveal(local, 0, .22, X.ease.inOut) *
      (1 - X.reveal(local, 1.36, .25, X.ease.inOut));
    positions.forEach(([x, y], index) => {
      const introduction = X.reveal(u, .08 + index * .075, .42, X.ease.inOut);
      const tile = X.place(p, { opacity: introduction * (1 - X.reveal(expand, .12, .25)),
        dy: 25 * (1 - introduction) });
      X.card(tile, x, y, 510, 300, { accent: index < activeIndex || u >= end ? P.green : null });
      X.text(tile, String(index + 1).padStart(2, '0'), x + 40, y + 59,
        { size: 38, color: P.indigo, weight: 750, anchor: 'start' });
      X.text(tile, names[index], x + 42, y + 138,
        { size: 58, color: P.ink, weight: 750, anchor: 'start' });
      subtitle(tile, angles[index].meaning, x + 42, y + 215);
      const verified = X.reveal(u, first + (index + 1) * interval, .32, X.ease.inOut);
      X.text(tile, '✓', x + 443, y + 61,
        { size: 49, color: P.green, weight: 750, opacity: verified });
    });
    if (activeIndex < 0 || expand <= .001) return;
    const [tileX, tileY] = positions[activeIndex];
    const x = X.lerp(tileX, 245, expand), y = X.lerp(tileY, 250, expand);
    const w = X.lerp(510, 1430, expand), h = X.lerp(300, 655, expand);
    const focus = X.place(p, { opacity: X.reveal(expand, .72, .28) });
    X.card(focus, x, y, w, h, { accent: P.indigo });
    const text = X.place(focus, { opacity: X.reveal(expand, .88, .12) });
    X.text(text, String(activeIndex + 1).padStart(2, '0'), 315, 344,
      { size: 38, color: P.indigo, weight: 750, anchor: 'start' });
    X.text(text, names[activeIndex], 960, 361,
      { size: 66, color: P.ink, weight: 750 });
    X.text(text, angles[activeIndex].meaning, 960, 429,
      { size: 42, color: P.muted });
    play(text, angles[activeIndex], activeIndex, local);
  };
})();
