#!/usr/bin/env python3
"""
build_logos.py

Traces the three reference logo images (React, the </> glyph, the Rebel
Alliance emblem) into matched ~900-point "traveller" clouds for the
banner's logo-morph loop.

Tracing method, and why it isn't just "dither the logo"
    A flat-colour icon has no midtones for Floyd-Steinberg to modulate --
    every interior pixel is either fully background or fully ink, so
    dithering it just returns "every pixel inside the shape", not a
    density-controlled point count. Instead: threshold the logo to a
    silhouette mask (by *distance from white*, not by darkness -- the
    React mark is a light cyan on white, far from black but far from
    white too), then place N points inside that mask and relax them with
    a few Lloyd (centroidal Voronoi) iterations so they spread evenly
    across the silhouette regardless of its local shape complexity.

Mask cleanup deliberately skips two things clean_mask() does for the
portrait:
    - fill_holes: the Rebel Alliance emblem's two "wing" cutouts are
      real negative space, not segmentation noise -- filling them would
      turn a recognisable emblem into a blob.
    - keep-largest-component: the </> glyph is three disconnected
      strokes. Keeping only the largest would discard two of them.
    A minimum-pixel-count filter still drops true noise specks (stray
    antialiasing pixels), just without those two destructive steps.

Matching three shapes to one bijective "traveller" index
    Each traveller must be the *same point* across all three logos so
    its motion path is continuous. pts1/pts2/pts3 are stippled
    independently (so on their own carry no correspondence), then
    scipy.optimize.linear_sum_assignment finds the minimum-total-distance
    bijection logo1->logo2, and logo2 is *reordered* by that assignment
    before solving logo2->logo3 -- so index i in the output always means
    "the same travelling dot" at each of the three keyframes.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree
from scipy.spatial.distance import cdist
from scipy.optimize import linear_sum_assignment

from dither import GRID_W, GRID_H

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "assets" / "data"

TARGET_CELLS = 204.0    # a traced logo's longer bbox side, in portrait-grid cell units
FRAME_CENTER = (GRID_W / 2, GRID_H / 2)
N_TRAVELLERS = 900


BACKGROUND_REFS = (
    (255.0, 255.0, 255.0),  # flattened onto plain white (react, e.g.)
    (230.0, 230.0, 230.0),  # flattened onto a checkerboard "transparency" matte (glyph, rebel)
)


def logo_mask(rgb_img: Image.Image, distance_thresh: float = 25.0, min_component_px: int = 15) -> np.ndarray:
    """Distance from white alone isn't enough here: two of the three
    source PNGs had their real alpha channel flattened by WhatsApp's
    re-compression onto a light-grey/white checkerboard matte (visible
    as a checker pattern when you open the file) instead of solid
    white, and that matte's grey squares (230,230,230) sit just past a
    plain white-only threshold -- so distance is measured to whichever
    background reference colour is closer, and the threshold is tighter
    to compensate for the matte's grey being that much closer to real
    (light-toned) glyph pixels to begin with."""
    arr = np.asarray(rgb_img.convert("RGB"), dtype=np.float64)
    dists = [np.sqrt(((arr - ref) ** 2).sum(axis=2)) for ref in BACKGROUND_REFS]
    dist_from_bg = np.minimum.reduce(dists)
    mask = dist_from_bg > distance_thresh
    mask = ndimage.binary_closing(mask, structure=np.ones((3, 3)), iterations=1)
    labeled, n = ndimage.label(mask)
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, labeled, range(1, n + 1))
    keep = {i + 1 for i, s in enumerate(sizes) if s >= min_component_px}
    return np.isin(labeled, list(keep))


def stipple_mask(mask: np.ndarray, n_points: int, seed: int, iters: int = 25) -> np.ndarray:
    """Lloyd-relax n_points inside mask (pixel-space xy) for even coverage."""
    rng = np.random.default_rng(seed)
    ys, xs = np.nonzero(mask)
    mask_xy = np.stack([xs, ys], axis=1).astype(np.float64)
    idx = rng.choice(len(mask_xy), size=n_points, replace=len(mask_xy) < n_points)
    pts = mask_xy[idx].copy()
    for _ in range(iters):
        tree = cKDTree(pts)
        _, assign = tree.query(mask_xy)
        new_pts = pts.copy()
        for i in range(len(pts)):
            sel = mask_xy[assign == i]
            new_pts[i] = sel.mean(axis=0) if len(sel) else mask_xy[rng.integers(0, len(mask_xy))]
        pts = new_pts
    return pts


def normalize_to_grid(pts_px: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Pixel-space stipple points -> fractional (x/GRID_W, y/GRID_H)
    portrait-grid coordinates: same isotropic cell scale as the
    portrait (its 300x340 resize happened to preserve the source crop's
    aspect, so grid cells there are already square), centred on the
    shared frame centre so all three logos morph around one anchor
    point instead of jumping between different centres."""
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    bbox_w, bbox_h = x1 - x0, y1 - y0
    scale = TARGET_CELLS / max(bbox_w, bbox_h)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    grid_xy = (pts_px - [cx, cy]) * scale + FRAME_CENTER
    return grid_xy / [GRID_W, GRID_H]


