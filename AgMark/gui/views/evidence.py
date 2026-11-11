"""Capture health and retained files in one presentation-only workspace."""

from __future__ import annotations

from dataclasses import dataclass, replace

from AgMark.gui.views.artifacts import ArtifactsProjection
from AgMark.gui.views.progress import ProgressProjection
from AgMark.gui.widgets.actions import ArtifactActionButton
from AgMark.gui.widgets.tables import PYSIDE6_AVAILABLE


@dataclass(frozen=True, slots=True)
class EvidenceProjection:
    capture: ProgressProjection
    artifacts: ArtifactsProjection
    treatments_contaminated: bool = False

    def __post_init__(self):
        if not isinstance(self.capture, ProgressProjection):
            raise ValueError("capture must be a ProgressProjection")
        if not isinstance(self.artifacts, ArtifactsProjection):
            raise ValueError("artifacts must be an ArtifactsProjection")
        if self.capture.run_id != self.artifacts.run_id:
            raise ValueError("Evidence must belong to the same run")


try:
    if not PYSIDE6_AVAILABLE:
        raise ImportError
    from PySide6.QtCore import QThread, Qt, Signal
    from PySide6.QtWidgets import (
        QAbstractItemView, QHBoxLayout, QHeaderView, QLabel,
        QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
    )
except ImportError:
    PYSIDE6_AVAILABLE = False


