"""Record site widgets as PNG frames through Chrome DevTools Protocol."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

import yaml


class CDPError(RuntimeError):
    """A browser or storyboard operation failed."""


class WebSocket:
    """The small RFC 6455 subset used by CDP JSON messages."""

    def __init__(self, url: str):
        parsed = urlparse(url)
        if parsed.scheme != "ws":
            raise CDPError(f"Expected a ws URL: {url}")
        self.sock = socket.create_connection((parsed.hostname, parsed.port), timeout=10)
        self.sock.settimeout(30)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (f"GET {parsed.path or '/'}{('?' + parsed.query) if parsed.query else ''} HTTP/1.1\r\n"
                   f"Host: {parsed.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                   "Origin: http://localhost\r\n\r\n")
        self.sock.sendall(request.encode())
        response = bytearray()
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("Chrome closed the WebSocket handshake")
            response.extend(chunk)
        headers, self.pending = bytes(response).split(b"\r\n\r\n", 1)
        expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if not headers.startswith(b"HTTP/1.1 101") or expected not in headers:
            raise CDPError(f"Chrome rejected the WebSocket handshake: {headers[:200]!r}")

    def _read(self, count: int) -> bytes:
        result = bytearray()
        if self.pending:
            take = self.pending[:count]
            result.extend(take)
            self.pending = self.pending[len(take):]
        while len(result) < count:
            chunk = self.sock.recv(count - len(result))
            if not chunk:
                raise CDPError("Chrome closed the WebSocket")
            result.extend(chunk)
        return bytes(result)

    def send(self, message: dict) -> None:
        payload = json.dumps(message).encode()
        mask = os.urandom(4)
        length = len(payload)
        header = bytes([0x81, 0x80 | length]) if length < 126 else (
            bytes([0x81, 0x80 | 126]) + struct.pack("!H", length) if length < 65536
            else bytes([0x81, 0x80 | 127]) + struct.pack("!Q", length))
        self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def receive(self) -> dict:
        while True:
            first, second = self._read(2)
            length = second & 127
            if length == 126:
                length = struct.unpack("!H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read(8))[0]
            mask = self._read(4) if second & 128 else None
            payload = self._read(length)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if first & 15 == 8:
                raise CDPError("Chrome closed the WebSocket")
            if first & 15 == 9:
                continue
            if first & 15 == 1:
                return json.loads(payload)

    def close(self) -> None:
        self.sock.close()


class Chrome:
    def __init__(self, executable: str, viewport: tuple[int, int], scale: float = 1,
                 theme: str = "light"):
        self.profile = tempfile.mkdtemp(prefix="opulse-video-chrome-")
        self.proc = subprocess.Popen([
            executable, "--headless=new", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", "--hide-scrollbars", "--font-render-hinting=none",
            "--remote-allow-origins=*",
            "--remote-debugging-port=0", f"--user-data-dir={self.profile}",
            "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            port_file = Path(self.profile) / "DevToolsActivePort"
            deadline = time.monotonic() + 15
            while not port_file.exists() and time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    raise CDPError("Chrome exited before opening CDP")
                time.sleep(0.1)
            if not port_file.exists():
                raise CDPError("Chrome did not open a debugging port")
            port = int(port_file.read_text().splitlines()[0])
            pages = json.load(urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
            page = next(p for p in pages if p.get("type") == "page")
            self.ws = WebSocket(page["webSocketDebuggerUrl"])
            self.sequence = 0
            self.call("Page.enable")
            self.call("Runtime.enable")
            self.call("Emulation.setDeviceMetricsOverride", {
                "width": viewport[0], "height": viewport[1],
                "deviceScaleFactor": scale, "mobile": False})
            self.call("Emulation.setEmulatedMedia", {"media": "screen",
                "features": [{"name": "prefers-reduced-motion", "value": "reduce"},
                             {"name": "prefers-color-scheme", "value": theme}]})
        except Exception:
            self.close()
            raise

    def call(self, method: str, params: dict | None = None) -> dict:
        self.sequence += 1
        self.ws.send({"id": self.sequence, "method": method, "params": params or {}})
        while True:
            reply = self.ws.receive()
            if reply.get("id") == self.sequence:
                if "error" in reply:
                    raise CDPError(f"{method}: {reply['error']}")
                return reply.get("result", {})

    def js(self, expression: str):
        result = self.call("Runtime.evaluate", {"expression": expression,
            "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            raise CDPError(details.get("exception", {}).get("description", details.get("text", "JavaScript error")))
        return result.get("result", {}).get("value")

    def navigate(self, url: str) -> None:
        result = self.call("Page.navigate", {"url": url})
        if "errorText" in result:
            raise CDPError(f"Cannot load {url}: {result['errorText']}")
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self.js("location.href") == url and self.js("document.readyState") == "complete":
                time.sleep(0.5)
                return
            time.sleep(0.1)
        raise CDPError(f"Page did not load: {url}")

    def wait_for(self, selector: str) -> None:
        deadline = time.monotonic() + 20
        query = "Boolean(document.querySelector(" + json.dumps(selector) + "))"
        while time.monotonic() < deadline:
            if self.js(query):
                return
            time.sleep(0.1)
        raise CDPError(f"Missing selector after page load: {selector}")

    def close(self) -> None:
        if hasattr(self, "ws"):
            self.ws.close()
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        time.sleep(0.2)
        shutil.rmtree(self.profile, ignore_errors=True)


STAGE_CSS = """
.md-header, .md-tabs, .md-sidebar, .md-footer, .md-banner, .md-top, .md-source-file,
.md-content__button, .md-dialog, .md-consent { display: none !important; }
.md-main__inner.md-grid { max-width: none !important; margin: 0 !important; }
.md-content { max-width: none !important; margin: 0 !important; }
.md-content__inner { margin: 80px !important; padding: 0 !important; }
html, body, .md-main { background: %(page)s !important; }
*, *::before, *::after { caret-color: transparent !important; }
"""

CARD_CSS = """
body > *:not(#opulse-card) { display: none !important; }
html, body { margin: 0; background: #0a0f1e !important; }
#opulse-card { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; overflow: hidden;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: radial-gradient(ellipse 70% 60% at 50% 38%, #18265a 0%, #0d1430 48%, #0a0f1e 100%);
  color: #e6ecff; font-family: Inter, "Noto Sans CJK SC", sans-serif; text-align: center; }
#opulse-card .logo { width: 150px; height: 150px; filter: drop-shadow(0 0 36px rgba(34, 211, 238, .35)); }
#opulse-card .name { margin: 22px 0 0; font-size: 112px; font-weight: 800; letter-spacing: -.02em; line-height: 1.1;
  background: linear-gradient(100deg, #22d3ee 0%, #818cf8 50%, #e879f9 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
#opulse-card .rule { width: 140px; height: 3px; margin: 44px 0; border-radius: 2px;
  background: linear-gradient(100deg, #22d3ee, #818cf8, #e879f9); opacity: .8; }
#opulse-card .en { font-size: 50px; font-weight: 500; line-height: 1.45; color: #eef2ff; }
#opulse-card .zh { margin-top: 30px; font-family: "Noto Serif CJK SC", serif; font-size: 40px;
  line-height: 1.6; letter-spacing: .12em; color: #aab6dc; }
#opulse-card .url { font-family: "JetBrains Mono", monospace; font-size: 52px; font-weight: 500;
  color: #67e8f9; letter-spacing: .01em; }
"""

LIGHT_CARD_CSS = """
html, body { background: #f5f7fb !important; }
#opulse-card { background: radial-gradient(ellipse 70% 60% at 50% 38%, #ffffff 0%, #f8fafc 70%, #eef2f8 100%); color: #0f172a; }
#opulse-card .logo { filter: drop-shadow(0 10px 18px rgba(15, 23, 42, .10)); }
#opulse-card .name { background: linear-gradient(100deg, #0e7490 0%, #4f46e5 50%, #a21caf 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent; }
#opulse-card .rule { background: linear-gradient(100deg, #0e7490, #4f46e5, #a21caf); }
#opulse-card .en { color: #0f172a; }
#opulse-card .zh { color: #475569; }
#opulse-card .url { color: #0e7490; }
"""


def js_string(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def element_script(selector: str, body: str) -> str:
    return "(() => { const el = document.querySelector(" + js_string(selector) + "); " + (
        "if (!el) throw new Error('Missing selector: ' + " + js_string(selector) + "); " + body + " })()")


def wait_until(chrome: Chrome, expression: str, what: str, timeout: float = 20) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if chrome.js(expression):
            return
        time.sleep(0.1)
    raise CDPError(f"Timed out waiting for {what}")


def settle(chrome: Chrome, seconds: float = 0.25) -> None:
    """Wait for fonts and two animation frames (headless Chrome may skip them), then pause."""
    chrome.js("document.fonts.ready.then(() => Promise.race([new Promise(r => requestAnimationFrame(() => "
              "requestAnimationFrame(() => r(true)))), new Promise(r => setTimeout(() => r(true), 400))]))")
    time.sleep(seconds)


def stage(chrome: Chrome, plan: dict, scene: dict, theme: str = "light") -> None:
    """Hide the site chrome, give the element its scene width and hide the listed parts."""
    css = STAGE_CSS % {"page": plan["stage"][theme]["page"]}
    for selector in scene.get("hide", []):
        css += f"{scene['selector']} {selector} {{ display: none !important; }}\n"
    css += scene.get("css", "")
    chrome.js("(() => { const s = document.createElement('style'); s.id = 'opulse-video-stage'; "
              "s.textContent = " + js_string(css) + "; document.head.appendChild(s); return true; })()")
    if "index" in scene:
        chrome.js("(() => { const el = document.querySelectorAll(" + js_string(scene["match"]) + ")["
                  + str(int(scene["index"])) + "]; if (!el) throw new Error('Missing indexed element'); "
                  "el.id = 'opulse-video-target'; return true; })()")
    # Hide the page content above the widget so it sits near the top of the viewport and the
    # screenshot never needs to reach beyond it.
    chrome.js(element_script(scene["selector"], "let a = el; while (a.parentElement && "
              "!a.parentElement.classList.contains('md-content__inner')) a = a.parentElement; "
              "for (let p = a.previousElementSibling; p; p = p.previousElementSibling) p.style.display = 'none'; "
              "window.scrollTo(0, 0); return true;"))
    if scene.get("width"):
        chrome.js(element_script(scene["selector"], f"el.style.width = '{int(scene['width'])}px'; "
                  "el.style.maxWidth = 'none'; el.style.margin = '0'; return true;"))
    settle(chrome, 0.6)


def capture(chrome: Chrome, selector: str, max_height: float | None = None, pad: float = 0) -> bytes:
    """Screenshot an element that is fully inside the unscrolled viewport."""
    if chrome.js("scrollX !== 0 || scrollY !== 0"):
        chrome.js("window.scrollTo({left: 0, top: 0, behavior: 'instant'}); true")
        settle(chrome, 0.1)
    box = chrome.js(element_script(selector, "const r = el.getBoundingClientRect(); "
        "return {x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height, "
        "scrollX, scrollY, viewportWidth: innerWidth, viewportHeight: innerHeight};"))
    if not box or box["width"] < 1 or box["height"] < 1:
        raise CDPError(f"Empty capture area: {selector}")
    if box["scrollX"] or box["scrollY"]:
        raise CDPError(f"Page scrolled during capture of {selector}: "
                       f"({box['scrollX']}, {box['scrollY']})")
    height = (min(box["height"], max_height) if max_height else box["height"]) + 2 * pad
    clip = {"x": box["x"] - pad, "y": box["y"] - pad, "width": box["width"] + 2 * pad, "height": height, "scale": 1}
    if (clip["x"] < 0 or clip["x"] + clip["width"] > box["viewportWidth"] or
            clip["y"] < 0 or clip["y"] + clip["height"] > box["viewportHeight"]):
        raise CDPError(f"{selector} is outside the viewport; adjust scene CSS or capture.viewport: {clip}")
    data = chrome.call("Page.captureScreenshot", {"format": "png", "clip": clip,
        "captureBeyondViewport": False, "fromSurface": True})["data"]
    return base64.b64decode(data)


def scene_url(plan: dict, scene: dict, query: str = "") -> str:
    url = urljoin(plan["site"].rstrip("/") + "/", scene["path"].lstrip("/"))
    return url + (("&" if "?" in url else "?") + query if query else "")


def check_theme(chrome: Chrome, theme: str) -> None:
    expected = "slate" if theme == "dark" else "default"
    actual = chrome.js("document.body.getAttribute('data-md-color-scheme')")
    if actual != expected:
        raise CDPError(f"Expected Material scheme {expected!r}, got {actual!r}")


def set_palette(chrome: Chrome, plan: dict, theme: str) -> None:
    """Store Material's palette at the site root before recording any page."""
    chrome.navigate(plan["site"].rstrip("/") + "/")
    # mkdocs.yml lists the light palette first and the dark one second, without media queries.
    index, scheme = (1, "slate") if theme == "dark" else (0, "default")
    palette = {"index": index, "color": {"scheme": scheme, "primary": "custom", "accent": "custom"}}
    chrome.js("__md_set('__palette', " + js_string(palette) + "); true")


def open_scene(chrome: Chrome, plan: dict, scene: dict, query: str = "",
               theme: str = "light") -> None:
    url = scene_url(plan, scene, query)
    current = chrome.js("location.href")
    old, new = urlparse(current), urlparse(url)
    if old.fragment != new.fragment and old._replace(fragment="") == new._replace(fragment=""):
        chrome.navigate("about:blank")
    chrome.navigate(url)
    check_theme(chrome, theme)
    wait_until(chrome, "Boolean(document.querySelector(" + js_string(scene.get("wait", scene["selector"])) + "))",
               scene.get("wait", scene["selector"]))
    stage(chrome, plan, scene, theme)
    check_theme(chrome, theme)


def record_card(chrome: Chrome, plan: dict, scene: dict, theme: str = "light") -> list[bytes]:
    card = scene["card"]
    parts = ['<img class="logo" src="' + urljoin(plan["site"].rstrip("/") + "/", "assets/images/logo.svg") + '" alt="">',
             '<div class="name">Opulse</div>', '<div class="rule"></div>']
    for key in ("en", "zh", "url"):
        if card.get(key):
            lines = "<br>".join(html_escape(line) for line in card[key].split("\n"))
            parts.append(f'<div class="{key}">{lines}</div>')
    chrome.navigate(urljoin(plan["site"].rstrip("/") + "/", ""))
    check_theme(chrome, theme)
    card_css = CARD_CSS + (LIGHT_CARD_CSS if theme == "light" else "")
    chrome.js("(() => { const s = document.createElement('style'); s.textContent = " + js_string(card_css) + "; "
              "document.head.appendChild(s); const d = document.createElement('div'); d.id = 'opulse-card'; "
              "d.innerHTML = " + js_string("".join(parts)) + "; document.body.appendChild(d); "
              "window.scrollTo(0, 0); return true; })()")
    wait_until(chrome, "document.querySelector('#opulse-card img').complete", "card logo")
    settle(chrome, 0.8)
    check_theme(chrome, theme)
    return [capture(chrome, "#opulse-card")]


def html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def measure(chrome: Chrome, scene: dict) -> dict:
    """Boxes of the scene's focus selectors, in CSS pixels relative to the element."""
    focus = dict(scene.get("focus", {}))
    script = ("(() => { const root = document.querySelector(" + js_string(scene["selector"]) + "); "
              "const o = root.getBoundingClientRect(); const out = {full: [0, 0, o.width, o.height]}; "
              "const focus = " + js_string(focus) + "; "
              "for (const [name, sel] of Object.entries(focus)) { let a = Infinity, b = Infinity, c = -Infinity, d = -Infinity; "
              "root.querySelectorAll(sel).forEach(e => { const r = e.getBoundingClientRect(); "
              "if (r.width < 1 || r.height < 1) return; a = Math.min(a, r.left); b = Math.min(b, r.top); "
              "c = Math.max(c, r.right); d = Math.max(d, r.bottom); }); "
              "out[name] = isFinite(a) ? [a - o.left, b - o.top, c - a, d - b] : null; } return out; })()")
    return chrome.js(script)


def set_range(chrome: Chrome, selector: str, value: int) -> None:
    chrome.js(element_script(selector, f"el.value = Math.min(Number(el.max), {int(value)}); "
        "el.dispatchEvent(new Event('input', {bubbles: true})); "
        "el.dispatchEvent(new Event('change', {bubbles: true})); return true;"))


def sequence_wait_expression(root: str, wait: str) -> str:
    """Build a wait condition from a root-relative selector or JavaScript expression."""
    expression = wait[3:].strip() if wait.startswith("js:") else wait.strip()
    if wait.startswith("js:") or expression.startswith(("document.", "window.", "Boolean(", "(()")):
        if not expression:
            raise CDPError("Empty sequence JavaScript wait expression")
        return f"Boolean({expression})"
    return ("Boolean(document.querySelector(" + js_string(root) + ")?.querySelector("
            + js_string(wait) + "))")


def record_states(chrome: Chrome, plan: dict, scene: dict,
                  theme: str = "light") -> tuple[list[bytes], list[dict]]:
    spec = scene["states"]
    root = scene["selector"]
    images, boxes = [], []
    pad = scene.get("pad", 0)

    def shot() -> None:
        images.append(capture(chrome, root, pad=pad))
        boxes.append(measure(chrome, scene))

    if "query" in spec:
        # One page load per frame, using the widget's own URL frame control.
        for value in range(int(spec["from"]), int(spec["to"]) + 1):
            open_scene(chrome, plan, scene, f"{spec['query']}={value}", theme)
            if spec.get("ready"):
                wait_until(chrome, spec["ready"].replace("{value}", str(value)), f"{scene['id']} frame {value}")
            settle(chrome)
            shot()
        return images, boxes
    open_scene(chrome, plan, scene, theme=theme)
    if "sequence" in spec:
        for index, action in enumerate(spec["sequence"]):
            if action.get("click"):
                chrome.js(element_script(root, "const target = el.querySelector(" + js_string(action["click"])
                    + "); if (!target) throw new Error('Missing sequence click target: ' + "
                    + js_string(action["click"]) + "); if (typeof target.click === 'function') target.click(); else target.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window})); return true;"))
            if action.get("wait"):
                wait_until(chrome, sequence_wait_expression(root, action["wait"]),
                           f"{scene['id']} sequence item {index} wait")
            settle(chrome, float(action.get("settle", 0.3)))
            if action.get("capture", True):
                shot()
        return images, boxes
    if spec.get("click"):
        chrome.js(element_script(f"{root} {spec['click']}", "el.click(); return true;"))
        settle(chrome, 0.4)
    if "range" in spec:
        target = f"{root} {spec['range']}"
        last = spec["to"] if spec["to"] != "max" else int(chrome.js(element_script(target, "return Number(el.max);")))
        for value in range(int(spec["from"]), int(last) + 1):
            set_range(chrome, target, value)
            settle(chrome, 0.15)
            shot()
    else:
        shot()
    return images, boxes


def record(storyboard: Path, output: Path, scene_ids: list[str] | None = None,
           chrome_binary: str = "/usr/bin/google-chrome", theme: str = "light") -> Path:
    plan = yaml.safe_load(storyboard.read_text())
    wanted = [s for s in plan["scenes"] if (s["id"] in scene_ids if scene_ids else s.get("enabled", True))]
    if scene_ids and len(wanted) != len(set(scene_ids)):
        raise CDPError("Requested scene is absent from the storyboard")
    output.mkdir(parents=True, exist_ok=True)
    chrome = Chrome(chrome_binary, tuple(plan["capture"]["viewport"]), plan["capture"]["scale"], theme)
    try:
        set_palette(chrome, plan, theme)
        for scene in wanted:
            kind = scene.get("kind", "states")
            if kind == "card":
                images, boxes = record_card(chrome, plan, scene, theme), [{}]
            else:
                images, boxes = record_states(chrome, plan, scene, theme)
            folder = output / theme / scene["id"]
            folder.mkdir(parents=True, exist_ok=True)
            for old in folder.glob("*.png"):
                old.unlink()
            for index, data in enumerate(images):
                (folder / f"{index:03d}.png").write_bytes(data)
            (folder / "boxes.json").write_text(json.dumps({"pad": scene.get("pad", 0),
                "scale": plan["capture"]["scale"], "states": boxes}, indent=1) + "\n")
            print(f"Recorded {scene['id']}: {len(images)} image(s)")
    finally:
        chrome.close()
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storyboard", type=Path, default=Path(__file__).with_name("storyboard.yaml"))
    parser.add_argument("--output", type=Path, default=Path("tools/video/output/frames"))
    parser.add_argument("--scene", action="append", dest="scenes")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    parser.add_argument("--theme", choices=("light", "dark"), default="light")
    args = parser.parse_args()
    print(record(args.storyboard, args.output, args.scenes, args.chrome, args.theme))


if __name__ == "__main__":
    main()
