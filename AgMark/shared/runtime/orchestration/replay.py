"""Post-finalization replay scheduling with immutable accepted linkage.

Missing restorable starting state creates explicit unavailable validation. This
pipeline never emits observations, attempts, retry/failure counts or scores.
"""
import json
from uuid import uuid4
from AgMark.shared.validation.codex_cache.models import (
    ProviderRequestCacheValidation, RuntimeEquivalence, ProviderRequestFieldAvailability as Field,
    SCHEMA_ID, SCHEMA_VERSION, SCOPE,
)
from AgMark.shared.validation.codex_cache.capabilities import unavailable_capabilities
from AgMark.shared.validation.codex_cache.comparison import configuration_values, compare_configuration
from AgMark.shared.validation.codex_cache.metrics import replay_summary, treatment_summary
from AgMark.shared.validation.codex_cache.capture import capture_replay, ReplayCaptureOptions, digest
from AgMark.shared.validation.codex_cache.normalization import normalize_spans
from AgMark.shared.validation.codex_cache.collector import canonical_capture_spans
from AgMark.shared.validation.codex_cache.diagnostics import EXTENSION, PROFILE, diagnostic_field
from AgMark.shared.runtime.identity import ExecutionBoundary
from ..identity.runtime_version import retained_runtime_version
from .finalization import AcceptedRun
from .unscored import ExecutedRun


REPLAY_CAPABILITY = "arcgrav.adapters:validation_replay"
CODEX_REPLAY_PROFILE = "codex_cli_cache_v1"


def supports_validation_replay(registration):
    """Only an explicit supported profile authorizes adapter-specific replay.

    Missing, unknown or malformed declarations remain unsupported. Neither a
    runner name nor request-supplied capture options may select a fallback.
    """
    from collections.abc import Mapping
    if not isinstance(registration, Mapping):
        return False
    extensions = registration.get("extensions")
    return (isinstance(extensions, Mapping)
            and extensions.get(REPLAY_CAPABILITY) == {"profile": CODEX_REPLAY_PROFILE})


def unsupported_validation_summaries(terminal):
    """Retain explicit non-execution, never hypothetical Codex replay facts."""
    observations = [json.loads(raw) for raw in terminal.treatment_observations]
    return tuple(treatment_summary(generation_id=terminal.generation_id,
        treatment_id=treatment, replays=(),
        scored_observation_ids=tuple(o["observation_id"] for o in observations if o["treatment_id"] == treatment),
        sampling_policy="unsupported_by_adapter", sampling_reason="adapter_validation_replay_unsupported")
        for treatment in dict.fromkeys(o["treatment_id"] for o in observations))


def _compare_capture_profile(comparison, runtime, profile):
    """Keep known original/replay instrumentation differences in comparison.

    Replay still runs after original finalization and retains its own evidence.
    A matching binary never makes different capture configurations equivalent.
    Historical replay interpretation remains unchanged for the legacy profile.
    """
    if profile in (None, "session"):
        return comparison, ()
    from AgMark.shared.validation.codex_cache.metrics import observed
    actual = dict(comparison.observed)
    actual["relevant_controls"] = observed(digest(json.dumps({
        "accepted_controls": comparison.expected["relevant_controls"].value,
        "original_capture_profile": profile,
        "executed_capture_profile": "stock_validation_traces_v1",
    }, sort_keys=True).encode()), "observed_replay_instrumentation_profile")
    result = compare_configuration(comparison.expected, actual, runtime_equivalence=runtime)
    reasons = ("original_and_replay_capture_profiles_differ",)
    if profile == "deep_telemetry":
        reasons += ("original_sensitive_diagnostic_header_and_overhead_not_replayed",)
    return result, reasons


