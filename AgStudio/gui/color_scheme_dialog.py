"""Live scheme editing with explicit persistence and reversible previews."""
from copy import deepcopy
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QSpinBox, QColorDialog, QGroupBox, QFormLayout, QDialogButtonBox,
    QMessageBox, QInputDialog, QSlider)
from .color_schemes import ROLE_LABELS


class ColorSchemeDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        from .app import SourceEditor, _CoreHighlighter
        from ..shared import LanguageCore
        self.window = window
        self.store = window.scheme_store
        self.working = deepcopy(window.color_scheme)
        self.scheme_name = window.scheme_name
        self.applied_scheme = deepcopy(window.color_scheme)
        self.applied_name = window.scheme_name
        self.setWindowTitle('Color Scheme')
        self.resize(760, 700)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel('Saved scheme'))
        self.schemes = QComboBox()
        row.addWidget(self.schemes, 1)
        load = QPushButton('Load')
        load.clicked.connect(self.load_scheme)
        row.addWidget(load)
        save = QPushButton('Save as…')
        save.clicked.connect(self.save_scheme)
        row.addWidget(save)
        reset = QPushButton('Reset to Default')
        reset.clicked.connect(self.reset_default)
        row.addWidget(reset)
        layout.addLayout(row)
        self.refresh_names()
        self.roles = QComboBox()
        for role, label in sorted(ROLE_LABELS.items(), key=lambda item: item[1].casefold()):
            self.roles.addItem(label, role)
        self.roles.setCurrentIndex(self.roles.findData('editor'))
        layout.addWidget(self.roles)
        channels = QHBoxLayout()
        self.controls = {}
        self.color_buttons = {}
        for kind, title in [('foreground', 'Character color'), ('background', 'Background color')]:
            group = QGroupBox(title)
            form = QFormLayout(group)
            button = QPushButton('Choose color…')
            button.clicked.connect(lambda checked=False, kind=kind: self.choose_color(kind))
            self.color_buttons[kind] = button
            form.addRow(button)
            spins = []
            for channel in ['Red', 'Green', 'Blue', 'Alpha (0–255)']:
                spin = QSpinBox()
                spin.setRange(0, 255)
                spin.setAccessibleName(f'{title} {channel}')
                spin.valueChanged.connect(self.changed)
                form.addRow(channel, spin)
                spins.append(spin)
            self.controls[kind] = spins
            channels.addWidget(group)
        layout.addLayout(channels)
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel('Deepest child opacity'))
        self.child_opacity = QSlider(Qt.Orientation.Horizontal)
        self.child_opacity.setRange(0, 100)
        self.child_opacity.setAccessibleName('Deepest child opacity')
        self.child_opacity.setToolTip('Percentage of current-row alpha at the deepest child; the selected parent stays at 100%.')
        self.child_opacity.valueChanged.connect(self.opacity_changed)
        opacity_row.addWidget(self.child_opacity, 1)
        self.child_opacity_value = QLabel()
        self.child_opacity_value.setMinimumWidth(40)
        opacity_row.addWidget(self.child_opacity_value)
        layout.addLayout(opacity_row)
        pulse_row = QHBoxLayout()
        pulse_row.addWidget(QLabel('Pulse speed (cycles/minute)'))
        self.pulse_speed = QSlider(Qt.Orientation.Horizontal)
        self.pulse_speed.setRange(0, 100)
        self.pulse_speed.setAccessibleName('Correlation pulse speed in cycles per minute; zero is Off')
        self.pulse_speed.setToolTip('0 = Off; 1–100 cycles/minute (60–0.6 seconds per cycle).')
        self.pulse_speed.valueChanged.connect(self.pulse_speed_changed)
        pulse_row.addWidget(self.pulse_speed, 1)
        self.pulse_speed_value = QLabel()
        pulse_row.addWidget(self.pulse_speed_value)
        layout.addLayout(pulse_row)
        hint = QLabel('Alpha: 0 = transparent, 255 = opaque. Current row character alpha 0 preserves syntax colors.\nChanges appear live in every open tab. Cancel restores the last applied colors.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.preview = SourceEditor()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(190)
        self.preview.setPlainText('Scope: file\n- Ordinary prose [Source]\n1. First step\nP0. Important\n=> Parse [Source] AS [Parsed] ↳\n"""\nLiteral contents\n"""\nAll files/*\nField: `message`\n=> Set `status` to "complete"')
        self.preview.appendPlainText('Please recieve text')
        self.preview.context_highlight = (0, self.preview.document().findBlockByNumber(2).position())
        self.preview.context_depths = {0: 0, 1: 1, 2: 2}
        self.highlighter = _CoreHighlighter(self.preview)
        model = LanguageCore.parse_document(LanguageCore.open_source(self.preview.toPlainText(), arcgrav_version=window.version))
        self.highlighter.update_model(model)
        layout.addWidget(self.preview, 1)
        self.message = QLabel(f'Schemes: {self.store.directory}')
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(self.message.textInteractionFlags())
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply_scheme)
        buttons.accepted.connect(self.accept_scheme)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.roles.currentIndexChanged.connect(self.populate_role)
        self.populate_role()
        self.update_preview()

    def refresh_names(self):
        self.schemes.clear()
        try:
            self.schemes.addItems(self.store.names())
        except OSError as error:
            QMessageBox.warning(self, 'Could not list schemes', str(error))
        index = self.schemes.findText(self.scheme_name)
        self.schemes.setCurrentIndex(max(0, index))

    def populate_role(self):
        style = self.working[self.roles.currentData()]
        pulse = self.roles.currentData() == 'correlation_pulse'
        spelling = self.roles.currentData() == 'spelling_underline'
        viewport = self.roles.currentData() == 'map_viewport'
        foreground = self.color_buttons['foreground'].parentWidget()
        background = self.color_buttons['background'].parentWidget()
        foreground.setTitle('Border color' if viewport else 'Underline color' if spelling else 'Character color')
        background.setTitle('Fill color' if viewport else 'Background color')
        for kind, group in (('foreground', foreground), ('background', background)):
            for spin, channel in zip(self.controls[kind], ['Red', 'Green', 'Blue', 'Alpha (0–255)']):
                spin.setAccessibleName(f'{group.title()} {channel}')
        self.color_buttons['background'].parentWidget().setEnabled(not spelling)
        self.color_buttons['background'].parentWidget().setToolTip(
            'Spelling changes underline color only; text and background colors are preserved.' if spelling else '')
        self.color_buttons['foreground'].parentWidget().setEnabled(not pulse)
        self.color_buttons['foreground'].parentWidget().setToolTip(
            'Pulse changes background only; syntax character colors are preserved.' if pulse else '')
        for kind, spins in self.controls.items():
            for spin, value in zip(spins, style[kind]):
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        self.update_swatches()

    def update_swatches(self):
        for kind, button in self.color_buttons.items():
            color = self.working[self.roles.currentData()][kind]
            button.setText('Choose color…  #' + ''.join(f'{c:02X}' for c in color[:3]))

    def changed(self):
        self.working[self.roles.currentData()] = {kind: [spin.value() for spin in spins] for kind, spins in self.controls.items()}
        self.scheme_name = 'Custom'
        self.update_swatches()
        self.update_preview()

    def choose_color(self, kind):
        before = deepcopy(self.working)
        before_name = self.scheme_name
        picker = QColorDialog(QColor(*self.working[self.roles.currentData()][kind]), self)
        title = self.color_buttons[kind].parentWidget().title().lower()
        picker.setWindowTitle('Choose ' + title)
        picker.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        picker.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        # Switching away from a platform-native dialog can reset its controls.
        picker.setCurrentColor(QColor(*before[self.roles.currentData()][kind]))
        def live_color(value):
            for spin, channel in zip(self.controls[kind], value.getRgb()):
                spin.blockSignals(True)
                spin.setValue(channel)
                spin.blockSignals(False)
            self.changed()
        picker.currentColorChanged.connect(live_color)
        if picker.exec() != QDialog.DialogCode.Accepted:
            self.working, self.scheme_name = before, before_name
            self.populate_role()
            self.update_preview()

    def reject(self):
        self.window.apply_color_scheme(self.applied_scheme, self.applied_name)
        super().reject()

    def opacity_changed(self, value):
        self.working['deepest_child_opacity'] = value
        self.scheme_name = 'Custom'
        self.update_preview()

    def pulse_speed_changed(self, value):
        self.working['pulse_cycles_per_minute'] = value
        self.scheme_name = 'Custom'
        self.update_preview()

    def update_preview(self):
        pulse_blocker = QSignalBlocker(self.pulse_speed)
        speed = self.working['pulse_cycles_per_minute']
        self.pulse_speed.setValue(speed)
        self.pulse_speed_value.setText(f'{speed} cycles/min' if speed else 'Off')
        blocker = QSignalBlocker(self.child_opacity)
        value = self.working['deepest_child_opacity']
        self.child_opacity.setValue(value)
        self.child_opacity_value.setText(f'{value}%')
        self.window.apply_color_scheme(self.working, self.scheme_name)
        self.preview.apply_color_scheme(self.working)
        self.highlighter.apply_color_scheme(self.working)
        spelling_start = self.preview.toPlainText().index('recieve')
        self.preview.set_spelling_ranges(((spelling_start, spelling_start + 7, 'Spelling underline preview'),))

    def load_scheme(self):
        name = self.schemes.currentText()
        try:
            scheme = self.store.load(name)
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, 'Could not load scheme', str(error))
            return
        self.working, self.scheme_name = scheme, name
        self.populate_role()
        self.update_preview()

    def reset_default(self):
        try:
            scheme = self.store.load('Default')
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, 'Could not load Default', str(error))
            return
        self.working, self.scheme_name = scheme, 'Default'
        self.schemes.setCurrentIndex(0)
        self.populate_role()
        self.update_preview()

    def save_scheme(self):
        name, okay = QInputDialog.getText(self, 'Save color scheme', 'Scheme name:', text='' if self.scheme_name == 'Custom' else self.scheme_name)
        if not okay:
            return
        try:
            path = self.store.path(name)
            if path.exists() and QMessageBox.question(self, 'Replace scheme?', f'Replace {name}?') != QMessageBox.StandardButton.Yes:
                return
            self.store.save(name, self.working)
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, 'Could not save scheme', str(error))
            return
        self.scheme_name = name
        self.refresh_names()
        self.message.setText(f'Saved {path}. Use Apply to select this scheme.')

    def apply_scheme(self):
        try:
            self.store.select(self.scheme_name, self.working)
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, 'Could not apply scheme', f'The selection could not be saved. Live colors are temporary; Cancel restores the last applied scheme.\n{error}')
            return False
        self.window.apply_color_scheme(self.working, self.scheme_name)
        self.applied_scheme = deepcopy(self.working)
        self.applied_name = self.scheme_name
        self.message.setText(f'Applied {self.scheme_name} to all tabs and saved the selection.')
        return True

    def accept_scheme(self):
        if self.apply_scheme():
            self.accept()
