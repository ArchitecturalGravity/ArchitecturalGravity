"""Selection-scoped diagnostic consent, isolated from asynchronous UI refreshes."""

from AgMark.shared.telemetry.profile import DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT
from threading import Event

from .diagnostic_consent import (
    DiagnosticConsentDialog, DiagnosticConsentPreferences, DiagnosticConsentRequired,
    DiagnosticExecutionGrant, consent_identity, consent_key,
)


class DiagnosticConsentController:
    def _begin_diagnostic_sidebar(self, projection) -> None:
        self._diagnostic_generation = getattr(self, "_diagnostic_generation", 0) + 1
        self._dismiss_diagnostic_dialog()
        if not hasattr(self, "_diagnostic_preferences"):
            self._diagnostic_preferences = DiagnosticConsentPreferences(self._shell_preferences)
            self._diagnostic_selection_key = None
            self._diagnostic_selection_revoked = Event()
            self._diagnostic_selection_revoked.set()
            self._diagnostic_window_closed = Event()
            self._diagnostic_runner = None
        if self._diagnostic_runner != projection.selected_runner:
            self._clear_diagnostic_selection()
        self._diagnostic_runner = projection.selected_runner

    def _clear_diagnostic_selection(self) -> None:
        self._diagnostic_selection_key = None
        self._diagnostic_selection_revoked.set()

    def _grant_diagnostic_selection(self, identity) -> None:
        key = consent_key(identity)
        if self._diagnostic_selection_key != key or self._diagnostic_selection_revoked.is_set():
            self._clear_diagnostic_selection()
            self._diagnostic_selection_revoked = Event()
        self._diagnostic_selection_key = key

    def diagnostic_execution_grant(self, runner, acknowledgement):
        """Resolve the operation's identity on the GUI thread, never sidebar authority."""
        identity = consent_identity(runner)
        if identity is None or acknowledgement != DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT:
            raise DiagnosticConsentRequired()
        key = consent_key(identity)
        remembered = self._diagnostic_preferences.remembers(identity)
        if not remembered and self._diagnostic_selection_key != key:
            raise DiagnosticConsentRequired()
        grant = DiagnosticExecutionGrant(runner, key, self._diagnostic_window_closed,
            None if remembered else self._diagnostic_selection_revoked)
        grant.require_valid()
        return grant

    def show_diagnostic_consent_required(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        self.set_application_status("Diagnostic consent required; operation not started", "error")
        if self._diagnostic_window_closed.is_set():
            return
        existing = getattr(self, "_diagnostic_dispatch_notice", None)
        if existing is not None:
            existing.raise_()
            return
        notice = QMessageBox(QMessageBox.Icon.Information, "Diagnostic consent required",
            str(DiagnosticConsentRequired()), QMessageBox.StandardButton.Ok, self)
        notice.setObjectName("diagnosticConsentRequired")
        self._diagnostic_dispatch_notice = notice
        def finished(_result):
            if self._diagnostic_dispatch_notice is notice:
                self._diagnostic_dispatch_notice = None
            notice.deleteLater()
        notice.finished.connect(finished)
        notice.open()

    def _dismiss_diagnostic_dialog(self) -> None:
        dialog = getattr(self, "_diagnostic_dialog", None)
        self._diagnostic_dialog = None
        if dialog is not None:
            dialog.reject()

    @staticmethod
    def _set_diagnostic_control(control, value) -> None:
        previous = control.combo_box.blockSignals(True)
        try:
            control.set_value(value)
        finally:
            control.combo_box.blockSignals(previous)

    def _diagnostic_identity(self):
        return consent_identity(self.runner_input.value)

    def _diagnostic_is_accepted(self) -> bool:
        identity = self._diagnostic_identity()
        return (identity is not None and self._diagnostic_selection_key == consent_key(identity)
                and not self._diagnostic_selection_revoked.is_set())

    def _initialize_diagnostic_controls(self) -> None:
        profile = self.additional_control_inputs.get("capture_mode")
        acknowledgement = self.additional_control_inputs.get("diagnostic_privacy_acknowledged")
        if acknowledgement is not None:
            self._set_diagnostic_control(acknowledgement, "not_acknowledged")
        if profile is None:
            self._clear_diagnostic_selection()
            return
        identity = self._diagnostic_identity()
        if profile.value == "deep_telemetry":
            if (acknowledgement is not None
                    and DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT in acknowledgement.options
                    and identity is not None and (
                self._diagnostic_is_accepted() or self._diagnostic_preferences.remembers(identity)
            )):
                self._grant_diagnostic_selection(identity)
                self._set_diagnostic_control(acknowledgement, DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT)
            else:
                self._set_diagnostic_control(profile, self._diagnostic_safe_profile(profile))
                self._clear_diagnostic_selection()
        else:
            self._clear_diagnostic_selection()
        self._diagnostic_last_profile = profile.value
        generation = self._diagnostic_generation
        profile.combo_box.currentIndexChanged.connect(
            lambda _index, control=profile, generation=generation:
                self._diagnostic_profile_changed(control, generation)
        )

    @staticmethod
    def _diagnostic_safe_profile(profile):
        return next((value for value in ("telemetry", "session")
                     if value in profile.options), None)

    def _diagnostic_profile_changed(self, profile, generation) -> None:
        if generation != self._diagnostic_generation or profile is not self.additional_control_inputs.get("capture_mode"):
            return
        acknowledgement = self.additional_control_inputs.get("diagnostic_privacy_acknowledged")
        if profile.value != "deep_telemetry":
            self._dismiss_diagnostic_dialog()
            self._clear_diagnostic_selection()
            self._diagnostic_last_profile = profile.value
            if acknowledgement is not None:
                self._set_diagnostic_control(acknowledgement, "not_acknowledged")
            self._refresh_build_plan_availability()
            self._handle_sidebar_intent_changed()
            return
        fallback = getattr(self, "_diagnostic_last_profile", None)
        if fallback == "deep_telemetry" or fallback not in profile.options:
            fallback = self._diagnostic_safe_profile(profile)
        # Pending consent never appears in a readiness or plan snapshot.
        self._set_diagnostic_control(profile, fallback)
        identity = self._diagnostic_identity()
        if (acknowledgement is None
                or DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT not in acknowledgement.options
                or identity is None or not profile.isEnabled()
                or getattr(self, "_operation_locks_controls", False)):
            return
        if self._diagnostic_preferences.remembers(identity):
            self._accept_diagnostic_selection(profile, acknowledgement, identity)
            return
        if getattr(self, "_diagnostic_dialog", None) is not None:
            return
        dialog = DiagnosticConsentDialog(runner=identity["runner"], parent=self)
        self._diagnostic_dialog = dialog

        def finished(result):
            current = self._diagnostic_dialog is dialog
            if current:
                self._diagnostic_dialog = None
            if (current and result == dialog.DialogCode.Accepted
                    and generation == self._diagnostic_generation
                    and profile is self.additional_control_inputs.get("capture_mode")
                    and identity == self._diagnostic_identity()
                    and profile.isEnabled()
                    and not getattr(self, "_operation_locks_controls", False)):
                if dialog.save_decision.isChecked():
                    self._diagnostic_preferences.remember(identity)
                self._accept_diagnostic_selection(profile, acknowledgement, identity)
            dialog.deleteLater()

        dialog.finished.connect(finished)
        dialog.open()

    def _accept_diagnostic_selection(self, profile, acknowledgement, identity) -> None:
        self._grant_diagnostic_selection(identity)
        self._diagnostic_last_profile = "deep_telemetry"
        self._set_diagnostic_control(acknowledgement, DIAGNOSTIC_CONSENT_ACKNOWLEDGEMENT)
        self._set_diagnostic_control(profile, "deep_telemetry")
        self._refresh_build_plan_availability()
        self._handle_sidebar_intent_changed()

    def _diagnostic_runner_changed(self) -> None:
        if getattr(self, "_diagnostic_runner", None) == self.runner_input.value:
            return
        self._dismiss_diagnostic_dialog()
        self._clear_diagnostic_selection()
        self._diagnostic_runner = self.runner_input.value
        profile = self.additional_control_inputs.get("capture_mode")
        acknowledgement = self.additional_control_inputs.get("diagnostic_privacy_acknowledged")
        if profile is not None and profile.value == "deep_telemetry":
            self._set_diagnostic_control(profile, self._diagnostic_safe_profile(profile))
        if profile is not None:
            self._diagnostic_last_profile = profile.value
        if acknowledgement is not None:
            self._set_diagnostic_control(acknowledgement, "not_acknowledged")
        self._refresh_build_plan_availability()
