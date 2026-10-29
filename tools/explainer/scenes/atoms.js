/* Six atoms, each shown as one formula assembling around its operator. */
(() => {
  'use strict';
  const X = window.OPX;
  const positions = [[130, 254], [690, 254], [1250, 254],
    [130, 596], [690, 596], [1250, 596]];

  X.scenes.atoms = (p, u) => {
    const { P } = X;
    X.heading(p, 2, 'Choose the atoms', P.atom);
    X.D.atoms.forEach((atom, index) => {
      const [x, y] = positions[index];
      const at = .35 + index * .78;
      const entry = X.reveal(u, at, .58, X.ease.out);
      if (!entry) return;
      const g = X.place(p, { opacity: entry, dy: 22 * (1 - entry) });
      X.card(g, x, y, 540, 320);
      X.text(g, atom.name, x + 270, y + 65, { size: 50, weight: 700 });
      X.text(g, atom.form.toUpperCase(), x + 270, y + 124,
        { size: 38, color: P.muted, weight: 650, spacing: 2 });

      const input = X.reveal(u, at + .38, .5, X.ease.out);
      const travel = X.reveal(u, at + .94, .65, X.ease.inOut);
      const output = X.reveal(u, at + 1.61, .65, X.ease.inOut);
      const result = X.reveal(u, at + 2.17, .24, X.ease.out);
      const cy = y + 226;
      const binary = atom.form === 'binary';
      const symbolX = x + (binary ? 190 : atom.form === 'postfix' ? 224 : 121);
      const operand = binary ? atom.example.split(' ')[0] : atom.form === 'postfix'
        ? atom.example.slice(0, -1) : atom.example.slice(1);
      const operandX = x + (binary ? 60 : atom.form === 'postfix' ? 78 : 267);
      const operandStart = operandX + (atom.form === 'prefix' ? 35 : -35);
      X.text(g, operand, X.lerp(operandStart, operandX, input), cy,
        { size: 55, mono: true, weight: 700, opacity: input });
      if (binary) {
        const right = atom.example.split(' ')[2];
        X.text(g, right, X.lerp(x + 365, x + 309, input), cy,
          { size: 55, mono: true, weight: 700, opacity: input });
      }
      X.node(g, symbolX, cy, atom.symbol, P.atom, { h: 116, w: 116, size: 76 });
      const pulse = X.window(u, at + 1.24, at + 1.92, .22, .36);
      if (pulse) X.rect(g, symbolX - 58, cy - 58, 116, 116, 'none', 22, P.cyan, 6,
        { opacity: pulse });
      if (travel > 0 && travel < 1) {
        const inputs = binary ? [[operand, operandX], [atom.example.split(' ')[2], x + 309]]
          : [[operand, operandX]];
        inputs.forEach(([value, start]) => X.token(g, value,
          X.lerp(start, symbolX + (start < symbolX ? -62 : 62), travel), cy + 45, P.cyan,
          { size: 40, opacity: Math.min(1, travel * 8, (1 - travel) * 8) }));
      }
      const equalX = x + 383;
      const valueX = x + 470;
      if (output > 0 && output < 1) X.token(g, atom.value,
        X.lerp(symbolX + 62, valueX, output), cy + 45, P.cyan,
        { size: 40, opacity: Math.min(1, output * 8, (1 - output) * 8) });
      X.text(g, '=', equalX, cy, { size: 55, mono: true, color: P.muted, opacity: result });
      X.text(g, atom.value, valueX, cy, { size: 55, mono: true, weight: 750,
        color: P.cyan, opacity: result });
    });
  };
})();
