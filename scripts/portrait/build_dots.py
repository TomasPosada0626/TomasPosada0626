#!/usr/bin/env python3
"""
build_dots.py

Turns the source portrait photo into two dot-grid arrays (dark-panel and
light-panel variants) and saves them as .npy -- the generator + these
arrays are the source of truth; assets/svg/banner-*.svg is a build
artifact regenerated from them, never hand-edited.

Source photo path is passed via --source and is deliberately NOT read
from anywhere inside the repo by default: reference photos are guide
material, gitignored, and must never be committed.

Pipeline
    1. Crop head+shoulders from the source photo, resize onto the shared
       GRID_W x GRID_H cell grid (see dither.py).
    2. Dark-mode mask: GrabCut foreground segmentation, then
       binary_closing + fill_holes + keep-largest-component to clean it
       up. GrabCut (not a flat colour-distance threshold) because the
       background behind this particular photo has real texture (wood
       grain), which fools a naive threshold.
    3. Shared tone prep: autocontrast(cutoff=1) -> contrast x1.3 ->
       UnsharpMask(radius=3, percent=140).
    4. Serpentine Floyd-Steinberg dither, run twice on the same prepped
       grayscale:
         - dark:  invert=True (ink = bright pixels), then hard-clip the
           result to a 1px-eroded mask -- clipping *after* dithering
           (rather than zeroing background before it) keeps the error
           diffusion inside the subject continuous, and the erosion
           specifically kills any bleed that diffused across the mask
           edge.
         - light: invert=False (ink = dark pixels), full frame, no mask
           (background stays in the piece).
    5. Save each as an (N, 2) float32 array of *fractional* (x, y) dot
       centers in [0, 1] -- resolution-independent, so the banner
       builder can place them at whatever panel size it wants.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import cv2

from dither import GRID_W, GRID_H, dither_serpentine, clean_mask

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "assets" / "data"


def load_cropped(path: Path, box) -> Image.Image:
    im = Image.open(path).convert("RGB")
    if box:
        im = im.crop(box)
    return im.resize((GRID_W, GRID_H), Image.LANCZOS)


def grabcut_foreground(rgb_img: Image.Image, force_bg_box=None, force_fg_box=None) -> np.ndarray:
    """Plain rect-init GrabCut, optionally refined with hard mask hints.
    force_bg_box / force_fg_box: (x0, y0, x1, y1) in this grid's own
    pixel space, seeded as GC_BGD / GC_FGD before a mask-init pass. Used
    to correct GrabCut pulling a same-toned background patch (e.g. a
    lit wood plank near skin/hair tones) into the "probable foreground"
    class -- a plain colour-distance threshold has the same failure
    mode here, so this is the manual assist the pipeline falls back to
    rather than trusting one automatic pass blind."""
    arr = np.array(rgb_img)
    h, w = arr.shape[:2]
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    bgd_model = np.zeros((1, 65), np.float64)
    fgd_model = np.zeros((1, 65), np.float64)

    mask = np.zeros((h, w), np.uint8)
    rect = (int(w * 0.03), int(h * 0.02), int(w * 0.95), int(h * 0.97))
    cv2.grabCut(bgr, mask, rect, bgd_model, fgd_model, 8, cv2.GC_INIT_WITH_RECT)

    if force_bg_box or force_fg_box:
        if force_bg_box:
            x0, y0, x1, y1 = force_bg_box
            mask[y0:y1, x0:x1] = cv2.GC_BGD
        if force_fg_box:
            x0, y0, x1, y1 = force_fg_box
            mask[y0:y1, x0:x1] = cv2.GC_FGD
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        cv2.grabCut(bgr, mask, None, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_MASK)

    return np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 1, 0).astype(bool)


def preprocess_gray(rgb_img: Image.Image) -> np.ndarray:
    g = ImageOps.grayscale(rgb_img)
    g = ImageOps.autocontrast(g, cutoff=1)
    g = ImageEnhance.Contrast(g).enhance(1.3)
    g = g.filter(ImageFilter.UnsharpMask(radius=3, percent=140))
    return np.asarray(g, dtype=np.float64)


def erode(mask: np.ndarray, px: int = 1) -> np.ndarray:
    from scipy import ndimage
    if px <= 0:
        return mask
    return ndimage.binary_erosion(mask, structure=np.ones((3, 3)), iterations=px)


def ink_to_fractional_points(ink: np.ndarray) -> np.ndarray:
    ys, xs = np.nonzero(ink)
    pts = np.stack([(xs + 0.5) / GRID_W, (ys + 0.5) / GRID_H], axis=1).astype(np.float32)
    return pts


def render_preview(points: np.ndarray, out_path: Path, bg: str, dot: str, scale: int = 3):
    canvas = Image.new("RGB", (GRID_W * scale, GRID_H * scale), bg)
    px = canvas.load()
    dot_rgb = Image.new("RGB", (1, 1), dot).getpixel((0, 0))
    r = max(1, scale // 2)
    for x, y in points:
        cx, cy = int(x * GRID_W * scale), int(y * GRID_H * scale)
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                px_x, px_y = cx + dx, cy + dy
                if 0 <= px_x < canvas.width and 0 <= px_y < canvas.height:
                    px[px_x, px_y] = dot_rgb
    canvas.save(out_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, type=Path, help="path to the raw portrait photo (not in the repo)")
    ap.add_argument("--crop", nargs=4, type=int, default=[50, 60, 1020, 1160], metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--preview-dir", type=Path, default=None, help="if set, also render PNG previews here (scratch only, never committed)")
    ap.add_argument("--force-bg-box", nargs=4, type=int, default=[235, 0, 300, 240], metavar=("X0", "Y0", "X1", "Y1"),
                     help="grid-space box to hard-seed as background before a mask-refine GrabCut pass (this photo's lit wood plank fooled the plain rect pass); pass four zeros to disable")
    ap.add_argument("--force-fg-box", nargs=4, type=int, default=[100, 120, 210, 320], metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--bg-lift", type=float, default=115, help="brightness added to background-only pixels before the light-mode dither pass, to thin a dark/busy backdrop to a texture instead of a near-solid slab")
    args = ap.parse_args()

    box = tuple(args.crop)
    im = load_cropped(args.source, box)

    force_bg = tuple(args.force_bg_box) if any(args.force_bg_box) else None
    force_fg = tuple(args.force_fg_box) if any(args.force_fg_box) else None
    fg_raw = grabcut_foreground(im, force_bg_box=force_bg, force_fg_box=force_fg)
    fg = clean_mask(fg_raw)
    coverage = fg.mean()
    print(f"segmentation: {coverage:.1%} of frame kept as foreground")
    if not (0.15 < coverage < 0.85):
        print("WARNING: foreground coverage looks implausible for a head+shoulders crop -- inspect the mask preview before trusting this run")

    gray = preprocess_gray(im)

    ink_dark_raw = dither_serpentine(gray, invert=True)
    fg_eroded = erode(fg, px=1)
    ink_dark = ink_dark_raw & fg_eroded

    # Light mode keeps the background (per spec), but this photo's wood
    # backdrop is dark enough on its own (~75% of its cells fall below
    # the dither threshold untouched) that it dithers to a near-solid
    # slab instead of a texture, and roughly doubles the dot count for
    # no visual gain. Lifting *only* the background pixels' brightness
    # before this dither pass thins it to a legible stipple without
    # touching the subject's own tones or removing the background.
    gray_light = gray.copy()
    gray_light[~fg] = np.clip(gray_light[~fg] + args.bg_lift, 0, 255)
    ink_light = dither_serpentine(gray_light, invert=False)

    pts_dark = ink_to_fractional_points(ink_dark)
    pts_light = ink_to_fractional_points(ink_light)
    print(f"dark dots:  {len(pts_dark):,}")
    print(f"light dots: {len(pts_light):,}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    np.save(args.out_dir / "portrait_dark.npy", pts_dark)
    np.save(args.out_dir / "portrait_light.npy", pts_light)
    np.save(args.out_dir / "portrait_mask.npy", fg)
    # boolean GRID_H x GRID_W grids alongside the point lists: the SVG
    # builder run-length-encodes rows for the <path>, which needs row
    # adjacency that's cheap to get from the grid and annoying to
    # reconstruct reliably from a flat point list.
    np.save(args.out_dir / "portrait_dark_grid.npy", ink_dark)
    np.save(args.out_dir / "portrait_light_grid.npy", ink_light)
    print(f"wrote {args.out_dir/'portrait_dark.npy'}, portrait_light.npy, portrait_mask.npy, portrait_dark_grid.npy, portrait_light_grid.npy")

    if args.preview_dir:
        args.preview_dir.mkdir(parents=True, exist_ok=True)
        render_preview(pts_dark, args.preview_dir / "preview_dark.png", bg="#0A101F", dot="#A78BFA")
        render_preview(pts_light, args.preview_dir / "preview_light.png", bg="#FFFFFF", dot="#7C3AED")
        mask_img = Image.fromarray((fg * 255).astype(np.uint8))
        mask_img.save(args.preview_dir / "preview_mask.png")
        print(f"wrote previews to {args.preview_dir}")


if __name__ == "__main__":
    main()
