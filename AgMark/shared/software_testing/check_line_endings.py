"""Validate the tracked AgMark tree against AgMark's local LF policy."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import sys


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SCOPE = "AgMark"
_EOL_RECORD = re.compile(rb"^i/(\S+)\s+w/(\S+)\s+attr/(.*)$")


@dataclass(frozen=True, slots=True)
class EolRecord:
    path: str
    index_eol: str
    worktree_eol: str
    attributes: str


def _run_git(
    *args: str,
    repository_root: Path = _REPOSITORY_ROOT,
    accepted_returncodes: tuple[int, ...] = (0,),
) -> bytes:
    process = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=repository_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode not in accepted_returncodes:
        detail = process.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"git {' '.join(args)} failed with exit code {process.returncode}: {detail}"
        )
    return process.stdout


def tracked_eol_records(
    repository_root: Path = _REPOSITORY_ROOT,
) -> tuple[EolRecord, ...]:
    output = _run_git(
        "ls-files",
        "--eol",
        "-z",
        "--",
        _SCOPE,
        repository_root=repository_root,
    )
    records: list[EolRecord] = []
    for raw_record in output.split(b"\0"):
        if not raw_record:
            continue
        try:
            metadata, raw_path = raw_record.split(b"\t", 1)
        except ValueError as exc:
            raise RuntimeError(
                f"unexpected git ls-files --eol record: {raw_record!r}"
            ) from exc
        match = _EOL_RECORD.fullmatch(metadata)
        if match is None:
            raise RuntimeError(
                f"unexpected git ls-files --eol metadata: {metadata!r}"
            )
        records.append(
            EolRecord(
                path=os.fsdecode(raw_path),
                index_eol=match.group(1).decode("ascii"),
                worktree_eol=match.group(2).decode("ascii"),
                attributes=match.group(3).decode("utf-8", errors="replace"),
            )
        )
    return tuple(records)


def tracked_text_paths_with_cr(
    repository_root: Path = _REPOSITORY_ROOT,
) -> tuple[str, ...]:
    output = _run_git(
        "grep",
        "--cached",
        "-I",
        "-z",
        "-l",
        "\r",
        "--",
        _SCOPE,
        repository_root=repository_root,
        accepted_returncodes=(0, 1),
    )
    return tuple(
        os.fsdecode(raw_path)
        for raw_path in output.split(b"\0")
        if raw_path
    )


def policy_violations(
    repository_root: Path = _REPOSITORY_ROOT,
) -> tuple[str, ...]:
    violations: list[str] = []
    records = tracked_eol_records(repository_root)
    if not records:
        return (f"{_SCOPE}/ has no tracked files to validate",)

    for record in records:
        if record.index_eol == "-text":
            continue
        attributes = record.attributes.split()
        if "eol=lf" not in attributes:
            violations.append(
                f"{record.path}: tracked text is missing eol=lf "
                f"(attr/{record.attributes})"
            )
        if record.index_eol in {"crlf", "mixed"}:
            violations.append(
                f"{record.path}: repository bytes are {record.index_eol}, not LF"
            )
        elif record.index_eol not in {"lf", "none"}:
            violations.append(
                f"{record.path}: unrecognized repository EOL state "
                f"{record.index_eol!r}"
            )
        if record.worktree_eol in {"crlf", "mixed"}:
            violations.append(
                f"{record.path}: checkout bytes are {record.worktree_eol}, not LF"
            )

    for path in tracked_text_paths_with_cr(repository_root):
        violations.append(
            f"{path}: repository-controlled text contains a CR byte; "
            "LF is the only permitted line ending"
        )

    return tuple(sorted(set(violations)))


def main() -> int:
    try:
        violations = policy_violations()
    except (OSError, RuntimeError) as exc:
        print(f"AgMark LF policy check could not run: {exc}", file=sys.stderr)
        return 2

    if violations:
        print("AgMark LF policy violations:", file=sys.stderr)
        for violation in violations:
            print(f"  {violation}", file=sys.stderr)
        return 1

    print("AgMark LF policy passed: tracked text is canonical LF; binaries are byte-exact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
