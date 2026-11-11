"""Independent execution outcomes and registered correctness for Results."""
from collections.abc import Mapping
import math
import json


AGGREGATION_EXTENSION = "arcgrav.shared.reporting:aggregation"
SCORE_DETAILS_EXTENSION = "arcgrav.shared.reporting:score-details"


def treatment_execution_states(observations, *, planned_observations=None, cancelled=False):
    """Project benchmark outcomes independently from score and telemetry health."""
    groups = {name: [] for name in planned_observations or {}}
    unreadable = 0
    for raw in observations:
        try:
            document = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
        except (ValueError, UnicodeError):
            unreadable += 1
            continue
        if (not isinstance(document, Mapping) or not isinstance(document.get("treatment_id"), str)
                or not isinstance(document.get("terminal_status"), str)):
            unreadable += 1
            continue
        groups.setdefault(document["treatment_id"], []).append(document["terminal_status"])
    result = {}
    for treatment, states in groups.items():
        expected = (planned_observations or {}).get(treatment, len(states))
        distinct = tuple(dict.fromkeys(states))
        if cancelled and len(states) < expected:
            status = "cancelled"
        elif len(distinct) == 1 and len(states) == expected and not unreadable:
            status = distinct[0]
        elif not states:
            status = "not started"
        else:
            status = "partial"
        result[treatment] = {"status": status, "outcomes": states,
                             "retained_observations": len(states), "planned_observations": expected,
                             "unclassified_observation_count": unreadable}
    return result


def registered_rate_summary(scores, registration):
    """Project the exact registered rate policy over retained score artifacts.

    Existing registrations retain their observation-weighted behavior. An
    explicit mean/mean registration first averages repetitions within each
    case and then gives every included case equal weight. Its denominator is
    cases, never field opportunities or the number of repetitions.
    """
    policy = registration.get("extensions", {}).get(AGGREGATION_EXTENSION)
    if policy is not None:
        if not isinstance(policy, Mapping) or dict(policy) != {
            "repetition_reducer": "mean", "case_reducer": "mean"
        }:
            raise ValueError("unsupported registered reporting aggregation")
        return _case_mean_summary(tuple(scores), registration)
    return _observation_rate_summary(scores, registration)


def _observation_rate_summary(scores, registration):
    if registration.get("numerator_denominator", {}).get("uses_rate") is not True:
        raise ValueError("registered rate aggregation required")
    dispositions = {item["state"]: item["disposition"] for item in registration.get("state_treatment", ())}
    numerator = 0
    denominator = 0
    for score in scores:
        identity = score.get("metric_registration", {})
        if identity.get("id") != registration["registration_id"] or identity.get("version") != registration["registration_version"]:
            raise ValueError("correctness registration mismatch")
        if score.get("availability") == "scored":
            value = score.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("registered scored value must be finite numeric")
            numerator += value
            denominator += 1
        elif dispositions.get(score.get("availability")) == "zero":
            denominator += 1
    return {"value": numerator / denominator if denominator else None,
            "numerator": numerator if denominator else None, "denominator": denominator if denominator else None,
            "metric": registration["metric_id"], "unit": registration.get("unit"), "evaluated_observations": denominator,
            "metric_registration": {"id": registration["registration_id"], "version": registration["registration_version"]}}