def trace_logo(path: Path, seed: int) -> np.ndarray:
    im = Image.open(path)
    mask = logo_mask(im)
    fg_px = int(mask.sum())
    pts_px = stipple_mask(mask, N_TRAVELLERS, seed=seed)
    pts_frac = normalize_to_grid(pts_px, mask)
    lo, hi = pts_frac.min(), pts_frac.max()
    print(f"{path.name}: {fg_px:,} silhouette px -> {len(pts_frac)} points, frac range [{lo:.3f}, {hi:.3f}]")
    if lo < -0.02 or hi > 1.02:
        print(f"  WARNING: {path.name} overflows the [0,1] frame -- lower TARGET_CELLS")
    return pts_frac.astype(np.float32)


def chain_optimal_transport(pts1, pts2, pts3):
    cost12 = cdist(pts1, pts2)
    _, col12 = linear_sum_assignment(cost12)
    pts2_aligned = pts2[col12]

    cost23 = cdist(pts2_aligned, pts3)
    _, col23 = linear_sum_assignment(cost23)
    pts3_aligned = pts3[col23]

    d12 = np.linalg.norm(pts1 - pts2_aligned, axis=1)
    d23 = np.linalg.norm(pts2_aligned - pts3_aligned, axis=1)
    print(f"OT transition 1->2: mean travel {d12.mean():.4f} (frac units), max {d12.max():.4f}")
    print(f"OT transition 2->3: mean travel {d23.mean():.4f} (frac units), max {d23.max():.4f}")
    return pts1, pts2_aligned, pts3_aligned


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--react", required=True, type=Path)
    ap.add_argument("--glyph", required=True, type=Path)
    ap.add_argument("--rebel", required=True, type=Path)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    pts_react = trace_logo(args.react, seed=1)
    pts_glyph = trace_logo(args.glyph, seed=2)
    pts_rebel = trace_logo(args.rebel, seed=3)

    # loop order: react -> glyph -> rebel, matching how the user listed them
    p1, p2, p3 = chain_optimal_transport(pts_react, pts_glyph, pts_rebel)

    travellers = np.stack([p1, p2, p3], axis=1)  # (900, 3, 2)
    centroid_logo1 = p1.mean(axis=0)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    np.save(args.out_dir / "travellers.npy", travellers)
    np.save(args.out_dir / "logo1_centroid.npy", centroid_logo1)
    print(f"wrote {args.out_dir/'travellers.npy'} shape={travellers.shape}")
    print(f"logo1 (react) centroid: {centroid_logo1}")


if __name__ == "__main__":
    main()
