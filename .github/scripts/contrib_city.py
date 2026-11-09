#!/usr/bin/env python3
"""Draw the 3D contribution city (assets/contrib-city-dark.svg and -light.svg).

Reads the last year of contributions from the GitHub GraphQL API and draws each day as an
isometric tower in a terminal window. Python standard library only.

  GITHUB_TOKEN=... python3 .github/scripts/contrib_city.py brixdorf assets
  python3 .github/scripts/contrib_city.py --sample assets        # made-up data, for previews
"""
import json
import math
import os
import random
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

W = 820
FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
THEMES = {
    "dark": dict(bg="#0d1117", border="#30363d", bar="#161b22", muted="#8b949e", text="#e6edf3",
                 green="#7ee787", ground="#30363d",
                 ramp=["#161b22", "#5b3a9e", "#7449cc", "#9a6cf0", "#d2a8ff"]),
    "light": dict(bg="#ffffff", border="#d0d7de", bar="#f6f8fa", muted="#57606a", text="#1f2328",
                  green="#1a7f37", ground="#d0d7de",
                  ramp=["#ebedf0", "#e2d6fb", "#c3a6f5", "#9a6ee8", "#8250df"]),
}
LOOP, FADE_AT = 20, 18.5  # seconds: one build-hold-fade cycle, and when the fade starts
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

QUERY = """query($login: String!) { user(login: $login) { contributionsCollection { contributionCalendar {
  totalContributions weeks { contributionDays { date weekday contributionCount contributionLevel } } } } } }"""


def fetch(login, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json",
                 "User-Agent": "contrib-city"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if "errors" in body:
        raise SystemExit(f"GitHub API error: {body['errors']}")
    cal = body["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = [[(d["weekday"], d["contributionCount"], LEVELS.get(d["contributionLevel"], 0))
              for d in w["contributionDays"]] for w in cal["weeks"]]
    return cal["totalContributions"], weeks


def sample():
    random.seed(7)
    end = date(2026, 11, 9)
    start = end - timedelta(days=(end.weekday() + 1) % 7 + 52 * 7)
    weeks, total = [], 0
    for w in range(53):
        week = []
        for r in range(7):
            i = w * 7 + r
            if start + timedelta(days=i) > end:
                break
            busy = 0.55 + 0.35 * math.sin(i / 40) + (0.25 if 0 < r < 6 else -0.2)
            n = 0 if random.random() > busy else int(random.expovariate(1 / 4)) + 1
            lv = 0 if not n else 1 if n <= 2 else 2 if n <= 4 else 3 if n <= 7 else 4
            week.append((r, n, lv))
            total += n
        weeks.append(week)
    return total, weeks


def shade(col, f):
    return "#%02x%02x%02x" % tuple(min(255, int(int(col[k:k + 2], 16) * f)) for k in (1, 3, 5))


