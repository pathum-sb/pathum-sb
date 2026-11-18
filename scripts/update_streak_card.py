#!/usr/bin/env python3
"""Create streak cards from the authenticated GitHub contribution calendar."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import os
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOGIN = os.environ.get("GH_PROFILE_USER", "pathum-sb")


def get_token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    return subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def graphql(query: str) -> dict:
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors") or not payload.get("data", {}).get("user"):
        raise RuntimeError("GitHub did not return contribution history")
    return payload["data"]["user"]


def summarize(lines: list[str]) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


TOKEN = get_token()
today = datetime.now(timezone.utc).date()

# Derive the history range from the account instead of hard-coding a start year.
meta = graphql(f'query {{ user(login:"{LOGIN}") {{ createdAt }} }}')
start_year = int(meta["createdAt"][:4])

collections = " ".join(
    f'y{year}: contributionsCollection(from:"{year}-01-01T00:00:00Z",to:"{year}-12-31T23:59:59Z") '
    "{ contributionCalendar { weeks { contributionDays { date contributionCount } } } }"
    for year in range(start_year, today.year + 1)
)
user = graphql(f'query {{ user(login:"{LOGIN}") {{ {collections} }} }}')

days = {}
for year in range(start_year, today.year + 1):
    for week in user[f"y{year}"]["contributionCalendar"]["weeks"]:
        for item in week["contributionDays"]:
            days[item["date"]] = item["contributionCount"]
ordered_days = sorted(days)
total = sum(days.values())

best_length = 0
best_start = best_end = None
current_length = 0
current_start = None
for day_text in ordered_days:
    if days[day_text] > 0:
        if current_length == 0:
            current_start = day_text
        current_length += 1
        if current_length > best_length:
            best_length, best_start, best_end = current_length, current_start, day_text
    else:
        current_length = 0
        current_start = None

# GitHub's calendar is UTC-based, and an ongoing streak should still count
# before today's first contribution arrives.
end = today if days.get(today.isoformat(), 0) > 0 else today - timedelta(days=1)
current_length = 0
cursor = end
while days.get(cursor.isoformat(), 0) > 0:
    current_length += 1
    cursor -= timedelta(days=1)
if current_length == 0:
    current_range = "No active streak"
elif current_length == 1:
    current_range = end.strftime("%b %-d")
else:
    current_range = f"{end - timedelta(days=current_length - 1):%b %-d} - {end:%b %-d}"

if best_length == 0:
    longest_range = "No contributions yet"
else:
    longest_range = f"{date.fromisoformat(best_start):%b %-d} - {date.fromisoformat(best_end):%b %-d}"
active_days = [day for day in ordered_days if days[day] > 0]
history_range = (
    f"{date.fromisoformat(active_days[0]):%b %-d, %Y} - Present"
    if active_days
    else "No contributions yet"
)

summarize([
    "### Streak card",
    f"- Total contributions: **{total}**",
    f"- Current streak: **{current_length}**",
    f"- Longest streak: **{best_length}**",
    "",
])


def replace_section(svg: str, comment: str, value: str) -> str:
    pattern = rf"(<!-- {comment} -->\s*<g[^>]*>\s*<text[^>]*>\s*)(.*?)(\s*</text>)"
    updated, count = re.subn(pattern, rf"\g<1>{value}\g<3>", svg, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Could not update {comment}")
    return updated


for theme, params in {
    "dark": {"background": "09142E", "currStreakNum": "FFFFFF", "sideNums": "FFFFFF", "sideLabels": "FFFFFF", "dates": "94A3B8"},
    "light": {"background": "FFFFFF", "currStreakNum": "0B1F4B", "sideNums": "0B1F4B", "sideLabels": "0B1F4B", "dates": "475569"},
}.items():
    query_params = {"user": LOGIN, "hide_border": "true", "disable_animations": "true", "ring": "0066FF", "fire": "0066FF", "currStreakLabel": "0066FF", **params}
    url = "https://streak-stats.demolab.com?" + urlencode(query_params)
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response:
        svg = response.read().decode("utf-8")
    svg = replace_section(svg, "Total Contributions big number", str(total))
    svg = replace_section(svg, "Total Contributions range", history_range)
    svg = replace_section(svg, "Current Streak big number", str(current_length))
    svg = replace_section(svg, "Current Streak range", current_range)
    svg = replace_section(svg, "Longest Streak big number", str(best_length))
    svg = replace_section(svg, "Longest Streak range", longest_range)
    (ROOT / "assets" / f"streak-{theme}.svg").write_text(svg, encoding="utf-8")
    print(f"Updated assets/streak-{theme}.svg")
