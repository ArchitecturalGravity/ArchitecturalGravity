"""Exact accepted-evidence admission before automatic report completion.

Final release validation is owned by runtime.artifacts.archive. There is no
separate reconstruction or publication-claim promotion operation.
"""
from __future__ import annotations
from collections.abc import Mapping, Sequence
import re
from typing import Any
from .core import ValidationIssue
from .evidence import EvidenceSetValidationOutcome
from .lifecycle import LifecycleValidationOutcome

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")

def validate_reporting_handoff(
    *,
    run_outcome: Mapping[str, Any],
    lifecycle_outcome: LifecycleValidationOutcome,
    evidence_outcome: EvidenceSetValidationOutcome,
    source_id: str,
) -> tuple[ValidationIssue, ...]:
    """Require exact accepted lifecycle and retained-evidence authority."""

    _source_id(source_id)
    if not isinstance(run_outcome, Mapping):
        raise TypeError("run_outcome must be a mapping")
    if type(lifecycle_outcome) is not LifecycleValidationOutcome:
        raise TypeError("lifecycle_outcome must be LifecycleValidationOutcome")
    if type(evidence_outcome) is not EvidenceSetValidationOutcome:
        raise TypeError("evidence_outcome must be EvidenceSetValidationOutcome")

    issues: list[ValidationIssue] = []
    if not lifecycle_outcome.valid:
        _add(issues, "PUBLICATION_LIFECYCLE_AUTHORITY_INVALID", source_id, "/run_outcome", "reporting requires valid lifecycle authority")
    elif not lifecycle_outcome.matches(run_outcome, source_id=lifecycle_outcome.source_id):
        _add(issues, "PUBLICATION_LIFECYCLE_AUTHORITY_MISMATCH", source_id, "/run_outcome", "lifecycle authority does not bind this exact terminal outcome")
    generation = run_outcome.get("generation_id")
    if run_outcome.get("status") != "accepted":
        _add(issues, "PUBLICATION_RUN_NOT_ACCEPTED", source_id, "/run_outcome/status", "reporting consumes finalized accepted evidence only")
    if lifecycle_outcome.valid and lifecycle_outcome.generation_id != generation:
        _add(issues, "PUBLICATION_LIFECYCLE_GENERATION_MISMATCH", source_id, "/run_outcome/generation_id", "lifecycle authority binds a different generation")
    if not evidence_outcome.publication_authorized:
        _add(issues, "PUBLICATION_EVIDENCE_AUTHORITY_INVALID", source_id, "/run_outcome/artifact_index", "reporting requires a valid accepted evidence set")
    elif evidence_outcome.generation_id != generation:
        _add(issues, "PUBLICATION_EVIDENCE_GENERATION_MISMATCH", source_id, "/run_outcome/generation_id", "accepted evidence binds a different generation")

    index = run_outcome.get("artifact_index")
    if not isinstance(index, list) or not index:
        _add(issues, "PUBLICATION_ARTIFACT_INDEX_INVALID", source_id, "/run_outcome/artifact_index", "accepted handoff requires a non-empty artifact index")
        return _norm(issues)
    seen: set[str] = set()
    for i, ref in enumerate(index):
        pointer = f"/run_outcome/artifact_index/{i}"
        if not isinstance(ref, Mapping):
            _add(issues, "PUBLICATION_ARTIFACT_INDEX_ENTRY_INVALID", source_id, pointer, "artifact-index entry must be an object")
            continue
        aid, digest = ref.get("artifact_id"), ref.get("sha256")
        if not isinstance(aid, str) or not aid:
            _add(issues, "PUBLICATION_ARTIFACT_ID_INVALID", source_id, f"{pointer}/artifact_id", "artifact_id must be non-empty")
            continue
        if aid in seen:
            _add(issues, "PUBLICATION_ARTIFACT_ID_AMBIGUOUS", source_id, f"{pointer}/artifact_id", "artifact_id is duplicated")
        seen.add(aid)
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            _add(issues, "PUBLICATION_ARTIFACT_HASH_INVALID", source_id, f"{pointer}/sha256", "artifact hash must be canonical SHA-256")
        elif evidence_outcome.publication_authorized and not evidence_outcome.authorizes(aid, digest):
            _add(issues, "PUBLICATION_ARTIFACT_NOT_AUTHORIZED", source_id, pointer, "artifact-index entry is not exact accepted evidence")
    return _norm(issues)


def _source_id(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("source_id must be a non-empty string")


def _add(issues: list[ValidationIssue], code: str, source_id: str, pointer: str, message: str) -> None:
    issues.append(ValidationIssue(code=code, source_id=source_id, json_pointer=pointer, message=message))


def _norm(issues: Sequence[ValidationIssue]) -> tuple[ValidationIssue, ...]:
    return tuple(sorted(set(issues), key=ValidationIssue.sort_key))


__all__ = ["validate_reporting_handoff"]
