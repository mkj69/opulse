"""Draw the static figures of the blog post (docs/blog/index.md and docs_zh/blog/index.md).

    python tools/blog_figures.py

Every figure comes in a desktop layout and a stacked phone layout, each in a light and a dark
colour scheme, under docs/assets/blog/:

    figN.svg, figN-dark.svg        desktop, viewBox 940 wide (the width of the text column)
    figN-m.svg, figN-m-dark.svg    phone, viewBox 360 wide

The page shows the desktop pair above 600px and the phone pair below it
(docs/assets/css/blogfig.css), and picks the colour scheme with Material's `#only-light` and
`#only-dark` suffixes. Because both viewBoxes match the column they are shown in, one unit is
close to one CSS pixel, so the type sizes below are the rendered sizes: 13.5px body, 14.5px
titles, 12px secondary labels on desktop.

Figure 3 is the step checker widget, rebuilt by tools/blog_visuals.py. The counts in Figure 4
(3, 19 and 39 lines; 13 rewrites that unfold ◆₂; six rewrites for one application of ◆₁) are the
reference derivations of the opening question, the task that tools/blog_visuals.py rebuilds.
All labels are English on both language pages.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets" / "blog"
SANS = "'Helvetica Neue', Helvetica, Arial, 'DejaVu Sans', sans-serif"
MONO = "'JetBrains Mono', Menlo, Consolas, 'DejaVu Sans Mono', monospace"

THEMES = {
    "light": {"fg": "#0f172a", "muted": "#475569", "line": "#94a3b8", "edge": "#d5dbe3",
              "panel": "#f8fafc", "card": "#ffffff", "cyan": "#0e7490", "amber": "#b45309",
              "magenta": "#a21caf", "accent": "#4f46e5", "tint": 0.09},
    "dark": {"fg": "#e5e7eb", "muted": "#a3adbf", "line": "#64748b", "edge": "#2b3656",
             "panel": "#10172e", "card": "#0d1328", "cyan": "#22d3ee", "amber": "#fbbf24",
             "magenta": "#e879f9", "accent": "#818cf8", "tint": 0.13},
}


@dataclass(frozen=True)
class Style:
    width: int      # viewBox width
    title: float    # panel titles
    body: float     # body labels
    small: float    # secondary labels
    mono: float     # code
    pad: float = 14
    gap: float = 12
    radius: float = 8
    stroke: float = 1
    lead: float = 1.38


DESKTOP = Style(width=940, title=14.5, body=13.5, small=12, mono=13)
PHONE = Style(width=360, title=15, body=14, small=12.5, mono=13.5)


def width_of(text: str, size: float, mono: bool = False, bold: bool = False) -> float:
    """Width estimate for Helvetica or Arial, with a small margin."""
    if mono:
        return len(text) * size * 0.61
    per = 0.57 if bold else 0.53
    narrow = sum(1 for ch in text if ch in "iljtfr .,:;'()|1")
    return (len(text) - narrow) * size * per + narrow * size * 0.33


def wrap(text: str, max_width: float, size: float, bold: bool = False) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if line and width_of(trial, size, bold=bold) > max_width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


class G:
    """A group of drawing commands with its own origin."""

    def __init__(self, theme: str, st: Style) -> None:
        self.c = THEMES[theme]
        self.theme = theme
        self.st = st
        self.parts: list[str] = []

    # ------------------------------------------------------------------ primitives
    def rect(self, x, y, w, h, stroke=None, fill=None, rx=None, width=None, dash=None, opacity=None):
        rx = self.st.radius if rx is None else rx
        width = self.st.stroke if width is None else width
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        extra += f' fill-opacity="{opacity}"' if opacity is not None else ""
        self.parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" '
            f'fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{width}"{extra}/>')

    def text(self, x, y, s, size=None, color=None, weight=400, anchor="start", mono=False):
        size = size or self.st.body
        family = MONO if mono else SANS
        self.parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color or self.c["fg"]}" text-anchor="{anchor}">'
            f'{escape(s)}</text>')

    def lines(self, x, y, rows, size=None, **kw) -> float:
        """Draw rows with the first baseline at y; return the y of the last baseline."""
        size = size or self.st.body
        step = size * self.st.lead
        for k, row in enumerate(rows):
            self.text(x, y + k * step, row, size=size, **kw)
        return y + (len(rows) - 1) * step

    def block_height(self, n_rows: int, size: float) -> float:
        return size * 0.75 + (n_rows - 1) * size * self.st.lead

    def line(self, x1, y1, x2, y2, color=None, width=None, dash=None):
        width = self.st.stroke if width is None else width
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                          f'stroke="{color or self.c["line"]}" stroke-width="{width}"{extra}/>')

    def path(self, d, color=None, width=1.4):
        self.parts.append(f'<path d="{d}" fill="none" stroke="{color or self.c["line"]}" '
                          f'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>')

    def arrow(self, x1, y1, x2, y2, color=None):
        color = color or self.c["muted"]
        self.line(x1, y1, x2, y2, color, 1.25)
        ang = math.atan2(y2 - y1, x2 - x1)
        head = 6
        pts = [(x2, y2)] + [(x2 + head * math.cos(ang + d), y2 + head * math.sin(ang + d))
                            for d in (math.radians(150), math.radians(-150))]
        self.parts.append('<polygon points="' + " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
                          + f'" fill="{color}"/>')

    def circle(self, x, y, r, stroke=None, fill=None, width=None, dash=None):
        width = self.st.stroke if width is None else width
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill or "none"}" '
                          f'stroke="{stroke or "none"}" stroke-width="{width}"{extra}/>')

    def tinted(self, x, y, w, h, color):
        self.rect(x, y, w, h, fill=color, width=0, opacity=self.c["tint"])
        self.rect(x, y, w, h, stroke=color, width=1.25)

    def box(self, x, y, w, h):
        self.rect(x, y, w, h, stroke=self.c["edge"], fill=self.c["card"])

    def place(self, other: G, x: float, y: float) -> None:
        self.parts.append(f'<g transform="translate({x:.1f},{y:.1f})">')
        self.parts.extend(other.parts)
        self.parts.append("</g>")

    def save(self, path: Path, height: float, label: str) -> None:
        w = self.st.width
        path.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-1 -1 {w + 2} {height + 2:.0f}" '
            f'width="{w + 2}" height="{height + 2:.0f}" role="img" aria-label="{escape(label)}">\n'
            f"<title>{escape(label)}</title>\n" + "\n".join(self.parts) + "\n</svg>\n",
            encoding="utf-8")


# ---------------------------------------------------------------------- panels
# A panel is a title plus content drawn by a function (g, width) -> content height. The frame is
# drawn by the layout, so panels in one row can share a height.

def panel_title(g: G, title: str, number: int | None, color=None) -> float:
    st, c = g.st, g.c
    x = st.pad
    base = st.pad + st.title * 0.78
    if number is not None:
        r = st.title * 0.62
        g.circle(st.pad + r, base - st.title * 0.36, r, fill=c["fg"], width=0)
        g.text(st.pad + r, base - st.title * 0.36 + st.small * 0.36, str(number), size=st.small,
               weight=700, color=c["panel"], anchor="middle")
        x += 2 * r + 7
    g.text(x, base, title, size=st.title, weight=700, color=color or c["fg"])
    return st.pad + st.title + 10


def make_panel(theme, st, w, title, number, content, color=None, strong=False):
    g = G(theme, st)
    top = panel_title(g, title, number, color) if title else st.pad
    inner = G(theme, st)
    h = content(inner, w - 2 * st.pad)
    return {"g": g, "inner": inner, "top": top, "h": top + h + st.pad, "w": w, "strong": strong}


def draw_panel(dst: G, p: dict, x: float, y: float, h: float | None = None) -> None:
    c = dst.c
    h = h or p["h"]
    if p["strong"]:
        dst.rect(x, y, p["w"], h, stroke=c["fg"], fill=c["card"], width=1.5)
    else:
        dst.rect(x, y, p["w"], h, stroke=c["edge"], fill=c["panel"])
    dst.place(p["g"], x, y)
    dst.place(p["inner"], x + dst.st.pad, y + p["top"])


def row_layout(dst: G, panels: list[dict], y: float, gap: float, arrows: bool) -> float:
    h = max(p["h"] for p in panels)
    x = 0.0
    for k, p in enumerate(panels):
        draw_panel(dst, p, x, y, h)
        x += p["w"]
        if k < len(panels) - 1:
            if arrows:
                dst.arrow(x + 4, y + h / 2, x + gap - 4, y + h / 2)
            x += gap
    return y + h


def column_layout(dst: G, panels: list[dict], y: float, gap: float, arrows: bool) -> float:
    for k, p in enumerate(panels):
        draw_panel(dst, p, 0, y)
        y += p["h"]
        if k < len(panels) - 1:
            if arrows:
                mid = dst.st.width / 2
                dst.arrow(mid, y + 3, mid, y + gap - 3)
            y += gap
    return y


def bullets(g: G, w: float, items: list[str], marker: str, color: str) -> float:
    st = g.st
    y = st.body * 0.8
    for k, item in enumerate(items):
        rows = wrap(item, w - 16, st.body)
        if marker == "square":
            g.rect(0, y - st.body * 0.62, 7, 7, fill=color, rx=1.5, width=0)
        else:
            g.circle(3.5, y - st.body * 0.33, 3.5, fill=color, width=0)
        y = g.lines(16, y, rows)
        if k < len(items) - 1:
            y += st.body * st.lead + 5
    return y + st.body * 0.3


# ====================================================================== Figure 1
def fig1(theme: str, st: Style) -> tuple[G, float]:
    c = THEMES[theme]
    phone = st is PHONE

    def atoms(g: G, w: float) -> float:
        size, gap = 26, 6
        cols = max(1, int((w + gap) // (size + gap)))
        for k, a in enumerate(["+", "-", "*", "/", "%", "@", "#", "$", "&"]):
            x, y = (k % cols) * (size + gap), (k // cols) * (size + gap)
            g.rect(x, y, size, size, stroke=c["line"], fill=c["card"], rx=5)
            g.text(x + size / 2, y + size * 0.68, a, size=st.mono, mono=True, anchor="middle", weight=700)
        rows = math.ceil(9 / cols)
        y = rows * (size + gap) + st.small
        end = g.lines(0, y, wrap("chosen by the user; any integer function can join", w, st.small),
                      size=st.small, color=c["muted"])
        return end + 4

    def combine(g: G, w: float) -> float:
        forms = [("cyan", "Substitution", "passes one result into another"),
                 ("amber", "Conditional choice", "takes the first case that holds"),
                 ("magenta", "Bounded recursion", "calls itself on a smaller value")]
        y = 0.0
        for k, (col, name, desc) in enumerate(forms):
            d = wrap(desc, w - 20, st.small)
            h = 10 + st.body + 4 + g.block_height(len(d), st.small) + 9
            g.tinted(0, y, w, h, c[col])
            g.text(10, y + 8 + st.body * 0.8, name, size=st.body, weight=700, color=c[col])
            g.lines(10, y + 12 + st.body + st.small * 0.8, d, size=st.small)
            y += h + (8 if k < 2 else 0)
        return y

    def layers(g: G, w: float) -> float:
        lab = 52
        gw = w - lab - 6
        rows = [("layer 1", ["magenta", "cyan", "amber"]),
                ("layer 0", ["amber", "cyan", "amber", "cyan"]),
                ("atoms", ["line"] * 6)]
        pos = {}
        for r, (label, cols) in enumerate(rows):
            y = 12 + r * 44
            g.text(0, y + st.small * 0.35, label, size=st.small, color=c["muted"])
            n = len(cols)
            for k in range(n):
                pos[(r, k)] = (lab + 6 + gw * (k + 0.5) / 6 + (6 - n) * gw / 12, y)
        edges = [((0, 0), (1, 0)), ((0, 0), (1, 1)), ((0, 1), (1, 2)), ((0, 1), (0, 0)),
                 ((0, 2), (1, 3)), ((0, 2), (1, 1)), ((1, 0), (2, 0)), ((1, 0), (2, 1)),
                 ((1, 1), (2, 2)), ((1, 1), (2, 1)), ((1, 2), (2, 3)), ((1, 2), (2, 4)),
                 ((1, 3), (2, 5)), ((1, 3), (1, 2))]
        for a, b in edges:
            g.line(*pos[a], *pos[b], c["line"], 1)
        for r, (label, cols) in enumerate(rows):
            for k, col in enumerate(cols):
                x, y = pos[(r, k)]
                if col == "line":
                    g.circle(x, y, 5.5, stroke=c["line"], fill=c["card"], width=1.25)
                else:
                    g.circle(x, y, 8, stroke=c[col], fill=c["card"], width=2)
        y = 12 + 2 * 44 + 26
        g.circle(5, y - 4, 5.5, stroke=c["line"], width=1.25, dash="2.5 2")
        g.line(2, y - 7, 8, y - 1, c["muted"], 1.25)
        g.line(2, y - 1, 8, y - 7, c["muted"], 1.25)
        end = g.lines(16, y, wrap("a draft that fails a check is discarded", w - 16, st.small),
                      size=st.small, color=c["muted"])
        y = end + st.small * st.lead + 2
        g.circle(5, y - 4, 5.5, stroke=c["magenta"], width=2)
        end = g.lines(16, y, wrap("recursion starts a new layer", w - 16, st.small), size=st.small,
                      color=c["magenta"])
        return end + 4

    def referee(g: G, w: float) -> float:
        rows = wrap("computes the exact value of every expression and checks every step before "
                    "anything is written", w, st.body)
        return g.lines(0, st.body * 0.8, rows) + 4

    def outputs(g: G, w: float) -> float:
        names = ["Tasks", "Step grading", "Rewards", "Corpora"]
        cols = 2 if phone else 1
        bw = (w - (cols - 1) * 8) / cols
        bh = 28
        for k, n in enumerate(names):
            x, y = (k % cols) * (bw + 8), (k // cols) * (bh + 7)
            g.rect(x, y, bw, bh, stroke=c["line"], fill=c["card"], rx=6)
            g.text(x + bw / 2, y + bh / 2 + st.body * 0.35, n, size=st.body, anchor="middle")
        rows = math.ceil(len(names) / cols)
        return rows * bh + (rows - 1) * 7

    specs = [("Atoms", atoms, 132), ("Combine", combine, 214), ("Grow in layers", layers, 238),
             ("Referee", referee, 152), ("Outputs", outputs, 124)]
    out = G(theme, st)
    if phone:
        panels = [make_panel(theme, st, st.width, t, k + 1, f, strong=(k == 3))
                  for k, (t, f, _) in enumerate(specs)]
        return out, column_layout(out, panels, 0, 20, True)
    gap = (st.width - sum(w for *_, w in specs)) / 4
    panels = [make_panel(theme, st, w, t, k + 1, f, strong=(k == 3)) for k, (t, f, w) in enumerate(specs)]
    return out, row_layout(out, panels, 0, gap, True)


# ====================================================================== Figure 2
def fig2(theme: str, st: Style) -> tuple[G, float]:
    c = THEMES[theme]
    phone = st is PHONE

    def change(g: G, w: float) -> float:
        knobs = ["atoms", "composition", "depth", "frequency", "notation", "granularity"]
        cols = 2 if phone else 3
        cw = (w - (cols - 1) * 22) / cols
        for i, k in enumerate(knobs):
            col, row = i % cols, i // cols
            x, y = col * (cw + 22), row * 52
            on = k == "frequency"
            g.text(x, y + st.body * 0.8, k, size=st.body, weight=700 if on else 400,
                   color=c["fg"] if on else c["muted"])
            ty = y + st.body + 16
            g.line(x + 2, ty, x + cw - 4, ty, c["line"], 3)
            rest = x + 2 + (cw - 6) * 0.35
            if on:
                hx = x + 2 + (cw - 6) * 0.8
                g.line(x + 2, ty, hx, ty, c["accent"], 3)
                g.circle(rest, ty, 4, stroke=c["accent"], fill=c["panel"], width=1, dash="2 1.5")
                g.circle(hx, ty, 7, stroke=c["accent"], fill=c["accent"], width=1.25)
            else:
                g.circle(rest, ty, 7, stroke=c["line"], fill=c["card"], width=1.25)
        rows = math.ceil(len(knobs) / cols)
        return rows * 52 - 14

    fixed = ["the other five options", "one semantics, one interpreter", "the token budget",
             "evaluation tasks, frozen in advance", "operator and training seeds, repeated"]
    meas = ["accuracy on fresh Opulse libraries", "accuracy on external tasks",
            "the first wrong step", "probes and patches against reference values"]

    def audit(g: G, w: float) -> float:
        text = ("Every task records its features, so a sample can be checked for side effects of "
                "the change.")
        return g.lines(0, st.body * 0.8, wrap(text, w, st.body)) + 4

    out = G(theme, st)
    if phone:
        W = st.width
        p1 = make_panel(theme, st, W, "Change one option", None, change, c["accent"])
        p2 = make_panel(theme, st, W, "Hold fixed", None,
                        lambda g, w: bullets(g, w, fixed, "square", c["muted"]))
        p3 = make_panel(theme, st, W, "Measure", None,
                        lambda g, w: bullets(g, w, meas, "dot", c["accent"]), c["accent"])
        y = column_layout(out, [p1, p2, p3], 0, 20, True)
    else:
        widths = [400, 238, 238]
        gap = (st.width - sum(widths)) / 2
        p1 = make_panel(theme, st, widths[0], "Change one option", None, change, c["accent"])
        p2 = make_panel(theme, st, widths[1], "Hold fixed", None,
                        lambda g, w: bullets(g, w, fixed, "square", c["muted"]))
        p3 = make_panel(theme, st, widths[2], "Measure", None,
                        lambda g, w: bullets(g, w, meas, "dot", c["accent"]), c["accent"])
        y = row_layout(out, [p1, p2, p3], 0, gap, True)
    y += st.gap
    pa = make_panel(theme, st, st.width, "Audit", None, audit, c["accent"])
    out.rect(0, y, st.width, pa["h"], stroke=c["accent"], fill=c["card"], dash="5 4")
    out.place(pa["g"], 0, y)
    out.place(pa["inner"], st.pad, y + pa["top"])
    return out, y + pa["h"]


# ====================================================================== Figure 4
def brace_down(g: G, x1: float, x2: float, y: float, tip: float, color: str, depth: float = 16):
    """A horizontal curly bracket under a source box: tip at (tip, y), arms at y + depth."""
    r = 6
    m = y + depth / 2
    g.path(f"M {x1} {y + depth} Q {x1} {m} {x1 + r} {m} L {tip - r} {m} Q {tip} {m} {tip} {y} "
           f"Q {tip} {m} {tip + r} {m} L {x2 - r} {m} Q {x2} {m} {x2} {y + depth}", color, 1.5)


def brace_right(g: G, x: float, y1: float, y2: float, tip: float, color: str):
    """A vertical curly bracket opening to the right, its tip pointing left at (x - 8, tip)."""
    r = 6
    g.path(f"M {x + 10} {y1} Q {x} {y1} {x} {y1 + r} L {x} {tip - r} Q {x} {tip} {x - 8} {tip} "
           f"Q {x} {tip} {x} {tip + r} L {x} {y2 - r} Q {x} {y2} {x + 10} {y2}", color, 1.5)


ATOM_STEPS = ["unfold ◆₁", "50 + 50 ⇒ 100", "100 $ ⇒ 3", "& 5 ⇒ 5", "# 5 ⇒ 15", "3 * 15 ⇒ 45"]
CALLS = ["◆₁ 50 ⇒ 45", "◆₁ 45 ⇒ 60", "◆₁ 60 ⇒ 60", "◆₁ 60 ⇒ 60"]


def fig4(theme: str, st: Style) -> tuple[G, float]:
    c = THEMES[theme]
    g = G(theme, st)
    bh = 32
    if st is PHONE:
        colx, colw = [2, 106, 226], [82, 100, 128]
        heads = [("◆₂ known", "3 lines"), ("◆₁ known", "19 lines"), ("atoms only", "39 lines")]
        for x, w, (h, sub) in zip(colx, colw, heads):
            g.text(x + w / 2, st.body, h, size=st.body, weight=700, anchor="middle")
            g.text(x + w / 2, st.body + st.small * 1.5, sub, size=st.small, anchor="middle",
                   color=c["muted"])
        y2 = 56
        boxes, y = [], y2
        for k, t in enumerate(["unfold ◆₂", *CALLS]):
            col = "magenta" if k == 0 else "cyan"
            g.tinted(colx[1], y, colw[1], bh, c[col])
            g.text(colx[1] + 8, y + bh / 2 + st.mono * 0.35, t, size=st.mono, mono=True)
            boxes.append(y)
            y += bh + 8
        b_bot = y - 8
        g.text(colx[1] + colw[1] / 2, b_bot + 20, "13 + 4 = 17", size=st.small, anchor="middle",
               color=c["muted"])
        y1 = (y2 + b_bot) / 2 - 24
        g.tinted(colx[0], y1, colw[0], 48, c["magenta"])
        g.lines(colx[0] + 8, y1 + 19, ["31 ◆₂ 50", "⇒ 60"], size=st.mono, mono=True, weight=700)
        g.text(colx[0] + colw[0] / 2, y1 + 66, "1 step", size=st.small, anchor="middle",
               color=c["muted"])
        brace_right(g, colx[1] - 9, y2, b_bot, y1 + 24, c["magenta"])
        g.line(colx[0] + colw[0], y1 + 24, colx[1] - 17, y1 + 24, c["magenta"], 1.25)
        y3 = boxes[1] - 16
        for k, t in enumerate(ATOM_STEPS):
            yy = y3 + k * (bh + 8)
            g.rect(colx[2], yy, colw[2], bh, stroke=c["cyan"] if k == 0 else c["line"],
                   fill=c["card"], width=1.25 if k == 0 else 1)
            g.text(colx[2] + 8, yy + bh / 2 + st.mono * 0.35, t, size=st.mono, mono=True)
        a_bot = y3 + 6 * bh + 5 * 8
        src = boxes[1] + bh / 2
        brace_right(g, colx[2] - 9, y3, a_bot, src, c["cyan"])
        g.line(colx[1] + colw[1], src, colx[2] - 17, src, c["cyan"], 1.25)
        g.text(colx[2] + colw[2] / 2, a_bot + 20, "6 steps", size=st.small, anchor="middle",
               color=c["muted"])
        return g, a_bot + 28

    # desktop: three rows, each one granularity, with brackets from a step to its block
    lab, x0 = 0, 168
    rows_y = [0, 92, 184]
    heads = [("◆₂ known", "3 lines in all"), ("◆₁ known", "19 lines in all"),
             ("atoms only", "39 lines in all")]
    for (h, sub), y in zip(heads, rows_y):
        g.text(lab, y + 13, h, size=st.body, weight=700)
        g.text(lab, y + 13 + st.small * 1.45, sub, size=st.small, color=c["muted"])

    def mono_w(t):
        return width_of(t, st.mono, mono=True) + 20

    avail = st.width - x0 - 132  # the step counts sit in the last column

    def widths(labels):
        natural = [mono_w(t) for t in labels]
        extra = (avail - sum(natural) - 10 * (len(labels) - 1)) / len(labels)
        return [w + max(0.0, extra) for w in natural]

    # row 1
    a_w = mono_w("31 ◆₂ 50 ⇒ 60") + 24
    g.tinted(x0, rows_y[0], a_w, bh, c["magenta"])
    g.text(x0 + 12, rows_y[0] + bh / 2 + st.mono * 0.35, "31 ◆₂ 50 ⇒ 60", size=st.mono, mono=True,
           weight=700)
    # row 2
    labels2 = ["unfold ◆₂: 13 steps", *CALLS]
    xs, x = [], x0
    for k, (t, w) in enumerate(zip(labels2, widths(labels2))):
        g.tinted(x, rows_y[1], w, bh, c["magenta" if k == 0 else "cyan"])
        g.text(x + 12, rows_y[1] + bh / 2 + st.mono * 0.35, t, size=st.mono, mono=True)
        xs.append((x, w))
        x += w + 10
    row2_end = x - 10
    # row 3
    x = x0
    for k, (t, w) in enumerate(zip(ATOM_STEPS, widths(ATOM_STEPS))):
        g.rect(x, rows_y[2], w, bh, stroke=c["cyan"] if k == 0 else c["line"], fill=c["card"],
               width=1.25 if k == 0 else 1)
        g.text(x + 12, rows_y[2] + bh / 2 + st.mono * 0.35, t, size=st.mono, mono=True)
        x += w + 10
    row3_end = x - 10
    brace_down(g, x0, row2_end, rows_y[0] + bh + 6, x0 + a_w / 2, c["magenta"], 40)
    src_x = xs[1][0] + xs[1][1] / 2
    brace_down(g, x0, row3_end, rows_y[1] + bh + 6, src_x, c["cyan"], 40)
    nx = st.width - 112
    for y, t in zip(rows_y, ["1 step", "13 + 4 = 17 steps", "6 steps"]):
        g.text(nx, y + bh / 2 + st.small * 0.35, t, size=st.small, color=c["muted"])
    return g, rows_y[2] + bh + 2


# ====================================================================== Figure 5
EXPERIMENTS = [
    ("Evaluate existing models", [
        ("Does an edit reach what was built on it?", "also trains",
         "how far an edit reaches in the dependency graph", "give edits in context or train them in"),
    ]),
    ("Train new models", [
        ("When should a rule live in the weights?", "also evaluates",
         "accuracy against training uses per rule", "train a rule in or supply it in context"),
        ("Should common concepts subsidise rare ones?", None,
         "the value of practice inside dependents", "a frequent core or a minimum per concept"),
        ("How many derivation tokens is an example worth?", None,
         "the depth at which full derivations pay", "how much of each solution to write out"),
    ]),
    ("Observe inside models", [
        ("Can probes be tested against exact values?", None,
         "what probes decode and patches change", "which probes and patches to trust"),
    ]),
]


def fig5(theme: str, st: Style) -> tuple[G, float]:
    c = THEMES[theme]
    g = G(theme, st)
    W = st.width
    banner = "Proposals. None of these has been run."
    g.rect(0, 0, W, 32, stroke=c["fg"], fill="none", dash="5 4")
    g.text(W / 2, 16 + st.body * 0.36, banner, size=st.body, weight=700, anchor="middle")
    y = 44
    if st is PHONE:
        for mode, items in EXPERIMENTS:
            g.text(0, y + st.title * 0.8, mode, size=st.title, weight=700)
            y += st.title + 10
            for q, extra, rev, inf in items:
                inner = W - 2 * st.pad
                tq = wrap(q, inner, st.body, bold=True)
                tr = wrap(rev, inner - 64, st.body)
                ti = wrap(inf, inner - 64, st.body)
                lines_h = (len(tq) + len(tr) + len(ti) + (1 if extra else 0)) * st.body * st.lead
                h = st.pad * 2 + lines_h - st.body * 0.4
                g.rect(0, y, W, h, stroke=c["edge"], fill=c["panel"])
                yy = g.lines(st.pad, y + st.pad + st.body * 0.8, tq, weight=700)
                if extra:
                    yy += st.body * st.lead
                    g.text(st.pad, yy, extra, size=st.small, color=c["muted"])
                yy += st.body * st.lead
                g.text(st.pad, yy, "reveals", size=st.small, weight=700, color=c["accent"])
                yy = g.lines(st.pad + 64, yy, tr) + st.body * st.lead
                g.text(st.pad, yy, "informs", size=st.small, weight=700, color=c["muted"])
                g.lines(st.pad + 64, yy, ti)
                y += h + 8
            y += 8
        return g, y - 16

    # desktop: a table grouped by mode
    cols = [(0, 150, "Mode"), (150, 300, "Question"), (450, 245, "Reveals"), (695, 245, "Informs")]
    for x, w, name in cols:
        g.text(x + (st.pad if x else 0), y + st.small, name.upper(), size=st.small, weight=700,
               color=c["muted"])
    y += st.small + 10
    g.line(0, y, W, y, c["line"], 1)
    for mode, items in EXPERIMENTS:
        gy = y
        for q, extra, rev, inf in items:
            tq = wrap(q, 300 - 2 * st.pad, st.body)
            if extra:
                tq.append(f"({extra})")
            tr = wrap(rev, 245 - 2 * st.pad, st.body)
            ti = wrap(inf, 245 - 2 * st.pad, st.body)
            n = max(len(tq), len(tr), len(ti))
            h = 2 * 10 + g.block_height(n, st.body) + 2
            base = y + 10 + st.body * 0.8
            for k, row in enumerate(tq):
                is_extra = extra and k == len(tq) - 1
                g.text(150 + st.pad, base + k * st.body * st.lead, row, size=st.small if is_extra else st.body,
                       color=c["muted"] if is_extra else c["fg"])
            g.lines(450 + st.pad, base, tr)
            g.lines(695 + st.pad, base, ti)
            y += h
            if (q, extra, rev, inf) != items[-1]:
                g.line(150, y, W, y, c["edge"], 1)
        g.text(0, gy + 10 + st.body * 0.8, mode.split()[0], size=st.body, weight=700)
        g.lines(0, gy + 10 + st.body * 0.8 + st.body * st.lead, [" ".join(mode.split()[1:])],
                size=st.small, color=c["muted"])
        g.line(0, y, W, y, c["line"], 1)
    return g, y + 1


# ====================================================================== Figure 6
LINEAGE = [
    ("Kleene; McCarthy", "1936, 1963", "composition, cases and recursion", "three composition forms"),
    ("Gold; Angluin's L*", "1967, 1987", "learning a language from data or queries",
     "value queries and counterexamples"),
    ("Lenat's AM", "1976", "concepts made by changing small programs",
     "concepts grown from a small grammar"),
    ("Doyle", "1979", "truth maintenance: a reason kept for each belief",
     "edits traced through dependencies"),
    ("Anderson's ACT", "1982", "knowledge compilation", "derivations at any granularity"),
    ("Elman", "1993", "training that starts with simple sentences", "curricula ordered by layer"),
    ("Schmidhuber", "2003", "the Gödel machine, which proves a rewrite useful first",
     "the interpreter as referee"),
    ("bAbI", "2015", "diagnostic tasks, later solved", "fresh seeds and a leakage check"),
]


def fig6(theme: str, st: Style) -> tuple[G, float]:
    c = THEMES[theme]
    g = G(theme, st)
    per_row = 1 if st is PHONE else 4
    cw = (st.width - (per_row - 1) * st.gap) / per_row
    inner = cw - 2 * st.pad

    def card(who, year, idea, feat):
        tw = wrap(who, inner - width_of(year, st.small) - 8, st.body, bold=True)
        ti = wrap(idea, inner, st.small)
        tf = wrap(feat, inner - 16, st.body)
        top_h = g.block_height(len(tw), st.body) + 6 + len(ti) * st.small * st.lead
        bot_h = g.block_height(len(tf), st.body)
        return tw, ti, tf, top_h, bot_h

    cards = [card(*row) for row in LINEAGE]
    y = 0.0
    for r in range(0, len(LINEAGE), per_row):
        chunk = list(range(r, min(r + per_row, len(LINEAGE))))
        top_h = max(cards[k][3] for k in chunk)
        bot_h = max(cards[k][4] for k in chunk)
        h = st.pad + top_h + 12 + bot_h + st.pad
        for j, k in enumerate(chunk):
            year = LINEAGE[k][1]
            tw, ti, tf, _, _ = cards[k]
            x = j * (cw + st.gap)
            g.rect(x, y, cw, h, stroke=c["edge"], fill=c["panel"])
            yy = g.lines(x + st.pad, y + st.pad + st.body * 0.8, tw, weight=700)
            g.text(x + cw - st.pad, y + st.pad + st.body * 0.8, year, size=st.small, anchor="end",
                   color=c["muted"])
            g.lines(x + st.pad, yy + st.small * st.lead + 2, ti, size=st.small, color=c["muted"])
            sep = y + st.pad + top_h + 6
            g.line(x + st.pad, sep, x + cw - st.pad, sep, c["edge"], 1)
            fy = sep + 6 + st.body * 0.8
            g.arrow(x + st.pad, fy - st.body * 0.33, x + st.pad + 10, fy - st.body * 0.33, c["accent"])
            g.lines(x + st.pad + 16, fy, tf, color=c["accent"])
        y += h + st.gap
    return g, y - st.gap


FIGURES = {1: (fig1, ("Overview of Opulse: atoms, three composition forms, layered growth, the "
                      "reference interpreter, and what it produces")),
           2: (fig2, "The laboratory: change one option, hold the rest fixed, measure"),
           4: (fig4, "Granularity: one coarse step equals a block of finer steps, down to atoms"),
           5: (fig5, "Map of the proposed experiments by mode"),
           6: (fig6, "Older ideas and the Opulse feature each one corresponds to")}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    count = 0
    for number, (draw, label) in FIGURES.items():
        for st, layout in ((DESKTOP, ""), (PHONE, "-m")):
            for theme, suffix in (("light", ""), ("dark", "-dark")):
                g, height = draw(theme, st)
                g.save(OUT / f"fig{number}{layout}{suffix}.svg", height + 2, label)
                count += 1
    print(f"wrote {count} files to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
