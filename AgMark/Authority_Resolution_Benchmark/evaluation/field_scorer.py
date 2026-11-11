"""Registered ARB field accuracy over one retained Golden and model response.

The shared boundary supplies integrity-checked, case-matched evidence. This
module never executes Golden, reads a source file, or consults another response.
Each expected schema field is one unit; unsupported extra output adds denominator
units. Order and schema validity remain explicit companion diagnostics.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any

from AgMark.shared.evaluation import ScorerCall

from .structured_parser import StructuredOutputParseError, parse_structured_output


_CONTROL_KEY = "arcgrav.authority-resolution:field-scoring"
_RESULT_KEY = "arcgrav.authority-resolution:field-comparison"
_RECORD_FIELDS = ("id", "value", "status", "authority", "derivation", "confidence")
_FINDING_FIELDS = ("id", "category", "evidence", "resolution", "confidence")
_EXECUTION_FIELDS = ("processed", "resolved", "findings", "validated")
_SECTIONS = ("records", "findings", "uncertainties", "execution")
_MISSING = object()

FIELD_SCORING_CONTROLS = MappingProxyType({
    "formula": "correct_units/(expected_units+unexpected_units)",
    "record_matching": "exact_id_first_occurrence",
    "finding_matching": "exact_id_occurrence",
    "uncertainty_matching": "position",
    "field_comparison": "type_sensitive_exact_json_value",
    "nonfinite_comparison": "same_constant_and_sign",
    "ordering": "diagnostic_only",
    "schema_defects": "partial_credit",
    "extra_units": "schema_fields_and_extra_occurrences",
    "treatment_parse_failure": "zero",
    "golden_invalid": "invalid",
})

FIELD_ACCURACY_COMPANIONS = (
    "correct_units", "expected_units", "unexpected_units", "expected_field_accuracy",
    "record_value_accuracy", "record_status_accuracy", "schema_valid",
    "records_order_matches", "findings_order_matches", "uncertainties_order_matches",
    "exact_result_match",
)


def _check_controls(call: ScorerCall) -> None:
    extensions = call.metric_registration.get("extensions")
    controls = extensions.get(_CONTROL_KEY) if isinstance(extensions, Mapping) else None
    if not isinstance(controls, Mapping) or dict(controls) != dict(FIELD_SCORING_CONTROLS):
        raise ValueError("unsupported or missing registered ARB field-scoring controls")


def _equal(left: Any, right: Any) -> bool:
    """Preserve JSON value types, non-finite constants, and floating signed zero."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_equal(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    if isinstance(left, float):
        if math.isnan(left) or math.isnan(right):
            return math.isnan(left) and math.isnan(right)
        if left == right == 0.0:
            return math.copysign(1.0, left) == math.copysign(1.0, right)
    return bool(left == right)


def _pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _trace_value(value: Any) -> dict[str, Any]:
    if value is _MISSING:
        return {"present": False}
    nonfinite: list[dict[str, str]] = []

    def finite(item: Any, path: str) -> Any:
        if isinstance(item, float) and not math.isfinite(item):
            constant = "NaN" if math.isnan(item) else ("Infinity" if item > 0 else "-Infinity")
            nonfinite.append({"path": path, "constant": constant})
            return constant
        if isinstance(item, dict):
            return {k: finite(v, f"{path}/{_pointer(k)}") for k, v in item.items()}
        if isinstance(item, list):
            return [finite(v, f"{path}/{i}") for i, v in enumerate(item)]
        return item

    result = {"present": True, "type": type(value).__name__, "value": finite(value, "")}
    if nonfinite:
        result["nonfinite_values"] = nonfinite
    return result


