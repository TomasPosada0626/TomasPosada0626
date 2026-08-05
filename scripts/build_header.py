#!/usr/bin/env python3
"""
build_header.py

Generates header.svg: a self-contained, autoplaying SVG with a CRT-styled
terminal panel that types out a short bio, next to a radar scanner that
sweeps forever.

  TERMINAL
      The panel fades in once, then "types" its lines left to right using
      an animated <clipPath> rect per line (grows 0 -> full width, then
      freezes) -- lighter than animating one <tspan> per character, and
      never relies on hover/JS. A block cursor starts blinking, forever,
      right after the last line finishes. Since GitHub re-fetches the
      image (and restarts its SMIL timeline) every time the README is
      loaded, "plays once" already means "replays on every visit" --
      there's no need to loop the retype on a timer on top of that.

  RADAR
      Concentric rings, a rotating sweep (a bright leading line plus a
      few fading trail lines standing in for a conic gradient -- SVG has
      no native one), and a few blips that flash right as the sweep's
      leading edge crosses their angle, then decay to a faint "known
      contact" glow until the next pass.

  LEGEND
      A small sign-off line that fades in once typing finishes and stays.

No randomness anywhere -- every position/timing is a deterministic
function of its index or of the text it's given, so re-running this
script with the same arguments produces a byte-identical file and the
daily Action run never creates a no-op diff.
"""

import argparse
import math
import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import requests

GRAPHQL_URL = "https://api.github.com/graphql"

# --- Palette: edit freely. terminal/accent drive nearly every color below. ---
PALETTE = {
    "bg": "#060809",
    "bg_vignette": "#0c1116",
    "panel": "#0a0d10",
    "terminal": "#39FF6B",   # phosphor green boot text / cursor
    "accent": "#58A6FF",     # radar rings / borders / captions
    "muted": "#5b6570",
}


class HeaderBuildError(Exception):
    """Raised for any condition that should abort the build without
    touching the on-disk SVG."""


