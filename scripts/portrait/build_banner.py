#!/usr/bin/env python3
"""
build_banner.py -- CHECKPOINT BUILD

Assembles the terminal chrome + VISUAL.MAP portrait panel + SYSTEM.INFO
readout into a single static frame (dark theme only). Deliberately does
NOT yet include: the intro scatter, the 14.2s loop, logo tracing/morph,
or the light theme -- those come once this layout itself is approved,
per the phase-1 "show one thing, react, then continue" plan. The one
animated piece already wired in is the LIVE badge pulse, since it's
self-contained and doesn't interact with the loop timeline to come.

Run from this directory: python3 build_banner.py
"""

from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np

from dither import GRID_W, GRID_H
from svg_dots import grid_to_path_d

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "assets" / "data"
OUT_DIR = REPO_ROOT / "assets" / "svg"

PALETTES = {
    # background/panel/live/text have no user-given light variant --
    # the terminal chrome stays visually a "terminal" in both themes,
    # only the tones the spec actually gave two values for (portrait,
    # UI chrome) switch. See build_animated_banner.py's theme note for
    # the one deliberate call made beyond the given palette: a light
    # background, since a light.svg with a near-black bg would defeat
    # the point of a theme-aware <picture> swap.
    "dark": {
        "bg": "#0A101F",
        "panel": "#0D1526",
        "portrait": "#A78BFA",
        "chrome": "#22D3EE",
        "accent": "#10B981",
        "live": "#EF4444",
        "text": "#E7ECFB",
    },
    "light": {
        "bg": "#FFFFFF",
        "panel": "#F3F1FC",
        "portrait": "#7C3AED",
        "chrome": "#0891B2",
        "accent": "#10B981",
        "live": "#DC2626",
        "text": "#1E2433",
    },
}

PALETTE = PALETTES["dark"]


def set_theme(theme: str):
    global PALETTE
    PALETTE = PALETTES[theme]
    return PALETTE

FONT = "ui-monospace,Consolas,monospace"

W, H = 1180, 610
TITLEBAR_H = 34
OUTER_MARGIN = 24
PANEL_Y = TITLEBAR_H + 16
PANEL_H = H - PANEL_Y - 16
BODY_W = W - 2 * OUTER_MARGIN
LEFT_X = OUTER_MARGIN
LEFT_W = round(0.38 * BODY_W)
PANEL_GAP = 28
RIGHT_X = LEFT_X + LEFT_W + PANEL_GAP
RIGHT_W = W - OUTER_MARGIN - RIGHT_X

ROW_FONT = 14
HEADER_FONT = 13
LIVE_FONT = 12
PILL_FONT = 14
ROW_SPACING = 23


def char_w(font_size: float) -> float:
    # advance width used for BOTH the textLength lock and the leader-gap
    # math, so the two stay consistent regardless of what the actual
    # font's real glyph metrics are -- see the textLength note below.
    return font_size * 0.6


ROWS = [
    ("Subject", "Tomas Posada"),
    ("Role", "Full-Stack Developer"),
    ("Origin", "Medellín, Colombia"),
    ("Education", "Ingeniería de Sistemas · EAFIT"),
    ("Status", "Building + Learning + Shipping"),
    ("ToolChain", "VS Code · Git · Docker · Claude Code"),
    ("Core.Lang", "TypeScript · JavaScript · Python · Java · SQL"),
    ("Core.Frontend", "React · Next.js · HTML · CSS"),
    ("Core.Backend", "Node.js · Express · NestJS"),
    ("Core.Database", "PostgreSQL · MongoDB"),
    ("Core.Infra", "Docker · AWS · Linux · CI/CD"),
    ("Grid.Mail", "tposadas1@eafit.edu.co"),
    ("Grid.Portfolio", "coming soon"),
    ("Grid.LinkedIn", "linkedin.com/in/tomasposadasuarez26"),
    ("Grid.GitHub", "github.com/TomasPosada0626"),
    ("Grid.Instagram", "instagram.com/tomas_posada26"),
]


