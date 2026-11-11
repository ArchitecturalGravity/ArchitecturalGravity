"""Request → replay → treatment arithmetic with independent coverage."""
from __future__ import annotations
from dataclasses import replace
from statistics import mean, median
from .models import (
    ProviderRequestFieldAvailability as Field, ProviderRequestCacheReplaySummary,
    ProviderRequestCacheTreatmentSummary, SummaryMeasurement, ValidationCoverage,
    TOKEN_FIELDS, SCOPE, TREATMENT_SCHEMA_ID, SCHEMA_VERSION,
)


def observed(value, method, refs=()):
    return Field(value, "available", "normalized_replay", method, evidence_references=tuple(refs))


def derive_request(record):
    values = dict(record.fields)
    total, cached = values["input_tokens"], values["cached_input_tokens"]
    available = total.availability == cached.availability == "available"
    valid = available and cached.value <= total.value
    refs = tuple(dict.fromkeys((*total.evidence_references, *cached.evidence_references)))
    reason = "cached_input_exceeds_input" if available and not valid else "required_counters_unavailable"
    values["uncached_input_tokens"] = (observed(total.value - cached.value, "input_minus_cached", refs)
                                        if valid else Field.unavailable(reason))
    values["cache_read_fraction"] = (observed(cached.value / total.value, "cached_divided_by_positive_input", refs)
                                      if valid and total.value > 0 else Field.unavailable("nonpositive_input" if valid else reason))
    limitations = record.limitations
    if available and not valid:
        limitations = tuple(dict.fromkeys((*limitations, "cached_input_exceeds_input")))
    missing = tuple(sorted(k for k, v in values.items() if v.availability == "unavailable"))
    return replace(record, fields=values, missing_fields=missing, limitations=limitations)


def _sum(records, name, *, metric=None):
    values = [r.fields[name] for r in records]
    contributors = [v for v in values if v.availability == "available"]
    if not contributors:
        return SummaryMeasurement(Field.unavailable("no_available_contributors"), 0, len(values), "sum")
    refs = tuple(dict.fromkeys(ref for v in contributors for ref in v.evidence_references))
    field = observed(sum(v.value for v in contributors), "sum_available_request_fields", refs)
    if len(contributors) != len(values):
        field = replace(field, availability="partial", reason="incomplete_request_field_coverage")
    return SummaryMeasurement(field, len(contributors), len(values), "sum")


def replay_summary(*, validation_id, validates_observation_id, treatment_id, repetition_id,
                   configuration_match, runtime_equivalence, capabilities, requests, limitations=()):
    requests = tuple(requests)
    generation = tuple(r for r in requests if r.request_kind == "generation")
    warmup = tuple(r for r in requests if r.request_kind == "warmup")
    metrics = {}
    boundaries = capabilities.fields["request_boundaries"].status == "supported" and bool(requests)
    incomplete = bool(limitations) or capabilities.fields["request_kind"].status != "supported"
    kinds = capabilities.fields["request_kind"].status == "supported"
    for key, group in (("provider_request_count", requests), ("generation_request_count", generation), ("warmup_request_count", warmup)):
        status = boundaries and (key == "provider_request_count" or kinds)
        metrics[key] = SummaryMeasurement(
            observed(len(group), "count_observed_requests") if status else Field.unavailable("request_coverage_unestablished"),
            1 if status else 0, 1, "count")
    for name in TOKEN_FIELDS:
        metrics["generation_" + name] = _sum(generation, name)
        if name in TOKEN_FIELDS[:3]:
            metrics["warmup_" + name] = _sum(warmup, name)
        first = generation[0].fields[name] if generation else Field.unavailable("generation_not_observed")
        metrics["first_generation_" + name] = SummaryMeasurement(first, int(first.value is not None), 1, "first")
    metrics["generation_request_duration_ms"] = _sum(generation, "request_duration_ms")
    for key in ("retry", "reconnect"):
        values = [r.fields[key] for r in requests]
        known = [v for v in values if v.availability == "available"]
        value = observed(sum(v.value for v in known), "count_observed_flags") if known else Field.unavailable("not_observed")
        if known and len(known) != len(values):
            value = replace(value, availability="partial", reason="incomplete_request_field_coverage")
        metrics[key + "_request_count"] = SummaryMeasurement(value, len(known), len(values), "count")
    # Ratio of paired counters over the exact same generation requests.
    paired = [r for r in generation if r.fields["cache_read_fraction"].availability == "available"]
    ratio = Field.unavailable("positive_paired_input_unavailable")
    if paired:
        ratio = observed(sum(r.fields["cached_input_tokens"].value for r in paired) /
                         sum(r.fields["input_tokens"].value for r in paired), "replay_paired_cached_divided_by_input")
        if len(paired) != len(generation):
            ratio = replace(ratio, availability="partial", reason="incomplete_request_field_coverage")
    metrics["generation_cache_read_fraction"] = SummaryMeasurement(ratio, len(paired), len(generation), "ratio")
    reuse = Field.unavailable("paired_positive_warmup_write_unavailable")
    if generation:
        first = generation[0]
        index = requests.index(first)
        prior = requests[index - 1] if index else None
        if prior and prior.request_kind == "warmup" and first.warmup_request_id == prior.request_id:
            write, read = prior.fields["cache_write_input_tokens"], first.fields["cached_input_tokens"]
            if write.availability == read.availability == "available" and write.value > 0:
                reuse = observed(read.value / write.value, "deterministically_paired_generation_read_divided_by_warmup_write")
    metrics["warmup_reuse_ratio"] = SummaryMeasurement(reuse, int(reuse.value is not None), 1, "ratio")
    if incomplete:
        # Observed requests retain their values, but omitted/unclassified spans
        # cannot silently become full replay coverage or treatment statistics.
        for key, measurement in tuple(metrics.items()):
            if measurement.field.availability == "available":
                metrics[key] = replace(measurement, field=replace(measurement.field,
                    availability="partial", reason="incomplete_replay_request_coverage"))
    return ProviderRequestCacheReplaySummary(
        validation_id, validates_observation_id, treatment_id, repetition_id,
        configuration_match.status, runtime_equivalence.status, metrics,
        observed(requests[0].request_kind, "first_observed_request") if requests else Field.unavailable(),
        observed(generation[0].request_ordinal, "first_observed_generation") if generation else Field.unavailable(),
        tuple(limitations))


