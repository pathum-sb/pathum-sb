#!/usr/bin/env python3
"""Refresh themed GitHub stats cards while keeping the logo separate from the rank ring."""
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import os
import subprocess
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
THEMES = {
    "dark": {"bg_color": "09142E", "title_color": "3B82F6", "text_color": "38BDAE", "icon_color": "BF91F3"},
    "light": {"bg_color": "FFFFFF", "title_color": "0066FF", "text_color": "0B1F4B", "icon_color": "0066FF"},
}
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
if not token:
    token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
year = datetime.now(timezone.utc).year
year_queries = " ".join(
    f'''y{y}: contributionsCollection(from:"{y}-01-01T00:00:00Z",to:"{y}-12-31T23:59:59Z") {{
      totalCommitContributions
      commitContributionsByRepository(maxRepositories: 100) {{ repository {{ nameWithOwner }} }}
      pullRequestContributionsByRepository(maxRepositories: 100) {{ repository {{ nameWithOwner }} }}
    }}'''
    for y in range(2024, year + 1)
)
query = f'''query {{ user(login:"pathum-sb") {{
  pullRequests {{ totalCount }}
  repositories(first:100,privacy:PUBLIC,isFork:false,ownerAffiliations:OWNER) {{ totalCount nodes {{ stargazerCount }} }}
  {year_queries}
}} }}'''
request = Request("https://api.github.com/graphql", data=json.dumps({"query": query}).encode(),
                  headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
with urlopen(request, timeout=30) as response:
    result = json.load(response)
if result.get("errors") or not result.get("data", {}).get("user"):
    raise RuntimeError("GitHub did not return complete stats")
user = result["data"]["user"]
contributed_repositories = set()
for y in range(2024, year + 1):
    collection = user[f"y{y}"]
    for key in ("commitContributionsByRepository", "pullRequestContributionsByRepository"):
        contributed_repositories.update(item["repository"]["nameWithOwner"] for item in collection[key])
metrics = {
    "stars": sum(repo["stargazerCount"] for repo in user["repositories"]["nodes"]),
    "commits": sum(user[f"y{y}"]["totalCommitContributions"] for y in range(2024, year + 1)),
    "prs": user["pullRequests"]["totalCount"],
    "contribs": len(contributed_repositories),
}

for theme, colors in THEMES.items():
    params = {
        "username": "pathum-sb",
        "show_icons": "true",
        "hide": "issues",
        "rank_icon": "github",
        "custom_title": "Stats",
        "card_width": "410",
        "line_height": "45",
        "hide_border": "true",
        "disable_animations": "true",
        "text_bold": "false",
        "ring_color": colors["bg_color"],
        **colors,
    }
    url = "https://github-readme-stats.vercel.app/api?" + urlencode(params)
    target = ROOT / "assets" / f"stats-{theme}.svg"
    try:
        with urlopen(url, timeout=30) as response:
            svg = response.read().decode("utf-8")
        if "Something went wrong" in svg:
            raise RuntimeError("Stats service error")
    except Exception:
        svg = target.read_text(encoding="utf-8")
    root = ET.fromstring(svg)
    style = next(el for el in root.iter() if el.tag == f"{{{SVG_NS}}}style")
    style.text = style.text.replace("font: 600 18px", "font: 600 22px")
    style.text = style.text.replace("font: 600 14px", "font: 400 24px")
    style.text = style.text.replace(".stat { font-size:12px; }", ".stat { font-size:24px; }")
    title = next(el for el in root.iter() if el.get("data-testid") == "card-title")
    title.set("transform", "translate(36, 43)")
    body = next(el for el in root.iter() if el.get("data-testid") == "main-card-body")
    body.set("transform", "translate(0, 80)")
    logo = next((el for el in root.iter() if el.get("data-testid") == "github-rank-icon"), None)
    if logo is None:
        raise RuntimeError(f"Stats service did not return the GitHub logo for {theme}")
    rank = next((el for el in root.iter() if el.get("data-testid") == "rank-circle"), None)
    if rank is None:
        raise RuntimeError(f"Stats service did not return the rank group for {theme}")
    rank.set("transform", "translate(353, 60)")
    for child in list(rank):
        if child.tag == f"{{{SVG_NS}}}circle":
            rank.remove(child)
    logo.set("x", "-65")
    logo.set("y", "-57")
    logo.set("width", "120")
    logo.set("height", "120")
    for path in logo.iter(f"{{{SVG_NS}}}path"):
        path.set("fill", f"#{colors['icon_color']}")
    labels = {
        "Total Stars Earned:": "Total Stars:",
        "Total Commits (last year):": "Total Commits:",
        "Contributed to (last year):": "Repos contributed to:",
    }
    for el in root.iter():
        if el.tag == f"{{{SVG_NS}}}g" and el.get("transform") == "translate(25, 0)":
            el.set("transform", "translate(36, 0)")
        if el.tag == f"{{{SVG_NS}}}text":
            if el.text in labels:
                el.text = labels[el.text]
            if el.get("class", "").startswith("stat "):
                el.set("y", "22")
            if el.get("data-testid") in {"stars", "commits", "prs", "contribs"}:
                el.set("x", "205")
        if el.get("data-testid") == "icon":
            el.set("y", "4")
        if el.get("data-testid") in metrics:
            el.text = str(metrics[el.get("data-testid")])
        if el.tag == f"{{{SVG_NS}}}desc":
            el.text = (f"Total Stars: {metrics['stars']}, Total Commits: {metrics['commits']}, "
                       f"Total PRs: {metrics['prs']}, Contributed to: {metrics['contribs']}")
    if not all(name in svg for name in ("Total Stars", "Total Commits", "Total PRs", "Contributed to")):
        raise RuntimeError(f"Stats service omitted a required stat for {theme}")
    target.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(f"Updated {target.relative_to(ROOT)}")
