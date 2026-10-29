/* Scene 6: definitions grow from atoms, then the graph becomes a generated field. */
(() => {
  'use strict';
  const X = window.OPX, P = X.P;
  const nodes = [
    {symbol:'+', kind:'atom', x:405, y:850, at:0},
    {symbol:'*', kind:'atom', x:610, y:850, at:0},
    {symbol:'-', kind:'atom', x:815, y:850, at:0},
    {symbol:'%', kind:'atom', x:1020, y:850, at:0},
    {symbol:'@', kind:'atom', x:1225, y:850, at:0},
    {symbol:'&', kind:'atom', x:1430, y:850, at:0},
    {symbol:'◆', kind:'simple', x:560, y:717, at:.45, calls:['+','*']},
    {symbol:'▲', kind:'branch', x:940, y:717, at:.85, calls:['-']},
    {symbol:'★', kind:'recursive', x:1320, y:717, at:1.25, calls:['*','-']},
    {symbol:'◇', kind:'simple', x:675, y:585, at:2.25, calls:['▲','★']},
    {symbol:'✦', kind:'simple', x:1205, y:585, at:4, calls:['▲','★']},
    {symbol:'⬡', kind:'simple', x:940, y:465, at:5.75, calls:['◆','◇','-']},
  ];
  const lookup = Object.fromEntries(nodes.map(node => [node.symbol, node]));
  const incoming = Object.fromEntries(nodes.map(node => [node.symbol,
    nodes.filter(caller => caller.calls?.includes(node.symbol)).sort((left, right) => left.x - right.x)]));
  const cardTimes = [2.25, 4, 5.75];

  function graph(p, u) {
    const rise = -245 * (1 - X.reveal(u, 0, 1.9));
    const shrink = X.reveal(u, 7.15, 1.05);
    const fade = 1 - X.reveal(u, 7.4, .7);
    if (fade <= .001) return;
    const g = X.place(p, {opacity:fade, k:1 - .25 * shrink, cx:960, cy:650,
      dy:rise + 95 * shrink});
    const opening = X.window(u, 0, 2.2, .45, .45);
    if (opening > .001) {
      const lead = X.place(p, {opacity:opening, dy:14 * (1 - X.reveal(u, 0, .45))});
      X.text(lead, 'ATOMS BECOME NEW OPERATORS', 960, 342,
        {size:44, color:P.indigo, weight:750, spacing:1});
    }
    for (const [label, y, at] of [['ATOMS',850,0],['LAYER 1',717,.45],
                                  ['LAYER 2',585,2.25],['LAYER 3',465,5.75]]) {
      const opacity = X.reveal(u, at, .45) * (1 - X.reveal(u, 7.48, .28));
      if (opacity > .001) X.text(g, label, 150, y,
        {size:36, color:P.muted, weight:750, anchor:'start', opacity, spacing:1.5});
    }
    const clears = (x1, y1, x2, y2, bend, from, to) => {
      const length = Math.hypot(x2 - x1, y2 - y1) || 1;
      const control = [(x1 + x2) / 2 - (y2 - y1) / length * bend,
        (y1 + y2) / 2 + (x2 - x1) / length * bend];
      for (let step = 1; step < 20; step++) {
        const [x, y] = X.qpoint([x1, y1], control, [x2, y2], step / 20);
        if (nodes.some(node => node !== from && node !== to &&
          Math.abs(x - node.x) < 79 && Math.abs(y - node.y) < 57)) return false;
      }
      return true;
    };
    for (const node of nodes) {
      if (!node.calls) continue;
      const progress = X.reveal(u, node.at + .2, .7);
      for (let index = 0; index < node.calls.length; index++) {
        const lower = lookup[node.calls[index]];
        const x1 = node.x + (index - (node.calls.length - 1) / 2) * 25;
        const callers = incoming[lower.symbol];
        const port = callers.indexOf(node) - (callers.length - 1) / 2;
        const y1 = node.y + 50, x2 = lower.x + port * 32;
        const y2 = lower.y - 52;
        const fan = (index - (node.calls.length - 1) / 2) * 30;
        const bend = [0, 75, -75, 150, -150, 230, -230].map(extra => fan + extra)
          .find(candidate => clears(x1, y1, x2, y2, candidate, node, lower)) ?? fan;
        const route = X.arrow(g, x1, y1, x2, y2,
          {color:P.kind[node.kind], bend, k:progress,
           opacity:.7 * X.reveal(u, node.at + .34, .35), sw:3.8, head:0});
        if (route && progress > .3 && progress < .99 && shrink < .6) {
          const point = X.qpoint([x1, y1], route.c, [x2, y2], progress);
          X.circle(g, point[0], point[1], 9, P.kind[node.kind], 'none', 0,
            {opacity:X.reveal(u, node.at + .34, .35)});
        }
      }
    }
    for (const node of nodes) {
      const visible = node.kind === 'atom' ? 1 : X.reveal(u, node.at, .55);
      if (visible < .001) continue;
      const focus = cardTimes.findIndex((at, index) =>
        node.symbol === X.D.layers.examples[index].symbol && u >= at && u < at + 1.45);
      const pulse = focus < 0 ? 0 : Math.sin(Math.PI * X.clamp((u - cardTimes[focus]) / 1.45)) ** 2;
      const holder = X.place(g, {opacity:visible, dy:(1 - visible) * 26,
        k:1 + .08 * pulse, cx:node.x, cy:node.y});
      X.node(holder, node.x, node.y, node.symbol, P.kind[node.kind],
        {w:node.kind === 'atom' ? 124 : 138, h:102, size:58,
         fill:pulse > .05 ? P.panel2 : P.panel, sw:3.5 + 2 * pulse});
    }
    X.D.layers.examples.forEach((item, index) => {
      const at = cardTimes[index];
      const opacity = X.window(u, at, at + 1.65, .3, .3) * (1 - shrink);
      if (opacity < .001) return;
      const card = X.place(p, {opacity, dy:(1 - X.reveal(u, at, .32)) * 22});
      X.card(card, 250, 218, 1420, 152);
      X.chip(card, item.kind, 400, 263, item.kind, 36);
      X.text(card, item.definition, 1110, 263, {mono:true, size:38, weight:650});
      X.text(card, item.name, 435, 330,
        {size:40, color:P.kind[item.kind], weight:720, anchor:'start'});
      X.text(card, `${item.expression} = ${item.value}`, 1595, 330,
        {mono:true, size:40, weight:700, color:P.cyan, anchor:'end'});
    });
  }

  function field(p, u) {
    const visible = X.reveal(u, 7.65, .85);
    if (visible < .001) return;
    const [small, large] = X.D.layers.sets;
    const growth = X.reveal(u, 10.15, 1.5);
    const g = X.place(p, {opacity:visible, k:1.075 - .075 * growth,
      cx:960, cy:570, dy:(1 - visible) * 40});
    X.text(g, 'GENERATED OPERATORS', 250, 246,
      {size:32, color:P.muted, anchor:'start', weight:750, spacing:1});
    X.text(g, 'L1 = BASE LAYER', 920, 246,
      {size:30, color:P.muted, anchor:'start', weight:700});
    X.card(g, 225, 277, 1470, 580);
    const oldOpacity = 1 - X.reveal(u, 10.22, .5);
    const newOpacity = X.reveal(u, 10.95, .48);
    const header = X.group(g, oldOpacity);
    X.text(header, small.total.toLocaleString('en-US'), 1665, 239,
      {size:62, color:P.indigo, anchor:'end', weight:800, mono:true});
    const nextHeader = X.group(g, newOpacity);
    X.text(nextHeader, large.total.toLocaleString('en-US'), 1665, 239,
      {size:62, color:P.indigo, anchor:'end', weight:800, mono:true});
    const kinds = ['simple','branch','recursive'];
    for (let row = 0; row < large.layers.length; row++) {
      const start = small.layers[row] || {count:0, kinds:{simple:0,branch:0,recursive:0}};
      const end = large.layers[row];
      const arrive = row < small.layers.length ? X.reveal(u, 7.5 + row * .07, .5) :
        X.reveal(u, 10.65 + (row - small.layers.length) * .33, .7);
      if (arrive < .001) continue;
      const y = 819 - row * X.lerp(50, 42, growth);
      const lane = X.place(g, {opacity:arrive});
      const maximum = X.lerp(200, 1000, growth);
      const count = X.lerp(start.count, end.count, growth);
      const width = 1040 * count / maximum;
      X.text(lane, `L${end.layer + 1}`, 262, y,
        {size:33, color:P.muted, anchor:'start', weight:750});
      X.rect(lane, 390, y - 10, 1040, 20, P.panel2, 10);
      let left = 390;
      kinds.forEach((kind, index) => {
        const kindCount = X.lerp(start.kinds[kind], end.kinds[kind], growth);
        const part = count ? width * kindCount / count : 0;
        if (part > .1) X.rect(lane, left, y - 10, part, 20, P.kind[kind],
          index === 0 ? 9 : 0);
        left += part;
      });
      if (row < small.layers.length) {
        X.text(X.group(lane, oldOpacity), start.count.toLocaleString('en-US'), 1645, y,
          {size:34, color:P.ink, anchor:'end', weight:700, mono:true});
      }
      X.text(X.group(lane, newOpacity), end.count.toLocaleString('en-US'), 1645, y,
        {size:34, color:P.ink, anchor:'end', weight:700, mono:true});
    }
    [[small, oldOpacity], [large, newOpacity]].forEach(([set, opacity]) => {
      const legend = X.group(g, opacity);
      kinds.forEach((kind, index) => {
        const x = 317 + index * 505;
        X.circle(legend, x, 902, 10, P.kind[kind]);
        X.text(legend, `${kind.toUpperCase()}  ${set.kinds[kind].toLocaleString('en-US')}`,
          x + 26, 902, {size:32, color:P.kind[kind], anchor:'start', weight:700});
      });
    });
  }

  X.scenes.layers = (p, u) => {
    X.text(p, '06 / 10', 120, 96,
      {size:30, color:P.indigo, anchor:'start', weight:700, spacing:2});
    X.text(p, 'Layers of concepts', 120, 152,
      {size:56, anchor:'start', weight:750});
    X.rect(p, 120, 200, 64, 4, 'url(#opx-rule)', 2);
    graph(p, u);
    field(p, u);
  };
})();
