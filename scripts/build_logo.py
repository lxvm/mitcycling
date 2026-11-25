#!/usr/bin/env python3
"""Generate a circular cycling-club badge (à la "MIT CYCLING / ROLL TECH")
entirely from parameters -- rings, spokes, hub and *curved* lettering are all
synthesised; nothing is copied from a source SVG.

The defining trick is that the ring text is genuinely **warped** around the
circle, not just rotated:

  * Each glyph outline is pulled from the font and flattened to a polyline.
  * Every edge -- including the dead-straight tops/bottoms of block letters --
    is densified into many short segments, so that after warping a flat edge
    follows the arc instead of cutting across it as a chord.
  * Each point is mapped through a polar warp: horizontal position -> angle
    around the badge, vertical position -> distance from centre. A vertical
    stroke therefore becomes a radial line and the letter is truly deformed to
    hug the curve (what `textPath`/Inkscape "text on path" cannot do).

Everything is driven by the `Config` dataclass below; the most useful knobs are
also exposed as CLI flags (see `--help`). Run with `--plot preview.png` for a
renderer-free preview, or `--render out.png` if cairosvg is installed.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from dataclasses import dataclass, field, replace

from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen

# Bundled with the repo (SIL Open Font License) and resolved relative to this
# script, so the badge builds the same on any machine and from any directory.
ALFA_SLAB = str(Path(__file__).resolve().parent / "fonts" / "AlfaSlabOne-Regular.ttf")


# ============================================================================
# Configuration -- everything about the badge lives here.
# ============================================================================
@dataclass
class Config:
    # -- canvas --------------------------------------------------------------
    size: float = 700.0                     # square viewport, px
    background: str | None = "#ffffff"      # disc colour, or None for transparent

    # One-color mode: set to a single ink colour to render the whole badge in
    # that one colour on a transparent ground. The lettering, ring gap and disc
    # holes become negative space (knockouts) so they stay legible. Overrides
    # all the individual colours below.
    mono: str | None = None

    # -- concentric rings, described by width from the outside in ------------
    border_color: str = "#000000"
    border_width: float = 28.0              # outer black rim
    gap_color: str = "#ffffff"
    gap_width: float = 11.0                 # thin spacer ring
    tire_color: str = "#a31f34"             # coloured band that carries the text
    tire_width: float = 100.0

    # -- hub -----------------------------------------------------------------
    hub_color: str = "#000000"
    hub_outer: float = 30.0                 # hub-shell radius (spokes start here)
    hub_inner: float = 5.0                  # axle hole radius

    # -- spokes --------------------------------------------------------------
    spoke_color: str = "#000000"
    spoke_width: float = 5.0
    spoke_count: int = 20
    spoke_pattern: str = "crossed"          # "radial" | "crossed" | "tangential"
    spoke_cross: int = 2                    # how many holes the rim end is offset
    spoke_phase: float = 0.0                # rotate the whole spoke set, degrees

    # -- valve stem (optional) ----------------------------------------------
    valve: bool = False
    valve_angle: float = 0.0                # 0=right, 90=top, 180=left, 270=bottom
    valve_avoid_spokes: bool = True         # nudge to nearest spoke-free angle
    valve_color: str = "#1a1a1a"
    valve_width: float = 5.0                # stem thickness
    valve_length: float = 26.0              # how far it pokes inward past the rim
    valve_cap: float = 4.5                  # knob radius at the inner tip

    # -- disc brake rotor (optional) ----------------------------------------
    # Sits behind the spokes; sized like a real ~160mm rotor on a 700mm wheel
    # (radius 80 in this 700-unit canvas).
    disc: bool = False
    disc_outer: float = 80.0                # rotor outer radius (160mm diameter)
    disc_track_width: float = 16.0          # braking-surface band width
    disc_color: str = "#9aa0a6"             # rotor (steel) colour
    disc_holes: int = 22                    # cooling holes punched in the track
    disc_hole_radius: float = 4.0
    disc_arms: int = 5                      # spider arms to the mounting ring
    disc_arm_width: float = 9.0
    disc_mount_radius: float = 42.0         # mounting-ring outer radius

    # -- text ----------------------------------------------------------------
    font_path: str = ALFA_SLAB
    top_text: str = "MIT CYCLING"
    bottom_text: str = "ROLL TECH"
    text_color: str = "#ffffff"
    font_size: float = 64.0                 # em height, px
    letter_spacing: float = 8.0             # extra px between glyphs
    flatten_px: float = 2.0                 # max segment length before warping

    # ---- derived radii (computed, not set directly) ------------------------
    @property
    def cx(self) -> float:
        return self.size / 2.0

    @property
    def cy(self) -> float:
        return self.size / 2.0

    @property
    def border_outer(self) -> float:
        return self.size / 2.0

    @property
    def border_inner(self) -> float:
        return self.border_outer - self.border_width

    @property
    def gap_outer(self) -> float:
        return self.border_inner

    @property
    def gap_inner(self) -> float:
        return self.gap_outer - self.gap_width

    @property
    def tire_outer(self) -> float:
        return self.gap_inner

    @property
    def tire_inner(self) -> float:
        return self.tire_outer - self.tire_width

    @property
    def text_band_center(self) -> float:
        return (self.tire_outer + self.tire_inner) / 2.0

    @property
    def rim_radius(self) -> float:
        """Where spokes terminate (inner edge of the tire)."""
        return self.tire_inner


# ============================================================================
# Glyph extraction -- flatten outlines to polylines.
# ============================================================================
class FlattenPen(BasePen):
    """Collect glyph contours as flat polylines (curves subdivided)."""

    def __init__(self, glyph_set, steps: int = 12):
        super().__init__(glyph_set)
        self.contours: list[list[tuple[float, float]]] = []
        self.steps = steps
        self._cur = (0.0, 0.0)

    def _moveTo(self, p):
        self.contours.append([p])
        self._cur = p

    def _lineTo(self, p):
        self.contours[-1].append(p)
        self._cur = p

    def _qCurveToOne(self, p1, p2):
        x0, y0 = self._cur
        for i in range(1, self.steps + 1):
            t = i / self.steps
            mt = 1 - t
            x = mt * mt * x0 + 2 * mt * t * p1[0] + t * t * p2[0]
            y = mt * mt * y0 + 2 * mt * t * p1[1] + t * t * p2[1]
            self.contours[-1].append((x, y))
        self._cur = p2

    def _curveToOne(self, p1, p2, p3):
        x0, y0 = self._cur
        for i in range(1, self.steps + 1):
            t = i / self.steps
            mt = 1 - t
            x = (mt**3 * x0 + 3 * mt*mt*t * p1[0] +
                 3 * mt*t*t * p2[0] + t**3 * p3[0])
            y = (mt**3 * y0 + 3 * mt*mt*t * p1[1] +
                 3 * mt*t*t * p2[1] + t**3 * p3[1])
            self.contours[-1].append((x, y))
        self._cur = p3

    def _closePath(self):
        pass


class Font:
    def __init__(self, path: str):
        self.ttf = TTFont(path)
        self.upm = self.ttf["head"].unitsPerEm
        self.glyph_set = self.ttf.getGlyphSet()
        self.cmap = self.ttf.getBestCmap()
        self.hmtx = self.ttf["hmtx"]
        self.cap_height = self.ttf["OS/2"].sCapHeight

    def glyph(self, ch: str):
        if ord(ch) not in self.cmap:
            return [], self.hmtx[".notdef"][0]
        gname = self.cmap[ord(ch)]
        pen = FlattenPen(self.glyph_set)
        self.glyph_set[gname].draw(pen)
        return pen.contours, self.hmtx[gname][0]


# ============================================================================
# Text layout + warp.
# ============================================================================
def layout(font: Font, text: str, font_size: float, letter_spacing: float):
    """Lay `text` flat along a baseline. Returns (contours_px, total_width_px),
    with x running along the line from 0 and y up (ascenders positive)."""
    scale = font_size / font.upm
    placed: list[list[tuple[float, float]]] = []
    x = 0.0
    items = [font.glyph(ch) for ch in text]
    for i, (contours, advance) in enumerate(items):
        for cont in contours:
            placed.append([(x + px * scale, py * scale) for px, py in cont])
        x += advance * scale
        if i < len(items) - 1:
            x += letter_spacing
    return placed, x


def densify(contour, max_seg: float):
    """Insert points so no segment is longer than `max_seg` -- this is what
    makes straight edges (block-letter tops/bottoms) bend along the arc once
    warped, instead of becoming chords."""
    if len(contour) < 2:
        return list(contour)
    out = [contour[0]]
    pts = contour + [contour[0]]            # close the loop
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dist = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(math.ceil(dist / max_seg)))
        for i in range(1, n + 1):
            t = i / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def warp_point(x, y, total_w, baseline_r, cx, cy, top):
    """Bend flat coord (x along line, y up) onto a circle of radius baseline_r."""
    phi = (x - total_w / 2.0) / baseline_r       # angular offset from centre
    if top:                                       # centred at 12 o'clock
        theta = math.pi / 2.0 - phi
        rho = baseline_r + y                       # ascenders point outward
    else:                                          # centred at 6 o'clock
        theta = -math.pi / 2.0 + phi
        rho = baseline_r - y                       # feet point outward
    return (cx + rho * math.cos(theta), cy - rho * math.sin(theta))


def curved_text(cfg: Config, font: Font, text: str, top: bool):
    """Lay out, densify and warp `text` around the badge."""
    placed, total_w = layout(font, text, cfg.font_size, cfg.letter_spacing)
    half_cap = (font.cap_height * cfg.font_size / font.upm) / 2.0
    baseline_r = (cfg.text_band_center - half_cap if top
                  else cfg.text_band_center + half_cap)
    warped = []
    for cont in placed:
        dense = densify(cont, cfg.flatten_px)
        warped.append([warp_point(x, y, total_w, baseline_r, cfg.cx, cfg.cy, top)
                       for x, y in dense])
    span_deg = math.degrees(total_w / baseline_r)
    return warped, span_deg, baseline_r


# ============================================================================
# Spoke geometry.
# ============================================================================
def spoke_segments(cfg: Config):
    """Return a list of ((x0,y0),(x1,y1)) hub->rim line segments."""
    n = cfg.spoke_count
    if cfg.spoke_pattern == "crossed" and n % 2 != 0:
        n += 1                                     # crossed lacing needs even N
    phase = math.radians(cfg.spoke_phase)
    lean = cfg.spoke_cross * (2 * math.pi / n)     # rim-end angular offset
    segs = []
    for i in range(n):
        a = phase + 2 * math.pi * i / n
        if cfg.spoke_pattern == "radial":
            d = 0.0
        elif cfg.spoke_pattern == "tangential":
            d = lean                               # all lean the same way
        else:                                      # crossed
            d = lean if i % 2 == 0 else -lean
        hub = (cfg.cx + cfg.hub_outer * math.cos(a),
               cfg.cy - cfg.hub_outer * math.sin(a))
        rim = (cfg.cx + cfg.rim_radius * math.cos(a + d),
               cfg.cy - cfg.rim_radius * math.sin(a + d))
        segs.append((hub, rim))
    return segs


# ============================================================================
# Valve stem + disc-brake geometry (shared by the SVG and the preview).
# ============================================================================
def spoke_rim_angles(cfg: Config):
    """Angles (deg, valve convention) where the spokes attach to the rim."""
    cx, cy = cfg.cx, cfg.cy
    angles = []
    for _, (rx, ry) in spoke_segments(cfg):
        angles.append(math.degrees(math.atan2(cy - ry, rx - cx)) % 360.0)
    return sorted(angles)


def resolve_valve_angle(cfg: Config):
    """Place the valve exactly midway between the two spoke rim-attachment
    points that bracket the requested angle."""
    if not cfg.valve_avoid_spokes:
        return cfg.valve_angle
    rim = spoke_rim_angles(cfg)
    if not rim:
        return cfg.valve_angle
    desired = cfg.valve_angle % 360.0
    for i in range(len(rim)):
        lo = rim[i]
        span = (rim[(i + 1) % len(rim)] - lo) % 360.0   # gap width (wraps)
        if (desired - lo) % 360.0 <= span:              # desired falls in gap
            return (lo + span / 2.0) % 360.0
    return cfg.valve_angle


def valve_geometry(cfg: Config):
    """Radial rod with a rim collar and a tip knob, pointing inward."""
    a = math.radians(resolve_valve_angle(cfg))
    ux, uy = math.cos(a), -math.sin(a)
    cx, cy = cfg.cx, cfg.cy
    P = lambda r: (cx + r * ux, cy + r * uy)
    return dict(
        stem=(P(cfg.tire_outer - 2), P(cfg.rim_radius - cfg.valve_length),
              cfg.valve_width),
        collar=(P(cfg.rim_radius + 12), P(cfg.rim_radius - 8),
                cfg.valve_width * 1.85),
        cap=(P(cfg.rim_radius - cfg.valve_length), cfg.valve_cap),
    )


def disc_geometry(cfg: Config):
    """Braking track (with cooling holes) + spider arms + mounting ring."""
    cx, cy = cfg.cx, cfg.cy
    outer = cfg.disc_outer
    track_inner = cfg.disc_outer - cfg.disc_track_width
    hole_r = (outer + track_inner) / 2.0
    holes = [(cx + hole_r * math.cos(2 * math.pi * k / cfg.disc_holes),
              cy - hole_r * math.sin(2 * math.pi * k / cfg.disc_holes),
              cfg.disc_hole_radius)
             for k in range(cfg.disc_holes)]
    phase = math.radians(cfg.spoke_phase)
    arms = []
    for k in range(cfg.disc_arms):
        a = phase + 2 * math.pi * k / cfg.disc_arms
        p = (cx + cfg.disc_mount_radius * math.cos(a),
             cy - cfg.disc_mount_radius * math.sin(a))
        q = (cx + track_inner * math.cos(a), cy - track_inner * math.sin(a))
        arms.append((p, q, cfg.disc_arm_width))
    return dict(outer=outer, track_inner=track_inner, holes=holes, arms=arms,
                mount_outer=cfg.disc_mount_radius, mount_inner=cfg.hub_outer)


# ============================================================================
# SVG emission.
# ============================================================================
def fmt(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".")


def contours_to_path_d(contours) -> str:
    parts = []
    for cont in contours:
        if not cont:
            continue
        x0, y0 = cont[0]
        parts.append(f"M {fmt(x0)},{fmt(y0)}")
        for x, y in cont[1:]:
            parts.append(f"L {fmt(x)},{fmt(y)}")
        parts.append("Z")
    return " ".join(parts)


def circle_subpath(r, cx, cy) -> str:
    return (f"M {fmt(cx - r)},{fmt(cy)} "
            f"a {fmt(r)},{fmt(r)} 0 1 0 {fmt(2 * r)},0 "
            f"a {fmt(r)},{fmt(r)} 0 1 0 {fmt(-2 * r)},0 Z")


def ring_path(outer, inner, color, cx, cy, ident) -> str:
    d = circle_subpath(outer, cx, cy) + " " + circle_subpath(inner, cx, cy)
    return (f'<path id="{ident}" fill-rule="evenodd" '
            f'style="fill:{color};stroke:none" d="{d}" />')


def stroke_line(p, q, width, color, cap="round") -> str:
    return (f'<path d="M {fmt(p[0])},{fmt(p[1])} L {fmt(q[0])},{fmt(q[1])}" '
            f'style="fill:none;stroke:{color};stroke-width:{fmt(width)};'
            f'stroke-linecap:{cap}" />')


def build_valve(cfg: Config) -> str:
    g = valve_geometry(cfg)
    c = cfg.valve_color
    (cap_c, cap_r) = g["cap"]
    return ('  <g id="valve">\n'
            f'    {stroke_line(*g["stem"], c)}\n'
            f'    {stroke_line(*g["collar"], c)}\n'
            f'    <circle cx="{fmt(cap_c[0])}" cy="{fmt(cap_c[1])}" '
            f'r="{fmt(cap_r)}" style="fill:{c};stroke:none" />\n'
            '  </g>')


def build_disc(cfg: Config) -> str:
    g = disc_geometry(cfg)
    c = cfg.disc_color
    cx, cy = cfg.cx, cfg.cy
    # braking track as one even-odd path: outer + inner + holes -> ring w/ holes
    d = circle_subpath(g["outer"], cx, cy) + " " + circle_subpath(g["track_inner"], cx, cy)
    for hx, hy, hr in g["holes"]:
        d += " " + circle_subpath(hr, hx, hy)
    parts = ['  <g id="disc-brake">']
    parts.append("    " + ring_path(g["mount_outer"], g["mount_inner"], c,
                                     cx, cy, "disc-mount"))
    for arm in g["arms"]:
        parts.append("    " + stroke_line(*arm, c, cap="butt"))
    parts.append(f'    <path id="disc-track" fill-rule="evenodd" '
                 f'style="fill:{c};stroke:none" d="{d}" />')
    parts.append("  </g>")
    return "\n".join(parts)


def build_svg(cfg: Config, font: Font):
    if cfg.mono:                            # one ink colour, everything else knocked out
        cfg = replace(cfg, background=None, border_color=cfg.mono,
                      tire_color=cfg.mono, spoke_color=cfg.mono, hub_color=cfg.mono,
                      valve_color=cfg.mono, disc_color=cfg.mono, text_color=cfg.mono)
    cx, cy = cfg.cx, cfg.cy
    top_c, top_span, top_r = curved_text(cfg, font, cfg.top_text, top=True)
    bot_c, bot_span, bot_r = curved_text(cfg, font, cfg.bottom_text, top=False)

    body = [
        f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        f'<svg width="{fmt(cfg.size)}" height="{fmt(cfg.size)}" '
        f'viewBox="0 0 {fmt(cfg.size)} {fmt(cfg.size)}" version="1.1" '
        f'xmlns="http://www.w3.org/2000/svg">',
    ]
    if cfg.background:
        body.append(f'  <circle cx="{fmt(cx)}" cy="{fmt(cy)}" '
                    f'r="{fmt(cfg.size / 2)}" '
                    f'style="fill:{cfg.background};stroke:none" />')

    # disc-brake rotor + valve stem sit at the BACK, behind the spokes
    if cfg.disc:
        body.append(build_disc(cfg))
    if cfg.valve:
        body.append(build_valve(cfg))

    # spokes (in front of the disc/valve, under the rings)
    seg = spoke_segments(cfg)
    d = " ".join(f"M {fmt(a[0])},{fmt(a[1])} L {fmt(b[0])},{fmt(b[1])}"
                 for a, b in seg)
    body.append(f'  <path id="spokes" d="{d}" '
                f'style="fill:none;stroke:{cfg.spoke_color};'
                f'stroke-width:{fmt(cfg.spoke_width)};stroke-linecap:round" />')

    # outer border ring
    body.append("  " + ring_path(cfg.border_outer, cfg.border_inner,
                                  cfg.border_color, cx, cy, "border"))

    if cfg.mono:
        # Tire with the lettering punched out of it (one even-odd path): the
        # annulus, then every glyph contour as a hole. The ring gap is simply
        # left undrawn, so it reads as a transparent paper line.
        d = (circle_subpath(cfg.tire_outer, cx, cy) + " " +
             circle_subpath(cfg.tire_inner, cx, cy) + " " +
             contours_to_path_d(top_c) + " " + contours_to_path_d(bot_c))
        body.append(f'  <path id="tire" fill-rule="evenodd" '
                    f'style="fill:{cfg.tire_color};stroke:none" d="{d}" />')
    else:
        if cfg.gap_width > 0:
            body.append("  " + ring_path(cfg.gap_outer, cfg.gap_inner,
                                          cfg.gap_color, cx, cy, "gap"))
        body.append("  " + ring_path(cfg.tire_outer, cfg.tire_inner,
                                      cfg.tire_color, cx, cy, "tire"))
        body.append(f'  <path id="top-text" fill-rule="evenodd" '
                    f'style="fill:{cfg.text_color};stroke:none" '
                    f'aria-label="{cfg.top_text}" d="{contours_to_path_d(top_c)}" />')
        body.append(f'  <path id="bottom-text" fill-rule="evenodd" '
                    f'style="fill:{cfg.text_color};stroke:none" '
                    f'aria-label="{cfg.bottom_text}" '
                    f'd="{contours_to_path_d(bot_c)}" />')

    # hub (on top)
    body.append("  " + ring_path(cfg.hub_outer, cfg.hub_inner,
                                  cfg.hub_color, cx, cy, "hub"))
    body.append("</svg>")
    body.append("")

    info = dict(top_span=top_span, bot_span=bot_span, top_r=top_r, bot_r=bot_r,
                top_c=top_c, bot_c=bot_c, spokes=seg)
    return "\n".join(body), info


# ============================================================================
# Renderer-free preview (matplotlib), drawn from the SAME computed values.
# ============================================================================
def preview_png(cfg: Config, info, path: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Wedge

    fig, ax = plt.subplots(figsize=(7, 7))
    cx, cy = cfg.cx, cfg.cy

    # In mono mode the page is "paper" and the lettering/holes knock out to it.
    paper = "#f4f1ea"
    page = paper if cfg.mono else "#dddddd"
    if cfg.mono:
        cfg = replace(cfg, background=paper, border_color=cfg.mono,
                      tire_color=cfg.mono, spoke_color=cfg.mono, hub_color=cfg.mono,
                      valve_color=cfg.mono, disc_color=cfg.mono, text_color=paper,
                      gap_color=paper)

    def annulus(outer, inner, color):
        ax.add_patch(Wedge((cx, cy), outer, 0, 360, width=outer - inner,
                           facecolor=color, edgecolor="none"))

    if cfg.background:
        ax.add_patch(plt.Circle((cx, cy), cfg.size / 2, color=cfg.background))
    # disc + valve at the back, behind the spokes
    if cfg.disc:
        g = disc_geometry(cfg)
        annulus(g["mount_outer"], g["mount_inner"], cfg.disc_color)
        for p, q, w in g["arms"]:
            ax.plot([p[0], q[0]], [p[1], q[1]], color=cfg.disc_color,
                    lw=w, solid_capstyle="butt")
        annulus(g["outer"], g["track_inner"], cfg.disc_color)
        for hx, hy, hr in g["holes"]:
            ax.add_patch(plt.Circle((hx, hy), hr, color=cfg.background or "white"))
    if cfg.valve:
        g = valve_geometry(cfg)
        for seg in (g["stem"], g["collar"]):
            p, q, w = seg
            ax.plot([p[0], q[0]], [p[1], q[1]], color=cfg.valve_color,
                    lw=w, solid_capstyle="round")
        (cc, cr) = g["cap"]
        ax.add_patch(plt.Circle(cc, cr, color=cfg.valve_color))
    for a, b in info["spokes"]:
        ax.plot([a[0], b[0]], [a[1], b[1]], color=cfg.spoke_color,
                lw=cfg.spoke_width, solid_capstyle="round")
    annulus(cfg.border_outer, cfg.border_inner, cfg.border_color)
    if cfg.gap_width > 0:
        annulus(cfg.gap_outer, cfg.gap_inner, cfg.gap_color)
    annulus(cfg.tire_outer, cfg.tire_inner, cfg.tire_color)
    for cont in info["top_c"] + info["bot_c"]:
        xs = [p[0] for p in cont] + [cont[0][0]]
        ys = [p[1] for p in cont] + [cont[0][1]]
        ax.fill(xs, ys, color=cfg.text_color, lw=0)
    annulus(cfg.hub_outer, cfg.hub_inner, cfg.hub_color)

    ax.set_xlim(0, cfg.size)
    ax.set_ylim(cfg.size, 0)                       # SVG y-down
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor(page)
    fig.savefig(path, dpi=100, bbox_inches="tight", facecolor=page)
    plt.close(fig)


def render_png(svg_path: str, png_path: str, size: float, dpi: float) -> int | None:
    """Rasterise the SVG to PNG at `dpi` (design is `size`px at 96dpi, so the
    output is size*dpi/96 px square). Returns the pixel size, or None if
    cairosvg is unavailable."""
    try:
        import cairosvg
    except ImportError:
        return None
    px = max(1, round(size * dpi / 96.0))
    cairosvg.svg2png(url=svg_path, write_to=png_path,
                     output_width=px, output_height=px, dpi=dpi)
    try:                                    # stamp the pHYs DPI tag for print
        from PIL import Image
        Image.open(png_path).save(png_path, dpi=(dpi, dpi))
    except Exception:
        pass
    return px


# ============================================================================
# CLI -- exposes a sensible subset of Config.
# ============================================================================
def main():
    cfg = Config()
    p = argparse.ArgumentParser(description="Generate a curved-text cycling badge.")
    p.add_argument("-o", "--out", default="curved_badge.svg")
    p.add_argument("--plot", metavar="PNG", help="renderer-free matplotlib preview")
    p.add_argument("--png", metavar="FILE",
                   help="also write a rasterised PNG (needs cairosvg)")
    p.add_argument("--dpi", type=float, default=96.0,
                   help="PNG resolution: output px = size*dpi/96 (default 96)")
    p.add_argument("--render", metavar="FILE", help=argparse.SUPPRESS)  # alias
    # text
    p.add_argument("--top-text", default=cfg.top_text)
    p.add_argument("--bottom-text", default=cfg.bottom_text)
    p.add_argument("--font", default=cfg.font_path)
    p.add_argument("--font-size", type=float, default=cfg.font_size)
    p.add_argument("--letter-spacing", type=float, default=cfg.letter_spacing)
    p.add_argument("--text-color", default=cfg.text_color)
    # spokes
    p.add_argument("--spoke-count", type=int, default=cfg.spoke_count)
    p.add_argument("--spoke-pattern", default=cfg.spoke_pattern,
                   choices=["radial", "crossed", "tangential"])
    p.add_argument("--spoke-cross", type=int, default=cfg.spoke_cross)
    p.add_argument("--spoke-width", type=float, default=cfg.spoke_width)
    p.add_argument("--spoke-color", default=cfg.spoke_color)
    # rings / colors
    p.add_argument("--tire-color", default=cfg.tire_color)
    p.add_argument("--tire-width", type=float, default=cfg.tire_width)
    p.add_argument("--border-color", default=cfg.border_color)
    p.add_argument("--border-width", type=float, default=cfg.border_width)
    p.add_argument("--background", default=cfg.background,
                   help='disc colour, or "none" for transparent')
    p.add_argument("--mono", metavar="COLOR", default=None,
                   help="render the whole badge in one ink colour (knockouts)")
    # valve stem (optional)
    p.add_argument("--valve", action="store_true", help="add a tube valve stem")
    p.add_argument("--valve-angle", type=float, default=cfg.valve_angle,
                   help="0=right, 90=top, 180=left, 270=bottom")
    p.add_argument("--valve-color", default=cfg.valve_color)
    p.add_argument("--valve-keep-angle", action="store_true",
                   help="don't auto-nudge the valve off spokes")
    # disc brake (optional)
    p.add_argument("--disc", action="store_true", help="add a disc-brake rotor")
    p.add_argument("--disc-color", default=cfg.disc_color)
    p.add_argument("--disc-outer", type=float, default=cfg.disc_outer)
    args = p.parse_args()

    cfg = Config(
        top_text=args.top_text, bottom_text=args.bottom_text,
        font_path=args.font, font_size=args.font_size,
        letter_spacing=args.letter_spacing, text_color=args.text_color,
        spoke_count=args.spoke_count, spoke_pattern=args.spoke_pattern,
        spoke_cross=args.spoke_cross, spoke_width=args.spoke_width,
        spoke_color=args.spoke_color, tire_color=args.tire_color,
        tire_width=args.tire_width, border_color=args.border_color,
        border_width=args.border_width,
        background=None if args.background.lower() == "none" else args.background,
        mono=args.mono,
        valve=args.valve, valve_angle=args.valve_angle,
        valve_color=args.valve_color,
        valve_avoid_spokes=not args.valve_keep_angle,
        disc=args.disc, disc_color=args.disc_color, disc_outer=args.disc_outer,
    )

    font = Font(cfg.font_path)
    svg, info = build_svg(cfg, font)
    with open(args.out, "w") as f:
        f.write(svg)

    print(f"wrote {args.out}")
    print(f"  top    '{cfg.top_text}': span {info['top_span']:.1f} deg")
    print(f"  bottom '{cfg.bottom_text}': span {info['bot_span']:.1f} deg")
    print(f"  spokes: {len(info['spokes'])} ({cfg.spoke_pattern})")
    if cfg.valve:
        print(f"  valve: requested {cfg.valve_angle:.0f} deg -> "
              f"placed {resolve_valve_angle(cfg):.1f} deg")
    if args.plot:
        preview_png(cfg, info, args.plot)
        print(f"wrote {args.plot}")
    png_out = args.png or args.render
    if png_out:
        px = render_png(args.out, png_out, cfg.size, args.dpi)
        if px:
            print(f"wrote {png_out} ({px}x{px} px @ {args.dpi:g} dpi)")
        else:
            print("  (cairosvg not installed; `pip install cairosvg` to enable --png)")


if __name__ == "__main__":
    main()
