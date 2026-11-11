"""Individual-run reports follow the mock and link to separate exact evidence."""

from __future__ import annotations

import copy
import hashlib
import re
from types import SimpleNamespace
import unittest
from urllib.parse import unquote, urlsplit

from AgMark.shared.reporting.generation import _human_markdown
from AgMark.shared.reporting.run_report import build_run_results, project_observation_results


SUMMARY_COLUMNS = [
    "Treatment", "Accuracy", "Input Tokens", "Uncached Input",
    "Reasoning Output Tokens", "Output Tokens", "Total Tokens",
    "Cache Read Fraction", "Average Inference Duration", "Average TTFT",
    "Average TBT", "Average Direct TTFT", "Average Direct TBT",
    "Tool Calls", "Distinct Tool Calls", "Failed Tool Calls",
]
OBSERVATION_COLUMNS = SUMMARY_COLUMNS + [
    "Execution Order", "Observation ID Prefix", "Repetition", "Attempt Start UTC",
]
OBSERVATIONS_HEADING = "### Treatment Results per Observation in Execution Order"
TOTALS_HEADING = "### Treatment Total Averaged Results"


def obj(**fields):
    return SimpleNamespace(**fields)


def measurement(value, *, unit="tokens", kind="runtime_counter", availability=None, details=None):
    return {
        "value": value, "unit": unit,
        "availability": availability or ("available" if value is not None else "unavailable"),
        "kind": kind, "source": "test:retained-telemetry",
        "meaning": "A retained test measurement", "method": "test:aggregation",
        "evidence_references": ["test:source"], "details": details or {},
    }


def _roles(input_tokens, cached_input, output, reasoning, tools, distinct, timing):
    return {
        "input_tokens": measurement(input_tokens),
        "cached_input_tokens": measurement(cached_input),
        "uncached_input_tokens": measurement(input_tokens - cached_input),
        "output_tokens": measurement(output),
        "reasoning_tokens": measurement(reasoning),
        "total_tokens": measurement(input_tokens + output),
        "cache_read_fraction": measurement(cached_input / input_tokens if input_tokens else None, unit="ratio"),
        "average_inference_ms": measurement(timing, unit="ms", kind="timing_estimate"),
        "average_ttft_ms": measurement(timing / 10, unit="ms", kind="timing_estimate"),
        "average_tbt_ms": measurement(timing / 1000, unit="ms", kind="timing_estimate"),
        "average_direct_ttft_ms": measurement(None, unit="ms"),
        "average_direct_tbt_ms": measurement(None, unit="ms"),
        "tool_calls": measurement(tools, unit="calls"),
        "distinct_tool_count": measurement(distinct, unit="tools"),
        "failed_tool_calls": measurement(0, unit="calls"),
    }


