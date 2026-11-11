"""Concrete PySide6 conformance tests for the Results workspace view."""

from __future__ import annotations

import json
import os
import threading
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AgMark.gui.views.results import (
    PYSIDE6_AVAILABLE,
    ResultRowProjection,
    ResultsProjection,
    ResultsView,
)

if PYSIDE6_AVAILABLE:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication


@unittest.skipUnless(PYSIDE6_AVAILABLE, "PySide6 is not available in this environment")
class ResultsViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._application = QApplication.instance() or QApplication([])

    def test_distinct_session_cached_counts_survive_runner_aggregation_and_results(self):
        import base64
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from AgMark.shared.adapters.Codex_CLI import CodexCliRunner
        from AgMark.shared.adapters.Codex_CLI.session import SESSION_RECORD
        from AgMark.shared.adapters.Codex_CLI.session_capture import read_session
        from AgMark.shared.adapters.execution import validate_retained_parity_observation
        from AgMark.shared.adapters._contract import sha256_bytes
        from AgMark.shared.evaluation.telemetry.consumption import (
            ATTEMPT_MEASUREMENTS, aggregate_treatment_measurements,
        )
        from AgMark.shared.software_testing.adapters.codex_cli.test_runner import (
            FakeCodexTransport, _boundary, _request,
        )
        from AgMark.shared.software_testing.adapters.codex_cli.test_session import rollout

        expected = (0, 37, 81, 0)
        inputs = (100, 100, 100, 0)
        with TemporaryDirectory() as directory:
            class DistinctSessionsTransport(FakeCodexTransport):
                def read_session(self, thread_id, *, launch_environment, environment):
                    index = len(tuple(Path(directory).glob('*.jsonl')))
                    raw = rollout(thread_id, prompts=(f'Distinct treatment {index}',), usage={
                        'input_tokens': inputs[index], 'cached_input_tokens': expected[index],
                        'output_tokens': 20, 'reasoning_output_tokens': 5, 'total_tokens': 125})
                    (Path(directory) / f'rollout-{thread_id}.jsonl').write_bytes(raw)
                    return read_session(thread_id, root=directory)

            runner = CodexCliRunner(transport=DistinctSessionsTransport(),
                                    executable_resolver=lambda _: '/fixture/codex')
            documents = []
            threads = set()
            for index, count in enumerate(expected):
                request = _request(_boundary(), suffix=str(index))
                request['treatment_id'] = f'treatment-{index}'
                observation = runner.execute(request)
                validate_retained_parity_observation(observation)
                record = observation['extensions'][SESSION_RECORD]
                identity = (record['observation_id'], record['attempt'], record['thread_id'])
                self.assertNotIn(identity, threads)
                threads.add(identity)
                self.assertNotIn('content_base64', record)
                captured = record['source_records']
                usage = next(row['payload']['info']['total_token_usage'] for row in captured
                             if row['type'] == 'event_msg' and row['payload']['type'] == 'token_count')
                self.assertEqual(count, usage['cached_input_tokens'])
                envelope = observation['extensions'][ATTEMPT_MEASUREMENTS]
                self.assertEqual(count, envelope['roles']['cached_input_tokens']['value'])
                documents.append((observation, sha256_bytes(json.dumps(observation).encode())))

            measurements = aggregate_treatment_measurements(documents,
                generation_id=documents[0][0]['accepted_generation_id'],
                planned_observations={doc['treatment_id']: 1 for doc, _ in documents})
            for index, aggregate in enumerate(measurements.values()):
                self.assertEqual(inputs[index] - expected[index], aggregate["roles"]["uncached_input_tokens"]["value"])
                self.assertEqual(expected[index] / inputs[index] if inputs[index] else None,
                                 aggregate["roles"]["cache_read_fraction"]["value"])
            rows = tuple(ResultRowProjection(treatment=doc['treatment_id'], score=1,
                evidence='available', status='Scored', status_icon='✓',
                measurements=measurements[doc['treatment_id']]['roles']) for doc, _ in documents)
            view = ResultsView(ResultsProjection(run_id='cached-count-regression', rows=rows))
            self.addCleanup(view.deleteLater)
            column = next(index for index, item in enumerate(view.comparison_table.columns)
                          if item.key == 'original')
            actual = []
            for index in range(len(expected)):
                view.cache_table.selectRow(index)
                model = view.comparison_table.table_model
                actual.append(model.data(model.index(0, column)))
            self.assertEqual(tuple(map(str, expected)), tuple(actual))
            from dataclasses import replace
            from AgMark.shared.validation.codex_cache.metrics import treatment_summary
            for disabled in (False, True):
                supplied = tuple(replace(row, validation=treatment_summary(
                    generation_id=view.run_id, treatment_id=row.treatment, replays=(),
                    scored_observation_ids=(documents[index][0]["observation_id"],),
                    sampling_policy="disabled_by_user", sampling_reason="Disabled by user"))
                    if disabled else row for index, row in enumerate(rows))
                view.set_projection(ResultsProjection(view.run_id, supplied))
                for index, row in enumerate(supplied):
                    view.cache_table.selectRow(index)
                    model = view.comparison_table.table_model
                    self.assertEqual(str(inputs[index] - expected[index]), model.data(model.index(2, 1)))
                    fraction = f"{expected[index] / inputs[index]:g} ratio" if inputs[index] else "Unavailable"
                    self.assertEqual(fraction, model.data(model.index(3, 1)))
                    self.assertEqual(fraction, self.cell(view.cache_table, "cache_read_fraction", row=index))
                    self.assertEqual("Disabled by user" if disabled else "Unavailable", model.data(model.index(3, 2)))
                    retained = view.projection.rows[index].measurements["uncached_input_tokens"]
                    self.assertEqual(1, retained["details"]["coverage"]["paired_attempts"])
                    self.assertIn(documents[index][1], retained["evidence_references"])


    def make_view(self, rows, gid='generation-results'):
        view = ResultsView(ResultsProjection(gid, rows, None if rows else 'No results'))
        self.addCleanup(view.deleteLater)
        return view

    def cell(self, table, key, row=0, role=None):
        index = next(i for i, column in enumerate(table.columns) if column.key == key)
        return table.table_model.data(table.table_model.index(row, index), role or int(Qt.ItemDataRole.DisplayRole))

    def test_cache_selection_preserves_all_scored_treatments_and_no_results_writeup(self):
        from PySide6.QtWidgets import QTableView, QTextBrowser
        rows = (ResultRowProjection('A', 0, 'Available', 'Scored', '✓', measurements={
            'input_tokens': {'value': 100, 'unit': 'tokens'},
            'cached_input_tokens': {'value': 0, 'unit': 'tokens', 'availability': 'available'},
            'cache_write_input_tokens': {'value': 4, 'unit': 'tokens', 'availability': 'available'}}),
            ResultRowProjection('B', None, 'Missing', 'Non-scorable', '!', 'warning'))
        view = self.make_view(rows)
        self.assertEqual(3, len(view.findChildren(QTableView)))
        self.assertEqual([], view.findChildren(QTextBrowser))
        self.assertEqual('Treatments', view.treatment_heading.text())
        self.assertEqual(['A', 'B'], [button.text() for button in view.treatment_buttons])
        self.assertTrue(view.treatment_buttons[0].isChecked())
        self.assertEqual('Telemetry Details', view.cache_heading.text())
        # The Scoring projection retains its measurements; Results does not render a second copy.
        self.assertEqual('0', view.projection._presentation['rows'][0].cells['score'].text)
        self.assertEqual('100', view.projection._presentation['rows'][0].cells['input_tokens'].text)
        self.assertEqual('0', self.cell(view.comparison_table, 'original'))
        self.assertEqual('4', self.cell(view.comparison_table, 'original', row=1))
        self.assertEqual('Unavailable', self.cell(view.comparison_table, 'original', row=2))
        self.assertEqual('Unavailable', self.cell(view.comparison_table, 'original', row=3))
        view.cache_table.selectRow(1)
        self.assertEqual('B', view._selected_row.treatment)
        self.assertTrue(view.treatment_buttons[1].isChecked())
        self.assertFalse(view.treatment_buttons[0].isChecked())
        self.assertEqual('Unavailable', self.cell(view.comparison_table, 'original'))
        self.assertEqual('warning', view.projection._presentation['rows'][1].cells['status'].status_semantics)
        view.set_projection(ResultsProjection(view.run_id, rows))
        self.assertEqual('B', view._selected_row.treatment)
        view.set_projection(ResultsProjection('generation-next', rows))
        self.assertEqual('A', view._selected_row.treatment)
        self.assertTrue(view.treatment_buttons[0].isChecked())

    def test_same_run_refresh_reuses_buttons_and_updates_accessible_status(self):
        from dataclasses import replace
        rows = (ResultRowProjection('A', 1, 'Retained', 'Scored', '✓'),
                ResultRowProjection('B', .5, 'Retained', 'Scored', '✓'))
        view = self.make_view(rows)
        self.assertEqual('Select treatment B', view.treatment_buttons[1].accessibleName())
        view.treatment_buttons[1].click()
        selected = view.treatment_buttons[1]
        refreshed = (replace(rows[0], score=None, status='Blocked'),
                     replace(rows[1], score=.75, status='Completed'))
        view.set_projection(ResultsProjection(view.run_id, refreshed))
        self.assertIs(selected, view.treatment_buttons[1])
        self.assertTrue(selected.isChecked())
        self.assertEqual('B', view._selected_row.treatment)
        self.assertIn('Status: Completed', selected.accessibleDescription())
        self.assertIn('Accuracy: 0.75', selected.accessibleDescription())

    def test_fractional_score_counts_and_comparisons_remain_inspectable(self):
        from AgMark.gui.projection.workspace.results import _measurement_details
        from AgMark.shared.reporting.results import (
            registered_rate_summary, registered_score_details, score_details_text,
        )
        from AgMark.shared.software_testing.integration.test_registered_score_reporting import (
            _registration, _score,
        )

        score = _score('a', .5)
        score['companion_values'] = [
            {'name': 'correct_units', 'value': 2},
            {'name': 'expected_units', 'value': 3},
            {'name': 'unexpected_units', 'value': 1},
        ]
        score['diagnostics'] = ['FIXTURE_FIELD_MISMATCH']
        score['extensions'] = {
            'fixture:comparison': {'path': '/records/0/value', 'expected': 8, 'observed': 9},
        }
        scores = [score, _score('b', 1)]
        summary = registered_rate_summary(scores, _registration())
        details = registered_score_details(scores, _registration())
        row = ResultRowProjection(
            'treatment', summary['value'], 'scored', 'Completed', '✓',
            details=_measurement_details({}, 'scored', summary) + '\n' + score_details_text(details),
            score_details=tuple(details),
        )
        view = self.make_view((row,))
        cell = view.projection._presentation['rows'][0].cells['score']
        self.assertEqual('0.75', cell.text)
        self.assertIn('denominator 2 cases', row.details)
        self.assertNotIn('denominator 2 fields', row.details)
        view.cache_tabs.setCurrentWidget(view.provenance_details)
        retained = view.provenance_details.topLevelItem(1)
        self.assertEqual('Score evidence — case a; repetitions 1', retained.text(0))
        self.assertEqual('0.5', retained.text(1))
        for value in ('/records/0/value', '"expected": 8', '"observed": 9',
                      'FIXTURE_FIELD_MISMATCH', 'correct_units', 'score-a-1'):
            self.assertIn(value, json.dumps(retained._retained))
        self.assertTrue(any(retained.child(index).text(0) == 'companion values'
                            for index in range(retained.childCount())))

    def test_call_count_exact_proxy_and_incomplete_labels_remain_distinct(self):
        from AgMark.gui.views.results import measurement_cell
        exact = {"value": 3, "unit": "calls", "availability": "available",
                 "kind": "session_counter"}
        proxy = {**exact, "kind": "token_event_proxy"}
        incomplete = {**exact, "availability": "partial"}
        self.assertEqual("3", measurement_cell(exact, role="inference_call_count").text)
        self.assertEqual("3 (estimate: token-event proxy)",
                         measurement_cell(proxy, role="inference_call_count").text)
        self.assertEqual("3 (partial)", measurement_cell(incomplete, role="inference_call_count").text)
        self.assertEqual("Unavailable", measurement_cell({"value": None}, role="provider_request_count").text)

    def test_partial_cost_and_source_details_remain_inspectable_without_writeup(self):
        measured = {'cost': {'value': .24, 'unit': 'USD', 'kind': 'estimated_cost',
            'availability': 'partial', 'source': 'retained-price', 'method': 'registered component rates',
            'details': {'coverage': {'measured_attempts': 2, 'planned_observations': 3}}, 'evidence_references': ['ref-price']},
            'failed_tool_calls': {'value': 1, 'unit': 'calls', 'availability': 'partial'}}
        view = self.make_view((ResultRowProjection('A', .5, 'Partial', 'Scored', '✓', measurements=measured),))
        cost_tree = view.telemetry_details.trees['configuration_cost']
        cost = next(cost_tree.topLevelItem(i) for i in range(cost_tree.topLevelItemCount())
                    if cost_tree.topLevelItem(i)._retained['id'] == 'cost')
        self.assertEqual('0.24 USD (partial)', cost.text(1))
        self.assertEqual('estimated', cost._retained['classification'])
        retained = json.dumps(cost._retained)
        for text in ('retained-price', 'registered component rates', 'measured_attempts', 'ref-price'):
            self.assertIn(text, retained)
        tools = view.telemetry_details.trees['tools_turns']
        failed = next(tools.topLevelItem(i) for i in range(tools.topLevelItemCount())
                      if tools.topLevelItem(i)._retained['id'] == 'failed_tool_calls')
        self.assertEqual('1 calls (partial)', failed.text(1))

    def test_unknown_null_empty_and_hostile_values_stay_literal_in_evidence(self):
        entry = {'value': None, 'availability': 'unavailable', 'unit': 'tokens',
            'source': "<img src='file:///secret'>", 'method': 'No source',
            'details': {'unknown': {'null': None, 'empty': [], 'zero': 0, 'flag': False},
                        'literal': '&lt;literal&gt;'}, 'evidence_references': ['ref-1']}
        view = self.make_view((ResultRowProjection('<b>A</b>', None, 'Unavailable', 'Missing', '–',
                              measurements={'cached_input_tokens': entry}, details='Report-only writeup'),))
        view.cache_tabs.setCurrentWidget(view.provenance_details)
        text = json.dumps(view.provenance_details.topLevelItem(0)._retained)
        for value in ("<img src='file:///secret'>", 'unavailable', 'ref-1', 'unknown', 'null', '[]', 'false', '&lt;literal&gt;'):
            self.assertIn(value, text)
        self.assertEqual('Report-only writeup', view.projection.rows[0].details)
        self.assertEqual('<b>A</b>', view._selected_row.treatment)
        self.assertEqual('<b>A</b>', view.treatment_buttons[0].text())

    def test_empty_and_replacement_clear_both_tables_and_cache_scope(self):
        row = ResultRowProjection('A', 0, 'Failed', 'Blocked', '!', 'blocked')
        view = self.make_view((row,))
        view.cache_tabs.setCurrentWidget(view.provenance_details)
        view.set_projection(ResultsProjection('empty', (), 'Results not yet produced'))
        self.assertEqual([], view.treatment_buttons)
        self.assertEqual(0, view.comparison_table.table_model.rowCount())
        self.assertEqual(0, view.cache_table.table_model.rowCount())
        self.assertEqual(0, view.provenance_details.topLevelItemCount())
        self.assertIsNone(view._selected_validation)
        self.assertEqual('Results not yet produced', view.empty_state_label.text())
        view.set_projection(ResultsProjection('new', (row,)))
        self.assertEqual(0, view.cache_tabs.currentIndex())
        self.assertEqual(['A'], [button.text() for button in view.treatment_buttons])
        self.assertTrue(view.treatment_buttons[0].isChecked())

    def test_treatment_buttons_scroll_and_switch_exact_telemetry(self):
        rows = tuple(ResultRowProjection(f'Treatment {i} with a long name', i / 10, 'Available',
            'Scored', '✓', measurements={'total_tokens': {'value': 100 + i, 'unit': 'tokens',
                'availability': 'available'}}) for i in range(12))
        view = self.make_view(rows)
        view.resize(560, 768); view.show()
        for _ in range(3): QApplication.processEvents()
        self.assertEqual(len(rows), len(view.treatment_buttons))
        scroll = view.treatment_scroll.horizontalScrollBar()
        self.assertGreater(scroll.maximum(), 0)
        scroll.setValue(scroll.maximum()); QApplication.processEvents()
        view.treatment_buttons[-1].click()
        self.assertEqual(rows[-1].treatment, view._selected_row.treatment)
        self.assertTrue(view.treatment_buttons[-1].isChecked())
        self.assertEqual(11, view.cache_table.currentIndex().row())
        tree = view.telemetry_details.trees['tokens_cache']
        values = [tree.topLevelItem(i).text(1) for i in range(tree.topLevelItemCount())
                  if tree.topLevelItem(i)._retained['id'] == 'total_tokens']
        self.assertEqual(['111 tokens'], values)
        scroll.setValue(0); QApplication.processEvents()
        view.treatment_buttons[0].click()
        self.assertEqual(rows[0].treatment, view._selected_row.treatment)
        self.assertTrue(view.treatment_buttons[0].isChecked())
        values = [tree.topLevelItem(i).text(1) for i in range(tree.topLevelItemCount())
                  if tree.topLevelItem(i)._retained['id'] == 'total_tokens']
        self.assertEqual(['100 tokens'], values)
        view.close()

    def test_invalid_projection_fails_closed_instead_of_inventing_authority(self):
        for factory in (lambda: ResultsProjection('run'),
                        lambda: ResultRowProjection('A', True, 'retained', 'Scored', '✓'),
                        lambda: ResultRowProjection('A', 1, 'retained', 'Scored', '✓', '')):
            with self.assertRaises(ValueError): factory()

    def test_worker_updates_and_stale_queued_generation_are_isolated(self):
        def projection(gid): return ResultsProjection(gid, (ResultRowProjection(gid, 1, 'Retained', 'Scored', '✓'),))
        view = ResultsView(projection('first'))
        self.addCleanup(view.deleteLater)
        worker = threading.Thread(target=view.set_projection, args=(projection('worker'),))
        worker.start(); worker.join(); QApplication.processEvents()
        self.assertEqual('worker', view.run_id)
        worker = threading.Thread(target=view.set_projection, args=(projection('stale'),))
        worker.start(); worker.join()
        view.set_projection(projection('newest'))
        QApplication.processEvents()
        self.assertEqual('newest', view.run_id)
        self.assertEqual('newest', view.treatment_buttons[0].text())


if __name__ == '__main__': unittest.main()
