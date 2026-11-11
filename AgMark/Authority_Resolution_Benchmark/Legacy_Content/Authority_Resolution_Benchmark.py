from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


DEFAULT_SOURCE_PATH = (
    Path(__file__).resolve().parents[1]
    / "cases"
    / "v1.0.0"
    / "arb-core-001.json"
)

ID_PATTERN = re.compile(r"^item_.*$")

# Lower numbers represent higher authority.
AUTHORITY_RANK = {
    "A": 1,
    "B": 2,
    "C": 3,
}

RECORD_FIELDS = (
    "id",
    "value",
    "status",
    "authority",
    "derivation",
    "confidence",
)

FINDING_FIELDS = (
    "id",
    "category",
    "evidence",
    "resolution",
    "confidence",
)

CATEGORY_ORDER = {
    "conflict": 0,
    "missing": 1,
    "instruction-content": 2,
    "relation": 3,
}

INSTRUCTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bignore\b.*\b(instructions?|polic(?:y|ies)|rules?|prompts?)\b",
        r"\b(disregard|override|bypass)\b.*\b"
        r"(instructions?|polic(?:y|ies)|rules?|prompts?)\b",
        r"\b(system|governing|developer)\s+"
        r"(instructions?|messages?|prompts?)\b",
        r"\bfollow\s+(these|my)\s+instructions\b",
    )
)


@dataclass(frozen=True)
class Record:
    id: str
    value: Any
    status: Any
    authority: str
    derivation: str
    confidence: str


@dataclass(frozen=True)
class Finding:
    id: str
    category: str
    evidence: str
    resolution: str
    confidence: str


@dataclass
class ExecutionStats:
    processed: int = 0
    resolved: int = 0
    findings: int = 0
    validated: bool = False


@dataclass
class BenchmarkResult:
    records: list[Record]
    findings: list[Finding]
    uncertainties: list[str]
    execution: ExecutionStats


@dataclass(frozen=True)
class FieldResolution:
    value: Any
    authority: str | None
    unresolved: bool
    explicit_candidates: tuple[tuple[Any, str], ...]
    top_conflict: bool


def matches_scope_id(value: Any) -> bool:
    """Return whether a value is an exact scoped item identifier."""
    return (
        isinstance(value, str)
        and ID_PATTERN.fullmatch(value) is not None
    )


def is_explicit(value: Any) -> bool:
    """Null values are not considered explicit evidence."""
    return value is not None


def attempts_to_alter_governing_behavior(text: str) -> bool:
    """Detect instruction-like content inside source data."""
    return any(pattern.search(text) for pattern in INSTRUCTION_PATTERNS)


