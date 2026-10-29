/* Piano roll and local Web Audio playback for the pitch world. */
(() => {
  const names = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
  const tr = window.OpulseWorlds.tr;
  const noteName = p => names[p % 12] + (Math.floor(p / 12) - 1);
  const css = name => `var(--op-${name})`;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  let audio = null;
  let active = null;
  const stepFrames = new WeakMap();

  function stop() {
    if (!active) return;
    active.stopped = true;
    active.timers.forEach(clearTimeout);
    active.nodes.forEach(node => { try { node.stop(); } catch (_) {} });
    active.blocks.forEach(block => block.style.fill = css("cyan"));
    active.button.textContent = tr("▶ Play", "▶ 播放");
    active = null;
  }

  function play(notes, button, blocks) {
    if (active && active.button === button) { stop(); return; }
    stop();
    const Audio = window.AudioContext || window.webkitAudioContext;
    if (!Audio) { button.textContent = tr("Audio is unavailable", "无法播放音频"); return; }
    audio ||= new Audio();
    audio.resume();
    const state = {button, blocks, timers: [], nodes: [], stopped: false};
    active = state;
    button.textContent = tr("■ Stop", "■ 停止");
    let offset = 0;
    notes.forEach(({p, d}, i) => {
      const duration = Math.max(0.12, Number(d) * 0.32);
      const start = audio.currentTime + offset + 0.03;
      const oscillator = audio.createOscillator();
      const soft = audio.createOscillator();
      const gain = audio.createGain();
      oscillator.type = "triangle";
      soft.type = "sine";
      oscillator.frequency.value = 440 * 2 ** ((p - 69) / 12);
      soft.frequency.value = oscillator.frequency.value;
      oscillator.connect(gain);
      soft.connect(gain);
      gain.connect(audio.destination);
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(0.12, start + 0.025);
      gain.gain.exponentialRampToValueAtTime(0.045, start + Math.min(duration * 0.55, 0.25));
      gain.gain.exponentialRampToValueAtTime(0.001, start + duration);
      oscillator.start(start);
      soft.start(start);
      oscillator.stop(start + duration + 0.01);
      soft.stop(start + duration + 0.01);
      state.nodes.push(oscillator, soft);
      state.timers.push(setTimeout(() => {
        if (state.stopped) return;
        state.blocks.forEach(block => block.style.fill = css("cyan"));
        if (blocks[i]) blocks[i].style.fill = css("amber");
      }, offset * 1000));
      offset += duration;
    });
    state.timers.push(setTimeout(() => { if (active === state) stop(); }, (offset + 0.08) * 1000));
  }

  function notesOf(value) {
    if (!value) return null;
    if (value.t === "note") return [{p: value.v, d: 1}];
    if (value.t === "melody") return value.v;
    return null;
  }

  function valueText(value) {
    const notes = notesOf(value);
    if (!notes) return window.OpulseWorlds.valueText(value);
    return notes.length ? notes.map(n => noteName(n.p) + (n.d === 1 ? "" : ":" + n.d)).join(" ") : tr("Rest", "休止");
  }

  function element(tag, cls, text) {
    const out = document.createElement(tag);
    if (cls) out.className = cls;
    if (text !== undefined) out.textContent = text;
    return out;
  }

  function renderValue(el, value, ctx) {
    if (active && el.contains(active.button)) stop();
    el.replaceChildren();
    const notes = notesOf(value);
    if (!notes) {
      window.OpulseWorlds.fallbackValue(el, value);
      return;
    }
    const mini = Boolean(ctx && ctx.mini);
    const compact = Boolean(ctx && ctx.compact);
    const card = element("div", "op-pitch-card");
    card.style.cssText = `border:1px solid ${css("line")};background:${css("card")};color:${css("fg")};border-radius:14px;padding:${mini ? 5 : compact ? 8 : 12}px;max-width:100%;box-sizing:border-box;${mini ? "width:min(12rem, 100%)" : compact ? "width:min(13rem, 100%)" : "width:100%"}`;
    const head = element("div", "op-pitch-head");
    head.style.cssText = `display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:${mini ? 3 : 9}px`;
    const title = element("span", "op-pitch-names", notes.length ? notes.map(n => noteName(n.p)).join("  ") : tr("Rest", "休止"));
    title.style.cssText = `font-size:.9rem;font-weight:650;letter-spacing:.02em;color:${css("fg")};${mini ? "white-space:nowrap;overflow:hidden;text-overflow:ellipsis" : "overflow-wrap:anywhere"}`;
    head.append(title);
    let button = null;
    if (!mini) {
      button = element("button", "op-pitch-play", tr("▶ Play", "▶ 播放"));
      button.type = "button";
      button.disabled = !notes.length;
      button.setAttribute("aria-label", tr("Play ", "播放") + (notes.length ? notes.map(n => noteName(n.p)).join(", ") : tr("rest", "休止")));
      button.style.cssText = `flex:none;border:1px solid ${css("cyan")};background:${css("bg")};color:${css("fg")};border-radius:99px;padding:5px 11px;font:inherit;font-size:.8rem;cursor:pointer`;
      head.append(button);
    }
    card.append(head);
    if (notes.length) {
      const pitches = notes.map(n => n.p);
      const low = Math.max(0, Math.min(...pitches) - 2);
      const high = Math.min(127, Math.max(...pitches) + 2);
      const count = high - low + 1;
      const total = notes.reduce((sum, n) => sum + Math.max(0.25, Number(n.d)), 0);
      const width = mini ? 240 : compact ? 260 : 440, label = compact ? 0 : 38, plot = width - label - 12;
      const row = mini ? 28 / count : compact ? Math.max(5, Math.min(9, 60 / count)) : Math.max(11, Math.min(17, 156 / count));
      const height = mini ? 28 : count * row + 8;
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      if (mini) svg.setAttribute("preserveAspectRatio", "none");
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", tr("Piano roll: ", "钢琴卷帘图：") + notes.map(n => tr(
        `${noteName(n.p)} for ${n.d} beat${n.d === 1 ? "" : "s"}`, `${noteName(n.p)} 持续 ${n.d} 拍`)).join(tr(", ", "，")));
      svg.style.cssText = `display:block;width:100%;height:${mini ? "28px" : "auto"};border-radius:8px;overflow:hidden`;
      for (let p = low; p <= high; p++) {
        const y = (high - p) * row;
        const stripe = document.createElementNS(svg.namespaceURI, "rect");
        stripe.setAttribute("x", label);
        stripe.setAttribute("y", y);
        stripe.setAttribute("width", plot);
        stripe.setAttribute("height", row);
        stripe.style.fill = [1, 3, 6, 8, 10].includes(p % 12) ? css("bg") : css("card");
        svg.append(stripe);
        if (!compact && (p % 12 === 0 || pitches.includes(p))) {
          const text = document.createElementNS(svg.namespaceURI, "text");
          text.setAttribute("x", "2"); text.setAttribute("y", String(y + row - 2));
          text.style.cssText = `fill:${css("muted")};font:17px system-ui,sans-serif`;
          text.textContent = noteName(p);
          svg.append(text);
        }
      }
      const blocks = [];
      let beat = 0;
      notes.forEach(n => {
        const block = document.createElementNS(svg.namespaceURI, "rect");
        block.setAttribute("x", String(label + beat / total * plot + 1));
        block.setAttribute("y", String((high - n.p) * row + 1));
        block.setAttribute("width", String(Math.max(4, n.d / total * plot - 3)));
        block.setAttribute("height", String(Math.max(1, row - (mini ? 0.5 : 2))));
        block.setAttribute("rx", "3");
        block.style.fill = css("cyan");
        svg.append(block);
        blocks.push(block);
        beat += n.d;
      });
      if (button) button.addEventListener("click", event => { event.stopPropagation(); play(notes, button, blocks); });
      card.append(svg);
      if (compact || mini) { el.append(card); return; }
      const foot = element("div", "op-pitch-duration", tr(
        `${total} beat${total === 1 ? "" : "s"} · ${notes.length} note${notes.length === 1 ? "" : "s"}`,
        `${total} 拍 · ${notes.length} 个音符`));
      foot.style.cssText = `margin-top:7px;color:${css("muted")};font-size:.8rem`;
      card.append(foot);
    }
    el.append(card);
    if (reduced.matches) card.style.scrollBehavior = "auto";
  }

  function renderStep(el, step) {
    if (active && el.contains(active.button)) stop();
    cancelAnimationFrame(stepFrames.get(el));
    el.replaceChildren();
    const value = notesOf(step.sound) ? step.sound :
      notesOf(step.value) ? step.value : melodyIn(step.expression);
    const before = notesOf(step.previous);
    const after = notesOf(value);
    if (!after || !before || !after.length || !before.length) {
      if (value) renderValue(el, value);
      else window.OpulseWorlds.fallbackValue(el, step.value);
      return;
    }
    const card = element("div", "op-pitch-step");
    card.style.cssText = `box-sizing:border-box;width:100%;max-width:100%;border:1px solid ${css("line")};border-radius:14px;background:${css("card")};padding:9px;color:${css("fg")}`;
    const summary = element("div", "op-pitch-step-summary", `${before.map(n => noteName(n.p)).join("  ")}  →  ${after.map(n => noteName(n.p)).join("  ")}`);
    summary.style.cssText = `font:600 .8rem system-ui,sans-serif;overflow-wrap:anywhere;margin-bottom:5px;color:${css("fg")}`;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 260 170");
    svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", tr("Piano roll from ", "钢琴卷帘图：从 ") + summary.textContent);
    svg.style.cssText = "display:block;width:100%;height:155px;border-radius:8px;overflow:hidden";
    const pitches = [...new Set([...before, ...after].map(n => n.p))].sort((left, right) => right - left);
    const rowHeight = Math.min(28, 158 / pitches.length);
    const rowY = pitch => 5 + (160 - rowHeight * pitches.length) / 2 + pitches.indexOf(pitch) * rowHeight;
    for (const pitch of pitches) {
      const stripe = document.createElementNS(svg.namespaceURI, "rect");
      stripe.setAttribute("x", "37"); stripe.setAttribute("y", String(rowY(pitch)));
      stripe.setAttribute("width", "223"); stripe.setAttribute("height", String(rowHeight - 1));
      stripe.style.fill = [1, 3, 6, 8, 10].includes(pitch % 12) ? css("bg") : css("card");
      svg.append(stripe);
      const text = document.createElementNS(svg.namespaceURI, "text");
      text.setAttribute("x", "2"); text.setAttribute("y", String(rowY(pitch) + rowHeight * .73));
      text.setAttribute("font-size", String(Math.min(14, rowHeight * .8)));
      text.style.fill = css("muted");
      text.textContent = noteName(pitch);
      svg.append(text);
    }
    const positions = notes => {
      const total = notes.reduce((sum, note) => sum + Math.max(.25, Number(note.d)), 0);
      let beat = 0;
      return notes.map(note => {
        const pos = {x: 39 + beat / total * 217, y: rowY(note.p) + 1,
          width: Math.max(8, Number(note.d) / total * 217 - 3)};
        beat += Math.max(.25, Number(note.d));
        return pos;
      });
    };
    const oldPositions = positions(before), newPositions = positions(after);
    const blocks = newPositions.map((target, index) => {
      const block = document.createElementNS(svg.namespaceURI, "rect");
      block.setAttribute("rx", "3"); block.setAttribute("height", String(Math.max(5, rowHeight - 3)));
      block.style.fill = css("cyan");
      const title = document.createElementNS(svg.namespaceURI, "title");
      title.textContent = noteName(after[index].p);
      block.append(title); svg.append(block);
      return block;
    });
    card.append(summary, svg);
    el.append(card);
    const paint = progress => blocks.forEach((block, index) => {
      const end = newPositions[index], start = oldPositions[index] || end;
      block.setAttribute("x", String(start.x + (end.x - start.x) * progress));
      block.setAttribute("y", String(start.y + (end.y - start.y) * progress));
      block.setAttribute("width", String(start.width + (end.width - start.width) * progress));
      block.style.opacity = oldPositions[index] ? "1" : String(progress);
      block.style.fill = progress < .8 ? css("amber") : css("cyan");
    });
    if (reduced.matches) { paint(1); return; }
    paint(0);
    const begun = performance.now();
    const tick = now => {
      if (!el.contains(card)) return;
      const fraction = Math.min(1, (now - begun) / 780);
      paint(1 - (1 - fraction) ** 3);
      if (fraction < 1) stepFrames.set(el, requestAnimationFrame(tick));
    };
    stepFrames.set(el, requestAnimationFrame(tick));
  }

  function melodyIn(expression) {
    const match = expression?.match(/\[\[(?:\s*\d+\s*,\s*\d+\s*\]\s*,\s*\[)*\s*\d+\s*,\s*\d+\s*\]\]/);
    if (!match) return null;
    try {
      const pairs = JSON.parse(match[0]);
      return {t: "melody", v: pairs.map(([p, d]) => ({p, d}))};
    } catch (_) { return null; }
  }

  // Melody literals in expressions and notes read as note names, for example ⟨C4 E4 G4:2⟩.
  const NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];
  function shorten(text) {
    return String(text).replace(/\[\[\d+, \d+\](?:, \[\d+, \d+\])*\]/g, literal => {
      const pairs = JSON.parse(literal);
      return "⟨" + pairs.map(([p, d]) => NAMES[p % 12] + (Math.floor(p / 12) - 1) + (d === 1 ? "" : ":" + d)).join(" ") + "⟩";
    });
  }

  window.OpulseWorlds.register("pitch", {renderValue, renderStep, shorten, valueText});
})();
