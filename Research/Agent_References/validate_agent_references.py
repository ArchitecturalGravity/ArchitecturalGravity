#!/usr/bin/env python3
"""Validate Research Markdown agent references and lazy-loading routing.

Structural and mechanical surface checks only. None proves semantic completeness.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REF_ROOT = Path(__file__).resolve().parent
RESEARCH = REF_ROOT.parent
ROOT = RESEARCH.parent
INDEX = REF_ROOT / "research_agent_reference_index.yaml"
MAINTENANCE = REF_ROOT / "README.yaml"

# Per-run AgMark Markdown is a generated evidence artifact, not a curated
# Research document. Match only the exact content-addressed report location.
GENERATED_AGMARK_REPORT = re.compile(
    r"^Prompt_Performance/Studies/AgMark_Runs/Data/generation-[0-9a-f]{64}/report\.md$"
)

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE = re.compile(r"^\s*(?:\x60{3,}|~{3,})")
EXPLICIT = re.compile(r"""^<a\s+id=["']([^"']+)["']\s*></a>$""", re.I)
HEADER = re.compile(
    r"^source:\n  path: ([^\n]+)\n  url: ([^\n]+)\n"
    r"  fingerprint: fnv1a32-([0-9a-f]{8})\s*$", re.M,
)
IDENTITY = re.compile(r"^id: (research\.[a-z0-9_.]+)\s*$", re.M)
SECTIONS = re.compile(r"^  ([^:\n]+): \|-\n((?:    .*\n)+)", re.M)
INDEX_ITEM = re.compile(r"^  (research\.[a-z0-9_.]+): ([A-Za-z0-9_./-]+\.yaml)\s*$", re.M)
GROUP = re.compile(r"^  ([a-z0-9_]+): \[([^\]]*)\]\s*$", re.M)
ROUTE = re.compile(r"^  ([a-z0-9_]+): (research\.[a-z0-9_.]+)\s*$", re.M)
REDUNDANT_LEAD = re.compile(
    r"^(?:Abstract|Conclusion|Scope and Evidence Status|"
    r"Role Within the Research Program|Role Within the Context Triad):(?:\s|$)"
)
TITLE_ONLY = re.compile(r"^(.{5,100}?):\s+\1(?:\.)?$")


def fingerprint(contents: str) -> str:
    value = 2166136261
    for character in contents:
        value = ((value ^ ord(character)) * 16777619) & 0xFFFFFFFF
    return f"{value:08x}"


def slug(title: str) -> str:
    title = re.sub(r"!?\[([^\]]+)\]\([^)]+\)", r"\1", title)
    title = re.sub(r"<[^>]*>", "", title)
    title = re.sub(r"[*_~\x60]", "", title)
    title = re.sub(r"[^\w\- ]", "", title.lower(), flags=re.UNICODE)
    return title.replace(" ", "-") or "section"


def heading_keys(markdown: str, path: Path, problems: list[str]) -> tuple[list[str], list[str]]:
    lines = markdown.splitlines()
    keys: list[str] = []  # Required H1/H2 reference anchors
    allowed: list[str] = []  # Verified H1/H2 plus selectively promoted H3 anchors
    counts: dict[str, int] = {}
    fenced = False
    explicit_ids: set[str] = set()
    for lineno, line in enumerate(lines):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue

        existing = EXPLICIT.fullmatch(line.strip())
        if existing:
            anchor_id = existing.group(1)
            if anchor_id in explicit_ids:
                problems.append(f"{path}: duplicate explicit HTML anchor {anchor_id}")
            explicit_ids.add(anchor_id)

        heading = HEADING.match(line)
        if not heading:
            continue
        level = len(heading.group(1))
        candidate = slug(heading.group(2))
        number = counts.get(candidate, 0)
        counts[candidate] = number + 1
        generated = candidate if not number else f"{candidate}-{number}"
        prior: list[str] = []
        for j in range(lineno - 1, -1, -1):
            previous = lines[j].strip()
            if not previous:
                continue
            found = EXPLICIT.fullmatch(previous)
            if not found:
                break
            prior.insert(0, found.group(1))
        if level <= 3:
            anchor = prior[0] if prior else generated
            allowed.append(anchor)
            if level <= 2:
                keys.append(anchor)
    if len(keys) != len(set(keys)):
        problems.append(f"{path}: duplicate effective H1/H2 anchor")
    if len(allowed) != len(set(allowed)):
        problems.append(f"{path}: duplicate effective H1/H2/H3 anchor")
    return keys, allowed


def is_generated_agmark_report(path: Path) -> bool:
    """Identify generated, content-addressed AgMark evidence reports only."""
    return bool(GENERATED_AGMARK_REPORT.fullmatch(path.relative_to(RESEARCH).as_posix()))


def sources() -> list[Path]:
    return sorted(
        path for path in RESEARCH.rglob("*.md")
        if REF_ROOT not in path.parents and not is_generated_agmark_report(path)
    )


def expected_reference(path: Path) -> Path:
    relative = path.relative_to(RESEARCH)
    if relative.as_posix() == "README.md":
        return REF_ROOT / "Overview/README.yaml"
    return (REF_ROOT / relative).with_suffix(".yaml")


def yaml_block(text: str, begin: str, end: str | None = None) -> str:
    marker = "\n" + begin + ":\n"
    value = "\n" + text
    if marker not in value:
        return ""
    tail = value.split(marker, 1)[1]
    if end and "\n" + end + ":\n" in tail:
        tail = tail.split("\n" + end + ":\n", 1)[0]
    return tail


def meaning_surface_issues(body: str) -> list[str]:
    """Catch mechanical summary defects, not unprovable semantic quality."""
    meaning = "\n".join(
        line[4:] if line.startswith("    ") else line
        for line in body.splitlines()
    ).strip()
    if not meaning:
        return ["empty meaning"]
    issues: list[str] = []
    if REDUNDANT_LEAD.match(meaning):
        issues.append("repeats its section label")
    if TITLE_ONLY.fullmatch(meaning):
        issues.append("duplicates its title without substantive meaning")
    if meaning.endswith(":"):
        issues.append("ends with an unfinished lead-in")
    return issues


def run() -> int:
    problems: list[str] = []
    docs = sources()
    expected: dict[str, str] = {}
    ids: dict[str, str] = {}
    total_markdown = total_yaml = 0
    for markdown_path in docs:
        document = markdown_path.relative_to(ROOT).as_posix()
        ref_path = expected_reference(markdown_path)
        relative = ref_path.relative_to(REF_ROOT).as_posix()
        expected[relative] = document
        if not ref_path.is_file():
            problems.append(f"Missing reference for {document}: {relative}")
            continue

        md = markdown_path.read_text(encoding="utf-8")
        ref = ref_path.read_text(encoding="utf-8")
        total_markdown += len(md.encode("utf-8"))
        total_yaml += len(ref.encode("utf-8"))
        if len(ref.encode("utf-8")) >= len(md.encode("utf-8")):
            problems.append(f"{relative}: reference is not smaller than Markdown")

        metadata = HEADER.search(ref)
        if not metadata:
            problems.append(f"{relative}: incomplete source path/url/fingerprint")
        else:
            source_path, source_url, actual_fp = metadata.groups()
            expected_url = Path(os.path.relpath(markdown_path, ref_path.parent)).as_posix()
            if source_path != document:
                problems.append(f"{relative}: source.path mismatch")
            if source_url != expected_url:
                problems.append(f"{relative}: source.url must be relative: {expected_url}")
            if (ref_path.parent / source_url).resolve() != markdown_path.resolve():
                problems.append(f"{relative}: source.url does not resolve")
            if actual_fp != fingerprint(md):
                problems.append(f"{relative}: source fingerprint stale; review semantics first")

        identity = IDENTITY.search(ref)
        if not identity:
            problems.append(f"{relative}: missing research reference ID")
        else:
            ref_id = identity.group(1)
            if ref_id in ids:
                problems.append(f"{relative}: duplicate ID {ref_id}")
            ids[ref_id] = relative

        if not re.search(r"(?m)^schema_version: 2$", ref):
            problems.append(f"{relative}: unexpected schema_version")
        if not re.search(r"(?m)^kind: research_reference$", ref):
            problems.append(f"{relative}: wrong reference kind")

        blocks = yaml_block(ref, "sections")
        matches = list(SECTIONS.finditer(blocks))
        actual_keys = [match.group(1) for match in matches]
        required_keys, allowed_keys = heading_keys(md, markdown_path, problems)
        if (not set(required_keys).issubset(actual_keys)
                or not set(actual_keys).issubset(allowed_keys)
                or len(actual_keys) != len(set(actual_keys))):
            missing = sorted(set(required_keys) - set(actual_keys))
            extra = sorted(set(actual_keys) - set(allowed_keys))
            duplicates = len(actual_keys) - len(set(actual_keys))
            problems.append(
                f"{relative}: source heading coverage: missing={missing}, "
                f"unknown_H3_or_other={extra}, duplicates={duplicates}"
            )
        for match in matches:
            for issue in meaning_surface_issues(match.group(2)):
                problems.append(f"{relative}: section {match.group(1)} {issue}")
        if not matches:
            problems.append(f"{relative}: no semantic sections")

    actual_refs = {
        file.relative_to(REF_ROOT).as_posix()
        for file in REF_ROOT.rglob("*.yaml")
        if file not in (INDEX, MAINTENANCE)
    }
    if actual_refs != set(expected):
        problems.append(
            "Reference inventory differs: missing="
            f"{sorted(set(expected) - actual_refs)}, extra={sorted(actual_refs - set(expected))}"
        )

    if not INDEX.is_file():
        problems.append("Missing research routing index")
    else:
        index = INDEX.read_text(encoding="utf-8")
        found = INDEX_ITEM.findall(yaml_block(index, "references", "groups"))
        indexed = dict(found)
        if len(found) != len(indexed):
            problems.append("Duplicate IDs in routing index")
        if indexed != ids or set(indexed.values()) != set(expected):
            problems.append("Routing references do not match source-derived YAML IDs and paths")

        groups = GROUP.findall(yaml_block(index, "groups", "routing"))
        grouped: set[str] = set()
        for name, values in groups:
            for item in values.split(","):
                item = item.strip()
                grouped.add(item)
                if item not in indexed:
                    problems.append(f"Group {name} references unknown ID {item}")
        if grouped != set(indexed):
            problems.append("Index groups do not cover all reference IDs")

        routes = ROUTE.findall(yaml_block(index, "routing", "maintenance"))
        for name, selected in routes:
            if selected not in indexed:
                problems.append(f"Routing {name} uses unknown reference ID {selected}")
        if not routes:
            problems.append("Index has no routes")
        if not re.search(r"(?m)^  path: \./README\.yaml$", yaml_block(index, "maintenance", "usage")):
            problems.append("Index must route maintenance to README.yaml")
        if not re.search(r"(?m)^  loader: \./load_agent_reference\.py$", yaml_block(index, "maintenance", "usage")):
            problems.append("Index must route section loader to load_agent_reference.py")

    if not MAINTENANCE.is_file():
        problems.append("Missing maintenance README.yaml")
    else:
        maintenance = MAINTENANCE.read_text(encoding="utf-8")
        for required in (
            "schema_version: 2",
            "id: research.references.maintenance",
            "kind: maintenance_reference",
            "index: ./research_agent_reference_index.yaml",
            "validator: ./validate_agent_references.py",
            "source_root: ..",
            "  lexical_semantics: >-",
            "  evidence_language: >-",
            "  compression_boundary: >-",
        ):
            if not re.search(r"(?m)^" + re.escape(required) + r"$", maintenance):
                problems.append(f"README.yaml missing {required}")
    if not (REF_ROOT / "load_agent_reference.py").is_file():
        problems.append("Missing lazy-loading helper load_agent_reference.py")
    if (REF_ROOT / "README.md").exists():
        problems.append("Agent reference root must use README.yaml, not README.md")
    if problems:
        print("Research Agent_References structural validation FAILED:", file=sys.stderr)
        for issue in problems:
            print(f"- {issue}", file=sys.stderr)
        return 1
    print(f"Validated {len(docs)} Research Markdown documents and {len(ids)} source references.")
    print(f"Reference/source bytes: {total_yaml}/{total_markdown} ({total_yaml / total_markdown:.1%}).")
    print("Source paths, headings, fingerprints, routes and mechanical meaning checks passed.")
    print("Scientific and semantic completeness requires independent source review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
