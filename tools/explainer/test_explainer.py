"""No-browser checks for the deterministic explainer source and output metadata."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
from data import build_data
from render import frame_times, poster_time, timestamp, write_vtt

SCRIPTS = re.findall(r'<script src="([^"]+)"', (HERE / "explainer.html").read_text())


class ExplainerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))

    def test_interpreter_data_and_examples(self):
        self.assertEqual(self.data, build_data())
        self.assertEqual([a["value"] for a in self.data["atoms"]], ["7", "5", "42", "2", "21", "11"])
        self.assertEqual(self.data["substitution"]["value"], "25")
        self.assertEqual([b["value"] for b in self.data["branch"]], ["4", "4"])
        self.assertEqual(self.data["recursion"]["fold"], ["1", "2", "4", "8", "16"])
        self.assertEqual(self.data["checked"]["value"], "5")
        self.assertEqual([e["value"] for e in self.data["layers"]["examples"]], ["1", "45", "24"])
        self.assertEqual([s["total"] for s in self.data["layers"]["sets"]], [1000, 10000])
        self.assertEqual(len(self.data["six_angles"]["angles"]), 6)
        self.assertEqual([w["title"] for w in self.data["new_material"]["worlds"]],
                         ["Strings", "Permutations", "Grids"])

    def test_timeline_is_contiguous_and_covers_duration(self):
        scenes = self.data["scenes"]
        self.assertEqual([s["id"] for s in scenes][0], "title")
        self.assertEqual([s["id"] for s in scenes][-1], "end")
        self.assertEqual(scenes[0]["start"], 0)
        self.assertEqual(scenes[-1]["end"], self.data["duration"])
        for left, right in zip(scenes, scenes[1:]):
            self.assertEqual(left["end"], right["start"])
            self.assertGreater(left["end"], left["start"])
        ids = {s["id"] for s in scenes}
        self.assertEqual(len(frame_times(scenes, ids, 30, False)), 30 * self.data["duration"])
        self.assertEqual(len(frame_times(scenes, ids, 30, True)), self.data["duration"])

    def test_poster_is_the_revealed_title_card(self):
        self.assertEqual(self.data["poster"]["scene"], "title")
        # The title card's last line finishes revealing at 1.95 + .55 + .8 = 3.3 s (scenes/title.js).
        self.assertIn("1.95 + i * .55, .8", (HERE / "scenes" / "title.js").read_text(encoding="utf-8"))
        title = self.data["scenes"][0]
        self.assertGreaterEqual(poster_time(self.data), title["start"] + 4)
        self.assertLess(poster_time(self.data), title["end"] - .3)

    def test_logo_is_the_site_logo(self):
        self.assertEqual((HERE / "logo.svg").read_bytes(),
                         (ROOT / "docs" / "assets" / "images" / "logo.svg").read_bytes())
        self.assertTrue((HERE / "fonts" / "inter-latin.woff2").is_file())
        self.assertIn("fonts/inter-latin.woff2", (HERE / "explainer.css").read_text())
        core = (HERE / "core.js").read_text(encoding="utf-8")
        self.assertIn("getText('logo.svg'", core)
        for script in SCRIPTS:
            js = (HERE / script).read_text(encoding="utf-8")
            if script != "core.js":
                # Scenes draw the logo only through OPX.logo, never their own mark.
                self.assertNotIn("#opx-logo", js, script)

    def test_captions_are_bilingual_and_well_timed(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            en = write_vtt(self.data["scenes"], output, "en").read_text(encoding="utf-8")
            zh = write_vtt(self.data["scenes"], output, "zh").read_text(encoding="utf-8")
        first = self.data["scenes"][1]
        self.assertTrue(en.startswith(f"WEBVTT\n\n2\n{timestamp(first['start'] + .3)} --> "
                                      f"{timestamp(first['end'] - .3)}"))
        self.assertNotIn("Finite atoms, endless concepts.", en)
        captioned = [s for s in self.data["scenes"] if s["caption"]]
        self.assertEqual(len(re.findall(r"(?m)^\d+$", en)), len(captioned))
        self.assertEqual(len(re.findall(r"(?m)^\d+$", zh)), len(captioned))
        for scene in captioned:
            self.assertRegex(scene["caption_zh"], r"[\u4e00-\u9fff]")
            self.assertNotRegex(scene["caption"], r"[\u4e00-\u9fff]")

    def test_frames_are_english_only(self):
        for script in SCRIPTS:
            self.assertNotRegex((HERE / script).read_text(encoding="utf-8"), r"[\u4e00-\u9fff]", script)

    def test_render_source_has_no_wall_clock_or_random_state(self):
        core = (HERE / "core.js").read_text(encoding="utf-8")
        css = (HERE / "explainer.css").read_text(encoding="utf-8")
        self.assertIn("function renderAt(t)", core)
        self.assertIn("window.renderAt = renderAt", core)
        self.assertIn("window.EXPLAINER = {duration:data.duration,scenes:data.scenes}", core)
        self.assertIn("svg.replaceChildren()", core)
        for script in SCRIPTS:
            js = (HERE / script).read_text(encoding="utf-8")
            for forbidden in ("Date(", "Date.now", "performance.now", "Math.random",
                              "setTimeout", "setInterval", "requestAnimationFrame", "crypto."):
                self.assertNotIn(forbidden, js, script)
        self.assertNotIn("animation:", css)
        self.assertNotIn("transition:", css)
        self.assertIn('viewBox="0 0 1920 1080"', (HERE / "explainer.html").read_text())
        ids = [s["id"] for s in self.data["scenes"]]
        self.assertEqual(SCRIPTS, ["core.js"] + [f"scenes/{i}.js" for i in ids])

    def test_timeline_has_no_text_or_tree_node_collisions(self):
        node = os.environ.get("NODE") or shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        script = r"""