def _case_mean_summary(scores, registration):
    if registration.get("numerator_denominator", {}).get("uses_rate") is not True:
        raise ValueError("registered rate aggregation required")
    dispositions = {
        item["state"]: item["disposition"]
        for item in registration.get("state_treatment", ())
    }
    cases = {}
    availability_counts = {}
    blockers = set()
    for score in scores:
        identity = score.get("metric_registration", {})
        if identity.get("id") != registration["registration_id"] or identity.get("version") != registration["registration_version"]:
            raise ValueError("correctness registration mismatch")
        case_id = score.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError("case-mean aggregation requires retained case identity")
        values = cases.setdefault(case_id, [])
        state = score.get("availability")
        availability_counts[state] = availability_counts.get(state, 0) + 1
        if state == "scored":
            value = score.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("registered scored value must be finite numeric")
            values.append(value)
            continue
        disposition = dispositions.get(state)
        if disposition == "zero":
            values.append(0)
        elif disposition == "exclude":
            continue
        elif disposition == "non_comparable" or state in {"non_comparable", "completed_non_scorable"}:
            blockers.add("non_comparable")
        else:
            # Required unavailable/invalid evidence cannot become a mean over
            # the remaining successes. The score's original state is retained.
            blockers.add("unavailable")

    case_summaries = [
        {"case_id": case_id, "value": math.fsum(values) / len(values),
         "evaluated_observations": len(values)}
        for case_id, values in sorted(cases.items()) if values
    ]
    availability = (
        "non_comparable" if "non_comparable" in blockers
        else "unavailable" if blockers or not case_summaries
        else "scored"
    )
    numerator = math.fsum(item["value"] for item in case_summaries) if availability == "scored" else None
    denominator = len(case_summaries) if availability == "scored" else None
    return {
        "value": numerator / denominator if denominator else None,
        "numerator": numerator,
        "denominator": denominator,
        "numerator_unit": "sum of case means",
        "denominator_unit": "cases",
        "aggregation": "mean of repetition means with equal case weight",
        "availability": availability,
        "availability_counts": availability_counts,
        "evaluated_observations": sum(item["evaluated_observations"] for item in case_summaries),
        "evaluated_cases": len(case_summaries),
        "case_summaries": case_summaries,
        "metric": registration["metric_id"],
        "unit": registration.get("unit"),
        "metric_registration": {
            "id": registration["registration_id"],
            "version": registration["registration_version"],
        },
    }


def registered_score_details(scores, registration):
    """Copy registered detail evidence without interpreting benchmark meaning."""
    selection = registration.get("extensions", {}).get(SCORE_DETAILS_EXTENSION)
    if selection is None:
        return []
    if not isinstance(selection, Mapping) or set(selection) != {"extension_keys"}:
        raise ValueError("invalid registered score detail selection")
    keys = selection["extension_keys"]
    if not isinstance(keys, (list, tuple)) or any(not isinstance(key, str) or ":" not in key for key in keys):
        raise ValueError("score detail extension keys must be namespaced names")
    if len(set(keys)) != len(keys):
        raise ValueError("score detail extension selection must be unique")
    result = []
    for score in scores:
        identity = score.get("metric_registration", {})
        if identity.get("id") != registration["registration_id"] or identity.get("version") != registration["registration_version"]:
            raise ValueError("score detail registration mismatch")
        extensions = score.get("extensions", {})
        result.append({
            "score_artifact_id": score.get("score_artifact_id"),
            "case_id": score.get("case_id"),
            "treatment_id": score.get("treatment_id"),
            "repetition_ids": _copy_json(score.get("repetition_ids", [])),
            "availability": score.get("availability"),
            "value": score.get("value"),
            "unit": score.get("unit", registration.get("unit")),
            "companion_values": _copy_json(score.get("companion_values", [])),
            "diagnostics": _copy_json(score.get("diagnostics", [])),
            "extensions": {key: _copy_json(extensions[key]) for key in keys if key in extensions},
        })
    return sorted(result, key=lambda item: (
        str(item["treatment_id"]), str(item["case_id"]),
        tuple(item["repetition_ids"]), str(item["score_artifact_id"]),
    ))


def score_details_text(details):
    """Readable projection of retained companions and selected detail payloads."""
    lines = []
    for item in details:
        repetitions = ", ".join(str(value) for value in item["repetition_ids"])
        lines.append(
            f"Score detail: case {item['case_id']}; repetitions {repetitions}; "
            f"{item['availability']}; value {item['value']} {item['unit']}"
        )
        companions = [
            f"{entry['name'].replace('_', ' ')}: "
            + json.dumps(entry["value"], ensure_ascii=False, allow_nan=False)
            + (f" {entry['unit']}" if entry.get("unit") else "")
            for entry in item["companion_values"]
        ]
        if companions:
            lines.append("Companion values: " + "; ".join(companions))
        if item["diagnostics"]:
            lines.append("Score diagnostics: " + ", ".join(item["diagnostics"]))
        for key, payload in item["extensions"].items():
            lines.append("Comparison evidence (" + key + "):")
            lines.append(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    return "\n".join(lines)


def _copy_json(value):
    if isinstance(value, Mapping):
        return {key: _copy_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy_json(item) for item in value]
    return value
