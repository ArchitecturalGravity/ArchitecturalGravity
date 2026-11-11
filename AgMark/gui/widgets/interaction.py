"""Application-wide cursor affordances, without changing control behavior."""

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QAbstractButton, QComboBox, QMenu, QTabBar


class ControlCursorFilter(QObject):
    """Keep pointer feedback tied to enabled clickable hit targets.

    Text editors, scrollbars, splitters and data views retain their native
    text, resize and selection cursors. Tab/menu gaps are not click targets.
    """

    def eventFilter(self, watched, event):
        if not isinstance(watched, (QAbstractButton, QComboBox, QTabBar, QMenu)):
            return False
        if event.type() not in (
            QEvent.Type.Polish, QEvent.Type.Show, QEvent.Type.Enter,
            QEvent.Type.MouseMove, QEvent.Type.EnabledChange,
        ):
            return False
        clickable = watched.isEnabled()
        if isinstance(watched, QComboBox):
            # Editable combos keep the native text cursor and dropdown behavior.
            if watched.isEditable():
                return False
        elif isinstance(watched, QTabBar):
            watched.setMouseTracking(True)
            index = watched.tabAt(watched.mapFromGlobal(QCursor.pos()))
            clickable = clickable and index >= 0 and watched.isTabEnabled(index)
        elif isinstance(watched, QMenu):
            action = watched.actionAt(watched.mapFromGlobal(QCursor.pos()))
            clickable = clickable and action is not None and action.isEnabled() and not action.isSeparator()
        watched.setCursor(Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor)
        return False


def install_control_cursors(application):
    """Install once; parent ownership keeps the event filter alive."""
    if getattr(application, "_arcgrav_control_cursors", None) is None:
        cursor_filter = ControlCursorFilter(application)
        application._arcgrav_control_cursors = cursor_filter
        application.installEventFilter(cursor_filter)
