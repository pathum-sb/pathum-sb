#!/usr/bin/env python3
"""Refresh profile detail cards with a little headroom above the chart peak."""
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)

for theme, api_theme in (("dark", "tokyonight"), ("light", "default")):
    query = urlencode({"username": "pathum-sb", "theme": api_theme, "name": "Pathum Sanjaya Bandara"})
    with urlopen(f"https://github-profile-summary-cards.vercel.app/api/cards/profile-details?{query}", timeout=30) as response:
        svg = response.read()
    root = ET.fromstring(svg)
    if root.get("width") != "700" or root.get("height") != "200":
        raise RuntimeError(f"Unexpected profile card dimensions for {theme}")
    root.set("height", "212")
    root.set("viewBox", "0 0 700 212")

    # Expand the plot downward by 12px while adding 10px above its previous peak.
    # The axis uses the same mapping, so tick labels keep their meaning.
    def chart_y(y: float) -> float:
        return 10 + y * 112 / 110

    clip = next(el for el in root.iter() if el.get("class") == "gpsc-reveal")
    clip.set("height", "122")
    area = next(el for el in root.iter() if el.get("class") == "gpsc-chart")
    path = next(el for el in area.iter(f"{{{NS}}}path"))
    path.set("transform", "translate(-30,10) scale(1,1.018181818181818)")

    x_axis = next(el for el in root.iter() if el.get("transform") == "translate(-30,110)")
    x_axis.set("transform", "translate(-30,122)")
    y_axis = next(el for el in root.iter() if el.get("transform") == "translate(350,0)")
    domain = next(el for el in y_axis if el.get("class") == "domain")
    domain.set("d", "M6,122.5H0.5V10.5H6")
    for tick in y_axis:
        if tick.get("class") != "tick":
            continue
        match = re.fullmatch(r"translate\(0,([\d.]+)\)", tick.get("transform", ""))
        if match is None:
            raise RuntimeError(f"Unexpected y-axis tick for {theme}")
        tick.set("transform", f"translate(0,{chart_y(float(match.group(1))):.3f})")

    target = ROOT / "assets" / f"profile-details-{theme}.svg"
    target.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(f"Updated {target.relative_to(ROOT)}")
