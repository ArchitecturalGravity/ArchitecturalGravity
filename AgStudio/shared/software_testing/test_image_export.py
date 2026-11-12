"""Code image export: full content, encodings and state preservation."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QTextLayout, QTextCharFormat
from AgStudio.gui.app import SourceEditor
from AgStudio.gui.image_export import (ExportOptions, ExportDialog, export_path,
                                       render_document, write_image, QUANTIZERS)


class ImageExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = SourceEditor()
        self.editor.resize(300, 120)
        self.editor.setPlainText('Hello: syntax\n' + 'W' * 200 + '\n' + 'last\n' * 200)

    def tearDown(self):
        self.editor.deleteLater()

    def test_full_document_and_state(self):
        before = (self.editor.toPlainText(), self.editor.textCursor().position(),
                  self.editor.verticalScrollBar().value(), self.editor.document().isModified())
        image = render_document(self.editor, ExportOptions())
        self.assertGreater(image.width, self.editor.width())
        self.assertGreater(image.height, self.editor.height() * 10)
        self.assertEqual(before, (self.editor.toPlainText(), self.editor.textCursor().position(),
                                 self.editor.verticalScrollBar().value(), self.editor.document().isModified()))
        bg = image.getpixel((0, 0))
        self.assertTrue(all(image.getpixel((0, y)) == bg for y in range(image.height)))
        self.assertGreater(len(set(image.crop((8, image.height - 65, 100, image.height - 8)).getdata())), 1)

    def test_formats_depths_and_quantizers(self):
        self.editor.setPlainText('Hello: colors')
        with tempfile.TemporaryDirectory() as temp:
            for depth in (1, 4, 8, 24):
                for quantizer in QUANTIZERS:
                    options = ExportOptions(depth=depth, quantizer=quantizer)
                    image = render_document(self.editor, options)
                    path = Path(temp) / 'out.png'
                    write_image(image, path, options)
                    with Image.open(path) as saved:
                        self.assertEqual(saved.size, image.size)
                        if depth != 24:
                            self.assertLessEqual(len(saved.getcolors()), 2 ** depth)
                    self.assertEqual(path.read_bytes()[24], depth if depth != 24 else 8)
            options = ExportOptions(format='JPG', quality=75, grayscale=True)
            image = render_document(self.editor, options)
            path = Path(temp) / 'out.jpg'
            write_image(image, path, options)
            with Image.open(path) as saved:
                self.assertEqual(saved.format, 'JPEG')
                self.assertEqual(saved.mode, 'L')

    def test_syntax_color_and_no_selection(self):
        self.editor.setPlainText('Colored')
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(255, 0, 0))
        value = QTextLayout.FormatRange()
        value.start, value.length, value.format = 0, 7, fmt
        self.editor.document().begin().layout().setFormats([value])
        self.editor.selectAll()
        image = render_document(self.editor, ExportOptions())
        self.assertTrue(any(r > 200 and g < 80 and b < 80 for r, g, b in image.getdata()))

    def test_plain_text_without_color_scheme(self):
        from copy import deepcopy
        scheme = deepcopy(self.editor.color_scheme)
        scheme['editor']['background'] = [40, 50, 60, 255]
        scheme['editor']['foreground'] = [220, 230, 240, 255]
        self.editor.apply_color_scheme(scheme)
        self.editor.setPlainText('Colorful text\n    indented\n\nlast')
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(255, 0, 0))
        fmt.setBackground(QColor(0, 255, 0))
        value = QTextLayout.FormatRange()
        value.start, value.length, value.format = 0, 13, fmt
        self.editor.document().begin().layout().setFormats([value])
        styled = render_document(self.editor, ExportOptions())
        self.assertEqual(styled.getpixel((0, 0)), (40, 50, 60))
        self.assertTrue(any(r > 200 and g < 80 and b < 80 for r, g, b in styled.getdata()))
        for format in ('PNG', 'JPG'):
            for grayscale in (False, True):
                options = ExportOptions(format=format, include_color_scheme=False,
                                        grayscale=grayscale)
                plain = render_document(self.editor, options)
                self.assertEqual(plain.size, styled.size)
                self.assertEqual(plain.getpixel((0, 0)), 255 if grayscale else (255, 255, 255))
                pixels = list(plain.convert('RGB').getdata())
                self.assertTrue(all(r == g == b for r, g, b in pixels))
                self.assertIn((0, 0, 0), pixels)
        self.assertEqual(self.editor.color_scheme, scheme)
        self.assertEqual(len(self.editor.document().begin().layout().formats()), 1)

    def test_size_guard_and_atomic_failure(self):
        with patch('AgStudio.gui.image_export.MAX_PIXELS', 10):
            with self.assertRaisesRegex(ValueError, 'not been clipped'):
                render_document(self.editor, ExportOptions())
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'keep.png'
            path.write_bytes(b'original')
            with patch.object(Image.Image, 'save', side_effect=OSError('failure')):
                with self.assertRaises(OSError):
                    write_image(Image.new('RGB', (2, 2)), path, ExportOptions())
            self.assertEqual(path.read_bytes(), b'original')
            self.assertEqual(list(Path(temp).iterdir()), [path])

    def test_options_and_suffix(self):
        dialog = ExportDialog()
        self.assertEqual(dialog.windowTitle(), "Export Code Image")
        self.assertTrue(dialog.options().include_color_scheme)
        dialog.scheme.setChecked(False)
        self.assertFalse(dialog.options().include_color_scheme)
        self.assertFalse(dialog.quantizer.isEnabled())
        dialog.depth.setCurrentIndex(1)
        self.assertTrue(dialog.quantizer.isEnabled())
        dialog.format.setCurrentText('JPG')
        self.assertTrue(dialog.quality.isEnabled())
        self.assertFalse(dialog.depth.isEnabled())
        self.assertEqual(export_path('name.png', dialog.options()), Path('name.jpg'))
        dialog.deleteLater()

    def test_tall_image_bands(self):
        self.editor.setPlainText('Band row\n' * 1800)
        image = render_document(self.editor, ExportOptions())
        self.assertGreater(image.height, 32767)
        bg = image.getpixel((0, 0))
        for top in (1010, 32750, image.height - 70):
            self.assertTrue(any(pixel != bg for pixel in
                                image.crop((8, top, 100, top + 40)).getdata()))

    def test_whitespace_and_custom_scheme(self):
        from copy import deepcopy
        scheme = deepcopy(self.editor.color_scheme)
        scheme['editor']['background'] = [240, 240, 240, 255]
        scheme['editor']['foreground'] = [10, 20, 30, 255]
        self.editor.apply_color_scheme(scheme)
        self.editor.setPlainText('X\n    X\n\n"""\n  literal  text\n"""\n' + 'Z' * 250)
        image = render_document(self.editor, ExportOptions())
        self.assertEqual(image.getpixel((0, 0)), (240, 240, 240))
        line_height = self.editor.fontMetrics().height()
        bg = image.getpixel((0, 0))
        def left(top):
            return min(x for x in range(100) for y in range(top, top + line_height)
                       if image.getpixel((x, y)) != bg)
        self.assertGreater(left(8 + line_height), left(8) + 20)
        self.assertTrue(all(pixel == bg for pixel in image.crop(
            (8, 8 + 2 * line_height, 100, 8 + 3 * line_height)).getdata()))
        self.assertGreater(image.width, 2000)

    def test_export_has_own_top_level_menu(self):
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.user_state import UserState
        window = StudioWindow("current", user_state=UserState(), background=False)
        try:
            menus = {action.text(): action.menu() for action in window.menuBar().actions()}
            self.assertEqual([a.text() for a in window.menuBar().actions()],
                             ["File", "Edit", "View", "Export", "Color Scheme"])
            self.assertIn("Export", menus)
            self.assertEqual([a.text() for a in menus["Export"].actions()], ["Code Image"])
            self.assertNotIn(window.export_action, menus["File"].actions())
            with patch('AgStudio.gui.app.ExportDialog') as dialog:
                dialog.return_value.exec.return_value = 0
                window.export_action.trigger()
                dialog.assert_called_once_with(window)
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_dialog_cancel_overwrite_and_error(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from AgStudio.gui.app import StudioWindow
        from PySide6.QtWidgets import QMessageBox
        tab = SimpleNamespace(editor=self.editor, path=None)
        window = MagicMock()
        window.current.return_value = tab
        with patch('AgStudio.gui.app.ExportDialog') as dialog, \
             patch('AgStudio.gui.app.QFileDialog.getSaveFileName') as save, \
             patch('AgStudio.gui.app.render_document') as render, \
             patch('AgStudio.gui.app.QMessageBox.question') as question, \
             patch('AgStudio.gui.app.QMessageBox.critical') as critical:
            dialog.return_value.exec.return_value = 0
            StudioWindow._export_current_image(window)
            save.assert_not_called()
            dialog.return_value.exec.return_value = 1
            dialog.return_value.options.return_value = ExportOptions()
            save.return_value = ('', '')
            StudioWindow._export_current_image(window)
            render.assert_not_called()
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'existing.png'
                path.write_bytes(b'unchanged')
                save.return_value = (str(path.with_suffix('.txt')), '')
                question.return_value = QMessageBox.StandardButton.No
                StudioWindow._export_current_image(window)
                render.assert_not_called()
                self.assertEqual(path.read_bytes(), b'unchanged')
                question.return_value = QMessageBox.StandardButton.Yes
                render.side_effect = MemoryError('test allocation error')
                StudioWindow._export_current_image(window)
                critical.assert_called_once()
                self.assertEqual(path.read_bytes(), b'unchanged')


if __name__ == '__main__':
    unittest.main()
