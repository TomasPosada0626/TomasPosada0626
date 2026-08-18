"""
dither.py

Shared dithering/segmentation primitives used by build_dots.py. Split out
of that script so build_dots.py stays a thin pipeline description and this
module can be unit-tested / re-run standalone against a crop candidate.

  GRID
      Every dot-art source (the portrait, each traced logo) is rasterized
      onto the same GRID_W x GRID_H cell grid before dithering, so a dot's
      position can always be expressed as a fraction (col/GRID_W,
      row/GRID_H) of the panel -- independent of whatever pixel size the
      banner SVG ends up using.

  SERPENTINE FLOYD-STEINBERG
      Standard FS error weights (7/16, 3/16, 5/16, 1/16), but the scan
      direction alternates every row (boustrophedon) and the two
      forward-diagonal weights (7/16 and 1/16) swap sides with it. Pure
      left-to-right FS on a portrait tends to drag mid-tone error into a
      visible rightward "wind"; serpentine cancels that directional bias.
      Quantization itself (round each pixel to 0 or 255) is direction- and
      mode-independent -- `invert` only controls which of those two levels
      counts as "ink" (a drawn dot), so light-mode ("ink = dark pixels",
      classic halftone) and dark-mode ("ink = bright pixels", a lit
      subject glowing out of a dark panel) share one code path.
"""

import numpy as np
from scipy import ndimage

GRID_W, GRID_H = 300, 340  # calibrated in the original research: ~17k dots is the point where
# more density starts reintroducing moire banding at GitHub's realistic README display width,
# even without shape-rendering=crispEdges -- confirmed by re-testing the 1.5x attempt at 430px


def dither_serpentine(gray: np.ndarray, invert: bool) -> np.ndarray:
    """gray: float64 array, values in [0, 255]. Returns a bool array,
    True where a dot should be drawn."""
    h, w = gray.shape
    buf = gray.astype(np.float64).copy()
    ink = np.zeros((h, w), dtype=bool)
    for y in range(h):
        left_to_right = (y % 2 == 0)
        xs = range(w) if left_to_right else range(w - 1, -1, -1)
        step = 1 if left_to_right else -1
        for x in xs:
            old = buf[y, x]
            new = 255.0 if old >= 128.0 else 0.0
            ink[y, x] = (new == 255.0) if invert else (new == 0.0)
            err = old - new
            for dx, dy, coef in ((step, 0, 7 / 16), (-step, 1, 3 / 16), (0, 1, 5 / 16), (step, 1, 1 / 16)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    buf[ny, nx] += err * coef
    return ink


def clean_mask(fg: np.ndarray) -> np.ndarray:
    """binary_closing -> fill_holes -> keep only the largest connected
    component, so a stray patch of background misclassified as
    foreground (or a hole punched through dark hair) can't survive."""
    fg = ndimage.binary_closing(fg, structure=np.ones((5, 5)), iterations=2)
    fg = ndimage.binary_fill_holes(fg)
    labeled, n = ndimage.label(fg)
    if n == 0:
        return fg
    if n > 1:
        sizes = ndimage.sum(fg, labeled, range(1, n + 1))
        keep = int(np.argmax(sizes)) + 1
        fg = labeled == keep
    return fg


def evenness_metric(points_xy: np.ndarray, groups: np.ndarray, w: int, h: int, n_bins: int = 4) -> float:
    """A portrait's own dot density is wildly non-uniform (dense over
    the face, sparse over hair, zero over a masked-out background) --
    so comparing any group's spatial spread to a *uniform* grid always
    reads as "clumped", whether the grouping is random or not, purely
    because the portrait itself isn't uniform. What actually
    distinguishes "interleaved" from "a wipe" is whether each group's
    per-bin share matches its *overall* share of that bin's dots (a bin
    that's 1/60 group 3 is exactly what 60-way random interleaving
    predicts there, no matter how dense or sparse that bin is).

    So: for each occupied bin, and each group, compare that group's
    actual dot count in the bin to the count *expected* if the group's
    overall share of all dots applied uniformly. Returns the mean
    relative deviation from that expectation across all (bin, group)
    pairs -- ~0 means groups track the portrait's own density evenly
    (interleaved), high means some groups dominate certain bins (a
    wipe or other spatial clustering)."""
    if len(points_xy) == 0:
        return 1.0
    bin_x = np.clip((points_xy[:, 0] / w * n_bins).astype(int), 0, n_bins - 1)
    bin_y = np.clip((points_xy[:, 1] / h * n_bins).astype(int), 0, n_bins - 1)
    cell = bin_y * n_bins + bin_x
    n_cells = n_bins * n_bins
    overall_counts = np.bincount(cell, minlength=n_cells).astype(float)
    total = len(points_xy)
    occupied = overall_counts > 0

    deviations = []
    for g in np.unique(groups):
        sel = cell[groups == g]
        g_total = len(sel)
        if g_total == 0:
            continue
        g_counts = np.bincount(sel, minlength=n_cells).astype(float)
        expected = overall_counts * (g_total / total)
        rel_dev = np.abs(g_counts[occupied] - expected[occupied]) / expected[occupied]
        deviations.append(rel_dev.mean())
    return float(np.mean(deviations)) if deviations else 1.0


def straight_boundary_metric(points_xy: np.ndarray, band_id: np.ndarray) -> float:
    """Fraction of adjacent-column pairs whose band assignment forms a
    perfectly straight vertical boundary -- i.e. how "grid-like" the
    band map looks. Computed by rounding points into a coarse raster,
    then for each pair of horizontally-adjacent cells checking whether
    the band boundary between them sits at the exact same column for
    every row (that's the signature of grouping directly on un-noised
    position). ~0.01 is organic, ~0.17+ means bands recreated a grid."""
    if len(points_xy) < 2:
        return 0.0
    cols = 40
    rows = 40
    x = points_xy[:, 0]
    y = points_xy[:, 1]
    cx = np.clip((x / (x.max() + 1e-6) * (cols - 1)).astype(int), 0, cols - 1)
    cy = np.clip((y / (y.max() + 1e-6) * (rows - 1)).astype(int), 0, rows - 1)
    grid = -np.ones((rows, cols), dtype=int)
    for i in range(len(points_xy)):
        grid[cy[i], cx[i]] = band_id[i]
    straight = 0
    total = 0
    for r in range(rows):
        row = grid[r]
        valid = row >= 0
        if valid.sum() < 2:
            continue
        idx = np.where(valid)[0]
        for a, b in zip(idx[:-1], idx[1:]):
            total += 1
            if row[a] != row[b]:
                # boundary at column b -- check if the same column has a
                # boundary in most other rows too (straight = grid-like)
                same_col_boundaries = 0
                rows_checked = 0
                for r2 in range(rows):
                    if grid[r2, a] >= 0 and grid[r2, b] >= 0:
                        rows_checked += 1
                        if grid[r2, a] != grid[r2, b]:
                            same_col_boundaries += 1
                if rows_checked > 3 and same_col_boundaries / rows_checked > 0.8:
                    straight += 1
    return straight / total if total else 0.0
