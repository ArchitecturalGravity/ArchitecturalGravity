"""Integrity-bound controlled capability evidence, independent of scored audits."""
import hashlib
import json
from pathlib import Path
from .models import Capability, ValidationCapabilities, CAPABILITY_FIELDS
from ...runtime.identity.runtime_version import retained_runtime_version
from .runtime_identity import cli_runtime_version, runtime_version as validate_runtime_version

HTTP_METHOD = "controlled_stock_http_sampling_span_ancestry_v1"
HTTP_WEBSOCKET_METHOD = "controlled_stock_http_websocket_sampling_span_ancestry_v1"


def admit_controlled_probe(probe, *, binary_sha256, runtime_version=None):
    """Admit a fresh selected-host experiment and return its exact source bytes."""
    import tempfile
    probe_raw = (json.dumps(probe, sort_keys=True, separators=(",", ":")) + "\n").encode()
    from .source_evidence import validate_source
    validate_source("probe", probe_raw, transient=True)
    observed_version = cli_runtime_version(probe["runtime_version"])
    if runtime_version is not None and validate_runtime_version(runtime_version) != observed_version:
        raise ValueError("capability probe runtime identity differs")
    if probe["runtime_binary_sha256"] != binary_sha256:
        raise ValueError("capability probe binary identity differs")
    # Full labels were compared above; only the minimized source is persisted.
    import copy
    probe = copy.deepcopy(probe)
    observed_version = retained_runtime_version(observed_version)
    probe["runtime_version"] = "codex-cli " + observed_version
    if "websocket_probe" in probe:
        probe["websocket_probe"]["runtime_version"] = "codex-cli " + observed_version
    probe_raw = (json.dumps(probe, sort_keys=True, separators=(",", ":")) + "\n").encode()
    probe_hash = "sha256:" + hashlib.sha256(probe_raw).hexdigest()
    dual = "websocket_probe" in probe
    method = HTTP_WEBSOCKET_METHOD if dual else HTTP_METHOD
    supported = {"validation_id", "request_boundaries", "completion_correlation", "input_tokens",
        "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_tokens", "transport"}
    if dual:
        supported.add("request_kind")
    fields = {name: {"status": "supported" if name in supported else "partial" if name == "request_kind" else "unsupported",
        "method": method, "evidence_references": [probe_hash],
        "limitation": None if name in supported else "Not independently established beyond admitted transport request kinds and generation counters." if dual else "Not independently established beyond HTTP generation counters."}
        for name in CAPABILITY_FIELDS}
    doc = {"runtime_version": observed_version, "runtime_binary_sha256": binary_sha256, "fields": fields,
        "probe_reference": "probe.json", "probe_sha256": probe_hash,
        "scope": "controlled HTTP and WebSocket warmup/generation; no provider cache behavior or request trajectory claim" if dual else "controlled HTTP generation only; no provider cache behavior or request trajectory claim"}
    raw = (json.dumps(doc, sort_keys=True, separators=(",", ":")) + "\n").encode()
    identity = "sha256:" + hashlib.sha256(raw).hexdigest()
    with tempfile.TemporaryDirectory(prefix="agmark-capability-admission-") as directory:
        root = Path(directory)
        (root / "probe.json").write_bytes(probe_raw)
        (root / "capabilities.json").write_bytes(raw)
        capabilities = load_capabilities(root / "capabilities.json", binary_sha256=binary_sha256,
            runtime_version=observed_version, evidence_sha256=identity)
    return capabilities, {"capabilities": raw, "probe": probe_raw}


def unavailable_capabilities(reason="controlled_capability_evidence_unavailable"):
    return ValidationCapabilities({k: Capability("unavailable", "capability_gate", (), reason) for k in CAPABILITY_FIELDS})