def _model():
    metric = obj(
        is_primary_endpoint=True,
        metric_id="test.metric.field-accuracy",
        registration_id="test.registration.primary", registration_version="1.0.0",
        registration={
            "metric_id": "test.metric.field-accuracy", "metric_version": "1.0.0",
            "unit": "proportion", "classification": "primary_correctness",
            "display_name": "Field accuracy", "is_primary_endpoint": True,
            "extensions": {"arcgrav.shared.reporting:aggregation": {
                "repetition_reducer": "mean", "case_reducer": "mean"}},
        }, scorer=obj(id="test.scorer"),
    )
    summary = obj(
        treatment_id="candidate", metric_registration_id=metric.registration_id,
        metric_registration_version=metric.registration_version,
        value=0.5, numerator=1.0, denominator=2,
        planned=3, finalized=3, completed=3, scorable=3,
        failed=0, missing=0, excluded=0, non_scorable=0,
        availability=obj(state="scored"),
    )
    rows = []
    values = [(100, 50, 20, 5, 2, 2, 1000), (900, 90, 180, 15, 2, 2, 3000),
              (1000, 0, 0, 0, 0, 0, 5000)]
    for index, value in enumerate(values, 1):
        rows.append({
            "observation_id": "observation-" + hashlib.sha256(str(index).encode()).hexdigest(),
            "case_id": "case-a" if index < 3 else "case-b", "treatment_id": "candidate",
            "repetition_id": 10 + index,
            "attempt_started_at": f"2026-11-05T03:00:0{index}Z",
            "score": {"value": 1.0 if index < 3 else 0.0, "availability": "scored", "unit": "proportion"},
            "measurements": {"roles": _roles(*value)},
            "source_artifact": {"artifact_id": f"observation-source-{index}",
                                "sha256": "sha256:" + str(index) * 64,
                                "reference": f"generation/observation-{index}.json"},
        })
    counts = {"planned": 3, "finalized": 3, "completed": 3, "scored": 3,
              "failed": 0, "missing": 0, "excluded": 0, "non_scorable": 0}
    accepted = obj(
        benchmark=obj(id="test.benchmark"), comparison_track_id="test.comparison-track",
        metrics=(metric,), primary_endpoint=obj(id=metric.metric_id),
        treatment_summaries=(summary,),
        case_result_matrix=tuple(obj(case_id=case, treatment_id="candidate",
            metric_registration_id=metric.registration_id,
            metric_registration_version=metric.registration_version,
            value=value, availability=obj(state="scored"))
            for case, value in (("case-a", 1.0), ("case-b", 0.0))),
        observation_matrix=tuple(obj(observation_id=row["observation_id"], case_id=row["case_id"],
            treatment_id=row["treatment_id"], repetition_id=row["repetition_id"],
            availability=obj(state="scored")) for row in rows),
        observation_counts=obj(to_dict=lambda: dict(counts)),
        execution_boundary_fingerprint="sha256:" + "a" * 64,
    )
    # Deliberately differ from the arithmetic means of the three observation
    # timings: the report must not silently use sample-weighted session means.
    total_roles = _roles(2000, 140, 200, 20, 4, 3, 9000)
    total_roles["distinct_tool_count"]["details"]["tool_names"] = ["read", "search", "write"]
    return obj(
        accepted=obj(accepted=accepted, observation_results=tuple(rows), model_id="test-model", reasoning_effort=None,
            treatment_measurements={"candidate": {"roles": total_roles, "sessions": (), "efficiency": {}}},
            score_details=(), synthetic_conformance=False),
        report_id="report:test", report_version="1.0.0", accepted_generation_id="generation:test",
        generated_at="2026-11-05T04:00:00Z", status="complete",
        sections={"executive_summary": obj(availability="available", reason=None),
                  "paired_treatment_comparisons": obj(availability="not_applicable", reason="Only one treatment.")},
        extensions={}, validations=(),
    )


def _render(model=None, **references):
    model = _model() if model is None else model
    return _human_markdown(model, build_run_results(model), **{
        "human_reference": "reports/run/report.md",
        "report_reference": "reports/run/report.json",
        "canonical_evidence_reference": "reports/run/canonical-evidence.json",
        "manifest_reference": "reports/run/report-manifest.json", **references,
    }).decode("utf-8")


def _table(markdown, heading):
    content = markdown.split(heading + "\n", 1)[1]
    lines = content.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("| "))
    table = []
    for line in lines[start:]:
        if not line.startswith("| "):
            break
        table.append([cell.strip() for cell in line.strip("|").split("|")])
    columns = table[0]
    return columns, [dict(zip(columns, row)) for row in table[2:]]


