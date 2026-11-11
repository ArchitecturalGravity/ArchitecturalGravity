"""Concrete Verification workspace view for the ArcGrav desktop GUI.

The view is a projection client. It renders caller-supplied retained
verification state and invokes only caller-supplied operations whose
availability has already been established by shared/GUI authority. Visible
success styling, matching labels, report/artifact presence, and local widget
state never create verification results.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from math import ceil

from AgMark.gui.design_system.status import DEFAULT_STATUS_STYLES
from AgMark.gui.widgets.containers import CardWidget
from AgMark.gui.widgets.status import PYSIDE6_AVAILABLE


VERIFICATION_CHECK_LABELS = (
    "Manifest Integrity",
    "Artifact Hashes",
    "Boundary Match",
    "Reconstruction Match",
)

VERIFICATION_SUMMARY_FIELDS = (
    ("manifest_id", "Manifest ID:"),
    ("verification_time", "Verification Time:"),
    ("result", "Result:"),
    ("verified_by", "Verified By:"),
    ("artifacts_checked", "Artifacts Checked:"),
    ("total_size", "Total Size:"),
    ("boundary_fingerprint", "Boundary Fingerprint:"),
    ("notes", "Notes:"),
)

_VERIFICATION_STATUSES = frozenset(
    {"failed", "mismatched", "unavailable", "incomplete", "verified", "passed"}
)


def _require_visible_text(value: str, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty visible string")
    return value


def _optional_visible_text(value: str | None, *, name: str) -> str | None:
    if value is None:
        return None
    return _require_visible_text(value, name=name)


def _require_bool(value: bool, *, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _require_tone(value: str, *, name: str) -> str:
    value = _require_visible_text(value, name=name)
    try:
        DEFAULT_STATUS_STYLES.style(value)
    except KeyError as exc:
        raise ValueError(f"{name} must be a registered semantic status tone") from exc
    return value


@dataclass(frozen=True, slots=True)
class VerificationBannerProjection:
    """Caller-supplied overall verification presentation."""

    status: str
    icon: str
    heading: str
    summary: str | None
    tone: str

    def __post_init__(self) -> None:
        status = _require_visible_text(self.status, name="status")
        if status not in _VERIFICATION_STATUSES:
            raise ValueError("status must be a published verification status")
        _require_visible_text(self.icon, name="icon")
        heading = _require_visible_text(self.heading, name="heading")
        _optional_visible_text(self.summary, name="summary")
        tone = _require_tone(self.tone, name="tone")

        if status == "verified":
            if heading != "Verified" or tone != "success":
                raise ValueError(
                    "verified status requires the exact Verified heading and success tone"
                )
        elif status == "passed":
            if heading != "Completion validation passed" or tone != "success":
                raise ValueError("passed completion requires its explicit heading and success tone")
        elif heading == "Verified" or tone == "success":
            raise ValueError(
                "non-verified status cannot use the Verified heading or success tone"
            )


@dataclass(frozen=True, slots=True)
class VerificationCheckProjection:
    """One caller-supplied shared verification check row."""

    check_id: str
    label: str
    result: str
    icon: str
    tone: str
    details: str
    expanded: bool = False

    def __post_init__(self) -> None:
        _require_visible_text(self.check_id, name="check_id")
        _require_visible_text(self.label, name="label")
        _require_visible_text(self.result, name="result")
        _require_visible_text(self.icon, name="icon")
        _require_tone(self.tone, name="tone")
        _require_visible_text(self.details, name="details")
        _require_bool(self.expanded, name="expanded")


@dataclass(frozen=True, slots=True)
class VerificationSummaryProjection:
    """Caller-supplied values for the normative verification summary card."""

    manifest_id: str
    verification_time: str
    result: str
    verified_by: str
    artifacts_checked: str
    total_size: str
    boundary_fingerprint: str
    notes: str | None

    def __post_init__(self) -> None:
        for field_name, _ in VERIFICATION_SUMMARY_FIELDS:
            if field_name == "notes":
                _optional_visible_text(self.notes, name="notes")
            else:
                _require_visible_text(getattr(self, field_name), name=field_name)


@dataclass(frozen=True, slots=True)
class VerificationProjection:
    """Exact retained-run verification projection supplied by GUI/shared boundaries."""

    run_id: str
    banner: VerificationBannerProjection
    summary: VerificationSummaryProjection
    checks: Sequence[VerificationCheckProjection] = ()
    checks_empty_state: str | None = None

    def __post_init__(self) -> None:
        _require_visible_text(self.run_id, name="run_id")
        if not isinstance(self.banner, VerificationBannerProjection):
            raise ValueError("banner must be a VerificationBannerProjection")
        if not isinstance(self.summary, VerificationSummaryProjection):
            raise ValueError("summary must be a VerificationSummaryProjection")
        if isinstance(self.checks, (str, bytes)):
            raise ValueError(
                "checks must be a sequence of VerificationCheckProjection values"
            )
        checks = tuple(self.checks)
        if any(not isinstance(check, VerificationCheckProjection) for check in checks):
            raise ValueError(
                "checks must contain only VerificationCheckProjection values"
            )
        check_ids = tuple(check.check_id for check in checks)
        if len(set(check_ids)) != len(check_ids):
            raise ValueError("check_id values must be unique within a projection")

        known_positions = {
            label: index for index, label in enumerate(VERIFICATION_CHECK_LABELS)
        }
        encountered = [
            known_positions[check.label]
            for check in checks
            if check.label in known_positions
        ]
        if encountered != sorted(encountered):
            raise ValueError(
                "default verification checks must preserve specification order"
            )

        empty_state = _optional_visible_text(
            self.checks_empty_state,
            name="checks_empty_state",
        )
        if not checks and empty_state is None and self.banner.status != "passed":
            raise ValueError(
                "empty Verification projections require an explicit "
                "caller-supplied checks_empty_state"
            )

        object.__setattr__(self, "checks", checks)


try:
    if not PYSIDE6_AVAILABLE:
        raise ImportError
    from PySide6.QtCore import QThread, Qt, Signal, QSize
    from PySide6.QtGui import QTextOption
    from PySide6.QtWidgets import (
        QBoxLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QToolButton,
        QTextEdit,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    PYSIDE6_AVAILABLE = False
else:
    PYSIDE6_AVAILABLE = True


if PYSIDE6_AVAILABLE:
    from AgMark.gui.widgets.responsive import ResponsiveView, apply_minimum, wrap_text

    class _ContentWidget(QWidget):
        """Calculate height at the assigned width, never at a zero-width floor."""

        def minimumSizeHint(self):
            return QSize(0, 0)


    class _SummaryValue(QTextEdit):
        """Selectable plain text that wraps even an uninterrupted fingerprint."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setReadOnly(True)
            self.setFrameShape(QFrame.Shape.NoFrame)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            self.document().setDocumentMargin(0)
            self.setStyleSheet("background: transparent; border: 0; padding: 0;")
            policy = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
            policy.setHeightForWidth(True)
            self.setSizePolicy(policy)

        def text(self):
            return self.toPlainText()

        def setText(self, text):
            self.setPlainText(text)
            self.updateGeometry()

        def heightForWidth(self, width):
            document = self.document().clone()
            document.setTextWidth(max(1, width))
            height = ceil(document.size().height())
            return height

        def sizeHint(self):
            return QSize(200, self.heightForWidth(200))

        def minimumSizeHint(self):
            return QSize(0, self.fontMetrics().height())


    class VerificationView(ResponsiveView):
        """Normative verification inspection surface with caller-owned authority."""

        projectionRequested = Signal(object)
        minimum_viewport_width = 0

        def __init__(
            self,
            projection: VerificationProjection,
            *,
            parent: QWidget | None = None,
        ) -> None:
            if not isinstance(projection, VerificationProjection):
                raise ValueError("projection must be a VerificationProjection")
            super().__init__(parent)

            self.setObjectName("verificationWorkspaceView")
            self.setAccessibleName("Verification workspace")
            self.setProperty("authoritySemantics", "presentation-only")

            layout = QHBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            self.add_responsive_layout(layout, 850)

            status_content = _ContentWidget(self)
            status_layout = QVBoxLayout(status_content)
            status_layout.setContentsMargins(0, 0, 0, 0)
            status_layout.setSpacing(8)

            self.banner_frame = QFrame(status_content)
            self.banner_frame.setObjectName("verificationBanner")
            self.banner_frame.setProperty("authoritySemantics", "presentation-only")
            banner_layout = QHBoxLayout(self.banner_frame)
            banner_layout.setContentsMargins(12, 12, 12, 12)
            banner_layout.setSpacing(10)

            self.banner_icon_label = QLabel(self.banner_frame)
            self.banner_icon_label.setObjectName("verificationBannerIcon")
            self.banner_icon_label.setAccessibleName("Verification status cue")
            self.banner_icon_label.setMinimumWidth(24)
            banner_layout.addWidget(self.banner_icon_label)

            banner_text = QWidget(self.banner_frame)
            banner_text_layout = QVBoxLayout(banner_text)
            banner_text_layout.setContentsMargins(0, 0, 0, 0)
            banner_text_layout.setSpacing(2)

            self.banner_heading_label = QLabel(banner_text)
            self.banner_heading_label.setObjectName("verificationBannerHeading")
            wrap_text(self.banner_heading_label)
            banner_text_layout.addWidget(self.banner_heading_label)

            self.banner_summary_label = QLabel(banner_text)
            self.banner_summary_label.setObjectName("verificationBannerSummary")
            self.banner_summary_label.setWordWrap(True)
            banner_text_layout.addWidget(self.banner_summary_label)

            banner_layout.addWidget(banner_text, 1)
            apply_minimum(self.banner_frame, 0, 72, False)
            wrap_text(self.banner_summary_label)
            status_layout.addWidget(self.banner_frame)

            self.checks_empty_state_label = QLabel(status_content)
            self.checks_empty_state_label.setObjectName("verificationChecksEmptyState")
            self.checks_empty_state_label.setAccessibleName(
                "Verification check availability"
            )
            self.checks_empty_state_label.setWordWrap(True)
            apply_minimum(self.checks_empty_state_label, 0, 64, False)
            wrap_text(self.checks_empty_state_label)
            status_layout.addWidget(self.checks_empty_state_label)

            self.checks_holder = QWidget(status_content)
            self.checks_holder.setObjectName("verificationChecks")
            self._checks_layout = QVBoxLayout(self.checks_holder)
            self._checks_layout.setContentsMargins(0, 0, 0, 0)
            self._checks_layout.setSpacing(6)
            status_layout.addWidget(self.checks_holder)
            status_layout.addStretch(1)

            self.status_card = CardWidget(
                "Verification Status",
                status_content,
                compact=True, parent=self,
            )
            apply_minimum(self.status_card, 0, 0)
            layout.addWidget(self.status_card, 3)

            summary_content = _ContentWidget(self)
            summary_layout = QVBoxLayout(summary_content)
            summary_layout.setContentsMargins(0, 0, 0, 0)
            summary_layout.setSpacing(2)

            self._summary_row_layouts = []
            self._summary_value_labels: dict[str, _SummaryValue] = {}
            self._summary_label_widgets: list[QLabel] = []
            for field_name, label_text in VERIFICATION_SUMMARY_FIELDS:
                row = _ContentWidget(summary_content)
                row.setObjectName(f"verificationSummaryRow_{field_name}")
                # Let text determine row height instead of reserving a blank line.
                # Height-for-width still grows rows for wrapped values.
                apply_minimum(row, 0, 0, False)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(8)

                label = QLabel(label_text, row)
                label.setObjectName(f"verificationSummaryLabel_{field_name}")
                label.setAccessibleName(label_text)
                label.setWordWrap(True)
                row_layout.addWidget(label)

                value = _SummaryValue(row)
                value.setObjectName(f"verificationSummaryValue_{field_name}")
                value.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByKeyboard
                    | Qt.TextInteractionFlag.TextSelectableByMouse
                )
                value.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                row_layout.addWidget(value, 1)

                self._summary_row_layouts.append(row_layout)
                summary_layout.addWidget(row)
                self._summary_label_widgets.append(label)
                self._summary_value_labels[field_name] = value

            summary_layout.addStretch(1)

            self.summary_card = CardWidget(
                "Verification Summary",
                summary_content,
                compact=True, parent=self,
            )
            apply_minimum(self.summary_card, 0, 0)
            layout.addWidget(self.summary_card, 2)

            self._projection = projection
            self._check_holders: list[QWidget] = []
            self._check_disclosure_buttons: dict[str, QToolButton] = {}
            self._check_details_labels: dict[str, QLabel] = {}
            self._check_result_labels: dict[str, QLabel] = {}

            self.projectionRequested.connect(
                self._apply_projection,
                Qt.ConnectionType.QueuedConnection,
            )
            self._apply_projection(projection)

        def set_available_width(self, width):
            # In two-column mode the summary receives two fifths of the page.
            # Reflow its fields using that local width, not the window width.
            summary_width = width if width < 850 else (width - 8) * 2 / 5
            direction = (QBoxLayout.Direction.TopToBottom if summary_width < 440
                         else QBoxLayout.Direction.LeftToRight)
            for row_layout in getattr(self, "_summary_row_layouts", ()):
                row_layout.setDirection(direction)
            super().set_available_width(width)

        @property
        def authority_semantics(self) -> str:
            return "presentation-only"

        @property
        def projection(self) -> VerificationProjection:
            return self._projection

        @property
        def run_id(self) -> str:
            return self._projection.run_id

        @property
        def check_order(self) -> tuple[str, ...]:
            return tuple(check.label for check in self._projection.checks)

        @property
        def summary_labels(self) -> tuple[str, ...]:
            return tuple(label.text() for label in self._summary_label_widgets)

        @property
        def summary_values(self) -> Mapping[str, str | None]:
            return MappingProxyType(
                {
                    field_name: getattr(self._projection.summary, field_name)
                    for field_name, _ in VERIFICATION_SUMMARY_FIELDS
                }
            )

        @property
        def check_disclosure_buttons(self) -> Mapping[str, QToolButton]:
            return MappingProxyType(self._check_disclosure_buttons)

        @property
        def check_details_labels(self) -> Mapping[str, QLabel]:
            return MappingProxyType(self._check_details_labels)

        @property
        def check_result_labels(self) -> Mapping[str, QLabel]:
            return MappingProxyType(self._check_result_labels)

        def set_projection(self, projection: VerificationProjection) -> None:
            """Replace caller-owned verification state on the GUI event thread."""

            if not isinstance(projection, VerificationProjection):
                raise ValueError("projection must be a VerificationProjection")
            if QThread.currentThread() == self.thread():
                self._apply_projection(projection)
                return
            self.projectionRequested.emit(projection)

        def _clear_checks(self) -> None:
            while self._checks_layout.count():
                item = self._checks_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            self._check_holders.clear()
            self._check_disclosure_buttons.clear()
            self._check_details_labels.clear()
            self._check_result_labels.clear()

        def _toggle_details(self, check_id: str, expanded: bool) -> None:
            details = self._check_details_labels.get(check_id)
            button = self._check_disclosure_buttons.get(check_id)
            if details is None or button is None:
                return
            details.setVisible(expanded)
            button.setArrowType(
                Qt.ArrowType.DownArrow
                if expanded
                else Qt.ArrowType.RightArrow
            )
            button.setProperty("expanded", expanded)
            button.setAccessibleDescription(
                "Expanded verification details"
                if expanded
                else "Collapsed verification details"
            )

        def _install_checks(
            self,
            checks: Sequence[VerificationCheckProjection],
        ) -> None:
            for check in checks:
                holder = QFrame(self.checks_holder)
                holder.setObjectName("verificationCheckRow")
                holder.setAccessibleName(check.label)
                holder.setProperty("authoritySemantics", "presentation-only")
                holder_layout = QVBoxLayout(holder)
                holder_layout.setContentsMargins(0, 0, 0, 0)
                holder_layout.setSpacing(4)

                row = QWidget(holder)
                apply_minimum(row, 0, 40, False)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(8)

                icon = QLabel(check.icon, row)
                icon.setObjectName("verificationCheckIcon")
                icon.setAccessibleName(f"{check.label} status cue")
                row_layout.addWidget(icon)

                label = QLabel(check.label, row)
                label.setObjectName("verificationCheckLabel")
                wrap_text(label)
                row_layout.addWidget(label, 1)

                result = QLabel(check.result, row)
                result.setObjectName("verificationCheckResult")
                result.setAccessibleName(f"{check.label} result")
                resolved = DEFAULT_STATUS_STYLES.resolve(
                    check.result,
                    check.tone,
                )
                result.setStyleSheet(
                    f"color: {resolved.foreground}; background: transparent;"
                )
                result.setProperty("semanticTone", check.tone)
                result.setWordWrap(True)
                result.setMinimumWidth(72)
                result.setMaximumWidth(120)
                row_layout.addWidget(result)

                disclosure = QToolButton(row)
                disclosure.setObjectName("verificationCheckDisclosure")
                disclosure.setAccessibleName(f"Details for {check.label}")
                disclosure.setMinimumSize(28, 28)
                disclosure.setCheckable(True)
                disclosure.setChecked(check.expanded)
                disclosure.setAutoRaise(True)
                disclosure.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                row_layout.addWidget(disclosure)

                holder_layout.addWidget(row)

                details = QLabel(check.details, holder)
                details.setObjectName("verificationCheckDetails")
                details.setAccessibleName(f"Details for {check.label}")
                wrap_text(details)
                details.setMinimumHeight(36)
                details.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByKeyboard
                    | Qt.TextInteractionFlag.TextSelectableByMouse
                )
                details.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                holder_layout.addWidget(details)

                self._checks_layout.addWidget(holder)
                self._check_holders.append(holder)
                self._check_disclosure_buttons[check.check_id] = disclosure
                self._check_details_labels[check.check_id] = details
                self._check_result_labels[check.check_id] = result

                disclosure.toggled.connect(
                    lambda expanded, check_id=check.check_id: self._toggle_details(
                        check_id,
                        expanded,
                    )
                )
                self._toggle_details(check.check_id, check.expanded)

        def _apply_banner(self, banner: VerificationBannerProjection) -> None:
            resolved = DEFAULT_STATUS_STYLES.resolve(
                banner.heading,
                banner.tone,
            )
            self.banner_icon_label.setText(banner.icon)
            self.banner_heading_label.setText(banner.heading)
            self.banner_summary_label.setText(banner.summary or "")
            self.banner_summary_label.setVisible(banner.summary is not None)
            self.banner_frame.setProperty("verificationStatus", banner.status)
            self.banner_frame.setProperty("semanticTone", banner.tone)
            self.banner_frame.setAccessibleName(
                f"{banner.heading}: {banner.summary}" if banner.summary else banner.heading
            )
            self.banner_frame.setStyleSheet(
                "QFrame#verificationBanner {"
                f"background-color: {resolved.background};"
                "border-radius: 6px;"
                "}"
                "QFrame#verificationBanner QLabel {"
                f"color: {resolved.foreground};"
                "background: transparent;"
                "}"
            )

        def _apply_summary(self, summary: VerificationSummaryProjection) -> None:
            for field_name, _ in VERIFICATION_SUMMARY_FIELDS:
                value = getattr(summary, field_name)
                label = self._summary_value_labels[field_name]
                label.setText(value or "")
                label.parentWidget().setVisible(value is not None)

        def _apply_projection(self, projection: VerificationProjection) -> None:
            self._clear_checks()
            self._projection = projection
            self._apply_banner(projection.banner)
            self._apply_summary(projection.summary)

            has_checks = bool(projection.checks)
            self.checks_holder.setVisible(has_checks)
            self.checks_empty_state_label.setVisible(
                not has_checks and projection.checks_empty_state is not None
            )
            self.checks_empty_state_label.setText(
                "" if has_checks else (projection.checks_empty_state or "")
            )
            if has_checks:
                self._install_checks(projection.checks)


else:

    class VerificationView:
        """Unavailable placeholder when the optional desktop toolkit is absent."""

        def __init__(self, *args, **kwargs) -> None:
            raise RuntimeError("PySide6 is required for VerificationView")


__all__ = [
    "PYSIDE6_AVAILABLE",
    "VERIFICATION_CHECK_LABELS",
    "VERIFICATION_SUMMARY_FIELDS",
    "VerificationBannerProjection",
    "VerificationCheckProjection",
    "VerificationProjection",
    "VerificationSummaryProjection",
    "VerificationView",
]
