#!/usr/bin/env python3
"""
build_divider.py

Generates a thin "light sheet" section divider: a horizontal line that
draws itself on once (left to right, via the same pathLength=100 dash-
reveal trick used in header.svg and hero.svg), then holds fully lit
while a soft glow behind it pulses forever. Transparent background --
this is meant to sit inline between README sections, not sit in its own
framed panel like header.svg does.

No randomness, no per-run variation: given the same --color/--width/etc.
this always emits a byte-identical file, so the daily Action run never
produces a no-op diff for these.
"""

import argparse
from pathlib import Path

COLOR_PRESETS = {
    "cyan": "#39E6FF",
    "green": "#39FF6B",
    "red": "#FF4D4D",
}


def resolve_color(value: str) -> str:
    if value.startswith("#"):
        return value
    try:
        return COLOR_PRESETS[value.lower()]
    except KeyError:
        raise SystemExit(f"unknown color preset '{value}' -- choose one of {list(COLOR_PRESETS)} or pass a #hex value")


def build_svg(args) -> str:
    color = resolve_color(args.color)
    w, h = args.width, args.height
    x1, x2, y = 6, w - 6, h / 2

    return (
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" role="img" aria-label="Decorative glowing section divider">'
        f'<defs>'
        f'<filter id="glow" x="-50%" y="-400%" width="200%" height="900%">'
        f'<feGaussianBlur in="SourceGraphic" stdDeviation="3" result="b"/>'
        f'<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        f'</filter>'
        f'</defs>'
        # soft glow layer behind the crisp line, pulsing forever once the reveal finishes
        f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{color}" stroke-width="2.4" '
        f'stroke-linecap="round" filter="url(#glow)" pathLength="100" stroke-dasharray="100" stroke-dashoffset="100" opacity=".6">'
        f'<animate attributeName="stroke-dashoffset" from="100" to="0" begin="0s" dur="{args.reveal_duration}s" fill="freeze"/>'
        f'<animate attributeName="opacity" values=".35;.75;.35" begin="{args.reveal_duration}s" dur="{args.pulse_duration}s" repeatCount="indefinite"/>'
        f'</line>'
        # crisp core line, reveals once and stays fully lit
        f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="{color}" stroke-width="1.2" '
        f'stroke-linecap="round" pathLength="100" stroke-dasharray="100" stroke-dashoffset="100">'
        f'<animate attributeName="stroke-dashoffset" from="100" to="0" begin="0s" dur="{args.reveal_duration}s" fill="freeze"/>'
        f'</line>'
        f'</svg>'
    )


def parse_args():
    p = argparse.ArgumentParser(description="Build a glowing section-divider SVG")
    p.add_argument("--color", default="cyan", help="preset name (cyan/green/red) or a #hex value")
    p.add_argument("--width", type=float, default=1200)
    p.add_argument("--height", type=float, default=24)
    p.add_argument("--reveal-duration", type=float, default=1.1, dest="reveal_duration")
    p.add_argument("--pulse-duration", type=float, default=2.4, dest="pulse_duration")
    p.add_argument("--output", default="assets/svg/divider.svg")
    return p.parse_args()


def main():
    args = parse_args()
    svg = build_svg(args)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(svg, encoding="utf-8")
    tmp_path.replace(out_path)
    print(f"wrote {out_path} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