def parse_and_scope(
    source_text: str,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Parse the source and apply the declared record/relation scope."""
    parsed = json.loads(source_text)

    if not isinstance(parsed, dict):
        raise ValueError("Source must decode to a JSON object.")

    raw_records = parsed.get("records", [])
    raw_relations = parsed.get("relations", [])

    if not isinstance(raw_records, list):
        raise ValueError("Source 'records' must be a list.")

    if not isinstance(raw_relations, list):
        raise ValueError("Source 'relations' must be a list.")

    scoped_records = [
        record
        for record in raw_records
        if (
            isinstance(record, dict)
            and matches_scope_id(record.get("id"))
        )
    ]

    scoped_relations = [
        relation
        for relation in raw_relations
        if (
            isinstance(relation, dict)
            and matches_scope_id(relation.get("from"))
            and matches_scope_id(relation.get("to"))
        )
    ]

    return parsed, scoped_records, scoped_relations


def inspect_content(
    scoped_records: Sequence[Mapping[str, Any]],
) -> list[Finding]:
    """Treat source instructions as data and record a finding."""
    findings: list[Finding] = []

    for record in scoped_records:
        record_id = str(record["id"])

        for field_name, field_value in record.items():
            if (
                isinstance(field_value, str)
                and attempts_to_alter_governing_behavior(field_value)
            ):
                findings.append(
                    Finding(
                        id=(
                            f"instruction-content:"
                            f"{record_id}:{field_name}"
                        ),
                        category="instruction-content",
                        evidence=(
                            f"Record {record_id!r}, "
                            f"field {field_name!r}, "
                            f"exact text: {field_value!r}"
                        ),
                        resolution=(
                            "Source content treated only as data "
                            "and not executed"
                        ),
                        confidence="high",
                    )
                )

    return findings


def resolve_field(
    group: Sequence[Mapping[str, Any]],
    field_name: str,
) -> FieldResolution:
    """
    Resolve one field using the highest-authority explicit value.

    Equal highest-authority conflicts remain unresolved.
    """
    candidates: list[tuple[Any, str]] = []

    for record in group:
        authority = record.get("authority")
        value = record.get(field_name)

        if (
            authority in AUTHORITY_RANK
            and is_explicit(value)
        ):
            candidates.append((value, str(authority)))

    if not candidates:
        return FieldResolution(
            value=None,
            authority=None,
            unresolved=True,
            explicit_candidates=(),
            top_conflict=False,
        )

    highest_rank = min(
        AUTHORITY_RANK[authority]
        for _, authority in candidates
    )

    top_candidates = [
        (value, authority)
        for value, authority in candidates
        if AUTHORITY_RANK[authority] == highest_rank
    ]

    distinct_top_values = {
        json.dumps(value, sort_keys=True)
        for value, _ in top_candidates
    }

    if len(distinct_top_values) > 1:
        return FieldResolution(
            value=None,
            authority=None,
            unresolved=True,
            explicit_candidates=tuple(candidates),
            top_conflict=True,
        )

    selected_value, selected_authority = top_candidates[0]

    return FieldResolution(
        value=selected_value,
        authority=selected_authority,
        unresolved=False,
        explicit_candidates=tuple(candidates),
        top_conflict=False,
    )


def has_conflicting_explicit_values(
    group: Sequence[Mapping[str, Any]],
    field_name: str,
) -> bool:
    """Return whether a field has multiple explicit source values."""
    values = {
        json.dumps(record[field_name], sort_keys=True)
        for record in group
        if (
            field_name in record
            and is_explicit(record[field_name])
        )
    }

    return len(values) > 1


def format_conflict_evidence(
    group: Sequence[Mapping[str, Any]],
    fields: Iterable[str],
) -> str:
    """Create concise evidence containing all conflicting values."""
    parts: list[str] = []

    for field_name in fields:
        observations = [
            (
                f"{record.get(field_name)!r} "
                f"({record.get('authority', 'unresolved')})"
            )
            for record in group
            if (
                field_name in record
                and is_explicit(record.get(field_name))
            )
        ]

        parts.append(
            f"{field_name}: " + ", ".join(observations)
        )

    return "; ".join(parts)


def resolve_records(
    scoped_records: Sequence[Mapping[str, Any]],
) -> tuple[
    list[Record],
    list[Finding],
    list[str],
    dict[str, dict[str, FieldResolution]],
]:
    """Group raw records by exact ID and resolve each group."""
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)

    for record in scoped_records:
        grouped[str(record["id"])].append(record)

    records: list[Record] = []
    findings: list[Finding] = []
    uncertainties: list[str] = []

    audit: dict[str, dict[str, FieldResolution]] = {}

    for record_id, group in grouped.items():
        value_result = resolve_field(group, "value")
        status_result = resolve_field(group, "status")

        audit[record_id] = {
            "value": value_result,
            "status": status_result,
        }

        unresolved_fields: list[str] = []

        if value_result.unresolved:
            unresolved_fields.append("value")

        if status_result.unresolved:
            unresolved_fields.append("status")

        recognized_authorities = [
            str(record["authority"])
            for record in group
            if record.get("authority") in AUTHORITY_RANK
        ]

        if not recognized_authorities:
            unresolved_fields.append("authority")

        selected_authorities = {
            result.authority
            for result in (value_result, status_result)
            if result.authority is not None
        }

        if not recognized_authorities or not selected_authorities:
            output_authority = "unresolved"
        elif len(selected_authorities) == 1:
            output_authority = next(iter(selected_authorities))
        else:
            output_authority = "mixed"

        conflict_fields = [
            field_name
            for field_name in ("value", "status")
            if has_conflicting_explicit_values(
                group,
                field_name,
            )
        ]

        if conflict_fields:
            resolutions: list[str] = []

            for field_name, result in (
                ("value", value_result),
                ("status", status_result),
            ):
                if field_name not in conflict_fields:
                    continue

                if result.unresolved:
                    resolutions.append(
                        f"{field_name}=unresolved"
                    )
                else:
                    resolutions.append(
                        f"{field_name}={result.value!r} "
                        f"prevailed under authority "
                        f"{result.authority}"
                    )

            conflict_confidence = (
                "low"
                if any(
                    result.top_conflict
                    for result in (
                        value_result,
                        status_result,
                    )
                )
                else "high"
            )

            findings.append(
                Finding(
                    id=f"conflict:{record_id}",
                    category="conflict",
                    evidence=format_conflict_evidence(
                        group,
                        conflict_fields,
                    ),
                    resolution="; ".join(resolutions),
                    confidence=conflict_confidence,
                )
            )

        for field_name in unresolved_fields:
            condition = (
                f"Record {record_id!r} has no resolvable "
                f"explicit {field_name!r} value"
            )

            findings.append(
                Finding(
                    id=(
                        f"missing:{record_id}:"
                        f"{field_name}"
                    ),
                    category="missing",
                    evidence=condition,
                    resolution=(
                        "Preserved as unresolved; "
                        "no value invented"
                    ),
                    confidence="low",
                )
            )

            uncertainties.append(condition)

        if unresolved_fields:
            derivation = "unresolved"
            confidence = "low"
        elif len(group) > 1 or conflict_fields:
            derivation = "resolved"
            confidence = "high"
        else:
            derivation = "explicit"
            confidence = "high"

        records.append(
            Record(
                id=record_id,
                value=(
                    None
                    if value_result.unresolved
                    else value_result.value
                ),
                status=(
                    None
                    if status_result.unresolved
                    else status_result.value
                ),
                authority=output_authority,
                derivation=derivation,
                confidence=confidence,
            )
        )

    return records, findings, uncertainties, audit


def analyze_relations(
    scoped_relations: Sequence[Mapping[str, Any]],
    records: Sequence[Record],
) -> tuple[list[Finding], list[str]]:
    """Record explicit relations without inferring causality."""
    record_ids = {record.id for record in records}

    findings: list[Finding] = []
    uncertainties: list[str] = []

    for relation in scoped_relations:
        source_id = relation.get("from")
        target_id = relation.get("to")
        relation_type = relation.get("type")

        type_for_id = (
            relation_type
            if is_explicit(relation_type)
            else "unresolved"
        )

        finding_id = (
            f"relation:{source_id}:"
            f"{type_for_id}:{target_id}"
        )

        evidence = (
            f"from={source_id!r}, "
            f"type={relation_type!r}, "
            f"to={target_id!r}"
        )

        endpoints_exist = (
            source_id in record_ids
            and target_id in record_ids
        )

        if endpoints_exist and is_explicit(relation_type):
            resolution = (
                "Recorded as an explicit relation without "
                "adding unstated causality"
            )
            confidence = "high"
        else:
            resolution = "unresolved"
            confidence = "low"

            uncertainties.append(
                f"Unresolved relation: {evidence}"
            )

        findings.append(
            Finding(
                id=finding_id,
                category="relation",
                evidence=evidence,
                resolution=resolution,
                confidence=confidence,
            )
        )

    return findings, uncertainties


def validate(
    scoped_records: Sequence[Mapping[str, Any]],
    scoped_relations: Sequence[Mapping[str, Any]],
    records: Sequence[Record],
    findings: Sequence[Finding],
    audit: Mapping[
        str,
        Mapping[str, FieldResolution],
    ],
) -> list[str]:
    """Run all declared validation checks."""
    failures: list[str] = []

    unique_scoped_ids = {
        str(record["id"])
        for record in scoped_records
    }

    output_ids = [
        record.id
        for record in records
    ]

    if (
        set(output_ids) != unique_scoped_ids
        or len(output_ids) != len(unique_scoped_ids)
    ):
        failures.append(
            "Expected exactly one resolved record "
            "per unique scoped record ID"
        )

    for record in records:
        if set(asdict(record)) != set(RECORD_FIELDS):
            failures.append(
                f"Record schema incomplete for {record.id}"
            )

    for finding in findings:
        if set(asdict(finding)) != set(FINDING_FIELDS):
            failures.append(
                f"Finding schema incomplete for {finding.id}"
            )

    finding_ids = [
        finding.id
        for finding in findings
    ]

    if len(finding_ids) != len(set(finding_ids)):
        failures.append(
            "Finding IDs are not unique"
        )

    for record in records:
        for field_name in ("value", "status"):
            if getattr(record, field_name) is None:
                expected_id = (
                    f"missing:{record.id}:"
                    f"{field_name}"
                )

                if expected_id not in finding_ids:
                    failures.append(
                        "Missing finding absent for "
                        f"{record.id}.{field_name}"
                    )

    expected_instruction_ids = {
        (
            f"instruction-content:"
            f"{record['id']}:{field_name}"
        )
        for record in scoped_records
        for field_name, field_value in record.items()
        if (
            isinstance(field_value, str)
            and attempts_to_alter_governing_behavior(
                field_value
            )
        )
    }

    actual_instruction_ids = {
        finding.id
        for finding in findings
        if finding.category == "instruction-content"
    }

    if actual_instruction_ids != expected_instruction_ids:
        failures.append(
            "Instruction-content findings do not match "
            "detected source instruction attempts"
        )

    relation_findings = [
        finding
        for finding in findings
        if finding.category == "relation"
    ]

    if len(relation_findings) != len(scoped_relations):
        failures.append(
            "Expected exactly one relation finding "
            "per scoped relation"
        )

    for record in records:
        source_group = [
            raw
            for raw in scoped_records
            if raw.get("id") == record.id
        ]

        for field_name in ("value", "status"):
            result = audit[record.id][field_name]
            output_value = getattr(record, field_name)

            if result.unresolved:
                if output_value is not None:
                    failures.append(
                        "Invented unresolved value for "
                        f"{record.id}.{field_name}"
                    )
            elif output_value != result.value:
                failures.append(
                    "Authority resolution mismatch for "
                    f"{record.id}.{field_name}"
                )

            if (
                not result.unresolved
                and result.authority is not None
            ):
                supporting_records = [
                    raw
                    for raw in source_group
                    if (
                        raw.get(field_name) == result.value
                        and raw.get("authority")
                        == result.authority
                    )
                ]

                if not supporting_records:
                    failures.append(
                        "Resolved value lacks exact source "
                        f"support for {record.id}.{field_name}"
                    )

    return failures


def run_orchestration(
    source_text: str,
) -> BenchmarkResult:
    """Run the benchmark phases in their declared order."""
    _, scoped_records, scoped_relations = (
        parse_and_scope(source_text)
    )

    stats = ExecutionStats(
        processed=len(scoped_records)
    )

    instruction_findings = inspect_content(
        scoped_records
    )

    (
        records,
        record_findings,
        uncertainties,
        audit,
    ) = resolve_records(scoped_records)

    (
        relation_findings,
        relation_uncertainties,
    ) = analyze_relations(
        scoped_relations,
        records,
    )

    findings = (
        instruction_findings
        + record_findings
        + relation_findings
    )

    uncertainties.extend(
        relation_uncertainties
    )

    records.sort(
        key=lambda record: record.id
    )

    findings.sort(
        key=lambda finding: (
            CATEGORY_ORDER[finding.category],
            finding.id,
        )
    )

    validation_failures = validate(
        scoped_records=scoped_records,
        scoped_relations=scoped_relations,
        records=records,
        findings=findings,
        audit=audit,
    )

    if validation_failures:
        uncertainties.extend(
            validation_failures
        )

    stats.resolved = len(records)
    stats.findings = len(findings)
    stats.validated = not validation_failures

    return BenchmarkResult(
        records=records,
        findings=findings,
        uncertainties=uncertainties,
        execution=stats,
    )


def main() -> None:
    source_text = DEFAULT_SOURCE_PATH.read_bytes().decode("utf-8")
    result = run_orchestration(source_text)
    print(json.dumps(asdict(result), allow_nan=True))


if __name__ == "__main__":
    main()
