"""Benchmark-neutral golden execution and admission.

The implementation deliberately accepts only explicit registered declaration
objects plus an immutable accepted execution boundary. It never discovers a
runtime through PATH, a shell, platform defaults, or benchmark semantics.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import time
from typing import Final

from ..artifacts import (
    ArtifactPayload,
    ArtifactRecord,
    ContractBinding,
    FilesystemArtifactStore,
    RETAINABLE_EVIDENCE,
    SchemaBinding,
    retain_artifact_stage,
    sha256_bytes,
)
from ..identity import (
    AcceptedBoundaryIdentity,
    IdentityRef,
    canonical_json_bytes,
    canonical_sha256,
)


GOLDEN_EXECUTION_CONTRACT_ID: Final[str] = "arcgrav.shared.golden-execution"
GOLDEN_EXECUTION_CONTRACT_VERSION: Final[str] = "2.0.0"
GOLDEN_OBSERVATION_SCHEMA_ID: Final[str] = "arcgrav.shared.schema.golden-observation"
GOLDEN_OBSERVATION_SCHEMA_VERSION: Final[str] = "2.0.0"
GOLDEN_EVIDENCE_EXTENSION: Final[str] = "arcgrav.shared.golden:evidence"

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_ENVIRONMENT_VARIABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PYTHON_RUNTIME_ID: Final[str] = "arcgrav.runtime.python"
_PYTHON_TEXT_OUTPUT_PRELUDE: Final[str] = (
    "import pathlib, runpy, sys\n"
    "target = pathlib.Path(sys.argv[1]).resolve()\n"
    "sys.path[0] = str(target.parent)\n"
    "sys.argv = sys.argv[1:]\n"
    "for stream in (sys.stdout, sys.stderr):\n"
    "    try:\n"
    "        stream.reconfigure(newline='\\n')\n"
    "    except (AttributeError, ValueError):\n"
    "        pass\n"
    "runpy.run_path(str(target), run_name='__main__')\n"
)


class GoldenExecutionError(ValueError):
    """Base class for invalid or blocked golden execution authority."""


class GoldenRegistrationError(GoldenExecutionError):
    """A golden declaration is incomplete or internally inconsistent."""


class GoldenIntegrityError(GoldenExecutionError):
    """Registered golden bytes cannot establish their declared identity."""


@dataclass(frozen=True)
class GoldenArtifactRequirement:
    """One registered golden implementation artifact."""

    artifact_id: str
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        _nonempty(self.artifact_id, "artifact_id")
        _safe_relative(self.relative_path)
        if not isinstance(self.sha256, str) or _SHA256.fullmatch(self.sha256) is None:
            raise GoldenRegistrationError(
                "golden artifact sha256 must use 'sha256:' plus 64 lowercase hex digits"
            )


@dataclass(frozen=True)
class TransientEnvironmentBinding:
    """Registered invocation-only secret source delivered to one child env key."""

    source_id: str
    environment_variable: str

    def __post_init__(self) -> None:
        _nonempty(self.source_id, "transient source_id")
        if (
            not isinstance(self.environment_variable, str)
            or _ENVIRONMENT_VARIABLE.fullmatch(self.environment_variable) is None
        ):
            raise GoldenRegistrationError(
                "transient environment variable must be an explicit valid variable name"
            )


@dataclass(frozen=True)
class GoldenDeclaration:
    """Validated benchmark-neutral declaration needed to execute one golden."""

    golden_implementation: IdentityRef
    runtime_identity: IdentityRef
    artifacts: tuple[GoldenArtifactRequirement, ...]
    entry_artifact_id: str
    environment_family: str
    environment_family_control: str = "golden.environment_family"
    runtime_executable_control: str = "golden.runtime_sha256"
    runtime_executable: str | None = None
    preflight_arguments: tuple[str, ...] = ("--version",)
    arguments: tuple[str, ...] = ()
    input_transport: str = "stdin"
    input_artifact_id: str | None = None
    output_transport: str = "stdout"
    require_nonempty_output: bool = True
    timeout_seconds: float = 60.0
    preflight_timeout_seconds: float = 10.0
    max_stdout_bytes: int = 16 * 1024 * 1024
    max_stderr_bytes: int = 4 * 1024 * 1024
    transient_environment: tuple[TransientEnvironmentBinding, ...] = ()

    def __post_init__(self) -> None:
        if type(self.golden_implementation) is not IdentityRef:
            raise TypeError("golden_implementation must be IdentityRef")
        if type(self.runtime_identity) is not IdentityRef:
            raise TypeError("runtime_identity must be IdentityRef")
        if (
            self.runtime_identity.sha256 is None
            or self.runtime_identity.reference is None
        ):
            raise GoldenRegistrationError(
                "runtime_identity must bind exact executable reference and SHA-256"
            )
        if self.runtime_identity.reference not in {"runtime/python", "runtime/executable"}:
            raise GoldenRegistrationError("runtime_identity reference must be a logical runtime reference")
        if not self.runtime_executable or not Path(self.runtime_executable).is_absolute():
            raise GoldenRegistrationError("runtime_executable must be a transient absolute path")
        if not self.artifacts or any(
            type(value) is not GoldenArtifactRequirement for value in self.artifacts
        ):
            raise GoldenRegistrationError(
                "artifacts must contain at least one GoldenArtifactRequirement"
            )
        ids = [value.artifact_id for value in self.artifacts]
        if len(set(ids)) != len(ids):
            raise GoldenRegistrationError("golden artifact identities must be unique")
        _nonempty(self.entry_artifact_id, "entry_artifact_id")
        if self.entry_artifact_id not in set(ids):
            raise GoldenRegistrationError(
                "entry_artifact_id must identify a declared golden artifact"
            )
        if self.input_transport == "registered_file":
            if (
                not isinstance(self.input_artifact_id, str)
                or self.input_artifact_id not in set(ids)
            ):
                raise GoldenRegistrationError(
                    "registered_file input must identify a declared golden artifact"
                )
            paths = [value.relative_path for value in self.artifacts]
            if len(set(paths)) != len(paths):
                raise GoldenRegistrationError(
                    "registered_file artifact paths must be unique"
                )
        elif self.input_artifact_id is not None:
            raise GoldenRegistrationError(
                "input_artifact_id requires registered_file input transport"
            )
        for field, value in (
            ("environment_family", self.environment_family),
            ("environment_family_control", self.environment_family_control),
            ("runtime_executable_control", self.runtime_executable_control),
            ("input_transport", self.input_transport),
            ("output_transport", self.output_transport),
        ):
            _nonempty(value, field)
        _argv(self.preflight_arguments, "preflight_arguments")
        _argv(self.arguments, "arguments")
        if not isinstance(self.require_nonempty_output, bool):
            raise TypeError("require_nonempty_output must be bool")
        if (
            not isinstance(self.timeout_seconds, (int, float))
            or isinstance(self.timeout_seconds, bool)
            or self.timeout_seconds <= 0
        ):
            raise GoldenRegistrationError("timeout_seconds must be positive")
        if (
            not isinstance(self.preflight_timeout_seconds, (int, float))
            or isinstance(self.preflight_timeout_seconds, bool)
            or self.preflight_timeout_seconds <= 0
        ):
            raise GoldenRegistrationError(
                "preflight_timeout_seconds must be positive"
            )
        for field, value in (
            ("max_stdout_bytes", self.max_stdout_bytes),
            ("max_stderr_bytes", self.max_stderr_bytes),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise GoldenRegistrationError(f"{field} must be a non-negative integer")
        if any(
            type(value) is not TransientEnvironmentBinding
            for value in self.transient_environment
        ):
            raise TypeError(
                "transient_environment must contain TransientEnvironmentBinding values"
            )
        source_ids = [value.source_id for value in self.transient_environment]
        variables = [
            value.environment_variable for value in self.transient_environment
        ]
        if len(set(source_ids)) != len(source_ids):
            raise GoldenRegistrationError("transient source identities must be unique")
        if len(set(variables)) != len(variables):
            raise GoldenRegistrationError(
                "transient environment destinations must be unique"
            )


@dataclass(frozen=True)
class GoldenCaseInput:
    """Accepted case/input bytes supplied to the registered golden."""

    case_id: str
    data: bytes

    def __post_init__(self) -> None:
        _nonempty(self.case_id, "case_id")
        if not isinstance(self.data, bytes):
            raise TypeError("golden case input must be exact bytes")

    @property
    def sha256(self) -> str:
        return sha256_bytes(self.data)


@dataclass(frozen=True)
class GoldenExecutionResult:
    """Fixed golden observation plus any exact retained artifact records."""

    observation_bytes: bytes
    retained_artifacts: tuple[ArtifactRecord, ...]
    treatment_authorized: bool

    @property
    def observation(self) -> dict[str, object]:
        return json.loads(self.observation_bytes.decode("utf-8"))


@dataclass(frozen=True)
class _ResolvedLaunch:
    environment_family: str
    runtime_reference: str
    runtime_sha256: str
    preflight_command: tuple[str, ...]


@dataclass(frozen=True)
class _ProcessOutcome:
    command: tuple[str, ...]
    started_at: str
    completed_at: str
    wall_seconds: float
    returncode: int | None
    stdout: bytes
    stderr: bytes
    status: str
    reason_code: str | None
    diagnostic: str | None


class _Block(Exception):
    def __init__(self, code: str, status: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message


def execute_required_golden(
    *,
    accepted_generation_id: str,
    benchmark: IdentityRef | Mapping[str, object],
    benchmark_root: str | Path,
    accepted_boundary: AcceptedBoundaryIdentity,
    retained_boundary_document: Mapping[str, object],
    declaration: GoldenDeclaration,
    case_input: GoldenCaseInput,
    artifact_store: FilesystemArtifactStore,
    transient_values: Mapping[str, str] | None = None,
) -> GoldenExecutionResult:
    """Execute and retain one required golden before treatment construction.

    Only the explicitly supported native environment family is launchable in
    this implementation frontier. Any other accepted family is blocked rather
    than silently falling back to the host.
    """

    generation = _safe_segment(accepted_generation_id, "accepted_generation_id")
    benchmark_ref = IdentityRef.from_value(benchmark, field="benchmark")
    if type(accepted_boundary) is not AcceptedBoundaryIdentity:
        raise TypeError("accepted_boundary must be AcceptedBoundaryIdentity")
    if not isinstance(retained_boundary_document, Mapping):
        raise TypeError("retained_boundary_document must be a mapping")
    if type(declaration) is not GoldenDeclaration:
        raise TypeError("declaration must be GoldenDeclaration")
    if type(case_input) is not GoldenCaseInput:
        raise TypeError("case_input must be GoldenCaseInput")
    if type(artifact_store) is not FilesystemArtifactStore:
        raise TypeError("artifact_store must be FilesystemArtifactStore")
    transient = dict(transient_values or {})
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in transient.items()):
        raise TypeError("transient_values must map string source IDs to string values")

    admission_started_at = _utc_now()
    diagnostics: list[str] = []
    integrity_evidence: list[dict[str, object]] = []
    observed: dict[str, object] = {}
    process_records: tuple[ArtifactRecord, ...] = ()
    status = "failed"
    admission_state = "blocked"
    output: dict[str, object] = {"availability": "unavailable"}
    secret_values = tuple(transient.values())

    try:
        boundary = accepted_boundary.revalidate(retained_boundary_document)
        boundary_document = boundary.to_dict()
        environment = _named_values(
            boundary_document.get("environment"),
            field="accepted execution boundary environment",
        )
        root = _benchmark_root(benchmark_root)

        if declaration.input_transport not in {"stdin", "registered_file"}:
            raise _Block(
                "GOLDEN_INPUT_TRANSPORT_UNSUPPORTED",
                "unsupported",
                "registered golden input transport is not supported by this executor",
            )
        if declaration.output_transport != "stdout":
            raise _Block(
                "GOLDEN_OUTPUT_TRANSPORT_UNSUPPORTED",
                "unsupported",
                "registered golden output transport is not supported by this executor",
            )

        artifact_paths, integrity_evidence = _verify_artifacts(root, declaration)
        launch = _resolve_native_launch(
            environment=environment,
            declaration=declaration,
        )
        preflight = _preflight(
            launch=launch,
            declaration=declaration,
            cwd=root,
            secrets=secret_values,
        )
        observed["preflight"] = preflight

        # Re-establish exact registered bytes and runtime bytes immediately
        # before workload submission so preflight cannot authorize drift.
        artifact_paths, integrity_evidence = _verify_artifacts(root, declaration)
        current_runtime_hash = sha256_bytes(Path(launch.runtime_reference).read_bytes())
        if current_runtime_hash != launch.runtime_sha256:
            raise _Block(
                "GOLDEN_RUNTIME_CHANGED_AFTER_PREFLIGHT",
                "failed",
                "resolved runtime bytes changed after successful preflight",
            )

        child_environment = _transient_environment(
            declaration=declaration,
            values=transient,
        )
        with ExitStack() as workspace:
            execution_root = root
            execution_paths = artifact_paths
            input_bytes: bytes | None = case_input.data
            if declaration.input_transport == "registered_file":
                execution_root = Path(workspace.enter_context(
                    tempfile.TemporaryDirectory(
                        prefix=".golden-input-", dir=artifact_store.root
                    )
                ))
                execution_paths = _stage_registered_file_input(
                    declaration=declaration,
                    artifact_paths=artifact_paths,
                    case_input=case_input,
                    destination=execution_root,
                )
                input_bytes = None
                observed["input_file_snapshot"] = {
                    "artifact_id": declaration.input_artifact_id,
                    "relative_path": execution_paths[
                        declaration.input_artifact_id
                    ].relative_to(execution_root).as_posix(),
                    "sha256": case_input.sha256,
                    "byte_length": len(case_input.data),
                }
            entry = execution_paths[declaration.entry_artifact_id]
            process = _run_process(
                command=_workload_command(
                    launch=launch,
                    declaration=declaration,
                    entry=entry,
                ),
                cwd=execution_root,
                input_bytes=input_bytes,
                environment=child_environment,
                timeout_seconds=float(declaration.timeout_seconds),
                secrets=secret_values,
            )

        if _contains_secret(process.command, process.stdout, process.stderr, secret_values):
            raise _Block(
                "GOLDEN_SECRET_EVIDENCE_LEAK",
                "failed",
                "golden process command or output contained transient secret material",
            )

        observed.update(
            {
                "environment_family": launch.environment_family,
                "runtime_reference": declaration.runtime_identity.reference,
                "runtime_sha256": launch.runtime_sha256,
                "command": {"runtime": declaration.runtime_identity.reference,
                            "entry": declaration.entry_artifact_id,
                            "arguments": list(declaration.arguments)},
                "process_started_at": process.started_at,
                "process_completed_at": process.completed_at,
                "wall_seconds": process.wall_seconds,
                "returncode": process.returncode,
                "stdout": {
                    "byte_length": len(process.stdout),
                    "sha256": sha256_bytes(process.stdout),
                },
                "stderr": {
                    "byte_length": len(process.stderr),
                },
            }
        )

        if process.reason_code == "GOLDEN_LAUNCH_FAILED":
            raise _Block(
                process.reason_code,
                process.status,
                process.diagnostic or "golden process could not be launched",
            )

        if len(process.stdout) > declaration.max_stdout_bytes:
            raise _Block(
                "GOLDEN_STDOUT_LIMIT_EXCEEDED",
                "failed",
                "golden stdout exceeded the registered byte limit",
            )
        if len(process.stderr) > declaration.max_stderr_bytes:
            raise _Block(
                "GOLDEN_STDERR_LIMIT_EXCEEDED",
                "failed",
                "golden stderr exceeded the registered byte limit",
            )

        process_records = retain_artifact_stage(
            store=artifact_store,
            generation_id=generation,
            stage_id=_observation_id(
                generation,
                declaration,
                case_input,
                boundary.fingerprint,
            )
            + "-process",
            artifacts=(
                ArtifactPayload(
                    artifact_id=_observation_id(
                        generation,
                        declaration,
                        case_input,
                        boundary.fingerprint,
                    )
                    + ".stdout",
                    role="golden_stdout",
                    relative_path="stdout.bin",
                    data=process.stdout,
                    provenance="arcgrav.shared.runtime.golden",
                    retention_class=RETAINABLE_EVIDENCE,
                    media_type="application/octet-stream",
                    contract=ContractBinding(
                        GOLDEN_EXECUTION_CONTRACT_ID,
                        GOLDEN_EXECUTION_CONTRACT_VERSION,
                    ),
                ),
            ),
        )
        stdout_record = next(
            value for value in process_records if value.role == "golden_stdout"
        )
        output = {
            "availability": "retained",
            "sha256": stdout_record.sha256,
            "reference": stdout_record.reference,
            "byte_length": len(process.stdout),
        }

        if process.status != "completed":
            raise _Block(
                process.reason_code or "GOLDEN_PROCESS_FAILED",
                process.status,
                process.diagnostic or "golden process did not complete successfully",
            )
        if declaration.require_nonempty_output and not process.stdout:
            raise _Block(
                "GOLDEN_REQUIRED_OUTPUT_EMPTY",
                "failed",
                "registered golden requires non-empty stdout",
            )

        status = "completed"
        admission_state = "admitted"
    except _Block as exc:
        status = exc.status
        admission_state = "blocked"
        diagnostics.append(exc.code)
    except Exception as exc:
        status = "failed"
        admission_state = "blocked"
        diagnostics.append("GOLDEN_INTERNAL_FAILURE")

    completed_at = _utc_now()
    observation_id = _observation_id_from_authority(
        generation=generation,
        declaration=declaration,
        case_input=case_input,
        boundary_fingerprint=accepted_boundary.fingerprint,
    )
    observation = _observation_document(
        observation_id=observation_id,
        generation=generation,
        benchmark=benchmark_ref,
        declaration=declaration,
        boundary_fingerprint=accepted_boundary.fingerprint,
        case_input=case_input,
        integrity_evidence=integrity_evidence,
        observed=observed,
        status=status,
        admission_state=admission_state,
        output=output,
        diagnostics=diagnostics,
        started_at=admission_started_at,
        completed_at=completed_at,
    )
    validate_golden_evidence(observation)
    observation_bytes = canonical_json_bytes(observation)
    all_records = process_records

    try:
        observation_records = retain_artifact_stage(
            store=artifact_store,
            generation_id=generation,
            stage_id=observation_id + "-observation",
            artifacts=(
                ArtifactPayload(
                    artifact_id=observation_id + ".observation",
                    role="golden_observation",
                    relative_path="observation.json",
                    data=observation_bytes,
                    provenance="arcgrav.shared.runtime.golden",
                    retention_class=RETAINABLE_EVIDENCE,
                    media_type="application/json",
                    encoding="utf-8",
                    schema=SchemaBinding(
                        GOLDEN_OBSERVATION_SCHEMA_ID,
                        GOLDEN_OBSERVATION_SCHEMA_VERSION,
                    ),
                    contract=ContractBinding(
                        GOLDEN_EXECUTION_CONTRACT_ID,
                        GOLDEN_EXECUTION_CONTRACT_VERSION,
                    ),
                ),
            ),
        )
        all_records = tuple(
            sorted((*process_records, *observation_records), key=lambda item: item.artifact_id)
        )
    except Exception as exc:
        # Without retained observation bytes there is no golden authority even
        # if the process itself succeeded and its raw bytes were retained.
        if admission_state == "admitted":
            diagnostics.append("GOLDEN_OBSERVATION_RETENTION_FAILED")
            admission_state = "blocked"
            status = "failed"
            observation = _observation_document(
                observation_id=observation_id,
                generation=generation,
                benchmark=benchmark_ref,
                declaration=declaration,
                boundary_fingerprint=accepted_boundary.fingerprint,
                case_input=case_input,
                integrity_evidence=integrity_evidence,
                observed=observed,
                status=status,
                admission_state=admission_state,
                output=output,
                diagnostics=diagnostics,
                started_at=admission_started_at,
                completed_at=_utc_now(),
            )
            validate_golden_evidence(observation)
    observation_bytes = canonical_json_bytes(observation)

    return GoldenExecutionResult(
        observation_bytes=observation_bytes,
        retained_artifacts=all_records,
        treatment_authorized=admission_state == "admitted",
    )


def _resolve_native_launch(
    *,
    environment: Mapping[str, object],
    declaration: GoldenDeclaration,
) -> _ResolvedLaunch:
    family = environment.get(declaration.environment_family_control)
    if not isinstance(family, str) or not family:
        raise _Block(
            "GOLDEN_ENVIRONMENT_FAMILY_MISSING",
            "unsupported",
            "accepted boundary lacks the registered golden environment-family control",
        )
    if family != declaration.environment_family:
        raise _Block(
            "GOLDEN_ENVIRONMENT_FAMILY_MISMATCH",
            "unsupported",
            "accepted boundary environment family differs from registered golden authority",
        )
    if family != "native":
        raise _Block(
            "GOLDEN_ENVIRONMENT_UNSUPPORTED",
            "unsupported",
            f"accepted environment family {family!r} has no registered resolver in this implementation",
        )

    if environment.get(declaration.runtime_executable_control) != declaration.runtime_identity.sha256:
        raise _Block("GOLDEN_RUNTIME_REFERENCE_MISMATCH", "failed",
                     "accepted runtime identity differs from registered runtime")
    candidate = Path(declaration.runtime_executable)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise _Block("GOLDEN_RUNTIME_UNAVAILABLE", "unavailable",
                     "registered native runtime could not be resolved") from exc
    if not resolved.is_file():
        raise _Block("GOLDEN_RUNTIME_UNAVAILABLE", "unavailable",
                     "registered native runtime is not a file")
    declared_sha256 = declaration.runtime_identity.sha256
    runtime_hash = sha256_bytes(resolved.read_bytes())
    if runtime_hash != declared_sha256:
        raise _Block(
            "GOLDEN_RUNTIME_HASH_MISMATCH",
            "failed",
            "accepted runtime executable failed registered SHA-256 verification",
        )
    return _ResolvedLaunch(
        environment_family=family,
        runtime_reference=str(resolved),
        runtime_sha256=runtime_hash,
        preflight_command=(str(resolved), *declaration.preflight_arguments),
    )


def _workload_command(
    *,
    launch: _ResolvedLaunch,
    declaration: GoldenDeclaration,
    entry: Path,
) -> tuple[str, ...]:
    if declaration.runtime_identity.id != _PYTHON_RUNTIME_ID:
        return (launch.runtime_reference, str(entry), *declaration.arguments)
    return (
        launch.runtime_reference,
        "-c",
        _PYTHON_TEXT_OUTPUT_PRELUDE,
        str(entry),
        *declaration.arguments,
    )


def _preflight(
    *,
    launch: _ResolvedLaunch,
    declaration: GoldenDeclaration,
    cwd: Path,
    secrets: tuple[str, ...],
) -> dict[str, object]:
    try:
        result = subprocess.run(
            launch.preflight_command,
            cwd=str(cwd),
            env={},
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=float(declaration.preflight_timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise _Block(
            "GOLDEN_RUNTIME_PREFLIGHT_TIMEOUT",
            "timed_out",
            f"registered runtime preflight timed out: {exc}",
        ) from exc
    except OSError as exc:
        raise _Block(
            "GOLDEN_RUNTIME_PREFLIGHT_FAILED",
            "unavailable",
            f"registered runtime preflight could not launch: {exc}",
        ) from exc

    evidence = {
        "runtime_reference": declaration.runtime_identity.reference,
        "arguments": list(declaration.preflight_arguments),
        "returncode": result.returncode,
        "stdout_sha256": sha256_bytes(result.stdout),
        "stdout_byte_length": len(result.stdout),
        "stderr_byte_length": len(result.stderr),
    }
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace")[:512]
        raise _Block(
            "GOLDEN_RUNTIME_PREFLIGHT_FAILED",
            "failed",
            "registered runtime preflight returned nonzero"
            + (f": {_redact(detail, secrets)}" if detail else ""),
        )
    return evidence


def _run_process(
    *,
    command: tuple[str, ...],
    cwd: Path,
    input_bytes: bytes | None,
    environment: Mapping[str, str],
    timeout_seconds: float,
    secrets: tuple[str, ...],
) -> _ProcessOutcome:
    started_at = _utc_now()
    start_ns = time.monotonic_ns()
    try:
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            env=dict(environment),
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except OSError as exc:
        return _ProcessOutcome(
            command=command,
            started_at=started_at,
            completed_at=_utc_now(),
            wall_seconds=(time.monotonic_ns() - start_ns) / 1_000_000_000,
            returncode=None,
            stdout=b"",
            stderr=b"",
            status="unavailable",
            reason_code="GOLDEN_LAUNCH_FAILED",
            diagnostic=_redact(f"golden launch failed: {exc}", secrets),
        )

    try:
        stdout, stderr = process.communicate(
            input=input_bytes,
            timeout=timeout_seconds,
        )
        completed_at = _utc_now()
        wall = (time.monotonic_ns() - start_ns) / 1_000_000_000
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        return _ProcessOutcome(
            command=command,
            started_at=started_at,
            completed_at=_utc_now(),
            wall_seconds=(time.monotonic_ns() - start_ns) / 1_000_000_000,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            status="timed_out",
            reason_code="GOLDEN_TIMEOUT",
            diagnostic="golden process exceeded the registered timeout",
        )

    if process.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace")[:512]
        return _ProcessOutcome(
            command=command,
            started_at=started_at,
            completed_at=completed_at,
            wall_seconds=wall,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
            status="failed",
            reason_code="GOLDEN_NONZERO_EXIT",
            diagnostic="golden process returned nonzero"
            + (f": {_redact(detail, secrets)}" if detail else ""),
        )
    return _ProcessOutcome(
        command=command,
        started_at=started_at,
        completed_at=completed_at,
        wall_seconds=wall,
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
        status="completed",
        reason_code=None,
        diagnostic=None,
    )


def _transient_environment(
    *,
    declaration: GoldenDeclaration,
    values: Mapping[str, str],
) -> dict[str, str]:
    expected = {binding.source_id for binding in declaration.transient_environment}
    actual = set(values)
    missing = expected - actual
    extra = actual - expected
    if missing:
        raise _Block(
            "GOLDEN_TRANSIENT_MATERIAL_MISSING",
            "unavailable",
            "required registered transient invocation material is unavailable",
        )
    if extra:
        raise _Block(
            "GOLDEN_TRANSIENT_MATERIAL_UNDECLARED",
            "failed",
            "undeclared transient invocation material was supplied",
        )
    return {
        binding.environment_variable: values[binding.source_id]
        for binding in declaration.transient_environment
    }


def _verify_artifacts(
    root: Path,
    declaration: GoldenDeclaration,
) -> tuple[dict[str, Path], list[dict[str, object]]]:
    paths: dict[str, Path] = {}
    evidence: list[dict[str, object]] = []
    for requirement in declaration.artifacts:
        relative = _safe_relative(requirement.relative_path)
        candidate = root.joinpath(*relative.parts)
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise _Block(
                "GOLDEN_ARTIFACT_UNAVAILABLE",
                "unavailable",
                f"registered golden artifact {requirement.artifact_id!r} is unavailable: {exc}",
            ) from exc
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise _Block(
                "GOLDEN_ARTIFACT_PATH_ESCAPE",
                "failed",
                f"registered golden artifact {requirement.artifact_id!r} escapes benchmark root",
            ) from exc
        if not resolved.is_file():
            raise _Block(
                "GOLDEN_ARTIFACT_UNAVAILABLE",
                "unavailable",
                f"registered golden artifact {requirement.artifact_id!r} is not a file",
            )
        actual = sha256_bytes(resolved.read_bytes())
        if actual != requirement.sha256:
            raise _Block(
                "GOLDEN_ARTIFACT_HASH_MISMATCH",
                "failed",
                f"registered golden artifact {requirement.artifact_id!r} failed SHA-256 verification",
            )
        paths[requirement.artifact_id] = resolved
        evidence.append(
            {
                "artifact_id": requirement.artifact_id,
                "relative_path": requirement.relative_path,
                "expected_sha256": requirement.sha256,
                "observed_sha256": actual,
                "verified": True,
            }
        )
    evidence.sort(key=lambda value: str(value["artifact_id"]))
    return paths, evidence


def _stage_registered_file_input(
    *,
    declaration: GoldenDeclaration,
    artifact_paths: Mapping[str, Path],
    case_input: GoldenCaseInput,
    destination: Path,
) -> dict[str, Path]:
    """Freeze verified code and case bytes together before a file-based launch.

    Package-relative paths are preserved so the registered program can load its
    default source relative to its own file. Repository edits after staging
    cannot replace the accepted input while the child is running.
    """
    paths: dict[str, Path] = {}
    for requirement in declaration.artifacts:
        data = artifact_paths[requirement.artifact_id].read_bytes()
        if sha256_bytes(data) != requirement.sha256:
            raise _Block(
                "GOLDEN_ARTIFACT_HASH_MISMATCH",
                "failed",
                f"registered artifact {requirement.artifact_id!r} changed before staging",
            )
        if (
            requirement.artifact_id == declaration.input_artifact_id
            and data != case_input.data
        ):
            raise _Block(
                "GOLDEN_INPUT_ARTIFACT_MISMATCH",
                "failed",
                "registered input file does not contain the accepted case bytes",
            )
        relative = _safe_relative(requirement.relative_path)
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o400)
        paths[requirement.artifact_id] = target
    _verify_artifacts(destination, declaration)
    return paths


def validate_golden_evidence(document):
    """Reject unknown/raw golden fields, including relabeled legacy evidence."""
    import json
    from ...validation.structure import validate_json_schema_structure
    from ...validation.core import SchemaIdentity
    schema = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "golden_observation.schema.json").read_text())
    issues = validate_json_schema_structure(document, schema_document=schema,
        schema=SchemaIdentity(GOLDEN_OBSERVATION_SCHEMA_ID, GOLDEN_OBSERVATION_SCHEMA_VERSION),
        source_id="golden-observation")
    if issues:
        raise ValueError("golden evidence violates current retention contract")


def _observation_document(
    *,
    observation_id: str,
    generation: str,
    benchmark: IdentityRef,
    declaration: GoldenDeclaration,
    boundary_fingerprint: str,
    case_input: GoldenCaseInput,
    integrity_evidence: list[dict[str, object]],
    observed: Mapping[str, object],
    status: str,
    admission_state: str,
    output: Mapping[str, object],
    diagnostics: list[str],
    started_at: str,
    completed_at: str,
) -> dict[str, object]:
    input_evidence: dict[str, object] = {
        "transport": declaration.input_transport if declaration.input_transport in {"stdin", "registered_file"} else "unsupported",
        "sha256": case_input.sha256,
        "byte_length": len(case_input.data),
    }
    if declaration.input_artifact_id is not None:
        requirement = next(
            value for value in declaration.artifacts
            if value.artifact_id == declaration.input_artifact_id
        )
        input_evidence.update({
            "artifact_id": requirement.artifact_id,
            "relative_path": requirement.relative_path,
        })
    evidence = {
        "case_id": case_input.case_id,
        "input": input_evidence,
        "declared": {
            "entry_artifact_id": declaration.entry_artifact_id,
            "implementation_artifact_ids": [
                value.artifact_id for value in declaration.artifacts
            ],
            "environment_family": declaration.environment_family,
            "environment_family_control": declaration.environment_family_control,
            "runtime_executable_control": declaration.runtime_executable_control,
            "runtime": declaration.runtime_identity.to_dict(),
            "require_nonempty_output": declaration.require_nonempty_output,
            "timeout_seconds": declaration.timeout_seconds,
            "max_stdout_bytes": declaration.max_stdout_bytes,
            "max_stderr_bytes": declaration.max_stderr_bytes,
        },
        "artifact_integrity": integrity_evidence,
        "observed": dict(observed),
    }
    return {
        "schema_id": GOLDEN_OBSERVATION_SCHEMA_ID,
        "schema_version": GOLDEN_OBSERVATION_SCHEMA_VERSION,
        "extensions": {GOLDEN_EVIDENCE_EXTENSION: evidence},
        "golden_observation_id": observation_id,
        "accepted_generation_id": generation,
        "benchmark": benchmark.to_dict(),
        "golden_implementation": declaration.golden_implementation.to_dict(),
        "runtime_identity": declaration.runtime_identity.to_dict(),
        "execution_boundary_fingerprint": boundary_fingerprint,
        "contract": {
            "id": GOLDEN_EXECUTION_CONTRACT_ID,
            "version": GOLDEN_EXECUTION_CONTRACT_VERSION,
        },
        "status": status,
        "admission_state": admission_state,
        "output": dict(output),
        "started_at": started_at,
        "completed_at": completed_at,
        "diagnostics": list(diagnostics),
    }


def _observation_id(
    generation: str,
    declaration: GoldenDeclaration,
    case_input: GoldenCaseInput,
    boundary_fingerprint: str,
) -> str:
    return _observation_id_from_authority(
        generation=generation,
        declaration=declaration,
        case_input=case_input,
        boundary_fingerprint=boundary_fingerprint,
    )


def _observation_id_from_authority(
    *,
    generation: str,
    declaration: GoldenDeclaration,
    case_input: GoldenCaseInput,
    boundary_fingerprint: str,
) -> str:
    digest = canonical_sha256(
        {
            "generation": generation,
            "golden": declaration.golden_implementation.to_dict(),
            "runtime": declaration.runtime_identity.to_dict(),
            "case_id": case_input.case_id,
            "input_sha256": case_input.sha256,
            "execution_boundary_fingerprint": boundary_fingerprint,
        }
    )
    return "golden-" + digest.removeprefix("sha256:")[:32]


def _named_values(value: object, *, field: str) -> dict[str, object]:
    if not isinstance(value, list):
        raise _Block(
            "GOLDEN_BOUNDARY_ENVIRONMENT_INVALID",
            "failed",
            f"{field} must be canonical name/value records",
        )
    result: dict[str, object] = {}
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"name", "value"}:
            raise _Block(
                "GOLDEN_BOUNDARY_ENVIRONMENT_INVALID",
                "failed",
                f"{field} contains an invalid record",
            )
        name = item["name"]
        if not isinstance(name, str) or not name or name in result:
            raise _Block(
                "GOLDEN_BOUNDARY_ENVIRONMENT_INVALID",
                "failed",
                f"{field} contains an invalid or duplicate name",
            )
        result[name] = item["value"]
    return result


def _benchmark_root(value: str | Path) -> Path:
    root = Path(value)
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise _Block(
            "GOLDEN_BENCHMARK_ROOT_UNAVAILABLE",
            "unavailable",
            f"benchmark root is unavailable: {exc}",
        ) from exc
    if not resolved.is_dir():
        raise _Block(
            "GOLDEN_BENCHMARK_ROOT_INVALID",
            "failed",
            "benchmark root must resolve to a directory",
        )
    return resolved


def _safe_relative(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise GoldenRegistrationError("golden artifact path must be non-empty")
    if "\\" in value or "\x00" in value:
        raise GoldenRegistrationError(
            "golden artifact paths must use normalized POSIX separators"
        )
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise GoldenRegistrationError(
            "golden artifact path must be a confined relative path"
        )
    return path


def _safe_segment(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise GoldenExecutionError(f"{field} must be a non-empty string")
    if value in {".", ".."} or "/" in value or "\\" in value or "\x00" in value:
        raise GoldenExecutionError(f"{field} must be a safe single path segment")
    return value


def _argv(values: tuple[str, ...], field: str) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(value, str) or "\x00" in value for value in values
    ):
        raise GoldenRegistrationError(f"{field} must be a tuple of safe strings")


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise GoldenRegistrationError(f"{field} must be a non-empty string")
    return value


def _contains_secret(
    command: tuple[str, ...],
    stdout: bytes,
    stderr: bytes,
    secrets: tuple[str, ...],
) -> bool:
    for secret in secrets:
        if not secret:
            continue
        if any(secret in part for part in command):
            return True
        encoded = secret.encode("utf-8")
        if encoded in stdout or encoded in stderr:
            return True
    return False


def _redact(value: str, secrets: tuple[str, ...]) -> str:
    redacted = value
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        redacted = redacted.replace(secret, "<redacted>")
    return redacted


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "GOLDEN_EVIDENCE_EXTENSION",
    "GOLDEN_EXECUTION_CONTRACT_ID",
    "GOLDEN_EXECUTION_CONTRACT_VERSION",
    "GOLDEN_OBSERVATION_SCHEMA_ID",
    "GOLDEN_OBSERVATION_SCHEMA_VERSION",
    "GoldenArtifactRequirement",
    "GoldenCaseInput",
    "GoldenDeclaration",
    "GoldenExecutionError",
    "GoldenExecutionResult",
    "GoldenIntegrityError",
    "GoldenRegistrationError",
    "TransientEnvironmentBinding",
    "execute_required_golden",
]
