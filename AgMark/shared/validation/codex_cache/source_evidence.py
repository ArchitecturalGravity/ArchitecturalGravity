"""Content-limited startup/capability sources and independent retained re-admission."""
import json
import re
from .capture import digest
from .collector import canonical_capture_spans
from .capabilities import admit_controlled_probe
from ...runtime.identity.runtime_version import retained_runtime_version
from .runtime_identity import cli_runtime_version, runtime_version

_HASH = re.compile(r"sha256:[0-9a-f]{64}")
STARTUP_FIELDS = {"observation_id", "generation_id", "frame_sha256", "phase", "runtime_binary_sha256",
    "runtime_version", "launch_mode", "platform", "workspace_state_id", "ambient_state_validation"}


def validate_source(kind, raw, *, transient=False):
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("invalid replay source")
    label = value.get("runtime_version")
    if not transient and isinstance(label, str):
        core = retained_runtime_version(label)
        expected_label = "codex-cli " + core if core and kind in {"startup", "probe"} else core
        if label != expected_label:
            raise ValueError("retained replay runtime version is not minimized")
    if kind == "startup":
        if set(value) != STARTUP_FIELDS or value["phase"] != "before_scored_invocation":
            raise ValueError("invalid startup source")
        cli_runtime_version(value["runtime_version"])
        if value["launch_mode"] not in {"native", "wsl"} or value["platform"] not in {"nt", "posix"}:
            raise ValueError("invalid startup host")
        for key in ("generation_id", "observation_id"):
            if not isinstance(value[key], str) or not re.fullmatch(r"[A-Za-z0-9:._-]+", value[key]):
                raise ValueError("invalid startup identity")
        if value["ambient_state_validation"] != "transient_equality_only":
            raise ValueError("invalid ambient-state evidence policy")
        for key in STARTUP_FIELDS - {"observation_id", "generation_id", "phase", "runtime_version", "launch_mode", "platform", "ambient_state_validation"}:
            if not isinstance(value[key], str) or not _HASH.fullmatch(value[key]):
                raise ValueError("invalid startup hash")
    elif kind == "probe":
        required = {"runtime_version", "runtime_binary_sha256", "validation_id", "returncode", "provider_requests",
                    "spans", "rejected_payloads", "purpose"}
        if set(value) not in (required, required | {"websocket_probe"}):
            raise ValueError("invalid probe source")
        cli_runtime_version(value["runtime_version"])
        from uuid import UUID
        UUID(value["validation_id"])
        if not _HASH.fullmatch(value["runtime_binary_sha256"]) or value["returncode"] != 0 or value["rejected_payloads"] != 0:
            raise ValueError("unsuccessful probe source")
        websocket = value["purpose"] == "Controlled WebSocket warmup and generation with independently supplied synthetic counters; not live-provider behavior."
        if not websocket and value["purpose"] != "Controlled HTTP generation with independently supplied synthetic counters; not live-provider behavior.":
            raise ValueError("invalid probe scope")
        expected = [{"ordinal": 1, "kind": "warmup"}, {"ordinal": 2, "kind": "generation"}, {"ordinal": 3, "kind": "generation"}] if websocket else [{"ordinal": 1}, {"ordinal": 2}]
        if value["provider_requests"] != expected or canonical_capture_spans(value["spans"]) != value["spans"]:
            raise ValueError("probe content outside admitted policy")
        if "websocket_probe" in value:
            if websocket or "websocket_probe" in value["websocket_probe"]:
                raise ValueError("nested probe outside admitted policy")
            validate_source("probe", json.dumps(value["websocket_probe"]).encode(), transient=transient)
            if any(value["websocket_probe"][key] != value[key] for key in ("runtime_version", "runtime_binary_sha256")):
                raise ValueError("controlled probe runtime identities differ")
    elif kind == "capabilities":
        if set(value) != {"runtime_version", "runtime_binary_sha256", "fields", "probe_reference", "probe_sha256", "scope"}:
            raise ValueError("invalid capability source")
        runtime_version(value["runtime_version"])
        if any(not isinstance(value[key], str) or not _HASH.fullmatch(value[key])
               for key in ("runtime_binary_sha256", "probe_sha256")):
            raise ValueError("invalid capability identity")
        if value["probe_reference"] != "probe.json" or value["scope"] not in {"controlled HTTP generation only; no provider cache behavior or request trajectory claim", "controlled HTTP and WebSocket warmup/generation; no provider cache behavior or request trajectory claim"}:
            raise ValueError("invalid capability scope")
        from .models import CAPABILITY_FIELDS
        from .capabilities import HTTP_METHOD, HTTP_WEBSOCKET_METHOD
        dual = value["scope"].startswith("controlled HTTP and WebSocket")
        supported = {"validation_id", "request_boundaries", "completion_correlation", "input_tokens",
            "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_tokens", "transport"}
        if dual:
            supported.add("request_kind")
        expected_fields = {name: {
            "status": "supported" if name in supported else "partial" if name == "request_kind" else "unsupported",
            "method": HTTP_WEBSOCKET_METHOD if dual else HTTP_METHOD,
            "evidence_references": [value["probe_sha256"]],
            "limitation": None if name in supported else "Not independently established beyond admitted transport request kinds and generation counters." if dual else "Not independently established beyond HTTP generation counters."
        } for name in CAPABILITY_FIELDS}
        if value["fields"] != expected_fields:
            raise ValueError("capability fields outside admitted evidence policy")
    else:
        raise ValueError("unregistered replay source kind")
    return value


