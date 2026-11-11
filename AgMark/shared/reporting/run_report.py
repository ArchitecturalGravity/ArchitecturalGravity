"""Concise individual-run results, separate from the retained evidence bundle.

Only revalidated shared observations and scores enter this projection. The
renderer never reads provider logs or interprets benchmark-specific payloads.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
import math
import posixpath
import re
from urllib.parse import quote

RUN_RESULTS_EXTENSION = "arcgrav.reporting:run-results"
COLUMNS = (
    ("input_tokens", "Input Tokens"),
    ("uncached_input_tokens", "Uncached Input"),
    ("reasoning_tokens", "Reasoning Output Tokens"),
    ("output_tokens", "Output Tokens"),
    ("total_tokens", "Total Tokens"),
    ("cache_read_fraction", "Cache Read Fraction"),
    ("average_inference_ms", "Average Inference Duration"),
    ("average_ttft_ms", "Average TTFT"),
    ("average_tbt_ms", "Average TBT"),
    ("average_direct_ttft_ms", "Average Direct TTFT"),
    ("average_direct_tbt_ms", "Average Direct TBT"),
    ("tool_calls", "Tool Calls"),
    ("distinct_tool_count", "Distinct Tool Calls"),
    ("failed_tool_calls", "Failed Tool Calls"),
)
TIMING_ROLES = frozenset(role for role, _ in COLUMNS if role.startswith("average_"))


def _copy(value):
    if isinstance(value, Mapping):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy(item) for item in value]
    return value


def _instant(value):
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("observation attempt start must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _utc(value):
    parsed = _instant(value)
    return None if parsed is None else parsed.isoformat().replace("+00:00", "Z")


def project_observation_results(accepted, *, documents, records):
    """Bind every planned row to exact retained observations and primary scores."""
    from ..evaluation.telemetry import aggregate_treatment_measurements

    primary = next(metric for metric in accepted.metrics if metric.is_primary_endpoint)
    observations = {
        documents[record.artifact_id]["observation_id"]: (documents[record.artifact_id], record)
        for record in records.values() if record.role == "treatment_observation"
    }
    consumed = {
        ref.artifact_id for entry in accepted.case_result_matrix
        if (entry.metric_registration_id, entry.metric_registration_version)
        == (primary.registration_id, primary.registration_version)
        for ref in entry.evidence_refs
    }
    scores = {}
    for record in records.values():
        if record.role != "score_artifact" or record.artifact_id not in consumed:
            continue
        score = documents[record.artifact_id]
        if score["metric_registration"] != {"id": primary.registration_id, "version": primary.registration_version}:
            raise ValueError("observation score metric differs from registered primary result")
        # A grouped case score does not establish any constituent observation's score.
        if len(score["observation_ids"]) != 1 or len(score["repetition_ids"]) != 1:
            continue
        identity = score["observation_ids"][0]
        if identity in scores:
            raise ValueError("ambiguous primary score for an observation")
        scores[identity] = score, record

    result = []
    for entry in accepted.observation_matrix:
        document, record = observations.get(entry.observation_id, (None, None))
        score, score_record = scores.get(entry.observation_id, (None, None))
        start = None
        measured = {"roles": {}}
        if document is not None:
            expected = (entry.request_id, entry.case_id, entry.treatment_id, entry.repetition_id)
            actual = tuple(document[key] for key in ("request_id", "case_id", "treatment_id", "repetition"))
            if actual != expected:
                raise ValueError("retained observation differs from its planned report row")
            starts = [_instant(attempt.get("started_at")) for attempt in document["attempts"]]
            if starts and all(value is not None for value in starts):
                start = min(starts).isoformat().replace("+00:00", "Z")
            measured = aggregate_treatment_measurements(
                [(document, record.sha256)], generation_id=accepted.accepted_generation_id,
                planned_observations={entry.treatment_id: 1},
                boundary_fingerprint=accepted.execution_boundary_fingerprint,
            )[entry.treatment_id]
        if score is not None and (score["case_id"] != entry.case_id
                or score["treatment_id"] != entry.treatment_id
                or score["repetition_ids"] != [entry.repetition_id]):
            raise ValueError("retained primary score differs from its observation")
        result.append({
            "observation_id": entry.observation_id, "case_id": entry.case_id,
            "treatment_id": entry.treatment_id, "repetition_id": entry.repetition_id,
            "attempt_started_at": start,
            "score": {"value": None if score is None else score.get("value"),
                      "availability": "unavailable" if score is None else score["availability"],
                      "unit": primary.registration.get("unit")},
            "measurements": measured,
            "source_artifact": None if record is None else {
                "artifact_id": record.artifact_id, "sha256": record.sha256, "reference": record.reference},
            "score_artifact": None if score_record is None else {
                "artifact_id": score_record.artifact_id, "sha256": score_record.sha256, "reference": score_record.reference},
        })
    return result


def _missing(state="unavailable"):
    return {"value": None, "availability": state, "kind": "unavailable"}


def _mean(values, authority=None):
    """Arithmetic observation means, preserving coverage and comparability."""
    if authority is not None and authority.get("availability") == "non_comparable":
        return _missing("non_comparable")
    if any(value.get("availability") == "non_comparable" for value in values):
        return _missing("non_comparable")
    contributors = [value for value in values if value.get("value") is not None
                    and value.get("availability") in {"available", "partial"}]
    if not contributors:
        return _missing()
    from ..evaluation.telemetry.consumption import _compatibility
    if len({_compatibility(value) for value in contributors}) != 1:
        return _missing("non_comparable")
    result = _copy(contributors[0])
    result["value"] = math.fsum(value["value"] for value in contributors) / len(contributors)
    result["availability"] = ("available" if len(contributors) == len(values)
                              and all(value["availability"] == "available" for value in contributors)
                              else "partial")
    result["details"] = {**{key: _copy(contributors[0].get("details", {}).get(key))
                               for key in ("runtime_version", "counting_rules", "compatibility", "pricing")
                               if key in contributors[0].get("details", {})},
                         "contributing_observations": len(contributors), "planned_observations": len(values)}
    result["method"] = "arithmetic mean of available observation values, including zeros"
    return result


def _prefixes(identities):
    hashes = {identity: re.sub(r"^(?:observation[:-]|sha256:)", "", identity) for identity in identities}
    result = {}
    for identity, value in hashes.items():
        length = min(12, len(value))
        while any(other != identity and text[:length] == value[:length] for other, text in hashes.items()):
            length += 1
            if length > len(value):
                value = identity
                length = len(value)
                break
        result[identity] = value[:length]
    return result


def build_run_results(model):
    """Build the shared numeric projection once for all report components."""
    accepted = model.accepted.accepted
    primary = next(metric for metric in accepted.metrics if metric.is_primary_endpoint)
    registration = primary.registration
    accuracy = registration.get("unit") == "proportion" and registration.get("classification") in {
        "correctness", "primary_correctness", "secondary_correctness"}
    metric_label = "Accuracy" if accuracy else registration.get("display_name") or registration.get("name") or registration.get("label") or primary.metric_id
    observations = _copy(model.accepted.observation_results)
    prefixes = _prefixes([row["observation_id"] for row in observations])
    observations.sort(key=lambda row: (_instant(row["attempt_started_at"]) is None,
        _instant(row["attempt_started_at"]) or datetime.max.replace(tzinfo=timezone.utc), row["observation_id"]))
    starts = Counter(_utc(row["attempt_started_at"]) for row in observations if row["attempt_started_at"] is not None)
    ranks = {}
    for index, row in enumerate(observations, 1):
        start = _utc(row["attempt_started_at"])
        row["attempt_started_at"] = start
        if start is not None:
            ranks.setdefault(start, index)
        row["execution_order"] = ranks.get(start)
        row["execution_order_tied"] = starts.get(start, 0) > 1
        row["observation_id_prefix"] = prefixes[row["observation_id"]]

    totals = []
    summaries = {summary.treatment_id: summary for summary in accepted.treatment_summaries
                 if (summary.metric_registration_id, summary.metric_registration_version)
                 == (primary.registration_id, primary.registration_version)}
    for treatment in sorted({row["treatment_id"] for row in observations} | set(summaries)):
        rows = [row for row in observations if row["treatment_id"] == treatment]
        retained = model.accepted.treatment_measurements.get(treatment, {}).get("roles", {})
        summary = summaries.get(treatment)
        score = {"value": None if summary is None else _copy(summary.value),
                 "availability": "unavailable" if summary is None else summary.availability.state,
                 "unit": registration.get("unit")}
        total_roles = {}
        for role, _ in COLUMNS:
            authority = retained.get(role, _missing())
            if role in TIMING_ROLES:
                values = [row["measurements"].get("roles", {}).get(role, _missing()) for row in rows]
                total_roles[role] = _mean(values, authority)
            else:
                total_roles[role] = _copy(authority)
        totals.append({"treatment_id": treatment, "score": score, "measurements": {"roles": total_roles}})
    # The machine report receives values, not a second copy of source traces.
    # Full role provenance and source references stay in canonical evidence.
    notable = []
    for role, label in (("total_tokens", "Total Tokens"), ("uncached_input_tokens", "Uncached Input Tokens"),
                        ("average_inference_ms", "Inference Duration"), ("average_ttft_ms", "TTFT"), ("average_tbt_ms", "TBT")):
        entries = [(row["treatment_id"], row["measurements"]["roles"][role]) for row in totals]
        if entries and all(value.get("value") is not None and value.get("availability") == "available" for _, value in entries):
            from ..evaluation.telemetry.consumption import _compatibility
            if len({_compatibility(value) for _, value in entries}) == 1:
                lowest = min(value["value"] for _, value in entries)
                notable.append({"role": role, "label": label,
                    "treatments": [name for name, value in entries if value["value"] == lowest],
                    "measurement": next(value for _, value in entries if value["value"] == lowest)})
    for row in (*observations, *totals):
        row["measurements"] = {"roles": {
            role: _display_value(row["measurements"].get("roles", {}).get(role, _missing()))
            for role, _ in COLUMNS}}
        row.pop("source_artifact", None)
        row.pop("score_artifact", None)
    for result in notable:
        result["measurement"] = _display_value(result["measurement"])
    return {"version": "1.0.0", "metric_label": metric_label, "metric_unit": registration.get("unit"),
            "accuracy_percentage": accuracy, "model_id": model.accepted.model_id,
            "reasoning_effort": model.accepted.reasoning_effort,
            "observations": observations, "treatment_totals": totals,
            "notable_results": notable}


def _display_value(measurement):
    return {key: _copy(measurement[key]) for key in ("value", "availability", "kind", "unit") if key in measurement}


def _cell(value):
    if value is None:
        return "Unavailable"
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _title_case_label(label):
    """Style human-facing labels without changing registered names or acronyms."""
    words = list(re.finditer(r"[A-Za-z]+", label))
    minor_words = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in",
                   "nor", "of", "on", "or", "per", "the", "to", "via", "with"}
    edges = {words[0].start(), words[-1].start()} if words else set()

    def replace(match):
        word = match.group()
        if word.isupper():
            return word
        if word.lower() in minor_words and match.start() not in edges:
            return word.lower()
        return word[0].upper() + word[1:]

    return re.sub(r"[A-Za-z]+", replace, label)


def _number(measurement, role):
    value = measurement.get("value")
    state = measurement.get("availability", "unavailable")
    if value is None or state not in {"available", "partial", "scored"}:
        return "Unavailable" if state == "unavailable" else state.replace("_", " ").capitalize()
    precision = 6 if role in {"average_tbt_ms", "average_direct_tbt_ms"} else 2
    if role == "cache_read_fraction":
        # Display percentages without modifying retained ratio values or units.
        text = f"{value * 100:,.4f}%"
    else:
        text = f"{value:,.{precision}f}" if role in TIMING_ROLES else f"{value:,}"
    kind = measurement.get("kind")
    if kind in {"timing_estimate", "token_event_proxy"}:
        text += " proxy"
    elif kind in {"offline_token_estimate", "estimated_cost"}:
        text += " estimate"
    if state == "partial":
        text += " (partial)"
    return text


def _score(score, projection):
    if score.get("value") is None or score.get("availability") != "scored":
        state = score.get("availability", "unavailable")
        return "Unavailable" if state == "unavailable" else state.replace("_", " ").capitalize()
    value = score["value"]
    if projection["accuracy_percentage"]:
        return f"{value * 100:.4f}%"
    return str(value) + (" " + projection["metric_unit"] if projection["metric_unit"] else "")


def _relative_reference(target, source):
    for value in (target, source):
        if (not isinstance(value, str) or not value or value.startswith("/")
                or "\\" in value or any(part in {"", ".", ".."} for part in value.split("/"))
                or any(char in value for char in (":", "\x00", "\r", "\n"))):
            raise ValueError("report links require safe relative artifact references")
    return quote(posixpath.relpath(target, posixpath.dirname(source) or "."), safe="/.-_")


def render_run_report(model, projection, *, human_reference, report_reference,
                      canonical_evidence_reference, manifest_reference):
    accepted = model.accepted.accepted
    counts = accepted.observation_counts.to_dict()
    metric_label = _title_case_label(projection["metric_label"])
    observations = projection["observations"]
    treatments = sorted({row["treatment_id"] for row in observations})
    cases = {row["case_id"] for row in observations}
    repetitions = sorted({row["repetition_id"] for row in observations})
    lines = ["# AgMark Individual Run Report", "", "## Run Details", "",
             f"- **Benchmark:** {_cell(accepted.benchmark.id)}",
             f"- **Comparison Track:** {_cell(accepted.comparison_track_id)}",
             f"- **Generation:** {_cell(model.accepted_generation_id)}",
             f"- **Report Generated:** {_cell(model.generated_at)}",
             f"- **Model:** {_cell(projection['model_id'])} · **Reasoning Level:** {_cell(projection['reasoning_effort'])}",
             f"- **Report Status:** {_cell(model.status)}",
             f"- **Coverage:** {len(treatments)} treatments, {len(cases)} cases, {len(repetitions)} distinct repetition identifiers. "
             f"{counts['completed']} of {counts['planned']} planned observations completed; {counts['scored']} scored. "
             f"{counts['failed']} failed, {counts['missing']} missing, {counts['excluded']} excluded, "
             f"{counts['non_scorable']} non-scorable.",
             "- **Scope:** Original accepted run only. " + (
                 "Post-treatment validation evidence is retained separately and excluded from these results."
                 if model.validations else "No post-treatment validation replay results are included.")]
    if model.accepted.synthetic_conformance:
        lines.append("- **Synthetic Conformance Profile:** Deterministic fixture evidence; no live model measurements.")
    lines += ["", "## Results Tables", "", "### Treatment Results per Observation in Execution Order", "",
              f"All {len(observations)} planned observations appear below. Execution order is the earliest recorded attempt start "
              "in UTC, not completion order or repetition number. Equal timestamps share a rank marked tied. "
              "Observations without complete attempt-start evidence appear last with no rank; ranks otherwise cover recorded starts only.", "",
              "Token and tool counts are per-observation totals, including failed attempts and retries. Timing values are in "
              "**milliseconds**. Cache Read Fraction is displayed as a percentage. **Proxy** marks duration-derived estimates. "
              "**Unavailable** is not zero; **partial** marks incomplete measurement coverage. Observation ID prefixes are "
              "at least 12 characters where possible, extended as needed to remain unique; full IDs are in supporting data.", ""]
    headers = ["Treatment", metric_label, *(label for _, label in COLUMNS)]

    def table(rows, *, individual=False):
        columns = headers + (["Execution Order", "Observation ID Prefix", "Repetition", "Attempt Start UTC"] if individual else [])
        lines.extend(["| " + " | ".join(_cell(value) for value in columns) + " |",
                      "| " + " | ".join("---" for _ in columns) + " |"])
        for row in rows:
            roles = row["measurements"].get("roles", {})
            values = [row["treatment_id"], _score(row["score"], projection),
                      *(_number(roles.get(role, _missing()), role) for role, _ in COLUMNS)]
            if individual:
                order = row["execution_order"]
                if order is not None and row["execution_order_tied"]:
                    order = f"{order} (tied)"
                values += [order, row["observation_id_prefix"], row["repetition_id"], row["attempt_started_at"]]
            lines.append("| " + " | ".join(_cell(value) for value in values) + " |")

    table(observations, individual=True)
    lines += ["", "### Treatment Total Averaged Results", "",
              "Token and invocation counts sum retained observations, including retries. The primary result preserves its registered "
              "aggregation. Timing is the arithmetic mean of available observation measurements, not a sum; missing contributors "
              "are not imputed as zero and incomplete means are marked partial. Cache Read Fraction is summed eligible cached input divided by summed eligible "
              "input. Distinct Tool Calls counts unique tool identities across the treatment, not the sum of observation counts.", ""]
    table(projection["treatment_totals"])
    lines += ["", "## Notable Results and Exceptions", ""]
    scores = [(row["treatment_id"], _score(row["score"], projection)) for row in projection["treatment_totals"]]
    if scores:
        lines.append("- **" + _cell(metric_label) + ":** " + "; ".join(_cell(t) + " " + _cell(s) for t, s in scores) + ".")
    for result in projection["notable_results"]:
        names = ", ".join(_cell(name) for name in result["treatments"])
        value = _number(result["measurement"], result["role"])
        lines.append(f"- **{result['label']}:** {names} recorded the lowest within-run value ({value}).")
    incomplete = Counter()
    for row in observations:
        for role, label in COLUMNS:
            state = row["measurements"].get("roles", {}).get(role, {}).get("availability", "unavailable")
            if state != "available":
                incomplete[(label, state)] += 1
    if incomplete:
        lines.append("- **Measurement Exceptions:** " + "; ".join(f"{label}: {number} {state.replace('_', ' ')}" for (label, state), number in incomplete.items()) + ".")
    if any(counts[key] for key in ("failed", "missing", "excluded", "non_scorable")):
        lines.append("- **Observation Exceptions:** See coverage above and linked evidence for the affected observations and reasons.")
    if model.status == "complete_with_deviations":
        lines.append("- **Deviations:** Present in the accepted evidence; details are retained in the supporting data.")
    if model.extensions.get("arcgrav.telemetry:validation-diagnostic"):
        lines.append("- **Validation:** Post-treatment validation was unavailable; the original scored results retain their independent authority. Details are in supporting data.")
    for extension in model.extensions.values():
        if not isinstance(extension, Mapping):
            continue
        sections = extension.get("sections", {})
        if not isinstance(sections, Mapping):
            continue
        for section in sections.values():
            if not isinstance(section, Mapping) or "registered_logic_prerequisites" not in section:
                continue
            state = section.get("state")
            if isinstance(state, str):
                reasons = section.get("reasons", ())
                details = "; ".join(_cell(reason) for reason in reasons if isinstance(reason, str))
                lines.append("- **Registered Prerequisites:** " + _cell(state) + (". " + details if details else "."))
    lines += ["- **Interpretation:** These are within-run observations, not evidence of a general performance advantage.",
              "", "## Measurements", "",
              "- **Treatment:** Registered treatment identifier; the same treatments appear in each results table.",
              "- **" + _cell(metric_label) + ":** " + (
                  "Registered correctness proportion, displayed as a percentage. This is the registered metric, not an assumed whole-output exact match."
                  if projection["accuracy_percentage"] else "Registered primary metric, retaining its original unit.")]
    primary = next(metric for metric in accepted.metrics if metric.is_primary_endpoint)
    from .results import AGGREGATION_EXTENSION
    if primary.registration.get("extensions", {}).get(AGGREGATION_EXTENSION) == {"repetition_reducer": "mean", "case_reducer": "mean"}:
        lines.append("  Treatment results average repetitions within each case, then weight cases equally; they are not pooled field counts.")
    else:
        lines.append("  Treatment results preserve the registered aggregation; no alternative score is calculated for this report.")
    lines += [
        "- **Input Tokens:** Retained input counter, including cached input. Treatment totals sum the observation counts.",
        "- **Uncached Input:** Input minus cached input from compatible attempt-local counters. Treatment totals sum the observation counts.",
        "- **Reasoning Output Tokens:** Reasoning subset already included in Output Tokens. Do not add it again to Total Tokens.",
        "- **Output Tokens:** Retained output counter, including reasoning output. Treatment totals sum the observation counts.",
        "- **Total Tokens:** Retained total input and output counter. Cached input and reasoning subsets are not added again. Counters are not billing measurements.",
        "- **Cache Read Fraction:** Cached input / input for compatible attempts. Treatment totals use the ratio of sums, not the mean of observation ratios. A zero denominator is unavailable. Displayed as a percentage, rounded to four decimals.",
        "- **Average Inference Duration:** Retained session inference mean in milliseconds. Proxy values derive from paired reasoning-item and agent-message-item durations, not provider request duration.",
        "- **Average TTFT:** Retained millisecond mean; a proxy uses reasoning-item duration, not measured request-to-first-token latency.",
        "- **Average TBT:** Retained millisecond mean; a proxy divides agent-message-item duration by (output tokens − 1), not observed inter-token timing. Rounded to six decimals.",
        "- **Average Direct TTFT:** Direct request-start to first-actual-token latency. Unavailable when the required timestamps are absent; not replaced with a proxy.",
        "- **Average Direct TBT:** Direct inter-token timing from ordered actual-token timestamps. Unavailable when these timestamps are absent; not replaced with a proxy.",
        "- **Tool Calls:** Observed tool invocations, including failed attempts and retries. A complete empty trace establishes zero; missing evidence does not.",
        "- **Distinct Tool Calls:** Unique tool identities per observation; treatment totals use the union of identities, not the sum of observation counts.",
        "- **Failed Tool Calls:** Invocations with observed failed terminal outcomes. Treatment totals sum the observation counts.",
        "- **Execution Order:** One-based rank by the earliest absolute attempt start across treatments. Ties share rank; incomplete start evidence has no rank. Not a repetition or completion rank.",
        "- **Observation ID Prefix:** Short unique prefix of the native identifier, starting with 12 hash characters and extending for collisions. Full identifiers remain in supporting data.",
        "- **Repetition:** Native repetition identifier, without renumbering.",
        "- **Attempt Start UTC:** Earliest native attempt started_at, normalized to UTC. Session-relative timestamps are not used.",
        "", "## Links to Supporting Data", "",
    ]
    for label, target, description in (
        ("Machine-readable run report", report_reference, "result tables, registered report sections and availability states"),
        ("Canonical run evidence", canonical_evidence_reference, "full observation IDs, scores, measurement provenance and source references"),
        ("Report manifest", manifest_reference, "exact component identities and integrity hashes"),
    ):
        lines.append(f"- [{label}]({_relative_reference(target, human_reference)}): {description}.")
    lines += ["", "Links are relative to this report. Preserve the accompanying data files and folder structure when moving it.", ""]
    return "\n".join(lines).encode("utf-8")
