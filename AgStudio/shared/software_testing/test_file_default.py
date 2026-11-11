"""The shipped Default file is the sole default, independent of palette values."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from AgStudio.gui import color_schemes as schemes


class FileDefaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.colors = {role: {'foreground': [12, 34, 56, 255], 'background': [1, 2, 3, 0]}
                       for role in schemes.ROLE_LABELS}
        self.colors['deepest_child_opacity'] = 43
        self.colors['pulse_cycles_per_minute'] = 12
        self.write_default()
        patched = patch.object(schemes, 'SCHEME_DIRECTORY', self.root)
        patched.start()
        self.addCleanup(patched.stop)
        self.store = schemes.SchemeStore()

    def write_default(self):
        (self.root / 'Default.json').write_text(json.dumps(
            {'version': 1, 'name': 'Default', 'colors': self.colors}))

    def test_load_reloads_file_and_returns_independent_colors(self):
        self.assertEqual(schemes.default_scheme(), self.colors)
        loaded = schemes.default_scheme()
        loaded['editor']['foreground'][0] = 99
        self.assertEqual(schemes.default_scheme(), self.colors)
        self.colors['editor']['foreground'] = [9, 8, 7, 6]
        self.colors['deepest_child_opacity'] = 71
        self.write_default()
        self.assertEqual(self.store.load('Default'), self.colors)
        self.assertEqual(self.store.selected(), ('Default', self.colors, None))

    def test_default_selection_follows_file_custom_is_preserved(self):
        self.store.select('Default', self.colors)
        self.colors['deepest_child_opacity'] += 1
        self.write_default()
        self.assertEqual(self.store.selected(), ('Default', self.colors, None))
        self.store.save('My custom', self.colors)
        self.store.select('My custom', self.colors)
        custom = self.store.selected()[1]
        saved = (self.root / 'My custom.json').read_bytes()
        self.colors['deepest_child_opacity'] += 1
        self.write_default()
        self.assertEqual(self.store.selected(), ('My custom', custom, None))
        self.assertEqual((self.root / 'My custom.json').read_bytes(), saved)
        self.assertEqual(self.store.names(), ['Default', 'My custom'])
        with self.assertRaises(FileNotFoundError):
            self.store.load('Base')

    def test_missing_corrupt_and_incomplete_default_fail_explicitly(self):
        path = self.root / 'Default.json'
        for content in (None, '{', '{}', json.dumps({'version': 1, 'name': 'Default', 'colors': {}})):
            if content is None:
                path.unlink()
            else:
                path.write_text(content)
            with self.assertRaisesRegex(ValueError, 'Restore a valid Default.json'):
                schemes.default_scheme()
            with self.assertRaisesRegex(ValueError, 'Default.json'):
                self.store.selected()
        self.write_default()
        (self.root / 'selected.json').write_text('{')
        name, colors, warning = self.store.selected()
        self.assertEqual((name, colors), ('Default', self.colors))
        self.assertTrue(warning)

    def test_legacy_missing_fields_inherit_file_without_overriding_existing_colors(self):
        old = {role: value for role, value in self.colors.items()
               if role not in {'backtick', 'backtick_content', 'deepest_child_opacity'}}
        old['symbol'] = {'foreground': [91, 92, 93, 255], 'background': [0, 0, 0, 0]}
        result = schemes.validate_scheme(old)
        self.assertEqual(result['symbol'], old['symbol'])
        for role in ('backtick', 'backtick_content', 'deepest_child_opacity'):
            self.assertEqual(result[role], self.colors[role])
        self.assertNotIn('backtick', old)

    def test_default_atomic_overwrite_reload_and_failure(self):
        original = (self.root / 'Default.json').read_bytes()
        changed = schemes.default_scheme()
        changed['deepest_child_opacity'] = 72
        with patch('AgStudio.gui.color_schemes.os.replace', side_effect=OSError('write blocked')):
            with self.assertRaises(OSError):
                self.store.save('Default', changed)
        self.assertEqual((self.root / 'Default.json').read_bytes(), original)
        self.assertFalse(list(self.root.glob('.scheme-*')))
        self.store.save('Default', changed)
        self.assertEqual(schemes.default_scheme(), changed)
        self.assertEqual(schemes.SchemeStore().load('Default'), changed)
        self.store.select('Default', changed)
        self.assertEqual(schemes.SchemeStore().selected(), ('Default', changed, None))

    def test_base_has_no_special_redirect_or_hidden_handling(self):
        self.assertNotIn('Base', self.store.names())
        with self.assertRaises(FileNotFoundError):
            self.store.load('Base')
        custom = schemes.default_scheme()
        custom['deepest_child_opacity'] = 12
        self.store.save('Base', custom)
        self.store.select('Base', custom)
        self.assertIn('Base', self.store.names())
        self.assertEqual(self.store.load('Base'), custom)
        self.assertEqual(self.store.selected(), ('Base', custom, None))

    def test_injected_directory_default_is_consistent_and_corruption_is_not_hidden(self):
        alternate = schemes.SchemeStore(self.root / 'alternate')
        canonical_bytes = (self.root / 'Default.json').read_bytes()
        # An empty alternate store starts from the canonical file, without copying it.
        self.assertEqual(alternate.load('Default'), self.colors)
        self.assertFalse(alternate.path('Default').exists())
        changed = schemes.default_scheme()
        changed['deepest_child_opacity'] = 19
        alternate.save('Default', changed)
        alternate.select('Default', changed)
        fresh = schemes.SchemeStore(alternate.directory)
        self.assertEqual(fresh.load('Default'), changed)
        self.assertEqual(fresh.selected(), ('Default', changed, None))
        self.assertEqual((self.root / 'Default.json').read_bytes(), canonical_bytes)
        fresh.path('Default').write_text('{')
        for load in (lambda: fresh.load('Default'), fresh.selected):
            with self.assertRaisesRegex(ValueError, 'alternate/Default.json'):
                load()
        # Missing files follow the explicit canonical-file fallback, never built-in colors.
        fresh.path('Default').unlink()
        self.assertEqual(fresh.load('Default'), self.colors)
        (self.root / 'Default.json').unlink()
        with self.assertRaisesRegex(ValueError, 'Restore a valid Default.json'):
            fresh.load('Default')