class ReportMarkdownPresentationTests(unittest.TestCase):
    def test_mock_structure_and_exact_result_columns(self):
        human = _render()
        headings = re.findall(r"^## (.+)$", human, re.MULTILINE)
        self.assertEqual(["Run Details", "Results Tables", "Notable Results and Exceptions",
                          "Measurements", "Links to Supporting Data"], headings)
        self.assertEqual([OBSERVATIONS_HEADING, TOTALS_HEADING],
                         re.findall(r"^### .+$", human, re.MULTILINE))
        self.assertIn("# AgMark Individual Run Report", human)
        self.assertEqual(OBSERVATION_COLUMNS, _table(human, OBSERVATIONS_HEADING)[0])
        self.assertEqual(SUMMARY_COLUMNS, _table(human, TOTALS_HEADING)[0])
        self.assertEqual(2, len(re.findall(r"^\| --- ", human, re.MULTILINE)))
        self.assertNotIn("Treatment Averages per Observation", human)
        self.assertNotIn("#### ", human)
        self.assertNotIn("treatment_averages", build_run_results(_model()))
        self.assertNotIn("Appendix", human)
        self.assertNotIn("```json", human)
        self.assertIn("test-model", human)
        self.assertIn("generation:test", human)

    def test_reasoning_level_is_next_to_model_and_missing_is_explicit(self):
        for effort in ("high", "xhigh", "none", None):
            with self.subTest(effort=effort):
                model = _model()
                model.accepted.reasoning_effort = effort
                human = _render(model)
                line = next(line for line in human.splitlines() if line.startswith("- **Model:**"))
                self.assertEqual(
                    "- **Model:** test-model · **Reasoning Level:** " + (effort or "Unavailable"), line)
                self.assertEqual(effort, build_run_results(model)["reasoning_effort"])
        # Neither the selected model nor reasoning-token counts establishes a level.
        self.assertIn("**Reasoning Level:** Unavailable", _render())

    def test_notable_result_labels_use_title_case_and_preserve_acronyms(self):
        human = _render()
        section = human.split("## Notable Results and Exceptions\n", 1)[1].split("## Measurements", 1)[0]
        labels = re.findall(r"^- \*\*([^*]+):\*\*", section, re.MULTILINE)
        self.assertEqual(["Accuracy", "Total Tokens", "Uncached Input Tokens", "Inference Duration",
                          "TTFT", "TBT", "Measurement Exceptions", "Interpretation"], labels)
        self.assertNotIn("Ttft", human)
        self.assertNotIn("Tbt", human)

    def test_custom_primary_metric_labels_are_title_cased_without_changing_metadata(self):
        model = _model()
        label = "mean TTFT per API request"
        model.accepted.accepted.metrics[0].registration.update(
            unit="ms", classification="secondary", display_name=label)
        human = _render(model)
        for heading in (OBSERVATIONS_HEADING, TOTALS_HEADING):
            self.assertEqual("Mean TTFT per API Request", _table(human, heading)[0][1])
        self.assertIn("- **Mean TTFT per API Request:**", human)
        self.assertEqual(label, build_run_results(model)["metric_label"])
        self.assertEqual(label, model.accepted.accepted.metrics[0].registration["display_name"])

    def test_cache_percentages_leave_retained_ratios_unchanged(self):
        model = _model()
        original_rows = copy.deepcopy(model.accepted.observation_results)
        original_totals = copy.deepcopy(model.accepted.treatment_measurements)
        projection = build_run_results(model)
        human = _render(model)
        self.assertIn("7.0000%", human)
        for row in (*projection["observations"], *projection["treatment_totals"]):
            self.assertEqual("ratio", row["measurements"]["roles"]["cache_read_fraction"]["unit"])
        self.assertEqual([0.5, 0.1, 0.0],
                         [row["measurements"]["roles"]["cache_read_fraction"]["value"]
                          for row in projection["observations"]])
        self.assertEqual(0.07, projection["treatment_totals"][0]["measurements"]["roles"]["cache_read_fraction"]["value"])
        self.assertEqual(original_rows, model.accepted.observation_results)
        self.assertEqual(original_totals, model.accepted.treatment_measurements)
        self.assertIn("Displayed as a percentage, rounded to four decimals", human)
        self.assertNotIn("unitless", human)

    def test_cache_percentage_preserves_availability_and_zero(self):
        cases = ((None, "unavailable", "Unavailable"),
                 (None, "non_comparable", "Non comparable"),
                 (0.5, "partial", "50.0000% (partial)"),
                 (0.0, "available", "0.0000%"),
                 (1.0, "available", "100.0000%"))
        for value, state, expected in cases:
            with self.subTest(state=state, value=value):
                model = _model()
                measured = measurement(value, unit="ratio", availability=state)
                for row in model.accepted.observation_results:
                    row["measurements"]["roles"]["cache_read_fraction"] = copy.deepcopy(measured)
                model.accepted.treatment_measurements["candidate"]["roles"]["cache_read_fraction"] = copy.deepcopy(measured)
                human = _render(model)
                for heading in (OBSERVATIONS_HEADING, TOTALS_HEADING):
                    for row in _table(human, heading)[1]:
                        self.assertEqual(expected, row["Cache Read Fraction"])

    def test_observation_counts_and_treatment_summary_have_separate_meanings(self):
        human = _render()
        _, observations = _table(human, OBSERVATIONS_HEADING)
        _, totals = _table(human, TOTALS_HEADING)
        self.assertEqual(["11", "12", "13"], [row["Repetition"] for row in observations])
        self.assertEqual(["100.0000%", "100.0000%", "0.0000%"], [row["Accuracy"] for row in observations])
        # Equal case weighting is retained rather than replacing the accepted
        # score with the (different) unweighted observation mean of 66.6667%.
        for row in totals:
            self.assertEqual("50.0000%", row["Accuracy"])
            self.assertEqual("3,000.00 proxy", row["Average Inference Duration"])
            self.assertEqual("300.00 proxy", row["Average TTFT"])
            self.assertEqual("3.000000 proxy", row["Average TBT"])
        self.assertEqual("2,000", totals[0]["Input Tokens"])
        self.assertEqual("1,860", totals[0]["Uncached Input"])
        self.assertEqual("20", totals[0]["Reasoning Output Tokens"])
        self.assertEqual("2,200", totals[0]["Total Tokens"])
        self.assertEqual("7.0000%", totals[0]["Cache Read Fraction"])
        self.assertEqual(["50.0000%", "10.0000%", "0.0000%"],
                         [row["Cache Read Fraction"] for row in observations])
        self.assertEqual("4", totals[0]["Tool Calls"])
        self.assertEqual("3", totals[0]["Distinct Tool Calls"])

    def test_unavailable_is_not_zero_and_proxy_does_not_fill_direct_timing(self):
        human = _render()
        for heading in (OBSERVATIONS_HEADING, TOTALS_HEADING):
            for row in _table(human, heading)[1]:
                self.assertEqual("Unavailable", row["Average Direct TTFT"])
                self.assertEqual("Unavailable", row["Average Direct TBT"])
                self.assertIn("proxy", row["Average TTFT"])
        model = _model()
        for row in model.accepted.observation_results:
            row["measurements"]["roles"]["reasoning_tokens"] = measurement(None)
        model.accepted.treatment_measurements["candidate"]["roles"]["reasoning_tokens"] = measurement(None)
        human = _render(model)
        for heading in (OBSERVATIONS_HEADING, TOTALS_HEADING):
            for row in _table(human, heading)[1]:
                self.assertEqual("Unavailable", row["Reasoning Output Tokens"])

    def test_partial_measurements_are_qualified_in_the_treatment_summary(self):
        model = _model()
        model.accepted.observation_results[1]["measurements"]["roles"]["input_tokens"] = measurement(None)
        model.accepted.treatment_measurements["candidate"]["roles"]["input_tokens"] = measurement(1100, availability="partial")
        human = _render(model)
        self.assertEqual("Unavailable", _table(human, OBSERVATIONS_HEADING)[1][1]["Input Tokens"])
        self.assertIn("partial", _table(human, TOTALS_HEADING)[1][0]["Input Tokens"].lower())

    def test_actual_start_order_is_not_hash_repetition_or_completion_order(self):
        model = _model()
        rows = model.accepted.observation_results
        rows[0]["attempt_started_at"] = "2026-11-05T04:00:02+01:00"
        rows[1]["attempt_started_at"] = "2026-11-05T03:00:01Z"
        rows[2]["attempt_started_at"] = "2026-11-05T03:00:03Z"
        human = _render(model)
        ordered = _table(human, OBSERVATIONS_HEADING)[1]
        self.assertEqual(["12", "11", "13"], [row["Repetition"] for row in ordered])
        self.assertEqual(["1", "2", "3"], [row["Execution Order"] for row in ordered])
        self.assertIn("start", human.lower())
        self.assertIn("completion", human.lower())

    def test_tied_and_absent_start_times_do_not_invent_execution_rank(self):
        model = _model()
        rows = model.accepted.observation_results
        rows[1]["attempt_started_at"] = "2026-11-05T04:00:01+01:00"
        rows[2]["attempt_started_at"] = None
        human = _render(model)
        ordered = _table(human, OBSERVATIONS_HEADING)[1]
        self.assertEqual(["1", "1", "Unavailable"],
                         [row["Execution Order"].split(" ", 1)[0] for row in ordered])
        self.assertEqual("Unavailable", ordered[-1]["Attempt Start UTC"])
        self.assertIn("tie", human.lower())

    def test_all_observations_are_rendered_without_preview_truncation(self):
        model = _model()
        rows = []
        for index in range(15):
            row = copy.deepcopy(model.accepted.observation_results[index % 3])
            row["observation_id"] = "observation-" + hashlib.sha256(f"extra-{index}".encode()).hexdigest()
            row["repetition_id"] = 100 + index
            row["attempt_started_at"] = f"2026-11-05T03:00:{index:02d}Z"
            rows.append(row)
        model.accepted.observation_results = tuple(reversed(rows))
        human = _render(model)
        displayed = _table(human, OBSERVATIONS_HEADING)[1]
        self.assertEqual(15, len(displayed))
        self.assertEqual([str(100 + index) for index in range(15)], [row["Repetition"] for row in displayed])
        self.assertNotIn("Showing 12", human)

    def test_colliding_observation_prefixes_remain_unambiguous(self):
        model = _model()
        rows = model.accepted.observation_results
        for index, row in enumerate(rows):
            row["observation_id"] = "observation-" + "a" * 12 + str(index) + "b" * 51
        displayed = _table(_render(model), OBSERVATIONS_HEADING)[1]
        prefixes = [row["Observation ID Prefix"] for row in displayed]
        self.assertEqual(len(prefixes), len(set(prefixes)))
        self.assertTrue(all(len(prefix) >= 13 for prefix in prefixes))

    def test_native_colon_identifiers_display_hash_prefixes(self):
        model = _model()
        for row in model.accepted.observation_results:
            row['observation_id'] = row['observation_id'].replace('observation-', 'observation:', 1)
        displayed = _table(_render(model), OBSERVATIONS_HEADING)[1]
        self.assertEqual(
            [row['observation_id'].split(':', 1)[1][:12] for row in model.accepted.observation_results],
            [row['Observation ID Prefix'] for row in displayed],
        )

    def test_non_accuracy_metric_keeps_registered_unit_and_zero(self):
        model = _model()
        metric = model.accepted.accepted.metrics[0]
        metric.registration.update(unit="units/case", classification="secondary", display_name="Measured units")
        model.accepted.accepted.treatment_summaries[0].value = 0.0
        for row in model.accepted.observation_results:
            row["score"].update(value=0.0, unit="units/case")
        human = _render(model)
        columns, observations = _table(human, OBSERVATIONS_HEADING)
        self.assertNotIn("Accuracy", columns)
        self.assertIn("Measured Units", columns[1])
        self.assertNotIn("%", observations[0][columns[1]])
        self.assertIn("0", observations[0][columns[1]])
        self.assertIn("units/case", human)

    def test_supporting_data_links_are_relative_to_report_location(self):
        human = _render(canonical_evidence_reference="evidence/canonical evidence.json")
        links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", human)
        self.assertIn("report.json", links)
        self.assertIn("report-manifest.json", links)
        self.assertIn("../../evidence/canonical evidence.json", [unquote(link) for link in links])
        self.assertTrue(links)
        for link in links:
            self.assertFalse(urlsplit(link).scheme, link)
            self.assertFalse(link.startswith("/"), link)
        self.assertNotIn("test:source", human)

    def test_unsafe_artifact_links_are_rejected_and_link_punctuation_is_encoded(self):
        for target in ("/absolute/evidence.json", "../evidence.json", "https://example.com/evidence",
                       "C:\\evidence.json", "data:evidence", "evidence/./report.json",
                       "evidence//report.json", "evidence\n.json"):
            with self.subTest(target=target), self.assertRaises(ValueError):
                _render(canonical_evidence_reference=target)
        human = _render(canonical_evidence_reference="reports/run/evidence (exact)#1.json")
        self.assertIn("evidence%20%28exact%29%231.json", human)

    def test_non_comparable_or_mixed_timing_kinds_are_not_pooled(self):
        for change in ("incompatible", "mixed_kind"):
            with self.subTest(change=change):
                model = _model()
                if change == "incompatible":
                    model.accepted.treatment_measurements["candidate"]["roles"]["average_ttft_ms"] = measurement(
                        None, unit="ms", availability="non_comparable")
                else:
                    model.accepted.observation_results[1]["measurements"]["roles"]["average_ttft_ms"]["kind"] = "direct_timing"
                human = _render(model)
                displayed = _table(human, TOTALS_HEADING)[1][0]["Average TTFT"]
                self.assertIn("non comparable", displayed.replace("_", " ").lower())
                self.assertNotRegex(displayed, r"\d")


