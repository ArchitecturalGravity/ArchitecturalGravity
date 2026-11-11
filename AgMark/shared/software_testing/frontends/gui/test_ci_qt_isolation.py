"""CI retires only test-owned Qt roots, including detached presentation trees."""
import io
import os
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid
from AgMark.shared.software_testing.ci import IsolatedQtTestResult


class CiQtIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_cleanup_retires_new_roots_and_preserves_existing_fixture(self):
        existing = QWidget()
        self.addCleanup(existing.deleteLater)
        created = []
        seen = []
        class First(unittest.TestCase):
            def runTest(self):
                created.append(QWidget())
                created.append(QWidget(created[0]))
                created[1].setParent(None)
        class Second(unittest.TestCase):
            def runTest(self):
                seen.append((isValid(existing), *(isValid(widget) for widget in created)))
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=IsolatedQtTestResult).run(
            unittest.TestSuite((First(), Second())))
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(seen, [(True, False, False)])
        self.assertTrue(isValid(existing))
