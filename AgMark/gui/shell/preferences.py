"""Presentation-only shell preference decoding."""

from __future__ import annotations

from collections.abc import MutableMapping

from AgMark.gui.widgets.console import CONSOLE_TABS
from .projections import WORKSPACE_TAB_LABELS

def _stored_positive_int(
    preferences: MutableMapping[str, object] | None,
    key: str,
    default: int,
) -> int:
    if preferences is None:
        return default
    value = preferences.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return default


def _stored_tab_index(
    preferences: MutableMapping[str, object] | None,
    key: str,
    default: int = 0,
) -> int:
    if preferences is None:
        return default
    value = preferences.get(key)
    if value in ("Capture", "Artifacts"):
        value = "Evidence"
    if isinstance(value, str) and value in WORKSPACE_TAB_LABELS:
        return WORKSPACE_TAB_LABELS.index(value)
    # Integer preferences predate the amended order; decode by old tab meaning.
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 5:
        legacy = ("Progress", "Results", "Reports", "Verification", "Artifacts")
        label = legacy[value]
        return WORKSPACE_TAB_LABELS.index("Evidence" if label == "Artifacts" else label)
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 0 <= value < len(WORKSPACE_TAB_LABELS)
    ):
        return value
    return default


def _stored_bool(
    preferences: MutableMapping[str, object] | None,
    key: str,
    default: bool,
) -> bool:
    if preferences is None:
        return default
    value = preferences.get(key)
    return value if isinstance(value, bool) else default


def _stored_console_tab(
    preferences: MutableMapping[str, object] | None,
    key: str,
    default: str,
) -> str:
    if preferences is None:
        return default
    value = preferences.get(key)
    return value if isinstance(value, str) and value in CONSOLE_TABS else default