class ObservationResultEvidenceTests(unittest.TestCase):
    """Per-observation rows require their own source and score authority."""

    def setUp(self):
        self.accepted = _model().accepted.accepted
        self.accepted.accepted_generation_id = "generation:test"
        for row in self.accepted.observation_matrix:
            row.request_id = "request-" + row.observation_id
        first = self.accepted.observation_matrix[0]
        self.observation = {
            "accepted_generation_id": self.accepted.accepted_generation_id,
            "execution_boundary_fingerprint": self.accepted.execution_boundary_fingerprint,
            "observation_id": first.observation_id, "request_id": first.request_id,
            "case_id": first.case_id, "treatment_id": first.treatment_id,
            "repetition": first.repetition_id,
            "attempts": [{"attempt": 1, "status": "completed",
                          "started_at": "2026-11-05T03:00:01Z", "completed_at": "2026-11-05T03:00:03Z"}],
            "extensions": {},
        }
        metric = self.accepted.metrics[0]
        self.score = {
            "metric_registration": {"id": metric.registration_id, "version": metric.registration_version},
            "case_id": first.case_id, "treatment_id": first.treatment_id,
            "observation_ids": [first.observation_id], "repetition_ids": [first.repetition_id],
            "value": 0.75, "availability": "scored",
        }
        self.documents = {"observation-source": self.observation, "score-source": self.score}
        self.records = {
            identity: obj(artifact_id=identity, role=role, sha256="sha256:" + char * 64,
                          reference="generation/" + identity + ".json")
            for identity, role, char in (("observation-source", "treatment_observation", "a"),
                                         ("score-source", "score_artifact", "b"))
        }
        for case in self.accepted.case_result_matrix:
            case.evidence_refs = (obj(artifact_id="score-source"),)

    def project(self):
        return project_observation_results(self.accepted, documents=self.documents, records=self.records)

    def test_all_planned_rows_and_exact_source_links_are_retained(self):
        rows = self.project()
        self.assertEqual(3, len(rows))
        self.assertEqual(self.observation["observation_id"], rows[0]["observation_id"])
        self.assertEqual(0.75, rows[0]["score"]["value"])
        self.assertEqual("generation/observation-source.json", rows[0]["source_artifact"]["reference"])
        self.assertEqual("sha256:" + "b" * 64, rows[0]["score_artifact"]["sha256"])
        for row in rows[1:]:
            self.assertIsNone(row["source_artifact"])
            self.assertIsNone(row["score_artifact"])
            self.assertIsNone(row["attempt_started_at"])
            self.assertIsNone(row["score"]["value"])
            self.assertEqual("unavailable", row["score"]["availability"])

    def test_grouped_case_score_is_not_copied_to_each_observation(self):
        self.score["observation_ids"].append(self.accepted.observation_matrix[1].observation_id)
        self.score["repetition_ids"].append(self.accepted.observation_matrix[1].repetition_id)
        rows = self.project()
        self.assertTrue(all(row["score"]["value"] is None for row in rows))

    def test_score_and_observation_coordinates_must_match(self):
        for document, key, changed in ((self.observation, "case_id", "other-case"),
                                       (self.observation, "request_id", "other-request"),
                                       (self.score, "case_id", "other-case"),
                                       (self.score, "treatment_id", "other-treatment"),
                                       (self.score, "repetition_ids", [999]),
                                       (self.score, "metric_registration", {"id": "other", "version": "1.0.0"})):
            with self.subTest(key=key):
                previous = document[key]
                document[key] = changed
                try:
                    with self.assertRaises(ValueError):
                        self.project()
                finally:
                    document[key] = previous

    def test_duplicate_primary_score_is_rejected(self):
        self.documents["duplicate-score"] = copy.deepcopy(self.score)
        self.records["duplicate-score"] = obj(artifact_id="duplicate-score", role="score_artifact",
            sha256="sha256:" + "c" * 64, reference="generation/duplicate-score.json")
        self.accepted.case_result_matrix[0].evidence_refs += (obj(artifact_id="duplicate-score"),)
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.project()

    def test_retries_sum_consumption_and_use_earliest_absolute_start(self):
        from AgMark.shared.evaluation.telemetry.consumption import attempt_measurements
        self.observation["attempts"] = [
            {"attempt": 1, "status": "failed", "started_at": "2026-11-05T03:00:05Z", "completed_at": "2026-11-05T03:00:06Z"},
            {"attempt": 2, "status": "completed", "started_at": "2026-11-05T04:00:01+01:00", "completed_at": "2026-11-05T03:00:02Z"},
        ]
        self.observation["extensions"]["arcgrav.telemetry:attempt-series"] = {
            str(index): attempt_measurements(runtime_version="1.0.0", source_identity="test:source",
                tokens={"total_tokens": count}, trace_complete=True)
            for index, count in ((1, 10), (2, 20))
        }
        row = self.project()[0]
        self.assertEqual("2026-11-05T03:00:01Z", row["attempt_started_at"])
        self.assertEqual(30, row["measurements"]["roles"]["total_tokens"]["value"])
        del self.observation["attempts"][1]["started_at"]
        self.assertIsNone(self.project()[0]["attempt_started_at"])


if __name__ == "__main__":
    unittest.main()
