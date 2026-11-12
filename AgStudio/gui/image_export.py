"""Full-document code-only image export without changing the live editor."""
from dataclasses import dataclass
import math
from itertools import islice
import os
from pathlib import Path
import tempfile

from PIL import Image
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QTextLayout, QTextOption
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QLabel, QSpinBox)

MAX_PIXELS = 24_000_000  # Bound RGB output, conversion copies and encoder memory.
MAX_WIDTH = 32760  # Qt raster paint coordinate limit; height is rendered in bands.
QUANTIZERS = {'Median cut': Image.Quantize.MEDIANCUT,
              'Maximum coverage': Image.Quantize.MAXCOVERAGE,
              'Fast octree': Image.Quantize.FASTOCTREE}


@dataclass(frozen=True)
class ExportOptions:
    format: str = 'PNG'
    depth: int = 24
    quantizer: str = 'Median cut'
    quality: int = 95
    grayscale: bool = False
    include_color_scheme: bool = True


class ExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Export Code Image')
        form = QFormLayout(self)
        form.addRow(QLabel('Entire document, code only. No gutter or selection.'))
        self.format = QComboBox()
        self.format.addItems(['PNG', 'JPG'])
        self.depth = QComboBox()
        for label, bits in [('Full color (24-bit, lossless)', 24),
                            ('256 colors (8-bit)', 8), ('16 colors (4-bit)', 4),
                            ('2 colors (1-bit)', 1)]:
            self.depth.addItem(label, bits)
        self.quantizer = QComboBox()
        self.quantizer.addItems(QUANTIZERS)
        self.quality = QSpinBox()
        self.quality.setRange(1, 100)
        self.quality.setValue(95)
        self.scheme = QCheckBox('Include editor color scheme')
        self.scheme.setChecked(True)
        self.scheme.setToolTip('Uncheck for plain black text on a white background.')
        self.gray = QCheckBox('Grayscale (black and white)')
        form.addRow('Format', self.format)
        form.addRow('PNG color depth', self.depth)
        form.addRow('PNG quantization', self.quantizer)
        form.addRow('JPG quality', self.quality)
        form.addRow(self.scheme)
        form.addRow(self.gray)
        form.addRow(QLabel('Reduced color/quality lowers file size, not image dimensions.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.format.currentTextChanged.connect(self._update)
        self.depth.currentIndexChanged.connect(self._update)
        self._update()

    def _update(self, *_):
        png = self.format.currentText() == 'PNG'
        self.depth.setEnabled(png)
        self.quantizer.setEnabled(png and self.depth.currentData() != 24)
        self.quality.setEnabled(not png)

    def options(self):
        return ExportOptions(self.format.currentText(), self.depth.currentData(),
                             self.quantizer.currentText(), self.quality.value(),
                             self.gray.isChecked(), self.scheme.isChecked())


def export_path(path, options):
    path = Path(path)
    allowed = {'.png'} if options.format == 'PNG' else {'.jpg', '.jpeg'}
    return path if path.suffix.lower() in allowed else path.with_suffix(
        '.png' if options.format == 'PNG' else '.jpg')


def render_document(editor, options):
    """Copy text layouts and syntax formats, never selections or gutter paint."""
    layouts = []
    y, width, padding = 8, 16, 8
    block = editor.document().begin()
    while block.isValid():
        layout = QTextLayout(block.text(), editor.font())
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.NoWrap)
        text_option.setTabStopDistance(editor.tabStopDistance())
        layout.setTextOption(text_option)
        if options.include_color_scheme:
            layout.setFormats(block.layout().formats())
        layout.beginLayout()
        line = layout.createLine()
        if line.isValid():
            line.setLineWidth(1_000_000_000)
            height = max(1, math.ceil(line.height()))
            width = max(width, math.ceil(line.naturalTextWidth()) + 2 * padding)
        else:
            height = editor.fontMetrics().height()
        layout.endLayout()
        layouts.append((y, height, layout))
        y += height
        if width > MAX_WIDTH or width * (y + padding) > MAX_PIXELS:
            raise ValueError('The complete image exceeds the safe export size '
                             '(24 million pixels or 32,760 pixels wide). '
                             'It has not been clipped or split. Reduce the editor font size or document length.')
        block = block.next()
    height = y + padding
    if options.format == 'JPG' and height > 65500:
        raise ValueError('This image is too tall for JPG. Choose PNG instead.')
    bg = (QColor(*editor.color_scheme['editor']['background'])
          if options.include_color_scheme else QColor('white'))
    fg = (QColor(*editor.color_scheme['editor']['foreground'])
          if options.include_color_scheme else QColor('black'))
    output = Image.new('RGB', (width, height), (bg.red(), bg.green(), bg.blue()))
    # Bands avoid Qt's signed 16-bit painter coordinates on tall documents.
    index = 0
    for top in range(0, height, 1024):
        band_height = min(1024, height - top)
        band = QImage(width, band_height, QImage.Format.Format_RGB32)
        if band.isNull():
            raise MemoryError('Not enough memory to render the image.')
        band.fill(bg)
        painter = QPainter(band)
        painter.setPen(fg)
        while index < len(layouts) and layouts[index][0] + layouts[index][1] <= top:
            index += 1
        for row_y, row_height, layout in islice(layouts, index, None):
            if row_y >= top + band_height:
                break
            layout.draw(painter, QPointF(padding, row_y - top))
        painter.end()
        rgb = band.convertToFormat(QImage.Format.Format_RGB888)
        pixels = Image.frombytes('RGB', (width, band_height), bytes(rgb.constBits()),
                                 'raw', 'RGB', rgb.bytesPerLine())
        output.paste(pixels, (0, top))
    if options.grayscale:
        output = output.convert('L')
    if options.format == 'PNG' and options.depth != 24:
        output = output.convert('RGB').quantize(colors=2 ** options.depth,
                                                method=QUANTIZERS[options.quantizer])
    return output


def write_image(image, path, options):
    """Atomic replacement: failed encoding leaves an existing destination intact."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.agstudio-export-', dir=path.parent)
    os.close(fd)
    try:
        kwargs = ({'bits': options.depth} if options.format == 'PNG' and options.depth != 24
                  else {})
        if options.format == 'JPG':
            kwargs.update(quality=options.quality, subsampling=0)
        image.save(temporary, format='JPEG' if options.format == 'JPG' else 'PNG', **kwargs)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
