"""Extraction contracts: engine ownership, worker migration and staged reuse.

These are host/API checks, not additional ArcGrav language authority.
"""
import base64
from contextlib import ExitStack
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import importlib
import json
from pathlib import Path
import pickle
import unittest
from unittest.mock import patch

import AgStudio.arcgrav_language_engine as engine
from AgStudio.arcgrav_language_engine import AnalysisContext
from AgStudio.arcgrav_language_engine.api import parse, resolve
from AgStudio.shared.analysis_snapshot import (
    AnalysisRequest, calculate_analysis_snapshot, calculate_parse_snapshot,
    restore_document, unpack_analysis,
)


class LanguageEngineIntegrationTests(unittest.TestCase):
    def test_legacy_imports_share_engine_identity_including_private_helpers(self):
        for suffix in ('core', 'recognition',
                       'recognition.source', 'recognition.section_boundaries',
                       'document', 'document.model', 'diagnostics',
                       'lint.syntax', 'lint.semantics', 'lint.members', 'lint.model',
                       'lint.document_end', 'lint.editor_checks', 'lint.spelling',
                       'lint.rules', 'lint.findings'):
            with self.subTest(module=suffix):
                self.assertIs(importlib.import_module('AgStudio.shared.' + suffix),
                              importlib.import_module('AgStudio.arcgrav_language_engine.' + suffix))
        from AgStudio.shared.lint import Analysis, analyze
        from AgStudio.shared import LanguageCore
        from AgStudio.shared.analysis_snapshot import AnalysisSnapshot
        self.assertIs(Analysis, engine.Analysis)
        self.assertIs(AnalysisSnapshot, engine.AnalysisSnapshot)
        self.assertIs(LanguageCore, engine.LanguageCore)
        self.assertIs(analyze, importlib.import_module('AgStudio.arcgrav_language_engine.lint').analyze)
        # Studio-only editing remains outside the language-engine package.
        from AgStudio.shared.lint import block_move
        self.assertTrue(block_move.__name__.startswith('AgStudio.'))

    def test_studio_workers_use_public_engine_boundary_once(self):
        source = 'Task:\r\n=> - 🌍 Active\r\n'
        request = AnalysisRequest(source, 'current', 'review', '{"spellcheck":false}')
        with patch.object(engine, 'prepare', wraps=engine.prepare) as prepare:
            snapshot = calculate_parse_snapshot(request)
        prepare.assert_called_once()
        self.assertEqual(prepare.call_args.args,
                         (source, AnalysisContext(arcgrav_version='current', profile='review',
                                                  configuration={'spellcheck': False})))
        with patch.object(engine, 'diagnose', wraps=engine.diagnose) as diagnose:
            result = calculate_analysis_snapshot(snapshot)
        diagnose.assert_called_once_with(snapshot)
        self.assertEqual(result.snapshot.diagnostics,
                         engine.analyze(source, prepare.call_args.args[1]).diagnostics)

    def test_preparation_is_single_parse_and_diagnostics_never_repeat_derivation(self):
        source = 'Scope:\n- "[Hidden]"\n[A]: 🌍\r\nTask:\n- Use [A]\n=> - Active\n[Open\n'
        context = AnalysisContext(arcgrav_version='current', configuration={'spellcheck': False})
        with patch('AgStudio.arcgrav_language_engine.api.parse', wraps=parse) as parser, \
                patch('AgStudio.arcgrav_language_engine.api.resolve', wraps=resolve) as resolver, \
                patch('AgStudio.arcgrav_language_engine.lint.findings.assemble_diagnostics',
                      side_effect=AssertionError('prepare ran diagnostics')):
            snapshot = engine.prepare(source, context)
        self.assertEqual((parser.call_count, resolver.call_count), (1, 1))
        original = restore_document(snapshot.document)
        canonical = restore_document(snapshot.document)
        self.assertNotIn('[Hidden]', [f.span.extract(source) for f in original.occurrence_facts])
        self.assertNotIn('[Hidden]', [f.span.extract(source) for f in canonical.occurrence_facts])
        with ExitStack() as stack:
            for target in ('AgStudio.arcgrav_language_engine.api.prepare',
                           'AgStudio.arcgrav_language_engine.api.parse',
                           'AgStudio.arcgrav_language_engine.api.resolve',
                           'AgStudio.arcgrav_language_engine.core.LanguageCore.open_source',
                           'AgStudio.arcgrav_language_engine.core.LanguageCore.parse_document',
                           'AgStudio.arcgrav_language_engine.lint.model.CanonicalDocument.__init__'):
                stack.enter_context(patch(target, side_effect=AssertionError('repeated derivation')))
            first = engine.diagnose(snapshot)
            second = engine.diagnose(pickle.loads(pickle.dumps(snapshot)))
        self.assertEqual(first, second)
        self.assertEqual(snapshot.diagnostics.status, 'pending')
        self.assertEqual(snapshot.diagnostics.findings, ())

    def test_old_snapshot_layout_and_missing_schema_are_rejected(self):
        snapshot = engine.prepare('Task:\n- Read\n', AnalysisContext(arcgrav_version='current'))
        for original in (snapshot, snapshot.document):
            state = original.__getstate__()
            for invalid in (state[:-1], [*state[:-1], 1], [*state[:-1], True]):
                with self.assertRaises(ValueError):
                    object.__new__(type(original)).__setstate__(invalid)
        self.assertEqual(pickle.loads(pickle.dumps(snapshot)), snapshot)

    def test_versions_fail_closed_and_returned_models_are_immutable(self):
        context = AnalysisContext(arcgrav_version='current', configuration={'spellcheck': False})
        snapshot = engine.prepare('Task:\n=> - Active\n', context)
        with self.assertRaises(FrozenInstanceError):
            snapshot.tree = None
        document = restore_document(snapshot.document)
        for attribute in ('syntax', 'semantics'):
            with self.assertRaises(FrozenInstanceError):
                setattr(document, attribute, None)
        for damaged in (replace(snapshot, schema_version=999),
                        replace(snapshot, tree=None),
                        replace(snapshot, document=replace(snapshot.document, canonical=False)),
                        replace(snapshot, document=replace(snapshot.document, schema_version=999))):
            with self.subTest(snapshot=damaged.schema_version):
                with self.assertRaises(ValueError):
                    engine.diagnose(damaged)
        unsupported = engine.analyze('Task:\n=> - Active\n',
                                    AnalysisContext(arcgrav_version='future-language'))
        self.assertEqual(unsupported.diagnostics.status, 'unsupported_version')
        self.assertEqual(unsupported.diagnostics.findings, ())
        self.assertEqual(unsupported.conformance, 'unknown')


if __name__ == '__main__':
    unittest.main()