def _schema_issues(result: dict[str, Any]) -> list[dict[str, str]]:
    """Check output shape only; field correctness is scored independently."""
    issues: list[dict[str, str]] = []

    def issue(path: str, code: str) -> None:
        issues.append({"path": path, "code": code})

    def keys(value: dict[str, Any], fields: tuple[str, ...], path: str) -> None:
        for key in fields:
            if key not in value:
                issue(f"{path}/{key}", "missing_field")
        for key in sorted(set(value) - set(fields)):
            issue(f"{path}/{_pointer(key)}", "unexpected_field")

    keys(result, _SECTIONS, "")
    seen_records: set[str] = set()
    for section, fields in (("records", _RECORD_FIELDS), ("findings", _FINDING_FIELDS)):
        rows = result.get(section, _MISSING)
        if not isinstance(rows, list):
            if rows is not _MISSING:
                issue(f"/{section}", "expected_array")
            continue
        for index, row in enumerate(rows):
            path = f"/{section}/{index}"
            if not isinstance(row, dict):
                issue(path, "expected_object")
                continue
            keys(row, fields, path)
            for key in fields:
                if key not in row or (section == "records" and key in {"value", "status"}):
                    continue
                if not isinstance(row[key], str) or (key == "id" and not row[key]):
                    issue(f"{path}/{key}", "expected_string")
            identity = row.get("id")
            if section == "records" and isinstance(identity, str):
                if identity in seen_records:
                    issue(f"{path}/id", "duplicate_record_id")
                seen_records.add(identity)
            labels = {"confidence": ("high", "low")}
            if section == "records":
                labels.update(authority=("A", "B", "C", "mixed", "unresolved"),
                              derivation=("explicit", "resolved", "unresolved"))
            else:
                labels["category"] = ("conflict", "missing", "instruction-content", "relation")
            for key, choices in labels.items():
                if key in row and row[key] not in choices:
                    issue(f"{path}/{key}", "invalid_label")
    uncertainties = result.get("uncertainties", _MISSING)
    if isinstance(uncertainties, list):
        for index, value in enumerate(uncertainties):
            if not isinstance(value, str):
                issue(f"/uncertainties/{index}", "expected_string")
    elif uncertainties is not _MISSING:
        issue("/uncertainties", "expected_array")
    execution = result.get("execution", _MISSING)
    if isinstance(execution, dict):
        keys(execution, _EXECUTION_FIELDS, "/execution")
        for key in _EXECUTION_FIELDS:
            if key not in execution:
                continue
            value = execution[key]
            if key == "validated":
                if type(value) is not bool:
                    issue(f"/execution/{key}", "expected_boolean")
            elif type(value) is not int or value < 0:
                issue(f"/execution/{key}", "expected_nonnegative_integer")
    elif execution is not _MISSING:
        issue("/execution", "expected_object")
    return issues


def _rows(value: Any) -> list[tuple[tuple[str, int] | None, int, Any]]:
    counts: dict[str, int] = defaultdict(int)
    result = []
    for index, row in enumerate(value if isinstance(value, list) else []):
        identity = row.get("id") if isinstance(row, dict) else None
        key = None
        if isinstance(identity, str):
            counts[identity] += 1
            key = (identity, counts[identity])
        result.append((key, index, row))
    return result


@dataclass
class _Comparison:
    sections: dict[str, dict[str, Any]] = field(default_factory=lambda: {
        name: {"correct_units": 0, "expected_units": 0, "unexpected_units": 0}
        for name in _SECTIONS
    })
    fields: list[dict[str, Any]] = field(default_factory=list)

    def add(self, section: str, expected: Any, observed: Any, *,
            expected_path: str | None, observed_path: str | None,
            name: str | None = None, identity: str | None = None,
            occurrence: int | None = None, units: int = 1) -> None:
        counts = self.sections.setdefault(section, {
            "correct_units": 0, "expected_units": 0, "unexpected_units": 0,
        })
        if expected is _MISSING:
            disposition = "unexpected"
            counts["unexpected_units"] += units
        else:
            counts["expected_units"] += units
            disposition = "missing" if observed is _MISSING else (
                "match" if _equal(expected, observed) else "mismatch"
            )
            if disposition == "match":
                counts["correct_units"] += units
        self.fields.append({
            "section": section, "identity": identity, "occurrence": occurrence,
            "field": name, "expected_path": expected_path, "observed_path": observed_path,
            "disposition": disposition, "units": units,
            "expected": _trace_value(expected), "observed": _trace_value(observed),
        })

    def extra_keys(self, section: str, row: dict[str, Any], fields: tuple[str, ...],
                   path: str, identity: str | None = None, occurrence: int | None = None) -> None:
        for key in sorted(set(row) - set(fields)):
            self.add(section, _MISSING, row[key], expected_path=None,
                     observed_path=f"{path}/{_pointer(key)}", name=key,
                     identity=identity, occurrence=occurrence)


