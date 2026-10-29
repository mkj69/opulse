"""Render the Opulse social card and favicon PNGs from the current SVG logo."""

from __future__ import annotations

import base64
from pathlib import Path
import subprocess
import tempfile
import sys

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "docs/assets/images"
LOGO = IMAGES / "logo.svg"
CHROME = "/usr/bin/google-chrome"
FONT = Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf")
RENDER_SIZE = 768


def render_logo() -> Image.Image:
    """Rasterize the SVG, keeping transparency for icons and the card."""
    try:
        import cairosvg
    except ImportError:
        cairosvg = None

    if cairosvg is not None:
        with tempfile.TemporaryDirectory() as directory:
            raster = Path(directory) / "logo.png"
            cairosvg.svg2png(url=str(LOGO), write_to=str(raster), output_width=RENDER_SIZE, output_height=RENDER_SIZE)
            with Image.open(raster) as captured:
                return captured.convert("RGBA")

    encoded = base64.b64encode(LOGO.read_bytes()).decode("ascii")
    html = (
        '<!doctype html><html><head><style>html,body{margin:0;background:transparent}'
        f'img{{display:block;width:{RENDER_SIZE}px;height:{RENDER_SIZE}px}}'
        '</style></head><body>'
        f'<img src="data:image/svg+xml;base64,{encoded}"></body></html>'
    )
    with tempfile.TemporaryDirectory() as directory:
        page = Path(directory) / "logo.html"
        screenshot = Path(directory) / "logo.png"
        page.write_text(html, encoding="utf-8")
        try:
            subprocess.run(
                [
                    CHROME,
                    "--headless=new",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--hide-scrollbars",
                    "--default-background-color=00000000",
                    "--window-size=1024,1024",
                    "--virtual-time-budget=1000",
                    f"--screenshot={screenshot}",
                    page.as_uri(),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as error:
            # Chrome can be blocked by container seccomp. librsvg is available
            # through the system Python's GdkPixbuf SVG loader in that case.
            print(f"Chrome SVG render failed ({error.returncode}); using GdkPixbuf", file=sys.stderr)
            subprocess.run(
                [
                    "/usr/bin/python3",
                    "-c",
                    "import gi, sys; gi.require_version('GdkPixbuf', '2.0'); "
                    "from gi.repository import GdkPixbuf; "
                    "image = GdkPixbuf.Pixbuf.new_from_file_at_scale(sys.argv[1], 768, 768, True); "
                    "image.savev(sys.argv[2], 'png', [], [])",
                    str(LOGO),
                    str(screenshot),
                ],
                check=True,
            )
        with Image.open(screenshot) as captured:
            if captured.width < RENDER_SIZE or captured.height < RENDER_SIZE:
                raise RuntimeError(f"Chrome screenshot is too small: {captured.size}")
            logo = captured.crop((0, 0, RENDER_SIZE, RENDER_SIZE)).convert("RGBA")
    if logo.getpixel((0, 0))[3] != 0:
        raise RuntimeError("Chrome did not preserve the transparent logo background")
    return logo


def make_icons(logo: Image.Image) -> None:
    for name, size in (
        ("favicon-32.png", 32),
        ("favicon-192.png", 192),
        ("apple-touch-icon.png", 180),
    ):
        # An indigo disk gives the pale glass edges contrast on light browser tabs.
        canvas = Image.new("RGBA", (size * 4, size * 4), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        inset = size * 4 // 32
        draw.ellipse(
            (inset, inset, size * 4 - inset - 1, size * 4 - inset - 1),
            fill=(22, 28, 62, 255),
        )
        artwork = logo.resize(canvas.size, Image.Resampling.LANCZOS)
        canvas.alpha_composite(artwork)
        canvas.resize((size, size), Image.Resampling.LANCZOS).save(IMAGES / name)


def make_social_card(logo: Image.Image) -> None:
    width, height = 1200, 630
    card = Image.new("RGB", (width, height))
    pixels = card.load()
    for x in range(width):
        t = x / (width - 1)
        base = (int(27 * (1 - t) + 9 * t), int(34 * (1 - t) + 12 * t), int(73 * (1 - t) + 31 * t))
        for y in range(height):
            glow = max(0.0, 1.0 - ((x - 285) / 330) ** 2 - ((y - 320) / 300) ** 2)
            pixels[x, y] = tuple(min(255, value + int(glow * lift)) for value, lift in zip(base, (7, 8, 20)))

    artwork = logo.resize((360, 360), Image.Resampling.LANCZOS)
    card.paste(artwork, (90, 125), artwork)
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle((500, 199, 631, 207), radius=4, fill="#22d3ee")
    draw.text((495, 226), "Opulse", font=ImageFont.truetype(str(FONT), 96), fill="#f5f7ff")
    message_font = ImageFont.truetype(str(FONT), 31)
    lines = (
        "Finite atoms, endless concepts.",
        "Every step of reasoning, in plain sight.",
    )
    for y, line in zip((375, 423), lines):
        if draw.textbbox((0, 0), line, font=message_font)[2] > width - 500 - 35:
            raise RuntimeError(f"Social card line is too wide: {line}")
        draw.text((500, y), line, font=message_font, fill="#cbd7f3")
    card.save(IMAGES / "social/opulse-preview.png", optimize=True)


if __name__ == "__main__":
    rendered_logo = render_logo()
    make_icons(rendered_logo)
    make_social_card(rendered_logo)
