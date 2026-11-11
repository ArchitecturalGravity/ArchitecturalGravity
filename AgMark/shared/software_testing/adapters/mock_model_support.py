"""Test-only identity construction for the independent mock adapter."""
from AgMark.shared.adapters.Mock_Model.catalog import RUNNER_ID, VERSION
from AgMark.shared.runtime.identity import ProviderRuntimeIdentity


def resolve_model_identity(model_id):
    return ProviderRuntimeIdentity(runtime_id=RUNNER_ID, runtime_version=VERSION,
        provider="AgMark Mock Model", access_method="local_process", model=model_id), {
        "model_id": model_id, "request_timeout_ms": 120000, "maximum_attempts": 1,
        "memory_policy": "disabled", "request_framing": "mock_json_v1",
        "sampling_mode": "deterministic", "tool_policy": "none"}
