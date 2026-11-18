#!/usr/bin/env python3
"""Refresh themed GitHub stats cards while keeping the logo separate from the rank ring."""
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
LOGIN = os.environ.get("GH_PROFILE_USER", "pathum-sb")
THEMES = {
    "dark": {"bg_color": "09142E", "title_color": "3B82F6", "text_color": "38BDAE", "icon_color": "BF91F3"},
    "light": {"bg_color": "FFFFFF", "title_color": "0066FF", "text_color": "0B1F4B", "icon_color": "0066FF"},
}
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)


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
        raise RuntimeError(f"GitHub did not return complete stats: {payload.get('errors')}")
    return payload["data"]["user"]


def summarize(lines: list[str]) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")


TOKEN = get_token()
now = datetime.now(timezone.utc)
year = now.year
stamp = now.strftime("%d %b %Y %H:%M UTC")

# Discover the account's start year instead of hard-coding it.
meta = graphql(f'query {{ user(login:"{LOGIN}") {{ createdAt }} }}')
start_year = int(meta["createdAt"][:4])
years = list(range(start_year, year + 1))

year_queries = " ".join(
    f'''y{y}: contributionsCollection(from:"{y}-01-01T00:00:00Z",to:"{y}-12-31T23:59:59Z") {{
      totalCommitContributions
      commitContributionsByRepository(maxRepositories: 100) {{ repository {{ nameWithOwner }} }}
      pullRequestContributionsByRepository(maxRepositories: 100) {{ repository {{ nameWithOwner }} }}
      issueContributionsByRepository(maxRepositories: 100) {{ repository {{ nameWithOwner }} }}
      pullRequestReviewContributionsByRepository(maxRepositories: 100) {{ repository {{ nameWithOwner }} }}
    }}'''
    for y in years
)
query = f'''query {{ user(login:"{LOGIN}") {{
  pullRequests {{ totalCount }}
  repositories(first:100,privacy:PUBLIC,isFork:false,ownerAffiliations:OWNER) {{
    totalCount
    pageInfo {{ hasNextPage endCursor }}
    nodes {{ stargazerCount }}
  }}
  {year_queries}
}} }}'''
user = graphql(query)

# The star total must not silently stop at the first 100 repositories.
starred_repos = [repo["stargazerCount"] for repo in user["repositories"]["nodes"]]
page_info = user["repositories"]["pageInfo"]
while page_info["hasNextPage"]:
    cursor = json.dumps(page_info["endCursor"])
    page = graphql(
        f'''query {{ user(login:"{LOGIN}") {{
          repositories(first:100,after:{cursor},privacy:PUBLIC,isFork:false,ownerAffiliations:OWNER) {{
            pageInfo {{ hasNextPage endCursor }}
            nodes {{ stargazerCount }}
          }}
        }} }}'''
    )["repositories"]
    starred_repos.extend(repo["stargazerCount"] for repo in page["nodes"])
    page_info = page["pageInfo"]

contributed_repositories = set()
for y in years:
    collection = user[f"y{y}"]
    for key in (
        "commitContributionsByRepository",
        "pullRequestContributionsByRepository",
        "issueContributionsByRepository",
        "pullRequestReviewContributionsByRepository",
    ):
        contributed_repositories.update(item["repository"]["nameWithOwner"] for item in collection[key])

metrics = {
    "stars": sum(starred_repos),
    "commits": sum(user[f"y{y}"]["totalCommitContributions"] for y in years),
    "prs": user["pullRequests"]["totalCount"],
    "contribs": len(contributed_repositories),
}

summarize([
    "### GitHub stats",
    f"- Updated: {stamp}",
    f"- Stars: **{metrics['stars']}**",
    f"- Commit contributions ({start_year}–{year}): **{metrics['commits']}**",
    f"- Pull requests: **{metrics['prs']}**",
    f"- Repositories contributed to: **{metrics['contribs']}**",
    "",
])

for theme, colors in THEMES.items():
    params = {
        "username": LOGIN,
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
    except Exception as error:
        print(
            f"::warning file=assets/stats-{theme}.svg::Could not refresh card ({error}); "
            "keeping the previous SVG",
            file=sys.stderr,
        )
        svg = target.read_text(encoding="utf-8")
    root = ET.fromstring(svg)
    style = next(el for el in root.iter() if el.tag == f"{{{SVG_NS}}}style")
    style.text = style.text.replace("font: 600 18px", "font: 600 22px")
    style.text = style.text.replace("font: 600 14px", "font: 400 18px")
    style.text = style.text.replace(".stat { font-size:12px; }", ".stat { font-size:18px; }")
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
    rank.set("transform", "translate(375, 60)")
    for child in list(rank):
        if child.tag == f"{{{SVG_NS}}}circle":
            rank.remove(child)
    logo.set("x", "-65")
    logo.set("y", "-57")
    logo.set("width", "120")
    logo.set("height", "120")
    for path in logo.iter(f"{{{SVG_NS}}}path"):
        path.set("fill", f"#{colors['icon_color']}")
    document_title = root.find(f"{{{SVG_NS}}}title")
    if document_title is not None:
        document_title.text = "GitHub stats"
    labels = {
        "Total Stars Earned:": "Total Stars:",
        "Total Commits (last year):": "Commit contributions:",
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
                el.set("x", "235")
        if el.get("data-testid") == "icon":
            el.set("y", "4")
        if el.get("data-testid") in metrics:
            el.text = str(metrics[el.get("data-testid")])
        if el.tag == f"{{{SVG_NS}}}desc":
            el.text = (
                f"Stars: {metrics['stars']}, Commit contributions: {metrics['commits']}, "
                f"Pull requests: {metrics['prs']}, Repositories contributed to: {metrics['contribs']}"
            )
    if not all(name in svg for name in ("Total Stars", "Total Commits", "Total PRs", "Contributed to")):
        raise RuntimeError(f"Stats service omitted a required stat for {theme}")
    target.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(f"Updated {target.relative_to(ROOT)}")
