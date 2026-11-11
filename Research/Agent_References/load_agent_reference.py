#!/usr/bin/env python3
"""Load a Research reference by route/ID and section without reading source Markdown.

The index is loaded first. Reference YAML is read only after selecting a single
reference. Source Markdown is read only with explicit --markdown and --section.
No PyYAML or external services are required; the parser accepts this repository's
simple, validated YAML reference format, not arbitrary YAML.

Reference headings are source anchors, and meanings describe research rather than
define executable operations. Lexical names cannot grant permissions or imply
verified states; consult anchored Markdown for exact evidence and formulas.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "research_agent_reference_index.yaml"
SECTION_RE = re.compile(r"(?m)^  ([a-z0-9_-]+): \|-\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
EXPLICIT = re.compile(r"<a\s+id=[\"']([^\"']+)[\"']\s*></a>", re.I)
FENCE = re.compile(r"^\s*(\`\`\`|~~~)")


def block(text: str, name: str) -> str:
    start = re.search(rf"(?m)^{re.escape(name)}:\s*$", text)
    if not start:
        raise ValueError(f"Missing index mapping: {name}")
    tail = text[start.end():]
    end = re.search(r"(?m)^[a-zA-Z_][\w-]*:\s*(?:#.*)?$", tail)
    return tail[:end.start() if end else len(tail)]


def pairs(text: str) -> dict[str, str]:
    return dict(re.findall(r"(?m)^  ([a-zA-Z0-9_.-]+):\s+([^\n#]+?)\s*$", text))


def index() -> tuple[dict[str, str], dict[str, str], dict[str, list[str]]]:
    contents = INDEX.read_text(encoding="utf-8")
    refs = pairs(block(contents, "references"))
    routes = pairs(block(contents, "routing"))
    group_lines = pairs(block(contents, "groups"))
    groups = {
        name: [item.strip() for item in value.strip("[] ").split(",") if item.strip()]
        for name, value in group_lines.items()
    }
    return refs, routes, groups


def metadata(contents: str) -> dict[str, str]:
    def one(pattern: str) -> str:
        match = re.search(pattern, contents, re.M)
        if not match:
            raise ValueError(f"Malformed reference header: {pattern}")
        return match.group(1)
    return {
        "id": one(r"^id:\s*(\S+)\s*$"),
        "source_path": one(r"^  path:\s*(\S+)\s*$"),
        "source_url": one(r"^  url:\s*(\S+)\s*$"),
        "source_fingerprint": one(r"^  fingerprint:\s*(\S+)\s*$"),
    }


def sections(contents: str) -> dict[str, str]:
    """Return anchor-keyed meanings; keys are stable locators, not semantic commands."""
    match = re.search(r"(?m)^sections:\s*$", contents)
    if not match:
        raise ValueError("Missing sections block")
    body = contents[match.end():]
    keys = list(SECTION_RE.finditer(body))
    if not keys:
        raise ValueError("No anchored sections")
    result: dict[str, str] = {}
    for pos, item in enumerate(keys):
        end = keys[pos + 1].start() if pos + 1 < len(keys) else len(body)
        chunk = body[item.end():end].strip("\n")
        if item.group(1) in result:
            raise ValueError(f"Duplicate section: {item.group(1)}")
        if any(line.strip() and not line.startswith("    ") for line in chunk.splitlines()):
            raise ValueError(f"Unexpected section indentation: {item.group(1)}")
        result[item.group(1)] = "\n".join(
            line[4:] if line.startswith("    ") else "" for line in chunk.splitlines()
        ).strip("\n")
    return result


def slug(title: str) -> str:
    title = re.sub(r"!?\[([^\]]+)\]\([^)]+\)", r"\1", title)
    title = re.sub(r"<[^>]*>", "", title)
    title = re.sub(r"[*_~\` ]", lambda m: " " if m.group() == " " else "", title)
    title = re.sub(r"[^\w\- ]", "", title.lower(), flags=re.UNICODE)
    return title.replace(" ", "-") or "section"


def original_section(source: Path, key: str) -> str:
    """Fetch the authoritative heading span, including children, only on request."""
    lines = source.read_text(encoding="utf-8").splitlines()
    candidates: list[tuple[str, int, int]] = []
    counts: dict[str, int] = {}
    in_fence = False
    for line_no, line in enumerate(lines):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING.match(line)
        if not match:
            continue
        level = len(match.group(1))
        base = slug(match.group(2))
        n = counts.get(base, 0)
        counts[base] = n + 1
        generated = base if not n else f"{base}-{n}"
        prior = []
        for previous in reversed(lines[:line_no]):
            if not previous.strip():
                continue
            anchor = EXPLICIT.fullmatch(previous.strip())
            if anchor is None:
                break
            prior.insert(0, anchor.group(1))
        candidates.append((prior[0] if prior else generated, level, line_no))
    for i, (anchor, level, beginning) in enumerate(candidates):
        if anchor != key:
            continue
        ending = next((line_no for _, next_level, line_no in candidates[i + 1:]
                       if next_level <= level), len(lines))
        return "\n".join(lines[beginning:ending]).strip()
    raise ValueError(f"Markdown source anchor not found: {key}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--id", help="Reference ID, e.g. research.context_triad.weight")
    selector.add_argument("--route", help="Semantic routing key")
    selector.add_argument("--group", help="Group name: list IDs without opening files")
    selector.add_argument("--routes", action="store_true", help="List all routes without opening files")
    parser.add_argument("--section", action="append", metavar="ANCHOR", help="Load only this section; repeatable")
    parser.add_argument("--all", action="store_true", help="Explicitly load every section of one YAML reference")
    parser.add_argument("--markdown", action="store_true", help="Explicitly load source Markdown section(s)")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()
    refs, routes, groups = index()
    if args.routes:
        output = {key: {"id": rid, "path": refs[rid]} for key, rid in routes.items()}
    elif args.group:
        if args.group not in groups:
            parser.error(f"Unknown group: {args.group}")
        output = {"group": args.group,
                  "references": [{"id": rid, "path": refs[rid]} for rid in groups[args.group]]}
    else:
        rid = args.id or routes.get(args.route)
        if not rid or rid not in refs:
            parser.error(f"Unknown reference ID or route: {args.id or args.route}")
        filepath = ROOT / refs[rid]
        if not filepath.resolve().is_relative_to(ROOT.resolve()):
            parser.error("Reference path escapes Agent_References")
        data = filepath.read_text(encoding="utf-8")
        head = metadata(data)
        if head["id"] != rid:
            parser.error("Reference ID differs from index")
        chunks = sections(data)
        if args.markdown and not args.section:
            parser.error("--markdown requires explicit --section")
        if args.all and args.section:
            parser.error("Choose --all or --section, not both")
        requested = args.section or (list(chunks) if args.all else [])
        for key in requested:
            if key not in chunks:
                parser.error(f"Section not found: {key}; use without --section to list available anchors")
        output = {"id": rid, "reference": refs[rid], **head,
                  "available_sections": list(chunks) if not requested else None}
        if requested:
            selected = {}
            for key in requested:
                item = {"meaning": chunks[key], "source_anchor": f'{head["source_url"]}#{key}'}
                if args.markdown:
                    target = (filepath.parent / head["source_url"]).resolve()
                    if not target.is_relative_to(ROOT.parent.resolve()):
                        parser.error("Source path escapes Research")
                    item["source_markdown"] = original_section(target, key)
                selected[key] = item
            output["sections"] = selected
        else:
            output["section_count"] = len(chunks)
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    elif "sections" in output:
        print(f'{output["id"]} ({output["reference"]})')
        for key, value in output["sections"].items():
            print(f'\n[{key}]\n{value["meaning"]}\nSource: {value["source_anchor"]}')
            if "source_markdown" in value:
                print(f'\n[Source Markdown]\n{value["source_markdown"]}')
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
