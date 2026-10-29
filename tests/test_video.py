"""Exercise camera geometry, timing, and video output with synthetic scene images."""

import base64
import importlib.util
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
import yaml

from conftest import requires_zh_site

ROOT = Path(__file__).resolve().parents[1]
RECORD_SPEC = importlib.util.spec_from_file_location("video_record", ROOT / "tools/video/record.py")
record_module = importlib.util.module_from_spec(RECORD_SPEC)
RECORD_SPEC.loader.exec_module(record_module)


@pytest.fixture(scope="module")
def Image():
    return pytest.importorskip("PIL.Image", reason="Video composition requires Pillow")


@pytest.fixture(scope="module")
def compose_module(Image):
    spec = importlib.util.spec_from_file_location("video_compose", ROOT / "tools/video/compose.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hash_only_world_navigation_reloads_document(monkeypatch):
    class Browser:
        href = "http://localhost:8770/worlds/#pitch"

        def __init__(self):
            self.visits = []

        def js(self, expression):
            assert expression == "location.href"
            return self.href

        def navigate(self, url):
            self.visits.append(url)
            self.href = url

    monkeypatch.setattr(record_module, "wait_until", lambda *_args: None)
    monkeypatch.setattr(record_module, "stage", lambda *_args: None)
    monkeypatch.setattr(record_module, "check_theme", lambda *_args: None)
    browser = Browser()
    plan = {"site": "http://localhost:8770"}
    scene = {"path": "/worlds/#action", "selector": ".ow-app"}
    record_module.open_scene(browser, plan, scene)
    assert browser.visits == ["about:blank", "http://localhost:8770/worlds/#action"]


def test_capture_rejects_offscreen_clip():
    class Browser:
        def js(self, expression):
            if expression == "scrollX !== 0 || scrollY !== 0":
                return False
            return {"x": -50, "y": 80, "width": 1300, "height": 446,
                    "scrollX": 0, "scrollY": 0, "viewportWidth": 1920, "viewportHeight": 2400}

        def call(self, *_args):
            pytest.fail("An offscreen element must not be captured")

    with pytest.raises(record_module.CDPError, match="outside the viewport"):
        record_module.capture(Browser(), "#opulse-video-target")


@pytest.mark.parametrize("theme,index,scheme", [("light", 0, "default"),
                                                  ("dark", 1, "slate")])
def test_palette_is_stored_at_site_root(theme, index, scheme):
    class Browser:
        def navigate(self, url):
            assert url == "http://localhost:8770/"

        def js(self, expression):
            prefix = "__md_set('__palette', "
            assert expression.startswith(prefix)
            palette = json.loads(expression.removeprefix(prefix).removesuffix("); true"))
            assert palette == {"index": index, "color": {
                "scheme": scheme, "primary": "custom", "accent": "custom"}}

    record_module.set_palette(Browser(), {"site": "http://localhost:8770"}, theme)


def test_capture_resets_scroll_before_measuring(monkeypatch):
    class Browser:
        reset = False

        def js(self, expression):
            if expression == "scrollX !== 0 || scrollY !== 0":
                return True
            if expression.startswith("window.scrollTo("):
                self.reset = True
                return True
            assert self.reset
            return {"x": 100, "y": 80, "width": 400, "height": 200,
                    "scrollX": 0, "scrollY": 0, "viewportWidth": 1920, "viewportHeight": 2400}

        def call(self, method, params):
            assert method == "Page.captureScreenshot"
            assert params["clip"]["x"] == 100
            return {"data": base64.b64encode(b"image").decode()}

    monkeypatch.setattr(record_module, "settle", lambda *_args: None)
    assert record_module.capture(Browser(), ".target") == b"image"


def test_sequence_wait_expression_accepts_relative_selector_and_javascript():
    selector = '.tab[aria-selected="true"]'
    relative = record_module.sequence_wait_expression(".widget", selector)
    assert relative == f'Boolean(document.querySelector(".widget")?.querySelector({json.dumps(selector)}))'
    expression = 'document.querySelector(".tab").getAttribute("aria-selected") === "true"'
    assert record_module.sequence_wait_expression(".widget", expression) == f"Boolean({expression})"
    assert record_module.sequence_wait_expression(".widget", f"js: {expression}") == f"Boolean({expression})"


def test_sequence_records_only_captured_items_after_click_wait_and_settle(monkeypatch):
    events = []

    class Browser:
        def js(self, expression):
            events.append(("click", expression))
            return True

    monkeypatch.setattr(record_module, "open_scene", lambda *_args, **_kwargs: events.append(("open",)))
    monkeypatch.setattr(record_module, "wait_until", lambda _chrome, expression, _what:
                        events.append(("wait", expression)))
    monkeypatch.setattr(record_module, "settle", lambda _chrome, seconds:
                        events.append(("settle", seconds)))
    monkeypatch.setattr(record_module, "capture", lambda _chrome, _root, pad:
                        events.append(("capture", pad)) or b"png")
    monkeypatch.setattr(record_module, "measure", lambda _chrome, _scene:
                        events.append(("measure",)) or {"full": [0, 0, 20, 10]})
    scene = {"id": "example", "selector": ".widget", "pad": 4, "states": {"sequence": [
        {"wait": ".ready"},
        {"click": ".tab", "wait": 'js: document.querySelector(".tab").ariaSelected === "true"',
         "settle": 0.1, "capture": False},
        {"click": ".cut"},
    ]}}
    images, boxes = record_module.record_states(Browser(), {}, scene)
    assert images == [b"png", b"png"]
    assert boxes == [{"full": [0, 0, 20, 10]}] * 2
    assert [event[0] for event in events] == [
        "open", "wait", "settle", "capture", "measure", "click", "wait", "settle",
        "click", "settle", "capture", "measure"]
    assert [event[1] for event in events if event[0] == "settle"] == [0.3, 0.1, 0.3]
    clicks = [event[1] for event in events if event[0] == "click"]
    assert len(clicks) == 2
    assert 'el.querySelector(".tab")' in clicks[0]
    assert 'el.querySelector(".cut")' in clicks[1]


def storyboard(tmp_path):
    plan = {
        "fps": 8, "size": [320, 180], "transition": 0.2, "state_fade": 0.1,
        "stage": {
            "light": {"page": "#eef2f8", "background": ["#f5f7fb", "#e3e9f3"],
                      "shadow": "#0f172a", "shadow_opacity": 0.22, "radius": 8},
            "dark": {"page": "#0a0f1e", "background": ["#0a0f1e", "#0f1630"],
                     "shadow": "#050815", "shadow_opacity": 0.12, "radius": 8},
        },
        "scenes": [
            {"id": "title", "kind": "card", "duration": 0.75,
             "caption": {"en": "", "zh": ""}},
            {"id": "states", "duration": 1.5, "hold_first": 0.3, "hold_last": 0.4,
             "camera": {"intro": 0.3, "move": 0.2, "view": "graph",
                        "views": {2: "detail"}, "width": 110, "margin": 0.02},
             "caption": {"en": "Operators grow.", "zh": "运算符逐层生成。"}},
            {"id": "keys", "duration": 0.75,
             "camera": {"keys": [{"at": 0, "view": "full"},
                                 {"at": 0.2, "view": "full"},
                                 {"at": 0.4, "view": "fig", "width": 100, "align": 0.5}]},
             "caption": {"en": "A figure.", "zh": "一张图。"}},
        ],
    }
    path = tmp_path / "storyboard.yaml"
    path.write_text(yaml.safe_dump(plan, allow_unicode=True))
    return path


def recorded_frames(tmp_path, Image, theme="light"):
    frames = tmp_path / "frames" / theme
    frames.mkdir(parents=True)
    (frames / "title").mkdir(parents=True)
    Image.new("RGB", (320, 180), "#0a0f1e").save(frames / "title" / "000.png")
    for name, colors in (("states", ("#337788", "#884433", "#448833")),
                         ("keys", ("#7183a5",))):
        folder = frames / name
        folder.mkdir()
        boxes = []
        for index, color in enumerate(colors):
            Image.new("RGB", (336, 196), color).save(folder / f"{index:03d}.png")
            boxes.append({"full": [0, 0, 160, 90],
                          "graph": [20 + 5 * index, 10, 70, 40],
                          "detail": [85, 35, 50, 30], "fig": [20, 15, 120, 60]})
        (folder / "boxes.json").write_text(json.dumps({"pad": 4, "scale": 2, "states": boxes}))
    return frames


def test_timeline_captions_and_holds(tmp_path, compose_module):
    plan = yaml.safe_load(storyboard(tmp_path).read_text())
    scenes = plan["scenes"]
    spans = compose_module.timeline(plan, scenes)
    assert len(spans) == 3
    for span, expected in zip(spans, [(0.0, 0.75), (0.55, 2.05), (1.85, 2.6)]):
        assert span == pytest.approx(expected)
    assert compose_module.state_times(scenes[1], 3) == pytest.approx([0, 0.3, 1.1])
    assert compose_module.state_times(
        {"id": "held", "duration": 5, "hold_first": 0.5, "hold_last": 0.5,
         "holds": {2: 1}}, 5) == pytest.approx([0, 0.5, 2, 3, 4.5])
    compose_module.write_vtt(plan, scenes, tmp_path, "en")
    compose_module.write_vtt(plan, scenes, tmp_path, "zh")
    en = (tmp_path / "captions.en.vtt").read_text()
    zh = (tmp_path / "captions.zh.vtt").read_text()
    assert en == ("WEBVTT\n\n1\n00:00:00.650 --> 00:00:01.950\nOperators grow.\n\n"
                  "2\n00:00:01.950 --> 00:00:02.600\nA figure.\n")
    assert "00:00:00.650 --> 00:00:01.950\n运算符逐层生成。" in zh
    assert "00:00:01.950 --> 00:00:02.600\n一张图。" in zh


def test_poster_time_uses_scene_local_timeline_and_legacy_fallback(tmp_path, compose_module):
    plan = yaml.safe_load(storyboard(tmp_path).read_text())
    scenes = plan["scenes"]
    assert compose_module.resolve_poster_time(plan, scenes, 0.5) == 0.5
    plan["poster"] = {"scene": "states", "at": 0.5}
    assert compose_module.resolve_poster_time(plan, scenes, 0.5) == pytest.approx(1.05)
    assert compose_module.resolve_poster_time(plan, scenes[1:], 0.5) == pytest.approx(0.5)
    with pytest.raises(ValueError, match="outside scene states"):
        compose_module.resolve_poster_time({**plan, "poster": {"scene": "states", "at": 1.5}}, scenes, 0.5)
    with pytest.raises(ValueError, match="not in the composed timeline"):
        compose_module.resolve_poster_time(plan, scenes[:1], 0.5)


def test_home_examples_storyboard_shows_four_scales_and_growing_cuts(compose_module):
    plan = yaml.safe_load((ROOT / "tools/video/storyboard.yaml").read_text())
    scenes = {scene["id"]: scene for scene in plan["scenes"]}
    scale, cuts = scenes["examples_scale"], scenes["examples_cuts"]
    assert scale["path"] == cuts["path"] == "/"
    assert scale["selector"] == cuts["selector"] == ".op-home-scales"
    assert sum(action.get("capture", True) for action in scale["states"]["sequence"]) == 4
    assert [action["click"] for action in scale["states"]["sequence"]
            if "Operator set size" in action.get("click", "")] == [
                f'.oh-tabs[aria-label="Operator set size"] .oh-tab:nth-child({index})'
                for index in (2, 3, 4)]
    assert sum(action.get("capture", True) for action in cuts["states"]["sequence"]) == 4
    data = ROOT / "docs/assets/data/scales/s10000/int10000b-simple.json"
    table = json.loads(data.read_text())["header"]["cut_table"]
    presets = list(reversed(table))
    for action, count in zip(cuts["states"]["sequence"][-4:], (1, 5, 37, 127)):
        assert f"{count} {'step' if count == 1 else 'steps'}" in action["wait"]
        position = (1 if ":first-child" in action["click"]
                    else int(action["click"].split("nth-child(")[1].split(")")[0]))
        assert presets[position - 1]["steps"] == count
    assert cuts["transition_in"] == 0
    assert compose_module.timeline(plan, plan["scenes"])[-1][1] == pytest.approx(78.2)
    assert plan["poster"] == {"scene": "examples_cuts", "at": 6.0}
    assert compose_module.resolve_poster_time(plan, plan["scenes"], 2.0) == pytest.approx(27.9)
    assert compose_module.state_times(cuts, 4)[-1] < plan["poster"]["at"]


def test_tour_scenes_follow_current_growth_and_grade_widgets():
    scenes = {scene["id"]: scene for scene in yaml.safe_load(
        (ROOT / "tools/video/storyboard.yaml").read_text())["scenes"]}
    growth, grade = scenes["growth"], scenes["wrong_step"]
    assert growth["selector"] == ".scales-growth"
    assert grade["selector"] == '.scales-tour[data-mode="grade"]'
    assert growth["selector"] in (ROOT / "docs/snippets/vis_growth.html").read_text()
    assert 'class="scales-tour" data-lang="en" data-mode="grade"' in (
        ROOT / "docs/snippets/vis_steps_scales.html").read_text()
    assert [action["click"] for action in growth["states"]["sequence"] if action.get("click")][
        :3] == [f".sg-tab:nth-child({index})" for index in (2, 3, 4)]
    assert growth["states"]["sequence"][-1]["click"] == ".sg-graph-scroll .sg-node.sg-simple"
    assert sum(action.get("capture", True) for action in growth["states"]["sequence"]) == 5
    report = json.loads((ROOT / "docs/assets/data/scales_grade/s10.json").read_text())
    assert report["runs"][1]["report"]["first_error"] == report["slip"]
    assert report["slip"] >= 50
    assert grade["states"]["sequence"][-1]["click"].endswith("button:last-child")
    assert ".st-grade-row.st-error" in grade["states"]["sequence"][-1]["wait"]


def test_camera_rectangles(tmp_path, compose_module, Image):
    fit = compose_module.fit_rect([10, 20, 80, 40], None, 0)
    assert fit == pytest.approx([50, 40, 80])
    assert compose_module.fit_rect([10, 20, 80, 40], 120, 0) == pytest.approx([50, 40, 120])
    assert compose_module.clamp_rect([0, 0, 80], (160, 90), 0) == pytest.approx([40, 22.5, 80])

    plan = yaml.safe_load(storyboard(tmp_path).read_text())
    frames = recorded_frames(tmp_path, Image)
    stage = compose_module.Stage(plan)
    states = compose_module.Scene(plan, plan["scenes"][1], frames / "states", stage)
    keys = compose_module.Scene(plan, plan["scenes"][2], frames / "keys", stage)
    assert states.camera.at(0) == pytest.approx(compose_module.fit_rect([0, 0, 160, 90], None, 0.02))
    assert states.camera.at(0.7) == pytest.approx([60, 30, 110])
    assert states.camera.at(1.4) == pytest.approx([107.2, 50, 110])
    assert keys.camera.at(0) == pytest.approx(compose_module.fit_rect([0, 0, 160, 90], None, 0.04))
    assert keys.camera.at(0.5)[2] == pytest.approx(100)


def test_scene_transition_dips_through_background(tmp_path, monkeypatch, compose_module, Image):
    plan = yaml.safe_load(storyboard(tmp_path).read_text())
    plan["fps"] = 20
    plan["scenes"] = [plan["scenes"][0], {"id": "end", "kind": "card", "duration": 0.75}]
    frames = recorded_frames(tmp_path, Image)
    (frames / "end").mkdir()
    Image.new("RGB", (320, 180), "#82374a").save(frames / "end" / "000.png")

    class Encoder:
        def __init__(self, frame_index):
            self.stdin = self
            self.frame_index = frame_index
            self.count = 0
            self.frame = None

        def write(self, data):
            if self.count == self.frame_index:
                self.frame = np.frombuffer(data, dtype=np.uint8).reshape(180, 320, 3).copy()
            self.count += 1

        def close(self):
            pass

        def wait(self):
            return 0

    encoder = Encoder(13)  # t=0.65, the midpoint of the 0.55–0.75 transition
    monkeypatch.setattr(compose_module.subprocess, "Popen", lambda *_args, **_kwargs: encoder)
    compose_module.render(plan, plan["scenes"], frames, tmp_path / "master.mkv")
    background = compose_module.Stage(plan).background.astype(np.uint8)
    assert np.max(np.abs(encoder.frame.astype(np.int16) - background.astype(np.int16))) <= 1

    plan["scenes"][1]["transition_in"] = 0
    encoder = Encoder(15)  # t=0.75, the first frame of the end card
    compose_module.render(plan, plan["scenes"], frames, tmp_path / "master.mkv")
    assert np.array_equal(encoder.frame, np.asarray(Image.open(frames / "end" / "000.png")))


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_compose_synthetic_scenes(tmp_path, theme, monkeypatch, compose_module, Image):
    board = storyboard(tmp_path)
    plan = yaml.safe_load(board.read_text())
    plan["poster"] = {"scene": "states", "at": 0.5}
    board.write_text(yaml.safe_dump(plan))
    recorded_frames(tmp_path, Image, theme)
    frames = tmp_path / "frames"
    output = tmp_path / "video"
    poster_seeks = []
    original_run = subprocess.run

    def capture_poster_seek(command, *args, **kwargs):
        if "-ss" in command:
            poster_seeks.append(float(command[command.index("-ss") + 1]))
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(compose_module.subprocess, "run", capture_poster_seek)
    result = compose_module.compose(board, frames, output, poster_time=0.5, theme=theme)
    assert poster_seeks == pytest.approx([1.05])
    assert result["duration"] == pytest.approx(2.625)
    assert result["scenes"] == ["title", "states", "keys"]
    assert all(0 < result[name] < 10_000_000 for name in
               (f"opulse-{theme}.mp4", f"opulse-{theme}.webm", f"poster-{theme}.jpg"))
    assert "Operators grow." in (output / "captions.en.vtt").read_text()
    for video, codec in ((f"opulse-{theme}.mp4", "h264"),
                         (f"opulse-{theme}.webm", "vp9")):
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,pix_fmt,width,height", "-of", "json", str(output / video)],
            check=True, capture_output=True, text=True)
        stream = json.loads(probe.stdout)["streams"][0]
        assert (stream["width"], stream["height"], stream["codec_name"], stream["pix_fmt"]) == (320, 180, codec, "yuv420p")


