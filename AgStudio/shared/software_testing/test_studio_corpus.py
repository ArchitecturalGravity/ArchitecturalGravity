"""AgStudio-owned sample corpus: source fidelity, mutations, and CLI parity.

Samples are owned by AgStudio. Tests must not open external ArcGrav guide
documents or track their directory layout.
"""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from AgStudio.shared.lint import analyze


ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = (
    ROOT / "AgStudio/examples/HelloWorld.arc",
)


class StudioCorpusTests(unittest.TestCase):
    def test_local_examples_are_lossless_deterministic_and_bounded(self):
        for path in EXAMPLES:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                result = analyze(source)
                self.assertEqual("".join(token.text for token in result.tree.tokens), source)
                self.assertEqual(result.as_record(), analyze(source).as_record())
                self.assertEqual(result.conformance, "unknown")
                for finding in result.diagnostics.findings:
                    span = finding.source_range.span
                    self.assertTrue(0 <= span.start < span.end <= len(source))
                    self.assertTrue(span.extract(source))

    def test_local_mutations_report_introduced_violations(self):
        source = "Scope: prepared\nTask:\n- Inspect\n"
        mutations = {
            "AG-OPERATION-LIST": "\n=> - Invalid combination\n",
            "AG-OPERATION-MULTIPLE": "\n=> => Double operation\n",
            "AG-ALIAS-SOURCE": "\nAS [MissingSource]\n",
            "AG-SECTION-EMPTY": "\nEmptySection:\n",
            "AG-LIST-EMPTY": "\nP0.\n",
            "AG-INDENT-WIDTH": "\n   - Odd indentation\n",
        }
        for rule_id, suffix in mutations.items():
            with self.subTest(rule=rule_id):
                result = analyze(source + suffix)
                self.assertTrue(any(
                    finding.rule_id == rule_id
                    and finding.source_range.span.start >= len(source)
                    for finding in result.diagnostics.findings
                ))

    def test_local_examples_cli_matches_canonical_engine(self):
        for path in EXAMPLES:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                expected = analyze(source).as_record()
                process = subprocess.run(
                    [sys.executable, "-m", "AgStudio.shared.cli", "--json", str(path)],
                    cwd=ROOT, capture_output=True, text=True, timeout=15,
                )
                self.assertIn(process.returncode, (0, 1), process.stderr)
                record = json.loads(process.stdout)["results"][0]
                record.pop("file")
                self.assertEqual(record, json.loads(json.dumps(expected)))


if __name__ == "__main__":
    unittest.main()
