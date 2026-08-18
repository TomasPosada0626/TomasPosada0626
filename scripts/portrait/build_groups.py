#!/usr/bin/env python3
"""
build_groups.py

Computes the two dot partitions the banner's animation needs, for a
given theme's portrait dot set:

  intro groups (~60, for the one-time reveal)
      Every dot independently assigned a uniform-random group id.
      Because assignment ignores position entirely, each group is
      already a representative scatter of the whole portrait -- "no
      spatial grouping" is a consequence of the method, not something
      layered on afterwards. Checked with evenness_metric (how unevenly
      the 60 groups cover an 8x8 spatial bin grid).

  drift bands (~94, for the loop)
      k-means over each dot's position *plus Gaussian noise, sigma 4*,
      not over its raw position. Raw-position k-means on a regular
      dither grid produces bands whose boundaries snap to straight
      lines (drift is a linear function of position, so is naive
      grouping, and two linear functions of the same variable line up)
      -- the SVG would visibly tear along a square grid the moment
      bands start translating apart. Clustering the *noised* copy while
      still recording each dot's real position breaks that alignment;
      checked with straight_boundary_metric.

Saves per-dot integer arrays (aligned 1:1 with portraitTHEME.npy's
point order, which numpy's nonzero() always returns in the same
deterministic row-major order for a given grid, so recomputation stays
consistent run to run without needing to store point identities).
"""

import argparse
from pathlib import Path

import numpy as np
from scipy.cluster.vq import kmeans2

from dither import GRID_W, GRID_H, evenness_metric, straight_boundary_metric

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "assets" / "data"

N_INTRO_GROUPS = 60
N_DRIFT_BANDS = 94
DRIFT_NOISE_SIGMA = 4.0


def build_intro_groups(n_dots: int, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, N_INTRO_GROUPS, size=n_dots)


def build_drift_bands(pts_px: np.ndarray, seed: int = 11) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noised = pts_px + rng.normal(0, DRIFT_NOISE_SIGMA, size=pts_px.shape)
    # kmeans2 wants float64 and can raise on empty clusters with certain
    # inits; 'points' init (real data points as seeds) is robust here.
    centroids, band_id = kmeans2(noised.astype(np.float64), N_DRIFT_BANDS, seed=seed, minit="points")
    return band_id


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--theme", required=True, choices=["dark", "light"])
    args = ap.parse_args()

    pts_frac = np.load(DATA_DIR / f"portrait_{args.theme}.npy")
    pts_px = pts_frac * [GRID_W, GRID_H]
    n = len(pts_px)
    print(f"{args.theme}: {n:,} dots")

    intro = build_intro_groups(n)
    ev = evenness_metric(pts_px, intro, GRID_W, GRID_H)
    print(f"intro groups: {N_INTRO_GROUPS}, evenness={ev:.4f} (~0.05 good, ~0.7 patchy)")

    bands = build_drift_bands(pts_px)
    sb = straight_boundary_metric(pts_px, bands)
    print(f"drift bands: {N_DRIFT_BANDS}, straight_boundary={sb:.4f} (~0.01 organic, ~0.17 = grid trap)")

    np.save(DATA_DIR / f"intro_groups_{args.theme}.npy", intro)
    np.save(DATA_DIR / f"drift_bands_{args.theme}.npy", bands)
    print(f"wrote intro_groups_{args.theme}.npy, drift_bands_{args.theme}.npy")


if __name__ == "__main__":
    main()
