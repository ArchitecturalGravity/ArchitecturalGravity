"""Provider-neutral model catalog and planning hooks for the bundled mock model."""
from __future__ import annotations
import hashlib
import json
from collections.abc import Mapping
from AgMark.shared.mock_model.protocol import MockRuntimeProtocol, ModelCatalogEntry, ModelProfileMapping
from AgMark.shared.mock_model.scenarios import KNOWN_INFERENCE_SCENARIOS

RUNNER_ID = "arcgrav.mock-model.runner"
VERSION = "1.0.0"
BASE_MODEL_ID = "mock-base"
MODELS = (ModelCatalogEntry(model_id=BASE_MODEL_ID, label="Mock Base", is_default=True), *(
    ModelCatalogEntry(model_id=f"{BASE_MODEL_ID}::scenario:{scenario}",
        label="Mock Base / " + scenario.replace("_", " "),
        profile=ModelProfileMapping(base_model_id=BASE_MODEL_ID, scenario_id=scenario))
    for scenario in sorted(KNOWN_INFERENCE_SCENARIOS)))


def runtime():
    return MockRuntimeProtocol(runtime_id=RUNNER_ID, runtime_version=VERSION,
        executable_id="agmark-mock-worker", capabilities=("inference", "model.discovery"), models=MODELS)


def probe_model_discovery(registration, *, control_values=None, **_unused):
    """Expose an adapter-owned catalog without provider I/O or inference."""
    if not isinstance(registration, Mapping) or registration.get("registration_id") != RUNNER_ID:
        return {"status": "unsupported", "error_code": "mock_registration_unsupported", "provider_submitted": False}
    choices = []
    for model in MODELS:
        scenario = model.profile.scenario_id if model.profile else "default"
        choices.append({"model_id": model.model_id, "label": model.label,
            "selection_mode": "explicit", "scenario": {
                "scenario_id": scenario, "label": scenario.replace("_", " ").capitalize(),
                "base_model_id": BASE_MODEL_ID, "model_id": model.model_id,
                "is_default": model.is_default}})
    projection = {"effective_default_model_id": BASE_MODEL_ID,
                  "selectable_model_ids": [m.model_id for m in MODELS], "choices": choices}
    return {"status": "ready", "provider_submitted": False,
            "surface": {"kind": "bundled_mock_catalog", "protocol": "agmark.mock-worker/1"},
            "resolved_configuration": {},
            "model_catalog_sha256": "sha256:" + hashlib.sha256(json.dumps(projection, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest(), **projection}


def probe_planning_identity(registration, *, control_values=None, **_unused):
    selected = dict(control_values or {})
    discovery = probe_model_discovery(registration)
    model = selected.get("model_id")
    timeout = selected.get("request_timeout_ms", 120000)
    if (discovery["status"] != "ready" or model not in discovery["selectable_model_ids"]
            or type(timeout) is not int or timeout < 1 or selected.get("maximum_attempts", 1) != 1):
        return {"status": "unsupported", "error_code": "mock_boundary_unsupported",
                "provider_submitted": False, "resolved_controls": {}}
    return {"status": "ready", "provider_submitted": False, "runtime_version": VERSION,
        "provider_runtime": {"runtime_id": RUNNER_ID, "runtime_version": VERSION,
            "provider": "AgMark Mock Model", "access_method": "local_process", "model": model},
        "resolved_controls": {"model_id": model, "request_timeout_ms": timeout, "maximum_attempts": 1},
        "noninteractive_surface_verified": True}
