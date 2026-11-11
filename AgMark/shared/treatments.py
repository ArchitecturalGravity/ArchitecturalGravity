"""Frozen treatment content identity, separate from scoring and certification."""
from base64 import b64decode, b64encode
from collections.abc import Mapping
from hashlib import sha256
import re
from pathlib import PurePosixPath, PureWindowsPath

POLICY = "arcgrav.benchmark:treatment-content-policy"
CONTENT = "arcgrav.runtime:treatment-content"
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")


def digest(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def freeze(treatment_id: str, expected: Mapping, data: bytes) -> dict:
    """Keep both registration expectations and exact supplied invocation bytes."""
    return {
        "treatment_id": treatment_id,
        "expected": dict(expected),
        "actual_sha256": digest(data),
        "actual_byte_length": len(data),
        "content_base64": b64encode(data).decode("ascii"),
    }


def content_entries(document: Mapping) -> list:
    """Validate retained content before either execution or certification checks."""
    entries = document.get("extensions", {}).get(CONTENT, [])
    if not isinstance(entries, list):
        raise ValueError("invalid retained treatment content")
    seen = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or set(entry) != {
            "treatment_id", "expected", "actual_sha256", "actual_byte_length", "content_base64"
        }:
            raise ValueError("invalid retained treatment identity")
        identity = entry["treatment_id"]
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError("invalid or duplicate retained treatment identity")
        seen.add(identity)
        expected = entry["expected"]
        if (not isinstance(expected, Mapping)
                or not isinstance(expected.get("reference"), str)
                or not expected["reference"]
                or not isinstance(expected.get("sha256"), str)
                or not _SHA256.fullmatch(expected["sha256"])
                or type(expected.get("byte_length")) is not int
                or expected["byte_length"] < 0):
            raise ValueError("invalid expected treatment content identity")
        if set(expected) - {"reference", "sha256", "byte_length", "media_type"}:
            raise ValueError("unrelated expected treatment metadata")
        ref = expected["reference"]
        if (PurePosixPath(ref).is_absolute() or PureWindowsPath(ref).drive or "\\" in ref
                or ".." in PurePosixPath(ref).parts or ref != PurePosixPath(ref).as_posix() or "://" in ref):
            raise ValueError("treatment references must be relative resources")
        if "media_type" in expected and (not isinstance(expected["media_type"], str) or re.fullmatch(r"(?:text/(?:plain|markdown)|application/(?:json|xml|yaml))(?:; charset=utf-8)?", expected["media_type"]) is None):
            raise ValueError("unsupported treatment media type")
        if not isinstance(entry["content_base64"], str):
            raise ValueError("invalid retained treatment bytes")
        data = b64decode(entry["content_base64"], validate=True)
        if (digest(data) != entry["actual_sha256"]
                or type(entry["actual_byte_length"]) is not int
                or len(data) != entry["actual_byte_length"]):
            raise ValueError("retained treatment bytes changed")
    return entries


def contaminated(document: Mapping) -> bool:
    """Derive status from identities; there is no independently clearable flag."""
    return any(e["expected"]["sha256"] != e["actual_sha256"]
               or e["expected"]["byte_length"] != e["actual_byte_length"]
               for e in content_entries(document))


def require_certifiable(document: Mapping) -> None:
    if contaminated(document):
        raise ValueError("Treatments Contaminated: verification and reports are unavailable")
