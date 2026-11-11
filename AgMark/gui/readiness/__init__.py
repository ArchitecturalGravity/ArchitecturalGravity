"""Registration-driven GUI readiness projection."""

from os import name as os_name

from .models import RunnerReadinessProjection, BenchmarkEvidenceReadinessProjection
from .environment import derive_application_environment
from .evidence import _matching_benchmark_candidate, derive_benchmark_evidence_readiness
from .controls import _diagnostic, _human_label, _visible_values, _model_discovery_context_controls, _matching_source, _model_control_projection, _numeric_control_projection, _control_projection, _selected_control_projection, _default_launch_mode, _string_default, _control_applicable, _effective_selected_control_values, _selected_wsl_launch, _project_model_discovery, _project_resolved_configuration
from .probes.authentication import _invoke_optional_control_probe, probe_registered_runner_authentication
from .probes.model_discovery import probe_registered_runner_model_discovery, _model_discovery_context_fingerprints
from .runner import derive_runner_readiness

__all__ = [
    "RunnerReadinessProjection",
    "BenchmarkEvidenceReadinessProjection",
    "derive_application_environment",
    "derive_benchmark_evidence_readiness",
    "probe_registered_runner_authentication",
    "probe_registered_runner_model_discovery",
    "derive_runner_readiness"
]
