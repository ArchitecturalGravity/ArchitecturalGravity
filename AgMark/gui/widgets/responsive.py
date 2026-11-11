"""Presentation-only size floors and responsive workspace composition.

Floors protect readable component viewports, not the width of their data.
Pages may grow taller when columns stack; the shell owns local page scrolling.
"""

from __future__ import annotations

try:
    from PySide6.QtCore import QEvent, QTimer
    from PySide6.QtWidgets import QBoxLayout, QLabel, QSizePolicy, QWidget
except ImportError:
    class ResponsiveView:
        pass
else:
    def apply_minimum(widget, width, height, vertical_expanding=True):
        height_for_width = widget.hasHeightForWidth()
        widget.setMinimumSize(width, height)
        policy = QSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding if vertical_expanding else QSizePolicy.Policy.Minimum,
        )
        policy.setHeightForWidth(height_for_width)
        widget.setSizePolicy(policy)

    def wrap_text(label: QLabel):
        """Wrap inspectable text without letting a single ID dictate card width."""
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        policy = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        label.setSizePolicy(policy)

    class ResponsiveView(QWidget):
        """Reflow box layouts before calculating the page's required height."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._responsive_layouts = []
            self._available_width = None
            self._sizing = False
            self._size_refresh_pending = False
            self._size_refresh_timer = QTimer(self)
            self._size_refresh_timer.setSingleShot(True)
            self._size_refresh_timer.timeout.connect(self._refresh_component_sizes)

        def add_responsive_layout(self, layout, breakpoint):
            self._responsive_layouts.append((layout, breakpoint))

        def set_available_width(self, width):
            if self._sizing or self.layout() is None:
                return
            self._sizing = True
            try:
                self._available_width = width
                for layout, breakpoint in self._responsive_layouts:
                    direction = (QBoxLayout.Direction.LeftToRight if width >= breakpoint
                                 else QBoxLayout.Direction.TopToBottom)
                    if layout.direction() != direction:
                        layout.setDirection(direction)
                root = self.layout()
                root.activate()
                content_width = max(self.minimumWidth(), width)
                height = max(240, root.minimumSize().height())
                # Preferred heights include editors and tables' size hints.
                # Only their usable minima should force the page to scroll.
                if root.hasHeightForWidth():
                    height = max(height, root.totalMinimumHeightForWidth(content_width))
                if self.minimumHeight() != height:
                    self.setMinimumHeight(height)
            finally:
                self._sizing = False

        def heightForWidth(self, width):
            # QScrollArea consults this even with an explicit minimumHeight.
            # A preferred editor height must not force scrolling before it shrinks.
            layout = self.layout()
            if layout is None:
                return super().heightForWidth(width)
            return max(240, layout.minimumSize().height(),
                       layout.totalMinimumHeightForWidth(width))

        def _refresh_component_sizes(self):
            self._size_refresh_pending = False
            self.set_available_width(self._available_width or self.width())

        def resizeEvent(self, event):
            super().resizeEvent(event)
            self.set_available_width(event.size().width())

        def event(self, event):
            result = super().event(event)
            if (event.type() == QEvent.Type.LayoutRequest
                    and hasattr(self, "_size_refresh_pending")
                    and not self._size_refresh_pending):
                self._size_refresh_pending = True
                self._size_refresh_timer.start(0)
            return result