if PYSIDE6_AVAILABLE:
    from AgMark.gui.widgets.responsive import ResponsiveView, apply_minimum, wrap_text

    class EvidenceView(ResponsiveView):
        """Sources contain linked files; unassociated artifacts remain reachable."""

        projectionRequested = Signal(object)
        captureProjectionRequested = Signal(object)

        def __init__(self, projection: EvidenceProjection, *, parent: QWidget | None = None):
            if not isinstance(projection, EvidenceProjection):
                raise ValueError("projection must be an EvidenceProjection")
            super().__init__(parent)
            self.setObjectName("evidenceWorkspaceView")
            self.setAccessibleName("Evidence workspace")
            self.setProperty("authoritySemantics", "presentation-only")
            self._projection = projection
            self._topology = None
            self._items = {}
            self._files = {}

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            self.contamination_label = QLabel("Treatments Contaminated", self)
            self.contamination_label.setStyleSheet("color: #F0212D;")
            self.contamination_label.setVisible(projection.treatments_contaminated)
            layout.addWidget(self.contamination_label)
            self.retention_label = QLabel(self)
            self.retention_label.setAccessibleName("Saved evidence availability")
            wrap_text(self.retention_label)
            layout.addWidget(self.retention_label)

            self.tree = QTreeWidget(self)
            self.tree.setObjectName("evidenceTree")
            self.tree.setAccessibleName("Capture sources and saved files")
            self.tree.setHeaderLabels(("Source / File", "Capture State", "Events", "Bytes",
                                       "Capture Health", "File Status"))
            self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.tree.setUniformRowHeights(True)
            self.tree.setAlternatingRowColors(True)
            self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            self.tree.header().setStretchLastSection(False)
            for index, width in enumerate((330, 130, 70, 90, 280, 160)):
                self.tree.setColumnWidth(index, width)
            apply_minimum(self.tree, 480, 260)
            layout.addWidget(self.tree, 1)

            self.details = QLabel("Select a capture source or saved file to inspect it.", self)
            self.details.setObjectName("evidenceDetails")
            self.details.setAccessibleName("Selected evidence details")
            self.details.setTextFormat(Qt.TextFormat.PlainText)
            self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            wrap_text(self.details)
            layout.addWidget(self.details)
            self.actions = QWidget(self)
            self.actions_layout = QHBoxLayout(self.actions)
            self.actions_layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.actions)
            self.open_button = None
            self.reveal_button = None
            self.tree.currentItemChanged.connect(self._selection_changed)
            self.projectionRequested.connect(self._apply_projection, Qt.ConnectionType.QueuedConnection)
            self.captureProjectionRequested.connect(self._apply_capture_projection, Qt.ConnectionType.QueuedConnection)
            self._apply_projection(projection)

        @property
        def projection(self):
            return self._projection

        @property
        def run_id(self):
            return self._projection.capture.run_id

        @property
        def authority_semantics(self):
            return "presentation-only"

        def set_projection(self, projection: EvidenceProjection):
            if not isinstance(projection, EvidenceProjection):
                raise ValueError("projection must be an EvidenceProjection")
            if QThread.currentThread() == self.thread():
                self._apply_projection(projection)
            else:
                self.projectionRequested.emit(projection)

        def set_capture_projection(self, projection: ProgressProjection):
            if not isinstance(projection, ProgressProjection):
                raise ValueError("projection must be a ProgressProjection")
            if QThread.currentThread() == self.thread():
                self._apply_capture_projection(projection)
            else:
                self.captureProjectionRequested.emit(projection)

        def _apply_capture_projection(self, projection):
            if (projection.run_id == self.run_id
                    and projection.generation_id == self._projection.capture.generation_id):
                self._apply_projection(replace(self._projection, capture=projection))

        @staticmethod
        def _source_key(source):
            return ("source", source.scope, source.treatment_id, source.attempt_id,
                    source.invocation_id, source.capture, source.source)

        @staticmethod
        def _linked(source, artifact):
            return (source.invocation_id is not None
                    and source.scope == artifact.capture_scope
                    and source.invocation_id in artifact.capture_invocation_ids)

        def _new_item(self, key, texts, parent=None):
            item = QTreeWidgetItem(parent if parent is not None else self.tree, texts)
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            self._items[key] = item
            return item

        def _add_file(self, parent, artifact, prefix):
            key = (*prefix, "file", artifact.artifact_id)
            self._new_item(key, (artifact.artifact, "—", "—", artifact.size,
                                 "—", artifact.status), parent)
            self._files[key] = artifact

        def _rebuild(self, projection, links):
            selected = self.tree.currentItem()
            previous_key = selected.data(0, Qt.ItemDataRole.UserRole) if selected else None
            expanded = {key for key, item in self._items.items() if item.isExpanded()}
            old_keys = set(self._items)
            same_run = self._topology is not None and self._topology[0] == projection.capture.run_id
            vertical = self.tree.verticalScrollBar().value() if same_run else 0
            horizontal = self.tree.horizontalScrollBar().value() if same_run else 0
            self.tree.blockSignals(True)
            try:
                self.tree.clear()
                self._items.clear()
                self._files.clear()
                groups = {}
                linked_ids = set()
                for source, artifacts in links:
                    scope_label = {"original": "Original Run", "replay": "Validation Replay"}.get(source.scope, "Capture sources")
                    group_keys = (("scope", scope_label),)
                    labels = [scope_label]
                    if source.treatment_id:
                        group_keys += (("treatment", scope_label, source.treatment_id),)
                        labels.append(source.treatment_id)
                    capture_label = " / ".join(filter(None, (source.invocation_id, source.attempt_id))) or source.capture
                    group_keys += (("capture", source.scope, source.treatment_id,
                                    source.invocation_id, source.attempt_id, source.capture),)
                    labels.append(capture_label)
                    parent = None
                    for key, label in zip(group_keys, labels, strict=True):
                        if key not in groups:
                            groups[key] = self._new_item(key, (label,), parent)
                            groups[key].setExpanded(key in expanded or key not in old_keys or not same_run)
                        parent = groups[key]
                    key = self._source_key(source)
                    item = self._new_item(key, (source.source,), parent)
                    item.setExpanded(same_run and key in expanded)
                    for artifact in artifacts:
                        linked_ids.add(artifact.artifact_id)
                        self._add_file(item, artifact, key)
                other = tuple(row for row in projection.artifacts.rows if row.artifact_id not in linked_ids)
                if other:
                    key = ("other",)
                    group = self._new_item(key, ("Other artifacts" if links else "Saved artifacts",))
                    group.setExpanded(key in expanded or key not in old_keys or not same_run)
                    for artifact in other:
                        self._add_file(group, artifact, key)
                if same_run and previous_key in self._items:
                    self.tree.setCurrentItem(self._items[previous_key])
            finally:
                self.tree.blockSignals(False)
            self.tree.verticalScrollBar().setValue(vertical)
            self.tree.horizontalScrollBar().setValue(horizontal)

        def _apply_projection(self, projection):
            self.contamination_label.setVisible(projection.treatments_contaminated)
            links = tuple((source, tuple(row for row in projection.artifacts.rows if self._linked(source, row)))
                          for source in projection.capture.capture_sources)
            topology = (projection.capture.run_id,
                        tuple((self._source_key(source), source.scope, source.treatment_id,
                               source.attempt_id, source.invocation_id,
                               tuple(row.artifact_id for row in rows)) for source, rows in links),
                        projection.artifacts.rows)
            old_artifacts = self._projection.artifacts
            self._projection = projection
            rebuilt = topology != self._topology
            if rebuilt:
                self._rebuild(projection, links)
                self._topology = topology
            for source, rows in links:
                item = self._items[self._source_key(source)]
                values = (source.source, source.state, source.events, source.bytes, source.health,
                          f"{len(rows)} linked {'file' if len(rows) == 1 else 'files'}" if rows else "No saved file linked")
                for column, value in enumerate(values):
                    item.setText(column, value)
            count = len(projection.artifacts.rows)
            inventory = f"{count} saved or generated {'artifact' if count == 1 else 'artifacts'}."
            self.retention_label.setText(
                inventory + " Expand a capture source to inspect linked files."
                if count and links else inventory if count else
                projection.artifacts.empty_state or "No saved artifacts are available.")
            self.tree.setVisible(bool(links or count))
            if rebuilt or old_artifacts != projection.artifacts:
                self._selection_changed()
            elif self.tree.currentItem() is not None:
                key = self.tree.currentItem().data(0, Qt.ItemDataRole.UserRole)
                if key not in self._files:
                    self._selection_changed()

        def _selection_changed(self, *_):
            while self.actions_layout.count():
                item = self.actions_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.open_button = self.reveal_button = None
            self.actions.hide()
            item = self.tree.currentItem()
            key = item.data(0, Qt.ItemDataRole.UserRole) if item else None
            artifact = self._files.get(key)
            if artifact is not None:
                self.details.setText(
                    f"{artifact.artifact}\nFile status: {artifact.status} · Type: {artifact.artifact_type} · Size: {artifact.size}"
                    f"\nSHA256: {artifact.integrity_hash}\nLocation: {artifact.reference or 'No retained local file'}")
                for label, action in (("Open", artifact.open_action), ("Reveal", artifact.reveal_action)):
                    button = ArtifactActionButton(label, action.operation, available=action.available, parent=self.actions)
                    button.setAccessibleDescription(action.unavailable_reason or "")
                    button.setProperty("callerUnavailableReason", action.unavailable_reason or "")
                    self.actions_layout.addWidget(button)
                    if label == "Open":
                        self.open_button = button
                    else:
                        self.reveal_button = button
                self.actions_layout.addStretch(1)
                self.actions.show()
            else:
                source = next((source for source in self._projection.capture.capture_sources
                               if self._source_key(source) == key), None)
                self.details.setText(
                    f"{source.capture} · {source.source}\nCapture state: {source.state} · {source.health}"
                    f"\nAvailability / Reason: {source.reason}"
                    if source else "Select a capture source or saved file to inspect it.")

else:
    class EvidenceView:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PySide6 is required for EvidenceView")


__all__ = ["EvidenceProjection", "EvidenceView", "PYSIDE6_AVAILABLE"]
