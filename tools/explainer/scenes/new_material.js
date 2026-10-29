/* Scene 9: one fixed composition, with values moving through three typed worlds. */
(() => {
  'use strict';
  const X = window.OPX;
  const centers = [395, 960, 1525];
  const cardTop = 440;
  const valueY = 778;
  const gridSize = 88;
  const gridPitch = 99;

  function slots(type, count) {
    const pitch = type === 'str' ? 115 : 96;
    return Array.from({ length: count }, (_, index) => (index - (count - 1) / 2) * pitch);
  }

  function piece(p, value, x, y, type, color, letterFlip = 0, capital = value) {
    const size = type === 'str' ? 104 : 86;
    X.rect(p, x - size / 2, y - size / 2, size, size, X.P.panel2, 16, color, 2.5);
    if (type === 'str' && letterFlip > 0) {
      const front = letterFlip < .5;
      const scale = Math.max(.015, Math.abs(1 - 2 * letterFlip));
      const face = X.el(p, 'g', { transform: `translate(${x} ${y}) scale(1 ${scale}) translate(${-x} ${-y})` });
      X.text(face, front ? value : capital, x, y + 1, { size: 62, color, weight: 750 });
    } else {
      X.text(p, value, x, y + 1, { size: type === 'str' ? 62 : 56, color, weight: 750 });
    }
  }

  function letters(p, world, stage, center, color, motion = null) {
    const list = world.type === 'str' ? [...world.values[stage]]
      : world.type === 'perm' ? world.cards[stage] : world.values[stage];
    const places = slots(world.type, list.length);
    list.forEach((value, index) => {
      let x = center + places[index];
      let y = valueY;
      let flip = 0;
      if (motion && motion.kind === 'travel') {
        x -= 565 * (1 - motion.progress);
        y -= (world.type === 'perm' ? 125 : 105) * Math.sin(Math.PI * motion.progress);
      } else if (motion && motion.kind === 'reorder') {
        const destination = motion.rotate ? (index + 1) % list.length : list.length - 1 - index;
        x = X.lerp(x, center + places[destination], motion.progress);
        const middle = (list.length - 1) / 2;
        const direction = motion.rotate ? (index === list.length - 1 ? -1 : 1)
          : index < middle ? -1 : index > middle ? 1 : 0;
        const height = motion.rotate ? 92 : world.type === 'str' ? 100
          : 50 + 38 * Math.abs(index - middle);
        y += direction * height * Math.sin(Math.PI * motion.progress);
      } else if (motion && motion.kind === 'uppercase') {
        flip = motion.progress;
      }
      if (motion && motion.kind === 'travel' && motion.progress <= .22) return;
      const ink = motion && motion.kind === 'travel'
        ? X.place(p, { opacity: X.reveal(motion.progress, .22, .13) }) : p;
      piece(ink, String(value), x, y, world.type, color, flip, world.values[2][index]);
    });
  }

  function grid(p, cells, center, rotation = 0, mirror = 1) {
    const outer = X.el(p, 'g', { transform: `translate(${center} ${valueY - 14}) scale(${mirror} 1) rotate(${rotation})` });
    const colors = [X.P.panel2, X.P.cyan, X.P.magenta, X.P.amber];
    cells.forEach((row, rowIndex) => row.forEach((cell, column) => {
      const x = (column - (row.length - 1) / 2) * gridPitch - gridSize / 2;
      const y = (rowIndex - (cells.length - 1) / 2) * gridPitch - gridSize / 2;
      X.rect(outer, x, y, gridSize, gridSize, colors[cell], 13,
        cell ? 'none' : X.P.lineStrong, cell ? 0 : 2.5);
    }));
  }

  function values(p, world, stage, center, color, motion = null) {
    if (world.type !== 'grid') {
      letters(p, world, stage, center, color, motion);
      return;
    }
    const progress = motion ? motion.progress : 1;
    const x = motion && motion.kind === 'travel' ? center - 565 * (1 - progress) : center;
    if (motion && motion.kind === 'rotate') {
      grid(p, world.values[0], x, 90 * progress);
    } else if (motion && motion.kind === 'mirror') {
      grid(p, world.values[1], x, 0, 1 - 2 * progress);
    } else if (motion && motion.kind === 'travel') {
      // Like the chips: the copy appears once it has lifted off its source.
      if (progress > .22) grid(X.place(p, { opacity: X.reveal(progress, .22, .13) }), world.values[stage], x);
    } else {
      grid(p, world.values[stage], x);
    }
  }

  function stage(p, world, local, index) {
    const first = index === 1;
    const start = first ? .43 : 1.75;
    const arrive = first ? 1.02 : 2.24;
    const finish = first ? 1.62 : 2.95;
    if (local < start) return;
    const center = centers[index];
    const source = first ? 0 : 1;
    if (local < arrive) {
      values(p, world, source, center, X.P.cyan,
        { kind: 'travel', progress: X.reveal(local, start, arrive - start) });
    } else if (local < finish) {
      const progress = X.reveal(local, arrive, finish - arrive);
      const kind = world.type === 'grid' ? (first ? 'rotate' : 'mirror')
        : world.type === 'str' && !first ? 'uppercase' : 'reorder';
      values(p, world, source, center, X.P.cyan,
        { kind, progress, rotate: world.type === 'perm' && first });
    } else {
      values(p, world, index, center, X.P.cyan);
    }
  }

  function worldFrame(p, world, local, opacity) {
    const layer = X.place(p, { opacity });
    const width = world.type === 'perm' ? 365 : world.type === 'str' ? 230 : 185;
    X.rect(layer, 960 - (width + 32) / 2, 361, width + 32, 68, X.P.panel, 34, X.P.cyan, 2.5);
    X.text(layer, world.title, 960, 395, { size: 44, color: X.P.cyan, weight: 700 });

    centers.forEach(center => X.card(layer, center - 260, cardTop, 520, 490));
    X.text(layer, 'INPUT', centers[0], 585,
      { size: 48, color: X.P.muted, weight: 700, spacing: 2 });
    [1, 2].forEach(index => {
      X.text(layer, world.symbols[index - 1], centers[index], 518,
        { size: 84, color: X.P.cyan, weight: 700,
          extra: { style: 'font-family:DejaVu Sans, sans-serif' } });
      X.text(layer, world.verbs[index - 1].toLowerCase(), centers[index], 585,
        { size: world.type === 'perm' && index === 2 ? 44 : 48,
          color: X.P.ink, weight: 650 });
    });
    values(layer, world, 0, centers[0], X.P.ink);
    stage(layer, world, local, 1);
    stage(layer, world, local, 2);
  }

  X.scenes.new_material = (p, u) => {
    X.heading(p, 9, 'Same structure, new material', X.P.cyan);
    X.text(p, 'One definition: apply f, then g', 960, 251,
      { size: 50, weight: 650, color: X.P.ink });
    ['a', 'f(a)', 'g(f(a))'].forEach((expression, index) =>
      X.text(p, expression, centers[index], 320,
        { size: 52, color: X.P.cyan, weight: 650 }));
    [0, 1].forEach(index => X.arrow(p, centers[index] + 260, 778,
      centers[index + 1] - 260, 778, { color: X.P.cyan, head: 12 }));
    X.D.new_material.worlds.forEach((world, index) => {
      const local = u - index * 3.55;
      const opacity = X.reveal(local, 0, .38) *
        (index === 2 ? 1 : 1 - X.reveal(local, 3.18, .37));
      if (opacity > .001) worldFrame(p, world, local, opacity);
    });
  };
})();
