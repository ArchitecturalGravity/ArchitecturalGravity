"""Accepted execution-boundary reuse and separate observed replay comparison."""
from .models import CONFIG_FIELDS, ValidationConfigurationMatch, ProviderRequestFieldAvailability as Field
from .metrics import observed
from AgMark.shared.runtime.identity import ExecutionBoundary, canonical_sha256


def configuration_values(boundary, *, prompt_sha256, input_sha256, runner_registration_sha256,
                         runtime_binary_sha256=None, workspace_state_id=None, supplemental=None):
    if type(boundary) is not ExecutionBoundary:
        raise TypeError("validated execution boundary required")
    boundary.revalidate()
    doc = boundary.to_dict()
    runtime = doc["provider_runtime"]
    controls = {v["name"]: v["value"] for v in doc["controls"]}
    environment = {v["name"]: v["value"] for v in doc["environment"]}
    raw = dict(execution_boundary_fingerprint=boundary.fingerprint, prompt_sha256=prompt_sha256,
        input_sha256=input_sha256, runner_registration_sha256=runner_registration_sha256,
        runtime_id=runtime["runtime_id"], runtime_version=runtime["runtime_version"], provider=runtime["provider"],
        model=runtime["model"], service_tier=controls.get("service_tier"),
        launch_mode=environment.get("launch_mode"), runtime_binary_sha256=runtime_binary_sha256,
        workspace_state_id=workspace_state_id, relevant_controls=canonical_sha256(doc["controls"]),
        environment_sha256=canonical_sha256(doc["environment"]))
    additional = supplemental or {}
    if set(additional) - set(CONFIG_FIELDS) or set(additional) & set(raw):
        raise ValueError("supplemental state cannot override accepted boundary values")
    raw.update(additional)
    return {k: observed(raw[k], "accepted_boundary_and_starting_state") if raw.get(k) is not None else
               Field.unavailable("comparison_field_not_observed") for k in CONFIG_FIELDS}


def compare_configuration(expected, actual, *, runtime_equivalence):
    if set(expected) != set(CONFIG_FIELDS) or set(actual) != set(CONFIG_FIELDS):
        raise ValueError("all comparison fields must preserve independent availability")
    # Instrumented equivalence needs separate demonstrated authority; a caller's
    # classification alone never overrides an actual binary difference.
    from .models import configuration_classification
    status, matched, unavailable, mismatch = configuration_classification(expected, actual)
    return ValidationConfigurationMatch(status, expected, actual, matched, unavailable, mismatch)
