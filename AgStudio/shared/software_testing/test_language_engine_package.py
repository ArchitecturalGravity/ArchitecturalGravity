"""Build and exercise the standalone wheel without checkout/Studio imports.

Install this directory's requirements.txt to make packaging verification
mandatory in CI. ARCGRAV_BUILD_PYTHON can select another build-only interpreter;
the consumer always runs in a fresh isolated virtual environment.
"""
from __future__ import annotations

from email.parser import Parser
import ast
import base64
import os
from pathlib import Path
import pickle
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import textwrap
import unittest
import venv
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[3]
STUDIO_ROOT = REPO_ROOT / 'AgStudio'


class StandaloneLanguageEnginePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = {
            key: value for key, value in os.environ.items()
            if key not in ('PYTHONPATH', 'PYTHONHOME')
        }
        cls.environment['PYTHONDONTWRITEBYTECODE'] = '1'
        cls.build_python = os.environ.get('ARCGRAV_BUILD_PYTHON', sys.executable)
        try:
            probe = subprocess.run(
                [cls.build_python, '-I', '-c', 'import setuptools, wheel, pip'],
                env=cls.environment, text=True, capture_output=True, timeout=30,
            )
        except OSError as exc:
            raise RuntimeError('ARCGRAV_BUILD_PYTHON must name a usable Python interpreter') from exc
        if probe.returncode:
            raise unittest.SkipTest(
                'Standalone wheel build needs pip, setuptools and wheel. Install '
                'AgStudio/shared/software_testing/requirements.txt or set '
                'ARCGRAV_BUILD_PYTHON to an interpreter with those build tools. '
                + probe.stderr.strip()
            )

        cls.temporary = TemporaryDirectory(prefix='arcgrav-standalone-wheel-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work = Path(cls.temporary.name).resolve()
        if cls.work.is_relative_to(REPO_ROOT):
            raise AssertionError('Standalone verification must run outside the checkout')
        cls.build_source = cls.work / 'source'
        # Build from the complete AgStudio project, not a curated engine-only
        # subset, so package discovery must exclude all Studio host modules.
        shutil.copytree(
            STUDIO_ROOT, cls.build_source,
            ignore=shutil.ignore_patterns(
                '__pycache__', '*.pyc', '.git', '.venv*', 'Runtime', 'build', 'dist', '*.egg-info',
            ),
        )
        for directory in (cls.build_source / 'Docs', cls.build_source / 'docs'):
            if directory.exists():
                shutil.rmtree(directory)
        for document in cls.build_source.rglob('*.md'):
            document.unlink()
        cls.wheels = cls.work / 'wheels'
        cls.wheels.mkdir()
        cls._run(
            [cls.build_python, '-I', '-m', 'pip', 'wheel', '--no-index',
             '--no-deps', '--no-build-isolation', '--wheel-dir', str(cls.wheels), '.'],
            cwd=cls.build_source / "arcgrav_language_engine",
        )
        built = list(cls.wheels.glob('*.whl'))
        if len(built) != 1:
            raise AssertionError(f'Expected exactly one engine wheel, got {built}')
        cls.wheel = built[0]

        cls.consumer = cls.work / 'consumer'
        cls.consumer.mkdir()
        cls.venv_root = cls.work / 'venv'
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(cls.venv_root)
        cls.python = cls.venv_root / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        cls._run(
            [str(cls.python), '-I', '-m', 'pip', 'install', '--no-index',
             '--no-deps', str(cls.wheel)], cwd=cls.consumer,
        )

    @classmethod
    def _run(cls, command, *, cwd):
        result = subprocess.run(
            command, cwd=cwd, env=cls.environment, text=True,
            capture_output=True, timeout=120,
        )
        if result.returncode:
            raise AssertionError(
                f'Command failed ({result.returncode}): {command!r}\n'
                f'{result.stdout}\n{result.stderr}'
            )
        return result

    def run_consumer(self, source):
        prelude = f'''
import importlib.util
import pathlib
import sys
for unavailable in ('AgStudio', 'PySide6', 'PyQt6', 'PyQt5', 'hunspell'):
    assert importlib.util.find_spec(unavailable) is None, unavailable
assert not any(pathlib.Path(p).resolve() == pathlib.Path({str(REPO_ROOT)!r})
               for p in sys.path if p)
import arcgrav_language_engine as engine
assert pathlib.Path(engine.__file__).resolve().is_relative_to(pathlib.Path({str(self.venv_root)!r}))
'''
        epilogue = '''
assert not any(name == 'AgStudio' or name.startswith(('AgStudio.', 'PySide', 'PyQt'))
               for name in sys.modules)
'''
        return self._run(
            [str(self.python), '-I', '-c', prelude + textwrap.dedent(source) + epilogue],
            cwd=self.consumer,
        )

    def test_wheel_contains_only_engine_and_fixed_metadata(self):
        with zipfile.ZipFile(self.wheel) as archive:
            names = archive.namelist()
            roots = {name.split('/')[0] for name in names}
            self.assertEqual(roots, {
                'arcgrav_language_engine', 'arcgrav_language_engine-0.2.0.dist-info',
            })
            self.assertIn('arcgrav_language_engine/__init__.py', names)
            source_modules = {
                'arcgrav_language_engine/' + path.relative_to(
                    STUDIO_ROOT / 'arcgrav_language_engine').as_posix()
                for path in (STUDIO_ROOT / 'arcgrav_language_engine').rglob('*.py')
                if not any(part in ('build', 'dist', '__pycache__') for part in path.parts)
            }
            self.assertEqual({name for name in names if name.endswith('.py')}, source_modules)
            self.assertFalse(any(name.endswith('/entry_points.txt') for name in names))
            for name in names:
                if name.startswith('arcgrav_language_engine/'):
                    self.assertTrue(
                        name.endswith(('.py', '.yaml')) or (
                            name.startswith('arcgrav_language_engine/lint/dictionaries/')
                            and (name.endswith(('.aff', '.dic', '.txt', '.md', '/SHA256SUMS'))
                                 or '/dictionaries/licenses/' in name)), name
                    )
                    if name.endswith('.py'):
                        module = ast.parse(archive.read(name), filename=name)
                        for node in ast.walk(module):
                            if isinstance(node, ast.Import):
                                imports = [alias.name for alias in node.names]
                            elif isinstance(node, ast.ImportFrom) and not node.level:
                                imports = [node.module or '']
                            else:
                                continue
                            self.assertFalse(any(
                                imported.split('.')[0] in ('AgStudio', 'PySide6', 'PyQt6', 'PyQt5')
                                for imported in imports
                            ), (name, imports))
            metadata = Parser().parsestr(archive.read(
                'arcgrav_language_engine-0.2.0.dist-info/METADATA').decode('utf-8'))
            self.assertEqual(metadata['Name'], 'arcgrav-language-engine')
            self.assertEqual(metadata['Version'], '0.2.0')
            self.assertEqual(metadata['Requires-Python'], '>=3.10')
            self.assertEqual(metadata.get_all('Provides-Extra'), ['spelling'])
            self.assertEqual(
                [value.replace(' ', '') for value in metadata.get_all('Requires-Dist', [])],
                ['chunspell==2.0.5;extra=="spelling"'],
            )

    def test_sdist_rebuilds_the_same_self_contained_wheel(self):
        sdists = self.work / 'sdists'
        sdists.mkdir()
        self._run(
            [self.build_python, '-I', '-c',
             'from setuptools.build_meta import build_sdist; '
             f'build_sdist({str(sdists)!r})'],
            cwd=self.build_source / 'arcgrav_language_engine',
        )
        archives = list(sdists.glob('*.tar.gz'))
        self.assertEqual(len(archives), 1)
        with tarfile.open(archives[0]) as archive:
            names = archive.getnames()
            self.assertTrue(any(name.endswith('/pyproject.toml') for name in names))
            self.assertFalse(any('/gui/' in name or '/shared/' in name for name in names))
        rebuilt = self.work / 'rebuilt'
        rebuilt.mkdir()
        self._run(
            [self.build_python, '-I', '-m', 'pip', 'wheel', '--no-index',
             '--no-deps', '--no-build-isolation', '--wheel-dir', str(rebuilt),
             str(archives[0])],
            cwd=self.consumer,
        )
        wheels = list(rebuilt.glob('*.whl'))
        self.assertEqual(len(wheels), 1)
        with zipfile.ZipFile(self.wheel) as direct, zipfile.ZipFile(wheels[0]) as rebuilt_wheel:
            direct_files = {name: direct.read(name) for name in direct.namelist()
                            if name.startswith('arcgrav_language_engine/')}
            rebuilt_files = {name: rebuilt_wheel.read(name) for name in rebuilt_wheel.namelist()
                             if name.startswith('arcgrav_language_engine/')}
            self.assertEqual(direct_files, rebuilt_files)

    def test_hunspell_resources_and_notices_are_shipped_byte_exact(self):
        source = STUDIO_ROOT / 'arcgrav_language_engine/lint/dictionaries'
        with zipfile.ZipFile(self.wheel) as archive:
            for resource in source.rglob('*'):
                if resource.is_file() and resource.suffix != '.md':
                    name = 'arcgrav_language_engine/lint/dictionaries/' + resource.relative_to(source).as_posix()
                    self.assertEqual(archive.read(name), resource.read_bytes(), name)
            self.assertIn(b'SET UTF-8', archive.read('arcgrav_language_engine/lint/dictionaries/en_US.aff'))

    def test_agent_reference_is_shipped_without_runtime_yaml_dependency(self):
        path = 'arcgrav_language_engine/arcgrav_agent_reference.yaml'
        with zipfile.ZipFile(self.wheel) as archive:
            names = archive.namelist()
            self.assertIn(path, names)
            raw = archive.read(path).decode('utf-8')
            self.assertIn('schema_version: 1', raw)
            self.assertIn('AG-OPERATION-LIST:', raw)
            self.assertIn('AG-SYNTAX-INCOMPLETE:', raw)
            self.assertNotIn('AGENTS.', raw)

        self.run_consumer(r'''
            import importlib.resources as resources
            from arcgrav_language_engine import AnalysisContext, analyze
            text = resources.files(engine).joinpath(
                'arcgrav_agent_reference.yaml'
            ).read_text(encoding='utf-8')
            assert 'AG-OPERATION-LIST:' in text
            assert 'AG-SYMBOL-UNUSED:' in text
            assert 'yaml' not in sys.modules
            result = analyze('Task:\n=> - Work\n',
                             AnalysisContext(arcgrav_version='current',
                                             configuration={'spellcheck': False}))
            assert any(f.rule_id == 'AG-OPERATION-LIST'
                       for f in result.diagnostics.findings)
            assert 'yaml' not in sys.modules
        ''')

    def test_external_consumer_uses_only_public_staged_and_sync_api(self):
        self.run_consumer(r'''
            from dataclasses import FrozenInstanceError
            from arcgrav_language_engine import (
                API_VERSION, PACKAGE_VERSION, LANGUAGE_CONTRACT_VERSION,
                SNAPSHOT_SCHEMA_VERSION, AnalysisContext, PreparedSnapshot,
                analyze, diagnose, prepare,
            )
            assert (PACKAGE_VERSION, API_VERSION, LANGUAGE_CONTRACT_VERSION,
                    SNAPSHOT_SCHEMA_VERSION) == ('0.2.0', '2', 'current', 2)
            context = AnalysisContext(arcgrav_version='current', configuration={'spellcheck': False})
            source = '- 🌍 Keep this text\r\n=> - Read [Missing]\r\n'
            snapshot = prepare(source, context)
            assert isinstance(snapshot, PreparedSnapshot)
            assert snapshot.diagnostics.status == 'pending'
            assert snapshot.diagnostics.findings == ()
            assert snapshot.schema_version == SNAPSHOT_SCHEMA_VERSION
            for deferred in ('lint.findings', 'lint.rules', 'lint.spelling'):
                assert 'arcgrav_language_engine.' + deferred not in sys.modules, deferred
            result = diagnose(snapshot)
            assert snapshot.diagnostics.status == 'pending'
            assert result == diagnose(snapshot)
            analysis = analyze(source, context)
            assert analysis.diagnostics == result
            assert analysis.document.source == source
            assert analysis.tree == snapshot.tree
            assert analysis.semantics == snapshot.semantics
            assert analysis.conformance == 'unknown'
            finding = next(f for f in result.findings
                           if f.rule_id == 'AG-OPERATION-LIST')
            start = source.index('=> - ')
            assert (finding.source_range.span.start, finding.source_range.span.end) == (start, start + 5)
            assert finding.source_range.span.extract(source) == '=> - '
            assert (finding.source_range.start.line, finding.source_range.start.column) == (2, 1)
            assert finding.message == 'Operation arrow and dash list marker share one line'
            assert finding.severity == 'error'
            assert not any(f.rule_id.startswith('AG-SPELL') for f in result.findings)
            assert 'hunspell' not in sys.modules
            try:
                snapshot.conformance = 'valid'
            except (FrozenInstanceError, AttributeError):
                pass
            else:
                raise AssertionError('snapshot must be immutable')
        ''')

    def test_external_consumer_enforces_symbol_brackets_and_names(self):
        self.run_consumer(r'''
            from arcgrav_language_engine import AnalysisContext, analyze
            context = AnalysisContext(arcgrav_version='current', configuration={'spellcheck': False})
            valid = analyze('[GoodName2]: value\n\nTask:\n- Use [GoodName2]\n', context)
            assert [s.kind for s in valid.semantics.symbols] == ['anchor', 'reference']
            assert not any(f.rule_id == 'AG-SYNTAX-INCOMPLETE' for f in valid.diagnostics.findings)
            for shape in ('[Outer [Inner] tail]', '[badName]', '[Has Space]', '[Bad_Name]', '[Open', ']'):
                result = analyze('[Inner]: value\n\nTask:\n- ' + shape + '\n', context)
                errors = [f for f in result.diagnostics.findings if f.rule_id == 'AG-SYNTAX-INCOMPLETE']
                assert errors and all(f.severity == 'error' for f in errors), shape
                assert not result.semantics.resolutions, shape
            quoted = analyze('Task:\n"[Outer [Inner] tail]"\n', context)
            assert not any(f.rule_id == 'AG-SYNTAX-INCOMPLETE' for f in quoted.diagnostics.findings)
        ''')

    def test_external_consumer_validates_context_and_snapshot_versions(self):
        self.run_consumer(r'''
            from dataclasses import replace
            from arcgrav_language_engine import (
                AnalysisContext, analyze, diagnose, prepare,
                freeze_analysis, restore_analysis, restore_document,
            )
            def raises(expected, callback):
                try:
                    callback()
                except expected:
                    return
                raise AssertionError('Expected ' + expected.__name__)

            supplied = {'spellcheck': False, 'nested': {'values': [1, 2]}}
            context = AnalysisContext(arcgrav_version='current', configuration=supplied)
            supplied['nested']['values'].append(3)
            context.configuration['nested']['values'].append(4)
            assert context.configuration['nested']['values'] == [1, 2]
            assert context.configuration_key == context.configuration_json
            assert context.version == context.arcgrav_version == 'current'
            raises(TypeError, lambda: AnalysisContext())
            raises(ValueError, lambda: AnalysisContext(arcgrav_version=' '))
            raises(ValueError, lambda: AnalysisContext(arcgrav_version='current', profile=''))
            raises(TypeError, lambda: AnalysisContext(arcgrav_version='current', configuration=[]))
            raises(TypeError, lambda: AnalysisContext(arcgrav_version='current', configuration={'a': {1: 'x'}}))
            raises(ValueError, lambda: AnalysisContext(arcgrav_version='current', configuration={'x': float('nan')}))
            raises(ValueError, lambda: AnalysisContext(arcgrav_version='current', configuration={'x': object()}))
            raises(TypeError, lambda: prepare(b'text', context))
            raises(TypeError, lambda: prepare('text', None))
            raises(TypeError, lambda: prepare('text'))
            raises(TypeError, lambda: analyze('text'))

            snapshot = prepare('=> - Inspect text\n', context)
            other = prepare('Different source\n', context)
            raises(TypeError, lambda: diagnose(replace(snapshot, document=None)))
            raises(ValueError, lambda: diagnose(replace(snapshot, document=other.document)))
            raises(ValueError, lambda: diagnose(replace(snapshot, tree=other.tree)))
            for version in (True, 999):
                unsupported = replace(snapshot, schema_version=version)
                raises(ValueError, lambda: diagnose(unsupported))
                raises(ValueError, lambda: restore_analysis(unsupported))
                raises(ValueError, lambda: restore_document(replace(snapshot.document, schema_version=version)))
            complete = analyze('=> - Inspect text\n', context)
            frozen = freeze_analysis(complete)
            assert restore_analysis(frozen).as_record() == complete.as_record()
            # Completed canonical transport can be reevaluated without reparsing.
            assert diagnose(frozen) == complete.diagnostics
            # A nonempty unsupported language version stays explicit. It never
            # silently falls back to current language rules or claims validity.
            unknown = analyze('=> - Inspect text\n', AnalysisContext(arcgrav_version='future-contract'))
            assert unknown.document.session.arcgrav_version == 'future-contract'
            assert unknown.diagnostics.status == 'unsupported_version'
            assert unknown.diagnostics.findings == ()
            assert unknown.conformance == 'unknown'
        ''')

    def test_trusted_snapshots_round_trip_between_source_checkout_and_wheel(self):
        from AgStudio.arcgrav_language_engine import AnalysisContext, prepare, diagnose

        source = 'Task:\r\n=> - 🌍 Keep this text\r\n'
        context = AnalysisContext(arcgrav_version='current', configuration={'spellcheck': False})
        snapshot = prepare(source, context)
        payload = base64.b64encode(pickle.dumps(snapshot)).decode('ascii')
        result = self.run_consumer(f"""
            import base64
            import pickle
            from arcgrav_language_engine import AnalysisContext, PreparedSnapshot, prepare, diagnose
            restored = pickle.loads(base64.b64decode({payload!r}))
            assert isinstance(restored, PreparedSnapshot)
            context = AnalysisContext(arcgrav_version='current', configuration={{'spellcheck': False}})
            snapshot = prepare({source!r}, context)
            assert restored == snapshot
            assert diagnose(restored) == diagnose(snapshot)
            encoded = base64.b64encode(pickle.dumps(snapshot)).decode('ascii')
            assert encoded == {payload!r}
            print(encoded)
        """)
        returned = pickle.loads(base64.b64decode(result.stdout.strip()))
        self.assertIs(type(returned), type(snapshot))
        self.assertEqual(returned, snapshot)
        self.assertEqual(diagnose(returned), diagnose(snapshot))

    def test_missing_optional_dictionary_has_existing_informational_finding(self):
        self.run_consumer(r'''
            from arcgrav_language_engine import AnalysisContext, analyze
            source = '- mispelled ordinary text\n'
            result = analyze(source, AnalysisContext(arcgrav_version='current'))
            spelling = [f for f in result.diagnostics.findings if f.rule_id.startswith('AG-SPELL')]
            assert len(spelling) == 1
            finding = spelling[0]
            assert (finding.rule_id, finding.severity) == ('AG-SPELLCHECK-UNAVAILABLE', 'information')
            assert finding.message == ('English spellcheck is unavailable; install '
                                       'AgStudio/gui/requirements.txt and restart AgStudio.')
            assert finding.source_range.span.extract(source) == 'mispelled'
            assert result.conformance == 'unknown'
            disabled = analyze(source, AnalysisContext(
                arcgrav_version='current', configuration={'spellcheck': False}))
            assert not any(f.rule_id.startswith('AG-SPELL') for f in disabled.diagnostics.findings)
        ''')


if __name__ == '__main__':
    unittest.main()
