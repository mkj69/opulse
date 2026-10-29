/* Action world value renderer. Three.js is loaded only when WebGL is available. */
const THREE_URL = 'https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js';
const ARC = {R: '#e53aa3', B: '#37a9e8', Y: '#f5cf4b', G: '#54c18a', P: '#9d77dc', O: '#ef8755'};
const DIRECTION = {N: '↑', E: '→', S: '↓', W: '←'};
const views = new WeakMap();
const stepAnimations = new WeakMap();
const tr = window.OpulseWorlds.tr;
let threePromise;

function sceneColours(el) {
  const styles = getComputedStyle(el);
  const probe = document.createElement('span');
  probe.style.display = 'none';
  el.append(probe);
  const swatch = document.createElement('canvas');
  swatch.width = swatch.height = 1;
  const context = swatch.getContext('2d', {willReadFrequently:true});
  const read = name => {
    if (!styles.getPropertyValue(name).trim()) return styles.color;
    probe.style.color = `var(${name})`;
    const value = getComputedStyle(probe).color;
    if (!context) return value;
    context.fillStyle = value;
    context.fillRect(0, 0, 1, 1);
    const [r, g, b] = context.getImageData(0, 0, 1, 1).data;
    return `rgb(${r}, ${g}, ${b})`;
  };
  const colours = {
    bg: read('--ow-scene-bg'), ground: read('--ow-scene-ground'),
    groundAlt: read('--ow-scene-ground-alt'), line: read('--ow-scene-line'),
    wall: read('--ow-scene-wall'), water: read('--ow-scene-water'),
    bench: read('--op-amber'), robot: read('--op-fg'), face: read('--op-bg')
  };
  probe.remove();
  return colours;
}
function darkScene() {
  const scheme = document.body.getAttribute('data-md-color-scheme');
  return scheme === 'slate' || (!scheme && matchMedia('(prefers-color-scheme: dark)').matches);
}
function reducedMotion() {
  return matchMedia('(prefers-reduced-motion: reduce)').matches;
}
function stateFrom(value) {
  return value && value.t === 'state' ? value.v : null;
}
function shortValue(value) {
  if (!value || value.t === 'nan') return '⊥';
  if (value.t === 'colour') return value.v;
  if (value.t === 'direction') return DIRECTION[value.v] || value.v;
  return String(value.v);
}
function injectStyle() {
  if (document.getElementById('op-action-style')) return;
  const style = document.createElement('style');
  style.id = 'op-action-style';
  style.textContent = `
    .op-action{display:block;width:100%;max-width:100%;min-width:0;box-sizing:border-box;padding:0;position:relative;overflow:hidden;border:1px solid var(--op-line);border-radius:14px;background:var(--op-card);color:var(--op-fg)}
    .op-action-canvas{display:block;width:100%;height:auto;aspect-ratio:4/3;touch-action:pan-y;cursor:grab}
    .op-action-canvas:active{cursor:grabbing}
    .op-action-caption{display:block;width:100%;box-sizing:border-box;padding:.4rem .75rem;font-size:.75rem;line-height:1.35;color:var(--op-muted);border-top:1px solid var(--op-line);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .op-action-caption strong{color:var(--op-fg)}
    .op-action-grid{display:grid;gap:2px;width:min(100%,430px);box-sizing:border-box;margin:.6rem auto;padding:.35rem;aspect-ratio:1;background:var(--ow-scene-grid);border-radius:8px}
    .op-action-cell{min-width:0;display:grid;place-items:center;position:relative;background:var(--ow-scene-cell);font-size:.8rem;line-height:1;border-radius:2px}
    .op-action-cell.alt{background:var(--ow-scene-cell-alt)}
    .op-action-grid.card{width:min(100%,200px);margin:0}
    .op-action-grid.small{width:120px;margin:0;gap:1px;padding:2px}
    .op-action-grid.small .op-action-cell{font-size:.8rem}
    .op-action-grid.small .height,.op-action-grid.card .height{display:none}
    .op-action-cell.water{background:var(--ow-scene-water);color:var(--ow-scene-mark)}
    .op-action-cell.wall{background:var(--ow-scene-wall);color:var(--ow-scene-mark)}
    .op-action-cell.bench{outline:2px solid var(--op-amber);outline-offset:-2px}
    .op-action-cell.bridge{background:var(--op-amber);color:var(--op-bg)}
    .op-action-cell.robot{box-shadow:inset 0 0 0 2px var(--op-fg)}
    .op-action-cell .height{position:absolute;right:2px;bottom:1px;font-size:.8rem}
  `;
  document.head.append(style);
}
function cellMap(state) {
  const map = new Map();
  (state.stacks || []).forEach(item => map.set(`${item.x},${item.y}`, item.blocks));
  return map;
}
function caption(state) {
  const held = state.robot.held;
  const item = held ? held.colour || held.name : tr('empty', '空');
  return tr(`Robot (${state.robot.x}, ${state.robot.y}) ${DIRECTION[state.robot.facing] || state.robot.facing} · hand: ${item}`,
    `机器人 (${state.robot.x}, ${state.robot.y}) ${DIRECTION[state.robot.facing] || state.robot.facing} · 手持：${item}`);
}
function fallback(el, state, showRobot = true) {
  const grid = document.createElement('div');
  grid.className = 'op-action-grid';
  grid.style.gridTemplateColumns = `repeat(${state.width},minmax(0,1fr))`;
  grid.setAttribute('role', 'img');
  grid.setAttribute('aria-label', tr('Block map from above. ', '俯视积木世界。') + caption(state));
  const stacks = cellMap(state);
  const tools = new Map((state.tools || []).map(item => [`${item.x},${item.y}`, item.name]));
  const bridges = new Set((state.bridges || []).map(([x,y]) => `${x},${y}`));
  for (let y = 0; y < state.height; y++) for (let x = 0; x < state.width; x++) {
    const key = `${x},${y}`;
    const tile = document.createElement('div');
    tile.className = 'op-action-cell';
    if ((x + y) % 2) tile.classList.add('alt');
    const terrain = state.terrain[y][x];
    if (terrain === '#') tile.classList.add('wall');
    if (terrain === '~') tile.classList.add(bridges.has(key) ? 'bridge' : 'water');
    if (terrain === 'B') tile.classList.add('bench');
    const stack = stacks.get(key) || [];
    if (stack.length) {
      tile.textContent = stack.at(-1);
      tile.style.color = ARC[stack.at(-1)] || 'var(--op-fg)';
      const height = document.createElement('span');
      height.className = 'height';
      height.textContent = stack.length;
      tile.append(height);
    } else if (tools.has(key)) tile.textContent = '⚒';
    else if (terrain === '#') tile.textContent = '■';
    else if (terrain === 'B') tile.textContent = '▣';
    else if (bridges.has(key)) tile.textContent = '═';
    if (showRobot && state.robot.x === x && state.robot.y === y) {
      tile.classList.add('robot');
      tile.textContent = DIRECTION[state.robot.facing] || '●';
    }
    grid.append(tile);
  }
  return grid;
}
function surface(el, state) {
  el.replaceChildren();
  el.classList.add('op-action');
  const canvas = document.createElement('canvas');
  canvas.className = 'op-action-canvas';
  canvas.setAttribute('aria-label', tr('Block map in 3D. ', '立体积木世界。') + caption(state));
  const note = document.createElement('div');
  note.className = 'op-action-caption';
  note.textContent = caption(state);
  el.append(canvas, note);
  return {el, canvas, note, state: null, angle: Math.PI / 4};
}
function disposeView(view) {
  if (view.raf) cancelAnimationFrame(view.raf);
  if (view.resize) view.resize.disconnect();
  if (view.themeObserver) view.themeObserver.disconnect();
  if (view.themeMedia) view.themeMedia.removeEventListener('change', view.onThemeChange);
  if (view.three) {
    const {world, mats, renderer} = view.three;
    world.traverse(object => {
      if (object.geometry) object.geometry.dispose();
      if (object.material && !Object.values(mats).includes(object.material)) object.material.dispose();
    });
    Object.values(mats).forEach(material => material.dispose());
    renderer.dispose();
  }
  if (views.get(view.el) === view) views.delete(view.el);
  view.three = null;
}
function roundedCube(THREE, size, height) {
  const r = .08, half = size / 2;
  const s = new THREE.Shape();
  s.moveTo(-half+r,-half); s.lineTo(half-r,-half);
  s.quadraticCurveTo(half,-half,half,-half+r); s.lineTo(half,half-r);
  s.quadraticCurveTo(half,half,half-r,half); s.lineTo(-half+r,half);
  s.quadraticCurveTo(-half,half,-half,half-r); s.lineTo(-half,-half+r);
  s.quadraticCurveTo(-half,-half,-half+r,-half);
  const g = new THREE.ExtrudeGeometry(s, {depth:height-.08, bevelEnabled:true,
    bevelThickness:.04, bevelSize:.04, bevelSegments:2, curveSegments:3});
  g.rotateX(-Math.PI/2);
  g.translate(0,-height/2,0);
  return g;
}
function fitCamera(THREE, camera, world, width, height) {
  world.updateMatrixWorld(true);
  camera.updateMatrixWorld(true);
  const corner = new THREE.Vector3();
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  world.traverse(object => {
    if (!object.geometry) return;
    if (!object.geometry.boundingBox) object.geometry.computeBoundingBox();
    const box = object.geometry.boundingBox;
    for (const x of [box.min.x, box.max.x])
      for (const y of [box.min.y, box.max.y])
        for (const z of [box.min.z, box.max.z]) {
          corner.set(x, y, z).applyMatrix4(object.matrixWorld).applyMatrix4(camera.matrixWorldInverse);
          minX = Math.min(minX, corner.x); maxX = Math.max(maxX, corner.x);
          minY = Math.min(minY, corner.y); maxY = Math.max(maxY, corner.y);
        }
  });
  const span = Math.max((maxY - minY) / .88, (maxX - minX) * height / (width * .88));
  const centerX = (minX + maxX) / 2, centerY = (minY + maxY) / 2;
  camera.left = centerX - span * width / height / 2;
  camera.right = centerX + span * width / height / 2;
  camera.top = centerY + span / 2;
  camera.bottom = centerY - span / 2;
  camera.updateProjectionMatrix();
}
async function makeThree(view, el) {
  try {
    if (!threePromise) threePromise = import(THREE_URL);
    const THREE = await threePromise;
    if (!el.isConnected || views.get(el) !== view) return;
    const renderer = new THREE.WebGLRenderer({canvas:view.canvas, antialias:true, alpha:true});
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-6,6,4.5,-4.5,.1,100);
    const world = new THREE.Group(); scene.add(world);
    const ambient = new THREE.AmbientLight(0xffffff, 2.1); scene.add(ambient);
    const sun = new THREE.DirectionalLight(0xffffff, 2.5);
    sun.position.set(-4, 12, 7); scene.add(sun);
    const mats = Object.fromEntries(Object.entries(ARC).map(([key,value]) =>
      [key, new THREE.MeshStandardMaterial({color:value, roughness:.68})]));
    view.three = {THREE, renderer, scene, camera, world, mats, ambient, sun};
    let dragging = false, lastX = 0;
    view.canvas.addEventListener('pointerdown', event => {
      dragging = true; lastX = event.clientX; view.canvas.setPointerCapture(event.pointerId);
    });
    view.canvas.addEventListener('pointerup', () => { dragging = false; });
    view.canvas.addEventListener('pointercancel', () => { dragging = false; });
    view.canvas.addEventListener('pointermove', event => {
      if (!dragging) return;
      view.angle += (event.clientX-lastX)*.008; lastX = event.clientX;
      draw(view, view.state);
    });
    view.resize = new ResizeObserver(() => draw(view, view.state));
    view.resize.observe(el);
    view.onThemeChange = () => {
      if (view.canvas.isConnected) draw(view, view.state);
      else disposeView(view);
    };
    view.themeObserver = new MutationObserver(view.onThemeChange);
    view.themeObserver.observe(document.body, {attributes:true, attributeFilter:['data-md-color-scheme']});
    view.themeMedia = matchMedia('(prefers-color-scheme: dark)');
    view.themeMedia.addEventListener('change', view.onThemeChange);
    draw(view, view.state);
  } catch (_) {
    if (views.get(el) !== view) return;
    disposeView(view);
    view.fallback = true;
    view.canvas.replaceWith(fallback(el, view.state));
    views.set(el, view);
  }
}
function draw(view, state, previous = null) {
  if (!state || !view.three) return;
  const {THREE, renderer, scene, camera, world, mats, ambient, sun} = view.three;
  while (world.children.length) {
    const object = world.children[0]; world.remove(object);
    object.traverse(child => { if (child.geometry) child.geometry.dispose();
      if (child.material && !Object.values(mats).includes(child.material)) child.material.dispose(); });
  }
  const width = Math.max(1, view.el.clientWidth);
  const height = width * 3 / 4;
  renderer.setSize(width, height, false);
  camera.position.set(Math.cos(view.angle)*13, 13, Math.sin(view.angle)*13);
  camera.lookAt(0, 0, 0);
  const palette = sceneColours(view.el);
  renderer.setClearColor(palette.bg, 1);
  scene.background = new THREE.Color(palette.bg);
  const dark = darkScene();
  ambient.intensity = dark ? 1.4 : 2.1;
  sun.intensity = dark ? 2.2 : 2.5;
  const tileMaterial = new THREE.MeshStandardMaterial({color:palette.ground,roughness:1});
  const altMaterial = new THREE.MeshStandardMaterial({color:palette.groundAlt,roughness:1});
  const wallMaterial = new THREE.MeshStandardMaterial({color:palette.wall,roughness:1});
  const waterMaterial = new THREE.MeshStandardMaterial({color:palette.water,transparent:true,opacity:.72,roughness:.28});
  const benchMaterial = new THREE.MeshStandardMaterial({color:palette.bench,roughness:.8});
  const robotMaterial = new THREE.MeshStandardMaterial({color:palette.robot,roughness:.75});
  const darkMaterial = new THREE.MeshStandardMaterial({color:palette.face});
  if (dark) {
    const grid = new THREE.Mesh(new THREE.PlaneGeometry(state.width, state.height),
      new THREE.MeshBasicMaterial({color:palette.line}));
    grid.rotation.x = -Math.PI / 2;
    grid.position.y = -.2;
    world.add(grid);
  }
  const stacks = cellMap(state), oldStacks = previous ? cellMap(previous) : new Map();
  const bridges = new Set((state.bridges || []).map(([x,y]) => `${x},${y}`));
  for (let y=0; y<state.height; y++) for (let x=0; x<state.width; x++) {
    const key=`${x},${y}`, kind=state.terrain[y][x], bridge=bridges.has(key);
    const tile = new THREE.Mesh(new THREE.BoxGeometry(.94,.13,.94),
      kind==='#' ? wallMaterial : kind==='~' && !bridge ? waterMaterial : (x+y)%2 ? altMaterial : tileMaterial);
    tile.position.set(x-(state.width-1)/2,-.13,y-(state.height-1)/2);
    world.add(tile);
    if (kind==='#') {
      const wall=new THREE.Mesh(roundedCube(THREE,.9,.9),wallMaterial);
      wall.position.set(tile.position.x,.39,tile.position.z); world.add(wall);
    }
    if (kind==='B') {
      const bench=new THREE.Mesh(roundedCube(THREE,.8,.12),benchMaterial);
      bench.position.set(tile.position.x,.12,tile.position.z); world.add(bench);
    }
    if (bridge) {
      const plank=new THREE.Mesh(roundedCube(THREE,.88,.13),benchMaterial);
      plank.position.set(tile.position.x,.1,tile.position.z); world.add(plank);
    }
    (stacks.get(key)||[]).forEach((c,i) => {
      const block = new THREE.Mesh(roundedCube(THREE,.62,.45),mats[c]);
      const finalY=.28+i*.47;
      block.position.set(tile.position.x,finalY,tile.position.z);
      world.add(block);
      if (previous && i >= (oldStacks.get(key)||[]).length && !reducedMotion()) {
        block.position.y += .9;
        animate(block.position, 'y', finalY, 320);
      }
    });
  }
  const robot = new THREE.Group();
  const torso = new THREE.Mesh(new THREE.CylinderGeometry(.25,.31,.54,12),robotMaterial);
  torso.position.y=.42; robot.add(torso);
  const head = new THREE.Mesh(new THREE.SphereGeometry(.25,16,12),robotMaterial);
  head.position.y=.88; robot.add(head);
  const face = new THREE.Mesh(new THREE.SphereGeometry(.045,8,8),darkMaterial);
  face.position.set(0,.91,-.235); robot.add(face);
  const arrow = new THREE.Mesh(new THREE.ConeGeometry(.11,.25,6),benchMaterial);
  arrow.position.set(0,.65,-.33); arrow.rotation.x=Math.PI/2; robot.add(arrow);
  const held = state.robot.held;
  if (held) {
    const object = new THREE.Mesh(roundedCube(THREE,.28,.28),
      held.kind === 'block' ? mats[held.colour] : benchMaterial);
    object.position.set(.34,.59,-.12); robot.add(object);
    if (previous && !previous.robot.held && !reducedMotion()) {
      object.position.y = .1;
      animate(object.position,'y',.59,320);
    }
  }
  const facingAngle={N:0,E:-Math.PI/2,S:Math.PI,W:Math.PI/2};
  robot.rotation.y=facingAngle[state.robot.facing] || 0;
  robot.position.set(state.robot.x-(state.width-1)/2,0,state.robot.y-(state.height-1)/2);
  world.add(robot);
  if (previous && !reducedMotion()) {
    const fromX=previous.robot.x-(state.width-1)/2;
    const fromZ=previous.robot.y-(state.height-1)/2;
    const toX=robot.position.x, toZ=robot.position.z;
    if (fromX!==toX || fromZ!==toZ) {
      robot.position.x=fromX; robot.position.z=fromZ;
      animate(robot.position,'x',toX,320); animate(robot.position,'z',toZ,320);
    }
    const fromA=facingAngle[previous.robot.facing] || 0;
    if (fromA!==robot.rotation.y) {
      const toA=robot.rotation.y; robot.rotation.y=fromA;
      animate(robot.rotation,'y',toA,320);
    }
  }
  fitCamera(THREE, camera, world, width, height);
  function frame() {
    if (!view.canvas.isConnected) { disposeView(view); return; }
    renderer.render(scene,camera);
    view.raf=requestAnimationFrame(frame);
  }
  if (view.raf) cancelAnimationFrame(view.raf);
  frame();
}
function animate(object, key, target, duration) {
  const start=object[key], begun=performance.now();
  function tick(now) {
    const t=Math.min(1,(now-begun)/duration);
    object[key]=start+(target-start)*(t*t*(3-2*t));
    if (t<1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
function renderValue(el,value,ctx) {
  injectStyle();
  const state=stateFrom(value);
  // Cards and atom panels draw the flat map; only the derivation player opens a WebGL scene.
  if (state && !(ctx && ctx.scene)) {
    const old = views.get(el);
    if (old) disposeView(old);
    const grid=fallback(el,state);
    grid.classList.add(ctx && ctx.compact ? 'small' : 'card');
    el.replaceChildren(grid);
    return;
  }
  if (!state) {
    const old=views.get(el);
    if (old) disposeView(old);
    el.replaceChildren(); window.OpulseWorlds.fallbackValue(el,value); return;
  }
  let view=views.get(el);
  if (!view) { view=surface(el,state); views.set(el,view); }
  const previous=view.state;
  view.state=state;
  view.note.textContent=caption(state);
  if (view.fallback) { el.replaceChildren(fallback(el,state),view.note); return; }
  const available=!!(view.canvas.getContext('webgl2') || view.canvas.getContext('webgl'));
  if (!available) { view.fallback=true; el.replaceChildren(fallback(el,state),view.note); return; }
  if (view.three) draw(view,state,previous);
  else if (!view.loading) { view.loading=true; makeThree(view,el); }
}
function renderStep(el,step,ctx) {
  (stepAnimations.get(el) || []).forEach(animation => animation.cancel());
  stepAnimations.delete(el);
  const state=stateFrom(step.value) || stateFrom(step.state) || stateFrom(ctx && ctx.currentValue);
  if (!state) {
    const old = views.get(el);
    if (old) disposeView(old);
    el.replaceChildren(); el.textContent=shortValue(step.value);
    return;
  }
  injectStyle();
  el.style.display = 'grid';
  el.style.justifyItems = 'center';
  const old = views.get(el);
  if (old) disposeView(old);
  const previous = stateFrom(step.previous);
  const grid = fallback(el, state, false);
  grid.classList.add('op-action-step-grid');
  grid.style.cssText += ';position:relative;width:min(100%,320px);margin:.3rem auto;';
  const cellAt = (x, y) => grid.children[y * state.width + x];
  const center = (x, y) => {
    const cell = cellAt(x, y);
    if (!cell) return null;
    const rect = cell.getBoundingClientRect(), frame = grid.getBoundingClientRect();
    return {x:rect.left - frame.left + rect.width / 2, y:rect.top - frame.top + rect.height / 2};
  };
  el.replaceChildren(grid);
  const end = center(state.robot.x, state.robot.y);
  if (!end) return;
  const start = previous && previous.width === state.width && previous.height === state.height &&
    center(previous.robot.x, previous.robot.y) || end;
  const moving = start.x !== end.x || start.y !== end.y;
  const angles = {N:0,E:90,S:180,W:270};
  const from = angles[previous?.robot.facing] ?? angles[state.robot.facing] ?? 0;
  let turn = (angles[state.robot.facing] ?? 0) - from;
  if (turn > 180) turn -= 360;
  if (turn < -180) turn += 360;
  const trail = document.createElement('div');
  trail.setAttribute('aria-hidden','true');
  trail.style.cssText = `position:absolute;left:${Math.min(start.x,end.x)}px;top:${Math.min(start.y,end.y)}px;width:${Math.max(2,Math.abs(end.x-start.x))}px;height:${Math.max(2,Math.abs(end.y-start.y))}px;border-top:${start.y === end.y ? '3px' : '0'} solid var(--op-amber);border-left:${start.x === end.x ? '3px' : '0'} solid var(--op-amber);pointer-events:none;`;
  if (moving) grid.append(trail);
  const robot = document.createElement('div');
  robot.textContent = '↑';
  robot.setAttribute('role','img');
  robot.setAttribute('aria-label',caption(state));
  robot.style.cssText = `position:absolute;left:50%;top:50%;width:1.65rem;height:1.65rem;display:grid;place-items:center;border-radius:50%;border:2px solid var(--op-cyan);background:var(--op-card);color:var(--op-fg);font:700 1.3rem system-ui,sans-serif;box-shadow:0 2px 8px #0004;transform:translate(-50%,-50%) rotate(${from + turn}deg);z-index:2;pointer-events:none`;
  cellAt(state.robot.x, state.robot.y).append(robot);
  const ghost = document.createElement('div');
  if (previous && (moving || turn)) {
    ghost.textContent = DIRECTION[previous.robot.facing] || '●';
    ghost.setAttribute('aria-hidden','true');
    ghost.style.cssText = `position:absolute;left:${turn && !moving ? '10%' : '50%'};top:${turn && !moving ? '12%' : '50%'};width:1.25rem;height:1.25rem;display:grid;place-items:center;border-radius:50%;border:2px dashed var(--op-amber);background:var(--op-card);color:var(--op-amber);font:700 1rem system-ui,sans-serif;transform:translate(-50%,-50%);pointer-events:none;z-index:3`;
    cellAt(previous.robot.x, previous.robot.y).append(ghost);
  }
  if (turn) {
    const heading = document.createElement('span');
    heading.setAttribute('aria-label', tr('Turn from ', '转向：') + DIRECTION[previous.robot.facing] + ' → ' + DIRECTION[state.robot.facing]);
    heading.textContent = `${DIRECTION[previous.robot.facing]}  →  ${DIRECTION[state.robot.facing]}`;
    heading.style.cssText = 'position:absolute;right:5px;top:5px;padding:3px 7px;border:1px solid var(--op-amber);border-radius:12px;background:var(--op-card);color:var(--op-amber);font:700 .8rem system-ui,sans-serif;z-index:3';
    grid.append(heading);
  }
  const note = document.createElement('div');
  note.className = 'op-action-caption';
  note.style.cssText = 'white-space:normal;overflow:visible;text-overflow:clip';
  note.textContent = previous && moving ?
    tr(`Robot (${previous.robot.x}, ${previous.robot.y}) → (${state.robot.x}, ${state.robot.y}) · ${DIRECTION[state.robot.facing]} · hand: ${state.robot.held?.colour || state.robot.held?.name || 'empty'}`,
      `机器人 (${previous.robot.x}, ${previous.robot.y}) → (${state.robot.x}, ${state.robot.y}) · ${DIRECTION[state.robot.facing]} · 手持：${state.robot.held?.colour || state.robot.held?.name || '空'}`) : caption(state);
  el.append(note);
  if (reducedMotion() || !previous) { ghost.remove(); return; }
  const animations = [];
  if (moving) {
    animations.push(robot.animate([
      {transform:`translate(-50%,-50%) translate(${start.x - end.x}px,${start.y - end.y}px) rotate(${from}deg)`},
      {transform:`translate(-50%,-50%) rotate(${from + turn}deg)`}
    ], {duration:800,easing:'cubic-bezier(.2,.8,.2,1)'}));
    animations.push(trail.animate([{opacity:0,transform:'scale(.2)'},{opacity:1,transform:'scale(1)'}],
      {duration:800,easing:'cubic-bezier(.2,.8,.2,1)'}));
  } else if (turn) animations.push(robot.animate([
    {transform:`translate(-50%,-50%) rotate(${from}deg)`,borderColor:'var(--op-amber)'},
    {transform:`translate(-50%,-50%) rotate(${from + turn}deg)`,borderColor:'var(--op-cyan)'}
  ], {duration:780,easing:'cubic-bezier(.2,.8,.2,1)'}));
  if (ghost.isConnected) {
    const fade = ghost.animate([{opacity:.95},{opacity:.65,offset:.6},{opacity:0}],
      {duration:780,easing:'ease-out'});
    fade.onfinish = () => ghost.remove();
    animations.push(fade);
  }
  stepAnimations.set(el,animations);
}
window.OpulseWorlds?.register('action',{renderValue,renderStep,persistent:true});
