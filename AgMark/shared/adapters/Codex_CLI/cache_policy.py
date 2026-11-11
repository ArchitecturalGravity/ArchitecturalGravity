"""Audited cache namespace policy, independent of token usage."""
from __future__ import annotations

_CODEX_SOURCE = "runtime/source/codex-rs/"

def _cache_policy(metadata, thread_id, runtime_version, source):
    """Infer only the audited root default; rollout counters are not wire evidence."""
    policy = {"cache_key_policy": None, "cache_key_value": None,
              "cache_key_provenance": None, "cache_key_observed": False,
              "cache_mode": None, "cache_mode_provenance": None,
              "root_thread_id": thread_id, "evidence_references": [source],
              "derived_contexts_observed": False,
              "usage_scope": "Root rollout totals, including any invocation-scoped derived cache usage reported there; helper usage is not independently separated."}
    if runtime_version != "0.159.0" or (metadata is not None and metadata.get("cli_version") == "unknown"):
        policy["reason"] = "unaudited_codex_runtime_version"
    elif metadata is None:
        policy["reason"] = "matched_root_session_metadata_unavailable"
    elif (metadata.get("source") != "exec" or metadata.get("cli_version") != runtime_version
          or metadata.get("session_id") != thread_id or metadata.get("parent_thread_id") is not None
          or metadata.get("forked_from_id") is not None):
        policy["reason"] = "audited_fresh_exec_root_identity_not_established"
    else:
        policy.update(cache_key_policy="codex_root_session_id", cache_key_value=thread_id,
                      cache_key_provenance="inferred_codex_0_159_0_root_default",
                      cache_mode="implicit", cache_mode_provenance="codex_request_schema",
                      cache_mode_limitation="Implicit cached-token totals can include growing conversation history.",
                      source_references=[_CODEX_SOURCE + "core/src/client.rs#L575-L596",
                                         _CODEX_SOURCE + "core/src/session/session.rs#L878-L915",
                                         _CODEX_SOURCE + "codex-api/src/common.rs#L279-L309"],
                      derived_context_policy={
                          "provenance": "inferred_codex_0_159_0_source",
                          "subagent": "Inherited root session_id",
                          "internal": "<internal source>:<parent_thread_id>, or inherited session_id without a parent",
                          "guardian_review": "guardian:<parent_thread_id>",
                          "ephemeral_root_fork": "Parent rollout session_id",
                          "persistent_root_fork": "New root session_id",
                          "source_references": [_CODEX_SOURCE + "core/src/guardian/review_session.rs#L272-L284",
                                                _CODEX_SOURCE + "core/src/session/session.rs#L878-L915"]})
    return policy
