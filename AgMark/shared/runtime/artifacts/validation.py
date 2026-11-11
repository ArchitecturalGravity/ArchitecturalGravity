"""Separate write-once post-treatment validation retention.

Finalized accepted artifacts and their index are never reopened. A companion
manifest binds typed treatment validation and immutable scored source hashes.
"""
import hashlib
import json
from contextlib import nullcontext
import os
from pathlib import Path
import re
import shutil
import tempfile
from AgMark.shared.validation.codex_cache.serialization import validation_bytes, admit_validation
from AgMark.shared.validation.codex_cache.models import ProviderRequestCacheTreatmentSummary


def _hash(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


class ValidationArtifactStore:
    def __init__(self, scored_store):
        self.scored_store = scored_store
        self.root = scored_store.root / ".agmark-validation"

    def _generation(self, generation_id):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", generation_id):
            raise ValueError("unsafe validation generation identity")
        if self.root.is_symlink() or any(p.is_symlink() for p in self.root.parents):
            raise ValueError("validation destination cannot use symlinks")
        if (self.scored_store.root / ("." + generation_id + ".deleted")).exists():
            raise ValueError("deleted generation cannot receive validation")
        return self.root / generation_id

    def retain_failure(self, terminal, code):
        """Persist a content-free validation failure outside scored authority."""
        return self.retain(terminal, (), failure_code=code)

    def retain(self, terminal, summaries, *, capture_evidence=None, failure_code=None, source_evidence=None):
        terminal.revalidate(self.scored_store)
        summaries = tuple(summaries)
        if any(type(s) is not ProviderRequestCacheTreatmentSummary or s.generation_id != terminal.generation_id for s in summaries):
            raise ValueError("typed validation generation differs")
        if failure_code is not None and (not re.fullmatch(r"[A-Za-z_]+(?::[A-Za-z]+)?", failure_code) or summaries or capture_evidence or source_evidence):
            raise ValueError("failure companion requires a content-free code and no validation data")
        destination = self._generation(terminal.generation_id)
        if destination.exists():
            raise ValueError("validation generation is write-once")
        self.root.mkdir(exist_ok=True)
        stage = Path(tempfile.mkdtemp(dir=self.root, prefix=".validation-"))
        try:
            documents = []
            captures = []
            sources = []
            from AgMark.shared.validation.codex_cache.source_evidence import validate_source
            for identity, (kind, data) in sorted((source_evidence or {}).items()):
                if type(data) is not bytes or _hash(data) != identity:
                    raise ValueError("replay source integrity differs")
                validate_source(kind, data)
                name = "source-" + identity.removeprefix("sha256:") + ".json"
                (stage / name).write_bytes(data)
                sources.append({"kind": kind, "reference": name, "sha256": identity})
            for identity, data in sorted((capture_evidence or {}).items()):
                if type(data) is not bytes or _hash(data) != identity:
                    raise ValueError("capture evidence integrity differs")
                spans = json.loads(data)
                if not isinstance(spans, list):
                    raise ValueError("normalized capture evidence must be an array")
                from AgMark.shared.validation.codex_cache.collector import canonical_capture_spans
                if canonical_capture_spans(spans) != spans:
                    raise ValueError("capture evidence contains non-admitted content")
                name = "capture-" + identity.removeprefix("sha256:") + ".json"
                (stage / name).write_bytes(data)
                captures.append({"reference": name, "sha256": identity})
            for index, summary in enumerate(summaries):
                data = validation_bytes(summary)
                name = "treatment-" + str(index) + ".json"
                (stage / name).write_bytes(data)
                documents.append({"reference":name,"sha256":_hash(data),"treatment_id":summary.treatment_id})
            manifest = {"generation_id":terminal.generation_id,
                "accepted_snapshot_id":terminal.accepted_snapshot_id,
                "execution_boundary_fingerprint":terminal.execution_boundary_fingerprint,
                "run_plan_sha256":terminal.plan_sha256,
                "scored_evidence":{r.artifact_id:r.sha256 for r in terminal.artifact_index.artifacts},
                "validations":documents,"captures":captures,"sources":sources,"scope":"configuration_equivalent_replay","included_in_score":False}
            if failure_code is not None:
                manifest["failure_code"] = failure_code
            raw = (json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode()
            (stage / "manifest.json").write_bytes(raw)
            (stage / "manifest.sha256").write_text(_hash(raw))
            if failure_code is None:
                self._read_directory(terminal, stage, staging=True)
            terminal.revalidate(self.scored_store)
            self._generation(terminal.generation_id)
            if destination.exists():
                raise ValueError("validation destination appeared during capture")
            os.rename(stage, destination)
            try:
                self._generation(terminal.generation_id)
                if failure_code is not None:
                    terminal.revalidate(self.scored_store)
                    return ()
                return self.read(terminal)
            except Exception:
                # A concurrent deletion after rename must not resurrect evidence.
                if (self.scored_store.root / ("." + terminal.generation_id + ".deleted")).exists() and destination.exists():
                    shutil.rmtree(destination)
                raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)

    def read(self, terminal, *, required=False):
        operation = getattr(self.scored_store, "verified_reads", None)
        with operation(terminal.generation_id) if callable(operation) else nullcontext() as reader:
            return self._read_directory(terminal, self._generation(terminal.generation_id),
                                        required=required, archive_reader=reader)

    def read_with_records(self, terminal, *, required=False):
        """Admit one current companion and derive references from that same read.

        This result is local to the caller's operation. It never substitutes for
        a later authority-boundary read or prepublication integrity check.
        """
        values = self.read(terminal, required=required)
        return values, self._records_from_values(terminal, values)

    def _read_directory(self, terminal, directory, *, staging=False, required=False, archive_reader=None):
        from .archive import archive_path, validate_archive
        sealed = archive_path(self.scored_store.root, terminal.generation_id)
        if staging:
            if directory.parent != self.root or not directory.name.startswith(".validation-"):
                raise ValueError("validation staging directory is outside its owned root")
        elif archive_reader is not None or sealed.exists():
            manifest = archive_reader.manifest if archive_reader is not None else validate_archive(sealed)
            prefix = directory.relative_to(self.scored_store.root).as_posix() + "/"
            if prefix + "manifest.json" not in manifest["files"]:
                if required:
                    raise ValueError("required validation companion is missing")
                return ()
        elif not directory.exists():
            if required:
                raise ValueError("required validation companion is missing")
            return ()
        terminal.revalidate(self.scored_store)
        def read(name):
            reference = (directory / name).relative_to(self.scored_store.root).as_posix()
            if staging:
                # A private, not-yet-published stage is not a generation archive.
                # Retain the store's confinement/symlink checks while validating
                # its bytes before the atomic rename into the generation scope.
                return self.scored_store._path_for_reference(reference).read_bytes()
            return self.scored_store.read_member(reference)
        raw = read("manifest.json")
        if _hash(raw) != read("manifest.sha256").decode():
            raise ValueError("validation manifest integrity differs")
        manifest = json.loads(raw)
        if (manifest["generation_id"],manifest["accepted_snapshot_id"],manifest["run_plan_sha256"],manifest["execution_boundary_fingerprint"]) != (
            terminal.generation_id,terminal.accepted_snapshot_id,terminal.plan_sha256,terminal.execution_boundary_fingerprint):
            raise ValueError("validation accepted identity differs")
        if manifest["scored_evidence"] != {r.artifact_id:r.sha256 for r in terminal.artifact_index.artifacts}:
            raise ValueError("validation scored evidence differs")
        if manifest.get("failure_code") is not None:
            code = manifest["failure_code"]
            if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z_]+(?::[A-Za-z]+)?", code) or manifest["validations"] or manifest.get("captures") or manifest.get("sources"):
                raise ValueError("invalid validation failure companion")
            raise ValueError("Replay validation unavailable: " + code)
        observations_by_treatment = {}
        observation_digests = {}
        for raw in terminal.treatment_observations:
            observation = json.loads(raw)
            identity = observation["observation_id"]
            if identity in observation_digests:
                raise ValueError("duplicate scored observation identity")
            observation_digests[identity] = _hash(raw)
            observations_by_treatment.setdefault(observation["treatment_id"], []).append(observation)
        scored_observation_digests = {r.sha256 for r in terminal.artifact_index.artifacts
                                     if r.role == "treatment_observation"}
        if manifest.get("scope") != "configuration_equivalent_replay" or manifest.get("included_in_score") is not False:
            raise ValueError("validation scope differs")
        captures = {}
        for entry in manifest.get("captures", ()):
            if not re.fullmatch(r"capture-[0-9a-f]{64}\.json", entry["reference"]):
                raise ValueError("unsafe capture evidence reference")
            data = read(entry["reference"])
            if _hash(data) != entry["sha256"] or entry["sha256"] in captures:
                raise ValueError("capture evidence integrity differs")
            spans = json.loads(data)
            from AgMark.shared.validation.codex_cache.collector import canonical_capture_spans
            if not isinstance(spans, list) or canonical_capture_spans(spans) != spans:
                raise ValueError("retained capture contains non-admitted content")
            captures[entry["sha256"]] = spans
        sources = {}
        from AgMark.shared.validation.codex_cache.source_evidence import validate_source, verify_managed_sources
        for entry in manifest.get("sources", ()):
            if not re.fullmatch(r"source-[0-9a-f]{64}\.json", entry["reference"]):
                raise ValueError("unsafe replay source reference")
            raw = read(entry["reference"])
            if _hash(raw) != entry["sha256"] or entry["sha256"] in sources:
                raise ValueError("replay source integrity differs")
            validate_source(entry["kind"], raw)
            sources[entry["sha256"]] = (entry["kind"], raw)
        results = []
        for entry in manifest["validations"]:
            if not re.fullmatch(r"treatment-\d+\.json",entry["reference"]):
                raise ValueError("unsafe validation evidence reference")
            raw = read(entry["reference"])
            if _hash(raw) != entry["sha256"]:
                raise ValueError("validation evidence integrity differs")
            value = admit_validation(raw)
            observations = observations_by_treatment.get(entry["treatment_id"], ())
            ids = tuple(o["observation_id"] for o in observations)
            if value.generation_id != terminal.generation_id or value.treatment_id != entry["treatment_id"] or value.scored_observation_ids != ids:
                raise ValueError("retained validation observation linkage differs")
            by_id = {o["observation_id"]: o for o in observations}
            from AgMark.shared.validation.codex_cache.normalization import normalize_spans
            for replay in value.replays:
                observation = by_id.get(replay.validates_observation_id)
                if observation is None or str(observation["repetition"]) != replay.repetition_id:
                    raise ValueError("retained replay repetition linkage differs")
                observed_digest = observation_digests[replay.validates_observation_id]
                if (observed_digest not in scored_observation_digests
                        or observed_digest not in replay.evidence_references):
                    raise ValueError("retained replay lacks its exact scored observation evidence")
                allowed_extensions = {"arcgrav.telemetry:stock-transport-diagnostics-v2",
                    "arcgrav.telemetry:startup-evidence", "arcgrav.telemetry:probe-evidence",
                    "arcgrav.telemetry:capabilities-evidence"}
                if set(replay.extensions) - allowed_extensions:
                    raise ValueError("replay contains undeclared evidence extensions")
                expected_references = (observed_digest,) + tuple(field.value for key, field in replay.extensions.items()
                    if key.endswith("-evidence") and field.availability == "available")
                if (len(replay.evidence_references) != len(expected_references)
                        or set(replay.evidence_references) != set(expected_references)):
                    raise ValueError("replay references must contain only its observation and source evidence")
                verify_managed_sources(replay, observation, sources)
                from AgMark.shared.validation.codex_cache.diagnostics import EXTENSION, PROFILE, diagnostic_field
                diagnostic = replay.extensions.get(EXTENSION)
                if diagnostic is not None:
                    if len(diagnostic.evidence_references) != 1 or diagnostic.evidence_references[0] not in captures:
                        raise ValueError("transport diagnostics lack exact capture evidence")
                    ref = diagnostic.evidence_references[0]
                    expected = diagnostic_field(captures[ref], validation_id=replay.validation_id, evidence_reference=ref)
                    if expected.to_dict() != diagnostic.to_dict():
                        raise ValueError("transport diagnostics differ from capture evidence")
                if not replay.requests:
                    continue
                refs = {ref for request in replay.requests for ref in request.evidence_references}
                if len(refs) != 1 or not refs <= captures.keys():
                    raise ValueError("retained request capture evidence unavailable")
                ref = next(iter(refs))
                reconstructed, _ = normalize_spans(captures[ref], validation_id=replay.validation_id,
                    capabilities=replay.capabilities, evidence_reference=ref,
                    profile=PROFILE)
                if tuple(r.to_dict() for r in reconstructed) != tuple(r.to_dict() for r in replay.requests):
                    raise ValueError("retained requests differ from capture evidence")
            results.append(value)
        if len({v.treatment_id for v in results}) != len(results):
            raise ValueError("duplicate treatment validation")
        used_sources = {field.value for value in results for replay in value.replays
            for key, field in replay.extensions.items()
            if key in {"arcgrav.telemetry:startup-evidence", "arcgrav.telemetry:capabilities-evidence", "arcgrav.telemetry:probe-evidence"}}
        used_captures = {ref for value in results for replay in value.replays
            for request in replay.requests for ref in request.evidence_references}
        used_captures.update(ref for value in results for replay in value.replays
            for key, field in replay.extensions.items() if key == "arcgrav.telemetry:stock-transport-diagnostics-v2"
            for ref in field.evidence_references)
        if used_captures != set(captures):
            raise ValueError("replay capture evidence must be exactly linked")
        if used_sources != set(sources):
            raise ValueError("replay source evidence must be exactly linked")
        return tuple(results)

    def delete_generation(self, generation_id):
        # Deletion is called only as part of the caller's existing run deletion.
        directory = self.root / generation_id
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", generation_id) or directory.is_symlink() or self.root.is_symlink():
            raise ValueError("unsafe validation deletion")
        if directory.exists():
            shutil.rmtree(directory)

    def records(self, terminal):
        return self.read_with_records(terminal)[1]

    def _records_from_values(self, terminal, values):
        from .model import ArtifactRecord, SchemaBinding
        directory = self._generation(terminal.generation_id)
        return tuple(ArtifactRecord(
            artifact_id=terminal.generation_id + ":validation-treatment:" + str(index),
            role="post_treatment_validation", reference=(directory / ("treatment-" + str(index) + ".json")).relative_to(self.scored_store.root).as_posix(),
            sha256=_hash(validation_bytes(value)), provenance="separate post-treatment validation manifest",
            schema=SchemaBinding(value.schema_id,value.schema_version)) for index,value in enumerate(values))
