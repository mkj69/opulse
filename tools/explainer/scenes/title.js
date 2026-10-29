/* Title card: the site's cover (tools/video/record.py CARD_CSS) drawn as SVG, revealed in order. */
(() => {
  'use strict';
  const X = window.OPX;
  // Layout of the old HTML card at 1920 x 1080: a centred column of logo, name, rule, two lines.
  const Y = { logo: 350, name: 508, rule: 615, line1: 697, line2: 769 };
  X.titleCard = function (p, u, { lines = ['Finite atoms, endless concepts.', 'Every step of reasoning, in plain sight.'] } = {}) {
    const { P, reveal, ease, place } = X;
    const k = reveal(u, .15, 1.1, ease.out);
    X.logo(place(p, { opacity: k, k: X.lerp(.82, 1, k), cx: 960, cy: Y.logo }), 960, Y.logo, 150);
    const name = reveal(u, .75, .9, ease.out);
    X.wordmark(place(p, { opacity: name, dy: 18 * (1 - name) }), 960, Y.name, 112);
    X.brandRule(p, 960, Y.rule, 140, reveal(u, 1.45, .7));
    lines.forEach((s, i) => {
      const a = reveal(u, 1.95 + i * .55, .8, ease.out);
      X.text(place(p, { opacity: a, dy: 14 * (1 - a) }), s, 960, i ? Y.line2 : Y.line1,
        { size: 50, weight: 500, color: P.ink });
    });
  };
  X.scenes.title = (p, u) => X.titleCard(p, u);
})();
