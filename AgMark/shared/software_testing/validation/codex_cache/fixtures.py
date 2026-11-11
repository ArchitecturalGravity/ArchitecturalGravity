"""Controlled normalized replay fixtures; no live provider authority."""
from AgMark.shared.validation.codex_cache.models import *
from AgMark.shared.validation.codex_cache.metrics import observed, derive_request, replay_summary

def capabilities():
    return ValidationCapabilities({k: Capability("supported", "controlled_fixture", ("fixture:capabilities",)) for k in CAPABILITY_FIELDS})

def configuration():
    values = {k: observed(True if k == "ambient_configuration_equal" else "fixture:" + k, "controlled_fixture") for k in CONFIG_FIELDS}
    return ValidationConfigurationMatch("comparable", values, values, CONFIG_FIELDS, (), ())

def runtime(runtime_version="0.159.0"):
    binary = observed("sha256:" + "a" * 64, "controlled_fixture")
    return RuntimeEquivalence("exact_stock", binary, binary, observed(runtime_version, "controlled_fixture"),
        ProviderRequestFieldAvailability.unavailable("stock_has_no_patch"), "stock")

def request(ordinal=1, *, kind="generation", input_tokens=100, cached=40, write=None,
            duration=10, warmup_request_id=None):
    fields = {k: ProviderRequestFieldAvailability.unavailable() for k in REQUEST_FIELDS}
    for k, v in (("input_tokens", input_tokens), ("cached_input_tokens", cached),
                 ("cache_write_input_tokens", write), ("output_tokens", 8), ("reasoning_tokens", 2),
                 ("retry", False), ("reconnect", False), ("generate", kind == "generation")):
        if v is not None:
            fields[k] = observed(v, "controlled_fixture", ("fixture:request",))
    if duration is not None:
        fields["request_duration_ms"] = observed(duration, "finalized_transmission_to_terminal_completion", ("fixture:lifecycle",))
    return derive_request(ProviderRequestCacheRecord("request-" + str(ordinal), ordinal, kind, "websocket", "full",
        fields, "lifecycle_id", "lifecycle-" + str(ordinal), warmup_request_id))

def replay(number=1, *, requests=None, config=None, state="completed"):
    requests = tuple(requests if requests is not None else (request(),))
    config, rt, caps = config or configuration(), runtime(), capabilities()
    ids = dict(validation_id="validation-" + str(number), validates_observation_id="observation-" + str(number),
               treatment_id="treatment", repetition_id=str(number))
    summary = replay_summary(**ids, configuration_match=config, runtime_equivalence=rt, capabilities=caps, requests=requests)
    return ProviderRequestCacheValidation(SCHEMA_ID, SCHEMA_VERSION, **ids, generation_id="generation",
        validation_scope=SCOPE, separate_invocation=True, included_in_score=False, status=state,
        configuration_match=config, runtime_equivalence=rt, capabilities=caps, replay_summary=summary,
        requests=requests, provenance="controlled_fixture; synthetic; no provider claims", evidence_references=("fixture:validation",))


def accepted_fixture(root, *, replay_supported=True, runtime_version="1.2.3"):
    """Accepted Codex lifecycle using controlled native I/O, never a provider.

    This is a Codex replay fixture, independent of the generic mock adapter and
    its configuration, framing, telemetry or replay capabilities.
    """
    from unittest.mock import patch
    from AgMark.shared.adapters.Codex_CLI import CodexCliRunner, load_registration
    from AgMark.shared.runtime.identity import ExecutionBoundary, IdentityRef
    from AgMark.shared.software_testing.adapters.codex_cli.test_runner import FakeCodexTransport, _controls
    from AgMark.shared.software_testing.runtime import test_scoring_orchestration as fixture
    from AgMark.shared.runtime.orchestration import score_accepted_treatments, finalize_scored_run
    from AgMark.shared.runtime.orchestration.replay import REPLAY_CAPABILITY
    registration = load_registration()
    if not replay_supported:
        registration["extensions"].pop(REPLAY_CAPABILITY, None)
    model = "gpt-5-codex"
    controls = {item["name"]: item["value"] for item in _controls(model_id=model)}
    controls.update(reasoning_effort="medium", capture_mode="session", codex_binary="runtime/codex")
    boundary = ExecutionBoundary.build(boundary_id="boundary-controlled-codex-replay",
        framework=IdentityRef("arcgrav.framework.runtime-scoring-test", "1.0.0"),
        runner=IdentityRef(registration["registration_id"], registration["registration_version"]),
        provider_runtime={"runtime_id": registration["registration_id"], "runtime_version": runtime_version,
                          "provider": "OpenAI", "access_method": "cli", "model": model},
        controls=controls, environment={"runtime_family": "controlled-native-transport"})
    catalog = {"data": [{"model": model, "displayName": "Controlled Codex model", "isDefault": True,
        "supportedReasoningEfforts": [{"reasoningEffort": "medium", "description": "Balanced"}],
        "defaultReasoningEffort": "medium"}], "nextCursor": None}
    def runner_factory(*, registration):
        return CodexCliRunner(registration=registration, transport=FakeCodexTransport(version=runtime_version),
            executable_resolver=lambda name: "/controlled/codex" if name == "codex" else None,
            platform_name="posix")
    owner = fixture.RegisteredScoringRuntimeTests()
    owner.setUp()
    with patch.object(fixture, "load_registration", return_value=registration), \
         patch.object(fixture, "_boundary", return_value=boundary), \
         patch("AgMark.shared.adapters.Codex_CLI.CodexCliRunner", new=runner_factory), \
         patch("AgMark.shared.adapters.Codex_CLI.model_discovery._run_interactive_model_list", return_value=catalog):
        boundary, plan, snapshot, store, gate, treatments = owner._started(root, generation_id="generation-replay-fixture")
    scores = score_accepted_treatments(gate=gate, snapshot=snapshot, benchmark=owner.benchmark,
        case_set=owner.case_set, treatment_set=owner.treatment_set, execution_boundary=boundary,
        treatment_result=treatments, artifact_store=store, scoring_definitions=(owner._definition(),))
    terminal = finalize_scored_run(gate=gate, treatment_result=treatments, scoring_result=scores, artifact_store=store)
    return terminal, boundary, store, plan
