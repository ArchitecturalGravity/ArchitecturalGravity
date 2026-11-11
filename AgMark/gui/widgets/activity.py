"""Accessible indeterminate work indicator; no lifecycle authority."""
try:
    from PySide6.QtCore import QRectF, Qt, QTimer
    from PySide6.QtGui import QColor, QPainter, QPen
    from PySide6.QtWidgets import QWidget
except ImportError:
    class BlueActivitySpinner:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PySide6 is required for the activity spinner")
else:
    class BlueActivitySpinner(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setFixedSize(24, 24)
            self.setAccessibleName("Working, duration unknown")
            self.setObjectName("operationActivitySpinner")
            self._busy = False
            self._angle = 0
            self._timer = QTimer(self)
            self._timer.setInterval(60)
            self._timer.timeout.connect(self._advance)

        @property
        def busy(self):
            return self._busy

        def set_busy(self, busy):
            self._busy = bool(busy)
            self.setProperty("busy", self._busy)
            self._sync_timer()
            self.update()

        def _sync_timer(self):
            if self._busy and self.isVisible():
                self._timer.start()
            else:
                self._timer.stop()

        def _advance(self):
            self._angle = (self._angle + 24) % 360
            self.update()

        def showEvent(self, event):
            super().showEvent(event)
            self._sync_timer()

        def hideEvent(self, event):
            self._timer.stop()
            super().hideEvent(event)

        def paintEvent(self, event):
            if not self._busy:
                return
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor("#267CDB"), 3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(QRectF(4, 4, 16, 16), -self._angle * 16, 270 * 16)
