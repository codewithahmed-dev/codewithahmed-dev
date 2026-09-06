#!/usr/bin/env python3
"""Render an animated blue isometric GitHub contribution calendar."""

from __future__ import annotations

import argparse
import json
import math
import os
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path


THEMES = {
    "dark": {
        "bg0": "#04131F",
        "bg1": "#082D48",
        "panel": "#071E31",
        "border": "#1A628F",
        "grid": "#164B6B",
        "text": "#F4FBFF",
        "muted": "#8AC9EE",
        "empty": "#0B2A41",
        "tops": ["#164C6E", "#0B74B8", "#158FD7", "#21A6F6", "#74D4FF"],
    },
    "light": {
        "bg0": "#F3FAFF",
        "bg1": "#DDF2FF",
        "panel": "#FFFFFF",
        "border": "#8AC9EE",
        "grid": "#B6DDF4",
        "text": "#061A2B",
        "muted": "#0B5E94",
        "empty": "#D9EDF9",
        "tops": ["#B9E4FA", "#74D4FF", "#42B9F4", "#21A6F6", "#0B74B8"],
    },
}


def post_graphql(query: str, variables: dict, token: str) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "codewithahmed-profile-isocalendar",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError(result["errors"][0].get("message", "GitHub GraphQL request failed"))
    return result["data"]


