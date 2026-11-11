#!/usr/bin/env python3
"""Validate Research references using relative paths and resolvable fragments.

Repository-internal navigation must be relative to the referring Markdown file.
External scholarly URLs are left absolute. Both stable HTML anchors and
GitHub-generated Markdown heading fragments are checked.
"""

from __future__ import annotations

import re
import sys
import zipfile
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
# Identify local project paths independently of the GitHub owner or repository name.
INTERNAL_GITHUB_PATH_RE = re.compile(
    r"^/[^/]+/[^/]+/(?:blob|tree)/(?:[^/]+/)+?"
    r"(?:AgMark|AgStudio|ArcGrav|Research)(?:/|$)", re.I
)

ANCHOR_RE = re.compile(r'<a\b[^>]*\b(?:id|name)=["\']([^"\']+)["\'][^>]*>', re.I)
HEADING_RE = re.compile(r'^ {0,3}#{1,6}[ \t]+(.+?)\s*$', re.M)
INLINE_LINK_RE = re.compile(
    r'\[[^\]\n]*\]\((<[^>]+>|[^)\s]+)(?:\s+["\'][^"\']*["\'])?\)'
)
REFERENCE_DEF_RE = re.compile(r'^ {0,3}\[[^\]\n]+\]:\s*(<[^>]+>|\S+)', re.M)
FENCE_RE = re.compile(r'^\s*(`{3,}|~{3,})')

# AgMark's exported report.md links to JSON inside its sibling ZIP rather
# than to loose files. Only exact generated report locations and named ZIP
# members receive this alternative resolution; ordinary links stay strict.
AGMARK_GENERATED_REPORT_RE = re.compile(
    r"^Prompt_Performance/Studies/AgMark_Runs/Data/(generation-[0-9a-f]{64})/report\.md$"
)
AGMARK_ARCHIVED_REPORT_MEMBERS = frozenset({
    "report.json", "canonical-evidence.json", "report-manifest.json",
})


@lru_cache(maxsize=None)
def archived_report_names(archive: Path) -> frozenset[str]:
    """Read ZIP member names once; missing and malformed archives stay invalid."""
    try:
        with zipfile.ZipFile(archive) as package:
            return frozenset(package.namelist())
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return frozenset()


def archived_agmark_link_exists(source: Path, target: str) -> bool:
    """Resolve only known exported report data links to actual ZIP members."""
    try:
        relative = source.relative_to(ROOT).as_posix()
    except ValueError:
        return False
    match = AGMARK_GENERATED_REPORT_RE.fullmatch(relative)
    if not match or target not in AGMARK_ARCHIVED_REPORT_MEMBERS:
        return False
    generation = match.group(1)
    archive = source.parent / f"{generation}.agmark"
    member = f"reports/{generation}/{target}"
    return member in archived_report_names(archive)


def visible_markdown(text: str) -> str:
    """Preserve source line numbers while omitting fenced code examples."""
    visible: list[str] = []
    fence_char: str | None = None
    fence_size = 0
    for line in text.splitlines(keepends=True):
        marker = FENCE_RE.match(line)
        if fence_char is None and marker:
            fence_char, fence_size = marker.group(1)[0], len(marker.group(1))
            visible.append("\n")
            continue
        if fence_char is not None:
            if marker and marker.group(1)[0] == fence_char and len(marker.group(1)) >= fence_size:
                fence_char = None
            visible.append("\n")
            continue
        visible.append(line)
    return "".join(visible)


def github_slug(heading: str) -> str:
    """Approximate GitHub's documented heading-to-fragment rules."""
    heading = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', heading)
    heading = re.sub(r'<[^>]*>', '', heading)
    heading = re.sub(r'[*`~]', '', heading)
    heading = re.sub(r'\s+#+\s*$', '', heading).strip()
    return re.sub(r'[^\w\- ]', '', heading.lower()).replace(" ", "-")


def anchors_in(markdown: str) -> tuple[set[str], set[str]]:
    text = visible_markdown(markdown)
    explicit = ANCHOR_RE.findall(text)
    seen: set[str] = set()
    duplicates: set[str] = set()
    for anchor in explicit:
        if anchor in seen:
            duplicates.add(anchor)
        seen.add(anchor)
    anchors = set(explicit)
    seen_headings: dict[str, int] = {}
    for heading in HEADING_RE.findall(text):
        slug = github_slug(heading)
        if not slug:
            continue
        count = seen_headings.get(slug, 0)
        seen_headings[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors, duplicates


def local_links(markdown: str):
    text = visible_markdown(markdown)
    for match in INLINE_LINK_RE.finditer(text):
        yield text.count("\n", 0, match.start()) + 1, match.group(1).strip("<>")
    for match in REFERENCE_DEF_RE.finditer(text):
        yield text.count("\n", 0, match.start()) + 1, match.group(1).strip("<>")


def main() -> int:
    paths = sorted(ROOT.rglob("*.md"))
    anchors: dict[Path, set[str]] = {}
    errors: list[str] = []
    local_link_count = 0
    fragment_count = 0
    for path in paths:
        found, duplicates = anchors_in(path.read_text(encoding="utf-8"))
        anchors[path.resolve()] = found
        for anchor in sorted(duplicates):
            errors.append(f"{path.relative_to(ROOT)}: duplicate explicit anchor #{anchor}")

    for source in paths:
        for line, raw_target in local_links(source.read_text(encoding="utf-8")):
            target = raw_target.strip()
            if not target:
                continue
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                if (
                    parsed.hostname
                    and parsed.hostname.lower() == "github.com"
                    and INTERNAL_GITHUB_PATH_RE.match(unquote(parsed.path))
                ):
                    errors.append(
                        f"{source.relative_to(ROOT)}:{line}: internal GitHub link must be relative: {target}"
                    )
                continue  # External literature references are not local paths.
            if target.startswith("/"):
                errors.append(
                    f"{source.relative_to(ROOT)}:{line}: repository-root link must be relative: {target}"
                )
                continue
            local_link_count += 1
            path_part = unquote(parsed.path)
            fragment = unquote(parsed.fragment)
            destination = (source.parent / path_part).resolve() if path_part else source.resolve()
            if destination.is_dir():
                destination = destination / "README.md"
            if not destination.is_file():
                if not fragment and archived_agmark_link_exists(source, path_part):
                    continue
                errors.append(f"{source.relative_to(ROOT)}:{line}: missing relative target: {target}")
                continue
            if not fragment:
                continue
            fragment_count += 1
            if destination.suffix.lower() != ".md":
                continue  # Source-code line references are not Markdown anchors.
            if destination not in anchors:
                anchors[destination], _ = anchors_in(destination.read_text(encoding="utf-8"))
            if fragment not in anchors[destination]:
                errors.append(
                    f"{source.relative_to(ROOT)}:{line}: unresolved fragment #{fragment} in "
                    f"{destination}"
                )

    if errors:
        print("Research link validation failed:", file=sys.stderr)
        for error in errors:
            print("- " + error, file=sys.stderr)
        return 1
    print(
        f"Validated {len(paths)} Research Markdown files, {local_link_count} relative links, "
        f"and {fragment_count} fragment references."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