def build_titlebar():
    dots = "".join(
        f'<circle cx="{LEFT_X + 10 + i * 18}" cy="{TITLEBAR_H / 2}" r="5.5" fill="{c}"/>'
        for i, c in enumerate(("#FF5F56", "#FFBD2E", "#27C93F"))
    )
    title = (
        f'<text x="{W / 2}" y="{TITLEBAR_H / 2 + 4.5}" text-anchor="middle" font-size="12.5" '
        f'font-family="{FONT}" fill="{PALETTE["chrome"]}" opacity=".85">profile.sh --live</text>'
    )
    return (
        f'<rect x="0" y="0" width="{W}" height="{TITLEBAR_H}" fill="{PALETTE["panel"]}"/>'
        f'<line x1="0" y1="{TITLEBAR_H}" x2="{W}" y2="{TITLEBAR_H}" stroke="{PALETTE["chrome"]}" stroke-opacity=".25"/>'
        f'{dots}{title}'
    )


def portrait_draw_box():
    """Geometry of the VISUAL.MAP portrait panel, shared by the static
    and animated banner builders so they can never drift apart: panel
    frame rect, and the (draw_x, draw_y, draw_w, draw_h, cell_w, cell_h)
    that place the GRID_W x GRID_H dot grid centred and aspect-correct
    inside it."""
    label_h = 22
    frame_y = PANEL_Y + label_h
    frame_h = PANEL_H - label_h
    frame_w = LEFT_W

    inner_pad = 10
    avail_w = frame_w - 2 * inner_pad
    avail_h = frame_h - 2 * inner_pad
    aspect = GRID_W / GRID_H
    if avail_w / aspect <= avail_h:
        draw_w, draw_h = avail_w, avail_w / aspect
    else:
        draw_h, draw_w = avail_h, avail_h * aspect
    draw_x = LEFT_X + (frame_w - draw_w) / 2
    draw_y = frame_y + (frame_h - draw_h) / 2
    cell_w = draw_w / GRID_W
    cell_h = draw_h / GRID_H
    return {
        "frame_y": frame_y, "frame_h": frame_h, "frame_w": frame_w,
        "draw_x": draw_x, "draw_y": draw_y, "draw_w": draw_w, "draw_h": draw_h,
        "cell_w": cell_w, "cell_h": cell_h,
    }


def build_portrait_panel(dark_grid: np.ndarray):
    box = portrait_draw_box()
    frame_y, frame_h, frame_w = box["frame_y"], box["frame_h"], box["frame_w"]

    label = (
        f'<text x="{LEFT_X}" y="{PANEL_Y + 12}" font-size="{HEADER_FONT}" letter-spacing=".14em" '
        f'font-family="{FONT}" fill="{PALETTE["chrome"]}" opacity=".75">VISUAL.MAP</text>'
    )

    path_d = grid_to_path_d(dark_grid, box["draw_x"], box["draw_y"], box["cell_w"], box["cell_h"], pad=0.25)

    frame_border = (
        f'<rect x="{LEFT_X}" y="{frame_y}" width="{frame_w}" height="{frame_h}" rx="6" '
        f'fill="{PALETTE["bg"]}" stroke="{PALETTE["chrome"]}" stroke-opacity=".3" stroke-width="1.2"/>'
    )
    dots = f'<path d="{path_d}" fill="{PALETTE["portrait"]}" shape-rendering="crispEdges"/>'
    return label + frame_border + dots, len(path_d)


def build_live_badge(x_right: float, y_center: float):
    label = "LIVE"
    text_w = len(label) * char_w(LIVE_FONT) + (len(label) - 1) * (LIVE_FONT * 0.12)
    dot_cx = x_right - text_w - 12
    return (
        f'<g>'
        f'<circle cx="{dot_cx:.1f}" cy="{y_center}" r="4" fill="{PALETTE["live"]}">'
        f'<animate attributeName="opacity" values="1;.35;1" dur="1.8s" repeatCount="indefinite"/>'
        f'</circle>'
        f'<text x="{x_right}" y="{y_center + 4}" text-anchor="end" font-size="{LIVE_FONT}" letter-spacing=".12em" '
        f'font-family="{FONT}" fill="{PALETTE["live"]}" font-weight="600" textLength="{text_w:.1f}" '
        f'lengthAdjust="spacingAndGlyphs">{label}</text>'
        f'</g>'
    )


