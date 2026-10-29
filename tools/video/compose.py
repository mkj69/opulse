"""Compose recorded scene images into the explainer video, its poster and WebVTT captions.

Each scene is a list of PNG images written by record.py, one per widget state, plus the focus
boxes measured in every state. A virtual camera frames each scene: it first shows the whole
widget, then moves and zooms to the focus named for the current state, or follows time keys
for a slow pan across a figure. Consecutive states crossfade briefly and scene transitions dip
through the stage background. Frames are rendered with Pillow and NumPy and piped to ffmpeg.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
from collections import OrderedDict
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFilter

LIMIT_BYTES = 10_000_000
ASPECT = 16 / 9


# ----------------------------------------------------------------------------- timing
def timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{whole:02}.{milliseconds:03}"


def timeline(plan: dict, scenes: list[dict]) -> list[tuple[float, float]]:
    """Start and end time of every scene; a scene starts while the previous one fades out."""
    spans, cursor = [], 0.0
    for index, scene in enumerate(scenes):
        fade = 0.0 if index == 0 else float(scene.get("transition_in", plan["transition"]))
        start = cursor - fade
        spans.append((start, start + float(scene["duration"])))
        cursor = start + float(scene["duration"])
    return spans


def resolve_poster_time(plan: dict, scenes: list[dict], poster_time: float) -> float:
    """Resolve a scene-local poster position on the composed video timeline."""
    poster = plan.get("poster")
    if poster is None:
        return poster_time
    for scene, (start, _end) in zip(scenes, timeline(plan, scenes)):
        if scene["id"] == poster["scene"]:
            at = float(poster["at"])
            if not 0 <= at < float(scene["duration"]):
                raise ValueError(f"Poster time {at} is outside scene {scene['id']}")
            return start + at
    raise ValueError(f"Poster scene {poster['scene']} is not in the composed timeline")


def write_vtt(plan: dict, scenes: list[dict], output: Path, language: str) -> Path:
    spans = timeline(plan, scenes)
    lines, number = ["WEBVTT", ""], 0
    for index, (scene, (start, end)) in enumerate(zip(scenes, spans)):
        text = scene["caption"][language].strip()
        if not text:
            continue
        lead = float(scene.get("transition_in", plan["transition"])) / 2 if index else 0
        tail = float(scenes[index + 1].get("transition_in", plan["transition"])) / 2 if index + 1 < len(scenes) else 0
        number += 1
        lines += [str(number), f"{timestamp(start + lead)} --> {timestamp(end - tail)}", text, ""]
    path = output / f"captions.{language}.vtt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def state_times(scene: dict, count: int) -> list[float]:
    """Onset of every state. The first and last states and any listed in ``holds`` get fixed
    durations; the other states share the remaining time evenly."""
    if count == 1:
        return [0.0]
    lengths: list[float | None] = [None] * count
    lengths[0] = float(scene.get("hold_first", 1.0))
    lengths[-1] = float(scene.get("hold_last", 1.5))
    for key, value in (scene.get("holds") or {}).items():
        lengths[int(key)] = float(value)
    free = [i for i, v in enumerate(lengths) if v is None]
    rest = float(scene["duration"]) - sum(v for v in lengths if v is not None)
    if rest < 0 or (free and rest <= 0):
        raise ValueError(f"Scene {scene['id']} is too short for its states")
    for i in free:
        lengths[i] = rest / len(free)
    onsets, cursor = [], 0.0
    for value in lengths:
        onsets.append(cursor)
        cursor += value
    return onsets


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


# ----------------------------------------------------------------------------- camera
def fit_rect(box: list[float], width: float | None, margin: float) -> list[float]:
    """Camera rectangle [cx, cy, w] in CSS pixels that shows ``box`` with a margin."""
    x, y, w, h = box
    need = max(w * (1 + 2 * margin), h * (1 + 2 * margin) * ASPECT)
    return [x + w / 2, y + h / 2, max(need, width or 0)]


def clamp_rect(rect: list[float], size: tuple[float, float], margin: float) -> list[float]:
    """Keep a zoomed rectangle inside the widget so the camera never shows empty space."""
    cx, cy, w = rect
    h = w / ASPECT
    width, height = size
    pad_x, pad_y = w * margin, h * margin
    if w < width + 2 * pad_x:
        cx = min(max(cx, w / 2 - pad_x), width - w / 2 + pad_x)
    if h < height + 2 * pad_y:
        cy = min(max(cy, h / 2 - pad_y), height - h / 2 + pad_y)
    return [cx, cy, w]


def lerp_rect(a: list[float], b: list[float], k: float) -> list[float]:
    return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k,
            math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * k)]


class Camera:
    """Piecewise eased moves between target rectangles."""

    def __init__(self, start: list[float]):
        self.start = start
        self.moves: list[tuple[float, float, list[float], list[float]]] = []

    def move(self, at: float, duration: float, target: list[float]) -> None:
        origin = self.at(at)
        if max(abs(origin[0] - target[0]), abs(origin[1] - target[1]), abs(origin[2] - target[2])) < 0.5:
            return
        self.moves.append((at, max(duration, 1e-6), origin, target))

    def at(self, t: float) -> list[float]:
        rect = self.start
        for start, duration, origin, target in self.moves:
            if t < start:
                break
            rect = lerp_rect(origin, target, ease((t - start) / duration))
        return rect


# ----------------------------------------------------------------------------- drawing
class Stage:
    def __init__(self, plan: dict, theme: str = "light"):
        self.width, self.height = plan["size"]
        conf = plan["stage"][theme]
        top, bottom = (np.array(Image.new("RGB", (1, 1), c).getpixel((0, 0)), dtype=np.float32)
                       for c in conf["background"])
        ramp = np.linspace(0, 1, self.height, dtype=np.float32)[:, None, None]
        self.background = (top * (1 - ramp) + bottom * ramp).repeat(self.width, axis=1)
        self.radius = float(conf["radius"])
        self.shadow_color = np.array(Image.new("RGB", (1, 1), conf["shadow"]).getpixel((0, 0)),
                                     dtype=np.float32)
        self.shadow_opacity = float(conf["shadow_opacity"])

    def full(self, image: Image.Image) -> np.ndarray:
        return np.asarray(image.convert("RGB").resize((self.width, self.height), Image.LANCZOS))

    def shadow(self, x0: float, y0: float, x1: float, y1: float, radius: float) -> np.ndarray:
        """Soft drop shadow of a card at output coordinates, drawn at quarter resolution."""
        q = 4
        small = Image.new("L", (self.width // q, self.height // q), 0)
        ImageDraw.Draw(small).rounded_rectangle(
            (x0 / q, (y0 + 12) / q, x1 / q, (y1 + 12) / q), max(1, radius / q), fill=255)
        small = small.filter(ImageFilter.GaussianBlur(7))
        return np.asarray(small.resize((self.width, self.height), Image.BILINEAR), dtype=np.float32) / 255


class Scene:
    """Renders the frames of one scene at local time t."""

    def __init__(self, plan: dict, scene: dict, folder: Path, stage: Stage):
        self.scene = scene
        self.stage = stage
        self.duration = float(scene["duration"])
        self.paths = sorted(folder.glob("*.png"))
        if not self.paths:
            raise FileNotFoundError(f"No recorded images in {folder}")
        self.kind = scene.get("kind", "states")
        self.fade = float(plan["state_fade"])
        self.images: OrderedDict[int, Image.Image] = OrderedDict()
        self.cache: OrderedDict[tuple, np.ndarray] = OrderedDict()
        if self.kind == "card":
            self.card = stage.full(Image.open(self.paths[0]))
            return
        meta = json.loads((folder / "boxes.json").read_text())
        self.pad, self.scale, self.boxes = float(meta["pad"]), float(meta["scale"]), meta["states"]
        self.onsets = state_times(scene, len(self.paths))
        self.camera = self.plan_camera(scene.get("camera", {}))

    # camera ----------------------------------------------------------------
    def size(self, index: int) -> tuple[float, float]:
        return tuple(self.boxes[index]["full"][2:])

    def view(self, index: int, name: str, width: float | None, conf: dict, align: float | None = None) -> list[float]:
        box = None
        for i in range(index, -1, -1):  # a focus missing in this state falls back to an earlier one
            box = self.boxes[i].get(name)
            if box:
                break
        if not box:
            raise ValueError(f"Scene {self.scene['id']} has no box named {name}")
        margin = float(conf.get("margin", 0.04))
        rect = fit_rect(box, None if name == "full" else width, margin)
        if align is not None and width:
            rect[2] = float(width)
            half = rect[2] / 2
            rect[0] = box[0] + half - rect[2] * margin + align * (box[2] - 2 * half + 2 * rect[2] * margin)
        if conf.get("lock_x"):
            rect[0] = self.size(index)[0] / 2
        return rect if name == "full" else clamp_rect(rect, self.size(index), margin)

    def plan_camera(self, conf: dict) -> Camera:
        if "keys" in conf:
            keys = conf["keys"]
            rects = [self.view(0, k.get("view", "full"), k.get("width"), conf, k.get("align")) for k in keys]
            camera = Camera(rects[0])
            for prev, key, rect in zip(keys, keys[1:], rects[1:]):
                camera.move(float(prev["at"]), float(key["at"]) - float(prev["at"]), rect)
            return camera
        intro = float(conf.get("intro", 1.8))
        move = float(conf.get("move", 0.9))
        width = conf.get("width")
        views = {int(k): v for k, v in (conf.get("views") or {}).items()}
        default = conf.get("view", "full")
        camera = Camera(self.view(0, "full" if intro > 0 else views.get(0, default), width, conf))
        for index, onset in enumerate(self.onsets):
            camera.move(max(onset, intro), move, self.view(index, views.get(index, default), width, conf))
        return camera

    # drawing ---------------------------------------------------------------
    def image(self, index: int) -> Image.Image:
        if index not in self.images:
            self.images[index] = Image.open(self.paths[index]).convert("RGB")
            if len(self.images) > 3:
                self.images.popitem(last=False)
        return self.images[index]

    def render(self, index: int, rect: list[float]) -> np.ndarray:
        key = (index, *(round(v, 2) for v in rect))
        if key in self.cache:
            return self.cache[key]
        stage, image = self.stage, self.image(index)
        out_w, out_h = stage.width, stage.height
        cx, cy, w = rect
        h = w / ASPECT
        k = out_w / w                                 # output pixels per CSS pixel
        s = self.scale
        # Image extent in CSS pixels relative to the element (captures include the pad).
        ex0, ey0 = -self.pad, -self.pad
        ex1, ey1 = ex0 + image.width / s, ey0 + image.height / s
        left, top = cx - w / 2, cy - h / 2
        to_x = lambda v: (v - left) * k
        to_y = lambda v: (v - top) * k
        frame = stage.background.copy()
        radius = stage.radius * k
        shade = stage.shadow(to_x(ex0), to_y(ey0), to_x(ex1), to_y(ey1), radius)
        strength = stage.shadow_opacity * shade[..., None]
        frame *= 1 - strength
        frame += stage.shadow_color * strength
        # Visible part of the card.
        vx0, vy0 = max(ex0, left), max(ey0, top)
        vx1, vy1 = min(ex1, left + w), min(ey1, top + h)
        if vx1 > vx0 and vy1 > vy0:
            ox0, oy0 = round(to_x(vx0)), round(to_y(vy0))
            ox1, oy1 = round(to_x(vx1)), round(to_y(vy1))
            ox1, oy1 = min(ox1, out_w), min(oy1, out_h)
            box = ((vx0 - ex0) * s, (vy0 - ey0) * s, (vx1 - ex0) * s, (vy1 - ey0) * s)
            part = image.resize((ox1 - ox0, oy1 - oy0), Image.BICUBIC, box=box, reducing_gap=2.0)
            mask = Image.new("L", (out_w, out_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (to_x(ex0), to_y(ey0), to_x(ex1) - 1, to_y(ey1) - 1), radius, fill=255)
            alpha = np.asarray(mask, dtype=np.float32)[oy0:oy1, ox0:ox1, None] / 255
            region = frame[oy0:oy1, ox0:ox1]
            frame[oy0:oy1, ox0:ox1] = region * (1 - alpha) + np.asarray(part, dtype=np.float32) * alpha
        # Where the card runs past the frame edge, fade it into the background instead of cutting it.
        depth = 90
        ramp = (np.linspace(0, 1, depth, dtype=np.float32) ** 1.2)
        background = stage.background
        if to_y(ey0) < 0:
            frame[:depth] = background[:depth] + (frame[:depth] - background[:depth]) * ramp[:, None, None]
        if to_y(ey1) > out_h:
            frame[-depth:] = background[-depth:] + (frame[-depth:] - background[-depth:]) * ramp[::-1, None, None]
        if to_x(ex0) < 0:
            frame[:, :depth] = background[:, :depth] + (frame[:, :depth] - background[:, :depth]) * ramp[None, :, None]
        if to_x(ex1) > out_w:
            frame[:, -depth:] = background[:, -depth:] + (frame[:, -depth:] - background[:, -depth:]) * ramp[None, ::-1, None]
        result = frame.round().clip(0, 255).astype(np.uint8)
        self.cache[key] = result
        if len(self.cache) > 8:
            self.cache.popitem(last=False)
        return result

    def frame(self, t: float) -> np.ndarray:
        if self.kind == "card":
            return self.card
        rect = self.camera.at(t)
        index = max(i for i, onset in enumerate(self.onsets) if onset <= t + 1e-9)
        current = self.render(index, rect)
        if index == 0:
            return current
        gap = self.onsets[index] - self.onsets[index - 1]
        fade = min(self.fade, 0.8 * gap)
        alpha = (t - self.onsets[index]) / fade if fade > 0 else 1.0
        if alpha >= 1:
            return current
        return blend(self.render(index - 1, rect), current, ease(alpha))


def blend(a: np.ndarray, b: np.ndarray, alpha: float) -> np.ndarray:
    return (a.astype(np.float32) * (1 - alpha) + b.astype(np.float32) * alpha + 0.5).astype(np.uint8)


# ----------------------------------------------------------------------------- output
def render(plan: dict, scenes: list[dict], frames: Path, master: Path,
           theme: str = "light") -> float:
    """Render every frame once into a near lossless master file; return the duration."""
    stage = Stage(plan, theme)
    background = stage.background.astype(np.uint8)
    players = [Scene(plan, s, frames / s["id"], stage) for s in scenes]
    spans = timeline(plan, scenes)
    total = spans[-1][1]
    fps = int(plan["fps"])
    width, height = plan["size"]
    encoder = subprocess.Popen([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "4", "-pix_fmt", "yuv444p", str(master)],
        stdin=subprocess.PIPE)
    count = round(total * fps)
    for n in range(count):
        t = n / fps
        active = [(i, t - start) for i, (start, end) in enumerate(spans) if start <= t < end]
        if len(active) == 1:
            image = players[active[0][0]].frame(active[0][1])
        else:
            (i, ta), (j, tb) = active[0], active[-1]
            fade = float(scenes[j].get("transition_in", plan["transition"]))
            a = ease(tb / fade)
            if a < 0.5:
                image = blend(players[i].frame(ta), background, 2 * a)
            else:
                image = blend(background, players[j].frame(tb), 2 * a - 1)
        encoder.stdin.write(image.tobytes())
    encoder.stdin.close()
    if encoder.wait():
        raise RuntimeError("ffmpeg failed while writing the master file")
    return count / fps


def encode(master: Path, output: Path, crf_mp4: int, crf_webm: int, theme: str) -> None:
    base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(master), "-an"]
    subprocess.run([*base, "-c:v", "libx264", "-preset", "slow", "-tune", "stillimage", "-crf", str(crf_mp4),
                    "-profile:v", "high", "-level", "4.1", "-g", "150", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(output / f"opulse-{theme}.mp4")], check=True)
    subprocess.run([*base, "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", str(crf_webm), "-deadline", "good",
                    "-cpu-used", "2", "-row-mt", "1", "-g", "150", "-pix_fmt", "yuv420p",
                    str(output / f"opulse-{theme}.webm")], check=True)


def compose(storyboard: Path, frames: Path, output: Path, crf_mp4: int = 24, crf_webm: int = 36,
            poster_time: float = 2.0, max_bytes: int = LIMIT_BYTES,
            theme: str = "light") -> dict:
    plan = yaml.safe_load(storyboard.read_text())
    frames = frames / theme
    scenes = [s for s in plan["scenes"] if s.get("enabled", True) and (frames / s["id"]).is_dir()]
    if not scenes:
        raise ValueError("No recorded scenes to compose")
    output.mkdir(parents=True, exist_ok=True)
    for language in ("en", "zh"):
        write_vtt(plan, scenes, output, language)
    master = frames / "master.mkv"
    duration = render(plan, scenes, frames, master, theme)
    encode(master, output, crf_mp4, crf_webm, theme)
    poster_time = resolve_poster_time(plan, scenes, poster_time)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(poster_time),
                    "-i", str(master), "-frames:v", "1", "-q:v", "3", str(output / f"poster-{theme}.jpg")], check=True)
    names = (f"opulse-{theme}.mp4", f"opulse-{theme}.webm", f"poster-{theme}.jpg")
    sizes = {name: (output / name).stat().st_size for name in names}
    if sizes[names[0]] > max_bytes:
        raise ValueError(f"{names[0]} is {sizes[names[0]]} bytes, over the {max_bytes} byte MP4 limit; "
                         "increase --crf-mp4 or --max-bytes")
    return {"duration": duration, "scenes": [s["id"] for s in scenes], **sizes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--storyboard", type=Path, default=Path(__file__).with_name("storyboard.yaml"))
    parser.add_argument("--frames", type=Path, default=Path("tools/video/output/frames"))
    parser.add_argument("--output", type=Path, default=Path("docs/assets/video"))
    parser.add_argument("--crf-mp4", type=int, default=24)
    parser.add_argument("--crf-webm", type=int, default=36)
    parser.add_argument("--theme", choices=("light", "dark"), default="light")
    parser.add_argument("--max-bytes", type=int, default=LIMIT_BYTES,
                        help="Maximum MP4 size in bytes")
    args = parser.parse_args()
    print(compose(args.storyboard, args.frames, args.output, args.crf_mp4, args.crf_webm,
                  max_bytes=args.max_bytes, theme=args.theme))


if __name__ == "__main__":
    main()
