"""Screen-bounded, read-only overflow for Infer Map tooltip text.

Ordinary summaries retain Qt's native tooltip. Long summaries use the same
tooltip font and colors, with scrolling rather than truncating any object.
"""
from html import escape

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, QTimer, Qt
from PySide6.QtGui import QCursor, QFontMetrics, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QApplication, QFrame, QPlainTextEdit, QStyle, QToolTip, QVBoxLayout, QWidget,
)


class MapTooltip(QObject):
    """Tooltip owned by its source widget; never focuses or edits the source.

    The caller supplies plain text and explicitly hides it whenever that text
    is invalidated. Hover/leave, Escape, and source-widget hiding are handled
    here, including a short grace period for moving into the overflow window.
    """

    SCREEN_MARGIN = 12
    LEAVE_GRACE_MS = 220

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._source = parent
        self._text = ''
        self._native_text = ''
        self._application_filter = False
        self._popup = QFrame(parent, Qt.WindowType.ToolTip
                             | Qt.WindowType.FramelessWindowHint
                             | Qt.WindowType.WindowDoesNotAcceptFocus)
        self._popup.setObjectName('mapOverflowTooltip')
        self._popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._popup.setFrameShape(QFrame.Shape.Box)
        self._popup.setAutoFillBackground(True)
        self._popup.setAccessibleName('Infer Map details')
        self._reader = QPlainTextEdit(self._popup)
        self._reader.setObjectName('mapOverflowTooltipText')
        self._reader.setReadOnly(True)
        self._reader.setUndoRedoEnabled(False)
        self._reader.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._reader.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._reader.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._reader.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._reader.setFrameShape(QFrame.Shape.NoFrame)
        self._reader.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        self._reader.verticalScrollBar().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._reader.horizontalScrollBar().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout = QVBoxLayout(self._popup)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.addWidget(self._reader)
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.setInterval(self.LEAVE_GRACE_MS)
        self._dismiss_timer.timeout.connect(self._dismiss_if_outside)
        parent.installEventFilter(self)

    def show_text(self, text: str, global_pos: QPoint):
        """Show every authored line, enabling scrolling only for overflow."""
        if not text or not self._source.isVisible():
            self.hide()
            return
        self._dismiss_timer.stop()
        # A repeated help event must not reset someone reading the last object.
        if text == self._text and self._popup.isVisible():
            return
        screen = (QGuiApplication.screenAt(global_pos) or self._source.screen()
                  or QGuiApplication.primaryScreen())
        available = screen.availableGeometry()
        # Keep even very small screens valid; normal desktop margins are 12 px.
        margin = min(self.SCREEN_MARGIN, max(0, (min(available.width(), available.height()) - 1) // 2))
        bounds = available.adjusted(margin, margin, -margin, -margin)
        font = QToolTip.font()
        measured = QFontMetrics(font).size(Qt.TextFlag.TextExpandTabs, text)
        natural = measured + QSize(20, 20)
        self._text = text
        if natural.width() <= bounds.width() and natural.height() <= bounds.height():
            self._popup.hide()
            self._remove_application_filter()
            self._native_text = '<p style="white-space:pre">' + escape(text).replace('\n', '<br>') + '</p>'
            QToolTip.showText(global_pos, self._native_text, self._source)
            return

        self._hide_native()
        palette = QToolTip.palette()
        background = palette.color(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipBase)
        foreground = palette.color(QPalette.ColorGroup.Inactive, QPalette.ColorRole.ToolTipText)
        for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base):
            palette.setColor(role, background)
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text):
            palette.setColor(role, foreground)
        self._popup.setPalette(palette)
        self._reader.setPalette(palette)
        self._reader.setFont(font)
        self._reader.setPlainText(text)
        scroll_extent = self._reader.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        width = min(bounds.width(), natural.width() + scroll_extent)
        height = min(bounds.height(), natural.height() + scroll_extent)
        self._popup.resize(width, height)
        x, y = global_pos.x() + 14, global_pos.y() + 18
        if x + width > bounds.right() + 1:
            x = global_pos.x() - width - 14
        if y + height > bounds.bottom() + 1:
            y = global_pos.y() - height - 18
        x = max(bounds.left(), min(x, bounds.right() - width + 1))
        y = max(bounds.top(), min(y, bounds.bottom() - height + 1))
        self._popup.move(x, y)
        self._install_application_filter()
        self._popup.show()
        self._reader.verticalScrollBar().setValue(0)
        self._reader.horizontalScrollBar().setValue(0)

    def hide(self):
        """Immediately dismiss stale evidence, including a pending leave."""
        self._dismiss_timer.stop()
        self._popup.hide()
        self._hide_native()
        self._text = ''
        self._remove_application_filter()

    def isVisible(self):  # noqa: N802
        return (self._popup.isVisible()
                or bool(self._native_text and QToolTip.isVisible()
                        and QToolTip.text() == self._native_text))

    def _hide_native(self):
        if self._native_text and QToolTip.text() == self._native_text:
            QToolTip.hideText()
        self._native_text = ''

    def _install_application_filter(self):
        if not self._application_filter:
            QApplication.instance().installEventFilter(self)
            self._application_filter = True

    def _remove_application_filter(self):
        if self._application_filter:
            QApplication.instance().removeEventFilter(self)
            self._application_filter = False

    def _is_popup_widget(self, widget):
        return (isinstance(widget, QWidget)
                and (widget is self._popup or self._popup.isAncestorOf(widget)))

    def _contains_pointer(self, widget):
        return widget.isVisible() and widget.rect().contains(widget.mapFromGlobal(QCursor.pos()))

    def _dismiss_if_outside(self):
        if not (self._contains_pointer(self._source) or self._contains_pointer(self._popup)):
            self.hide()

    def eventFilter(self, watched, event):  # noqa: N802
        kind = event.type()
        if watched is self._source:
            if kind in (QEvent.Type.Hide, QEvent.Type.Close, QEvent.Type.ParentChange):
                self.hide()
            elif kind in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel):
                self.hide()
            elif kind == QEvent.Type.Leave:
                if self._popup.isVisible():
                    self._dismiss_timer.start()
                else:
                    self._hide_native()
            elif kind == QEvent.Type.Enter:
                self._dismiss_timer.stop()
        if not self._popup.isVisible():
            return False
        if kind in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and event.key() == Qt.Key.Key_Escape:
            if kind == QEvent.Type.KeyPress:
                self.hide()
            event.accept()
            return True
        if kind == QEvent.Type.ApplicationDeactivate:
            self.hide()
        elif self._is_popup_widget(watched):
            if kind in (QEvent.Type.Enter, QEvent.Type.Wheel):
                self._dismiss_timer.stop()
            elif kind == QEvent.Type.Leave:
                self._dismiss_timer.start()
            elif kind == QEvent.Type.ToolTip:
                return True
        elif kind == QEvent.Type.MouseButtonPress:
            self.hide()
        return False
