#!/usr/bin/env python3
"""
build_animated_banner.py

Wires the intro reveal, the drift-band loop, and the logo-morph
travellers into the VISUAL.MAP panel, replacing build_banner.py's
static portrait with the full animated one. Chrome (titlebar) and the
SYSTEM.INFO panel are unchanged and imported from build_banner.py so
the two builders can never drift apart on layout.

Two independent dot layers occupy the same panel (see dither.py /
build_groups.py docstrings for *why* each needs its own copy of the
portrait rather than sharing one):

  Layer A -- intro (60 random groups)
      Plays once, [0, ~3.2s]: each group fades in (fill="freeze") on
      its own staggered <animate>, then the whole layer just sits at
      full opacity forever after -- there is no loop-time behaviour to
      wire up for it.

  Layer B -- drift-band loop (94 noise-clustered bands)
      Base opacity 0 (invisible) until its own animations, all sharing
      begin="{INTRO_DUR}s", take over: full opacity/no drift through
      the portrait hold, drifts ~42% toward the react logo's centroid
      while fading out through transition 1, sits hidden through the
      whole logo cycle, then reverses through transition 4 to land
      back at "full opacity, no drift" exactly as dur="14.2s" wraps --
      so the loop and the layer handoff are seamless every repeat.

  Travellers (900 dots, one <path>, "d" itself animated)
      Hidden through the portrait hold + transition 1, fades in already
      sitting at the react shape, holds, morphs to the glyph, holds,
      morphs to the rebel emblem, holds, then fades out (still at the
      rebel shape) through transition 4 -- handing back to Layer B.
      One <animate attributeName="d"> covering all 900 dots at once
      (browsers interpolate same-structure path strings numerically)
      is dramatically cheaper than 900 individually-animated elements.
"""

from pathlib import Path

import numpy as np

import build_banner
from build_banner import (
    FONT, W, H, LEFT_X, LEFT_W, GRID_W, GRID_H,
    build_titlebar, build_info_panel, portrait_draw_box, set_theme,
)
from svg_dots import grid_to_path_d, points_to_path_d

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "assets" / "data"
OUT_DIR = REPO_ROOT / "assets" / "svg"

INTRO_DUR = 3.2
INTRO_FADE_WINDOW = 2.0
INTRO_GROUP_FADE = 0.6
N_INTRO_GROUPS = 60

LOOP_DUR = 14.2
T = dict(t0=0.0, t1=3.0, t2=4.3, t3=6.3, t4=7.6, t5=9.6, t6=10.9, t7=12.9, t8=14.2)
KT = {k: round(v / LOOP_DUR, 5) for k, v in T.items()}

DRIFT_FRACTION = 0.42
TRAVELLER_DOT_SIZE_FRAC = 0.011  # fraction of panel draw_w, tuned to roughly match portrait dot size


def group_grid_from_ids(dark_grid: np.ndarray, ids: np.ndarray, target_id: int) -> np.ndarray:
    """ids is aligned to np.nonzero(dark_grid)'s deterministic order
    (row-major) -- the same order build_dots.py/build_groups.py used
    when they produced the point list this id array describes."""
    out = np.zeros_like(dark_grid)
    ys, xs = np.nonzero(dark_grid)
    sel = ids == target_id
    out[ys[sel], xs[sel]] = True
    return out