def fetch_total_commits(username: str, token: str, timeout: float = 15.0) -> int:
    """Same field (totalCommitContributions) and error-handling posture
    as scripts/build_stats.py -- deliberately duplicated rather than
    imported, so this script stays a fully independent, reusable
    component that doesn't need its sibling scripts to run."""
    query = "query($login: String!) { user(login: $login) { contributionsCollection { totalCommitContributions } } }"
    try:
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": query, "variables": {"login": username}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise HeaderBuildError(f"network error calling GitHub GraphQL API: {exc}") from exc
    if resp.status_code == 401:
        raise HeaderBuildError("GitHub API rejected the token (401) — check GH_PAT is valid, unexpired and has read:user scope")
    if resp.status_code == 403:
        raise HeaderBuildError(f"GitHub API returned 403 (likely rate-limited): {resp.text[:300]}")
    if resp.status_code != 200:
        raise HeaderBuildError(f"GitHub API returned HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        payload = resp.json()
    except ValueError as exc:
        raise HeaderBuildError(f"GitHub API response was not valid JSON: {exc}") from exc
    if payload.get("errors"):
        raise HeaderBuildError(f"GitHub GraphQL API returned errors: {payload['errors']}")
    try:
        return payload["data"]["user"]["contributionsCollection"]["totalCommitContributions"]
    except (KeyError, TypeError) as exc:
        raise HeaderBuildError(f"unexpected GraphQL response shape: {payload}") from exc


def build_terminal(x, y, w, h, lines_text, font_size, cps, start_at, gap):
    """CRT panel + scanline pattern + sequential clip-path typing.
    Plays once (fill="freeze"). Returns (svg_fragment, typing_end)."""
    pad_x, pad_y, line_h = 20, 34, font_size * 1.9
    text_x = x + pad_x

    panel = (
        f'<g opacity="0">'
        f'<animate attributeName="opacity" from="0" to="1" begin="{start_at - 0.3:.2f}s" dur="0.4s" fill="freeze"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{PALETTE["panel"]}"/>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="url(#scanlines)"/>'
        f'<rect x="{x + 1}" y="{y + 1}" width="{w - 2}" height="{h - 2}" rx="7" fill="none" '
        f'stroke="{PALETTE["accent"]}" stroke-opacity=".55" stroke-width="1.2"/>'
        f'<rect x="{x + 1}" y="{y + 1}" width="{w - 2}" height="{h - 2}" rx="7" fill="none" '
        f'stroke="{PALETTE["accent"]}" stroke-width="1.4" filter="url(#glow)" opacity=".7">'
        f'<animate attributeName="opacity" values=".35;.8;.35" dur="2.6s" repeatCount="indefinite"/>'
        f'</rect>'
    )

    t = start_at
    clip_defs, texts = [], []
    for i, line in enumerate(lines_text):
        w_est = len(line) * font_size * 0.62 + 8
        dur = max(0.35, len(line) / cps)
        line_y = y + pad_y + i * line_h
        clip_defs.append(
            f'<clipPath id="type-line-{i}">'
            f'<rect x="{text_x - 2}" y="{line_y - font_size}" width="0" height="{font_size * 1.4}">'
            f'<animate attributeName="width" from="0" to="{w_est:.0f}" begin="{t:.2f}s" dur="{dur:.2f}s" fill="freeze"/>'
            f'</rect></clipPath>'
        )
        texts.append(
            f'<text x="{text_x}" y="{line_y}" font-size="{font_size}" '
            f'font-family="ui-monospace,Consolas,monospace" fill="{PALETTE["terminal"]}" '
            f'clip-path="url(#type-line-{i})">{escape(line)}</text>'
        )
        t += dur + gap

    typing_end = t
    cursor_x = text_x + len(lines_text[-1]) * font_size * 0.62 + 6
    cursor_y = y + pad_y + (len(lines_text) - 1) * line_h
    cursor = (
        f'<rect x="{cursor_x:.1f}" y="{cursor_y - font_size:.1f}" width="{font_size * 0.55:.1f}" '
        f'height="{font_size * 1.05:.1f}" fill="{PALETTE["terminal"]}" opacity="0">'
        f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.5;1" '
        f'calcMode="discrete" begin="{typing_end:.2f}s" dur="1s" repeatCount="indefinite"/>'
        f'</rect>'
    )

    panel += "".join(texts) + cursor + "</g>"
    return "".join(clip_defs) + panel, typing_end


def build_radar(cx, cy, start_at, caption):
    """Concentric rings, a rotating sweep (leading line + fading trail
    lines standing in for a conic gradient), and blips that flash right
    as the sweep's leading edge crosses their angle, then decay to a
    faint "known contact" glow until the next pass -- reads as "the
    radar just detected something there" instead of blinking on an
    unrelated timer. Loops forever once started."""
    sweep_dur = 6.0
    rings = "".join(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{PALETTE["accent"]}" stroke-opacity=".3" stroke-width="1"/>'
        for r in (28, 58, 90)
    )

    trail = "".join(
        f'<line x1="0" y1="0" x2="{92 * math.cos(math.radians(-off)):.1f}" '
        f'y2="{92 * math.sin(math.radians(-off)):.1f}" '
        f'stroke="{PALETTE["accent"]}" stroke-width="{max(1, 3 - off * 0.15):.1f}" '
        f'stroke-linecap="round" opacity="{max(0.05, 0.55 - off * 0.045):.2f}"/>'
        for off in (0, 5, 10, 15, 20, 25)
    )
    # Un-transformed inner <g> for the rotation, rather than animating
    # the same attribute the outer translate() owns, sidesteps any
    # ambiguity over how "additive" composition of two different
    # transform types would combine.
    sweep = (
        f'<g transform="translate({cx},{cy})">'
        f'<g>{trail}'
        f'<animateTransform attributeName="transform" type="rotate" from="0" to="360" '
        f'dur="{sweep_dur}s" begin="{start_at:.2f}s" repeatCount="indefinite"/>'
        f'</g></g>'
    )

    # angle uses the same clockwise-from-+x convention as the rotate
    # transform above, so (angle/360)*sweep_dur is exactly the moment
    # within each sweep_dur-second rotation when the leading edge points
    # straight at this blip.
    blip_specs = [(40, 55), (140, 75), (210, 40), (300, 65)]
    blips = []
    for angle, r in blip_specs:
        bx = cx + r * math.cos(math.radians(angle))
        by = cy + r * math.sin(math.radians(angle))
        hit_time = (angle / 360.0) * sweep_dur
        begin = start_at + hit_time
        blips.append(
            f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="3.2" fill="{PALETTE["terminal"]}" opacity=".08" filter="url(#glow)">'
            f'<animate attributeName="opacity" values=".08;1;.1;.08" keyTimes="0;0.04;0.3;1" '
            f'dur="{sweep_dur}s" begin="{begin:.2f}s" repeatCount="indefinite"/>'
            f'</circle>'
        )

    label = (
        f'<text x="{cx}" y="{cy - 108}" text-anchor="middle" font-size="9" letter-spacing=".18em" '
        f'font-family="ui-monospace,Consolas,monospace" fill="{PALETTE["accent"]}" opacity=".8">{escape(caption)}</text>'
    )

    return (
        f'<g opacity="0">'
        f'<animate attributeName="opacity" from="0" to="1" begin="{start_at - 0.3:.2f}s" dur="0.4s" fill="freeze"/>'
        f'{label}{rings}{sweep}{"".join(blips)}'
        f'</g>'
    )


def build_starfield(w, h, n=36):
    """A faint scatter of twinkling background dots. Positions come from
    two coprime-ish multipliers (173, 91) walked mod width/height rather
    than an RNG, so the scatter still looks organic but re-running this
    script with the same canvas size always places every star in the
    exact same spot -- no per-run diff noise. Rendered first, so the
    terminal/radar panels simply draw over and hide whichever stars end
    up underneath them."""
    stars = []
    for i in range(n):
        x = (i * 173 + 37) % int(w - 20) + 10
        y = (i * 91 + 53) % int(h - 20) + 10
        r = 0.6 + (i % 3) * 0.35
        dur = 2.2 + (i % 5) * 0.55
        begin = (i % 7) * 0.35
        peak = 0.35 + (i % 4) * 0.12
        stars.append(
            f'<circle cx="{x}" cy="{y}" r="{r:.2f}" fill="#FFFFFF">'
            f'<animate attributeName="opacity" values=".08;{peak:.2f};.08" '
            f'dur="{dur:.2f}s" begin="{begin:.2f}s" repeatCount="indefinite"/>'
            f'</circle>'
        )
    return f'<g>{"".join(stars)}</g>'


def build_corner_brackets(w, h, color):
    """Four static L-shaped HUD corner brackets, framing the whole scene
    -- same minimal sci-fi-HUD motif used elsewhere in this profile's
    assets. Purely decorative, no animation needed."""
    m, s = 14, 16  # margin from the edge, and bracket arm length
    return (
        f'<g fill="none" stroke="{color}" stroke-width="2" opacity=".85">'
        f'<path d="M{m},{m + s} L{m},{m} L{m + s},{m}"/>'
        f'<path d="M{w - m},{m + s} L{w - m},{m} L{w - m - s},{m}"/>'
        f'<path d="M{m},{h - m - s} L{m},{h - m} L{m + s},{h - m}"/>'
        f'<path d="M{w - m},{h - m - s} L{w - m},{h - m} L{w - m - s},{h - m}"/>'
        f'</g>'
    )


def ship_silhouette_markup():
    """A small original starfighter silhouette: tapered fuselage, swept
    wings, a glowing cockpit, an engine core, and a faint exhaust trail
    behind it. This is an in-house design (own proportions, own panel
    shapes) meant to read as "generic sci-fi fighter" -- it is not
    based on, and should not be edited toward, any specific existing
    ship design. Drawn nose-right in local space; ships travelling the
    other way just wrap this same markup in a scale(-1,1) group."""
    return (
        f'<line x1="-34" y1="0" x2="-14" y2="0" stroke="{PALETTE["accent"]}" stroke-width="2" '
        f'stroke-linecap="round" opacity=".5" filter="url(#glow)"/>'
        f'<path d="M18,0 L5,-4 L-12,-3.4 L-15,0 L-12,3.4 L5,4 Z" fill="#11161c" stroke="{PALETTE["muted"]}" stroke-width="1"/>'
        f'<path d="M-3,-2.4 L-17,-10 L-10,-3 Z" fill="#11161c" stroke="{PALETTE["muted"]}" stroke-width="1"/>'
        f'<path d="M-3,2.4 L-17,10 L-10,3 Z" fill="#11161c" stroke="{PALETTE["muted"]}" stroke-width="1"/>'
        f'<ellipse cx="7" cy="0" rx="3.2" ry="1.7" fill="{PALETTE["accent"]}" opacity=".9" filter="url(#glow)"/>'
        f'<circle cx="-14" cy="0" r="1.6" fill="{PALETTE["terminal"]}" filter="url(#glow)"/>'
    )


def build_ship_instance(y, direction, begin, travel_dur, cycle_dur, w):
    """One background ship on its own independent loop: sits fully off-
    canvas, then crosses the whole width fast, then waits off-canvas
    again until the next pass. `direction` is 1 for left-to-right or -1
    for right-to-left. The mirror for right-to-left ships is applied on
    its own dedicated wrapper <g> with no other transform on it, so it
    just flips the silhouette in place -- combining it with the <use>
    positioning attributes directly would flip the *position* too,
    which is the classic gotcha with this trick."""
    margin = 60
    if direction == 1:
        x_start, x_end = -margin, w + margin
        inner = ship_silhouette_markup()
    else:
        x_start, x_end = w + margin, -margin
        inner = f'<g transform="scale(-1,1)">{ship_silhouette_markup()}</g>'
    t0 = begin / cycle_dur
    t1 = (begin + travel_dur) / cycle_dur
    return (
        f'<g>'
        f'<animateTransform attributeName="transform" type="translate" '
        f'values="{x_start:.0f},{y};{x_start:.0f},{y};{x_end:.0f},{y};{x_end:.0f},{y}" '
        f'keyTimes="0;{t0:.4f};{t1:.4f};1" dur="{cycle_dur:.2f}s" repeatCount="indefinite"/>'
        f'{inner}'
        f'</g>'
    )


def build_ships(w):
    """Four ships confined to the top strip (y < 46, fully open) and a
    band in the bottom strip that sits above the legend text (y ~ 282,
    legend baseline is ~302) so a fast-moving silhouette never has to
    cross behind the opaque terminal panel and pop in/out oddly, and
    never overlaps the legend. Timings are staggered and irregular
    (different cycle lengths) purely so passes don't fall into a
    noticeable repeating pattern -- still fully deterministic, no RNG."""
    ships = [
        build_ship_instance(20, 1, 1.0, 0.65, 7.0, w),
        build_ship_instance(34, -1, 3.6, 0.55, 8.0, w),
        build_ship_instance(282, 1, 2.0, 0.70, 9.0, w),
        build_ship_instance(282, -1, 5.5, 0.60, 10.0, w),
    ]
    return f'<g>{"".join(ships)}</g>'


def build_svg(args, total_commits):
    w, h = args.width, args.height

    term_x, term_y = 56, 46
    term_w, term_h = 624, 228
    term_font = 15
    start_at = 0.4

    lines_text = [
        "> BOOTING SYSTEM...",
        f"> {args.linkedin}",
        f"> {args.line3}",
        f"> STATUS: {args.status}",
    ]
    if total_commits is not None:
        lines_text.append(f"> {total_commits:,} COMMITS AND COUNTING")

    terminal_svg, typing_end = build_terminal(term_x, term_y, term_w, term_h, lines_text, term_font, args.type_cps, start_at, args.line_gap)
    radar_svg = build_radar(w - 220, h / 2, start_at, "SIGNAL SCAN")

    legend = (
        f'<g opacity="0">'
        f'<animate attributeName="opacity" from="0" to="1" begin="{typing_end + 0.2:.2f}s" dur="0.5s" fill="freeze"/>'
        f'<text x="{w / 2:.0f}" y="{h - 18}" text-anchor="middle" font-size="15" font-style="italic" letter-spacing=".08em" '
        f'font-family="ui-monospace,Consolas,monospace" fill="{PALETTE["accent"]}" opacity=".8">'
        f'MAY THE CODE BE WITH YOU</text>'
        f'</g>'
    )

    return (
        f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="Animated CRT terminal typing out a short bio next to a looping radar scanner">'
        f'<title>{escape(args.handle)} — console</title>'
        f'<defs>'
        f'<radialGradient id="bgGrad" cx="50%" cy="35%" r="85%">'
        f'<stop offset="0%" stop-color="{PALETTE["bg_vignette"]}"/><stop offset="100%" stop-color="{PALETTE["bg"]}"/>'
        f'</radialGradient>'
        f'<filter id="glow" x="-80%" y="-80%" width="260%" height="260%">'
        f'<feGaussianBlur in="SourceGraphic" stdDeviation="2.6" result="b"/>'
        f'<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>'
        f'</filter>'
        f'<pattern id="scanlines" width="2" height="4" patternUnits="userSpaceOnUse">'
        f'<rect x="0" y="0" width="2" height="1" fill="#000000" opacity=".4"/>'
        f'</pattern>'
        f'</defs>'
        f'<rect width="{w}" height="{h}" fill="url(#bgGrad)"/>'
        f'{build_starfield(w, h)}'
        f'{build_ships(w)}'
        f'{build_corner_brackets(w, h, PALETTE["accent"])}'
        f'{terminal_svg}'
        f'{radar_svg}'
        f'{legend}'
        f'</svg>'
    )


def parse_args():
    p = argparse.ArgumentParser(description="Build the arcade-terminal header.svg")
    p.add_argument("--handle", default="TomasPosada0626", help="short identity used only in aria-label/title metadata")
    p.add_argument("--linkedin", default="https://www.linkedin.com/in/tomasposadasuarez26/", help="exact text typed on the second terminal line")
    p.add_argument("--line3", default="Systems Engineering · EAFIT")
    p.add_argument("--status", default="BUILDING TOWARD FULL STACK DEVELOPER")
    p.add_argument("--github-user", dest="github_user", default="TomasPosada0626", help="GitHub login to fetch a live commit count for")
    p.add_argument("--commits", type=int, default=None, help="commit count to display; overrides a live fetch if given. Omit both this and a reachable GH_PAT to just skip that line")
    p.add_argument("--width", type=float, default=1200)
    p.add_argument("--height", type=float, default=320)
    p.add_argument("--type-cps", type=float, default=22, dest="type_cps", help="typing speed in characters/second")
    p.add_argument("--line-gap", type=float, default=0.18, dest="line_gap", help="pause in seconds between one line finishing and the next starting")
    p.add_argument("--output", default="assets/svg/header.svg")
    return p.parse_args()


def main():
    args = parse_args()

    total_commits = args.commits
    if total_commits is None:
        token = os.environ.get("GH_PAT")
        if token:
            try:
                total_commits = fetch_total_commits(args.github_user, token)
            except HeaderBuildError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(1)
        else:
            print("note: no --commits given and no GH_PAT in the environment -- the commits line will be omitted", file=sys.stderr)

    svg = build_svg(args, total_commits)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(svg, encoding="utf-8")
    tmp_path.replace(out_path)
    print(f"wrote {out_path} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
