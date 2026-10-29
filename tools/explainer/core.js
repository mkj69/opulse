/* Opulse explainer core: palette, drawing helpers and the frame dispatcher.
 *
 * Every visible property is a pure function of the requested time and frozen data.
 * Scenes live in scenes/<id>.js and register themselves as OPX.scenes[id] = (p, u, s) => {...},
 * where p is the scene's root group, u the seconds since the scene started and s its timeline
 * entry. Scenes must draw only through these helpers or plain SVG, never read the clock.
 */
(() => {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const W = 1920, H = 1080;
  const svg = document.getElementById('stage');
  const theme = new URLSearchParams(location.search).get('theme') === 'dark' ? 'dark' : 'light';
  const dark = theme === 'dark';
  // The site palette (docs/assets/css/custom.css, playground.css). Kind colours follow the
  // Playground: atom slate, simple cyan, branch amber, recursive magenta.
  const P = dark ? {
    bg:'#0a0f1e', bg2:'#0d1430', bgGlow:'#18265a', panel:'#111a33', panel2:'#16213f',
    ink:'#eef2ff', muted:'#aab6dc', faint:'#6b7aa6', line:'#2c3a5e', lineStrong:'#3d4d78',
    cyan:'#22d3ee', amber:'#fbbf24', magenta:'#e879f9', indigo:'#818cf8', red:'#f87171', green:'#4ade80',
    atom:'#94a3b8', grad:['#22d3ee','#818cf8','#e879f9'], gradText:['#22d3ee','#818cf8','#e879f9'],
    focusBg:'rgba(251,191,36,.24)', newBg:'rgba(34,211,238,.20)', shadow:'rgba(0,0,0,0)'
  } : {
    bg:'#f5f7fb', bg2:'#f8fafc', bgGlow:'#ffffff', panel:'#ffffff', panel2:'#f1f5f9',
    ink:'#0f172a', muted:'#475569', faint:'#94a3b8', line:'#e4e7ec', lineStrong:'#d0d5dd',
    cyan:'#0e7490', amber:'#b45309', magenta:'#a21caf', indigo:'#4f46e5', red:'#b91c1c', green:'#15803d',
    atom:'#475569', grad:['#06b6d4','#6366f1','#d946ef'], gradText:['#0e7490','#4f46e5','#a21caf'],
    focusBg:'rgba(180,83,9,.16)', newBg:'rgba(14,116,144,.14)', shadow:'rgba(15,23,42,.08)'
  };
  P.kind = { atom:P.atom, simple:P.cyan, branch:P.amber, recursive:P.magenta };
  const FONT = 'Inter, ui-sans-serif, system-ui, sans-serif';
  const MONO = '"JetBrains Mono", ui-monospace, monospace';

  // ------------------------------------------------------------------ timing
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const lerp = (a, b, k) => a + (b - a) * k;
  const ease = {
    linear: x => clamp(x),
    smooth: x => { x = clamp(x); return x * x * (3 - 2 * x); },
    inOut: x => { x = clamp(x); return x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; },
    out: x => { x = clamp(x); return 1 - Math.pow(1 - x, 3); },
    in: x => { x = clamp(x); return x * x * x; },
    back: x => { x = clamp(x); const c = 1.4; return 1 + (c + 1) * Math.pow(x - 1, 3) + c * Math.pow(x - 1, 2); },
  };
  // Progress 0..1 of a motion that starts at `at` and lasts `span` seconds.
  const reveal = (u, at, span = .55, fn = ease.inOut) => fn((u - at) / span);
  // 1 while inside [at, until], fading in over `fin` and out over `fout`.
  const window_ = (u, at, until, fin = .45, fout = .45) =>
    reveal(u, at, fin) * (1 - reveal(u, until - fout, fout));

  // ------------------------------------------------------------------ SVG
  function el(parent, tag, attrs = {}, content) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) n.setAttribute(k, String(v));
    if (content !== undefined) n.textContent = String(content);
    parent.appendChild(n); return n;
  }
  const group = (p, opacity = 1, extra = {}) => el(p, 'g', { opacity: +opacity.toFixed(4), ...extra });
  // A group moved by (dx, dy) and scaled by k around (cx, cy).
  const place = (p, { opacity = 1, dx = 0, dy = 0, k = 1, cx = 0, cy = 0 } = {}) =>
    group(p, opacity, { transform: `translate(${dx + cx * (1 - k)} ${dy + cy * (1 - k)}) scale(${k})` });
  const rect = (p, x, y, w, h, fill, rx = 0, stroke = 'none', sw = 0, extra = {}) =>
    el(p, 'rect', { x, y, width: w, height: h, rx, fill, stroke, 'stroke-width': sw, ...extra });
  const line = (p, x1, y1, x2, y2, color = P.line, sw = 3, opacity = 1) =>
    el(p, 'line', { x1, y1, x2, y2, stroke: color, 'stroke-width': sw, 'stroke-linecap': 'round', opacity });
  const path = (p, d, color = P.line, sw = 4, fill = 'none', opacity = 1, extra = {}) =>
    el(p, 'path', { d, fill, stroke: color, 'stroke-width': sw, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', opacity, ...extra });
  const circle = (p, x, y, r, fill, stroke = 'none', sw = 0, extra = {}) =>
    el(p, 'circle', { cx: x, cy: y, r, fill, stroke, 'stroke-width': sw, ...extra });
  // Text: centred on (x, y) by default. opts: size, color, anchor, weight, mono, opacity, spacing.
  function text(p, s, x, y, opts = {}) {
    const { size = 36, color = P.ink, anchor = 'middle', weight = 500, mono = false, opacity, spacing, extra = {} } = opts;
    const readableSize = Math.max(size, mono ? 34 : 30);
    return el(p, 'text', { x, y, fill: color, 'font-size': readableSize, 'font-weight': weight, 'text-anchor': anchor,
      'dominant-baseline': 'central', 'font-family': mono ? MONO : FONT, opacity,
      'letter-spacing': spacing, class: mono ? 'mono' : undefined, ...extra }, s);
  }
  // Rough advance width, for layout only (Inter ≈ .56 em, mono .60 em).
  const textWidth = (s, size, mono = false) => [...String(s)].length * Math.max(size, mono ? 34 : 30) * (mono ? .6 : .56);

  // Stroke a polyline/path progressively: returns the attrs for a dash-drawn stroke of length L.
  const drawn = (L, k) => ({ 'stroke-dasharray': `${L} ${L}`, 'stroke-dashoffset': L * (1 - clamp(k)) });
  // Point at fraction k along a quadratic Bézier from a to b with control c.
  const qpoint = (a, c, b, k) => [
    (1 - k) * (1 - k) * a[0] + 2 * (1 - k) * k * c[0] + k * k * b[0],
    (1 - k) * (1 - k) * a[1] + 2 * (1 - k) * k * c[1] + k * k * b[1]];

  // ------------------------------------------------------------------ brand
  // The real logo (logo.svg), inlined once into the persistent <defs> as #opx-logo.
  function logo(p, x, y, size = 150, opacity = 1, glow = true) {
    const g = group(p, opacity);
    if (glow) {
      if (dark) circle(g, x, y, size * .62, 'url(#opx-logo-glow)');
      else el(g, 'ellipse', { cx: x, cy: y + size * .12, rx: size * .5, ry: size * .5, fill: 'url(#opx-logo-shadow)' });
    }
    el(g, 'use', { href: '#opx-logo', x: x - size / 2, y: y - size / 2, width: size, height: size });
    return g;
  }
  // "Opulse" in Inter 800 with the brand text gradient, as on the title card.
  function wordmark(p, x, y, size = 112, opacity = 1) {
    return text(p, 'Opulse', x, y, { size, weight: 800, color: 'url(#opx-wordmark)', opacity,
      spacing: (-.02 * size).toFixed(2) });
  }
  // The short gradient rule under the wordmark; k draws it out from the centre.
  function brandRule(p, x, y, w = 140, k = 1, opacity = .8) {
    const half = w / 2 * clamp(k);
    if (half <= .5) return null;
    return rect(p, x - half, y - 1.5, half * 2, 3, 'url(#opx-rule)', 1.5, 'none', 0, { opacity });
  }
  // Full-frame soft radial background of the title card.
  const backdrop = p => rect(p, 0, 0, W, H, 'url(#opx-backdrop)');

  // ------------------------------------------------------------------ components
  // Playground card: rounded panel, hairline border, faint brand gradient along the top edge.
  function card(p, x, y, w, h, { accent = null, top = true, fill = P.panel, rx = 18, sw = 2 } = {}) {
    const g = group(p);
    if (!dark) rect(g, x, y + 6, w, h, P.shadow, rx);
    rect(g, x, y, w, h, fill, rx, accent || P.line, accent ? 3 : sw);
    if (top && !accent) rect(g, x + rx, y, w - 2 * rx, 3, 'url(#opx-rule)', 1.5, 'none', 0, { opacity: .55 });
    return g;
  }
  // Uppercase kind chip in the Playground's colours: kind is atom | simple | branch | recursive.
  function chip(p, label, x, y, kind = 'simple', size = 30, opacity = 1) {
    size = Math.max(size, 30);
    // Uppercase Inter 700 with 1.5 px tracking is about .72 em per letter.
    const n = [...label].length, c = P.kind[kind] || kind, w = n * (size * .72 + 1.5) + size * 1.4, h = size * 1.7;
    const g = group(p, opacity);
    rect(g, x - w / 2, y - h / 2, w, h, P.panel, h / 2, c, 2.5);
    text(g, label.toUpperCase(), x, y + 1, { size, color: c, weight: 700, spacing: 1.5 });
    return g;
  }
  // Operator / value node: rounded box with a mono label.
  function node(p, x, y, label, color = P.cyan, { w, h = 92, size = 46, fill = P.panel, opacity = 1, sw = 3.5 } = {}) {
    size = Math.max(size, 34);
    const width = w || Math.max(h, textWidth(label, size, true) + size * 1.1);
    const g = group(p, opacity);
    rect(g, x - width / 2, y - h / 2, width, h, fill, Math.min(22, h / 2), color, sw);
    text(g, label, x, y + 2, { size, color, weight: 700, mono: true });
    return g;
  }
  // Arrow from (x1,y1) to (x2,y2), optionally curved (bend px sideways), drawn up to fraction k.
  function arrow(p, x1, y1, x2, y2, { color = P.lineStrong, sw = 4, bend = 0, k = 1, opacity = 1, head = 14 } = {}) {
    if (k <= 0) return null;
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, len = Math.hypot(x2 - x1, y2 - y1) || 1;
    const c = [mx - (y2 - y1) / len * bend, my + (x2 - x1) / len * bend];
    const g = group(p, opacity);
    const steps = 24, pts = [];
    for (let i = 0; i <= steps * clamp(k); i++) pts.push(qpoint([x1, y1], c, [x2, y2], i / steps));
    const end = qpoint([x1, y1], c, [x2, y2], clamp(k)); pts.push(end);
    path(g, 'M ' + pts.map(q => q.map(v => v.toFixed(1)).join(' ')).join(' L '), color, sw);
    if (k > .94 && head) {
      const before = qpoint([x1, y1], c, [x2, y2], clamp(k) - .03), a = Math.atan2(end[1] - before[1], end[0] - before[0]);
      const length = head * reveal(k, .94, .06, ease.smooth);
      path(g, `M ${end[0] - length * Math.cos(a - .5)} ${end[1] - length * Math.sin(a - .5)} L ${end[0]} ${end[1]} ` +
        `L ${end[0] - length * Math.cos(a + .5)} ${end[1] - length * Math.sin(a + .5)}`, color, sw);
    }
    return { g, c };
  }
  // A value travelling along a (possibly curved) edge: a filled pill with its label.
  function token(p, label, x, y, color = P.cyan, { size = 34, opacity = 1 } = {}) {
    size = Math.max(size, 34);
    const w = Math.max(size * 1.6, textWidth(label, size, true) + size), h = size * 1.55;
    const g = group(p, opacity);
    rect(g, x - w / 2, y - h / 2, w, h, color, h / 2);
    text(g, label, x, y + 1, { size, color: dark ? P.bg : '#ffffff', weight: 700, mono: true });
    return g;
  }
  // An expression with one highlighted span [a, b) (Playground's focus / new marks).
  function expr(p, s, x, y, { size = 44, color = P.ink, anchor = 'middle', mark = null, markKind = 'focus', opacity = 1, weight = 600 } = {}) {
    size = Math.max(size, 34);
    const g = group(p, opacity), cw = size * .6, w = [...s].length * cw;
    const left = anchor === 'start' ? x : anchor === 'end' ? x - w : x - w / 2;
    if (mark && mark[1] > mark[0]) {
      const chars = [...s], a = chars.slice(0, mark[0]).length, b = chars.slice(0, mark[1]).length;
      const [bg, edge] = markKind === 'new' ? [P.newBg, P.cyan] : markKind === 'bad' ? ['rgba(239,68,68,.16)', P.red] : [P.focusBg, P.amber];
      rect(g, left + a * cw - 6, y - size * .72, (b - a) * cw + 12, size * 1.44, bg, 8);
      rect(g, left + a * cw - 6, y + size * .66, (b - a) * cw + 12, 3, edge, 1.5);
    }
    text(g, s, left, y, { size, color, anchor: 'start', weight, mono: true });
    return g;
  }

  // ------------------------------------------------------------------ frame furniture
  const sceneFurniture = Symbol('sceneFurniture');
  function heading(p, index, title, accent = P.cyan, total = 10) {
    const furniture = group(p);
    if (p[sceneFurniture]) p[sceneFurniture].push({ element: furniture, heading: true });
    text(furniture, String(index).padStart(2, '0') + ' / ' + String(total).padStart(2, '0'), 120, 96,
      { size: 30, color: accent, anchor: 'start', weight: 700, spacing: 2 });
    text(furniture, title, 120, 152, { size: 56, anchor: 'start', weight: 750 });
    rect(furniture, 120, 200, 64, 4, 'url(#opx-rule)', 2);
  }
  function footer(p, scene) {
    if (!scene.caption) return;
    const furniture = group(p);
    if (p[sceneFurniture]) p[sceneFurniture].push({ element: furniture, heading: false });
    text(furniture, scene.caption, W / 2, 990,
      { size: 42, weight: 550 });
  }

  // ------------------------------------------------------------------ defs
  // Persistent definitions live in a separate, zero-size <svg id="defs"> so renderAt can clear the stage.
  function buildDefs(logoText) {
    const host = document.getElementById('defs');
    if (!host) return;
    const defs = el(host, 'defs');
    const linear = (id, stops, attrs = {}) => {
      const g = el(defs, 'linearGradient', { id, ...attrs });
      stops.forEach((c, i) => el(g, 'stop', { offset: i / (stops.length - 1), 'stop-color': c }));
    };
    // Gradient angle 100deg as in the site's CSS; the wordmark spans about x 770..1150 at 112 px.
    linear('opx-wordmark', P.gradText, { gradientUnits: 'objectBoundingBox', x1: 0, y1: .4, x2: 1, y2: .6 });
    linear('opx-rule', P.grad, { x1: 0, y1: 0, x2: 1, y2: 0 });
    // CSS "radial-gradient(ellipse 70% 60% at 50% 38%)": radii 70% W and 60% H.
    const cy = H * .38, sy = (.6 * H) / (.7 * W);
    const bg = el(defs, 'radialGradient', { id: 'opx-backdrop', gradientUnits: 'userSpaceOnUse',
      cx: W / 2, cy, r: .7 * W, gradientTransform: `translate(0 ${cy * (1 - sy)}) scale(1 ${sy})` });
    const stops = dark ? [[0, P.bgGlow], [.48, P.bg2], [1, P.bg]] : [[0, '#ffffff'], [.7, '#f8fafc'], [1, '#eef2f8']];
    stops.forEach(([o, c]) => el(bg, 'stop', { offset: o, 'stop-color': c }));
    const glow = el(defs, 'radialGradient', { id: 'opx-logo-glow' });
    [[0, 'rgba(34,211,238,.30)'], [.55, 'rgba(34,211,238,.10)'], [1, 'rgba(34,211,238,0)']]
      .forEach(([o, c]) => el(glow, 'stop', { offset: o, 'stop-color': c }));
    const shadow = el(defs, 'radialGradient', { id: 'opx-logo-shadow' });
    [[0, 'rgba(15,23,42,.10)'], [.6, 'rgba(15,23,42,.04)'], [1, 'rgba(15,23,42,0)']]
      .forEach(([o, c]) => el(shadow, 'stop', { offset: o, 'stop-color': c }));
    if (logoText && typeof DOMParser !== 'undefined') {
      // Prefix the logo's own ids so they cannot clash with ours, then wrap it in a <symbol>.
      const src = logoText.replace(/id="([^"]+)"/g, 'id="lg-$1"').replace(/url\(#([^)]+)\)/g, 'url(#lg-$1)');
      const doc = new DOMParser().parseFromString(src, 'image/svg+xml').documentElement;
      const symbol = el(defs, 'symbol', { id: 'opx-logo', viewBox: doc.getAttribute('viewBox') });
      for (const child of [...doc.childNodes]) if (child.nodeName !== 'title') symbol.appendChild(document.importNode(child, true));
    }
  }

  // ------------------------------------------------------------------ dispatcher
  const OPX = window.OPX = {
    W, H, NS, theme, dark, P, FONT, MONO, D: null, scenes: {},
    clamp, lerp, ease, reveal, window: window_, el, group, place, rect, line, path, circle, text, textWidth,
    drawn, qpoint, logo, wordmark, brandRule, backdrop, card, chip, node, arrow, token, expr, heading, footer,
  };
  const FADE = .6;
  function drawScene(parent, index, u, textOpacity = 1, headingOpacity = textOpacity) {
    const s = OPX.D.scenes[index], draw = OPX.scenes[s.id];
    if (!draw) throw new Error(`No scene registered for ${s.id}`);
    parent[sceneFurniture] = [];
    draw(parent, u, s);
    footer(parent, s);
    if (textOpacity < 1 || headingOpacity < 1) {
      for (const furniture of parent[sceneFurniture])
        furniture.element.setAttribute('opacity', (furniture.heading ? headingOpacity : textOpacity).toFixed(4));
      const fadeText = node => {
        if (parent[sceneFurniture].some(furniture => furniture.element === node)) return;
        if (node.tagName === 'text' || node.tag === 'text') {
          const base = node.getAttribute?.('opacity') ?? node.attrs?.opacity ?? 1;
          const x = Number(node.getAttribute?.('x') ?? node.attrs?.x);
          const y = Number(node.getAttribute?.('y') ?? node.attrs?.y);
          const opacity = x === 120 && (y === 96 || y === 152) ? headingOpacity : textOpacity;
          node.setAttribute('opacity', (Number(base) * opacity).toFixed(4));
        }
        for (const child of node.children) fadeText(child);
      };
      fadeText(parent);
    }
  }
  function renderAt(t) {
    const D = OPX.D;
    if (!D) throw new Error('Explainer data is not loaded');
    if (!Number.isFinite(t)) throw new TypeError('t must be a finite number');
    t = clamp(t, 0, D.duration);
    svg.replaceChildren();
    backdrop(svg);
    let i = D.scenes.findIndex(s => t >= s.start && t < s.end);
    if (i < 0) i = D.scenes.length - 1;
    const s = D.scenes[i], u = t - s.start;
    // Complementary whole-scene fades keep the graphics visible at every instant.
    // Words exchange in separate windows so text from different scenes never collides.
    const a = i === 0 ? 1 : reveal(u, .2, FADE - .2, ease.smooth);
    if (i > 0 && u < FADE) {
      const prev = D.scenes[i - 1];
      drawScene(group(svg, 1 - a), i - 1, prev.end - prev.start - 1 / 60,
        1 - reveal(u, .25, .2, ease.smooth), 1 - reveal(u, .25, .15, ease.smooth));
    }
    drawScene(group(svg, a), i, u,
      i === 0 ? 1 : reveal(u, .45, .2, ease.smooth),
      i === 0 ? 1 : reveal(u, .4, .05, ease.smooth));
    return t;
  }
  window.renderAt = renderAt;
  const fontsReady = (document.fonts && document.fonts.load)
    ? Promise.all(['500 40px Inter', '600 40px Inter', '700 40px Inter', '800 40px Inter',
      '400 40px "JetBrains Mono"', '600 40px "JetBrains Mono"', '700 40px "JetBrains Mono"']
      .map(f => document.fonts.load(f))).then(() => document.fonts.ready) : Promise.resolve();
  const getText = (url, json) => fetch(url).then(r => { if (!r.ok) throw Error(`Cannot load ${url}`); return json ? r.json() : r.text(); });
  // Scene scripts are plain <script> tags after this one; they register before the data arrives.
  Promise.all([getText('data.json', true), getText('logo.svg', false), fontsReady]).then(([data, logoText]) => {
    buildDefs(logoText);
    OPX.D = data;
    renderAt(0);
    window.EXPLAINER = {duration:data.duration,scenes:data.scenes};
  }).catch(error => { document.body.dataset.error = error.message; throw error; });
})();
