"""Typed non-scored validation presentation shared by Results and reports."""
from AgMark.shared.validation.codex_cache.models import ProviderRequestCacheTreatmentSummary
from AgMark.shared.validation.codex_cache.serialization import admit_validation

VALIDATION_EXTENSION = "arcgrav.telemetry:provider-request-cache-validation"
SUMMARY_LABELS = (
    ("provider_request_count", "Provider Requests"), ("warmup_request_count", "Warmup Requests"),
    ("generation_request_count", "Generation Requests"),
    *(('warmup_' + key, 'Warmup ' + label) for key,label in (
        ('input_tokens','Input'),('cached_input_tokens','Cached'),('cache_write_input_tokens','Cache Write'))),
    *(('first_generation_' + key, 'First Gen ' + label) for key,label in (
        ('input_tokens','Input'),('cached_input_tokens','Cached'),('cache_write_input_tokens','Cache Write'),('uncached_input_tokens','Uncached'))),
    *(('generation_' + key, 'Generation ' + label) for key,label in (
        ('input_tokens','Input'),('cached_input_tokens','Cached'),('cache_write_input_tokens','Cache Write'),
        ('uncached_input_tokens','Uncached'),('output_tokens','Output'),('reasoning_tokens','Reasoning'))),
    ('generation_cache_read_fraction','Generation Cache Read Fraction'),('warmup_reuse_ratio','Warmup Reuse Ratio'),
    ('retry_request_count','Retry Requests'),('reconnect_request_count','Reconnect Requests'),
    ('generation_request_duration_ms','Generation Request Duration (ms)'),
)


def validate_consumers(values, generation_id):
    result = []
    for value in values:
        if type(value) is not ProviderRequestCacheTreatmentSummary or value.generation_id != generation_id:
            raise ValueError("typed validation consumer generation differs")
        result.append(admit_validation(value.to_dict()))
    if len({v.treatment_id for v in result}) != len(result):
        raise ValueError("duplicate treatment validation")
    return tuple(result)


def field_text(field):
    if field.value is None:
        return "Unavailable" + (": " + field.reason if field.reason else "")
    value = str(field.value).lower() if type(field.value) is bool else f"{field.value:g}" if type(field.value) is float else str(field.value)
    return value + (f" ({field.availability})" if field.availability != "available" else "")


def validation_markdown(value, *, selected_validation_id=None):
    """Readable exact normalized authority; never parse provider/OTLP payloads."""
    from html import escape
    def cell(v):
        return escape(str(v)).replace("|", "&#124;").replace("\n", "<br>")
    lines = ["## Post-treatment cache validation", "", "Scope: configuration_equivalent_replay. Separate invocation; excluded from score.", ""]
    if value is None:
        return "\n".join((*lines, "Validation unavailable: no retained replay authority."))
    if type(value) is not ProviderRequestCacheTreatmentSummary:
        raise TypeError("typed treatment summary required")
    def table(headers, rows):
        lines.extend(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"])
        lines.extend("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)
        lines.append("")
    if value.sampling_policy == "unsupported_by_adapter":
        return "\n".join(["## Validation replay", "", "Unsupported by the selected adapter. No replay invocations or replay-only probes were run.", "Original-run measurements and scoring are unchanged.", ""])
    if value.sampling_policy == "disabled_by_user":
        lines.extend(["Validation Replay: Disabled by user. No replay invocations or replay-only probes were run.", "Original-run measurements and scoring are unchanged.", ""])
        return "\n".join(lines)
    coverage = value.coverage
    lines.extend(["### Treatment " + cell(value.treatment_id), "",
        f"Scored observations: {coverage.scored_observation_count}; planned: {coverage.validation_replays_planned}; attempted: {coverage.validation_replays_attempted}; completed: {coverage.validation_replays_completed}; comparable: {coverage.validation_replays_comparable}.",
        f"Lifecycle available: {coverage.request_lifecycle_available}; token usage available: {coverage.token_usage_available}; comparable coverage: {cell(field_text(coverage.comparable_coverage))}.",
        "Sampling: " + cell(value.sampling_policy) + "; reason: " + cell(value.sampling_reason),
        "Sampled observation IDs: " + cell(", ".join(value.sampled_observation_ids)), ""])
    table(["Measurement", "Mean", "Median", "Min", "Max", "Contributing / comparable replays"],
        [[label, *(field_text(value.metrics[key][stat].field) for stat in ("mean","median","min","max")),
          str(value.metrics[key]["mean"].contributors) + "/" + str(value.metrics[key]["mean"].eligible)]
         for key,label in SUMMARY_LABELS if key in value.metrics])
    for replay in value.replays:
        if selected_validation_id is not None and replay.validation_id != selected_validation_id:
            continue
        lines.extend(["### Replay " + cell(replay.validation_id), "",
            "Observation: " + cell(replay.validates_observation_id) + "; repetition: " + cell(replay.repetition_id),
            "Outcome: " + cell(replay.status) + "; configuration: " + cell(replay.configuration_match.status) + "; runtime: " + cell(replay.runtime_equivalence.status),
            "Provenance: " + cell(replay.provenance), ""])
        table(["Configuration field","Expected","Observed"], [[key,field_text(replay.configuration_match.expected[key]),field_text(replay.configuration_match.observed[key])] for key in replay.configuration_match.expected])
        lines.extend(["Matched: " + cell(", ".join(replay.configuration_match.matched_fields)),
                      "Unavailable: " + cell(", ".join(replay.configuration_match.unavailable_fields)),
                      "Mismatches: " + cell("; ".join(replay.configuration_match.mismatch_reasons)),
                      "Stock binary: " + cell(field_text(replay.runtime_equivalence.stock_binary_sha256)),
                      "Observed binary: " + cell(field_text(replay.runtime_equivalence.observed_binary_sha256)),
                      "Patch: " + cell(field_text(replay.runtime_equivalence.patch_sha256)),
                      "Instrumentation: " + cell(replay.runtime_equivalence.instrumentation), ""])
        table(["Capability","Status","Method","Limitations","Evidence"], [[k,v.status,v.method,v.limitation or "",", ".join(v.evidence_references)] for k,v in replay.capabilities.fields.items()])
        table(["Request", "Kind", "Transport", "Continuation", "Field", "Value / availability", "Source / method", "Evidence"],
            [[r.request_ordinal,r.request_kind,r.transport,r.continuation_mode,k,field_text(f),f.source + " / " + f.method,", ".join(f.evidence_references)]
             for r in replay.requests for k,f in r.fields.items()])
        if not replay.requests:
            lines.extend(["No provider request records are available.", ""])
        lines.extend(["Replay limitations: " + cell("; ".join((*replay.limitations,*replay.replay_summary.limitations))),
                      "Replay evidence: " + cell(", ".join(replay.evidence_references)), ""])
    lines.extend(["Limitations: " + cell("; ".join(value.limitations)),
        "Replay evidence does not establish the exact scored request trajectory, shared cache identity, warmup writes from later reads, or physical cache eviction.", ""])
    return "\n".join(lines)
