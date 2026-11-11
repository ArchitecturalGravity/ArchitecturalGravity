#!/usr/bin/env python3
"""Validate local scholarly reference metadata and manuscript bibliographies.

Run from any working directory:
    python Research/Style_Guide/validate_references.py

No network access or third-party dependencies are required.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = Path(__file__).resolve().parent / "reference_catalog.json"
PAPERS = [
    ROOT / "Model_Native_Structural_Representation.md",
    ROOT / "Representational_Capacity_Reclamation.md",
    ROOT / "ArcGrav_Interpretive_Efficiency.md",
    ROOT / "ArcGrav_Syntax_Efficiency.md",
    ROOT / "ArcGrav_Reasoning_Interaction_Substitution.md",
    ROOT / "Context_Triad" / "Semantic_Locality.md",
    ROOT / "Context_Triad" / "Semantic_Shadow.md",
    ROOT / "Context_Triad" / "Semantic_Weight.md",
]
URL = re.compile(r"https?://[^\s<>]+")
YEAR = re.compile(r"^\d{4}$")


def normalized(url: str) -> str:
    return url.rstrip("/").lower()


def main() -> int:
    errors: list[str] = []
    items = json.loads(CATALOG.read_text(encoding="utf-8"))["references"]
    by_url: dict[str, dict] = {}
    ids: set[str] = set()
    for item in items:
        for key in ("id", "authors", "year", "title", "venue", "url"):
            if not item.get(key):
                errors.append(f"Catalog item missing {key}: {item!r}")
        if item["id"] in ids:
            errors.append(f"Duplicate catalog id: {item['id']}")
        ids.add(item["id"])
        key = normalized(item["url"])
        if key in by_url:
            errors.append(f"Duplicate canonical URL: {item['url']}")
        by_url[key] = item
        for alias in item.get("alternate_urls", []):
            alternate_key = normalized(alias)
            if alternate_key in by_url:
                errors.append(f"Duplicate alternate URL: {alias}")
            by_url[alternate_key] = item
        if not YEAR.fullmatch(str(item["year"])):
            errors.append(f"Invalid publication year: {item['id']}")

    total_entries = 0
    for path in PAPERS:
        text = path.read_text(encoding="utf-8")
        if "\n## References\n" not in text:
            errors.append(f"Missing References section: {path.relative_to(ROOT)}")
            continue
        body, remaining = text.rsplit("\n## References\n", 1)
        refs = remaining.split("\n## ", 1)[0]
        entries = [line[2:] for line in refs.splitlines() if line.startswith("- ")]
        total_entries += len(entries)
        if entries != sorted(entries, key=str.casefold):
            errors.append(f"References not alphabetized: {path.relative_to(ROOT)}")
        if len(entries) != len(set(entries)):
            errors.append(f"Duplicate reference entries: {path.relative_to(ROOT)}")

        # Check that every cataloged external citation in the manuscript body
        # has a corresponding bibliography entry, without requiring uncataloged
        # contextual or platform URLs to masquerade as scholarly sources.
        covered = {normalized(m.group(0).rstrip('.,;')) for entry in entries
                   for m in URL.finditer(entry)}
        for key, item in by_url.items():
            variants = [key, *(normalized(url) for url in item.get("alternate_urls", []))]
            if any(v in normalized(body) for v in variants) and not any(
                v in covered for v in variants
            ):
                errors.append(f"Missing bibliography: {path.relative_to(ROOT)}: {item['id']}")

    if errors:
        for problem in errors:
            print("ERROR:", problem)
        return 1
    print(f"References valid: {len(PAPERS)} manuscripts, "
          f"{len(items)} canonical sources, {total_entries} bibliography entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
