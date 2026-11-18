#!/usr/bin/env python3
"""Refresh themed GitHub stats cards while keeping the logo separate from the rank ring."""
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
THEMES = {
    "dark": {"bg_color": "09142E", "title_color": "3B82F6", "text_color": "38BDAE", "icon_color": "BF91F3"},
    "light": {"bg_color": "FFFFFF", "title_color": "0066FF", "text_color": "0B1F4B", "icon_color": "0066FF"},
}
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

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
    with urlopen(url, timeout=30) as response:
        svg = response.read().decode("utf-8")
    if "Something went wrong" in svg:
        raise RuntimeError(f"Stats service returned an error for {theme}")
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
        "Contributed to (last year):": "Contributed to:",
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
    if not all(name in svg for name in ("Total Stars", "Total Commits", "Total PRs", "Contributed to")):
        raise RuntimeError(f"Stats service omitted a required stat for {theme}")
    target = ROOT / "assets" / f"stats-{theme}.svg"
    target.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(f"Updated {target.relative_to(ROOT)}")