def build_intro_layer(dark_grid: np.ndarray, groups: np.ndarray, box: dict, color: str) -> str:
    """Each group fades in once and freezes -- but the *layer as a
    whole* also fades back out, once, right as Layer B's loop takes
    over at begin="{INTRO_DUR}s". Without that outer fade, this layer
    would sit at opacity 1 forever (that's what "freeze" means) behind
    everything else, permanently showing the undrifted full portrait
    and silently defeating every fade/drift Layer B ever does -- the
    two layers are only supposed to overlap for the single instant of
    the handoff, where they're guaranteed to look identical anyway."""
    parts = []
    for g in range(N_INTRO_GROUPS):
        gmask = group_grid_from_ids(dark_grid, groups, g)
        if not gmask.any():
            continue
        d = grid_to_path_d(gmask, box["draw_x"], box["draw_y"], box["cell_w"], box["cell_h"], pad=0.25)
        begin = g * (INTRO_FADE_WINDOW / N_INTRO_GROUPS)
        parts.append(
            f'<g opacity="0"><animate attributeName="opacity" from="0" to="1" '
            f'begin="{begin:.3f}s" dur="{INTRO_GROUP_FADE}s" fill="freeze"/>'
            f'<path d="{d}" fill="{color}" shape-rendering="crispEdges"/></g>'
        )
    return (
        f'<g><animate attributeName="opacity" from="1" to="0" '
        f'begin="{INTRO_DUR}s" dur="0.01s" fill="freeze"/>'
        f'{"".join(parts)}</g>'
    )


def build_drift_loop_layer(dark_grid: np.ndarray, bands: np.ndarray, box: dict, color: str,
                            pts_px: np.ndarray, logo1_centroid_frac: np.ndarray) -> str:
    draw_x, draw_y, draw_w, draw_h = box["draw_x"], box["draw_y"], box["draw_w"], box["draw_h"]
    logo1_px = (logo1_centroid_frac[0] * draw_w, logo1_centroid_frac[1] * draw_h)

    key_times_str = f'{KT["t0"]};{KT["t1"]};{KT["t2"]};{KT["t7"]};{KT["t8"]}'
    opacity_values = "1;1;0;0;1"

    parts = []
    unique_bands = np.unique(bands)
    for b in unique_bands:
        bmask = group_grid_from_ids(dark_grid, bands, b)
        if not bmask.any():
            continue
        d = grid_to_path_d(bmask, draw_x, draw_y, box["cell_w"], box["cell_h"], pad=0.25)

        sel = bands == b
        band_centroid_grid = pts_px[sel].mean(axis=0)  # pixel-grid units (GRID_W x GRID_H)
        band_centroid_px = (band_centroid_grid[0] / GRID_W * draw_w, band_centroid_grid[1] / GRID_H * draw_h)
        dx = DRIFT_FRACTION * (logo1_px[0] - band_centroid_px[0])
        dy = DRIFT_FRACTION * (logo1_px[1] - band_centroid_px[1])

        translate_values = f'0,0;0,0;{dx:.2f},{dy:.2f};{dx:.2f},{dy:.2f};0,0'
        parts.append(
            f'<g opacity="0">'
            f'<animateTransform attributeName="transform" type="translate" '
            f'values="{translate_values}" keyTimes="{key_times_str}" '
            f'begin="{INTRO_DUR}s" dur="{LOOP_DUR}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="{opacity_values}" keyTimes="{key_times_str}" '
            f'begin="{INTRO_DUR}s" dur="{LOOP_DUR}s" repeatCount="indefinite"/>'
            f'<path d="{d}" fill="{color}" shape-rendering="crispEdges"/>'
            f'</g>'
        )
    return f'<g>{"".join(parts)}</g>'


def build_travellers_layer(box: dict, color: str) -> str:
    travellers = np.load(DATA_DIR / "travellers.npy")  # (900, 3, 2) fractional [0,1]
    draw_x, draw_y, draw_w, draw_h = box["draw_x"], box["draw_y"], box["draw_w"], box["draw_h"]
    dot_size = TRAVELLER_DOT_SIZE_FRAC * draw_w

    d_states = []
    for i in range(3):
        d = points_to_path_d(travellers[:, i, :], draw_x, draw_y, draw_w, draw_h, dot_size)
        d_states.append(d)
    d_react, d_glyph, d_rebel = d_states

    d_key_times = f'{KT["t0"]};{KT["t1"]};{KT["t2"]};{KT["t3"]};{KT["t4"]};{KT["t5"]};{KT["t6"]};{KT["t7"]};{KT["t8"]}'
    d_values = ";".join([d_react, d_react, d_react, d_react, d_glyph, d_glyph, d_rebel, d_rebel, d_rebel])

    op_key_times = f'{KT["t0"]};{KT["t1"]};{KT["t2"]};{KT["t7"]};{KT["t8"]}'
    op_values = "0;0;1;1;0"

    return (
        f'<path d="{d_react}" fill="{color}" shape-rendering="crispEdges" opacity="0">'
        f'<animate attributeName="d" values="{d_values}" keyTimes="{d_key_times}" '
        f'begin="{INTRO_DUR}s" dur="{LOOP_DUR}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="{op_values}" keyTimes="{op_key_times}" '
        f'begin="{INTRO_DUR}s" dur="{LOOP_DUR}s" repeatCount="indefinite"/>'
        f'</path>'
    )