const fs = require('fs');
const data = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
class Element {
  constructor(tag) { this.tag = tag; this.attrs = {}; this.children = []; this.textContent = ''; }
  setAttribute(key, value) { this.attrs[key] = value; }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren() { this.children = []; }
}
const stage = new Element('svg'), defs = new Element('svg');
global.document = { getElementById: id => id === 'defs' ? defs : stage,
  createElementNS: (_, tag) => new Element(tag), body: { dataset: {} } };
global.window = {};
global.location = { search: process.argv[3] === 'dark' ? '?theme=dark' : '' };
global.fetch = async url => ({ ok: true, json: async () => data, text: async () => '<svg viewBox="0 0 256 256"></svg>' });
for (const script of JSON.parse(process.argv[2])) require(script);
function visit(element, opacity, texts, circles) {
  opacity *= Number(element.attrs.opacity ?? 1);
  if (opacity < .001) return;
  const a = element.attrs;
  if (element.tag === 'text') {
    const size = Number(a['font-size']), x = Number(a.x), y = Number(a.y);
    const width = [...element.textContent].length * size * (a.class === 'mono' ? .6 : .55)
      + Math.max(0, element.textContent.length - 1) * Number(a['letter-spacing'] || 0);
    const left = a['text-anchor'] === 'start' ? x : a['text-anchor'] === 'end' ? x - width : x - width / 2;
    texts.push({ text: element.textContent, left, right: left + width,
      top: y - size * .43, bottom: y + size * .43 });
  }
  if (element.tag === 'circle' && Number(a.r) >= 65)
    circles.push({ x: Number(a.cx), y: Number(a.cy), r: Number(a.r) });
  for (const child of element.children) visit(child, opacity, texts, circles);
}
const errors = new Set();
setImmediate(() => {
for (let frame = 0; frame < data.duration * 10; frame++) {
  const time = frame / 10;
  window.renderAt(time);
  const texts = [], circles = [];
  visit(stage, 1, texts, circles);
  for (let left = 0; left < texts.length; left++) {
    for (let right = left + 1; right < texts.length; right++) {
      const a = texts[left], b = texts[right];
      if (Math.min(a.right, b.right) - Math.max(a.left, b.left) > 4 &&
          Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 4)
        errors.add(`${time.toFixed(1)}: ${a.text} / ${b.text}`);
    }
  }
}
if (errors.size) { console.error([...errors].slice(0, 30).join('\n')); process.exitCode = 1; }
});
"""
        scripts = json.dumps([str(HERE / name) for name in SCRIPTS])
        for theme in ("light", "dark"):
            result = subprocess.run([node, "-e", script, str(HERE / "data.json"), scripts, theme],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
