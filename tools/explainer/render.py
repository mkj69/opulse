"""Render deterministic SVG frames through CDP, then encode homepage video assets."""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import subprocess
import sys
import threading

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools" / "video"))
from record import Chrome, CDPError  # Reuse the site's tested CDP transport.


def timestamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    whole, ms = divmod(ms, 1000)
    return f"{hours:02}:{minutes:02}:{whole:02}.{ms:03}"


def write_vtt(scenes: list[dict], output: Path, language: str) -> Path:
    """Write non-overlapping cues, leaving 0.3 s at each scene boundary."""
    field = "caption" if language == "en" else "caption_zh"
    lines = ["WEBVTT", ""]
    for index, scene in enumerate(scenes):
        caption = scene[field].strip()
        if not caption:
            continue
        start = scene["start"] + (0.3 if index else 0)
        end = scene["end"] - (0.3 if index < len(scenes)-1 else 0)
        lines.extend((str(index + 1), f"{timestamp(start)} --> {timestamp(end)}", caption, ""))
    target = output / f"captions.{language}.vtt"
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def load_data() -> dict:
    data = json.loads((HERE / "data.json").read_text(encoding="utf-8"))
    assert data["scenes"][0]["start"] == 0
    assert data["scenes"][-1]["end"] == data["duration"]
    assert all(a["end"] == b["start"] for a,b in zip(data["scenes"], data["scenes"][1:]))
    return data


def poster_time(data: dict) -> float:
    """The poster is a still of one scene (the fully revealed title card)."""
    scene = next(s for s in data["scenes"] if s["id"] == data["poster"]["scene"])
    at = scene["start"] + data["poster"]["offset"]
    assert scene["start"] <= at < scene["end"]
    return at


@contextmanager
def server():
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(HERE)))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/explainer.html"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def capture(chrome: Chrome, at: float, target: Path) -> None:
    chrome.js(f"window.renderAt({at:.9f})")
    reply = chrome.call("Page.captureScreenshot", {"format": "png", "fromSurface": True,
                                                   "captureBeyondViewport": False})
    target.write_bytes(base64.b64decode(reply["data"]))


def run_ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def encode(frames: Path, fps: int, output: Path, stem: str) -> None:
    source = str(frames / "frame%06d.png")
    common = ["-framerate", str(fps), "-i", source, "-an"]
    run_ffmpeg(*common, "-c:v", "libx264", "-preset", "medium", "-crf", "23",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output / f"{stem}.mp4"))
    run_ffmpeg(*common, "-c:v", "libvpx-vp9", "-deadline", "good", "-cpu-used", "3",
               "-crf", "35", "-b:v", "0", "-pix_fmt", "yuv420p", str(output / f"{stem}.webm"))


def sheet(frames: Path, count: int, output: Path, theme: str) -> None:
    """Build four by four 480 px thumbnails without a Pillow dependency."""
    for offset in range(0, count, 16):
        target = output / f"sheet-{theme}-{offset//16+1:02}.jpg"
        run_ffmpeg("-start_number", str(offset), "-i", str(frames / "frame%06d.png"),
                   "-vf", "scale=480:270,tile=4x4:padding=8:margin=8",
                   "-frames:v", "1", "-q:v", "3", str(target))


def frame_times(scenes: list[dict], selected: set[str], fps: int, samples: bool) -> list[float]:
    result = []
    for scene in scenes:
        if scene["id"] not in selected:
            continue
        step = 1 if samples else 1 / fps
        count = math.ceil((scene["end"]-scene["start"]) / step)
        result.extend(scene["start"] + i*step for i in range(count))
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("chrome", help="path to a Chrome or Chromium binary")
    parser.add_argument("output_dir", type=Path, help="frame and contact sheet workspace")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--themes", nargs="+", choices=("light", "dark"), default=["light", "dark"])
    parser.add_argument("--scenes", nargs="+", metavar="ID", help="render only these scene IDs")
    parser.add_argument("--sheet", action="store_true", help="sample one frame per second into contact sheets only")
    parser.add_argument("--at", nargs="+", type=float, metavar="T",
                        help="only capture these times (seconds) to <output_dir>/<theme>/at-<T>.png")
    parser.add_argument("--assets-dir", type=Path, default=ROOT / "docs" / "assets" / "video")
    args = parser.parse_args(argv)
    if args.fps < 1:
        parser.error("--fps must be positive")
    data = load_data()
    all_ids = {s["id"] for s in data["scenes"]}
    chosen = set(args.scenes or all_ids)
    if not chosen <= all_ids:
        parser.error(f"unknown scenes: {', '.join(sorted(chosen-all_ids))}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if not args.sheet and not args.at:
        args.assets_dir.mkdir(parents=True, exist_ok=True)
        if not args.scenes:
            write_vtt(data["scenes"], args.assets_dir, "en")
            write_vtt(data["scenes"], args.assets_dir, "zh")
    times = args.at or frame_times(data["scenes"], chosen, args.fps, args.sheet)
    with server() as url:
        for theme in args.themes:
            frames = args.output_dir / theme / ("." if args.at else "samples" if args.sheet else "frames")
            frames.mkdir(parents=True, exist_ok=True)
            chrome = Chrome(args.chrome, (1920, 1080), theme=theme)
            try:
                chrome.navigate(f"{url}?theme={theme}")
                # data.json, logo.svg and both font families load before EXPLAINER is set.
                import time
                deadline = time.monotonic() + 20
                while not chrome.js("Boolean(window.EXPLAINER && window.renderAt)"):
                    if time.monotonic() >= deadline:
                        raise CDPError("explainer data did not load")
                    time.sleep(.1)
                metadata = chrome.js("window.EXPLAINER")
                if metadata != {"duration": data["duration"], "scenes": data["scenes"]}:
                    raise CDPError("browser scene metadata differs from data.json")
                for n, at in enumerate(times):
                    name = f"at-{at:07.2f}.png" if args.at else f"frame{n:06d}.png"
                    capture(chrome, at, frames / name)
                    if n % max(1, args.fps*5) == 0:
                        print(f"{theme}: {n+1}/{len(times)} frames", flush=True)
                if not args.sheet and not args.scenes and not args.at:
                    poster = args.output_dir / theme / "poster.png"
                    capture(chrome, poster_time(data), poster)
                    run_ffmpeg("-i", str(poster), "-frames:v", "1", "-q:v", "3",
                               str(args.assets_dir / f"poster-{theme}.jpg"))
            finally:
                chrome.close()
            if args.at:
                continue
            if args.sheet:
                sheet(frames, len(times), args.output_dir, theme)
            else:
                stem = f"opulse-{theme}" if not args.scenes else f"opulse-{theme}-preview"
                destination = args.assets_dir if not args.scenes else args.output_dir
                encode(frames, args.fps, destination, stem)
    print("Done", flush=True)


if __name__ == "__main__":
    main()
