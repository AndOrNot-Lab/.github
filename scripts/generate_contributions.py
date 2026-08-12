#!/usr/bin/env python3
"""Generate a contribution calendar for an organization's owned public repos."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path


API_ROOT = "https://api.github.com"
def api_get(path: str, token: str) -> object:
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "andornot-contribution-chart",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {error.code} for {path}: {detail}") from error


def paginated(path: str, token: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    page = 1
    separator = "&" if "?" in path else "?"
    while True:
        batch = api_get(f"{path}{separator}per_page=100&page={page}", token)
        if not isinstance(batch, list):
            raise RuntimeError(f"Expected a list from GitHub API: {path}")
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def collect(org: str, token: str, today: date) -> tuple[Counter[date], list[str]]:
    repos = paginated(
        f"/orgs/{urllib.parse.quote(org)}/repos?type=public&sort=updated",
        token,
    )
    owned = [
        repo
        for repo in repos
        if not repo.get("fork")
        and not repo.get("archived")
    ]

    start = today - timedelta(days=363)
    counts: Counter[date] = Counter()
    names: list[str] = []
    since = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc).isoformat()
    until = datetime.combine(today + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).isoformat()

    for repo in owned:
        name = str(repo["name"])
        names.append(name)
        commits = paginated(
            "/repos/"
            f"{urllib.parse.quote(org)}/{urllib.parse.quote(name)}"
            "/commits?"
            f"since={urllib.parse.quote(since)}&until={urllib.parse.quote(until)}",
            token,
        )
        for commit in commits:
            author = commit.get("author")
            if not isinstance(author, dict):
                continue
            login = str(author.get("login", ""))
            if login.endswith("[bot]"):
                continue
            commit_data = commit.get("commit")
            if not isinstance(commit_data, dict):
                continue
            author_data = commit_data.get("author")
            if not isinstance(author_data, dict) or not author_data.get("date"):
                continue
            committed = datetime.fromisoformat(str(author_data["date"]).replace("Z", "+00:00"))
            counts[committed.date()] += 1

    return counts, sorted(names, key=str.casefold)


def level(value: int, maximum: int) -> int:
    if value <= 0 or maximum <= 0:
        return 0
    ratio = value / maximum
    if ratio <= 0.25:
        return 1
    if ratio <= 0.5:
        return 2
    if ratio <= 0.75:
        return 3
    return 4


def render(org: str, counts: Counter[date], repos: list[str], today: date) -> str:
    start = today - timedelta(days=363)
    start -= timedelta(days=(start.weekday() + 1) % 7)
    end = start + timedelta(days=370)
    total = sum(counts.values())
    active_days = sum(1 for value in counts.values() if value)
    maximum = max(counts.values(), default=0)
    weeks = 53
    cell = 10
    gap = 3
    grid_x = 162
    grid_y = 112
    width = 1000
    height = 280

    cells: list[str] = []
    current = start
    while current <= end:
        week = (current - start).days // 7
        weekday = (current.weekday() + 1) % 7
        value = counts.get(current, 0) if current <= today else 0
        css_class = f"l{level(value, maximum)}" if current <= today else "future"
        x = grid_x + week * (cell + gap)
        y = grid_y + weekday * (cell + gap)
        cells.append(
            f'<rect class="day {css_class}" x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2">'
            f"<title>{escape(current.isoformat())}: {value} commits</title></rect>"
        )
        current += timedelta(days=1)

    month_labels: list[str] = []
    previous_month = -1
    for week in range(weeks):
        week_date = start + timedelta(days=week * 7)
        if week_date.month != previous_month and week_date.day <= 7:
            x = grid_x + week * (cell + gap)
            month_labels.append(
                f'<text class="axis" x="{x}" y="99">{week_date.strftime("%b")}</text>'
            )
            previous_month = week_date.month

    repo_text = ", ".join(repos) if repos else "No owned public project repositories yet"
    updated = today.isoformat()
    return f'''<svg width="1000" height="280" viewBox="0 0 1000 280" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">{escape(org)} owned-project contribution activity</title>
  <desc id="desc">{total} commits across {len(repos)} organization-owned public repositories in the last 52 weeks. Forks and bots are excluded.</desc>
  <style>
    :root {{ --bg:#f6f8fa; --surface:#ffffff; --border:#d0d7de; --text:#1f2328; --muted:#59636e; --empty:#ebedf0; --l1:#aceebb; --l2:#4ac26b; --l3:#2da44e; --l4:#116329; }}
    @media (prefers-color-scheme:dark) {{ :root {{ --bg:#0d1117; --surface:#161b22; --border:#30363d; --text:#f0f6fc; --muted:#8b949e; --empty:#21262d; --l1:#0e4429; --l2:#006d32; --l3:#26a641; --l4:#39d353; }} }}
    .frame {{ fill:var(--bg); stroke:var(--border); }} .surface {{ fill:var(--surface); stroke:var(--border); }}
    .text {{ fill:var(--text); font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
    .muted,.axis {{ fill:var(--muted); font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
    .axis {{ font-size:11px; }} .day {{ fill:var(--empty); }} .l1 {{ fill:var(--l1); }} .l2 {{ fill:var(--l2); }} .l3 {{ fill:var(--l3); }} .l4 {{ fill:var(--l4); }} .future {{ fill:transparent; }}
  </style>
  <rect class="frame" x="1" y="1" width="998" height="278" rx="8"/>
  <rect class="surface" x="24" y="22" width="952" height="236" rx="6"/>
  <text class="text" x="48" y="57" font-size="18" font-weight="700">ORGANIZATION ACTIVITY / 52 WEEKS</text>
  <text class="muted" x="48" y="79" font-size="12">Organization-owned public repositories only; forks and bots excluded</text>
  <text class="text" x="48" y="128" font-size="28" font-weight="700">{total}</text>
  <text class="muted" x="48" y="147" font-size="11">COMMITS</text>
  <text class="text" x="48" y="184" font-size="22" font-weight="700">{active_days}</text>
  <text class="muted" x="48" y="202" font-size="11">ACTIVE DAYS</text>
  {''.join(month_labels)}
  <text class="axis" x="128" y="134">Mon</text><text class="axis" x="128" y="160">Wed</text><text class="axis" x="128" y="186">Fri</text>
  {''.join(cells)}
  <text class="muted" x="162" y="230" font-size="11">Included now: {escape(repo_text)}</text>
  <text class="muted" x="952" y="230" font-size="11" text-anchor="end">Updated {updated}</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", default="AndOrNot-Lab")
    parser.add_argument("--out", default="profile/assets/contributions.svg")
    parser.add_argument("--today", help="Override current UTC date (YYYY-MM-DD)")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 2
    today = date.fromisoformat(args.today) if args.today else datetime.now(timezone.utc).date()
    counts, repos = collect(args.org, token, today)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(args.org, counts, repos, today), encoding="utf-8", newline="\n")
    print(f"wrote {output}: {sum(counts.values())} commits across {len(repos)} repos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
