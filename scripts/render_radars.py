#!/usr/bin/env python3
"""Render blue, theme-aware radar cards for Ahmed's profile README."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.request
from html import escape
from pathlib import Path


THEMES = {
    "dark": {
        "bg": "#061A2B",
        "panel": "#08243A",
        "grid": "#1A567E",
        "text": "#F4FBFF",
        "muted": "#8AC9EE",
        "accent": "#21A6F6",
        "accent2": "#74D4FF",
        "shadow": "#02101B",
    },
    "light": {
        "bg": "#F3FAFF",
        "panel": "#FFFFFF",
        "grid": "#B6DDF4",
        "text": "#061A2B",
        "muted": "#0B5E94",
        "accent": "#158DD7",
        "accent2": "#0B74B8",
        "shadow": "#9CCBE8",
    },
}

EXCLUDED_LANGUAGES = {
    "HTML",
    "CSS",
    "Shell",
    "Makefile",
    "Dockerfile",
    "Batchfile",
    "Procfile",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def request_json(url: str, token: str | None) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "codewithahmed-profile-radar",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def live_language_data(username: str, token: str | None, limit: int = 5) -> dict:
    repos = request_json(
        f"https://api.github.com/users/{username}/repos?per_page=100&type=owner&sort=updated",
        token,
    )
    totals: dict[str, int] = {}
    for repo in repos:
        if repo.get("fork") or repo.get("archived"):
            continue
        languages = request_json(repo["languages_url"], token)
        for language, byte_count in languages.items():
            if language in EXCLUDED_LANGUAGES:
                continue
            totals[language] = totals.get(language, 0) + int(byte_count)

    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    if len(ranked) < 5:
        raise RuntimeError("Not enough public language data to render the radar")

    total_bytes = sum(value for _, value in ranked)
    maximum = max(value for _, value in ranked)
    axes = []
    for label, byte_count in ranked:
        share = 100 * byte_count / total_bytes
        curved = 100 * ((byte_count / maximum) ** 0.42)
        short_label = "Jupyter" if label == "Jupyter Notebook" else label
        axes.append(
            {
                "label": short_label,
                "value": round(curved, 1),
                "display": f"{share:.1f}%",
            }
        )
    return {
        "title": "Code Footprint",
        "subtitle": "Live bytes across public repositories",
        "axes": axes,
    }


def point(cx: float, cy: float, radius: float, index: int, count: int) -> tuple[float, float]:
    angle = -math.pi / 2 + (2 * math.pi * index / count)
    return cx + radius * math.cos(angle), cy + radius * math.sin(angle)


def points_string(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def render_card(data: dict, theme_name: str) -> str:
    palette = THEMES[theme_name]
    axes = data["axes"]
    count = len(axes)
    if not 5 <= count <= 8:
        raise ValueError("Radar charts must contain between five and eight axes")

    width, height = 520, 500
    cx, cy, radius = 260, 285, 132
    elements: list[str] = []

    for level in range(1, 6):
        level_radius = radius * level / 5
        polygon = [point(cx, cy, level_radius, i, count) for i in range(count)]
        opacity = 0.35 if level < 5 else 0.75
        elements.append(
            f'<polygon points="{points_string(polygon)}" fill="none" '
            f'stroke="{palette["grid"]}" stroke-width="1.2" opacity="{opacity}" />'
        )

    for index in range(count):
        x, y = point(cx, cy, radius, index, count)
        elements.append(
            f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" '
            f'stroke="{palette["grid"]}" stroke-width="1" opacity="0.7" />'
        )

    value_points = []
    for index, axis in enumerate(axes):
        value = max(0.0, min(100.0, float(axis["value"])))
        value_points.append(point(cx, cy, radius * value / 100, index, count))

    polygon_points = points_string(value_points)
    elements.append(
        f'<polygon class="signal" points="{polygon_points}" fill="url(#signalFill)" '
        f'stroke="{palette["accent2"]}" stroke-width="3" stroke-linejoin="round" />'
    )
    for x, y in value_points:
        elements.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{palette["accent2"]}" '
            f'stroke="{palette["panel"]}" stroke-width="2" />'
        )

    for index, axis in enumerate(axes):
        x, y = point(cx, cy, radius + 43, index, count)
        cosine = math.cos(-math.pi / 2 + (2 * math.pi * index / count))
        anchor = "middle" if abs(cosine) < 0.25 else ("start" if cosine > 0 else "end")
        baseline_adjustment = 4 if y >= cy else 0
        label = escape(str(axis["label"]))
        display = escape(str(axis.get("display", f'{float(axis["value"]):.0f}%')))
        elements.append(
            f'<text x="{x:.1f}" y="{y + baseline_adjustment:.1f}" text-anchor="{anchor}" '
            f'class="axis-label">{label}</text>'
        )
        elements.append(
            f'<text x="{x:.1f}" y="{y + baseline_adjustment + 18:.1f}" text-anchor="{anchor}" '
            f'class="axis-value">{display}</text>'
        )

    title = escape(str(data.get("title", "Skill Radar")))
    subtitle = escape(str(data.get("subtitle", "Five-axis build signals")))
    body = "\n    ".join(elements)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="520" height="500" viewBox="0 0 520 500" role="img" aria-labelledby="title desc">
  <title id="title">{title}</title>
  <desc id="desc">{subtitle}</desc>
  <defs>
    <linearGradient id="panelFill" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{palette['panel']}" />
      <stop offset="1" stop-color="{palette['bg']}" />
    </linearGradient>
    <radialGradient id="signalFill">
      <stop offset="0" stop-color="{palette['accent2']}" stop-opacity="0.5" />
      <stop offset="1" stop-color="{palette['accent']}" stop-opacity="0.18" />
    </radialGradient>
    <filter id="glow" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="7" result="blur" />
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <style>
    text {{ font-family: Inter, Segoe UI, Arial, sans-serif; }}
    .title {{ fill: {palette['text']}; font-size: 25px; font-weight: 760; letter-spacing: 0.4px; }}
    .subtitle {{ fill: {palette['muted']}; font-size: 13px; font-weight: 600; letter-spacing: 1px; }}
    .axis-label {{ fill: {palette['text']}; font-size: 14px; font-weight: 700; }}
    .axis-value {{ fill: {palette['accent2']}; font-size: 12px; font-weight: 700; }}
    .signal {{ filter: url(#glow); animation: pulse 3.6s ease-in-out infinite; transform-origin: 260px 285px; }}
    @keyframes pulse {{ 0%, 100% {{ opacity: .82; }} 50% {{ opacity: 1; }} }}
  </style>
  <rect x="6" y="6" width="508" height="488" rx="24" fill="{palette['shadow']}" opacity="0.25" />
  <rect x="3" y="3" width="508" height="488" rx="24" fill="url(#panelFill)" stroke="{palette['grid']}" stroke-width="1.5" />
  <path d="M28 82 H492" stroke="{palette['grid']}" stroke-width="1" opacity="0.72" />
  <circle cx="31" cy="31" r="5" fill="{palette['accent2']}" />
  <circle cx="48" cy="31" r="5" fill="{palette['accent']}" opacity="0.75" />
  <text x="260" y="38" text-anchor="middle" class="title">{title}</text>
  <text x="260" y="62" text-anchor="middle" class="subtitle">{subtitle.upper()}</text>
    {body}
  <text x="260" y="478" text-anchor="middle" class="subtitle">BLUE SIGNAL ARRAY • 5 AXES</text>
</svg>
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("assets/skills.json"))
    parser.add_argument("--language-seed", type=Path, default=Path("assets/languages.json"))
    parser.add_argument("--username")
    parser.add_argument("--out", type=Path, default=Path("assets"))
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    skill_data = load_json(args.data)
    language_data = load_json(args.language_seed)

    if args.username and not args.offline:
        try:
            language_data = live_language_data(
                args.username,
                os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"),
            )
            args.language_seed.write_text(
                json.dumps(language_data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print("Fetched live language bytes from GitHub", file=sys.stderr)
        except (urllib.error.URLError, TimeoutError, RuntimeError, KeyError) as error:
            print(f"Live language sync unavailable; using saved snapshot: {error}", file=sys.stderr)

    args.out.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        (args.out / f"radar-skills-{theme}.svg").write_text(
            render_card(skill_data, theme), encoding="utf-8"
        )
        (args.out / f"radar-languages-{theme}.svg").write_text(
            render_card(language_data, theme), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