def disabled_validation_summaries(terminal, *, cancelled=False):
    """Retain user disposition without preparing or invoking any replay work."""
    observations = [json.loads(raw) for raw in terminal.treatment_observations]
    return tuple(treatment_summary(generation_id=terminal.generation_id,
        treatment_id=treatment, replays=(),
        scored_observation_ids=tuple(o["observation_id"] for o in observations if o["treatment_id"] == treatment),
        sampling_policy="cancelled" if cancelled else "disabled_by_user", sampling_reason="Run cancelled" if cancelled else "Disabled by user")
        for treatment in dict.fromkeys(o["treatment_id"] for o in observations))


def validate_finalized_run(*, terminal, artifact_store, boundary, case_inputs, treatment_prompts,
                           capture_options=None, temporary_root=None, capture_evidence=None, startup_records=None, source_evidence=None, startup_diagnostics=None, activity=None):
    if type(terminal) not in (AcceptedRun, ExecutedRun):
        raise TypeError("replay requires finalized accepted authority")
    terminal.revalidate(artifact_store)
    if type(boundary) is not ExecutionBoundary or terminal.execution_boundary_fingerprint != boundary.fingerprint:
        raise ValueError("replay accepted boundary differs")
    boundary.revalidate()
    observations = [json.loads(raw) for raw in terminal.treatment_observations]
    prompts = {v.treatment_id:v.data for v in treatment_prompts}
    inputs = {v.case_id:v.data for v in case_inputs}
    registrations = [r for r in terminal.artifact_index.artifacts if r.role == "runner_registration"]
    if len(registrations) != 1:
        raise ValueError("exact accepted runner registration required")
    registration = json.loads(artifact_store.read_verified(registrations[0]))
    if not supports_validation_replay(registration):
        # Gate before accessing Codex framing, capture options or startup facts.
        return unsupported_validation_summaries(terminal)
    if capture_options:
        raise ValueError("replay requires runtime-owned pre-invocation startup authority")
    # Each replay binds its own accepted observation. The companion manifest
    # retains the complete scored-evidence map once, rather than copying every
    # observation reference into every replay.
    observation_evidence = {
        observation["observation_id"]: digest(raw)
        for observation, raw in zip(observations, terminal.treatment_observations, strict=True)
    }
    accepted_observation_hashes = {
        record.sha256 for record in terminal.artifact_index.artifacts
        if record.role == "treatment_observation"
    }
    if not set(observation_evidence.values()) <= accepted_observation_hashes:
        raise ValueError("replay observation evidence differs from accepted artifacts")
    results = []
    capability_cache = {}
    for replay_index, observation in enumerate(observations, 1):
        if activity is not None:
            activity.emit("replay", replay_index, len(observations))
        validation_id = str(uuid4())
        observation_id, treatment_id = observation["observation_id"], observation["treatment_id"]
        prompt, case_input = prompts[treatment_id], inputs[observation["case_id"]]
        config = configuration_values(boundary, prompt_sha256=digest(prompt), input_sha256=digest(case_input),
            runner_registration_sha256=registrations[0].sha256)
        # The accepted observation itself must establish the submitted bytes.
        evidence = observation.get("extensions", {}).get("arcgrav.shared:execution-evidence", {})
        if not evidence:
            from AgMark.shared.adapters.execution.emission import EXECUTION_EVIDENCE_EXTENSION_KEY
            evidence = observation.get("extensions", {}).get(EXECUTION_EVIDENCE_EXTENSION_KEY, {})
        if evidence.get("request_framing", {}).get("sha256") != digest(prompt + b"\n\n" + case_input):
            raise ValueError("replay framing differs from accepted scored invocation")
        unavailable = Field.unavailable("replay_start_state_not_reproducible")
        runtime = RuntimeEquivalence("unavailable", unavailable, unavailable, unavailable, unavailable, "stock",
                                     reasons=("replay_start_state_not_reproducible",))
        capabilities = unavailable_capabilities()
        requests, status = (), "unavailable"
        limitations = ("replay_start_state_not_reproducible",)
        if (startup_diagnostics or {}).get(observation_id) == "pre_invocation_startup_capture_unavailable":
            limitations += ("pre_invocation_startup_capture_unavailable",)
        comparison = compare_configuration(config, config, runtime_equivalence=runtime)
        extensions = {}
        startup = (startup_records or {}).get(observation_id)
        if startup is not None:
            comparison, runtime, capabilities, requests, status, limitations, extensions = _managed_replay(
                startup, boundary=boundary, generation_id=terminal.generation_id, observation_id=observation_id,
                validation_id=validation_id, prompt=prompt, case_input=case_input,
                registration_sha256=registrations[0].sha256, capture_evidence=capture_evidence,
                source_evidence=source_evidence, capability_cache=capability_cache,
                activity=activity, replay_index=replay_index, replay_total=len(observations))
        profile = next((control["value"] for control in boundary.to_dict()["controls"]
                        if control["name"] == "capture_mode"), "session")
        comparison, profile_limits = _compare_capture_profile(comparison, runtime, profile)
        limitations = (*limitations, *profile_limits)
        ids = dict(validation_id=validation_id, validates_observation_id=observation_id,
                   treatment_id=treatment_id, repetition_id=str(observation["repetition"]))
        summary = replay_summary(**ids, configuration_match=comparison, runtime_equivalence=runtime,
            capabilities=capabilities, requests=requests, limitations=limitations)
        results.append(ProviderRequestCacheValidation(SCHEMA_ID, SCHEMA_VERSION, **ids,
            generation_id=terminal.generation_id, validation_scope=SCOPE, separate_invocation=True,
            included_in_score=False, status=status, configuration_match=comparison,
            runtime_equivalence=runtime, capabilities=capabilities, replay_summary=summary,
            requests=requests, provenance="accepted post-treatment configuration-equivalent replay",
            evidence_references=(observation_evidence[observation_id],) +
                tuple(field.value for key, field in extensions.items() if key.endswith("-evidence") and field.availability == "available"),
            limitations=limitations, extensions=extensions))
    terminal.revalidate(artifact_store)
    return tuple(treatment_summary(generation_id=terminal.generation_id, treatment_id=treatment,
        replays=tuple(r for r in results if r.treatment_id == treatment),
        scored_observation_ids=tuple(o["observation_id"] for o in observations if o["treatment_id"] == treatment))
        for treatment in dict.fromkeys(o["treatment_id"] for o in observations))


