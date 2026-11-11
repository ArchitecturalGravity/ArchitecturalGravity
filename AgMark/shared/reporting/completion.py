"""Versioned completion facts for the single automatic report publication.

These facts describe integrity and report availability. An unsuccessful
completion retains diagnostics, not a final report.
"""
from __future__ import annotations

from datetime import datetime, timezone
from .generation import GeneratedReportBundle

COMPLETION_SCHEMA_ID = "arcgrav.shared.run-completion"
COMPLETION_SCHEMA_VERSION = "2.0.0"


def completion_record(generation_id: str, *, status: str,
                      bundle: GeneratedReportBundle | None = None,
                      diagnostic: str | None = None) -> dict[str, object]:
    if status not in {"complete", "validation_failed", "report_failed", "not_applicable"}:
        raise ValueError("unknown completion status")
    if (status == "complete") != (bundle is not None):
        raise ValueError("only successful completion may contain a final report")
    report = None
    if bundle is not None:
        roles = (("machine_json", bundle.report),
                 ("canonical_evidence_json", bundle.canonical_evidence),
                 ("markdown", bundle.human), ("manifest", bundle.manifest))
        report = {"report_id": bundle.report_document["report_id"],
                  "components": [{"role": role, "artifact_id": component.artifact_id,
                                  "reference": component.reference,
                                  "sha256": component.sha256}
                                 for role, component in roles]}
    return {"schema_id": COMPLETION_SCHEMA_ID,
            "schema_version": COMPLETION_SCHEMA_VERSION,
            "generation_id": generation_id,
            "status": status,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "validation": {"status": "failed" if status == "validation_failed" else
                           "not_applicable" if status == "not_applicable" else "passed",
                           "diagnostic": diagnostic},
            "report": report}


def report_components(bundle: GeneratedReportBundle | None) -> dict[str, bytes]:
    if bundle is None:
        return {}
    return {component.reference: component.data
            for component in (*bundle.components, bundle.manifest)}
