"""
svg_dots.py

Turns a boolean GRID_H x GRID_W ink grid into ONE compact <path>, instead
of one <rect>/<circle> per dot. At 16-70k dots a per-element tag ("<rect
x=... y=... width=... height=.../>", ~45-55 bytes) would put a single
static layer past a megabyte on its own; row-wise run-length merging
collapses every horizontal run of adjacent "on" cells into one path
subcommand, so solid regions (a lit cheek, a light-mode shoulder) cost a
handful of bytes per row instead of one chunk per cell, while genuinely
isolated dither dots (hair speckle, background grain) cost the same as
drawing them individually would -- this never loses information, it just
stops paying per-cell overhead for cells that happen to be adjacent.

Emits square cells rather than circles for path simplicity (a <circle>
needs an arc command, a square is two h/v lines). No shape-rendering
hint is set: crispEdges was tried first (sharp squares at native size)
but it disables antialiasing, and GitHub renders this banner scaled
down from its native 1180px canvas to whatever width the README column
actually is -- at that point a single dither grid row can land under
one device pixel, and crispEdges rounds each row's coverage to fully
on or fully off instead of blending it, which beats against the row
frequency and shows up as banding/moire. Antialiasing acts as the
low-pass filter a downscaled fine pattern needs; verified by rendering
this banner at realistic GitHub column widths (~900px) with and
without the hint before removing it.
"""

from dither import GRID_W, GRID_H


def grid_to_path_d(grid, origin_x: float, origin_y: float, cell_w: float, cell_h: float, pad: float = 0.15) -> str:
    """pad: fraction of a cell left as a gap between dots (0 = seamless
    fill, ~0.15-0.3 = visible dot texture even in fully-inked runs)."""
    gap = pad * min(cell_w, cell_h)
    dw, dh = cell_w - gap, cell_h - gap
    parts = []
    h, w = grid.shape
    for y in range(h):
        row = grid[y]
        x = 0
        while x < w:
            if not row[x]:
                x += 1
                continue
            x0 = x
            while x < w and row[x]:
                x += 1
            run_len = x - x0
            px = origin_x + x0 * cell_w + gap / 2
            py = origin_y + y * cell_h + gap / 2
            rw = dw + (run_len - 1) * cell_w
            parts.append(f"M{px:.2f},{py:.2f}h{rw:.2f}v{dh:.2f}h{-rw:.2f}z")
    return "".join(parts)


def points_to_path_d(points_frac, origin_x: float, origin_y: float, panel_w: float, panel_h: float, dot_size: float) -> str:
    """Same square-run primitive, but for an arbitrary (already
    irregular, e.g. drift-band-shifted) point cloud rather than a clean
    grid -- used for logo/traveller dots, where no two points share a
    row/column to run-length merge. One square per point."""
    half = dot_size / 2
    parts = []
    for x, y in points_frac:
        px = origin_x + x * panel_w - half
        py = origin_y + y * panel_h - half
        parts.append(f"M{px:.2f},{py:.2f}h{dot_size:.2f}v{dot_size:.2f}h{-dot_size:.2f}z")
    return "".join(parts)
