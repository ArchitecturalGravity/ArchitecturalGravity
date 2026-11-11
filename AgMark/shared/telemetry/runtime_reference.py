"""Retained capture versions and non-blocking planning advisories.

A reference runtime identifies an implementation update's basis. It is neither
a release allowlist nor evidence that the selected runtime exports a capability.
Retained versions contain numeric cores only. A match compares cores, not exact
prerelease/build strings or binaries; those suffixes cannot be reconstructed.
Update the runner's capture-capability-update declaration alongside capture
implementation changes, using the actual reference version. Do
not replace that reference with a user's installed runtime during plan building.
"""
from collections.abc import Mapping
import re


UPDATE_EXTENSION = "agmark.telemetry:capture-capability-update"
PLAN_EXTENSION = "agmark.telemetry:capture-runtime-advisory"
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?")
_ADVISORY_FIELDS = {"schema_version", "runner_id", "update_revision", "reference_runtime_version",
    "selected_runtime_version", "status", "blocking"}

# Release source plus real-binary controlled capture, documented in
# software_testing/adapters/codex_cli/CAPTURE_AUDIT_0_167_0.md. These facts
# describe a schema, not an allowlist for execution or a delivery guarantee.
_CAPTURE_AUDITS = {
    "0.167.0": {"source_commit": "086ccc833bc9cf01024ad2dd6af7dbd421b6bf9a",
                "token_usage_record_v1": True},
}


def capture_schema_audit(runtime_version):
    """Return demonstrated stock schema facts for an exact release label.

    Prerelease/build variants do not inherit a stock release's source audit.
    Persist capability markers with new captures so older evidence keeps its
    original interpretation when this table grows.
    """
    if not isinstance(runtime_version, str):
        return {}
    return dict(_CAPTURE_AUDITS.get(runtime_version.removeprefix("codex-cli "), {}))


def _version(value):
    if not isinstance(value, str):
        return None
    value = value.removeprefix("codex-cli ")
    if len(value) > 128 or not _VERSION.fullmatch(value):
        return None
    # Build/prerelease suffixes can contain host or customer labels. Retain
    # only the numeric core; executable digests carry exact binary identity.
    return re.split(r"[-+]", value, maxsplit=1)[0]


def _label(value):
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", value):
        return value
    return None


def _comparison(reference, selected):
    return "unknown" if reference is None or selected is None else (
        "match" if reference == selected else "mismatch")


def validate_runtime_advisory(value):
    """Admit only current, bounded runtime advisory metadata for persistence."""
    if (not isinstance(value, Mapping) or set(value) != _ADVISORY_FIELDS
            or value.get("schema_version") != "1.0.0" or value.get("blocking") is not False
            or _label(value.get("runner_id")) != value.get("runner_id") or value.get("runner_id") is None):
        raise ValueError("unsupported retained runtime advisory")
    if value.get("update_revision") is not None and _label(value["update_revision"]) != value["update_revision"]:
        raise ValueError("invalid retained runtime advisory revision")
    for key in ("reference_runtime_version", "selected_runtime_version"):
        if value[key] is not None and _version(value[key]) != value[key]:
            raise ValueError("invalid retained runtime version")
    if value["status"] != _comparison(value["reference_runtime_version"], value["selected_runtime_version"]):
        raise ValueError("runtime advisory status differs from retained versions")


def read_runtime_advisory(value):
    """Read optional retained metadata safely; malformed claims become unknown.

    This does not create execution authority or certify capture compatibility.
    The recorded classification must agree with the recorded versions.
    """
    value = value if isinstance(value, Mapping) else {}
    reference = _version(value.get("reference_runtime_version"))
    selected = _version(value.get("selected_runtime_version"))
    status = _comparison(reference, selected)
    if (set(value) != _ADVISORY_FIELDS or value.get("schema_version") != "1.0.0"
            or value.get("blocking") is not False or value.get("status") != status):
        status = "unknown"
    return {
        "reference_runtime_version": reference,
        "selected_runtime_version": selected,
        "status": status,
    }


def build_runtime_advisory(registration, provider_runtime):
    """Freeze reference versus selected-host identity without gating a plan.

The caller supplies the discovered, validated registration. Adapters without
this declaration do not acquire a Codex-specific warning. Missing metadata is
explicitly unknown, never an inferred mismatch or a substitute capability.
"""
    extensions = registration.get("extensions", {})
    if not isinstance(extensions, Mapping) or UPDATE_EXTENSION not in extensions:
        return None
    update = extensions[UPDATE_EXTENSION]
    update = update if isinstance(update, Mapping) else {}
    reference = _version(update.get("reference_runtime_version"))
    selected = _version(provider_runtime.get("runtime_version"))
    status = _comparison(reference, selected)
    return {
        "schema_version": "1.0.0",
        "runner_id": registration["registration_id"],
        "update_revision": _label(update.get("revision")),
        "reference_runtime_version": reference,
        "selected_runtime_version": selected,
        "status": status,
        "blocking": False,
    }
