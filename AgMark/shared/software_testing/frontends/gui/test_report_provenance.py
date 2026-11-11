"""Saved-report presentation must retain values without promoting evidence."""
import json
import os
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from AgMark.gui.widgets.report_provenance import readable_provenance
from AgMark.gui.widgets.report_reader import ReportReader
from PySide6.QtWidgets import QApplication


def report(details, availability='partial', treatment='control'):
    raw = json.dumps(details, ensure_ascii=False).replace('|', '\\|').replace('<', '&lt;').replace('>', '&gt;')
    return ('### ' + treatment + ' measurement provenance\n\n'
        '- total_tokens: ' + availability + '; source: retained source; meaning: Recorded count.; method: registered sum.\n'
        '  Details: ' + raw + '\n- Efficiency: {"availability": "unavailable", "reason": "No registered formula."}\n')


class ProvenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def render(self, source):
        reader = ReportReader()
        self.addCleanup(reader.deleteLater)
        reader.set_report(source)
        return reader

    def test_coverage_and_input_units_are_grouped_for_every_treatment(self):
        details = {'coverage': {'measured_attempts': 1, 'observed_attempts': 2, 'planned_observations': 3},
                   'inputs': [{'value': 0, 'unit': 'tokens', 'kind': 'runtime_counter', 'availability': 'available'}]}
        source = report(details) + report(details, treatment='candidate')
        reader = self.render(source)
        text = reader.toPlainText()
        self.assertIn('control / Total tokens', [title for title, _ in reader.sections])
        self.assertIn('candidate / Total tokens', [title for title, _ in reader.sections])
        for expected in ('control measurement provenance', 'candidate measurement provenance', 'Total tokens',
                         'What this measures: Recorded count.', 'Source: retained source',
                         'Aggregation method: registered sum', 'Measurement coverage', 'Measured attempts',
                         'Retained input measurements / Item 1', 'tokens', 'runtime_counter', 'No registered formula.'):
            self.assertIn(expected, text)
        self.assertEqual(text.count('Availability: partial'), 2)
        self.assertNotIn('{"', text)
        self.assertIn('\n0\n', text)

    def test_scalars_arrays_empty_values_unknown_fields_and_escaping(self):
        payload = {'customCase': {'zero': 0, 'missing': None, 'flag': False, 'string_flag': 'false', 'blank': '',
                   'empty_record': {}, 'empty_list': [], 'values': ['a|b', '<img src=x>', '[link](https://example.invalid)', 'x\ny', 4]},
                   'hash': 'a' * 200}
        text = self.render(report(payload)).toPlainText()
        for expected in ('CustomCase', 'Not recorded (null)', 'False (boolean)', 'false (text)',
                         'Empty text', 'empty object', 'empty list', 'a|b', '<img src=x>',
                         '[link](https://example.invalid)', 'x\\ny', 'a' * 200, 'Item 5'):
            self.assertIn(expected, text)
        self.assertNotIn('![', text)
        for value in (None, 0, False, 'unknown', [], {}, [1, None, {'new': 'field'}]):
            rendered = self.render(report(value)).toPlainText()
            self.assertIn('Measurement details', rendered)
            self.assertNotIn('unrecognized format', rendered)

    def test_unrelated_json_and_unrecognized_content_are_not_rewritten(self):
        source = '# Other\nDetails: {"untouched": true}\n'
        self.assertEqual(readable_provenance(source), source.rstrip('\n'))
        source = '### x measurement provenance\n  Details: {broken\n## Next\n  Details: {"untouched": true}'
        text = self.render(source).toPlainText()
        self.assertIn('{broken', text)
        self.assertIn('unrecognized format', text)
        self.assertIn('Details: {"untouched": true}', text)

    def test_invalid_or_ambiguous_json_remains_visible(self):
        for raw in ('{"a": 1, "a": 2}', '{"bad": NaN}', '{"bad": Infinity}'):
            source = '### x measurement provenance\n  Details: ' + raw
            text = self.render(source).toPlainText()
            self.assertIn(raw, text)
            self.assertIn('unrecognized format', text)
        source = '### x measurement provenance\n  Details: {"exact": 0.123456789012345678901}'
        self.assertIn('0.123456789012345678901', self.render(source).toPlainText())

    def test_narrow_reader_retains_content_and_navigation(self):
        reader = self.render(report({'coverage': {'planned_observations': 1}, 'id': 'sha256:' + 'f' * 64,
                                     'inputs': [{'value': 42, 'unit': 'tokens'}]}))
        for width in (340, 540, 1000):
            reader.resize(width, 620); reader.show(); self.app.processEvents()
            self.assertLessEqual(reader.horizontalScrollBar().maximum(), 1)
            reader.go_to_section(reader.sections[-1][1])
            self.assertIn('Total tokens', reader.textCursor().block().text())
            self.assertFalse(reader.grab().isNull())


if __name__ == '__main__':
    unittest.main()
