"""Guard the executable contract boundary against documentation dependencies."""
from dataclasses import fields
import ast
import importlib
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import textwrap
import unittest

from AgStudio.arcgrav_language_engine import AnalysisContext, analyze, prepare
from AgStudio.arcgrav_language_engine.diagnostics import Finding, RuleEvidence
from AgStudio.arcgrav_language_engine.lint.rules import Rule, REGISTRY, RULES, _RULE_UNITS

STUDIO = Path(__file__).resolve().parents[2]


class SelfContainedContractTests(unittest.TestCase):
    def test_runtime_has_no_documentation_path_literals_or_retired_modules(self):
        retired = {'authority', 'gaps', 'surface', 'rules'}
        for path in sorted(STUDIO.rglob('*.py')):
            if 'software_testing' in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertIsNone(
                        re.search(r'(?i)[\w.-]+\.(?:md|rst|pdf)(?:#\S*)?', node.value),
                        (path.relative_to(STUDIO), node.lineno, node.value),
                    )
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module, {
                        'AgStudio.shared.' + name for name in retired
                    }, (path, node.lineno))
        for name in retired:
            with self.assertRaises(ModuleNotFoundError):
                importlib.import_module('AgStudio.arcgrav_language_engine.' + name)

    def test_models_expose_local_evidence_not_external_authority(self):
        deleted_fields = {'guide', 'section', 'authority_file', 'authority_section',
                          'fixture_path', 'implementation_path', 'blocking_gap_ids',
                          'provenance', 'related_gap_ids'}
        for model in (Rule, Finding, RuleEvidence):
            self.assertTrue(deleted_fields.isdisjoint({field.name for field in fields(model)}))
        self.assertEqual(len(REGISTRY), len(RULES))
        self.assertEqual(set(REGISTRY), set(_RULE_UNITS))
        self.assertTrue(all(unit.definition is REGISTRY[identifier]
                            for identifier, unit in _RULE_UNITS.items()))
        self.assertTrue(all(callable(unit.detect) and callable(unit.verify)
                            for unit in _RULE_UNITS.values()))
        result = analyze('Task:\n=> - Work\n', AnalysisContext(
            arcgrav_version='current', configuration={'spellcheck': False}))
        record = result.as_record()
        self.assertEqual(record['schema_version'], 2)
        self.assertNotIn('catalogue', record)
        self.assertEqual(record['findings'][0]['evidence'], {
            'contract_version': 'current', 'syntax_id': 'syntax.operation',
            'premises': ('canonical_prefix_chain',),
            'limits': REGISTRY['AG-OPERATION-LIST'].limits,
        })

    def test_every_active_rule_has_a_nontriggering_source_case(self):
        # A complete clean document is a common negative fixture for every
        # enabled rule; the separate catalogue coverage matrix exercises positives.
        source = 'Scope:\n- Read text\n\nTask:\n- Act\n'
        result = analyze(source, AnalysisContext(arcgrav_version='current'))
        self.assertEqual({rule.id for rule in result.diagnostics.rules}, set(REGISTRY))
        self.assertEqual(result.diagnostics.findings, ())
        self.assertEqual(result.diagnostics.suppressed_conclusions, ())

    def test_preparation_and_projections_work_without_any_documentation(self):
        with TemporaryDirectory(prefix='agstudio-without-docs-') as directory:
            destination = Path(directory) / 'AgStudio'
            shutil.copytree(STUDIO, destination, ignore=shutil.ignore_patterns(
                'Docs', 'software_testing', '__pycache__', '*.pyc', '*.md', '*.rst',
                '*.pdf', 'guide_coverage.json', '.venv*',
            ))
            script = textwrap.dedent('''
                import sys
                sys.path.insert(0, '.')
                from dataclasses import replace
                from AgStudio.arcgrav_language_engine import (
                    AnalysisContext, analyze, prepare, diagnose, restore_analysis,
                    pack_analysis, unpack_analysis,
                )
                from AgStudio.shared.panel_projections import derive_findings, derive_outline
                from AgStudio.shared.highlight_projection import derive_highlighting
                context = AnalysisContext(arcgrav_version='current', configuration={'spellcheck': False})
                source = 'Scope:\\r\\n- 🌍 Read text\\r\\n\\r\\nTask:\\r\\n=> - Work\\r\\n'
                snapshot = prepare(source, context)
                result = diagnose(snapshot)
                assert len(result.findings) == 1
                finding = result.findings[0]
                assert finding.rule_id == 'AG-OPERATION-LIST'
                assert finding.source_range.span.extract(source) == '=> - '
                restored = restore_analysis(replace(unpack_analysis(pack_analysis(snapshot)), diagnostics=result))
                assert restored.as_record() == analyze(source, context).as_record()
                assert derive_findings(restored).rows
                assert derive_outline(restored).rows
                assert derive_highlighting(snapshot)
                assert not any(name.startswith(('PySide', 'PyQt')) for name in sys.modules)
            ''')
            process = subprocess.run([sys.executable, '-I', '-c', script], cwd=directory,
                                     capture_output=True, text=True, timeout=30)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
