"""Platform-independent Finding List indicators without changing native hit targets."""
from PySide6.QtWidgets import QStyleFactory

from .compact_arrow import CompactArrowButton as FindingExpansionButton


def style_finding_header(header):
    """Keep sort arrows beside labels, including on WindowsVista themes.

    Scope the standard Fusion style to this header only. The existing stylesheet
    continues to provide colors/padding; the rest of the app keeps its native style.
    Parent and retain the style because QWidget.setStyle does not own it.
    """
    header._finding_style = QStyleFactory.create('Fusion')
    header._finding_style.setParent(header)
    header.setStyle(header._finding_style)
