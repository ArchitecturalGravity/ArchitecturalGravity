"""The diagnostic API exposes severity and evidence without Class metadata."""
from dataclasses import fields
import json
from pathlib import Path
import subprocess
import sys
import unittest

from AgStudio.shared import LanguageCore
from AgStudio.shared.diagnostics import Finding
from AgStudio.shared.lint import analyze
from AgStudio.shared.lint.rules import Rule, RULES

ROOT = Path(__file__).resolve().parents[3]


class DiagnosticMetadataTests(unittest.TestCase):
    def test_models_and_both_rule_catalogues_have_no_class_field(self):
        for model in (Finding, Rule):
            self.assertNotIn('classification', {f.name for f in fields(model)})
        result = analyze('=> - Act\n')
        record = result.as_record()
        self.assertTrue(result.diagnostics.rules)
        self.assertTrue(result.diagnostics.rules)
        self.assertNotIn('"classification"', json.dumps(record))
        self.assertTrue(all(not hasattr(r, 'classification') for r in RULES))
        self.assertEqual({f.severity for f in result.diagnostics.findings},
                         {'critical', 'error', 'information'})
        self.assertTrue(all(f.id and f.evidence and f.suppression_prerequisites for f in result.diagnostics.findings))

    def test_cli_text_and_json_have_no_class_metadata(self):
        source = 'Read text\n\nTask: value\n'
        process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '-'],
                                 input=source.encode(), cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn('information AG-DOCUMENT-START-SECTION: Define an initial invocation at the top like "Scope" to constrain the overall LLM inference boundary.', process.stdout.decode())
        for marker in ('[advisory]', '[normative]', '[heuristic]'):
            self.assertNotIn(marker, process.stdout.decode())
        process = subprocess.run([sys.executable, '-m', 'AgStudio.shared.cli', '--json', '-'],
                                 input=source.encode(), cwd=ROOT, capture_output=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertNotIn('"classification"', process.stdout.decode())
        findings = json.loads(process.stdout)['results'][0]['findings']
        self.assertEqual(set(findings[0]), {'id', 'rule_id', 'severity', 'source_range',
                                          'evidence', 'suppression_prerequisites', 'message'})

