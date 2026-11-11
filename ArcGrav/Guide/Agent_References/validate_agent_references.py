#!/usr/bin/env python3
"""Validate source-aligned ArcGrav Guide references, anchors, and freshness.

This validator cannot certify semantic equivalence; semantic review is separate.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[3]
REF_ROOT = Path(__file__).resolve().parent
INDEX = REF_ROOT / "arcgrav_agent_reference_index.yaml"
MAINTENANCE = REF_ROOT / "README.yaml"

ANCHOR_RE = re.compile(r'<a\s+id=["\']([^"\']+)["\']\s*></a>', re.I)
HEADING_RE = re.compile(r"^#{1,6}\s+")
FENCE_RE = re.compile(r"^\s*(?:\x60{3,}|~{3,})")
HEADER_RE = re.compile(
    r"^source:\n  path: (.+)\n  url: (.+)\n"
    r"  fingerprint: fnv1a32-([0-9a-f]{8})\s*$", re.M
)
REF_ID_RE = re.compile(r"^id: (arcgrav\.[a-z0-9_.]+)\s*$", re.M)
SECTION_RE = re.compile(r"^  (ag-[a-z0-9-]+): \|-\s*$", re.M)
INDEX_LINE_RE = re.compile(
    r"^  (arcgrav\.[a-z0-9_.]+): ([A-Za-z0-9_./-]+\.yaml)\s*$", re.M
)
MARKDOWN_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
ABSOLUTE_REPO_LINK_RE = re.compile(
    r"https?://github\.com/[^/\s]+/[^/\s]+/(?:blob|tree)/(?:[^/\s]+/)+?"
    r"(?:AgMark|AgStudio|ArcGrav|Research)(?:[/#\s)]|$)", re.I
)
SOURCE_SECTION_RE = re.compile(
    r'^<a id="(ag-[a-z0-9-]+)"></a>\n#{1,6}[^\n]*\n', re.M
)

def discover_sources() -> list[Path]:
    guide = ROOT / "ArcGrav/Guide"
    sources = [ROOT / "ArcGrav/README.md"]
    for subdir in ("Principles", "Syntax", "Patterns"):
        sources.extend(sorted((guide / subdir).rglob("*.md")))
    return sources


def expected_ref(path: Path) -> Path:
    rel = path.relative_to(ROOT)
    if rel.as_posix() == "ArcGrav/README.md":
        return REF_ROOT / "Overview/README.yaml"
    return (REF_ROOT / Path(*rel.parts[2:])).with_suffix(".yaml")


def fingerprint(text: str) -> str:
    value = 2166136261
    for character in text:
        value = ((value ^ ord(character)) * 16777619) & 0xFFFFFFFF
    return f"{value:08x}"


def markdown_anchors(text: str, path: Path, issues: list[str]) -> set[str]:
    ids: set[str] = set()
    previous = ""
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            previous = line
            continue
        if in_fence:
            continue
        for match in ANCHOR_RE.finditer(line):
            name = match.group(1)
            if name in ids:
                issues.append(f"{path}: duplicate anchor {name} at line {lineno}")
            ids.add(name)
        if HEADING_RE.match(line):
            match = ANCHOR_RE.fullmatch(previous.strip())
            if not match or not match.group(1).startswith("ag-"):
                issues.append(f"{path}: heading without immediate explicit ag- anchor at line {lineno}")
        previous = line
    return ids


def substantive_source_sections(text: str) -> set[str]:
    """Find anchored sections with direct content, excluding empty category headings."""
    matches = list(SOURCE_SECTION_RE.finditer(text))
    result: set[str] = set()
    for idx, match in enumerate(matches):
        last = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[match.end():last]
        if any(line.strip() and line.strip() not in ("---", "----")
               for line in body.splitlines()):
            result.add(match.group(1))
    return result


def run() -> int:
    issues: list[str] = []
    sources = discover_sources()
    expected: dict[str, str] = {}
    refs_by_id: dict[str, str] = {}
    metrics: list[tuple[int, int]] = []

    for path in sources:
        relative = path.relative_to(ROOT).as_posix()
        ref_path = expected_ref(path)
        ref_rel = ref_path.relative_to(REF_ROOT).as_posix()
        expected[ref_rel] = relative
        if not ref_path.is_file():
            issues.append(f"missing reference {ref_rel} for {relative}")
            continue

        md = path.read_text(encoding="utf-8")
        ref = ref_path.read_text(encoding="utf-8")
        metrics.append((len(md), len(ref)))
        anchors = markdown_anchors(md, path, issues)

        src = HEADER_RE.search(ref)
        if not src:
            issues.append(f"{ref_rel}: missing source.path, source.url or fingerprint")
            continue
        source_path, source_url, stated_fingerprint = src.groups()
        if source_path != relative:
            issues.append(f"{ref_rel}: source.path mismatch: {source_path}")
        expected_url = Path(os.path.relpath(path, start=ref_path.parent)).as_posix()
        if source_url != expected_url:
            issues.append(
                f"{ref_rel}: source.url must be file-relative: "
                f"expected {expected_url!r}, got {source_url!r}"
            )
        if (ref_path.parent / source_url).resolve() != path.resolve():
            issues.append(f"{ref_rel}: relative source.url does not resolve to source.path")
        if stated_fingerprint != fingerprint(md):
            issues.append(f"{ref_rel}: source changed; semantic review and fingerprint update required")

        ref_id = REF_ID_RE.search(ref)
        if not ref_id:
            issues.append(f"{ref_rel}: missing reference ID")
        elif ref_id.group(1) in refs_by_id:
            issues.append(f"{ref_rel}: duplicate reference ID {ref_id.group(1)}")
        else:
            refs_by_id[ref_id.group(1)] = ref_rel

        split = ref.split("\nsections:\n", 1)
        if len(split) != 2:
            issues.append(f"{ref_rel}: missing sections mapping")
            continue
        sections = split[1]
        matches = list(SECTION_RE.finditer(sections))
        ids = [m.group(1) for m in matches]
        if len(ids) != len(set(ids)):
            issues.append(f"{ref_rel}: duplicate source anchor keys")
        if not ids:
            issues.append(f"{ref_rel}: no semantic sections")
        missing_material = substantive_source_sections(md) - set(ids)
        if missing_material:
            issues.append(f"{ref_rel}: source sections without representation: {sorted(missing_material)}")
        if len(ref.encode("utf-8")) >= len(md.encode("utf-8")):
            issues.append(f"{ref_rel}: reference is not smaller than anchored Markdown source")
        for index, match in enumerate(matches):
            name = match.group(1)
            if name not in anchors:
                issues.append(f"{ref_rel}: unresolved Markdown source anchor #{name}")
            finish = matches[index + 1].start() if index + 1 < len(matches) else len(sections)
            body = sections[match.end():finish]
            if not any(line.startswith("    ") and line.strip() for line in body.splitlines()):
                issues.append(f"{ref_rel}: empty semantic section #{name}")

        if ABSOLUTE_REPO_LINK_RE.search(ref):
            issues.append(f"{ref_rel}: repository reference links must be relative")
        for target in MARKDOWN_LINK_RE.findall(ref):
            if target.startswith(("#", "mailto:")) or re.match(
                r"^[a-z][a-z0-9+.-]*://", target, re.I
            ):
                continue
            relative_target, _, fragment = target.partition("#")
            if relative_target.startswith(("/", "\\")):
                issues.append(f"{ref_rel}: absolute Markdown path is not allowed: {target}")
                continue
            destination = (ref_path.parent / unquote(relative_target)).resolve()
            if not destination.is_relative_to(ROOT.resolve()) or not destination.exists():
                issues.append(f"{ref_rel}: invalid relative Markdown link: {target}")
            elif fragment.startswith("ag-") and destination.is_file():
                if fragment not in ANCHOR_RE.findall(destination.read_text(encoding="utf-8")):
                    issues.append(f"{ref_rel}: missing linked semantic anchor: {target}")

    actual = {
        p.relative_to(REF_ROOT).as_posix()
        for p in REF_ROOT.rglob("*.yaml")
        if p.name != INDEX.name and p != MAINTENANCE
    }
    if actual != set(expected):
        issues.append(
            f"reference inventory mismatch: missing={sorted(set(expected)-actual)}, "
            f"extra={sorted(actual-set(expected))}"
        )

    if (REF_ROOT / "README.md").exists():
        issues.append("Maintenance documentation must be README.yaml, not README.md")
    if not MAINTENANCE.is_file():
        issues.append("maintenance YAML README.yaml not found")
    else:
        maintenance = MAINTENANCE.read_text(encoding="utf-8")
        for required in (
            "schema_version: 2",
            "id: arcgrav.references.maintenance",
            "kind: maintenance_reference",
        ):
            if not re.search(r"^" + re.escape(required) + r"$", maintenance, re.M):
                issues.append(f"README.yaml: missing {required}")
        for key, expected_path in (
            ("index", INDEX),
            ("engine", ROOT / "AgStudio/arcgrav_language_engine/arcgrav_agent_reference.yaml"),
            ("validator", REF_ROOT / "validate_agent_references.py"),
        ):
            match = re.search(r"^\s*" + key + r":\s*(\S+)\s*$", maintenance, re.M)
            if not match:
                issues.append(f"README.yaml: missing {key} path")
            elif (MAINTENANCE.parent / match.group(1)).resolve() != expected_path.resolve():
                issues.append(f"README.yaml: {key} is not a valid relative path")
        if ABSOLUTE_REPO_LINK_RE.search(maintenance):
            issues.append("README.yaml: internal links must be relative")
    if not INDEX.is_file():
        issues.append("routing index not found")
    else:
        body = INDEX.read_text(encoding="utf-8")
        if not re.search(r"(?m)^maintenance:\n  path: \./README\.yaml$", body):
            issues.append("routing index must point maintenance to ./README.yaml")
        section = body.split("references:\n", 1)
        if len(section) < 2:
            issues.append("routing index missing references mapping")
        else:
            source = section[1].split("\ngroups:", 1)[0]
            items = INDEX_LINE_RE.findall(source)
            indexed = dict(items)
            if len(items) != len(indexed):
                issues.append("duplicate index IDs")
            if set(indexed.values()) != set(expected) or indexed != refs_by_id:
                issues.append("routing index does not match discovered reference paths and IDs")

    total_source = sum(a for a, _ in metrics)
    total_ref = sum(b for _, b in metrics)
    if issues:
        print("ArcGrav AgentRef validation FAILED:", file=sys.stderr)
        for error in issues:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Validated {len(sources)} sources, {len(metrics)} references, and routing anchors.")
    print(f"Reference / anchored Markdown characters: {total_ref}/{total_source} ({total_ref / total_source:.1%})")
    print("Semantic equivalence requires independent review; structural checks cannot prove it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
