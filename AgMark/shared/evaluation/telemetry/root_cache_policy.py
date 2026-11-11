"""Project already validated retained root cache policy, without re-inference.

This describes stock CLI policy metadata. It is not a transmitted request key,
helper trajectory, request ledger, or physical cache-hit observation.
"""
from copy import deepcopy
import re
from .session_metrics import SESSION_METRICS

SESSION_RECORD = "openai.codex_cli:session-record"
_SESSION_CAPTURE = "openai.codex_cli:session-capture"
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_POLICY_FIELDS = (
    "cache_key_policy", "cache_key_value", "cache_key_provenance", "cache_key_observed",
    "cache_mode", "cache_mode_provenance", "cache_mode_limitation", "root_thread_id",
    "derived_contexts_observed", "usage_scope", "evidence_references", "source_references",
)


def project_root_cache_policies(attempts):
    """Return original-run metadata per authorized attempt, never replay values.

    Inputs are the validated (observation, attempt, envelope, artifact-reference)
    tuples used by shared measurement aggregation. The original session record is
    unindexed, so it cannot establish policy for a multi-attempt observation.
    """
    results = []
    for document, attempt, envelope, evidence in attempts:
        item = {"observation_id": document["observation_id"], "attempt": attempt["attempt"],
                "thread_id": None, "scope": "original_run_root", "availability": "unavailable",
                "reason": "retained_root_cache_policy_unavailable", "policy": None,
                "evidence_references": [evidence], "runtime_version": None,
                "method": "projection_of_existing_validated_retained_policy"}
        results.append(item)
        record = document.get("extensions", {}).get(SESSION_RECORD)
        if not isinstance(record, dict) or not isinstance(envelope, dict):
            continue
        item["thread_id"] = record.get("thread_id")
        item["runtime_version"] = record.get("runtime_version")
        if len(document.get("attempts", ())) != 1:
            item["reason"] = "root_policy_attempt_scope_not_established"
            continue
        if (record.get("observation_id") != document["observation_id"]
                or record.get("generation_id") != document.get("accepted_generation_id")
                or record.get("attempt") != attempt["attempt"]):
            item["reason"] = "root_policy_observation_attempt_linkage_differs"
            continue
        if record.get("runtime_version") != "0.159.0" or envelope.get("runtime_version") != "0.159.0":
            item["reason"] = "unaudited_codex_runtime_version"
            continue
        source = record.get("sha256")
        session = envelope.get("extensions", {}).get(SESSION_METRICS, {})
        captured = session.get("extensions", {}).get(_SESSION_CAPTURE)
        if (record.get("availability") != "retained" or not isinstance(source, str) or not _HASH.fullmatch(source)
                or envelope.get("source_identity") != source
                or captured != {k: v for k, v in record.items() if k != "content_base64"}):
            item["reason"] = "root_policy_retained_source_linkage_differs"
            continue
        policy = record.get("cache_policy")
        if not isinstance(policy, dict):
            continue
        if policy.get("reason") == "unaudited_codex_runtime_version":
            item["reason"] = "unaudited_codex_runtime_version"
            continue
        thread_id = record.get("thread_id")
        if (not isinstance(thread_id, str) or not thread_id
                or session.get("thread_id") != thread_id or policy.get("root_thread_id") != thread_id
                or policy.get("cache_key_value") != thread_id
                or policy.get("cache_key_policy") != "codex_root_session_id"
                or policy.get("cache_key_provenance") != "inferred_codex_0_159_0_root_default"
                or policy.get("cache_key_observed") is not False
                or policy.get("derived_contexts_observed") is not False
                or policy.get("cache_mode") != "implicit"
                or policy.get("cache_mode_provenance") != "codex_request_schema"
                or policy.get("evidence_references") != [source]):
            item["reason"] = "audited_fresh_exec_root_identity_not_established"
            continue
        item.update(availability="inferred", reason=None,
                    policy={key: deepcopy(policy[key]) for key in _POLICY_FIELDS if key in policy},
                    evidence_references=[evidence, source],
                    fresh_root_conditions={
                        "basis": "Existing retained Codex 0.159.0 extractor policy; no new raw-source inference.",
                        "root": "Audited fresh exec root with matching session_id/thread_id and no parent or fork.",
                        "linkage": "Retained observation, generation, single attempt, session source hash and thread agree.",
                        "limitation": "Inferred root default only; transmitted key, helper requests and physical cache hits are not observed."})
    return results
