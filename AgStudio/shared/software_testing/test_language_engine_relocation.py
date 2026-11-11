"""Source-layout/import identity contracts for the engine inside AgStudio."""
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[3]


class LanguageEngineRelocationTests(unittest.TestCase):
    def run_source(self, source):
        result = subprocess.run(
            [sys.executable, '-I', '-c',
             f'import sys; sys.path.insert(0, {str(ROOT)!r})\n' + textwrap.dedent(source)],
            cwd=ROOT.parent, text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_implementation_exists_only_under_studio(self):
        self.assertFalse((ROOT / 'arcgrav_language_engine').exists())
        self.assertFalse((ROOT / 'arcgrav_language_engine.py').exists())
        self.assertTrue((ROOT / 'AgStudio/arcgrav_language_engine/api.py').is_file())
        self.assertTrue((ROOT / 'AgStudio/arcgrav_language_engine/pyproject.toml').is_file())
        self.assertFalse((ROOT / 'pyproject.toml').exists())
        for name in ('__init__.py', '__main__.py', 'pyproject.toml'):
            self.assertFalse((ROOT / 'AgStudio' / name).exists())

    def test_namespace_import_does_not_activate_engine_or_gui(self):
        self.run_source("""
            before = list(sys.meta_path)
            import AgStudio
            assert AgStudio.__spec__.origin is None
            assert list(sys.meta_path) == before
            assert 'arcgrav_language_engine' not in sys.modules
            assert 'AgStudio.arcgrav_language_engine' not in sys.modules
            assert not any(name.startswith(('AgStudio.gui', 'AgStudio.shared', 'PySide', 'PyQt'))
                           for name in sys.modules)
        """)

    def test_source_entrypoint_is_lazy_and_keeps_public_pickle_names(self):
        self.run_source('''
            import AgStudio.arcgrav_language_engine as engine
            assert engine.__name__ == 'arcgrav_language_engine'
            assert engine.AnalysisContext.__module__ == 'arcgrav_language_engine.context'
            assert not any(name.startswith(('AgStudio.gui', 'AgStudio.shared', 'PySide', 'PyQt'))
                           for name in sys.modules)
            context = engine.AnalysisContext(arcgrav_version='current', configuration={'spellcheck': False})
            snapshot = engine.prepare('=> - Read text\\r\\n', context)
            assert snapshot.__class__.__module__ == 'arcgrav_language_engine.snapshot'
            for suffix in ('lint.findings', 'lint.rules', 'lint.spelling'):
                assert 'arcgrav_language_engine.' + suffix not in sys.modules
                assert 'AgStudio.arcgrav_language_engine.' + suffix not in sys.modules
            import pickle
            assert pickle.loads(pickle.dumps(snapshot)) == snapshot
            assert engine.diagnose(snapshot).status == 'evaluated'
        ''')

    def test_all_engine_modules_share_identity_in_both_import_orders(self):
        modules = tuple(sorted(
            '.'.join(path.relative_to(ROOT / 'AgStudio').with_suffix('').parts)
            .removesuffix('.__init__')
            for path in (ROOT / 'AgStudio/arcgrav_language_engine').rglob('*.py')
        ))
        for first in ('canonical', 'standalone', 'legacy'):
            with self.subTest(first=first):
                self.run_source(f'''
                    import importlib
                    import pathlib
                    import sys
                    before_path = list(sys.path)
                    if {first!r} == 'standalone':
                        sys.path.insert(0, {str(ROOT / 'AgStudio')!r})
                        import arcgrav_language_engine
                        sys.path.pop(0)
                    elif {first!r} == 'legacy':
                        import AgStudio.shared.core
                    else:
                        import AgStudio.arcgrav_language_engine.lint.model
                    import AgStudio.arcgrav_language_engine as engine
                    for name in {modules!r}:
                        standalone = importlib.import_module(name)
                        canonical = importlib.import_module('AgStudio.' + name)
                        assert standalone is canonical, name
                        assert canonical.__name__ == name, name
                        assert canonical.__spec__.name == name, name
                        assert pathlib.Path(canonical.__file__).resolve().is_relative_to(
                            pathlib.Path({str(ROOT / 'AgStudio/arcgrav_language_engine')!r})), name
                    assert sys.path == before_path
                    from AgStudio.shared.core import LanguageCore
                    from AgStudio.arcgrav_language_engine.core import LanguageCore as CanonicalCore
                    assert LanguageCore is CanonicalCore is engine.LanguageCore
                    assert not any(name.startswith(('AgStudio.gui', 'PySide', 'PyQt')) for name in sys.modules)
                ''')

    def test_preimport_specs_retain_package_and_origin_metadata(self):
        self.run_source(f"""
            import importlib.util
            from pathlib import Path
            root = Path({str(ROOT / 'AgStudio/arcgrav_language_engine')!r})
            for suffix, relative, is_package in (
                ('', '__init__.py', True),
                ('.recognition', 'recognition/__init__.py', True),
                ('.recognition.source', 'recognition/source.py', False),
            ):
                name = 'AgStudio.arcgrav_language_engine' + suffix
                assert name not in sys.modules
                spec = importlib.util.find_spec(name)
                assert spec.name == name
                assert Path(spec.origin) == root / relative
                assert (spec.submodule_search_locations is not None) == is_package
                assert name not in sys.modules
            assert importlib.util.find_spec('AgStudio.arcgrav_language_engine.not_a_module') is None
            assert 'arcgrav_language_engine.lint.findings' not in sys.modules
        """)

    def test_reload_and_package_resources_keep_stable_engine_spec(self):
        self.run_source('''
            import importlib
            import importlib.resources
            import AgStudio
            import AgStudio.arcgrav_language_engine as engine
            import AgStudio.arcgrav_language_engine.lint as lint
            from AgStudio.arcgrav_language_engine.context import AnalysisContext
            hook_count = len(sys.meta_path)
            importlib.reload(AgStudio)
            assert len(sys.meta_path) == hook_count
            assert importlib.reload(engine) is engine
            assert len(sys.meta_path) == hook_count
            assert engine.AnalysisContext is AnalysisContext
            assert lint.__spec__.name == 'arcgrav_language_engine.lint'
        ''')

    def test_conflicting_preloaded_installation_is_rejected_explicitly(self):
        self.run_source('''
            from types import ModuleType
            installed = ModuleType('arcgrav_language_engine')
            installed.__file__ = '/another-installation/arcgrav_language_engine/__init__.py'
            sys.modules['arcgrav_language_engine'] = installed
            try:
                import AgStudio.arcgrav_language_engine
            except ImportError as error:
                assert 'another installation' in str(error)
            else:
                raise AssertionError('Must not silently use an unrelated installed engine')
            assert sys.modules['arcgrav_language_engine'] is installed
        ''')


if __name__ == '__main__':
    unittest.main()