def treatment_summary(*, generation_id, treatment_id, replays, scored_observation_ids,
                      sampling_policy="one_per_accepted_observation", sampling_reason="complete_selection"):
    replays = tuple(replays)
    scored = tuple(scored_observation_ids)
    disabled = sampling_policy == "disabled_by_user"
    unsupported = sampling_policy == "unsupported_by_adapter"
    if (disabled or unsupported) and replays:
        raise ValueError("Disabled or unsupported validation cannot contain replay invocations")
    scored_ids = set(scored)
    if len(scored_ids) != len(scored):
        raise ValueError("scored observation identity must be unique")
    if any(r.validates_observation_id not in scored_ids for r in replays):
        raise ValueError("replay is not linked to accepted scored observation")
    if len({r.validates_observation_id for r in replays}) != len(replays):
        raise ValueError("one replay per scored observation; repeats need a separately declared policy")
    completed = [r for r in replays if r.status == "completed"]
    comparable = [r for r in completed if r.configuration_match.status == "comparable" and
                  r.runtime_equivalence.status in {"exact_stock", "instrumented_equivalent"}]
    def has_fields(r, names):
        return all(r.replay_summary.metrics[n].field.availability == "available" for n in names)
    ratio = observed(len(comparable) / len(scored), "comparable_replays_divided_by_scored_observations") if scored else Field.unavailable("zero_scored_observation_denominator")
    if scored and len(comparable) < len(scored):
        ratio = replace(ratio, availability="partial", reason="incomplete_comparable_coverage")
    if disabled or unsupported:
        ratio = Field.unavailable("adapter_validation_replay_unsupported" if unsupported else "disabled_by_user")
    coverage = ValidationCoverage(len(scored), len(replays), sum(r.status in {"failed", "completed"} for r in replays),
        len(completed), len(comparable), sum(has_fields(r, ["generation_request_duration_ms"]) for r in completed),
        sum(has_fields(r, ["generation_input_tokens", "generation_cached_input_tokens"]) for r in completed), ratio)
    keys = sorted({k for r in replays for k in r.replay_summary.metrics})
    metrics = {}
    for name in keys:
        values = [r.replay_summary.metrics[name].field for r in comparable if name in r.replay_summary.metrics and
                  r.replay_summary.metrics[name].field.availability == "available"]
        nums = [v.value for v in values]
        statistics = {}
        for statistic, func in (("mean", mean), ("median", median), ("min", min), ("max", max)):
            value = observed(func(nums), "comparable_replay_" + statistic) if nums else Field.unavailable("no_comparable_field_contributors")
            if nums and (len(nums) < len(comparable) or len(comparable) < len(scored)):
                value = replace(value, availability="partial", reason="incomplete_replay_field_coverage")
            statistics[statistic] = SummaryMeasurement(value, len(nums), len(comparable), statistic)
        metrics[name] = statistics
    return ProviderRequestCacheTreatmentSummary(TREATMENT_SCHEMA_ID, SCHEMA_VERSION, generation_id, treatment_id,
        SCOPE, coverage, metrics, replays, sampling_policy, sampling_reason,
        tuple(r.validates_observation_id for r in replays), scored,
        (("Adapter does not support the selected validation replay profile; no replay was executed.",)
         if unsupported else
         ("Configuration-equivalent replay does not reproduce the exact scored request trajectory or prove physical cache eviction.",)))
