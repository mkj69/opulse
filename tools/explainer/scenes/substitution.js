/* A ◆ becomes its body; arguments enter the leaves and computed values flow upward. */
(() => {
  'use strict';
  const X = window.OPX;
  const root = [960, 475];
  const products = [[650, 635], [1270, 635]];
  const slots = [[350, 805], [800, 805], [1120, 805], [1570, 805]];
  const sources = [[650, 500], [1270, 500]];

  X.scenes.substitution = (p, u) => {
    const { P } = X;
    const trace = X.D.substitution;
    const expression = trace.expression.split(' ');
    const arguments_ = [expression[0], expression[2]];
    const values = [trace.steps[1].output, trace.steps[2].output];
    X.heading(p, 3, 'Substitution', P.cyan);

    const definition = X.reveal(u, .35, .7, X.ease.out);
    if (definition) {
      const group = X.place(p, { opacity: definition, dy: 18 * (1 - definition) });
      X.card(group, 180, 242, 1560, 135);
      X.chip(group, 'simple', 330, 310, 'simple', 34);
      const rule = X.D.rules.squares.replace(/[{}]/g, '').replace(/\s+/g, ' ').trim();
      X.text(group, rule, 1060, 310, { size: 47, mono: true, weight: 600 });
    }

    const initial = X.reveal(u, .85, .65, X.ease.out);
    const growth = X.reveal(u, 2.38, 1.05, X.ease.inOut);
    const leafGrowth = X.reveal(u, 2.95, .85, X.ease.inOut);
    const transfer = X.reveal(u, 4.05, 1.35, X.ease.inOut);
    const productTime = [5.95, 6.45];
    const productFlow = [X.reveal(u, 6.85, .75, X.ease.inOut),
      X.reveal(u, 7.35, .75, X.ease.inOut)];
    const rootFlow = X.reveal(u, 8.05, .58, X.ease.inOut);
    const rootValue = X.reveal(u, 8.66, .24, X.ease.out);
    const final = X.reveal(u, 8.9, .4, X.ease.out);

    if (initial) {
      const old = initial * (1 - X.reveal(u, 2.15, .35));
      if (old) {
        X.node(X.place(p, { opacity: old }), ...root, expression[1], P.cyan,
          { h: 136, w: 148, size: 76 });
        sources.forEach(([x, y], index) => {
          X.arrow(p, x + (index ? -64 : 64), y, root[0] + (index ? 78 : -78), root[1],
            { color: P.lineStrong, opacity: old, k: initial, head: 13 });
        });
      }
      const sourceOpacity = initial * (1 - X.reveal(u, 3.7, .5));
      if (sourceOpacity) sources.forEach(([x, y], index) =>
        X.node(X.place(p, { opacity: sourceOpacity }), x, y, arguments_[index], P.ink,
          { h: 126, w: 132, size: 66, sw: 3 }));
    }

    if (growth) {
      const tree = X.place(p, { opacity: X.reveal(u, 2.51, .45, X.ease.out) });
      const rootSymbol = 1 - X.reveal(u, 8.13, .28);
      X.node(tree, ...root, '', P.cyan, { h: 136, w: 148 });
      X.text(tree, trace.steps[3].symbol, root[0], root[1] + 2,
        { size: 78, mono: true, weight: 700, color: P.cyan, opacity: rootSymbol });
      X.text(tree, trace.value, root[0], root[1] + 2,
        { size: 68, mono: true, weight: 700, color: P.cyan, opacity: rootValue });

      products.forEach(([x, y], index) => {
        const [productX, productY] = [X.lerp(root[0], x, growth), X.lerp(root[1], y, growth)];
        const productEntry = X.reveal(u, 2.9, .34, X.ease.out);
        const productEdge = X.reveal(u, 3.42, .25, X.ease.out);
        if (productEdge) X.arrow(p, productX, productY - 68,
          root[0] + (index ? 77 : -77), root[1] + 70,
          { color: P.lineStrong, opacity: productEdge, head: 13, sw: 5 });

        const product = X.place(p, { opacity: productEntry });
        X.node(product, productX, productY, '', P.atom, { h: 132, w: 142 });
        const symbolOpacity = X.reveal(u, 2.9, .34) *
          (1 - X.reveal(u, productTime[index], .3));
        X.text(product, trace.steps[index + 1].symbol, productX, productY + 2,
          { size: 72, mono: true, weight: 700, color: P.atom, opacity: symbolOpacity });
        const valueOpacity = X.reveal(u, productTime[index] + .32, .28, X.ease.out);
        X.text(product, values[index], productX, productY + 2,
          { size: 70, mono: true, weight: 700, color: P.cyan, opacity: valueOpacity });

        for (let side = 0; side < 2; side++) {
          const [slotX, slotY] = slots[index * 2 + side];
          const leafX = X.lerp(productX, slotX, leafGrowth);
          const leafY = X.lerp(productY, slotY, leafGrowth);
          const leafEntry = X.reveal(u, 3.45, .36, X.ease.out);
          const leafEdge = X.reveal(u, 3.8, .22, X.ease.out);
          if (leafEdge) X.arrow(p, leafX, leafY - 61,
            productX + (side ? 73 : -73), productY + 68,
            { color: P.lineStrong, opacity: leafEdge, head: 12, sw: 5 });
          if (leafEntry) {
            const leaf = X.place(p, { opacity: leafEntry });
            X.node(leaf, leafX, leafY, '', P.muted,
              { h: 120, w: 128, sw: 3 });
            X.rect(leaf, leafX - 64, leafY - 60, 128, 120, 'none', 22, P.cyan, 3,
              { opacity: X.reveal(u, 5.17, .33, X.ease.out) });
            X.text(leaf, index ? 'b' : 'a', leafX, leafY + 2,
              { size: 68, mono: true, weight: 700, color: P.muted,
                opacity: 1 - X.reveal(u, 4.08, .26) });
            X.text(leaf, arguments_[index], leafX, leafY + 2,
              { size: 68, mono: true, weight: 700, color: P.cyan,
                opacity: X.reveal(u, 5.35, .28, X.ease.out) });
          }
        }
      });

      if (transfer > 0 && transfer < 1) slots.forEach((slot, index) => {
        const source = sources[Math.floor(index / 2)];
        const from = [source[0] + (index % 2 ? 25 : -25), source[1] + 74];
        const [x, y] = X.qpoint(from, [(from[0] + slot[0]) / 2, 688],
          [slot[0], slot[1] - 70], transfer);
        X.token(p, arguments_[Math.floor(index / 2)], x, y, P.cyan,
          { size: 46, opacity: Math.min(1, transfer * 9, (1 - transfer) * 9) });
      });

      values.forEach((value, index) => {
        const progress = productFlow[index];
        if (progress > 0 && progress < 1) {
          const from = [products[index][0], products[index][1] - 76];
          const to = [root[0] + (index ? 83 : -83), root[1] + 77];
          const [x, y] = X.qpoint(from, [(from[0] + to[0]) / 2, 525], to, progress);
          X.token(p, value, x, y, P.cyan,
            { size: 46, opacity: Math.min(1, progress * 9, (1 - progress) * 9) });
        }
      });
      if (rootFlow > 0 && rootFlow < 1) X.token(p, trace.value, root[0],
        X.lerp(root[1] + 94, root[1] + 8, rootFlow), P.cyan,
        { size: 46, opacity: Math.min(1, rootFlow * 8, (1 - rootFlow) * 8) });
    }

    if (final) {
      const group = X.place(p, { opacity: final, dy: 18 * (1 - final) });
      X.card(group, 1180, 414, 560, 108, { accent: P.cyan });
      X.text(group, `${trace.expression} = ${trace.value}`, 1460, 468,
        { size: 68, mono: true, weight: 700 });
    }
  };
})();