def build_handle_pill(x: float, y_center: float, handle: str):
    w = len(handle) * char_w(PILL_FONT) + 22
    h = 22
    return (
        f'<g>'
        f'<rect x="{x}" y="{y_center - h / 2}" width="{w:.1f}" height="{h}" rx="{h / 2}" '
        f'fill="{PALETTE["accent"]}" fill-opacity=".16" stroke="{PALETTE["accent"]}" stroke-opacity=".55"/>'
        f'<text x="{x + w / 2:.1f}" y="{y_center + 4.5}" text-anchor="middle" font-size="{PILL_FONT}" '
        f'font-family="{FONT}" fill="{PALETTE["accent"]}">{escape(handle)}</text>'
        f'</g>'
    )


def build_row(y_baseline: float, label: str, value: str):
    label_x = RIGHT_X + 4
    value_end_x = RIGHT_X + RIGHT_W - 4
    lw = len(label) * char_w(ROW_FONT)
    vw = len(value) * char_w(ROW_FONT)

    label_svg = (
        f'<text x="{label_x:.1f}" y="{y_baseline:.1f}" font-size="{ROW_FONT}" font-family="{FONT}" '
        f'fill="{PALETTE["chrome"]}" opacity=".7" textLength="{lw:.1f}" lengthAdjust="spacingAndGlyphs">'
        f'{escape(label)}</text>'
    )
    value_svg = (
        f'<text x="{value_end_x:.1f}" y="{y_baseline:.1f}" text-anchor="end" font-size="{ROW_FONT}" '
        f'font-family="{FONT}" fill="{PALETTE["text"]}" textLength="{vw:.1f}" lengthAdjust="spacingAndGlyphs">'
        f'{escape(value)}</text>'
    )

    leader_start = label_x + lw + 6
    leader_end = value_end_x - vw - 6
    leader_svg = ""
    if leader_end > leader_start:
        pitch = 6.0
        size = 1.6
        n = int((leader_end - leader_start) // pitch) + 1
        cy = y_baseline - ROW_FONT * 0.32
        parts = []
        for i in range(n):
            cx = leader_start + i * pitch
            if cx > leader_end:
                break
            parts.append(f"M{cx:.2f},{cy:.2f}h{size:.2f}v{size:.2f}h{-size:.2f}z")
        leader_svg = f'<path d="{"".join(parts)}" fill="{PALETTE["chrome"]}" opacity=".3" shape-rendering="crispEdges"/>'

    return leader_svg + label_svg + value_svg


def build_info_panel():
    header_content_h = 90
    rows_h = len(ROWS) * ROW_SPACING
    content_h = header_content_h + rows_h
    top_offset = PANEL_Y + (PANEL_H - content_h) / 2

    header_y = top_offset + 14
    header = (
        f'<text x="{RIGHT_X + 4}" y="{header_y:.1f}" font-size="{HEADER_FONT}" letter-spacing=".14em" '
        f'font-family="{FONT}" fill="{PALETTE["chrome"]}" opacity=".85">SYSTEM.INFO</text>'
    )
    live = build_live_badge(RIGHT_X + RIGHT_W - 4, header_y - 4)

    pill_center_y = header_y + 26
    pill = build_handle_pill(RIGHT_X + 4, pill_center_y, "@TomasPosada0626")

    rows_start_y = pill_center_y + 30
    rows_svg = "".join(
        build_row(rows_start_y + i * ROW_SPACING, label, value)
        for i, (label, value) in enumerate(ROWS)
    )

    return header + live + pill + rows_svg


def build_svg(dark_grid: np.ndarray):
    portrait_svg, path_bytes = build_portrait_panel(dark_grid)
    info_svg = build_info_panel()

    svg = (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="Tomas Posada — animated developer profile banner">'
        f'<title>TomasPosada0626 — profile.sh --live</title>'
        f'<rect width="{W}" height="{H}" fill="{PALETTE["bg"]}"/>'
        f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="10" fill="none" '
        f'stroke="{PALETTE["chrome"]}" stroke-opacity=".35" stroke-width="1.4"/>'
        f'{build_titlebar()}'
        f'{portrait_svg}'
        f'{info_svg}'
        f'</svg>'
    )
    return svg, path_bytes


def main():
    dark_grid = np.load(DATA_DIR / "portrait_dark_grid.npy")
    svg, path_bytes = build_svg(dark_grid)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "banner-dark.svg"
    out_path.write_text(svg, encoding="utf-8")
    total_bytes = len(svg.encode("utf-8"))
    print(f"wrote {out_path}  ({total_bytes:,} bytes total, portrait path {path_bytes:,} bytes)")


if __name__ == "__main__":
    main()