def verify_managed_sources(replay, observation, sources):
    key = "arcgrav.telemetry:startup-evidence"
    if key not in replay.extensions:
        return
    def source(kind):
        field = replay.extensions.get("arcgrav.telemetry:" + kind + "-evidence")
        if field is None or field.availability != "available" or field.value not in sources:
            raise ValueError("retained replay source unavailable")
        actual_kind, raw = sources[field.value]
        if actual_kind != kind or digest(raw) != field.value:
            raise ValueError("retained replay source identity differs")
        return validate_source(kind, raw), raw
    startup, _ = source("startup")
    execution = observation["extensions"]["arcgrav.runner:execution"]
    if (startup["generation_id"] != replay.generation_id or startup["observation_id"] != replay.validates_observation_id or
            startup["frame_sha256"] != execution["request_framing"]["sha256"]):
        raise ValueError("startup accepted observation linkage differs")
    expected = replay.configuration_match.expected
    for a, b in (("runtime_binary_sha256", "runtime_binary_sha256"),
                 ("workspace_state_id", "workspace_state_id")):
        if expected[a].value != startup[b]:
            raise ValueError("startup expected configuration differs")
    if expected["ambient_configuration_equal"].value is not True:
        raise ValueError("startup requires transient ambient-state comparison")
    controlled_environment = digest(json.dumps({"platform": startup["platform"],
        "launch_mode": startup["launch_mode"]}, sort_keys=True).encode())
    if expected["environment_sha256"].value != controlled_environment or expected["launch_mode"].value != startup["launch_mode"]:
        raise ValueError("controlled startup environment differs")
    has_capability = "arcgrav.telemetry:capabilities-evidence" in replay.extensions
    if not has_capability:
        if replay.requests or replay.status in {"completed", "failed"}:
            raise ValueError("attempted replay lacks controlled capability evidence")
        return
    probe, _ = source("probe")
    _, document = source("capabilities")
    startup_version = cli_runtime_version(startup["runtime_version"])
    if expected["runtime_version"].value != startup_version:
        raise ValueError("startup expected runtime version differs")
    capabilities, proof = admit_controlled_probe(probe, binary_sha256=startup["runtime_binary_sha256"],
        runtime_version=startup_version)
    if capabilities.to_dict() != replay.capabilities.to_dict() or proof["capabilities"] != document:
        raise ValueError("retained capability admission differs")
