"""Transient shell input snapshots crossing from controls to commands."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite

from .projections import _require_bool, _require_non_empty

@dataclass(frozen=True, slots=True)
class SidebarControlInputSnapshot:
    """One transient provider-neutral runner-control input value."""

    control_name: str
    value: str | float | None
    secret: bool = False

    def __post_init__(self) -> None:
        _require_non_empty(self.control_name, name="control_name")
        if self.value is not None and (
            isinstance(self.value, bool)
            or not isinstance(self.value, (str, int, float))
        ):
            raise ValueError("value must be text, numeric, or None")
        if isinstance(self.value, (int, float)) and not isinstance(self.value, bool):
            number = float(self.value)
            if not isfinite(number):
                raise ValueError("numeric value must be finite")
            object.__setattr__(self, "value", number)
        _require_bool(self.secret, name="secret")


@dataclass(frozen=True, slots=True)
class SidebarInputSnapshot:
    """Transient user intent emitted to the caller-owned Build Plan operation."""

    benchmark: str | None
    runner: str | None
    model: str | None
    credential: str
    temperature: float | None
    max_tokens: float | None
    additional_controls: tuple[SidebarControlInputSnapshot, ...] = ()
    model_discovery_context_fingerprints: tuple[str, ...] = ()
    prompt_folder: str = ""
    iterations: int = 1
    randomize_treatment_start: bool = True
    randomize_per_iteration: bool = True
    run_cache_validation_replays: bool = False
    excluded_treatments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.excluded_treatments, (str, bytes)):
            raise ValueError("excluded_treatments must be file names")
        exclusions = tuple(self.excluded_treatments)
        if (
            any(not isinstance(name, str) or not name for name in exclusions)
            or len(set(exclusions)) != len(exclusions)
        ):
            raise ValueError("excluded_treatments must contain unique file names")
        object.__setattr__(self, "excluded_treatments", exclusions)
        if type(self.randomize_treatment_start) is not bool:
            raise ValueError("randomize_treatment_start must be a boolean")
        if type(self.randomize_per_iteration) is not bool:
            raise ValueError("randomize_per_iteration must be a boolean")
        if type(self.run_cache_validation_replays) is not bool:
            raise ValueError("run_cache_validation_replays must be a boolean")
        if type(self.iterations) is not int or self.iterations < 1:
            raise ValueError("iterations must be a positive integer")


CommandOperation = Callable[[], object]
CommandDispatcher = Callable[[CommandOperation], object]
BuildPlanOperation = Callable[[SidebarInputSnapshot], object]
TestRunnerOperation = Callable[[SidebarInputSnapshot], object]
SidebarIntentOperation = Callable[[SidebarInputSnapshot], object]
RunSelectionOperation = Callable[[str], object]
LifecycleOperation = Callable[[], object]


__all__ = ["SidebarControlInputSnapshot", "SidebarInputSnapshot"]