def load_capabilities(path, *, binary_sha256, runtime_version, evidence_sha256):
    raw = Path(path).read_bytes()
    if "sha256:" + hashlib.sha256(raw).hexdigest() != evidence_sha256:
        raise ValueError("capability evidence integrity differs")
    from .source_evidence import validate_source
    doc = validate_source("capabilities", raw)
    validate_runtime_version(runtime_version)
    runtime_version = retained_runtime_version(runtime_version)
    validate_runtime_version(doc["runtime_version"])
    if doc["runtime_binary_sha256"] != binary_sha256 or doc["runtime_version"] != runtime_version:
        return unavailable_capabilities("capability_runtime_identity_mismatch")
    # Resolve the retained controlled observation, not just its asserted hash.
    probe_path = Path(path).parent / Path(doc["probe_reference"]).name
    probe_raw = probe_path.read_bytes()
    if "sha256:" + hashlib.sha256(probe_raw).hexdigest() != doc["probe_sha256"]:
        raise ValueError("capability probe integrity differs")
    probe = json.loads(probe_raw)
    from .source_evidence import validate_source
    validate_source("probe", probe_raw)
    if probe["runtime_binary_sha256"] != binary_sha256 or probe["runtime_version"] != "codex-cli " + runtime_version or probe["returncode"] != 0:
        raise ValueError("capability probe runtime identity differs")
    if set(doc["fields"]) != set(CAPABILITY_FIELDS):
        raise ValueError("exact capability fields required")
    dual = "websocket_probe" in probe
    method = HTTP_WEBSOCKET_METHOD if dual else HTTP_METHOD
    for name, value in doc["fields"].items():
        if value["evidence_references"] != [doc["probe_sha256"]]:
            raise ValueError("capability assertions require exact controlled probe")
        # This admitted experiment demonstrates HTTP generation and counters;
        # it cannot establish other transports, timing, or cache lifecycle facts.
        supported = {"validation_id", "request_boundaries", "completion_correlation",
                     "input_tokens", "cached_input_tokens", "cache_write_input_tokens",
                     "output_tokens", "reasoning_tokens", "transport"}
        if dual:
            supported.add("request_kind")
        allowed = "supported" if name in supported else "partial" if name == "request_kind" else "unsupported"
        if value["status"] != allowed or value["method"] != method:
            raise ValueError("capability assertion exceeds controlled experiment")
    capabilities = ValidationCapabilities({k: Capability(**{**doc["fields"][k],
        "evidence_references": tuple(doc["fields"][k]["evidence_references"])}) for k in CAPABILITY_FIELDS})
    from .normalization import normalize_spans
    records, reasons = normalize_spans(probe["spans"], validation_id=probe["validation_id"],
        capabilities=capabilities, evidence_reference=doc["probe_sha256"])
    if reasons or len(records) != 2 or len(probe["provider_requests"]) != 2 or probe["rejected_payloads"]:
        raise ValueError("controlled capability probe does not establish request correlation")
    for ordinal, record in enumerate(records, 1):
        expected = {"input_tokens": 100 * ordinal, "cached_input_tokens": 20 * ordinal,
                    "cache_write_input_tokens": 11 * ordinal, "output_tokens": 7 * ordinal,
                    "reasoning_tokens": 3 * ordinal}
        if record.transport != "http" or any(record.fields[key].value != value for key, value in expected.items()):
            raise ValueError("controlled capability counters differ from supplied independent tuple")
    if dual:
        ws = probe["websocket_probe"]
        if (ws["runtime_version"] != probe["runtime_version"] or ws["runtime_binary_sha256"] != binary_sha256 or
                ws["returncode"] != 0 or ws["rejected_payloads"] or ws["validation_id"] == probe["validation_id"] or
                ws["provider_requests"] != [{"ordinal": 1, "kind": "warmup"}, {"ordinal": 2, "kind": "generation"}, {"ordinal": 3, "kind": "generation"}]):
            raise ValueError("controlled WebSocket probe authority differs")
        records, reasons = normalize_spans(ws["spans"], validation_id=ws["validation_id"], capabilities=capabilities, evidence_reference=doc["probe_sha256"])
        if reasons or len(records) != 3 or [r.request_kind for r in records] != ["warmup", "generation", "generation"]:
            raise ValueError("controlled WebSocket boundary/kind correlation unavailable")
        if any(r.transport != "websocket" for r in records) or any(records[0].fields[k].value is not None for k in ("input_tokens", "cache_write_input_tokens", "request_duration_ms")):
            raise ValueError("controlled WebSocket warmup availability differs")
        for ordinal, record in enumerate(records[1:], 2):
            for field, scale in (("input_tokens", 100), ("cached_input_tokens", 20), ("cache_write_input_tokens", 11), ("output_tokens", 7), ("reasoning_tokens", 3)):
                if record.fields[field].value != scale * ordinal:
                    raise ValueError("controlled WebSocket counters differ from independent provider tuple")
    return capabilities
