"""Immutable target-composition authority for shared runner execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


SelectorValue = str | int | bool | None


def _non_empty_text(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _selector_items(
    value: Mapping[str, SelectorValue] | Iterable[tuple[str, SelectorValue]],
) -> tuple[tuple[str, SelectorValue], ...]:
    if isinstance(value, Mapping):
        raw_items = value.items()
    else:
        raw_items = value

    normalized: list[tuple[str, SelectorValue]] = []
    names: set[str] = set()
    for raw_name, raw_value in raw_items:
        name = _non_empty_text(raw_name, name="launch environment selector name")
        if name in names:
            raise ValueError(f"duplicate launch environment selector {name!r}")
        if raw_value is not None and type(raw_value) not in {str, int, bool}:
            raise ValueError(
                "launch environment selector values must be str, int, bool, or None"
            )
        if isinstance(raw_value, str) and not raw_value:
            raise ValueError("launch environment selector string values must be non-empty")
        names.add(name)
        normalized.append((name, raw_value))
    return tuple(normalized)


def _artifact_ids(value: Iterable[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError("runner implementation artifact authority must be a sequence")
    normalized = tuple(
        _non_empty_text(item, name="runner implementation artifact id") for item in value
    )
    if not normalized:
        raise ValueError("runner implementation artifact authority must not be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError("runner implementation artifact authority contains duplicates")
    return normalized


@dataclass(frozen=True)
class TargetCompositionDescriptor:
    """Validated immutable data selected before runner-owned preflight or submission.

    The descriptor contains target-varying authority as data. Shared runner logic can
    therefore consume one composition boundary without selecting alternate behavior
    because a target is live or mock.
    """

    target_class: str
    evidence_class: str
    runtime_id: str
    runtime_version: str | None
    access_method: str
    external_provider_submission: bool
    launch_mode: str
    launch_environment_selector: tuple[tuple[str, SelectorValue], ...]
    executable: str
    authentication_class: str
    compatibility_profile: str | None
    production_runner_entry_point: str
    runner_implementation_artifact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "target_class",
            "evidence_class",
            "runtime_id",
            "access_method",
            "launch_mode",
            "executable",
            "authentication_class",
            "production_runner_entry_point",
        ):
            _non_empty_text(getattr(self, name), name=name)

        if not isinstance(self.external_provider_submission, bool):
            raise ValueError("external_provider_submission must be boolean")
        if self.runtime_version is not None:
            _non_empty_text(self.runtime_version, name="runtime_version")
        if self.compatibility_profile is not None:
            _non_empty_text(self.compatibility_profile, name="compatibility_profile")
        if ":" not in self.production_runner_entry_point:
            raise ValueError(
                "production_runner_entry_point must use module:attribute form"
            )

        object.__setattr__(
            self,
            "launch_environment_selector",
            _selector_items(self.launch_environment_selector),
        )
        object.__setattr__(
            self,
            "runner_implementation_artifact_ids",
            _artifact_ids(self.runner_implementation_artifact_ids),
        )

    @classmethod
    def create(
        cls,
        *,
        target_class: str,
        evidence_class: str,
        runtime_id: str,
        runtime_version: str | None,
        access_method: str,
        external_provider_submission: bool,
        launch_mode: str,
        launch_environment_selector: Mapping[str, SelectorValue]
        | Iterable[tuple[str, SelectorValue]],
        executable: str,
        authentication_class: str,
        compatibility_profile: str | None,
        production_runner_entry_point: str,
        runner_implementation_artifact_ids: Iterable[str],
    ) -> "TargetCompositionDescriptor":
        """Construct a descriptor while defensively freezing collection inputs."""

        return cls(
            target_class=target_class,
            evidence_class=evidence_class,
            runtime_id=runtime_id,
            runtime_version=runtime_version,
            access_method=access_method,
            external_provider_submission=external_provider_submission,
            launch_mode=launch_mode,
            launch_environment_selector=_selector_items(launch_environment_selector),
            executable=executable,
            authentication_class=authentication_class,
            compatibility_profile=compatibility_profile,
            production_runner_entry_point=production_runner_entry_point,
            runner_implementation_artifact_ids=_artifact_ids(
                runner_implementation_artifact_ids
            ),
        )

    @property
    def runner_authority(self) -> tuple[str, tuple[str, ...]]:
        """Return the exact runner identity used by same-runner parity checks."""

        return (
            self.production_runner_entry_point,
            self.runner_implementation_artifact_ids,
        )
