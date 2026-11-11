"""Shared compact progress artwork and visibility-bound panel animation."""
from PySide6.QtCore import QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


def paint_pending_spinner(widget, editor, phase, *, palette=None):
    background = (palette.window().color() if palette is not None
                  else QColor(*editor.color_scheme['editor']['background']))
    background.setAlpha(255)
    foreground = (palette.windowText().color() if palette is not None
                  else QColor(*editor.color_scheme['editor']['foreground']))
    if abs(foreground.lightness() - background.lightness()) < 60:
        foreground = QColor(55, 55, 55) if background.lightness() > 127 else QColor(215, 215, 215)
    foreground.setAlpha(205)
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    ring = QRectF(3, 3, 14, 14)
    track = QColor(foreground)
    track.setAlpha(35)
    painter.setPen(QPen(track, 2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(ring)
    pen = QPen(foreground, 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawArc(ring, (90 - phase) * 16, -250 * 16)
    painter.end()


class PendingSpinner(QWidget):
    """The map's 20px spinner, with no timer work while its panel is hidden."""
    def __init__(self, editor, name, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.pending = False
        self.phase = 0
        self.setFixedSize(20, 20)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName(f'{name} update in progress')
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self._advance)
        editor.colorSchemeChanged.connect(self.update)
        self.hide()

    def set_pending(self, pending, *, stale=False):
        self.pending = pending
        description = ('Analysis pending; previous results are stale and navigation is unavailable'
                       if stale else 'Analysis pending; navigation is unavailable') if pending else ''
        self.setAccessibleDescription(description)
        self.setToolTip(description)
        self.setVisible(pending)
        self._sync_timer()

    def _sync_timer(self):
        if self.pending and self.isVisible():
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()

    def _advance(self):
        self._sync_timer()
        if self.timer.isActive():
            self.phase = (self.phase + 30) % 360
            self.update()

    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event):  # noqa: N802
        self.timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event):  # noqa: N802
        self.set_pending(False)
        super().closeEvent(event)

    def paintEvent(self, event):  # noqa: N802
        # Headers use the application palette, independently of editor themes.
        paint_pending_spinner(self, self.editor, self.phase, palette=self.palette())
