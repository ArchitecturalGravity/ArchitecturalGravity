"""Independent evidence and API boundaries for the single rule runner."""
from dataclasses import fields
import importlib
import unittest
from AgStudio.arcgrav_language_engine import AnalysisContext, analyze, prepare, diagnose
from AgStudio.arcgrav_language_engine.lint.rules import Rule, RULES, REGISTRY
from AgStudio.arcgrav_language_engine.lint.rule_units import build_units

class RuleDiagnosticBoundaryTests(unittest.TestCase):
    def test_source_and_unsupported_context_are_explicit(self):
        source = 'Task:\r\n"""\n=> forged\n[Fake]: *\n"""\n=> - Work\n'
        context = AnalysisContext(arcgrav_version='unverified-version', profile='plain', configuration={'mode': ['local']})
        result = analyze(source, context)
        self.assertEqual(result.document.source, source)
        self.assertEqual(result.diagnostics.document_id, result.document.document_id)
        self.assertEqual(result.diagnostics.arcgrav_version, context.arcgrav_version)
        self.assertEqual(result.diagnostics.findings, ())
        self.assertEqual(result.diagnostics.status, 'unsupported_version')
        self.assertEqual(result.diagnostics, diagnose(prepare(source, context)))

    def test_one_executable_unit_per_rule_and_no_documentation_fields(self):
        self.assertEqual(set(REGISTRY), {r.id for r in RULES})
        self.assertEqual(set(build_units(REGISTRY)), set(REGISTRY))
        self.assertFalse({'guide', 'section', 'authority_file', 'blocking_gap_ids'} & {f.name for f in fields(Rule)})
        self.assertNotIn('AG-SYMBOL-REBINDING', REGISTRY)
        self.assertNotIn('AG-ALIAS-REBINDING', REGISTRY)
        self.assertNotIn('AG-CURRENT-OPERATION-DASH-COMBINATION', REGISTRY)
        with self.assertRaises(ValueError):
            build_units({})

    def test_removed_apis_have_no_alias_or_fallback(self):
        import AgStudio.arcgrav_language_engine as engine
        for name in ('AUTHORITY_FLOW', 'CORE_GAPS', 'DOCUMENTED_SURFACES', 'RuleCatalogue', 'diagnose_document'):
            self.assertFalse(hasattr(engine, name), name)
        for prefix in ('AgStudio.shared.', 'AgStudio.arcgrav_language_engine.'):
            for suffix in ('authority', 'surface', 'gaps', 'rules'):
                with self.assertRaises(ModuleNotFoundError):
                    importlib.import_module(prefix + suffix)
        with self.assertRaises(TypeError):
            diagnose('Task: text')