def _managed_replay(startup, *, boundary, generation_id, observation_id, validation_id, prompt,
                    case_input, registration_sha256, capture_evidence, source_evidence, capability_cache,
                    activity=None, replay_index=0, replay_total=0):
    from dataclasses import replace
    import subprocess
    from AgMark.shared.validation.codex_cache.startup import StartupRecord
    from AgMark.shared.validation.codex_cache.metrics import observed
    if type(startup) is not StartupRecord or startup.generation_id != generation_id or startup.observation_id != observation_id:
        raise ValueError("startup accepted linkage differs")
    if startup.frame_sha256 != digest(prompt + b"\n\n" + case_input):
        raise ValueError("startup framing differs")
    if capture_evidence is None or source_evidence is None:
        raise ValueError("managed replay requires caller-owned evidence retention")
    snapshot = startup.revalidate()
    config_args = dict(prompt_sha256=digest(prompt), input_sha256=digest(case_input),
                       runner_registration_sha256=registration_sha256)
    expected = startup.configuration(boundary, **config_args)
    unknown = Field.unavailable("replay_runtime_unavailable")
    runtime = RuntimeEquivalence("unavailable", unknown, unknown, unknown, unknown, "stock",
        reasons=("replay_runtime_unavailable",))
    caps, requests, status = unavailable_capabilities(), (), "unavailable"
    comparison = compare_configuration(expected, {k: unknown for k in expected}, runtime_equivalence=runtime)
    extensions = {}
    def retain(kind, data):
        identity = digest(data)
        source_evidence[identity] = (kind, data)
        extensions["arcgrav.telemetry:" + kind + "-evidence"] = observed(identity, "retained_" + kind)
    retain("startup", json.dumps(startup.public_document(), sort_keys=True, separators=(",", ":")).encode())
    try:
        controls = {v["name"]: v["value"] for v in boundary.to_dict()["controls"]}
        if controls.get("tool_policy") != "workspace_write" or controls.get("memory_policy") != "disabled":
            return comparison, runtime, caps, requests, status, ("replay_safety_policy_not_admitted",), extensions
        if any(name.startswith("hooks/") for name in snapshot["profile"]):
            return comparison, runtime, caps, requests, status, ("replay_profile_hooks_not_isolatable",), extensions
        actual = startup.current()
        exact = snapshot["binary_sha256"] == actual["binary_sha256"] and snapshot["version"] == actual["version"]
        runtime = RuntimeEquivalence("exact_stock" if exact else "non_comparable",
            observed(snapshot["binary_sha256"], "pre_invocation_binary"), observed(actual["binary_sha256"], "replay_binary"),
            observed(retained_runtime_version(actual["version"]), "selected_host_runtime"),
            Field.unavailable("stock_has_no_patch"), "stock", reasons=() if exact else ("runtime_binary_or_version_changed",))
        current = replace(startup, snapshot_bytes=json.dumps(actual, sort_keys=True).encode())
        observed_config = current.configuration(boundary, observed_launch=True, ambient_equivalent=(actual == snapshot), **config_args)
        comparison = compare_configuration(expected, observed_config, runtime_equivalence=runtime)
        if comparison.status != "comparable":
            return comparison, runtime, caps, requests, status, ("replay_configuration_not_comparable",), extensions
        # Capability evidence belongs to this exact runtime on the selected
        # host. Identical binary bytes alone do not identify a version response,
        # WSL distribution, executable location, or launch environment.
        key = (snapshot["binary_sha256"], snapshot["version"],
            startup.transport.launch_mode, startup.transport.prefix, snapshot["platform"],
            snapshot["executable"], snapshot["environment_sha256"],
            digest(json.dumps(dict(startup.transport.environment), sort_keys=True).encode()))
        if key not in capability_cache:
            if activity is not None:
                activity.emit("capability", replay_index, replay_total)
            capability_cache[key] = startup.capabilities()
        caps, proof = capability_cache[key]
        for kind, data in proof.items():
            retain(kind, data)
        controls = {v["name"]: v["value"] for v in boundary.to_dict()["controls"]}
        timeout = max(1, min(300, int(controls.get("request_timeout_ms", 60000)) // 1000))
        if activity is not None:
            activity.emit("replay", replay_index, replay_total)
        spans, runtime, status, limitations, actual = startup.capture(validation_id, prompt + b"\n\n" + case_input, timeout)
        current = replace(startup, snapshot_bytes=json.dumps(actual, sort_keys=True).encode())
        comparison = compare_configuration(expected, current.configuration(boundary, observed_launch=True, ambient_equivalent=(actual == snapshot), **config_args), runtime_equivalence=runtime)
        if status in {"completed", "failed"}:
            spans = canonical_capture_spans(spans)
            data = json.dumps(spans, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            identity = digest(data)
            capture_evidence[identity] = data
            requests, reasons = normalize_spans(spans, validation_id=validation_id, capabilities=caps, evidence_reference=identity, profile=PROFILE)
            extensions[EXTENSION] = diagnostic_field(spans, validation_id=validation_id, evidence_reference=identity)
            limitations = (*limitations, *reasons)
            if not requests:
                limitations += ("request_evidence_not_observed",)
        return comparison, runtime, caps, requests, status, limitations, extensions
    except (ValueError, OSError, TypeError, KeyError, subprocess.SubprocessError):
        return comparison, runtime, caps, (), "unavailable", ("selected_host_replay_admission_unavailable",), extensions
