"""Original-run cache derivations from compatible, attempt-local counter pairs."""
from copy import deepcopy


def aggregate_paired_cache(attempts, *, observed, planned, boundary_fingerprint):
    from .consumption import _compatibility, observed_measurement, unavailable_measurement

    pairs, excluded = [], []
    for document, attempt, envelope, artifact in attempts:
        identity = {"observation_id": document["observation_id"], "attempt": attempt["attempt"],
                    "evidence_identity": artifact}
        reason = None
        components = (envelope or {}).get("roles", {})
        inputs, cached = (components.get(role, {}) for role in ("input_tokens", "cached_input_tokens"))
        if any(m.get("availability") not in {"available", "partial"} or type(m.get("value")) is not int for m in (inputs, cached)):
            reason = "Both input and cached input counters must be observed in the same attempt."
        elif not 0 <= cached["value"] <= inputs["value"]:
            reason = "Cached input must be a nonnegative subset of input."
        elif any(m.get("kind") not in {"runtime_counter", "provider_reported_usage"} for m in (inputs, cached)):
            reason = "Paired cache derivations require observed counters, not offline token estimates."
        elif any(m.get("unit") != "tokens" for m in (inputs, cached)):
            reason = "Paired counters must use token units."
        elif any(inputs.get(k) != cached.get(k) for k in ("source", "kind", "method")) or any(
            inputs.get("details", {}).get(k) != cached.get("details", {}).get(k)
            for k in ("runtime_version", "extraction_version", "counting_rules", "compatibility")
        ):
            reason = "Input and cached input have incompatible source or extraction provenance."
        elif inputs.get("details", {}).get("counting_rules", {}).get("cached_input_tokens_subset_of_input_tokens") != "true":
            reason = "Source does not declare cached input to be a subset of input."
        elif any(envelope["source_identity"] not in m.get("evidence_references", ()) for m in (inputs, cached)):
            reason = "Paired counters do not identify the same attempt source."
        if reason:
            excluded.append({**identity, "reason": reason})
        else:
            pairs.append({**identity, "source_identity": envelope["source_identity"],
                          "input_tokens": deepcopy(inputs), "cached_input_tokens": deepcopy(cached)})
    complete_pairs = sum(all(p[k]["availability"] == "available" for k in ("input_tokens", "cached_input_tokens")) for p in pairs)
    coverage = {"paired_attempts": len(pairs), "observed_attempts": len(attempts),
                "paired_observations": len({p["observation_id"] for p in pairs}),
                "observed_observations": observed, "planned_observations": planned,
                "excluded_attempts": len(excluded), "complete_pair_attempts": complete_pairs}
    signatures = {tuple((_compatibility(p[k]), p[k].get("method"), p[k].get("details", {}).get("extraction_version"))
                        for k in ("input_tokens", "cached_input_tokens")) for p in pairs}
    compatible = len(signatures) <= 1
    total_input = sum(p["input_tokens"]["value"] for p in pairs) if compatible and pairs else None
    total_cached = sum(p["cached_input_tokens"]["value"] for p in pairs) if compatible and pairs else None
    details = {"coverage": coverage, "paired_input_tokens": total_input, "paired_cached_input_tokens": total_cached,
               "execution_boundary_fingerprint": boundary_fingerprint, "inputs": pairs, "excluded": excluded,
               "denominator_coverage": {**coverage, "input_tokens": total_input}}
    refs = sorted({p["evidence_identity"] for p in pairs} | {ref for p in pairs for k in ("input_tokens", "cached_input_tokens") for ref in p[k]["evidence_references"]})
    complete = observed == planned and len(pairs) == len(attempts) and complete_pairs == len(pairs)
    result = {}
    for role, unit, formula in (("uncached_input_tokens", "tokens", "sum(input - cached input) over eligible attempt pairs"),
                                ("cache_read_fraction", "ratio", "sum(paired cached input) / sum(paired input)")):
        reason = ("No eligible paired input/cached input evidence." if not pairs else
                  "Incompatible measurement sources or counting rules across attempt pairs." if not compatible else
                  "Paired input denominator is zero." if role == "cache_read_fraction" and total_input == 0 else None)
        if reason:
            value = unavailable_measurement(role, reason, unit=unit)
            if pairs and not compatible:
                value["availability"] = "non_comparable"
            value["details"].update(deepcopy(details))
            value["evidence_references"] = refs
        else:
            numeric = total_input - total_cached if role == "uncached_input_tokens" else total_cached / total_input
            value = observed_measurement(numeric, unit=unit, kind="derived_cache_counter", source=pairs[0]["input_tokens"]["source"],
                meaning="Original-run paired attempt counters, including failed attempts and retries; not billing usage.",
                method="paired-cache@1.0.0: " + formula, evidence_references=refs, details=deepcopy(details))
            value["availability"] = "available" if complete else "partial"
        result[role] = value
    return result
