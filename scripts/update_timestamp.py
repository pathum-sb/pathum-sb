#!/usr/bin/env python3
"""Stamp the README dashboard with the last refresh time (UTC)."""
from datetime import datetime, timezone
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

stamp = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
text = README.read_text(encoding="utf-8")
updated, count = re.subn(
    r"(<!-- STATS_UPDATED:START -->).*?(<!-- STATS_UPDATED:END -->)",
    rf"\g<1>{stamp}\g<2>",
    text,
    flags=re.S,
)
if count != 1:
    raise RuntimeError("README is missing the STATS_UPDATED markers")
README.write_text(updated, encoding="utf-8")
print(f"Updated README timestamp: {stamp}")
