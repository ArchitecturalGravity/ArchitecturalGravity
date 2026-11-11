"""Selectable plain text that wraps identifiers without modifying their bytes."""
from __future__ import annotations

try:
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QTextOption
    from PySide6.QtWidgets import QFrame, QSizePolicy, QTextBrowser
except ImportError:
    pass
else:
    class WrappingText(QTextBrowser):
        """Label-like reader with character fallback for long hashes and paths."""

        def __init__(self, text: str, parent=None):
            super().__init__(parent)
            self.setFrameShape(QFrame.Shape.NoFrame)
            self.setReadOnly(True)
            self.setOpenLinks(False)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                         | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
            self.document().setDocumentMargin(0)
            self.setStyleSheet("background: transparent; border: none; padding: 0px;")
            self.setPlainText(text)
            policy = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            policy.setHeightForWidth(True)
            self.setSizePolicy(policy)
            self.setMinimumWidth(0)

        def text(self) -> str:
            return self.toPlainText()

        def wordWrap(self) -> bool:
            return True

        def heightForWidth(self, width: int) -> int:
            document = self.document().clone()
            document.setTextWidth(max(1, width))
            height = int(document.size().height() + 1)
            return max(self.fontMetrics().height(), height)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            # Box layouts otherwise use the editor's one-line minimum even
            # when its height-for-width reports several wrapped lines.
            height = self.heightForWidth(event.size().width())
            if self.minimumHeight() != height:
                self.setMinimumHeight(height)

        def minimumSizeHint(self) -> QSize:
            return QSize(0, self.fontMetrics().height() + 1)

        def sizeHint(self) -> QSize:
            return QSize(180, self.heightForWidth(180))
