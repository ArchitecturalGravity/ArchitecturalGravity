"""Versioned UI consent preferences and an explicit stock-diagnostics dialog.

Remembering a decision is a desktop preference, never benchmark configuration.
The registered acknowledgement control still carries each actual consent into
planning, execution and retained provenance.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import MutableMapping
from dataclasses import dataclass
from threading import Event

from AgMark.shared.telemetry.profile import (
    DIAGNOSTIC_CONSENT_SCOPE,
    DIAGNOSTIC_CONSENT_VERSION,
)


def consent_identity(runner: str | None) -> dict[str, str] | None:
    if not runner:
        return None
    return {
        "scope": DIAGNOSTIC_CONSENT_SCOPE,
        "version": DIAGNOSTIC_CONSENT_VERSION,
        "profile": "deep_telemetry",
        "runner": runner,
        "decision": "accepted",
    }


def consent_key(identity: dict[str, str]) -> str:
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return "privacy/diagnostic_consent/" + digest


class DiagnosticConsentRequired(RuntimeError):
    """Safe, explicit refusal before an operation starts sensitive capture."""

    def __init__(self) -> None:
        super().__init__(
            "This operation uses Deep Telemetry and requires a current consent grant. "
            "Select Deep Telemetry for the operation's runner and accept the disclosure, "
            "or build and accept a plan with a different Capture Mode. "
            "An accepted plan does not preserve unsaved consent after you leave that selection."
        )


@dataclass(frozen=True)
class DiagnosticExecutionGrant:
    """A worker-safe grant: no widget or preference access after admission."""

    runner: str
    identity_key: str
    window_closed: Event
    selection_revoked: Event | None

    def require_valid(self) -> None:
        identity = consent_identity(self.runner)
        if (self.window_closed.is_set() or identity is None
                or self.identity_key != consent_key(identity)
                or (self.selection_revoked is not None and self.selection_revoked.is_set())):
            raise DiagnosticConsentRequired()


class DiagnosticConsentPreferences:
    """Strict affirmative records in an injected mapping or native UI settings."""

    def __init__(self, preferences: MutableMapping[str, object] | None) -> None:
        self._preferences = preferences
        self._settings = None
        if preferences is None:
            from PySide6.QtCore import QSettings
            self._settings = QSettings("ArchitecturalGravity", "AgMark")

    def remembers(self, identity: dict[str, str] | None) -> bool:
        if identity is None:
            return False
        key = consent_key(identity)
        value = (self._preferences.get(key) if self._preferences is not None
                 else self._settings.value(key))
        try:
            return isinstance(value, str) and json.loads(value) == identity
        except (ValueError, TypeError):
            return False

    def remember(self, identity: dict[str, str]) -> bool:
        key, value = consent_key(identity), json.dumps(identity, sort_keys=True)
        try:
            if self._preferences is not None:
                self._preferences[key] = value
            else:
                self._settings.setValue(key, value)
                self._settings.sync()
                return self._settings.status() == self._settings.Status.NoError
        except (OSError, TypeError, ValueError):
            return False
        return True


try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox, QDialog, QDialogButtonBox, QLabel, QScrollArea, QVBoxLayout, QWidget,
    )
except ImportError:
    DiagnosticConsentDialog = None
else:
    class DiagnosticConsentDialog(QDialog):
        """Window-modal disclosure; only the explicit affirmative button accepts."""

        def __init__(self, *, runner: str, parent: QWidget) -> None:
            super().__init__(parent)
            self.setObjectName("diagnosticConsentDialog")
            self.setWindowTitle("Allow sensitive diagnostics?")
            self.setWindowModality(Qt.WindowModality.WindowModal)
            self.setModal(True)
            self.resize(620, 530)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(24, 20, 24, 20)
            layout.setSpacing(14)
            title = QLabel("Allow sensitive diagnostics?", self)
            title.setStyleSheet("font-size: 20px; font-weight: 600")
            layout.addWidget(title)
            scroll = QScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            content = QWidget(scroll)
            body = QVBoxLayout(content)
            body.setContentsMargins(0, 0, 10, 0)
            body.setSpacing(14)
            paragraphs = (
                "Deep Telemetry lets stock Codex write raw prompts, responses, tool output, "
                "file and terminal content, and subagent activity to a private temporary "
                "directory on the selected execution host (inside WSL when WSL is selected). "
                "Payload text may contain secrets. This storage has no encryption guarantee.",
                "AgMark invokes the stock local trace reducer, then retains sanitized structural "
                "events, metadata and links as run evidence. Raw payload text and credential/header "
                "fields are excluded from that retained evidence. Sensitive content can exist in "
                "the raw and reduced temporary files before sanitization.",
                "AgMark normally deletes this temporary storage after collection, including "
                "failure or cancellation. Cleanup is best-effort: an abrupt exit, crash or cleanup "
                "failure can leave sensitive files on the execution host. No external telemetry "
                "collector is used by AgMark.",
                "Diagnostics add local I/O and reduction overhead and an inference-call header "
                "to stock provider requests. They do not provide exact wire latency, individual "
                "token arrival times or complete WebSocket warmup coverage.",
                "Without saving, this acceptance lasts only for the current diagnostic selection "
                "in this window. Selecting another Capture Mode or runner ends it. A saved decision "
                "applies to this runner and this consent version across restarts; a changed "
                "capture scope or consent version requires a new decision.",
            )
            for index, text in enumerate(paragraphs):
                label = QLabel(text, content)
                label.setObjectName(f"diagnosticDisclosure{index}")
                label.setWordWrap(True)
                label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                body.addWidget(label)
            scope = QLabel(f"Runner: {runner}\nConsent: {DIAGNOSTIC_CONSENT_SCOPE} · "
                           f"{DIAGNOSTIC_CONSENT_VERSION}", content)
            scope.setWordWrap(True)
            scope.setObjectName("diagnosticConsentScope")
            body.addWidget(scope)
            body.addStretch(1)
            scroll.setWidget(content)
            layout.addWidget(scroll, 1)
            self.save_decision = QCheckBox("Save this decision for future use", self)
            self.save_decision.setObjectName("saveDiagnosticConsent")
            self.save_decision.setChecked(False)
            layout.addWidget(self.save_decision)
            self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
            self.accept_button = self.buttons.addButton(
                "Enable Deep Telemetry", QDialogButtonBox.ButtonRole.AcceptRole)
            self.accept_button.setObjectName("enableDiagnostics")
            self.accept_button.setAutoDefault(False)
            self.accept_button.setDefault(False)
            self.cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
            self.cancel_button.setDefault(True)
            self.cancel_button.setFocus()
            self.buttons.accepted.connect(self.accept)
            self.buttons.rejected.connect(self.reject)
            layout.addWidget(self.buttons)