def _compare(golden: dict[str, Any], treatment: dict[str, Any]) -> _Comparison:
    comparison = _Comparison()
    for section, fields in (("records", _RECORD_FIELDS), ("findings", _FINDING_FIELDS)):
        actual = _rows(treatment.get(section))
        by_key = {key: (index, row) for key, index, row in actual if key is not None}
        matched_indices: set[int] = set()
        for key, index, row in _rows(golden[section]):
            actual_index, observed = by_key.get(key, (None, {}))
            if actual_index is not None:
                matched_indices.add(actual_index)
            for name in fields:
                comparison.add(section, row[name], observed.get(name, _MISSING),
                               expected_path=f"/{section}/{index}/{name}",
                               observed_path=None if actual_index is None else f"/{section}/{actual_index}/{name}",
                               name=name, identity=key[0], occurrence=key[1])
        for key, index, row in actual:
            identity, occurrence = key if key is not None else (None, None)
            if index not in matched_indices:
                comparison.add(section, _MISSING, row, expected_path=None,
                               observed_path=f"/{section}/{index}", identity=identity,
                               occurrence=occurrence, units=len(fields))
            if isinstance(row, dict):
                comparison.extra_keys(section, row, fields, f"/{section}/{index}", identity, occurrence)
    uncertainties = treatment.get("uncertainties")
    actual_uncertainties = uncertainties if isinstance(uncertainties, list) else []
    for index, value in enumerate(golden["uncertainties"]):
        observed = actual_uncertainties[index] if index < len(actual_uncertainties) else _MISSING
        comparison.add("uncertainties", value, observed,
                       expected_path=f"/uncertainties/{index}",
                       observed_path=f"/uncertainties/{index}" if observed is not _MISSING else None)
    for index in range(len(golden["uncertainties"]), len(actual_uncertainties)):
        comparison.add("uncertainties", _MISSING, actual_uncertainties[index],
                       expected_path=None, observed_path=f"/uncertainties/{index}")
    execution = treatment.get("execution")
    actual_execution = execution if isinstance(execution, dict) else {}
    for name in _EXECUTION_FIELDS:
        comparison.add("execution", golden["execution"][name], actual_execution.get(name, _MISSING),
                       expected_path=f"/execution/{name}", observed_path=f"/execution/{name}", name=name)
    comparison.extra_keys("execution", actual_execution, _EXECUTION_FIELDS, "/execution")
    comparison.extra_keys("unexpected", treatment, _SECTIONS, "")
    for counts in comparison.sections.values():
        denominator = counts["expected_units"] + counts["unexpected_units"]
        counts["accuracy"] = counts["correct_units"] / denominator if denominator else None
    return comparison


def _base_output() -> dict[str, Any]:
    return {"companion_values": [], "failure_refs": [], "diagnostics": [], "extensions": {}}


def _invalid_golden(*, parseable: bool, issues: list[dict[str, str]]) -> dict[str, Any]:
    output = _base_output()
    output.update(availability="invalid", diagnostics=["ARB_GOLDEN_MALFORMED" if not parseable else "ARB_GOLDEN_SCHEMA_INVALID"])
    output["companion_values"] = [{"name": name, "value": None} for name in FIELD_ACCURACY_COMPANIONS]
    output["extensions"] = {_RESULT_KEY: {
        "golden_parseable": parseable, "golden_schema_valid": False,
        "treatment_parseable": None, "schema_diagnostics": issues,
        "sections": {}, "field_comparisons": [],
    }}
    return output


