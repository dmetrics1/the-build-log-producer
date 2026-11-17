"""Reads config/affiliates.toml (one table per program: name, url, commission, rules) and the
disclosure texts from config.toml [affiliates]. Used by the Producer (in-video disclosure) and
the Publisher (links + disclosure line in the description).

Channel rule: a link goes in only if the tool appears in the video; with a link, double
disclosure; in the description, highest commission first."""
from __future__ import annotations

import re
import tomllib

from .config import PROJECT_ROOT, load_config

AFFILIATES_FILE = PROJECT_ROOT / "config" / "affiliates.toml"
DEFAULT_DISCLOSURE = {
    "spoken": "Some links in the description are affiliate links.",
    "on_screen": "Affiliate link in description",
    "description": "Some links are affiliate links; The Build Log earns a commission at no extra cost to you.",
    "max_start_s": 30,
}


def commission_pct(p: dict) -> float:
    """First percentage in the commission text ('22% recurring...' -> 22.0); 0 if there is none."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", p.get("commission", ""))
    return float(m.group(1).replace(",", ".")) if m else 0.0


def load() -> dict:
    programs = {}
    if AFFILIATES_FILE.exists():
        with open(AFFILIATES_FILE, "rb") as f:
            programs = {k: v for k, v in tomllib.load(f).items() if isinstance(v, dict)}
    disclosure = {**DEFAULT_DISCLOSURE, **load_config().get("affiliates", {})}
    return {"programs": programs, "disclosure": disclosure}


def _variants(name: str) -> list[str]:
    """'ElevenLabs' -> ['ElevenLabs', 'Eleven Labs']: ways the tool can appear in a script."""
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    return list(dict.fromkeys([name, spaced]))


def mentioned(text: str, data: dict | None = None) -> list[dict]:
    """Programs whose name appears in the text (whole word, case-insensitive),
    sorted from highest to lowest commission."""
    data = data or load()
    found = []
    for key, p in data["programs"].items():
        if any(re.search(rf"(?<!\w){re.escape(v)}(?!\w)", text, re.I) for v in _variants(p.get("name", key))):
            found.append({"id": key, **p})
    return sorted(found, key=commission_pct, reverse=True)


def description_block(programs: list[dict], data: dict | None = None) -> str:
    """First lines of the description: disclosure and links, highest commission first.
    Empty if the video mentions no program."""
    if not programs:
        return ""
    data = data or load()
    ordered = sorted(programs, key=commission_pct, reverse=True)
    return "\n".join([data["disclosure"]["description"]] + [f"{p['name']}: {p['url']}" for p in ordered])
