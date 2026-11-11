"""Conformance tests for concrete PySide6 card and disclosure widgets."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.widgets.containers import (
    CardWidget,
    DisclosureWidget,
    PYSIDE6_AVAILABLE,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QLabel


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class ContainerWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def test_card_preserves_title_content_availability_and_surface(self) -> None:
        content = QLabel("accepted")
        card = CardWidget(
            "Run Summary",
            content,
            available=True,
            icon_role="current-run-plan",
        )
        self.addCleanup(card.deleteLater)

        self.assertEqual(card.title, "Run Summary")
        self.assertIs(card.content_widget, content)
        self.assertTrue(card.available)
        self.assertTrue(card.isEnabled())
        self.assertEqual(card.surface.background, "#FFFFFF")
        self.assertEqual(card.surface.border, "#D7E3EF")
        self.assertEqual(card.surface.radius_px, 8)
        self.assertEqual(card.authority_semantics, "presentation-only")
        self.assertEqual(card.icon_role, "current-run-plan")
        self.assertIsNotNone(card.title_icon_label)
        self.assertFalse(card.title_icon_label.pixmap().isNull())

        card.set_title("blocked")
        self.assertEqual(card.title, "blocked")
        self.assertTrue(card.available)

        card.set_available(False)
        self.assertFalse(card.available)
        self.assertFalse(card.isEnabled())
        self.assertEqual(card.title, "blocked")
        self.assertEqual(content.text(), "accepted")

    def test_compact_card_preserves_content_priority_at_tall_sizes(self) -> None:
        content = QLabel("Retained status details")
        card = CardWidget("Workspace card", content, compact=True)
        self.addCleanup(card.deleteLater)
        card.show()
        title = card.findChild(QLabel, "semanticCardTitle")
        header_heights = []
        for height in (300, 900):
            card.resize(600, height)
            for _ in range(8):
                QApplication.processEvents()
            self.assertLessEqual(content.geometry().top() - title.geometry().bottom() - 1, 4)
            header_heights.append(title.height())
        self.assertEqual(header_heights[0], header_heights[1])

    def test_disclosure_preserves_label_expansion_content_and_availability(self) -> None:
        content = QLabel("verified")
        disclosure = DisclosureWidget(
            "Details",
            content,
            expanded=False,
            available=True,
        )
        self.addCleanup(disclosure.deleteLater)

        self.assertEqual(disclosure.label, "Details")
        self.assertIs(disclosure.content_widget, content)
        self.assertFalse(disclosure.expanded)
        self.assertTrue(content.isHidden())
        self.assertEqual(
            disclosure.toggle_button.arrowType(),
            Qt.ArrowType.RightArrow,
        )
        self.assertTrue(disclosure.available)
        self.assertEqual(disclosure.authority_semantics, "presentation-only")

        disclosure.set_expanded(True)
        self.assertTrue(disclosure.expanded)
        self.assertFalse(content.isHidden())
        self.assertEqual(
            disclosure.toggle_button.arrowType(),
            Qt.ArrowType.DownArrow,
        )

        disclosure.set_available(False)
        self.assertFalse(disclosure.available)
        self.assertFalse(disclosure.isEnabled())
        self.assertTrue(disclosure.expanded)
        self.assertFalse(content.isHidden())

    def test_disclosure_activation_changes_only_local_expansion_state(self) -> None:
        content = QLabel("retained response")
        disclosure = DisclosureWidget(
            "accepted",
            content,
            expanded=False,
        )
        self.addCleanup(disclosure.deleteLater)

        disclosure.toggle_button.click()
        self.assertTrue(disclosure.expanded)
        self.assertEqual(disclosure.label, "accepted")
        self.assertEqual(content.text(), "retained response")
        self.assertEqual(disclosure.authority_semantics, "presentation-only")

        disclosure.set_label("blocked")
        self.assertEqual(disclosure.label, "blocked")
        self.assertTrue(disclosure.expanded)
        self.assertTrue(disclosure.available)

    def test_unavailable_disclosure_preserves_expansion_without_activation(self) -> None:
        content = QLabel("diagnostics")
        disclosure = DisclosureWidget(
            "Unavailable details",
            content,
            expanded=True,
            available=False,
        )
        self.addCleanup(disclosure.deleteLater)

        self.assertTrue(disclosure.expanded)
        self.assertFalse(disclosure.available)
        self.assertFalse(disclosure.toggle_button.isEnabled())
        self.assertFalse(content.isHidden())

        disclosure.toggle_button.click()
        self.assertTrue(disclosure.expanded)
        self.assertFalse(content.isHidden())

    def test_invalid_caller_input_fails_closed(self) -> None:
        content = QLabel("content")

        with self.assertRaisesRegex(ValueError, "title"):
            CardWidget("   ", content)

        with self.assertRaisesRegex(ValueError, "content"):
            CardWidget("Title", object())  # type: ignore[arg-type]

        with self.assertRaisesRegex(KeyError, "unknown semantic icon role"):
            CardWidget("Title", QLabel("content"), icon_role="stock-card")

        with self.assertRaisesRegex(ValueError, "icon_role"):
            CardWidget("Title", QLabel("content"), icon_role="   ")

        with self.assertRaisesRegex(ValueError, "available"):
            CardWidget("Title", QLabel("content"), available=1)  # type: ignore[arg-type]

        with self.assertRaisesRegex(ValueError, "label"):
            DisclosureWidget("", QLabel("content"), expanded=False)

        with self.assertRaisesRegex(ValueError, "expanded"):
            DisclosureWidget(
                "Details",
                QLabel("content"),
                expanded=0,  # type: ignore[arg-type]
            )

        with self.assertRaisesRegex(ValueError, "available"):
            DisclosureWidget(
                "Details",
                QLabel("content"),
                expanded=False,
                available=None,  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
