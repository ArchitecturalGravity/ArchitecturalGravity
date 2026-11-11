"""Test-only registered scorer for the provider-free lifecycle harness."""

from __future__ import annotations

from collections.abc import Mapping
import json


def diagnostic_health_scorer(call) -> Mapping[str, object]:
    """Score only whether the provider-free diagnostic observation completed."""

    observation = json.loads(
        call.evidence_by_role["treatment_observation"].decode("utf-8")
    )
    if observation["terminal_status"] != "completed":
        return {
            "availability": "failed",
            "companion_values": [],
            "failure_refs": ["failure:" + observation["observation_id"]],
            "diagnostics": ["SHARED_SELF_TEST_TREATMENT_NOT_COMPLETED"],
            "extensions": {},
        }
    return {
        "availability": "scored",
        "value": 1.0,
        "companion_values": [],
        "failure_refs": [],
        "diagnostics": [],
        "extensions": {},
    }


__all__ = ["diagnostic_health_scorer"]
