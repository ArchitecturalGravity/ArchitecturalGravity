"""Presentation-only text for sanitized completion stage diagnostics."""
from AgMark.shared.runtime.completion_diagnostics import sanitize_completion_diagnostics

_STAGE_LABELS = {
    "post_treatment_validation": "Post-treatment validation",
    "archive_readback": "Archive readback",
    "source_validation": "Source validation",
    "report_request": "Report request",
    "report_build": "Report build",
    "prepublication_validation": "Prepublication validation",
    "publication": "Archive publication",
    "post_publication_cleanup": "Post-publication cleanup",
    "diagnostic_persistence": "Diagnostic persistence",
}


def completion_diagnostic_lines(entries):
    """Never display exception messages, provider payloads, or filesystem paths."""
    lines = []
    for item in sanitize_completion_diagnostics(entries):
        stage = _STAGE_LABELS.get(item["stage"], "Completion")
        operation = {"loose_sources": "temporary source removal", "publication_lock": "publication lock release"}.get(item.get("operation"))
        if operation:
            stage += " / " + operation
        status = item["status"]
        details = item.get("code") or ""
        if item.get("error_class"):
            details += f"; {item['error_class']}"
        if item["stage"] == "post_publication_cleanup" and status == "warning":
            details += "; published archive remains available"
        lines.append(f"{stage}: {status}" + (f" ({details})" if details else ""))
    return tuple(lines)


def retained_diagnostic_lines(root, generation_id, completion):
    """Sidecar diagnostics add context but never replace archive completion status."""
    from AgMark.shared.runtime.completion_diagnostics import retained_completion_diagnostics
    entries = retained_completion_diagnostics(root, generation_id)
    return completion_diagnostic_lines(entries or completion.get("diagnostics", ()))
