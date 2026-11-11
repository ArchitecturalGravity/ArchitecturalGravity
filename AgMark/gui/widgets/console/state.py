"""Presentation-only state for the GUI bottom console.

The state object deliberately accepts already-authorized generation identities and
already-redacted presentation text from callers. It never derives lifecycle,
evidence, report, verification authority from visible console content.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import MutableMapping


CONSOLE_TABS = ("Live View", "Diagnostics", "Environment", "History")
RAW_RESPONSE_UNAVAILABLE = "Raw response unavailable."
LAST_EXPANDED_HEIGHT_KEY = "console/last_nonzero_expanded_height"


def _require_generation_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("generation_id must be a non-empty string")
    return value


def _require_tab(value: str) -> str:
    # Restore preferences written before the two inspection views were merged.
    value = {"Live Output": "Live View", "Raw Response": "Live View"}.get(value, value)
    if value not in CONSOLE_TABS:
        raise ValueError(f"unknown console tab: {value!r}")
    return value


def _require_invocation_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("invocation_id must be a non-empty string")
    return value


def _require_height(value: int, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("console height must be an integer")
    minimum = 0 if allow_zero else 1
    if value < minimum:
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"console height must be {qualifier}")
    return value


@dataclass(frozen=True, slots=True)
class ConsoleSnapshot:
    """Read-only presentation snapshot for rendering and frontend tests."""

    active_generation_id: str | None
    active_tab: str
    expanded: bool
    last_nonzero_expanded_height: int
    visible_text: str
    raw_response_available: bool
    authority_semantics: str = "presentation-only"


class BottomConsoleState:
    """Own local console presentation state without owning benchmark authority."""

    def __init__(
        self,
        *,
        preferences: MutableMapping[str, int] | None = None,
        default_expanded_height: int = 260,
    ) -> None:
        default_height = _require_height(default_expanded_height)
        self._preferences = preferences
        stored_height: object = (
            preferences.get(LAST_EXPANDED_HEIGHT_KEY) if preferences is not None else None
        )
        if (
            isinstance(stored_height, int)
            and not isinstance(stored_height, bool)
            and stored_height > 0
        ):
            self._last_nonzero_expanded_height = stored_height
        else:
            self._last_nonzero_expanded_height = default_height

        self._active_generation_id: str | None = None
        self._active_tab = CONSOLE_TABS[0]
        self._expanded = False
        self._buffers = {
            "Diagnostics": "",
            "Environment": "",
            "History": "",
        }
        self._invocations: dict[str, tuple[str | None, str | None]] = {}
        self._visible_invocations: set[str] = set()
        self._treatments: dict[str, str] = {}
        self._show_input = True
        self._show_output = True
        self._raw_response: str | None = None
        self._raw_response_available = False

    @property
    def active_generation_id(self) -> str | None:
        return self._active_generation_id

    @property
    def active_tab(self) -> str:
        return self._active_tab

    @property
    def expanded(self) -> bool:
        return self._expanded

    @property
    def last_nonzero_expanded_height(self) -> int:
        return self._last_nonzero_expanded_height

    @property
    def raw_response_available(self) -> bool:
        return self._raw_response_available

    @property
    def retained_raw_response(self) -> str | None:
        """Return the exact caller-supplied retained response projection, if available."""

        return self._raw_response if self._raw_response_available else None

    @property
    def visible_text(self) -> str:
        if self._active_tab == "Live View":
            sections = []
            for invocation, (input_text, output_text) in self._invocations.items():
                if invocation not in self._visible_invocations:
                    continue
                treatment = self._treatments.get(invocation)
                prefix = f"{treatment} - " if treatment else ""
                if self._show_input:
                    sections.append(prefix + "Input:\n" + (
                        "Input unavailable." if input_text is None else input_text))
                if self._show_output:
                    sections.append(prefix + "Output:\n" + (
                        "Output unavailable." if input_text is None and output_text is None
                        else (output_text or "")))
            return "\n\n".join(sections)
        return self._buffers[self._active_tab]

    def set_live_view_channels(self, *, input_enabled: bool, output_enabled: bool) -> None:
        """Filter presentation without modifying the retained snapshots."""
        self._show_input = input_enabled
        self._show_output = output_enabled

    def bind_generation(self, generation_id: str) -> None:
        """Bind the console to an explicit active generation supplied by the caller."""

        generation = _require_generation_id(generation_id)
        if generation == self._active_generation_id:
            return

        self._active_generation_id = generation
        self._invocations.clear()
        self._treatments.clear()
        self._visible_invocations.clear()
        self._buffers["Diagnostics"] = ""
        self._raw_response = None
        self._raw_response_available = False

    def detach_generation(self, generation_id: str) -> bool:
        """Discard only an abandoned presentation generation, retaining Environment."""
        if self._active_generation_id != _require_generation_id(generation_id):
            return False
        self._active_generation_id = None
        self._invocations.clear()
        self._treatments.clear()
        self._visible_invocations.clear()
        self._buffers["Diagnostics"] = ""
        self._raw_response = None
        self._raw_response_available = False
        return True

    def set_live_view(
        self,
        generation_id: str,
        invocation_id: str,
        input_text: str | None = None,
        output_text: str | None = None,
        treatment_name: str | None = None,
    ) -> bool:
        """Replace supplied invocation snapshots, without parsing or rewriting text.

        None means unchanged; an empty string is a valid snapshot. Invocation order
        is first-observed order, so concurrent response updates cannot interleave.
        """

        generation = _require_generation_id(generation_id)
        invocation = _require_invocation_id(invocation_id)
        if input_text is not None and not isinstance(input_text, str):
            raise TypeError("input_text must be a string or None")
        if output_text is not None and not isinstance(output_text, str):
            raise TypeError("output_text must be a string or None")
        if generation != self._active_generation_id:
            return False
        previous_input, previous_output = self._invocations.get(invocation, (None, None))
        self._invocations[invocation] = (
            previous_input if input_text is None else input_text,
            previous_output if output_text is None else output_text,
        )
        if treatment_name is not None:
            self._treatments[invocation] = treatment_name
        self._visible_invocations.add(invocation)
        return True

    def append_live_output(self, generation_id: str, text: str) -> bool:
        """Compatibility route: execution/progress logs now belong to Diagnostics."""

        return self.append_diagnostic(generation_id, text)

    def append_diagnostic(self, generation_id: str, text: str) -> bool:
        return self._append_generation_bound("Diagnostics", generation_id, text)

    def set_environment(self, text: str) -> None:
        """Replace the application/session Environment presentation snapshot."""

        if not isinstance(text, str):
            raise TypeError("console text must be a string")
        self._buffers["Environment"] = text

    def append_history(self, text: str) -> None:
        """Retain every status emission for this session, across run changes."""
        if not isinstance(text, str):
            raise TypeError("console text must be a string")
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        self._buffers["History"] += f"[{timestamp}] {text}\n"

    def _append_generation_bound(
        self,
        tab: str,
        generation_id: str,
        text: str,
    ) -> bool:
        generation = _require_generation_id(generation_id)
        if not isinstance(text, str):
            raise TypeError("console text must be a string")
        if generation != self._active_generation_id:
            return False
        self._buffers[tab] += text
        return True

    def set_raw_response(self, generation_id: str, response: str | None) -> bool:
        """Project an exact retained response, or None for explicit unavailability."""

        generation = _require_generation_id(generation_id)
        if response is not None and not isinstance(response, str):
            raise TypeError("raw response must be a string or None")
        if generation != self._active_generation_id:
            return False

        self._raw_response = response
        self._raw_response_available = response is not None
        # Legacy callers have no invocation identity or prompt. Keep their exact
        # response in one replaceable section, never append it to streaming output.
        if response is not None:
            self.set_live_view(generation, "legacy-response", output_text=response)
        else:
            self._invocations.pop("legacy-response", None)
            self._visible_invocations.discard("legacy-response")
        return True

    def select_tab(self, tab: str) -> None:
        self._active_tab = _require_tab(tab)

    def clear_visible(self) -> None:
        """Clear only the local presentation buffer for the currently visible view."""

        if self._active_tab == "History":
            return  # Session history is complete until the application closes.
        elif self._active_tab == "Live View":
            self._visible_invocations.clear()
        else:
            self._buffers[self._active_tab] = ""

    def collapse(self) -> None:
        self._expanded = False

    def expand(self) -> int:
        self._expanded = True
        return self._last_nonzero_expanded_height

    def resize(self, height: int) -> None:
        """Apply presentation-only user resizing and persist only positive height."""

        value = _require_height(height, allow_zero=True)
        if value == 0:
            self.collapse()
            return

        self._last_nonzero_expanded_height = value
        self._expanded = True
        if self._preferences is not None:
            self._preferences[LAST_EXPANDED_HEIGHT_KEY] = value

    def snapshot(self) -> ConsoleSnapshot:
        return ConsoleSnapshot(
            active_generation_id=self._active_generation_id,
            active_tab=self._active_tab,
            expanded=self._expanded,
            last_nonzero_expanded_height=self._last_nonzero_expanded_height,
            visible_text=self.visible_text,
            raw_response_available=self._raw_response_available,
        )


__all__ = [
    "BottomConsoleState",
    "CONSOLE_TABS",
    "ConsoleSnapshot",
    "LAST_EXPANDED_HEIGHT_KEY",
    "RAW_RESPONSE_UNAVAILABLE",
]