def score_field_accuracy(call: ScorerCall) -> Mapping[str, Any]:
    """Score C/(G+E) using only retained, same-generation input bytes."""
    _check_controls(call)
    roles = call.evidence_by_role
    if set(roles) != {"golden_stdout", "treatment_response"}:
        raise ValueError("ARB field scorer requires exact registered input roles")
    try:
        golden = parse_structured_output(roles["golden_stdout"])
    except StructuredOutputParseError:
        return _invalid_golden(parseable=False, issues=[{"path": "", "code": "invalid_json"}])
    golden_issues = _schema_issues(golden)
    if not golden_issues:
        for name, section in (("resolved", "records"), ("findings", "findings")):
            if golden["execution"][name] != len(golden[section]):
                golden_issues.append({"path": f"/execution/{name}", "code": "inconsistent_golden_count"})
    if golden_issues:
        return _invalid_golden(parseable=True, issues=golden_issues)
    parseable = True
    try:
        treatment = parse_structured_output(roles["treatment_response"])
    except StructuredOutputParseError:
        parseable = False
        treatment = {}
    schema_issues = _schema_issues(treatment) if parseable else [{"path": "", "code": "invalid_json"}]
    comparison = _compare(golden, treatment)
    correct = sum(counts["correct_units"] for counts in comparison.sections.values())
    expected = sum(counts["expected_units"] for counts in comparison.sections.values())
    unexpected = sum(counts["unexpected_units"] for counts in comparison.sections.values())
    order = {
        section: parseable and isinstance(treatment.get(section), list) and (
            [key for key, _, _ in _rows(golden[section])] ==
            [key for key, _, _ in _rows(treatment[section])]
        ) for section in ("records", "findings")
    }
    order["uncertainties"] = parseable and _equal(golden["uncertainties"], treatment.get("uncertainties"))
    values: dict[str, Any] = {
        "correct_units": correct, "expected_units": expected, "unexpected_units": unexpected,
        "expected_field_accuracy": correct / expected,
        "schema_valid": parseable and not schema_issues,
        **{f"{name}_order_matches": value for name, value in order.items()},
        "exact_result_match": parseable and _equal(golden, treatment),
    }
    for name in ("value", "status"):
        matches = [item for item in comparison.fields if item["section"] == "records"
                   and item["field"] == name and item["expected"]["present"]]
        values[f"record_{name}_accuracy"] = (
            sum(item["disposition"] == "match" for item in matches) / len(matches) if matches else None
        )
    diagnostics = []
    if not parseable:
        diagnostics.append("ARB_TREATMENT_MALFORMED")
    elif schema_issues:
        diagnostics.append("ARB_TREATMENT_SCHEMA_DEFECT")
    if correct < expected:
        diagnostics.append("ARB_FIELD_MISMATCH")
    if unexpected:
        diagnostics.append("ARB_UNEXPECTED_OUTPUT")
    if parseable and not all(order.values()):
        diagnostics.append("ARB_OUTPUT_ORDER_MISMATCH")
    output = _base_output()
    output.update(availability="scored", value=correct / (expected + unexpected), diagnostics=diagnostics)
    output["companion_values"] = [{"name": name, "value": values[name]} for name in FIELD_ACCURACY_COMPANIONS]
    output["extensions"] = {_RESULT_KEY: {
        "golden_parseable": True, "golden_schema_valid": True, "treatment_parseable": parseable,
        "schema_diagnostics": schema_issues, "sections": comparison.sections,
        "field_comparisons": comparison.fields,
        "trace_value_encoding": "nonfinite_constants_as_strings_with_explicit_json_pointer_annotations",
    }}
    return output


__all__ = ["FIELD_ACCURACY_COMPANIONS", "FIELD_SCORING_CONTROLS", "score_field_accuracy"]
