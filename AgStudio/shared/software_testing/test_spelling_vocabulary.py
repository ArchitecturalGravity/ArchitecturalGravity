"""User vocabulary is explicit, persistent, case-insensitive and revision-safe."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from AgStudio.shared.lint import analyze, spelling

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def flagged(source, **options):
    return [f.source_range.span.extract(source) for f in analyze(source, **options).diagnostics.findings
            if f.rule_id == 'AG-SPELLING']


class VocabularyEngineTests(unittest.TestCase):
    def test_technical_supplement_and_capitalized_typos(self):
        for word in spelling.TECHNICAL_WORDS:
            with self.subTest(word=word):
                self.assertFalse(flagged('- ' + ' '.join((word, word.title(), word.upper())) + '\n'))
        source = '- mispelled Mispelled MISPELLED QZXV runtmie\n'
        self.assertEqual(flagged(source), ['mispelled', 'Mispelled', 'MISPELLED', 'QZXV', 'runtmie'])

    def test_explicit_words_normalization_possessives_and_no_cache_leak(self):
        source = '- zorbular Zorbular ZORBULAR Zorbular’s\n'
        self.assertEqual(len(flagged(source)), 4)  # Cache the unknown base first.
        self.assertFalse(flagged(source, configuration={'spelling_words': ['ZORBULAR']}))
        self.assertEqual(len(flagged(source)), 4)
        self.assertFalse(flagged('- naïve\n', configuration={'spelling_words': ['NAI\u0308VE']}))
        self.assertEqual(flagged('- mispelled\n', configuration={'spellcheck': False,
                                                               'spelling_words': ['zorbular']}), [])

    def test_invalid_configuration_entries_are_not_patterns_or_paths(self):
        for value in ('mispelled', {'mispelled': True}, [None, 3, '*', '/tmp/words', 'two words'],
                      ['mispelled'] * 20001):
            self.assertEqual(flagged('- mispelled\n', configuration={'spelling_words': value}), ['mispelled'])
        with patch('builtins.open', side_effect=AssertionError('no document-selected files')):
            self.assertFalse(flagged('- Zorbular\n', configuration={'spelling_words': ['zorbular']}))

    def test_protected_syntax_and_unavailable_backend_remain_safe(self):
        source = '- `mispelled` "mispelled" [Mispelled] obj.mispelled snake_mispelled camelMispelled\n'
        self.assertFalse(flagged(source, configuration={'spelling_words': []}))
        with patch.object(spelling, '_CHECKER', None):
            self.assertFalse([f for f in analyze('- runtime Zorbular\n', configuration={'spelling_words': ['zorbular']}).diagnostics.findings if f.rule_id in spelling.SPELLING_MESSAGES])
            findings = analyze('- runtime mispelled\n').diagnostics.findings
            self.assertTrue(any(f.rule_id == 'AG-SPELLCHECK-UNAVAILABLE' for f in findings))


class VocabularyStoreTests(unittest.TestCase):
    def setUp(self):
        from AgStudio.gui.spelling_vocabulary import SpellingVocabularyStore
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'user.spelling.json'
        self.store = SpellingVocabularyStore(path=self.path)

    def test_explicit_additions_are_separate_persistent_and_normalized(self):
        from AgStudio.gui.spelling_vocabulary import SpellingVocabularyStore
        self.assertFalse(self.path.exists())
        self.assertTrue(self.store.update(add='ZORBULAR'))
        self.assertTrue(self.store.update(add='Blorptastic', scope='ignored'))
        self.assertTrue(self.store.update(add='Zorbular'))
        restored = SpellingVocabularyStore(path=self.path)
        self.assertEqual(restored.accepted, {'zorbular'})
        self.assertEqual(restored.ignored, {'blorptastic'})
        self.assertEqual(restored.words, ['blorptastic', 'zorbular'])
        self.assertEqual(json.loads(self.path.read_text())['version'], 1)

    def test_invalid_files_remain_byte_exact_and_keep_last_good_memory(self):
        self.store.update(add='zorbular')
        for data in (b'{', b'\xff', b'[]', b'{"version":true}', b'{"version":2}',
                     b'{"version":1,"accepted":["two words"],"ignored":[]}',
                     b'{"version":1,"accepted":[],"ignored":"all"}',
                     b'{"version":1,"accepted":[],"accepted":["lost"],"ignored":[]}'):
            with self.subTest(data=data):
                self.path.write_bytes(data)
                self.assertFalse(self.store.reload())
                self.assertEqual(self.store.accepted, {'zorbular'})
                self.assertFalse(self.store.update(add='another'))
                self.assertEqual(self.path.read_bytes(), data)

    def test_large_and_non_regular_files_are_rejected(self):
        self.path.write_bytes(b' ' * (1024 * 1024 + 1))
        self.assertFalse(self.store.reload())
        self.assertFalse(self.store.update(add='zorbular'))
        self.path.unlink()
        self.path.mkdir()
        self.assertFalse(self.store.reload())
        self.assertFalse(self.store.update(add='zorbular'))
        self.path.rmdir()
        target = self.path.with_name('target.json')
        target.write_text('{"version":1,"accepted":[],"ignored":[]}')
        self.path.symlink_to(target)
        self.assertFalse(self.store.reload())
        self.assertFalse(self.store.update(add='zorbular'))
        self.assertEqual(json.loads(target.read_text())['accepted'], [])

    def test_atomic_write_failures_preserve_file_and_memory(self):
        self.store.update(add='zorbular')
        before = self.path.read_bytes()
        for failed_stage in ('open', 'write', 'commit'):
            with self.subTest(stage=failed_stage), patch('AgStudio.gui.spelling_vocabulary.QSaveFile') as factory:
                target = factory.return_value
                target.open.return_value = failed_stage != 'open'
                target.write.side_effect = lambda data: -1 if failed_stage == 'write' else len(data)
                target.commit.return_value = failed_stage != 'commit'
                target.errorString.return_value = 'read only'
                self.assertFalse(self.store.update(add='blorptastic'))
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(self.store.words, ['zorbular'])

    def test_merge_unknown_fields_lock_and_whole_list_conflict(self):
        from PySide6.QtCore import QLockFile
        from AgStudio.gui.spelling_vocabulary import SpellingVocabularyStore
        self.path.write_text('{"version":1,"accepted":[],"ignored":[],"extra":{"keep":true}}')
        other = SpellingVocabularyStore(path=self.path)
        self.store.update(add='zorbular')
        self.assertTrue(other.update(add='blorptastic', scope='ignored'))
        self.assertTrue(json.loads(self.path.read_text())['extra']['keep'])
        self.assertEqual(other.words, ['blorptastic', 'zorbular'])
        before = self.path.read_bytes()
        self.assertFalse(self.store.update(accepted=[], ignored=[], expected=(set(), set())))
        self.assertEqual(self.path.read_bytes(), before)
        lock = QLockFile(str(self.path) + '.lock')
        self.assertTrue(lock.tryLock(0))
        try:
            self.assertFalse(self.store.update(add='other'))
            self.assertEqual(self.path.read_bytes(), before)
        finally:
            lock.unlock()

    def test_read_only_file_and_settings_are_preserved(self):
        from PySide6.QtCore import QSettings
        from AgStudio.gui.spelling_vocabulary import SpellingVocabularyStore
        settings = QSettings(str(self.path.with_name('prefs.ini')), QSettings.Format.IniFormat)
        settings.setValue('existing', 'preserve')
        settings.sync()
        store = SpellingVocabularyStore(settings)
        self.assertEqual(str(store.path), settings.fileName() + '.spelling.json')
        store.update(add='zorbular')
        before = store.path.read_bytes()
        store.path.chmod(0o444)
        try:
            self.assertFalse(store.update(add='another'))
            self.assertEqual(store.path.read_bytes(), before)
        finally:
            store.path.chmod(0o644)
        self.assertEqual(settings.allKeys(), ['existing'])
        self.assertEqual(settings.value('existing'), 'preserve')

    def test_memory_adapter_and_invalid_additions(self):
        from AgStudio.gui.spelling_vocabulary import SpellingVocabularyStore
        memory = SpellingVocabularyStore()
        self.assertTrue(memory.update(add='zorbular'))
        self.assertTrue(memory.reload())
        self.assertEqual(memory.words, ['zorbular'])
        for word in ('', 'two words', '../words', '*', 'x' * 129):
            self.assertFalse(memory.update(add=word))
            self.assertEqual(memory.words, ['zorbular'])
        self.assertFalse(self.path.exists())


class VocabularyGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from AgStudio.gui.spelling_vocabulary import SpellingVocabularyStore
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = SpellingVocabularyStore(path=self.root / 'user.spelling.json')
        self.windows = []
        self.addCleanup(self.dispose)

    def dispose(self):
        for window in self.windows:
            for i in range(window.tabs.count()):
                window.tabs.widget(i).dispose_analysis()
            window.deleteLater()
        self.app.processEvents()

    def window(self, *, background=False, store=None):
        from AgStudio.gui.app import StudioWindow
        from AgStudio.gui.color_schemes import SchemeStore
        from AgStudio.gui.user_state import UserState
        state = UserState()
        state.set_panel('document_map', False)
        window = StudioWindow('current', background=background, user_state=state,
                              scheme_store=SchemeStore(self.root / 'colors'),
                              vocabulary_store=store if store is not None else self.store)
        self.windows.append(window)
        window.show()
        self.app.processEvents()
        return window

    def wait_for(self, predicate):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + 15
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertTrue(predicate(), 'Timed out waiting for background vocabulary update')

    def action(self, tab, label, word='zorbular'):
        position = tab.editor.toPlainText().lower().index(word)
        menu = tab.editor.spelling_context_menu(position)
        self.addCleanup(menu.deleteLater)
        return next(action for action in menu.actions() if action.text() == label)

    def test_add_and_ignore_refresh_tabs_windows_and_persist_without_text_edits(self):
        from AgStudio.gui.spelling_vocabulary import SpellingVocabularyStore
        window = self.window()
        first = window.current()
        first.editor.setPlainText('- zorbular ZORBULAR blorptastic mispelled\n')
        other_tab = window.new_document()
        other_tab.editor.setPlainText(first.source)
        other_window = self.window(store=SpellingVocabularyStore(path=self.store.path))
        other_window.current().editor.setPlainText(first.source)
        before = (first.source, first.dirty, first.editor.document().availableUndoSteps(),
                  first.editor.textCursor().position(), first.editor.textCursor().anchor())
        old_action = self.action(first, 'Add to user dictionary')
        old_action.trigger()
        old_action.trigger()  # Stale action must not write or affect remaining words.
        self.action(first, 'Ignore word for this user (persistent)', 'blorptastic').trigger()
        for tab in (first, other_tab, other_window.current()):
            self.assertEqual([f.source_range.span.extract(tab.source) for f in tab.diagnostics.findings
                              if f.rule_id == 'AG-SPELLING'], ['mispelled'])
        self.assertEqual(before, (first.source, first.dirty, first.editor.document().availableUndoSteps(),
                                 first.editor.textCursor().position(), first.editor.textCursor().anchor()))
        persisted = SpellingVocabularyStore(path=self.store.path)
        self.assertEqual(persisted.accepted, {'zorbular'})
        self.assertEqual(persisted.ignored, {'blorptastic'})
        restarted = self.window(store=persisted).current()
        restarted.editor.setPlainText(first.source)
        self.assertEqual(len(restarted.editor._spelling_ranges), 1)
        self.assertEqual(set(json.loads(self.store.path.read_text())), {'version', 'accepted', 'ignored'})

    def test_stale_and_read_only_menus_do_not_add_words(self):
        window = self.window()
        tab = window.current()
        tab.editor.setPlainText('- zorbular\n')
        action = self.action(tab, 'Add to user dictionary')
        tab.editor.insertPlainText('new ')
        action.trigger()
        self.assertFalse(self.store.path.exists())
        tab.editor.setReadOnly(True)
        menu = tab.editor.spelling_context_menu(2)
        self.addCleanup(menu.deleteLater)
        self.assertNotIn('Add to user dictionary', [a.text() for a in menu.actions()])

    def test_dialog_removal_cancel_conflict_and_write_failure(self):
        from AgStudio.gui.spelling_vocabulary_dialog import SpellingVocabularyDialog
        from PySide6.QtWidgets import QMessageBox
        window = self.window()
        window.current().editor.setPlainText('- zorbular blorptastic\n')
        self.store.update(add='zorbular')
        self.store.update(add='blorptastic', scope='ignored')
        window._broadcast_spelling_vocabulary()
        dialog = SpellingVocabularyDialog(self.store, window)
        self.addCleanup(dialog.deleteLater)
        dialog.accepted_words.setPlainText('')
        dialog.reject()
        self.assertIn('zorbular', self.store.words)
        dialog = SpellingVocabularyDialog(self.store, window)
        self.addCleanup(dialog.deleteLater)
        dialog.accepted_words.setPlainText('')
        dialog.ignored_words.setPlainText('')
        dialog.save()
        window._broadcast_spelling_vocabulary()
        self.assertEqual(len(window.current().editor._spelling_ranges), 2)
        dialog = SpellingVocabularyDialog(self.store, window)
        self.addCleanup(dialog.deleteLater)
        self.store.update(add='zorbular')
        with patch.object(QMessageBox, 'warning') as warning:
            dialog.save()
        warning.assert_called_once()
        self.assertIn('zorbular', self.store.words)
        self.store.path.write_text('{broken')
        with patch.object(QMessageBox, 'warning') as warning:
            window._add_spelling_word('accepted', 'blorptastic')
        warning.assert_called_once()
        self.assertEqual(self.store.path.read_text(), '{broken')

    def test_finding_context_menu_and_invalid_startup_dictionary(self):
        from PySide6.QtCore import QPoint
        self.store.path.write_text('{invalid')
        self.store.reload()
        window = self.window()
        self.assertIn('Could not load user spelling vocabulary', window.statusBar().currentMessage())
        tab = window.current()
        tab.editor.setPlainText('Task:\n- zorbular\n')
        self.assertEqual(len(tab.editor._spelling_ranges), 1)
        self.assertEqual(self.store.path.read_text(), '{invalid')
        self.store.path.unlink()
        window._refresh_spelling_vocabulary()
        row = next(tab.diagnostic_list.topLevelItem(i) for i in range(tab.diagnostic_list.topLevelItemCount())
                   if tab.diagnostic_list.topLevelItem(i).text(1) == 'AG-SPELLING')
        def choose(menu, point):
            next(a for a in menu.actions() if a.text() == 'Add to user dictionary').trigger()
        original_menu = tab.editor.spelling_context_menu
        def build_menu(*args, **kwargs):
            menu = original_menu(*args, **kwargs)
            menu.exec = lambda point: choose(menu, point)
            return menu
        with patch.object(tab.diagnostic_list, 'itemAt', return_value=row), patch.object(
                tab.editor, 'spelling_context_menu', side_effect=build_menu):
            tab._spelling_finding_menu(QPoint())
        self.assertEqual(self.store.accepted, {'zorbular'})
        self.assertFalse(tab.editor._spelling_ranges)
        self.assertEqual(tab.source, 'Task:\n- zorbular\n')

    def test_background_revisions_use_current_vocabulary_and_removals(self):
        window = self.window(background=True)
        tab = window.current()
        tab.editor.setPlainText('- zorbular Zorbular mispelled\n')
        self.wait_for(lambda: tab.diagnostics is not None and len(tab.editor._spelling_ranges) == 3)
        old_revision = tab.controller.revision
        old_analysis = tab.analysis
        self.action(tab, 'Add to user dictionary').trigger()
        self.assertGreater(tab.controller.revision, old_revision)
        tab._analysis_ready(old_revision, old_analysis)
        self.assertIsNone(tab.diagnostics)
        self.wait_for(lambda: tab.diagnostics is not None and len(tab.editor._spelling_ranges) == 1)
        self.assertEqual(tab.document.session.configuration['spelling_words'], ['zorbular'])
        self.assertTrue(self.store.update(accepted=[], ignored=[]))
        window._broadcast_spelling_vocabulary()
        self.wait_for(lambda: tab.diagnostics is not None and len(tab.editor._spelling_ranges) == 3)
        self.assertEqual(tab.source, '- zorbular Zorbular mispelled\n')