def render(theme, total, weeks):
    c = THEMES[theme]
    s = 10.2                                   # half-width of a tile
    ox, oy = (W - 60 * s) / 2 + 7 * s, 150     # where week 0 / Sunday sits
    counts = sorted(n for wk in weeks for _, n, _ in wk if n)
    cap = counts[int(len(counts) * 0.95)] if counts else 1  # tallest tower = busy day, not one outlier
    h = 480
    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" role="img" '
        f'aria-label="3D city of {total:,} GitHub contributions in the last year; each day is a tower.">',
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{h - 1}" rx="10" fill="{c["bg"]}" stroke="{c["border"]}"/>',
        f'<path d="M10.5 0.5 H{W - 10.5} A10 10 0 0 1 {W - 0.5} 10.5 V32.5 H0.5 V10.5 A10 10 0 0 1 10.5 0.5 Z" '
        f'fill="{c["bar"]}"/>',
        f'<line x1="0.5" y1="32.5" x2="{W - 0.5}" y2="32.5" stroke="{c["border"]}"/>',
        '<circle cx="20" cy="16.5" r="6" fill="#ff5f57"/><circle cx="40" cy="16.5" r="6" fill="#febc2e"/>'
        '<circle cx="60" cy="16.5" r="6" fill="#28c840"/>',
        f'<g font-family="{FONT}">',
        f'<text x="{W / 2}" y="21.5" fill="{c["muted"]}" font-size="13" text-anchor="middle">'
        "romit@github: ~$ git log --since='1 year ago' | city</text>",
        f'<text x="38" y="60" font-size="13" fill="{c["green"]}">❯</text>',
        f'<text x="56" y="60" font-size="13" fill="{c["text"]}" font-weight="600">{total:,} contributions'
        f'<tspan fill="{c["muted"]}" font-weight="400"> in the last year</tspan></text>',
    ]
    tiles = [(w + r, w, r, n, lv) for w, wk in enumerate(weeks) for r, n, lv in wk]
    for _, w, r, n, lv in sorted(tiles):      # back to front, so nearer towers cover farther ones
        top = c["ramp"][lv] if lv else c["ground"]
        # square-root scale: quiet days still get a visible tower, busy days don't dwarf everything
        bh = 2 + (8 + 62 * math.sqrt(min(n, cap) / cap) if n else 0)
        x, y = ox + (w - r) * s, oy + (w + r) * s * 0.5
        # Build left to right, hold, fade out, repeat. Looping means someone who scrolls down
        # later still sees the city being built (an <img> animation starts on page load).
        a = 0.4 + (w - r + 6) * 0.075          # this tower starts rising (screen left -> right)
        b = a + 0.8                            # ...and has landed
        kt = f"0;{a / LOOP:.4f};{b / LOOP:.4f};{FADE_AT / LOOP:.4f};{(FADE_AT + 0.8) / LOOP:.4f};1"
        ks = "0 0 1 1;0.2 0.8 0.2 1;0 0 1 1;0.4 0 1 1;0 0 1 1"
        p.append(
            f'<g opacity="0" transform="translate(0 -24)">'
            f'<animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes="{kt}" dur="{LOOP}s" '
            f'repeatCount="indefinite" calcMode="spline" keySplines="{ks}"/>'
            f'<animateTransform attributeName="transform" type="translate" '
            f'values="0 -24;0 -24;0 0;0 0;0 0;0 0" keyTimes="{kt}" dur="{LOOP}s" '
            f'repeatCount="indefinite" calcMode="spline" keySplines="{ks}"/>'
            f'<polygon points="{x - s:.1f},{y + s / 2 - bh:.1f} {x:.1f},{y + s - bh:.1f} {x:.1f},{y + s:.1f} '
            f'{x - s:.1f},{y + s / 2:.1f}" fill="{shade(top, 0.7)}"/>'
            f'<polygon points="{x + s:.1f},{y + s / 2 - bh:.1f} {x:.1f},{y + s - bh:.1f} {x:.1f},{y + s:.1f} '
            f'{x + s:.1f},{y + s / 2:.1f}" fill="{shade(top, 0.55)}"/>'
            f'<polygon points="{x:.1f},{y - bh:.1f} {x + s:.1f},{y + s / 2 - bh:.1f} {x:.1f},{y + s - bh:.1f} '
            f'{x - s:.1f},{y + s / 2 - bh:.1f}" fill="{top}"/></g>')
    p += ["</g>", "</svg>"]
    return "\n".join(p) + "\n"


def main():
    args = sys.argv[1:]
    if args and args[0] == "--sample":
        total, weeks = sample()
        out = Path(args[1] if len(args) > 1 else "assets")
    else:
        login, out = args[0], Path(args[1] if len(args) > 1 else "assets")
        token = os.environ.get("CONTRIB_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("Set GITHUB_TOKEN (or CONTRIB_TOKEN)")
        total, weeks = fetch(login, token)
    out.mkdir(parents=True, exist_ok=True)
    for t in THEMES:
        (out / f"contrib-city-{t}.svg").write_text(render(t, total, weeks), encoding="utf-8")
    print(f"drew {total} contributions into {out}/contrib-city-{{dark,light}}.svg")


if __name__ == "__main__":
    main()
