"""Bounded arrow artwork with native tool-button interaction."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPalette, QPolygonF
from PySide6.QtWidgets import QStyle, QStyleOptionToolButton, QStylePainter, QToolButton


class CompactArrowButton(QToolButton):
    """Keep native button behavior while bounding only the disclosure artwork."""
    GLYPH_SIZE = 8

    def glyph_rect(self):
        size = min(self.GLYPH_SIZE, self.width(), self.height())
        return QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)

    def paintEvent(self, event):  # noqa: N802 - Qt API
        option = QStyleOptionToolButton()
        self.initStyleOption(option)
        # Native styles may expand Arrow artwork to almost the entire button.
        # Let the native style draw hover/pressed/focus, then draw a bounded glyph.
        option.features &= ~QStyleOptionToolButton.ToolButtonFeature.Arrow
        option.arrowType = Qt.ArrowType.NoArrow
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ToolButton, option)
        box = self.glyph_rect()
        center = box.center()
        half = box.width() / 4
        if self.arrowType() == Qt.ArrowType.DownArrow:
            points = [QPointF(box.left(), center.y() - half),
                      QPointF(box.right(), center.y() - half), QPointF(center.x(), center.y() + half)]
        elif self.arrowType() == Qt.ArrowType.UpArrow:
            points = [QPointF(box.left(), center.y() + half),
                      QPointF(box.right(), center.y() + half), QPointF(center.x(), center.y() - half)]
        elif self.arrowType() == Qt.ArrowType.RightArrow:
            points = [QPointF(center.x() - half, box.top()),
                      QPointF(center.x() - half, box.bottom()), QPointF(center.x() + half, center.y())]
        elif self.arrowType() == Qt.ArrowType.LeftArrow:
            points = [QPointF(center.x() + half, box.top()),
                      QPointF(center.x() + half, box.bottom()), QPointF(center.x() - half, center.y())]
        else:
            return
        group = QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(box)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(option.palette.color(group, QPalette.ColorRole.ButtonText))
        painter.drawPolygon(QPolygonF(points))