def build_animated_portrait_panel(theme: str):
    color = build_banner.PALETTE["portrait"]
    dark_grid = np.load(DATA_DIR / f"portrait_{theme}_grid.npy")
    pts_frac = np.load(DATA_DIR / f"portrait_{theme}.npy")
    pts_px = pts_frac * [GRID_W, GRID_H]
    intro_groups = np.load(DATA_DIR / f"intro_groups_{theme}.npy")
    drift_bands = np.load(DATA_DIR / f"drift_bands_{theme}.npy")
    logo1_centroid = np.load(DATA_DIR / "logo1_centroid.npy")

    box = portrait_draw_box()

    label = (
        f'<text x="{LEFT_X}" y="{box["frame_y"] - 10}" font-size="13" letter-spacing=".14em" '
        f'font-family="{FONT}" fill="{build_banner.PALETTE["chrome"]}" opacity=".75">VISUAL.MAP</text>'
    )
    frame_border = (
        f'<rect x="{LEFT_X}" y="{box["frame_y"]}" width="{box["frame_w"]}" height="{box["frame_h"]}" rx="6" '
        f'fill="{build_banner.PALETTE["bg"]}" stroke="{build_banner.PALETTE["chrome"]}" stroke-opacity=".3" stroke-width="1.2"/>'
    )
    clip = (
        f'<clipPath id="portraitClip-{theme}">'
        f'<rect x="{LEFT_X}" y="{box["frame_y"]}" width="{box["frame_w"]}" height="{box["frame_h"]}" rx="6"/>'
        f'</clipPath>'
    )

    layer_a = build_intro_layer(dark_grid, intro_groups, box, color)
    layer_b = build_drift_loop_layer(dark_grid, drift_bands, box, color, pts_px, logo1_centroid)
    # same hue as the portrait: the logo shapes are the same "dot matter"
    # continuing on, not a different UI element wandering into the panel
    travellers = build_travellers_layer(box, color)

    clipped = f'<g clip-path="url(#portraitClip-{theme})">{layer_a}{layer_b}{travellers}</g>'
    return clip + label + frame_border + clipped


def build_svg(theme: str):
    portrait_svg = build_animated_portrait_panel(theme)
    info_svg = build_info_panel()

    svg = (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="Tomas Posada — animated developer profile banner">'
        f'<title>TomasPosada0626 — profile.sh --live</title>'
        f'<rect width="{W}" height="{H}" fill="{build_banner.PALETTE["bg"]}"/>'
        f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="10" fill="none" '
        f'stroke="{build_banner.PALETTE["chrome"]}" stroke-opacity=".35" stroke-width="1.4"/>'
        f'{build_titlebar()}'
        f'{portrait_svg}'
        f'{info_svg}'
        f'</svg>'
    )
    return svg


def main():
    for theme in ("dark", "light"):
        set_theme(theme)
        svg = build_svg(theme)
        out_path = OUT_DIR / f"banner-{theme}.svg"
        out_path.write_text(svg, encoding="utf-8")
        print(f"wrote {out_path}  ({len(svg.encode('utf-8')):,} bytes)")


if __name__ == "__main__":
    main()
