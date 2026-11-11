"""Caller-owned shell command routing and background dispatch."""

from __future__ import annotations

from collections.abc import Callable
from threading import Thread

from .input_snapshot import SidebarInputSnapshot
from .projections import _require_non_empty

def _dispatch_command_in_background(operation: CommandOperation) -> Thread:
    """Run one caller-owned command away from the GUI event thread."""

    worker = Thread(
        target=operation,
        name="arcgrav-gui-command",
        daemon=True,
    )
    worker.start()
    return worker


class ShellCommandRouter:
    """Dispatch shell-originated requests without creating lifecycle authority."""

    def __init__(
        self,
        *,
        command_dispatcher: CommandDispatcher | None = None,
        on_build_plan: BuildPlanOperation | None = None,
        on_test_runner: TestRunnerOperation | None = None,
        on_run_selected: RunSelectionOperation | None = None,
        on_delete_run: RunSelectionOperation | None = None,
        on_accept_plan: LifecycleOperation | None = None,
        on_start_benchmark: LifecycleOperation | None = None,
    ) -> None:
        if command_dispatcher is not None and not callable(command_dispatcher):
            raise ValueError("command_dispatcher must be callable or None")
        for name, operation in (
            ("on_build_plan", on_build_plan),
            ("on_test_runner", on_test_runner),
            ("on_run_selected", on_run_selected),
            ("on_delete_run", on_delete_run),
            ("on_accept_plan", on_accept_plan),
            ("on_start_benchmark", on_start_benchmark),
        ):
            if operation is not None and not callable(operation):
                raise ValueError(f"{name} must be callable or None")
        self._dispatch = command_dispatcher or _dispatch_command_in_background
        self._on_build_plan = on_build_plan
        self._on_test_runner = on_test_runner
        self._on_run_selected = on_run_selected
        self._on_delete_run = on_delete_run
        self._on_accept_plan = on_accept_plan
        self._on_start_benchmark = on_start_benchmark

    @property
    def run_selection_available(self) -> bool:
        return self._on_run_selected is not None

    def _submit(self, operation: CommandOperation) -> object:
        return self._dispatch(operation)

    def build_plan(self, snapshot: SidebarInputSnapshot) -> object | None:
        if not isinstance(snapshot, SidebarInputSnapshot):
            raise ValueError("snapshot must be SidebarInputSnapshot")
        if self._on_build_plan is None:
            return None
        return self._submit(lambda: self._on_build_plan(snapshot))

    def test_runner(self, snapshot: SidebarInputSnapshot) -> object | None:
        if not isinstance(snapshot, SidebarInputSnapshot):
            raise ValueError("snapshot must be SidebarInputSnapshot")
        if self._on_test_runner is None:
            return None
        return self._submit(lambda: self._on_test_runner(snapshot))

    def select_run(self, run_id: str) -> object | None:
        run_id = _require_non_empty(run_id, name="run_id")
        if self._on_run_selected is None:
            return None
        return self._submit(lambda: self._on_run_selected(run_id))

    def delete_run(self, run_id: str) -> object | None:
        run_id = _require_non_empty(run_id, name="run_id")
        if self._on_delete_run is None:
            return None
        return self._submit(lambda: self._on_delete_run(run_id))

    def accept_plan(self) -> object | None:
        if self._on_accept_plan is None:
            return None
        return self._submit(self._on_accept_plan)

    def start_benchmark(self) -> object | None:
        if self._on_start_benchmark is None:
            return None
        return self._submit(self._on_start_benchmark)


__all__ = ["ShellCommandRouter"]
