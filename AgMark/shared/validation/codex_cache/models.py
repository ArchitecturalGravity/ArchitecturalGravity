"""Independent, immutable provider-request replay authority.

These records never represent scored measurements. Serialization is exact;
missing observations remain null with their own availability and provenance.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from collections.abc import Mapping
from types import MappingProxyType
import math

SCHEMA_ID = "arcgrav.shared.schema.provider-request-cache-validation"
TREATMENT_SCHEMA_ID = "arcgrav.shared.schema.provider-request-cache-treatment"
SCHEMA_VERSION = "2.0.0"
SCOPE = "configuration_equivalent_replay"
TOKEN_FIELDS = ("input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                "uncached_input_tokens", "output_tokens", "reasoning_tokens")
REQUEST_FIELDS = (*TOKEN_FIELDS, "request_duration_ms", "cache_read_fraction",
                  "after_prewarm", "generate", "previous_response_id", "response_id",
                  "retry", "reconnect", "thread_id", "context_type", "cache_key_value",
                  "cache_key_provenance", "cache_key_observed")
CONFIG_FIELDS = ("execution_boundary_fingerprint", "prompt_sha256", "input_sha256",
                 "runtime_id", "runtime_version", "runtime_binary_sha256",
                 "runner_registration_sha256", "provider", "model", "service_tier",
                 "launch_mode", "workspace_state_id", "relevant_controls",
                 "tools_sha256", "ambient_configuration_equal", "features_sha256",
                 "environment_sha256", "permissions_sha256", "repository_state_id")
CAPABILITY_FIELDS = ("validation_id", "request_boundaries", "request_kind",
                     "completion_correlation", *TOKEN_FIELDS[:3], "output_tokens",
                     "reasoning_tokens", "response_identity", "continuation_identity",
                     "transport", "retry", "reconnect", "request_duration_ms", "cache_key")


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")


def _count(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def _map(value, name, cls, keys=None):
    if not isinstance(value, Mapping) or any(type(v) is not cls for v in value.values()):
        raise ValueError(f"{name} has invalid typed members")
    if keys is not None and set(value) != set(keys):
        raise ValueError(f"{name} requires exactly {keys}")
    return MappingProxyType(dict(value))


def _typed(record, **members):
    for name, cls in members.items():
        if type(getattr(record, name)) is not cls:
            raise ValueError(f"{name} requires typed {cls.__name__}")


def _sequences(record, *names):
    for name in names:
        values = getattr(record, name)
        if not isinstance(values, (tuple, list)):
            raise ValueError(f"{name} must be a sequence")
        for value in values:
            _text(value, name)
        object.__setattr__(record, name, tuple(values))


def configuration_classification(expected, observed):
    matched, unavailable, mismatch = [], [], []
    for key in CONFIG_FIELDS:
        a, b = expected[key], observed[key]
        if a.availability != "available" or b.availability != "available":
            unavailable.append(key)
        elif type(a.value) is type(b.value) and a.value == b.value:
            matched.append(key)
        else:
            mismatch.append(key + ": expected and observed differ")
    status = "non_comparable" if mismatch else "unavailable" if not matched else "partial" if unavailable else "comparable"
    return status, tuple(matched), tuple(unavailable), tuple(mismatch)


def to_value(value):
    if is_dataclass(value):
        return {f.name: to_value(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {k: to_value(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [to_value(v) for v in value]
    return value


class Record:
    def to_dict(self):
        return to_value(self)


@dataclass(frozen=True)
class ProviderRequestFieldAvailability(Record):
    value: str | int | float | bool | None
    availability: str
    source: str
    method: str
    reason: str | None = None
    evidence_references: tuple[str, ...] = ()

    def __post_init__(self):
        if self.availability not in {"available", "partial", "unavailable", "inferred", "non_comparable"}:
            raise ValueError("invalid field availability")
        _text(self.source, "source")
        _text(self.method, "method")
        if self.value is not None and type(self.value) not in {str, int, float, bool}:
            raise ValueError("field value must be a JSON scalar")
        if type(self.value) is float and not math.isfinite(self.value):
            raise ValueError("field value must be finite")
        if self.availability in {"unavailable", "non_comparable"}:
            if self.value is not None or not self.reason:
                raise ValueError("unavailable fields require null and a reason")
        elif self.value is None or self.value == "":
            raise ValueError("observed fields require a value")
        if self.reason is not None:
            _text(self.reason, "reason")
        refs = tuple(self.evidence_references)
        for ref in refs:
            _text(ref, "evidence reference")
        object.__setattr__(self, "evidence_references", refs)

    @classmethod
    def unavailable(cls, reason="not_observed", source="replay", method="not_observed"):
        return cls(None, "unavailable", source, method, reason)


@dataclass(frozen=True)
class ValidationConfigurationMatch(Record):
    status: str
    expected: Mapping[str, ProviderRequestFieldAvailability]
    observed: Mapping[str, ProviderRequestFieldAvailability]
    matched_fields: tuple[str, ...]
    unavailable_fields: tuple[str, ...]
    mismatch_reasons: tuple[str, ...]

    def __post_init__(self):
        if self.status not in {"comparable", "non_comparable", "partial", "unavailable"}:
            raise ValueError("invalid configuration status")
        for name in ("expected", "observed"):
            object.__setattr__(self, name, _map(getattr(self, name), name, ProviderRequestFieldAvailability, CONFIG_FIELDS))
        for values in (self.expected, self.observed):
            ambient = values["ambient_configuration_equal"]
            if ambient.availability == "available" and type(ambient.value) is not bool:
                raise ValueError("ambient configuration comparison must be an attested boolean")
        _sequences(self, "matched_fields", "unavailable_fields", "mismatch_reasons")
        actual = (self.status, self.matched_fields, self.unavailable_fields, self.mismatch_reasons)
        if actual != configuration_classification(self.expected, self.observed):
            raise ValueError("configuration classification differs from retained values")


@dataclass(frozen=True)
class RuntimeEquivalence(Record):
    status: str
    stock_binary_sha256: ProviderRequestFieldAvailability
    observed_binary_sha256: ProviderRequestFieldAvailability
    runtime_version: ProviderRequestFieldAvailability
    patch_sha256: ProviderRequestFieldAvailability
    instrumentation: str
    demonstrated_scope: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    def __post_init__(self):
        _sequences(self, "demonstrated_scope", "evidence_references", "reasons")
        _text(self.instrumentation, "instrumentation")
        for name in ("stock_binary_sha256", "observed_binary_sha256", "runtime_version", "patch_sha256"):
            if type(getattr(self, name)) is not ProviderRequestFieldAvailability:
                raise ValueError("typed runtime fields required")
        if self.status == "exact_stock" and (self.runtime_version.availability != "available" or self.patch_sha256.value is not None or self.reasons):
            raise ValueError("exact stock requires version and no patch or mismatch")
        if self.status in {"unavailable", "non_comparable"} and not self.reasons:
            raise ValueError("runtime classification requires reasons")
        if self.status not in {"exact_stock", "instrumented_equivalent", "non_comparable", "unavailable"}:
            raise ValueError("invalid runtime equivalence")
        if self.status == "exact_stock" and (
            self.stock_binary_sha256.availability != "available" or
            self.observed_binary_sha256.availability != "available" or
            self.stock_binary_sha256.value != self.observed_binary_sha256.value or
            self.instrumentation != "stock"
        ):
            raise ValueError("exact stock requires equal observed binary hashes")
        if self.status == "instrumented_equivalent":
            # No hook implementation or equivalence verifier is currently
            # registered. A supplied patch hash/scope is not controlled proof.
            raise ValueError("instrumented runtime equivalence is not admitted")


@dataclass(frozen=True)
class Capability(Record):
    status: str
    method: str
    evidence_references: tuple[str, ...]
    limitation: str | None = None

    def __post_init__(self):
        _sequences(self, "evidence_references")
        if self.limitation is not None:
            _text(self.limitation, "capability limitation")
        if self.status not in {"supported", "partial", "unsupported", "unavailable"}:
            raise ValueError("invalid capability")
        _text(self.method, "capability method")
        if self.status in {"supported", "partial"} and not self.evidence_references:
            raise ValueError("capability requires controlled evidence")


@dataclass(frozen=True)
class ValidationCapabilities(Record):
    fields: Mapping[str, Capability]

    def __post_init__(self):
        object.__setattr__(self, "fields", _map(self.fields, "capabilities", Capability, CAPABILITY_FIELDS))


@dataclass(frozen=True)
class ProviderRequestCacheRecord(Record):
    request_id: str
    request_ordinal: int
    request_kind: str
    transport: str
    continuation_mode: str
    fields: Mapping[str, ProviderRequestFieldAvailability]
    correlation_method: str
    lifecycle_id: str | None = None
    warmup_request_id: str | None = None
    missing_fields: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()

    def __post_init__(self):
        _sequences(self, "missing_fields", "limitations", "evidence_references")
        for name in ("lifecycle_id", "warmup_request_id"):
            if getattr(self, name) is not None:
                _text(getattr(self, name), name)
        _text(self.request_id, "request_id")
        _count(self.request_ordinal, "request_ordinal")
        if self.request_ordinal < 1:
            raise ValueError("request ordinal starts at one")
        if self.request_kind not in {"warmup", "generation", "helper_internal", "unknown"}:
            raise ValueError("invalid request kind")
        if self.transport not in {"websocket", "http", "unknown"}:
            raise ValueError("invalid transport")
        if self.continuation_mode not in {"full", "incremental", "unknown"}:
            raise ValueError("invalid continuation")
        if self.correlation_method not in {"span_ancestry", "lifecycle_id", "request_response_id"}:
            raise ValueError("request requires deterministic correlation")
        object.__setattr__(self, "fields", _map(self.fields, "request fields", ProviderRequestFieldAvailability, REQUEST_FIELDS))
        for name in (*TOKEN_FIELDS, "request_duration_ms", "cache_read_fraction"):
            field = self.fields[name]
            if field.value is not None and (type(field.value) not in {int, float} or field.value < 0):
                raise ValueError(f"{name} must be nonnegative numeric or unavailable")
            if name in TOKEN_FIELDS and field.value is not None and type(field.value) is not int:
                raise ValueError(f"{name} must be integer")
        for name in ("after_prewarm", "generate", "retry", "reconnect", "cache_key_observed"):
            if self.fields[name].value is not None and type(self.fields[name].value) is not bool:
                raise ValueError(f"{name} must be boolean")
        for name in ("previous_response_id", "response_id", "thread_id", "context_type", "cache_key_value", "cache_key_provenance"):
            value = self.fields[name].value
            if value is not None:
                _text(value, name)
        generate = self.fields["generate"]
        if generate.availability == "available" and ((self.request_kind == "generation" and generate.value is False) or
                                                     (self.request_kind == "warmup" and generate.value is True)):
            raise ValueError("request kind contradicts observed generate flag")
        if self.fields["request_duration_ms"].value is not None and (
            not self.lifecycle_id or self.fields["request_duration_ms"].method != "finalized_transmission_to_terminal_completion"
        ):
            raise ValueError("duration requires correlated logical lifecycle")


@dataclass(frozen=True)
class SummaryMeasurement(Record):
    field: ProviderRequestFieldAvailability
    contributors: int
    eligible: int
    statistic: str

    def __post_init__(self):
        _typed(self, field=ProviderRequestFieldAvailability)
        _count(self.contributors, "contributors")
        _count(self.eligible, "eligible")
        if self.contributors > self.eligible:
            raise ValueError("contributors exceed eligible coverage")
        if self.statistic not in {"count", "sum", "first", "ratio", "mean", "median", "min", "max"}:
            raise ValueError("explicit statistic required")
        if self.field.value is not None and not self.contributors:
            raise ValueError("numeric summary requires contributors")


@dataclass(frozen=True)
class ProviderRequestCacheReplaySummary(Record):
    validation_id: str
    validates_observation_id: str
    treatment_id: str
    repetition_id: str
    configuration_match_status: str
    runtime_equivalence: str
    metrics: Mapping[str, SummaryMeasurement]
    first_request_kind: ProviderRequestFieldAvailability
    first_generation_ordinal: ProviderRequestFieldAvailability
    limitations: tuple[str, ...] = ()

    def __post_init__(self):
        _typed(self, first_request_kind=ProviderRequestFieldAvailability, first_generation_ordinal=ProviderRequestFieldAvailability)
        _sequences(self, "limitations")
        object.__setattr__(self, "metrics", _map(self.metrics, "summary metrics", SummaryMeasurement))


@dataclass(frozen=True)
class ProviderRequestCacheValidation(Record):
    schema_id: str
    schema_version: str
    validation_id: str
    validates_observation_id: str
    treatment_id: str
    repetition_id: str
    generation_id: str
    validation_scope: str
    separate_invocation: bool
    included_in_score: bool
    status: str
    configuration_match: ValidationConfigurationMatch
    runtime_equivalence: RuntimeEquivalence
    capabilities: ValidationCapabilities
    replay_summary: ProviderRequestCacheReplaySummary
    requests: tuple[ProviderRequestCacheRecord, ...]
    provenance: str
    evidence_references: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    extensions: Mapping[str, ProviderRequestFieldAvailability] = field(default_factory=dict)

    def __post_init__(self):
        _typed(self, configuration_match=ValidationConfigurationMatch, runtime_equivalence=RuntimeEquivalence,
               capabilities=ValidationCapabilities, replay_summary=ProviderRequestCacheReplaySummary)
        _sequences(self, "evidence_references", "limitations")
        if (self.schema_id, self.schema_version) != (SCHEMA_ID, SCHEMA_VERSION):
            raise ValueError("unsupported replay schema identity")
        if self.validation_scope != SCOPE or self.separate_invocation is not True or self.included_in_score is not False:
            raise ValueError("replay must remain separate and excluded from score")
        for name in ("validation_id", "validates_observation_id", "treatment_id", "repetition_id", "generation_id", "provenance"):
            _text(getattr(self, name), name)
        if self.status not in {"planned", "unavailable", "failed", "completed"}:
            raise ValueError("invalid replay status")
        requests = tuple(self.requests)
        if any(type(r) is not ProviderRequestCacheRecord for r in requests):
            raise ValueError("normalized typed requests required")
        if len({r.request_id for r in requests}) != len(requests) or [r.request_ordinal for r in requests] != list(range(1, len(requests) + 1)):
            raise ValueError("requests require unique identity and contiguous order")
        if requests and self.status not in {"completed", "failed"}:
            raise ValueError("unattempted replay cannot contain requests")
        dependencies = {k: k for k in (*TOKEN_FIELDS[:3], "output_tokens", "reasoning_tokens", "retry", "reconnect", "request_duration_ms")}
        dependencies.update(response_id="response_identity", previous_response_id="continuation_identity",
                            cache_key_value="cache_key", cache_key_provenance="cache_key", cache_key_observed="cache_key")
        for request in requests:
            for required in ("validation_id", "request_boundaries", "completion_correlation"):
                if self.capabilities.fields[required].status != "supported":
                    raise ValueError("request correlation capability not established")
            for name, capability in dependencies.items():
                if request.fields[name].value is not None and self.capabilities.fields[capability].status != "supported":
                    raise ValueError(f"{name} exceeds demonstrated capability")
            if request.transport != "unknown" and self.capabilities.fields["transport"].status != "supported":
                raise ValueError("transport capability not established")
            if request.continuation_mode != "unknown" and self.capabilities.fields["continuation_identity"].status != "supported":
                raise ValueError("continuation capability not established")
            kind = self.capabilities.fields["request_kind"].status
            if request.request_kind != "unknown" and not (kind == "supported" or kind == "partial" and request.request_kind == "generation"):
                raise ValueError("request kind exceeds demonstrated capability")
        for name in ("validation_id", "validates_observation_id", "treatment_id", "repetition_id"):
            if getattr(self, name) != getattr(self.replay_summary, name):
                raise ValueError("replay summary linkage differs")
        if self.configuration_match.status != self.replay_summary.configuration_match_status or self.runtime_equivalence.status != self.replay_summary.runtime_equivalence:
            raise ValueError("replay summary comparison differs")
        object.__setattr__(self, "requests", requests)
        object.__setattr__(self, "extensions", _map(self.extensions, "extensions", ProviderRequestFieldAvailability))


@dataclass(frozen=True)
class ValidationCoverage(Record):
    scored_observation_count: int
    validation_replays_planned: int
    validation_replays_attempted: int
    validation_replays_completed: int
    validation_replays_comparable: int
    request_lifecycle_available: int
    token_usage_available: int
    comparable_coverage: ProviderRequestFieldAvailability

    def __post_init__(self):
        _typed(self, comparable_coverage=ProviderRequestFieldAvailability)
        for name in (f.name for f in fields(self) if f.name != "comparable_coverage"):
            _count(getattr(self, name), name)
        if not (self.validation_replays_comparable <= self.validation_replays_completed <= self.validation_replays_attempted <= self.validation_replays_planned):
            raise ValueError("inconsistent replay coverage")
        if max(self.request_lifecycle_available, self.token_usage_available) > self.validation_replays_completed:
            raise ValueError("field coverage exceeds completed replays")
        if self.scored_observation_count == 0 and self.comparable_coverage.value is not None:
            raise ValueError("zero denominator must remain unavailable")


@dataclass(frozen=True)
class ProviderRequestCacheTreatmentSummary(Record):
    schema_id: str
    schema_version: str
    generation_id: str
    treatment_id: str
    validation_scope: str
    coverage: ValidationCoverage
    metrics: Mapping[str, Mapping[str, SummaryMeasurement]]
    replays: tuple[ProviderRequestCacheValidation, ...]
    sampling_policy: str
    sampling_reason: str
    sampled_observation_ids: tuple[str, ...]
    scored_observation_ids: tuple[str, ...]
    limitations: tuple[str, ...] = ()
    extensions: Mapping[str, ProviderRequestFieldAvailability] = field(default_factory=dict)

    def __post_init__(self):
        _typed(self, coverage=ValidationCoverage)
        _sequences(self, "sampled_observation_ids", "scored_observation_ids", "limitations")
        for name in ("generation_id", "treatment_id", "sampling_policy", "sampling_reason"):
            _text(getattr(self, name), name)
        replays = tuple(self.replays)
        if any(type(r) is not ProviderRequestCacheValidation for r in replays):
            raise ValueError("typed replays required")
        object.__setattr__(self, "replays", replays)
        if len(set(self.scored_observation_ids)) != len(self.scored_observation_ids):
            raise ValueError("duplicate scored observation identity")
        if self.sampled_observation_ids != tuple(r.validates_observation_id for r in replays) or not set(self.sampled_observation_ids) <= set(self.scored_observation_ids):
            raise ValueError("sampled replay observation linkage differs")
        if (self.schema_id, self.schema_version, self.validation_scope) != (TREATMENT_SCHEMA_ID, SCHEMA_VERSION, SCOPE):
            raise ValueError("unsupported treatment validation identity")
        if any(r.treatment_id != self.treatment_id or r.generation_id != self.generation_id for r in self.replays):
            raise ValueError("cross-treatment/generation replay merge")
        if len({r.validation_id for r in self.replays}) != len(self.replays):
            raise ValueError("duplicate replay identity")
        object.__setattr__(self, "metrics", MappingProxyType({k: _map(v, k, SummaryMeasurement) for k, v in self.metrics.items()}))
        object.__setattr__(self, "extensions", _map(self.extensions, "extensions", ProviderRequestFieldAvailability))
