"""Payload-free completion diagnostics, independent of sealed evidence authority."""
from __future__ import annotations

import json
import errno
import os
from pathlib import Path
import re
import stat
import tempfile

STAGES = frozenset({"post_treatment_validation", "source_validation", "report_request",
    "report_build", "prepublication_validation", "publication", "archive_readback",
    "post_publication_cleanup", "diagnostic_persistence"})
ERROR_CLASSES = frozenset({"Exception", "ValueError", "TypeError", "OSError", "PermissionError",
    "FileNotFoundError", "FileExistsError", "RuntimeError", "KeyError", "IndexError",
    "AssertionError", "UnicodeError", "UnicodeDecodeError", "JSONDecodeError",
    "ApplicationReportingError", "ReportingInputRevalidationError", "ArchiveError",
    "ArchiveCleanupWarning", "ArtifactError", "ArtifactIntegrityError", "ArtifactPathError",
    "ArtifactDestinationError", "ArtifactCollisionError", "GenerationReuseError",
    "TerminalAuthorityConflictError", "SecretRetentionError", "TerminalPublicationError"})
STATUSES = frozenset({"passed", "failed", "warning"})


def completion_diagnostic(stage, status, error=None, *, operation=None):
    name = type(error).__name__ if error is not None else None
    if name is not None and name not in ERROR_CLASSES:
        name = "Exception"
    result = {"stage": stage, "status": status, "error_class": name,
              "code": "completion_" + stage + "_" + status}
    if operation is not None:
        result["operation"] = operation
    if not valid_completion_diagnostic(result):
        raise ValueError("invalid completion diagnostic")
    return result


def valid_completion_diagnostic(value):
    if not isinstance(value, dict):
        return False
    required = {"stage", "status", "error_class", "code"}
    if set(value) not in (required, required | {"operation"}):
        return False
    if "operation" in value and (value.get("stage") != "post_publication_cleanup"
            or value["operation"] not in ("loose_sources", "publication_lock")):
        return False
    stage, status, name = value["stage"], value["status"], value["error_class"]
    return (isinstance(stage, str) and stage in STAGES and isinstance(status, str)
            and status in STATUSES and value["code"] == "completion_" + stage + "_" + status
            and (name is None or isinstance(name, str) and name in ERROR_CLASSES))


def _path(root, generation_id):
    if not isinstance(generation_id, str) or not re.fullmatch(r"generation-[a-zA-Z0-9_-]+", generation_id):
        raise ValueError("invalid completion generation")
    return Path(root) / ".agmark-completion" / (generation_id + ".json")


def persist_completion_diagnostics(root, generation_id, diagnostics):
    if not all(valid_completion_diagnostic(row) for row in diagnostics):
        raise ValueError("invalid completion diagnostics")
    path = _path(root, generation_id)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError("unsafe completion diagnostic destination")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                prefix=".completion-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"schema_version": "agmark.completion-diagnostics/1",
                "generation_id": generation_id, "diagnostics": diagnostics}, stream,
                separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                try:
                    os.fsync(directory)
                except OSError as exc:
                    if exc.errno not in {errno.EINVAL, errno.ENOTSUP}:
                        raise
            finally:
                os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def retained_completion_diagnostics(root, generation_id):
    """Read only sanitized presentation facts; never authorize a report."""
    try:
        path = _path(root, generation_id)
        if path.parent.is_symlink():
            return []
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > 65536:
            return []
        # Nonblocking/no-follow open avoids hanging on a substituted FIFO and
        # fstat verifies the opened object rather than trusting a prior check.
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (not stat.S_ISREG(opened.st_mode) or opened.st_size > 65536
                    or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
                return []
            raw = os.read(descriptor, 65537)
            if len(raw) > 65536:
                return []
        finally:
            os.close(descriptor)
        document = json.loads(raw)
        rows = document["diagnostics"]
        if (document.get("schema_version") != "agmark.completion-diagnostics/1"
                or document.get("generation_id") != generation_id or not isinstance(rows, list)
                or len(rows) > 64 or not all(valid_completion_diagnostic(row) for row in rows)):
            return []
        return rows
    except (OSError, ValueError, TypeError, KeyError):
        return []


def delete_completion_diagnostics(root, generation_id):
    path = _path(root, generation_id)
    if not path.is_symlink() and not path.parent.is_symlink():
        path.unlink(missing_ok=True)


def sanitize_completion_diagnostics(entries):
    if not isinstance(entries, (list, tuple)):
        return []
    result = []
    for row in entries[:64]:
        if not isinstance(row, dict):
            continue
        row = dict(row)
        if row.get("error_class") is not None and (not isinstance(row.get("error_class"), str) or row.get("error_class") not in ERROR_CLASSES):
            row["error_class"] = "Exception"
        if valid_completion_diagnostic(row):
            result.append(row)
    return result


def list_retained_completion_diagnostics(root):
    """Discover diagnostic-only generations without admitting report authority."""
    directory = Path(root) / ".agmark-completion"
    if directory.is_symlink():
        return {}
    try:
        paths = sorted(directory.glob("generation-*.json"))
        return {path.stem: rows for path in paths
                if (rows := retained_completion_diagnostics(root, path.stem))}
    except OSError:
        return {}
