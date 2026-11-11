"""Versioned, ZIP-compatible run archives with fail-closed content validation.

SHA-256 seals detect accidental or unsophisticated modification. They are
SELF-ASSERTED: authenticity requires an independently trusted GitHub/other
attestation of the complete archive SHA-256. No signing key is shipped here.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from datetime import datetime, timezone
from hashlib import sha256
import errno
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from threading import get_ident
from typing import Mapping
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

FORMAT = "agmark.run-archive/4"
COMPLETION_MEMBER = "completion/release.json"
COMPLETION_SCHEMA_ID = "arcgrav.shared.run-completion"
COMPLETION_SCHEMA_VERSION = "2.0.0"
_GENERATION = re.compile(r"generation-[A-Za-z0-9_-]+\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_MANIFEST = 16 * 1024 * 1024
_MAX_MEMBERS = 50_000
_MAX_FILE = 2 * 1024**3
_MAX_TOTAL = 16 * 1024**3
_CHUNK = 1024 * 1024


class ArchiveError(ValueError):
    """Untrusted archive or unsafe publication boundary."""


class ArchiveCleanupWarning(Exception):
    """Publication succeeded; optional source or lock retirement did not.

    Consumers must retain the published result. Issues contain only stable
    operation labels and known exception categories, never exception text.
    """

    def __init__(self, archive_path: Path, issues: tuple[str, ...]):
        self.archive_path = archive_path
        self.issues = issues
        super().__init__("archive published; cleanup incomplete: " + ", ".join(issues))


@dataclass
class _PublicationOutcome:
    archive_path: Path | None = None
    issues: list[str] = field(default_factory=list)


def _cleanup_issue(operation: str, error: Exception) -> str:
    category = next((kind.__name__ for kind in
                     (PermissionError, FileNotFoundError, OSError, ArchiveError)
                     if isinstance(error, kind)), "Exception")
    return operation + ":" + category


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ArchiveError("duplicate JSON member: " + key)
        result[key] = value
    return result


def _json(data: bytes):
    return json.loads(data.decode("utf-8"), object_pairs_hook=_unique,
                      parse_constant=lambda x: (_ for _ in ()).throw(ArchiveError("nonfinite JSON constant")))


def _generation(value: str) -> str:
    if not isinstance(value, str) or _GENERATION.fullmatch(value) is None:
        raise ArchiveError("invalid archive generation ID")
    return value


def _member(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise ArchiveError("unsafe ZIP member name")
    path = PurePosixPath(name)
    if (path.is_absolute() or name != path.as_posix()
            or any(part in {"", ".", ".."} for part in name.split("/"))):
        raise ArchiveError("ZIP traversal or noncanonical member name")
    if name.startswith(("revisions/", "history/", "reports/", "verification/")):
        return name
    if name in {"manifest.json", COMPLETION_MEMBER} or name.startswith((".agmark-validation/", ".agmark-progress/")):
        return name
    if name.startswith("generation-") or (name.startswith(".generation-") and name.endswith(".terminal")):
        return name
    raise ArchiveError("unknown archive member namespace: " + name)


def _core_member(name: str, generation_id: str) -> bool:
    return (name.startswith(generation_id + "/")
            or name.startswith(".agmark-validation/" + generation_id + "/")
            or name == ".agmark-progress/" + generation_id + ".json"
            or name == "." + generation_id + ".terminal")


def _safe_archive_path(path: Path) -> None:
    if path.suffix != ".agmark" or _GENERATION.fullmatch(path.stem) is None:
        raise ArchiveError("expected generation-<id>.agmark")
    if path.is_symlink() or not path.is_file():
        raise ArchiveError("run archive unavailable or symlinked")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ArchiveError("run archive must be a regular file")


def archive_path(root: Path, generation_id: str) -> Path:
    return Path(root) / (_generation(generation_id) + ".agmark")


def _hash_stream(stream) -> str:
    state = sha256()
    for block in iter(lambda: stream.read(_CHUNK), b""):
        state.update(block)
    return "sha256:" + state.hexdigest()


def validate_archive(path: str | Path, *, _expected_generation_id: str | None = None) -> dict:
    """Fully validate ZIP structure, inventory, lifecycle marker and hash chain.

    No extraction, code execution, import authority, or filesystem mutation.
    The returned manifest is *not* proof of authentic execution.
    """
    source = Path(path)
    if _expected_generation_id is None:
        _safe_archive_path(source)
    else:
        _generation(_expected_generation_id)
        if source.is_symlink() or not source.is_file():
            raise ArchiveError("unavailable candidate ZIP archive")
    try:
        with ZipFile(source, "r", allowZip64=True) as bundle:
            return _validate_archive_bundle(bundle, _expected_generation_id or source.stem)
    except (BadZipFile, OSError, EOFError, RuntimeError, OverflowError, UnicodeError,
            json.JSONDecodeError, TypeError, KeyError, RecursionError) as exc:
        raise ArchiveError("archive cannot be safely validated: " + str(exc)) from exc


def _valid_publication_timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?(?:Z|[+-][0-9]{2}:[0-9]{2})", value):
        return False
    try:
        datetime.fromisoformat(value)
        return True
    except ValueError:
        return False


def _validate_archive_bundle(bundle: ZipFile, gid: str) -> dict:
    """Validate exact bytes from one already opened ZIP; never trust a pathname."""
    infos = bundle.infolist()
    if not 2 <= len(infos) <= _MAX_MEMBERS:
        raise ArchiveError("archive member count outside limits")
    found = {}
    total = 0
    for info in infos:
        name = _member(info.filename)
        if name in found or info.is_dir():
            raise ArchiveError("duplicate or directory ZIP member: " + name)
        if (info.flag_bits & 1 or info.file_size > _MAX_FILE
                or info.file_size < 0 or info.compress_size < 0
                or (info.file_size > 128 * 1024 * 1024 and info.file_size >
                    10_000 * max(1, info.compress_size))):
            raise ArchiveError("encrypted, oversized or suspicious ZIP member: " + name)
        if ((info.external_attr >> 16) & 0o170000) == stat.S_IFLNK:
            raise ArchiveError("ZIP symlinks are forbidden")
        found[name] = info
        total += info.file_size
        if total > _MAX_TOTAL:
            raise ArchiveError("uncompressed archive exceeds limit")
    if "manifest.json" not in found or found["manifest.json"].file_size > _MAX_MANIFEST:
        raise ArchiveError("missing or oversized archive manifest")
    raw = bundle.read("manifest.json")
    manifest = _json(raw)
    if not isinstance(manifest, dict) or canonical_bytes(manifest) != raw:
        raise ArchiveError("noncanonical archive manifest")
    expected_manifest_fields = {"format", "generation_id", "terminal_status", "revision",
        "previous_manifest_sha256", "sealed_at", "core_files", "core_sha256", "files"}
    if set(manifest) != expected_manifest_fields:
        raise ArchiveError("unsupported archive manifest fields")
    if manifest.get("format") != FORMAT or manifest.get("generation_id") != gid:
        raise ArchiveError("archive format or generation identity mismatch")
    if not _valid_publication_timestamp(manifest.get("sealed_at")):
        raise ArchiveError("invalid archive publication timestamp")
    if manifest.get("terminal_status") not in ("accepted", "blocked", "executed"):
        raise ArchiveError("invalid archive terminal status")
    revision = manifest.get("revision")
    if type(revision) is not int or not 1 <= revision <= 100_000:
        raise ArchiveError("invalid archive revision")
    files = manifest.get("files")
    core = manifest.get("core_files")
    if not isinstance(files, dict) or not isinstance(core, dict) or not core:
        raise ArchiveError("missing archive file inventory")
    if set(files) != set(found) - {"manifest.json"}:
        raise ArchiveError("unlisted, extra or missing ZIP members")
    if not set(core).issubset(files):
        raise ArchiveError("core inventory is missing retained evidence")
    if any(files[name] != expected for name, expected in core.items()):
        raise ArchiveError("original core evidence hash differs from archive inventory")
    if any(name != COMPLETION_MEMBER and not _core_member(name, gid) and not name.startswith(
            ("revisions/", "history/", "reports/", "verification/"))
            for name in files):
        raise ArchiveError("foreign-generation or unexpected evidence namespace")
    if set(core) != {p for p in files if _core_member(p, gid)}:
        raise ArchiveError("core inventory differs from retained run evidence")
    if "." + gid + ".terminal" not in core or not any(
        p.startswith(gid + "/") for p in core
    ):
        raise ArchiveError("terminal marker or original run evidence is missing")
    if manifest.get("core_sha256") != digest(canonical_bytes(core)):
        raise ArchiveError("original run core seal differs")
    for name, expected in files.items():
        if (_member(name) != name or not isinstance(expected, str)
                or not _DIGEST.fullmatch(expected)):
            raise ArchiveError("unsafe or invalid inventory digest")
        with bundle.open(name, "r") as item:
            actual = _hash_stream(item)
        if actual != expected:
            raise ArchiveError("evidence digest mismatch: " + name)
    if bundle.read("." + gid + ".terminal") != manifest["terminal_status"].encode("ascii"):
        raise ArchiveError("terminal status marker mismatch")
    previous = manifest.get("previous_manifest_sha256")
    if revision == 1:
        if previous is not None:
            raise ArchiveError("initial revision cannot reference prior manifests")
        if any(name.startswith(("revisions/", "history/", "verification/")) for name in files):
            raise ArchiveError("initial revision cannot contain later artifacts")
    else:
        for number in range(1, revision):
            name = "revisions/%06d.json" % number
            if name not in files:
                raise ArchiveError("missing sealed revision history: " + name)
            raw_prev = bundle.read(name)
            old = _json(raw_prev)
            if (not isinstance(old, dict) or canonical_bytes(old) != raw_prev
                    or set(old) != expected_manifest_fields
                    or old.get("format") != FORMAT
                    or not _valid_publication_timestamp(old.get("sealed_at"))
                    or old.get("revision") != number
                    or old.get("generation_id") != gid
                    or old.get("core_sha256") != manifest["core_sha256"]
                    or old.get("core_files") != core):
                raise ArchiveError("invalid previous revision manifest")
            original_inventory = old.get("files")
            if not isinstance(original_inventory, dict):
                raise ArchiveError("invalid previous inventory")
            if any(files.get(reference) != checksum
                   for reference, checksum in original_inventory.items()
                   if reference != "history/presentation.json"):
                raise ArchiveError("previously sealed artifact was modified or removed")
            if number == revision - 1 and previous != digest(raw_prev):
                raise ArchiveError("revision linkage mismatch")
            if number > 1 and old.get("previous_manifest_sha256") != digest(
                bundle.read("revisions/%06d.json" % (number - 1))
            ):
                raise ArchiveError("revision chain mismatch")
    observations = _validate_core_evidence(bundle, core)
    _validate_replay_companion(bundle, core, gid, observations)
    _validate_completion(bundle, manifest)
    return manifest


def _validate_core_evidence(bundle: ZipFile, core: dict) -> dict:
    """Apply shipped structural policies to recognized retained observations.

    Benchmark input/output bytes remain opaque scoring authority. This is not
    a generic content scanner, nor does import execute producer or scorer code.
    """
    observations = {}
    structural_schemas = {"arcgrav.shared.schema.golden-observation",
        "arcgrav.shared.schema.treatment-observation", "arcgrav.shared.schema.execution-boundary",
        "arcgrav.shared.schema.run-plan"}
    for name in core:
        required = name.endswith(("/observation.json", "/execution-boundary.json",
                                  "/accepted-plan/plan.json", "/run-plan.json"))
        # Scoring byte channels are deliberately opaque. Other JSON documents
        # cannot evade admission merely by renaming their conventional file.
        if not required and name.endswith(("/stdout.bin", "/input.bin", "/response.bin")):
            continue
        with bundle.open(name) as source:
            prefix = source.read(1024)
            if not required and not prefix.lstrip().startswith(b"{"):
                continue
            raw = prefix + source.read()
        try:
            document = _json(raw)
        except (ValueError, UnicodeError) as exc:
            if required:
                raise ArchiveError("invalid retained structural evidence") from exc
            continue
        if not isinstance(document, dict):
            if required:
                raise ArchiveError("invalid retained structural evidence")
            continue
        if not required and document.get("schema_id") not in structural_schemas:
            continue
        if name.endswith(("/accepted-plan/plan.json", "/run-plan.json")) or document.get("schema_id") == "arcgrav.shared.schema.run-plan":
            from ..orchestration.planning import RunPlan
            try:
                RunPlan.from_document(document)
            except (ValueError, TypeError, KeyError) as exc:
                raise ArchiveError("unsupported retained run plan") from exc
            continue
        if name.endswith("/execution-boundary.json") or document.get("schema_id") == "arcgrav.shared.schema.execution-boundary":
            from ..identity.boundary import ExecutionBoundary
            try:
                ExecutionBoundary.from_document(document)
            except (ValueError, TypeError, KeyError) as exc:
                raise ArchiveError("unsupported retained execution boundary") from exc
            continue
        schema_id = document.get("schema_id")
        filenames = {"arcgrav.shared.schema.golden-observation": "golden_observation.schema.json",
                     "arcgrav.shared.schema.treatment-observation": "treatment_observation.schema.json"}
        if schema_id not in filenames:
            raise ArchiveError("unsupported retained observation schema")
        from ...validation.structure import validate_cataloged_document
        entry, schema = _report_schema_authority(schema_id, "2.0.0" if schema_id.endswith("golden-observation") else "1.0.0", filenames[schema_id])
        if validate_cataloged_document(document, schema_document=schema, entry=entry, source_id=name):
            raise ArchiveError("invalid retained observation structure")
        if schema_id == "arcgrav.shared.schema.golden-observation":
            from ..golden.execution import validate_golden_evidence
            try:
                validate_golden_evidence(document)
            except (ValueError, TypeError, KeyError) as exc:
                raise ArchiveError("unsupported retained golden evidence") from exc
            continue
        try:
            from ...adapters.execution.emission import validate_retained_parity_observation
            validate_retained_parity_observation(document)
            extensions = document["extensions"]
            if "agmark.telemetry:capture" in extensions:
                from ...telemetry.evidence import validate_manifest
                validate_manifest(extensions["agmark.telemetry:capture"])
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ArchiveError("unsupported retained observation evidence") from exc
        identity = document["observation_id"]
        if identity in observations:
            raise ArchiveError("duplicate retained observation identity")
        observations[identity] = (document, digest(raw))
    return observations


def _validate_replay_companion(bundle: ZipFile, core: dict, gid: str, observations: dict) -> None:
    """Admit current minimized companion documents without executing a replay."""
    prefix = ".agmark-validation/" + gid + "/"
    members = {name for name in core if name.startswith(prefix)}
    if not members:
        return
    try:
        manifest_name = prefix + "manifest.json"
        raw = bundle.read(manifest_name)
        if bundle.read(prefix + "manifest.sha256").decode("ascii") != digest(raw):
            raise ValueError("companion digest mismatch")
        manifest = _json(raw)
        fields = {"generation_id", "accepted_snapshot_id", "run_plan_sha256",
            "execution_boundary_fingerprint", "scored_evidence", "validations", "captures",
            "sources", "scope", "included_in_score"}
        if (not isinstance(manifest, dict) or set(manifest) not in (fields, fields | {"failure_code"})
                or manifest["generation_id"] != gid or manifest["scope"] != "configuration_equivalent_replay"
                or manifest["included_in_score"] is not False):
            raise ValueError("unsupported companion structure")
        if (not isinstance(manifest["accepted_snapshot_id"], str)
                or not re.fullmatch(r"accepted-snapshot:[0-9a-f]{64}", manifest["accepted_snapshot_id"])
                or any(not isinstance(manifest[key], str) or not _DIGEST.fullmatch(manifest[key])
                       for key in ("run_plan_sha256", "execution_boundary_fingerprint"))):
            raise ValueError("invalid companion identity fields")
        scored = manifest["scored_evidence"]
        if (not isinstance(scored, dict) or any(not isinstance(key, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,1023}", key)
                or not isinstance(value, str) or not _DIGEST.fullmatch(value) or value not in core.values()
                for key, value in scored.items())):
            raise ValueError("invalid companion scored inventory")
        plan_name = gid + "/accepted-plan/plan.json"
        if plan_name in core:
            plan = _json(bundle.read(plan_name))
            from ..identity.canonical import canonical_sha256
            snapshot_hash = canonical_sha256({"kind": "accepted-run-snapshot",
                "run_plan_id": plan["run_plan_id"], "plan_sha256": plan["plan_sha256"],
                "execution_boundary_sha256": plan["execution_boundary"]["sha256"],
                "execution_boundary_fingerprint": plan["execution_boundary_fingerprint"],
                "benchmark": plan["benchmark"], "case_set": plan["case_set"], "treatment_set": plan["treatment_set"]})
            if (manifest["run_plan_sha256"] != plan["plan_sha256"]
                    or manifest["execution_boundary_fingerprint"] != plan["execution_boundary_fingerprint"]
                    or manifest["accepted_snapshot_id"] != "accepted-snapshot:" + snapshot_hash.removeprefix("sha256:")):
                raise ValueError("companion accepted plan binding mismatch")
        expected = {manifest_name, prefix + "manifest.sha256"}
        treatments = set()
        sources, captures, used_sources, used_captures = {}, {}, set(), set()
        from ...validation.codex_cache.source_evidence import validate_source, verify_managed_sources
        from ...validation.codex_cache.collector import canonical_capture_spans
        from ...validation.codex_cache.serialization import admit_validation
        for category in ("sources", "captures", "validations"):
            entries = manifest[category]
            if not isinstance(entries, list):
                raise ValueError("invalid companion inventory")
            for entry in entries:
                keys = {"reference", "sha256"} | ({"kind"} if category == "sources" else
                       {"treatment_id"} if category == "validations" else set())
                pattern = (r"source-[0-9a-f]{64}\.json" if category == "sources" else
                           r"capture-[0-9a-f]{64}\.json" if category == "captures" else r"treatment-[0-9]+\.json")
                if not isinstance(entry, dict) or set(entry) != keys or not re.fullmatch(pattern, entry["reference"]):
                    raise ValueError("invalid companion reference")
                name = prefix + entry["reference"]
                if name in expected or name not in members:
                    raise ValueError("duplicate or missing companion reference")
                expected.add(name)
                data = bundle.read(name)
                if digest(data) != entry["sha256"]:
                    raise ValueError("companion source digest mismatch")
                if category == "sources":
                    validate_source(entry["kind"], data)
                    sources[entry["sha256"]] = (entry["kind"], data)
                elif category == "captures":
                    spans = _json(data)
                    if not isinstance(spans, list) or canonical_capture_spans(spans) != spans:
                        raise ValueError("non-minimized capture evidence")
                    captures[entry["sha256"]] = spans
                else:
                    summary = admit_validation(_json(data))
                    if summary.treatment_id in treatments:
                        raise ValueError("duplicate companion treatment")
                    treatments.add(summary.treatment_id)
                    if summary.generation_id != gid or summary.treatment_id != entry["treatment_id"]:
                        raise ValueError("companion identity mismatch")
                    expected_ids = {identity for identity, (item, _) in observations.items()
                                    if item["treatment_id"] == summary.treatment_id}
                    if set(summary.scored_observation_ids) != expected_ids:
                        raise ValueError("companion scored observation identities differ")
                    for replay in summary.replays:
                        observation, checksum = observations[replay.validates_observation_id]
                        if (observation["treatment_id"] != summary.treatment_id
                                or str(observation["repetition"]) != replay.repetition_id
                                or checksum not in manifest["scored_evidence"].values()):
                            raise ValueError("companion observation binding mismatch")
                        allowed = {"arcgrav.telemetry:stock-transport-diagnostics-v2",
                            "arcgrav.telemetry:startup-evidence", "arcgrav.telemetry:probe-evidence",
                            "arcgrav.telemetry:capabilities-evidence"}
                        if set(replay.extensions) - allowed:
                            raise ValueError("unknown replay evidence extension")
                        for key, field in replay.extensions.items():
                            if key.endswith("-evidence") and field.availability == "available":
                                used_sources.add(field.value)
                            elif key == "arcgrav.telemetry:stock-transport-diagnostics-v2":
                                used_captures.update(field.evidence_references)
                        expected_refs = {checksum} | {field.value for key, field in replay.extensions.items()
                            if key.endswith("-evidence") and field.availability == "available"}
                        if set(replay.evidence_references) != expected_refs or len(replay.evidence_references) != len(expected_refs):
                            raise ValueError("unrelated replay references")
                        verify_managed_sources(replay, observation, sources)
                        from ...validation.codex_cache.diagnostics import EXTENSION, PROFILE, diagnostic_field
                        diagnostic = replay.extensions.get(EXTENSION)
                        if diagnostic is not None:
                            if len(diagnostic.evidence_references) != 1:
                                raise ValueError("ambiguous diagnostic capture")
                            reference = diagnostic.evidence_references[0]
                            calculated = diagnostic_field(captures[reference], validation_id=replay.validation_id,
                                                          evidence_reference=reference)
                            if calculated.to_dict() != diagnostic.to_dict():
                                raise ValueError("diagnostic capture mismatch")
                        for request in replay.requests:
                            used_captures.update(request.evidence_references)
                        if replay.requests:
                            refs = {ref for request in replay.requests for ref in request.evidence_references}
                            if len(refs) != 1:
                                raise ValueError("ambiguous replay capture")
                            reference = next(iter(refs))
                            from ...validation.codex_cache.normalization import normalize_spans
                            reconstructed, _ = normalize_spans(captures[reference], validation_id=replay.validation_id,
                                capabilities=replay.capabilities, evidence_reference=reference, profile=PROFILE)
                            if tuple(item.to_dict() for item in reconstructed) != tuple(item.to_dict() for item in replay.requests):
                                raise ValueError("replay request capture mismatch")
        if members != expected or set(sources) != used_sources or set(captures) != used_captures:
            raise ValueError("unlisted or unused companion evidence")
        if "failure_code" in manifest:
            from ..completion_diagnostics import ERROR_CLASSES
            if (manifest["failure_code"] not in {"post_treatment_validation_failed:" + kind for kind in ERROR_CLASSES}
                    or any(manifest[key] for key in ("sources", "captures", "validations"))):
                raise ValueError("unsafe companion failure diagnostic")
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError) as exc:
        raise ArchiveError("unsupported retained replay companion") from exc


@lru_cache(maxsize=2)
def _report_schema_authority(schema_id: str, version: str, filename: str):
    # Resolve only shipped structural contracts. Import never loads producer
    # reporting code, benchmark policy, a scorer, or an archive-supplied schema.
    from ...validation.catalog import resolve_catalog_entry
    from ...validation.core import SchemaIdentity
    root = Path(__file__).resolve().parents[2] / "schemas"
    catalog = _json((root / "catalog.json").read_bytes())
    catalog_schema = _json((root / "schema_catalog.schema.json").read_bytes())
    entry, issues = resolve_catalog_entry(catalog, expected=SchemaIdentity(schema_id, version),
                                         catalog_schema_document=catalog_schema)
    if issues or entry is None or entry.file != "AgMark/shared/schemas/" + filename:
        raise ArchiveError("retained report structural contract is unavailable")
    return entry, _json((root / filename).read_bytes())


def _validate_report_structure(document: dict, schema_id: str, version: str,
                               filename: str) -> None:
    from ...validation.structure import validate_cataloged_document
    entry, schema = _report_schema_authority(schema_id, version, filename)
    issues = validate_cataloged_document(document, schema_document=schema,
                                         entry=entry, source_id="retained-" + filename)
    if issues:
        raise ArchiveError("invalid retained report structure: " + issues[0].code
                           + " " + (issues[0].json_pointer or ""))


def _validate_completion(bundle: ZipFile, manifest: dict) -> dict:
    """Validate the sealed release contract without invoking producer policy."""
    files = manifest["files"]
    if COMPLETION_MEMBER not in files:
        raise ArchiveError("required completion record is missing; unsupported archive format")
    if bundle.getinfo(COMPLETION_MEMBER).file_size > _MAX_MANIFEST:
        raise ArchiveError("oversized completion record")
    raw = bundle.read(COMPLETION_MEMBER)
    record = _json(raw)
    if not isinstance(record, dict) or canonical_bytes(record) != raw:
        raise ArchiveError("noncanonical completion record")
    if (record.get("schema_id") != COMPLETION_SCHEMA_ID
            or record.get("schema_version") != COMPLETION_SCHEMA_VERSION):
        raise ArchiveError("unsupported completion record version")
    if (record.get("generation_id") != manifest["generation_id"]
            or record.get("core_sha256") != manifest["core_sha256"]):
        raise ArchiveError("completion record evidence identity mismatch")
    expected_fields = {"schema_id", "schema_version", "generation_id", "core_sha256",
                       "status", "completed_at", "validation", "report"}
    if set(record) not in (expected_fields, expected_fields | {"diagnostics"}):
        raise ArchiveError("unsupported completion record fields")
    if "diagnostics" in record:
        from ..completion_diagnostics import valid_completion_diagnostic
        rows = record["diagnostics"]
        if (not isinstance(rows, list) or len(rows) > 64
                or not all(valid_completion_diagnostic(row) for row in rows)):
            raise ArchiveError("invalid completion diagnostics")
    status = record.get("status")
    expected_validation = {"complete": "passed", "validation_failed": "failed",
                           "report_failed": "passed", "not_applicable": "not_applicable"}
    validation = record.get("validation")
    if (status not in expected_validation or not isinstance(validation, dict)
            or set(validation) != {"status", "diagnostic"}
            or validation.get("status") not in ({"passed", "failed", "not_applicable"}
                if status == "report_failed" else {expected_validation[status]})
            or not isinstance(record.get("completed_at"), str)
            or not record["completed_at"]):
        raise ArchiveError("invalid completion state")
    try:
        completed_at = datetime.fromisoformat(record["completed_at"])
    except ValueError as exc:
        raise ArchiveError("invalid completion timestamp") from exc
    from ..completion_diagnostics import ERROR_CLASSES
    diagnostic = validation.get("diagnostic")
    allowed_diagnostics = {prefix + ":" + category
        for prefix in ("post_treatment_validation_failed", "automatic_validation_failed", "automatic_report_failed")
        for category in ERROR_CLASSES}
    if completed_at.tzinfo is None or (diagnostic is not None and (
            not isinstance(diagnostic, str) or diagnostic not in allowed_diagnostics)):
        raise ArchiveError("invalid completion timestamp or diagnostic")
    report = record.get("report")
    report_names = {name for name in files if name.startswith("reports/")}
    if status != "complete":
        if report is not None or report_names:
            raise ArchiveError("unsuccessful completion cannot publish a final report")
        return record
    if manifest["terminal_status"] != "accepted":
        raise ArchiveError("only an accepted generation can publish a completed report")
    if not isinstance(report, dict) or not isinstance(report.get("report_id"), str) or not report["report_id"]:
        raise ArchiveError("completed release lacks report identity")
    components = report.get("components")
    if not isinstance(components, list) or len(components) != 4:
        raise ArchiveError("completed report requires all four components")
    roles, names, identities = set(), set(), set()
    documents = {}
    descriptors = {}
    for component in components:
        if not isinstance(component, dict):
            raise ArchiveError("invalid completed report component descriptor")
        role, name = component.get("role"), component.get("reference")
        identity = component.get("artifact_id")
        if (not isinstance(role, str) or role in roles
                or not isinstance(name, str) or name in names
                or not name.startswith("reports/" + manifest["generation_id"] + "/")
                or not isinstance(identity, str) or not identity or identity in identities
                or name not in files or component.get("sha256") != files[name]):
            raise ArchiveError("completed report component identity mismatch")
        roles.add(role)
        descriptors[role] = component
        names.add(name)
        identities.add(identity)
        if role == "markdown":
            bundle.read(name).decode("utf-8")
        else:
            # Telemetry-bearing reports are evidence, not bounded metadata.
            # Every member already passed _MAX_FILE and _MAX_TOTAL above;
            # only the report manifest shares the smaller metadata limit.
            if role == "manifest" and bundle.getinfo(name).file_size > _MAX_MANIFEST:
                raise ArchiveError("oversized report JSON component")
            document = _json(bundle.read(name))
            documents[role] = document
            if not isinstance(document, dict) or document.get("accepted_generation_id") != manifest["generation_id"]:
                raise ArchiveError("report component generation mismatch")
            if role in {"machine_json", "canonical_evidence_json"} and document.get("report_id") != report["report_id"]:
                raise ArchiveError("report component report identity mismatch")
    if roles != {"markdown", "machine_json", "canonical_evidence_json", "manifest"} or names != report_names:
        raise ArchiveError("missing or unbound completed report components")
    report_manifest = documents["manifest"]
    machine_document = documents["machine_json"]
    if (machine_document.get("schema_id") != "arcgrav.shared.schema.report"
            or machine_document.get("schema_version") != "3.0.0"
            or report_manifest.get("schema_id") != "arcgrav.shared.schema.report-manifest"
            or report_manifest.get("schema_version") != "1.0.0"):
        raise ArchiveError("unsupported retained report or report manifest schema version")
    _validate_report_structure(machine_document, "arcgrav.shared.schema.report", "3.0.0",
                               "report.schema.json")
    _validate_report_structure(report_manifest, "arcgrav.shared.schema.report-manifest", "1.0.0",
                               "report_manifest.schema.json")
    if machine_document["status"] not in {"complete", "complete_with_deviations", "dry_run"}:
        raise ArchiveError("completed release cannot contain an incomplete or invalid report")
    manifest_identity = descriptors["manifest"]["artifact_id"]
    if (machine_document.get("report_manifest_id") != manifest_identity
            or report_manifest.get("manifest_id") != manifest_identity):
        raise ArchiveError("retained report manifest identity mismatch")
    machine_ref = descriptors["machine_json"]
    declared_report = report_manifest.get("report")
    if not isinstance(declared_report, dict) or any(
        declared_report.get(key) != machine_ref[key] for key in ("reference", "sha256", "artifact_id")
    ):
        raise ArchiveError("report manifest report binding mismatch")
    declared_components = report_manifest.get("components")
    if not isinstance(declared_components, list) or len(declared_components) != 3:
        raise ArchiveError("report manifest component inventory mismatch")
    expected = {(descriptors[role]["reference"], descriptors[role]["sha256"], descriptors[role]["artifact_id"])
                for role in ("markdown", "machine_json", "canonical_evidence_json")}
    if any(not isinstance(item, dict) for item in declared_components) or {
        (item.get("reference"), item.get("sha256"), item.get("artifact_id")) for item in declared_components
    } != expected:
        raise ArchiveError("report manifest component binding mismatch")
    return record


@lru_cache(maxsize=24)
def _validated_inventory(
    location: str,
    device: int,
    inode: int,
    size: int,
    mtime_ns: int,
    ctime_ns: int,
) -> dict:
    """Hash all entries once for an unchanged filesystem identity/revision."""
    return validate_archive(location)


_READERS = ContextVar("agmark_verified_archive_readers", default=())


def _file_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _active_archive_reader(path):
    location = str(Path(path).absolute())
    for reader in reversed(_READERS.get()):
        if str(reader.path) == location:
            return reader
    return None


class VerifiedArchiveReader:
    """One thread-bound, current-byte read operation over one validated ZIP.

    Inventory validation and ZIP directory parsing happen once. Every requested
    member is still rehashed, and descriptor/path identities are checked before
    and after reads. No validation result survives the operation or permits a
    later authority boundary to skip its own validation.
    """

    def __init__(self, path):
        self.path = Path(path).absolute()
        self._entered = False
        self._owner = None
        self._stream = None
        self._bundle = None
        self._manifest = None
        self._token = None

    def __enter__(self):
        if self._entered:
            raise ArchiveError("archive reader is single-use")
        self._entered = True
        self._owner = get_ident()
        try:
            _safe_archive_path(self.path)
            before = self.path.lstat()
            flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0)
                     | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
            descriptor = os.open(self.path, flags)
            try:
                self._stream = os.fdopen(descriptor, "rb")
            except BaseException:
                os.close(descriptor)
                raise
            self._identity = _file_identity(before)
            self._check_current()
            self._bundle = ZipFile(self._stream, "r", allowZip64=True)
            self._manifest = _validate_archive_bundle(self._bundle, self.path.stem)
            self._check_current()
            self._token = _READERS.set((*_READERS.get(), self))
            return self
        except BaseException as exc:
            self._close()
            if isinstance(exc, (ArchiveError, KeyboardInterrupt, SystemExit)):
                raise
            raise ArchiveError("archive cannot be safely opened for verified reads") from exc

    def _check_current(self):
        if self._owner != get_ident() or self._stream is None:
            raise ArchiveError("archive reader is closed or belongs to another thread")
        try:
            current = self.path.lstat()
            opened = os.fstat(self._stream.fileno())
        except OSError as exc:
            raise ArchiveError("archive changed during verified reads") from exc
        if (not stat.S_ISREG(current.st_mode) or not stat.S_ISREG(opened.st_mode)
                or _file_identity(current) != self._identity
                or _file_identity(opened) != self._identity):
            raise ArchiveError("archive changed during verified reads")

    @property
    def manifest(self):
        self._check_current()
        return _json(canonical_bytes(self._manifest))

    def _expected(self, name):
        self._check_current()
        _member(name)
        if name not in self._manifest["files"]:
            raise ArchiveError("archive member not listed: " + name)
        return self._manifest["files"][name]

    def read_member(self, name):
        expected = self._expected(name)
        try:
            data = self._bundle.read(name)
            if digest(data) != expected:
                raise ArchiveError("archive member changed during read")
            self._check_current()
            return data
        except (BadZipFile, OSError, EOFError, RuntimeError) as exc:
            raise ArchiveError("archive member cannot be safely read") from exc

    def verify_member(self, name, expected_sha256=None):
        expected = self._expected(name)
        if expected_sha256 is not None and expected_sha256 != expected:
            raise ArchiveError("archive member differs from expected artifact identity")
        try:
            with self._bundle.open(name, "r") as stream:
                actual = _hash_stream(stream)
            if actual != expected:
                raise ArchiveError("archive member changed during read")
            self._check_current()
        except (BadZipFile, OSError, EOFError, RuntimeError) as exc:
            raise ArchiveError("archive member cannot be safely verified") from exc

    def _close(self):
        try:
            if self._bundle is not None:
                self._bundle.close()
        finally:
            self._bundle = None
            if self._stream is not None:
                self._stream.close()
                self._stream = None

    def __exit__(self, kind, error, traceback):
        try:
            if kind is None:
                self._check_current()
        finally:
            if self._token is not None:
                _READERS.reset(self._token)
                self._token = None
            self._close()


@contextmanager
def verified_archive_reads(path):
    """Reuse a same-operation reader only within its thread and lexical scope."""
    existing = _active_archive_reader(path)
    if existing is not None:
        existing._check_current()
        yield existing
        existing._check_current()
    else:
        with VerifiedArchiveReader(path) as reader:
            yield reader


def read_archive_member(path: str | Path, name: str) -> bytes:
    """Read one hash-verified member without rehashing unrelated members N times.

    The complete inventory is revalidated after any detectable filesystem change.
    The requested member is always rehashed, even on a cached inventory. An
    independently trusted whole-archive digest is still needed for authenticity.
    """
    active = _active_archive_reader(path)
    if active is not None:
        return active.read_member(name)
    target = Path(path)
    _safe_archive_path(target)
    info = target.stat()
    manifest = _validated_inventory(
        str(target.resolve(strict=True)), info.st_dev, info.st_ino,
        info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )
    _member(name)
    if name not in manifest["files"]:
        raise ArchiveError("archive member not listed: " + name)
    with ZipFile(target, "r") as bundle:
        data = bundle.read(name)
    if digest(data) != manifest["files"][name]:
        raise ArchiveError("archive member changed during read")
    return data


def _sync_directory(path: Path) -> None:
    if os.name != "nt":
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


@contextmanager
def _publication_lock(root: Path, gid: str, outcome: _PublicationOutcome | None = None):
    marker = root / ("." + gid + ".archive-lock")
    try:
        descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ArchiveError("another archive revision is in progress") from exc
    os.close(descriptor)
    try:
        yield
    finally:
        try:
            marker.unlink(missing_ok=True)
        except Exception as exc:
            if outcome is None or outcome.archive_path is None:
                raise
            outcome.issues.append(_cleanup_issue("publication_lock", exc))


def _temporary(root: Path) -> Path:
    descriptor, location = tempfile.mkstemp(dir=root, prefix=".agmark-stage-", suffix=".agmark")
    os.close(descriptor)
    return Path(location)


def _write_zip_file(zipped: ZipFile, name: str, path: Path) -> None:
    with path.open("rb") as source, zipped.open(name, "w", force_zip64=True) as dest:
        shutil.copyfileobj(source, dest, _CHUNK)


def _write_zip_bytes(zipped: ZipFile, name: str, data: bytes) -> None:
    zipped.writestr(name, data)


def _working_files(root: Path, gid: str) -> dict[str, Path]:
    paths = [root / gid, root / ".agmark-validation" / gid,
             root / ".agmark-progress" / (gid + ".json"),
             root / ("." + gid + ".terminal")]
    members = {}
    for path in paths:
        if not path.exists():
            continue
        if path.is_symlink():
            raise ArchiveError("working evidence contains symlink")
        if path.is_file():
            files = [path]
        elif path.is_dir():
            files = [f for f in path.rglob("*") if f.is_file()]
            if any(f.is_symlink() for f in path.rglob("*")):
                raise ArchiveError("working evidence contains symlink")
        else:
            raise ArchiveError("unsupported working evidence node")
        for file in files:
            name = file.relative_to(root).as_posix()
            if not _core_member(name, gid):
                raise ArchiveError("non-core evidence in working directory")
            members[_member(name)] = file
    return members


def seal_generation(root: str | Path, generation_id: str, *,
                    report_components: Mapping[str, bytes],
                    completion_record: Mapping[str, object]) -> Path:
    """Publish validated original evidence, then retire loose sources.

    ArchiveCleanupWarning means publication succeeded and must not be retried
    or reported as a failed release. All earlier failures remain failures.
    """
    root = Path(root).resolve(strict=True)
    gid = _generation(generation_id)
    target = archive_path(root, gid)
    outcome = _PublicationOutcome()
    with _publication_lock(root, gid, outcome):
        if target.exists() or target.is_symlink():
            raise ArchiveError("run archive already sealed")
        members = _working_files(root, gid)
        core = {}
        for name, path in sorted(members.items()):
            with path.open("rb") as stream:
                core[name] = _hash_stream(stream)
        if "." + gid + ".terminal" not in core:
            raise ArchiveError("cannot seal a run without terminal authority")
        status = members["." + gid + ".terminal"].read_text("ascii")
        if status not in ("accepted", "blocked", "executed"):
            raise ArchiveError("invalid terminal status")
        generated = {}
        if not any(name.startswith(gid + "/") for name in core):
            # A golden-gate failure can legally have zero produced benchmark
            # artifacts. Retain a clearly declared blocked-status marker, never
            # a fabricated observation, score, or accepted artifact.
            if status != "blocked":
                raise ArchiveError("completed run cannot omit all original artifacts")
            marker = gid + "/blocked-generation.json"
            generated[marker] = canonical_bytes({
                "generation_id": gid, "terminal_status": "blocked",
                "evidence_availability": "not_produced",
            })
            core[marker] = digest(generated[marker])
        if not isinstance(report_components, Mapping) or not isinstance(completion_record, Mapping):
            raise ArchiveError("sealing requires completion record and exact report components")
        for name, data in report_components.items():
            if not _member(name).startswith("reports/") or not isinstance(data, bytes):
                raise ArchiveError("invalid completed report component")
        record = dict(completion_record)
        record["core_sha256"] = digest(canonical_bytes(core))
        generated.update(report_components)
        generated[COMPLETION_MEMBER] = canonical_bytes(record)
        inventory = dict(core)
        inventory.update({name: digest(data) for name, data in generated.items()})
        manifest = {
            "format": FORMAT, "generation_id": gid, "terminal_status": status,
            "revision": 1, "previous_manifest_sha256": None,
            "sealed_at": datetime.now(timezone.utc).isoformat(),
            "core_files": core, "core_sha256": digest(canonical_bytes(core)),
            "files": inventory,
        }
        stage = _temporary(root)
        try:
            with ZipFile(stage, "w", compression=ZIP_DEFLATED, compresslevel=6,
                         allowZip64=True) as output:
                for name, path in sorted(members.items()):
                    _write_zip_file(output, name, path)
                for name, data in sorted(generated.items()):
                    _write_zip_bytes(output, name, data)
                _write_zip_bytes(output, "manifest.json", canonical_bytes(manifest))
            # Windows requires a writable descriptor for os.fsync/_commit.
            with stage.open("r+b") as sealed:
                os.fsync(sealed.fileno())
            validate_archive(stage, _expected_generation_id=gid)
        except Exception:
            stage.unlink(missing_ok=True)
            raise
        # Validation is name-bound. Stage remains private; verify exact bytes after install.
        try:
            os.replace(stage, target)
            _sync_directory(root)
            validate_archive(target)
        except Exception:
            target.unlink(missing_ok=True)
            stage.unlink(missing_ok=True)
            raise
        # Commit only after exact installed bytes pass every archive check.
        outcome.archive_path = target
        try:
            _retire_sources(root, gid)
        except Exception as exc:
            outcome.issues.append(_cleanup_issue("loose_sources", exc))
    if outcome.issues:
        raise ArchiveCleanupWarning(target, tuple(outcome.issues))
    return target


def _retire_sources(root: Path, gid: str) -> None:
    """Retire loose sources only after the installed ZIP is authoritative."""
    directory = root / gid
    if directory.exists():
        for file in directory.rglob("*"):
            file.chmod(0o755 if file.is_dir() else 0o600)
        directory.chmod(0o755)
        shutil.rmtree(directory)
    companion = root / ".agmark-validation" / gid
    if companion.exists():
        shutil.rmtree(companion)
    progress = root / ".agmark-progress" / (gid + ".json")
    progress.unlink(missing_ok=True)
    for suffix in (".terminal", ".generation-claim"):
        claim = root / ("." + gid + suffix)
        try:
            mode = claim.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(mode):
            raise ArchiveError("working generation claim is not a regular file")
        # Storage creates these claims read-only. Windows cannot unlink a
        # read-only file; retire only these owned markers, and only after
        # the installed archive has been validated as authoritative.
        claim.chmod(0o600)
        claim.unlink(missing_ok=True)
    for folder in (root / ".agmark-validation", root / ".agmark-progress"):
        try:
            folder.rmdir()
        except FileNotFoundError:
            pass
        except OSError as exc:
            # Shared parent folders may still hold other generations.
            if exc.errno not in (errno.ENOTEMPTY, errno.EEXIST):
                raise
    _sync_directory(root)


def revise_archive(root: str | Path, generation_id: str,
                   additions: Mapping[str, bytes]) -> Path:
    """Revise optional presentation metadata without changing completed outputs.

    A newly sealed revision includes the previous manifest bytes and references its
    SHA-256, leaving all original run evidence and previous report bytes unchanged.
    """
    root = Path(root).resolve(strict=True)
    gid = _generation(generation_id)
    target = archive_path(root, gid)
    if not isinstance(additions, Mapping) or not additions:
        raise ArchiveError("revision requires new archived artifacts")
    for name, value in additions.items():
        _member(name)
        if name != "history/presentation.json":
            raise ArchiveError("completed archives permit presentation-only revisions")
        if not isinstance(value, bytes):
            raise ArchiveError("archived artifact must contain exact bytes")
    with _publication_lock(root, gid):
        old = validate_archive(target)
        old_raw = canonical_bytes(old)
        old_names = set(old["files"])
        for name, value in additions.items():
            if name in old_names and name != "history/presentation.json":
                raise ArchiveError("cannot overwrite retained report or verification evidence")
        if all(name in old_names and digest(value) == old["files"][name]
               for name, value in additions.items()):
            return target
        revision = old["revision"] + 1
        previous_path = "revisions/%06d.json" % old["revision"]
        if previous_path in old_names:
            raise ArchiveError("revision history collision")
        inventory = dict(old["files"])
        inventory[previous_path] = digest(old_raw)
        for name, value in additions.items():
            inventory[name] = digest(value)
        manifest = dict(old, revision=revision, sealed_at=datetime.now(timezone.utc).isoformat(),
                        files=inventory, previous_manifest_sha256=digest(old_raw))
        stage = _temporary(root)
        try:
            with ZipFile(target, "r") as source, ZipFile(stage, "w", compression=ZIP_DEFLATED,
                                                         compresslevel=6, allowZip64=True) as output:
                for name in sorted(old["files"]):
                    if name in additions:
                        continue
                    with source.open(name, "r") as inp, output.open(name, "w", force_zip64=True) as dest:
                        shutil.copyfileobj(inp, dest, _CHUNK)
                for name, data in sorted(additions.items()):
                    _write_zip_bytes(output, name, data)
                _write_zip_bytes(output, previous_path, old_raw)
                _write_zip_bytes(output, "manifest.json", canonical_bytes(manifest))
            # Windows requires a writable descriptor for os.fsync/_commit.
            with stage.open("r+b") as sealed:
                os.fsync(sealed.fileno())
            validate_archive(stage, _expected_generation_id=gid)
            os.replace(stage, target)
            _sync_directory(root)
        finally:
            stage.unlink(missing_ok=True)
    return target


__all__ = ["ArchiveError", "ArchiveCleanupWarning", "archive_path", "canonical_bytes", "digest",
           "read_archive_member", "revise_archive", "seal_generation", "validate_archive",
           "VerifiedArchiveReader", "verified_archive_reads"]
