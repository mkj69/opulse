# Programmatic homepage explainer

The video is drawn by code, not recorded. `explainer.html` loads `core.js` and one script per
scene from `scenes/`, in timeline order. The SVG stage is 1920 × 1080. `window.EXPLAINER`
exposes the timeline and `window.renderAt(t)` draws the exact frame at second `t`.
`?theme=light` and `?theme=dark` select the site's palettes. The drawn video contains English
text only; Chinese is in a separate VTT caption track. Title and end cards have on-screen copy
instead of captions.

- `core.js`: palette, easing and drawing helpers (cards, kind chips, nodes, arrows, value
  tokens, marked expressions, the logo and wordmark) and the frame dispatcher with cross-fades.
- `scenes/<id>.js`: each registers `OPX.scenes[id] = (group, secondsIntoScene, scene) => ...`.
- `data.py` → `data.json`: the timeline, captions and every value and step shown, computed by the
  Playground `Workspace` (the engine the site runs). `data_<key>.py` modules add scene data as
  `OPX.D.<key>`.
- `logo.svg` is the site logo (`docs/assets/images/logo.svg`), inlined once at load.
  `fonts/inter-latin.woff2` is Inter, the site font. `fonts/jetbrains-mono-latin-400.woff2`
  is the Latin variable JetBrains Mono (weights 100–800), used for expressions and code;
  its SIL OFL licence is in `fonts/JetBrainsMono-OFL.txt`. Frames start after both font
  families and the logo have loaded.

## Render

From the repository root, with Chrome/Chromium and ffmpeg installed:

```bash
PYTHONPATH=src python3 tools/explainer/data.py
python3 tools/explainer/render.py /path/to/chrome /tmp/opulse-explainer
```

The second command renders both themes at 30 fps. Frames go into
`/tmp/opulse-explainer/{light,dark}/frames`. It writes the homepage assets to
`docs/assets/video/`: `opulse-{light,dark}.{mp4,webm}`, `poster-{light,dark}.jpg`,
`captions.en.vtt`, and `captions.zh.vtt`. The poster is the fully revealed title card
(`POSTER` in `data.py`). The script serves this folder on a temporary localhost port and calls
`renderAt(t)` once for each frame over Chrome DevTools, then closes Chrome and the server.

Options:

```bash
python3 tools/explainer/render.py /path/to/chrome /tmp/opulse-explainer --fps 24 --themes dark
python3 tools/explainer/render.py /path/to/chrome /tmp/opulse-explainer --scenes substitution branch
python3 tools/explainer/render.py /path/to/chrome /tmp/opulse-explainer --sheet
python3 tools/explainer/render.py /path/to/chrome /tmp/opulse-explainer --at 2.5 17 40
```

`--scenes` encodes a preview in the output directory and leaves the homepage assets alone.
`--sheet` samples one frame per second into numbered 4 × 4 contact sheets. `--at` captures
single PNG frames (`<theme>/at-<T>.png`) for review. `--assets-dir` changes the full render's
destination. Keep 30 fps for the published homepage build.

## Verify without Chrome

```bash
PYTHONPATH=src python3 -m pytest -q tools/explainer
```

The tests regenerate all values through the interpreter, check the timeline, VTT timing, the
poster and the logo, scan every script for wall clock or random state, and run the whole
timeline in Node to look for overlapping text in both themes.
