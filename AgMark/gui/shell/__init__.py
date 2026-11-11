"""Persistent shell contracts and concrete desktop composition."""

from .command_router import ShellCommandRouter
from .input_snapshot import SidebarControlInputSnapshot, SidebarInputSnapshot
from .projections import (
    CurrentRunProjection, ExecutionBoundaryProjection, NumericInputProjection,
    RetainedRunProjection, RunPlanProjection, SidebarChoiceControlProjection,
    SidebarModelChoiceProjection, SidebarNumericControlProjection,
    SidebarPrerequisiteDiagnosticProjection, SidebarProjection,
    SidebarResolvedTextProjection, SidebarTextControlProjection, WorkspaceProjection,
)
from .window import BenchmarkShellWindow, PYSIDE6_AVAILABLE

__all__ = [
    "BenchmarkShellWindow", "CurrentRunProjection", "ExecutionBoundaryProjection",
    "NumericInputProjection", "PYSIDE6_AVAILABLE", "RetainedRunProjection",
    "RunPlanProjection", "ShellCommandRouter", "SidebarChoiceControlProjection",
    "SidebarControlInputSnapshot", "SidebarInputSnapshot", "SidebarModelChoiceProjection",
    "SidebarNumericControlProjection", "SidebarPrerequisiteDiagnosticProjection",
    "SidebarProjection", "SidebarResolvedTextProjection", "SidebarTextControlProjection",
    "WorkspaceProjection",
]
