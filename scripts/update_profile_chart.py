#!/usr/bin/env python3
"""Refresh profile detail cards with a little headroom above the chart peak."""
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from collections import defaultdict
from datetime import date
import json
import math
import os
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)

token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
if not token:
    token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
query = '''query { user(login:"pathum-sb") {
  repositories(first:1,privacy:PUBLIC,isFork:false,ownerAffiliations:OWNER) { totalCount }
  contributionsCollection { contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } } }
} }'''
request = Request("https://api.github.com/graphql", data=json.dumps({"query": query}).encode(),
                  headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
with urlopen(request, timeout=30) as response:
    result = json.load(response)
if result.get("errors") or not result.get("data", {}).get("user"):
    raise RuntimeError("GitHub did not return profile metrics")
user = result["data"]["user"]
calendar = user["contributionsCollection"]["contributionCalendar"]
monthly = defaultdict(int)
for week in calendar["weeks"]:
    for day in week["contributionDays"]:
        monthly[day["date"][:7]] += day["contributionCount"]
months = sorted(monthly)
if len(months) < 2:
    raise RuntimeError("Contribution calendar is incomplete")
y_max = max(2, math.ceil(max(monthly.values()) / 2) * 2)
coords = [(i * 380.5 / (len(months) - 1), 110 * (1 - monthly[month] / y_max)) for i, month in enumerate(months)]
slopes = [(coords[i + 1][1] - coords[i][1]) / (coords[i + 1][0] - coords[i][0]) for i in range(len(coords) - 1)]
tangents = [slopes[0]]
for left, right in zip(slopes, slopes[1:]):
    tangents.append(0 if left * right <= 0 else 2 * left * right / (left + right))
tangents.append(slopes[-1])
area_parts = [f"M{coords[0][0]:.3f},{coords[0][1]:.3f}"]
for i in range(len(coords) - 1):
    x0, y0 = coords[i]
    x1, y1 = coords[i + 1]
    h = (x1 - x0) / 3
    area_parts.append(f"C{x0+h:.3f},{y0+tangents[i]*h:.3f} {x1-h:.3f},{y1-tangents[i+1]*h:.3f} {x1:.3f},{y1:.3f}")
area_parts.append("L380.5,110 L0,110 Z")
area_path = " ".join(area_parts)

for theme, api_theme in (("dark", "tokyonight"), ("light", "default")):
    query = urlencode({"username": "pathum-sb", "theme": api_theme, "name": "Pathum Sanjaya Bandara"})
    with urlopen(f"https://github-profile-summary-cards.vercel.app/api/cards/profile-details?{query}", timeout=30) as response:
        svg = response.read()
    root = ET.fromstring(svg)
    if root.get("width") != "700" or root.get("height") != "200":
        raise RuntimeError(f"Unexpected profile card dimensions for {theme}")
    root.set("height", "224")
    root.set("viewBox", "0 0 700 224")

    card = next(el for el in root.iter() if el.get("class") == "gpsc-root")
    title = next(el for el in card if el.tag == f"{{{NS}}}text")
    card.remove(title)
    details = next(el for el in root.iter() if el.get("transform") == "translate(30,30)")
    details.set("transform", "translate(30,-5)")
    for item in details:
        if item.tag == f"{{{NS}}}text" and item.text:
            if "Contributions on GitHub" in item.text:
                item.text = f"{calendar['totalContributions']} Contributions on GitHub"
            elif "Public Repos" in item.text:
                item.text = f"{user['repositories']['totalCount']} Public Repos"
    for item in details:
        if item.tag == f"{{{NS}}}text":
            item.set("y", str(14 + (int(item.get("y", "14")) - 14) * 46 // 28))
        elif item.get("class") == "gpsc-item":
            icon = next((el for el in item if el.get("transform", "").startswith("translate(0,")), None)
            if icon is not None:
                old_y = int(re.fullmatch(r"translate\(0,(\d+)\)", icon.get("transform")).group(1))
                icon.set("transform", f"translate(0,{old_y * 46 // 28})")
    if theme == "dark":
        background = next(el for el in card if el.tag == f"{{{NS}}}rect")
        background.set("fill", "#09142E")
        background.set("stroke", "#09142E")

    # Expand the plot downward by 12px more, giving the peak 22px of headroom.
    # The axis uses the same mapping, so tick labels keep their meaning.
    def chart_y(y: float) -> float:
        return 22 + y * 112 / 110

    clip = next(el for el in root.iter() if el.get("class") == "gpsc-reveal")
    clip.set("height", "134")
    area = next(el for el in root.iter() if el.get("class") == "gpsc-chart")
    path = next(el for el in area.iter(f"{{{NS}}}path"))
    path.set("transform", "translate(-30,22) scale(1,1.018181818181818)")
    path.set("d", area_path)

    x_axis = next(el for el in root.iter() if el.get("transform") == "translate(-30,110)")
    x_axis.set("transform", "translate(-30,134)")
    x_ticks = [el for el in x_axis if el.get("class") == "tick"]
    for tick, index in zip(x_ticks, range(0, len(months), 2)):
        tick.set("transform", f"translate({coords[index][0]+0.5:.3f},0)")
        label = next(el for el in tick if el.tag == f"{{{NS}}}text")
        label.text = months[index][2:4] + "/" + months[index][5:7]
    y_axis = next(el for el in root.iter() if el.get("transform") == "translate(350,0)")
    domain = next(el for el in y_axis if el.get("class") == "domain")
    domain.set("d", "M6,134.5H0.5V22.5H6")
    for tick in y_axis:
        if tick.get("class") != "tick":
            continue
        label = next(el for el in tick if el.tag == f"{{{NS}}}text")
        old_index = list(y_axis).index(tick) - 1
        value = old_index * y_max / (len([el for el in y_axis if el.get('class') == 'tick']) - 1)
        tick.set("transform", f"translate(0,{22 + 112*(1-value/y_max)+0.5:.3f})")
        label.text = str(round(value))

    target = ROOT / "assets" / f"profile-details-{theme}-v2.svg"
    target.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(f"Updated {target.relative_to(ROOT)}")
