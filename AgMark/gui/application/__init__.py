"""Production shared-authority binding for the ArcGrav desktop GUI."""

from AgMark.gui.diagnostics import ApplicationEnvironmentProjection
from AgMark.gui.readiness import derive_application_environment
from .contracts import (
    ApplicationProjectionUpdate, ApplicationProjector, ApplicationRequestResolver,
    ConsoleProjectionUpdate, DesktopCommandPort, RunnerTestResult,
    SharedApplicationBoundary, SidebarEnvironmentProjector, SidebarIntentProjector,
    SidebarRefreshProjector, WorkspaceProjector,
)
from .dispatch import AuthorityDispatcher, FailureHandler
from .session_boundary import PlanningSessionApplicationBoundary
from .projector import SharedApplicationProjector
from .console_projection import _terminal_console_update
from .desktop import BenchmarkDesktopApplication, PYSIDE6_AVAILABLE

__all__ = [
    "ApplicationEnvironmentProjection", "ApplicationProjectionUpdate",
    "ApplicationProjector", "ApplicationRequestResolver", "AuthorityDispatcher",
    "BenchmarkDesktopApplication", "ConsoleProjectionUpdate", "DesktopCommandPort",
    "FailureHandler", "PlanningSessionApplicationBoundary", "RunnerTestResult",
    "SharedApplicationBoundary", "SharedApplicationProjector",
    "SidebarEnvironmentProjector", "SidebarIntentProjector",
    "SidebarRefreshProjector", "WorkspaceProjector",
]
