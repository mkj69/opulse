/* End card: the title card's look with the closing lines and the site address. */
(() => {
  'use strict';
  const X = window.OPX;
  X.scenes.end = (p, u) => {
    X.titleCard(p, u, { lines: ['Endless concepts. Every step proven.'] });
    const reveal = X.reveal(u, 2.75, .8, X.ease.out);
    X.text(X.place(p, { opacity: reveal, dy: 14 * (1 - reveal) }),
      'mkj69.github.io/opulse', 960, 790,
      { size: 52, weight: 500, mono: true, color: X.dark ? '#67e8f9' : '#0e7490', spacing: .52 });
  };
})();