def test_theme_stage_colours(tmp_path, monkeypatch, compose_module):
    plan = yaml.safe_load(storyboard(tmp_path).read_text())
    light = compose_module.Stage(plan, "light")
    dark = compose_module.Stage(plan, "dark")
    assert light.background[0, 0].astype(int).tolist() == [245, 247, 251]
    assert dark.background[0, 0].astype(int).tolist() == [10, 15, 30]
    assert dark.shadow_opacity < light.shadow_opacity
    assert plan["stage"]["light"]["page"] == "#eef2f8"
    assert plan["stage"]["dark"]["page"] == "#0a0f1e"
    monkeypatch.setattr(record_module, "settle", lambda *_args: None)

    class Browser:
        def __init__(self):
            self.scripts = []

        def js(self, script):
            self.scripts.append(script)

    for theme, color in (("light", "#eef2f8"), ("dark", "#0a0f1e")):
        browser = Browser()
        record_module.stage(browser, plan, {"selector": ".widget"}, theme)
        assert color in browser.scripts[0]


@pytest.mark.parametrize("page,caption", [("docs/index.md", "captions.en.vtt"),
                                           pytest.param("docs_zh/index.md", "captions.zh.vtt",
                                                        marks=requires_zh_site)])
def test_homepage_has_light_fallback_and_both_theme_urls(page, caption):
    markup = (ROOT / page).read_text()
    for theme in ("light", "dark"):
        for kind, extension in (("mp4", "mp4"), ("webm", "webm"), ("poster", "jpg")):
            name = f"assets/video/{'poster' if kind == 'poster' else 'opulse'}-{theme}.{extension}"
            assert f'data-{theme}-{kind}="{name}"' in markup
            if theme == "light":
                assert f'src="{name}"' in markup or f'poster="{name}"' in markup
    assert f'assets/video/{caption}' in markup
