"""Review persistent user spelling vocabulary without editing document text."""
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QMessageBox, QPlainTextEdit, QVBoxLayout


class SpellingVocabularyDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.expected = (set(store.accepted), set(store.ignored))
        self.setWindowTitle('User spelling vocabulary')
        self.resize(580, 520)
        layout = QVBoxLayout(self)
        note = QLabel('One word per line; matching ignores case. Both lists apply to all documents and persist across restarts.\nRemove an entry to check it again, then Save.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.accepted_words = QPlainTextEdit('\n'.join(sorted(store.accepted)))
        self.ignored_words = QPlainTextEdit('\n'.join(sorted(store.ignored)))
        for label, editor in (('Accepted words — user dictionary', self.accepted_words),
                              ('Ignored words — persistent spelling exceptions', self.ignored_words)):
            layout.addWidget(QLabel(label))
            editor.setAccessibleName(label)
            layout.addWidget(editor)
        location = QLabel(str(store.path) if store.path is not None else 'Memory only (isolated profile)')
        location.setWordWrap(True)
        layout.addWidget(location)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        def lines(editor):
            return [word.strip() for word in editor.toPlainText().splitlines() if word.strip()]
        if not self.store.update(accepted=lines(self.accepted_words), ignored=lines(self.ignored_words), expected=self.expected):
            QMessageBox.warning(self, 'Could not save spelling vocabulary', self.store.error)
            return
        self.accept()
