"""Shared spacing for compact panel title bars."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy


def panel_heading_layout(widget, *, left=12):
    """Use explicit insets and gaps without enlarging compact title bars."""
    widget.setObjectName('panelHeading')
    widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(left, 0, 8, 0)
    layout.setSpacing(8)
    return layout


def add_heading_control(layout, widget):
    layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