def fetch_calendar(username: str, token: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=365)
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionCount
                weekday
              }
            }
          }
        }
      }
    }
    """
    variables = {
        "login": username,
        "from": start.isoformat().replace("+00:00", "Z"),
        "to": now.isoformat().replace("+00:00", "Z"),
    }
    data = post_graphql(query, variables, token)
    user = data.get("user")
    if not user:
        raise RuntimeError(f"GitHub user not found: {username}")
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [day for week in weeks for day in week["contributionDays"]]


def demo_calendar() -> list[dict]:
    today = date.today()
    start = today - timedelta(days=365)
    days = []
    for offset in range(366):
        current = start + timedelta(days=offset)
        pulse = (offset * 17 + current.month * 11) % 29
        count = 0 if pulse < 16 else 1 + (pulse % 7)
        days.append(
            {
                "date": current.isoformat(),
                "contributionCount": count,
                "weekday": (current.weekday() + 1) % 7,
            }
        )
    return days


def calendar_stats(days: list[dict], demo: bool) -> dict:
    ordered = sorted(days, key=lambda item: item["date"])
    counts = [int(item["contributionCount"]) for item in ordered]
    if demo:
        return {
            "total": "LIVE SYNC",
            "current": "READY",
            "best": "AFTER PUBLISH",
            "highest": "AUTO",
            "average": "12H REFRESH",
        }

    best = 0
    running = 0
    for count in counts:
        if count:
            running += 1
            best = max(best, running)
        else:
            running = 0

    today = date.today()
    by_date = {date.fromisoformat(item["date"]): int(item["contributionCount"]) for item in ordered}
    cursor = today if by_date.get(today, 0) else today - timedelta(days=1)
    current = 0
    while by_date.get(cursor, 0):
        current += 1
        cursor -= timedelta(days=1)

    total = sum(counts)
    return {
        "total": f"{total:,}",
        "current": f"{current} days",
        "best": f"{best} days",
        "highest": str(max(counts, default=0)),
        "average": f"{total / max(1, len(counts)):.2f}",
    }


def hex_shade(hex_color: str, factor: float) -> str:
    raw = hex_color.lstrip("#")
    channels = [int(raw[index : index + 2], 16) for index in (0, 2, 4)]
    return "#" + "".join(f"{max(0, min(255, round(value * factor))):02X}" for value in channels)


def contribution_level(count: int, maximum: int) -> int:
    if count <= 0:
        return 0
    return max(1, min(4, math.ceil(4 * count / max(1, maximum))))


def render_svg(days: list[dict], username: str, theme_name: str, demo: bool) -> str:
    palette = THEMES[theme_name]
    stats = calendar_stats(days, demo)
    parsed = [
        {
            "date": date.fromisoformat(item["date"]),
            "count": int(item["contributionCount"]),
            "weekday": int(item["weekday"]),
        }
        for item in days
    ]
    parsed.sort(key=lambda item: item["date"])
    first_sunday = parsed[0]["date"] - timedelta(days=parsed[0]["weekday"])
    maximum = max((item["count"] for item in parsed), default=1)
    cubes = []

    for item in parsed:
        week = (item["date"] - first_sunday).days // 7
        weekday = item["weekday"]
        x = 68 + week * 11.0 + weekday * 5.8
        y = 301 - week * 3.55 + weekday * 3.55
        level = contribution_level(item["count"], maximum)
        top_color = palette["empty"] if level == 0 else palette["tops"][level]
        height = 0 if level == 0 else 3 + level * 4.8
        half_width, half_height = 5.0, 2.8
        top_y = y - height
        top = (
            f"{x:.1f},{top_y - half_height:.1f} "
            f"{x + half_width:.1f},{top_y:.1f} "
            f"{x:.1f},{top_y + half_height:.1f} "
            f"{x - half_width:.1f},{top_y:.1f}"
        )
        delay = ((week * 7 + weekday) % 42) * 0.018
        if level == 0:
            cubes.append(
                f'<polygon points="{top}" fill="{top_color}" stroke="{palette["grid"]}" '
                f'stroke-width="0.45" opacity="0.72"><title>{item["date"]}: 0 contributions</title></polygon>'
            )
            continue
        left = (
            f"{x - half_width:.1f},{top_y:.1f} {x:.1f},{top_y + half_height:.1f} "
            f"{x:.1f},{y + half_height:.1f} {x - half_width:.1f},{y:.1f}"
        )
        right = (
            f"{x + half_width:.1f},{top_y:.1f} {x:.1f},{top_y + half_height:.1f} "
            f"{x:.1f},{y + half_height:.1f} {x + half_width:.1f},{y:.1f}"
        )
        cubes.append(
            f'<g class="cube" style="animation-delay:{delay:.3f}s">'
            f'<polygon points="{left}" fill="{hex_shade(top_color, 0.62)}" />'
            f'<polygon points="{right}" fill="{hex_shade(top_color, 0.78)}" />'
            f'<polygon points="{top}" fill="{top_color}" stroke="{palette["tops"][4]}" stroke-width="0.55">'
            f'<title>{item["date"]}: {item["count"]} contributions</title></polygon></g>'
        )

    stat_rows = [
        ("TOTAL CONTRIBUTIONS", stats["total"]),
        ("CURRENT STREAK", stats["current"]),
        ("BEST STREAK", stats["best"]),
        ("HIGHEST IN A DAY", stats["highest"]),
        ("AVERAGE PER DAY", stats["average"]),
    ]
    stats_svg = []
    for index, (label, value) in enumerate(stat_rows):
        y = 126 + index * 55
        stats_svg.append(
            f'<text x="772" y="{y}" class="stat-label">{escape(label)}</text>'
            f'<text x="772" y="{y + 25}" class="stat-value">{escape(value)}</text>'
        )

    cube_markup = "\n    ".join(cubes)
    stat_markup = "\n    ".join(stats_svg)
    updated = datetime.now(timezone.utc).strftime("%d %b %Y • %H:%M UTC")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="440" viewBox="0 0 1040 440" role="img" aria-labelledby="title desc">
  <title id="title">{escape(username)} 3D contribution city</title>
  <desc id="desc">A blue isometric full-year GitHub contribution calendar with streak and activity statistics.</desc>
  <defs>
    <linearGradient id="background" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{palette['bg0']}" />
      <stop offset="1" stop-color="{palette['bg1']}" />
    </linearGradient>
    <filter id="softGlow" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="2.7" result="blur" />
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  <style>
    text {{ font-family: Inter, Segoe UI, Arial, sans-serif; }}
    .title {{ fill: {palette['text']}; font-size: 26px; font-weight: 760; letter-spacing: .5px; }}
    .subtitle {{ fill: {palette['muted']}; font-size: 12px; font-weight: 650; letter-spacing: 1.5px; }}
    .stat-label {{ fill: {palette['muted']}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
    .stat-value {{ fill: {palette['text']}; font-size: 20px; font-weight: 760; }}
    .cube {{ opacity: 1; animation: rise .9s ease both; filter: url(#softGlow); }}
    @keyframes rise {{ from {{ opacity: 0; transform: translateY(9px); }} to {{ opacity: 1; transform: translateY(0); }} }}
  </style>
  <rect x="3" y="3" width="1034" height="434" rx="26" fill="url(#background)" stroke="{palette['border']}" stroke-width="2" />
  <circle cx="31" cy="30" r="5" fill="{palette['tops'][4]}" />
  <circle cx="48" cy="30" r="5" fill="{palette['tops'][3]}" opacity=".8" />
  <text x="520" y="39" text-anchor="middle" class="title">3D Contribution City</text>
  <text x="520" y="62" text-anchor="middle" class="subtitle">FULL YEAR ACTIVITY • LIVE STREAK SIGNALS</text>
  <text x="70" y="103" class="subtitle">CONTRIBUTION CALENDAR</text>
  <rect x="754" y="88" width="250" height="295" rx="18" fill="{palette['panel']}" stroke="{palette['border']}" stroke-width="1.2" />
  <text x="772" y="106" class="subtitle">COMMIT STREAKS</text>
  <g aria-label="isometric contribution calendar">
    {cube_markup}
  </g>
  <g aria-label="contribution statistics">
    {stat_markup}
  </g>
  <g transform="translate(70 395)">
    <text x="0" y="10" class="subtitle">LESS</text>
    <polygon points="50,4 56,1 62,4 56,7" fill="{palette['empty']}" />
    <polygon points="70,4 76,1 82,4 76,7" fill="{palette['tops'][1]}" />
    <polygon points="90,4 96,1 102,4 96,7" fill="{palette['tops'][2]}" />
    <polygon points="110,4 116,1 122,4 116,7" fill="{palette['tops'][3]}" />
    <polygon points="130,4 136,1 142,4 136,7" fill="{palette['tops'][4]}" />
    <text x="154" y="10" class="subtitle">MORE</text>
  </g>
  <text x="1002" y="413" text-anchor="end" class="subtitle">UPDATED {updated}</text>
</svg>
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="codewithahmed-dev")
    parser.add_argument("--out", type=Path, default=Path("assets/metrics-isocalendar"))
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if args.demo:
        days = demo_calendar()
    else:
        if not token:
            raise RuntimeError("GITHUB_TOKEN is required for a live contribution calendar")
        days = fetch_calendar(args.username, token)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        Path(f"{args.out}-{theme}.svg").write_text(
            render_svg(days, args.username, theme, args.demo), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
