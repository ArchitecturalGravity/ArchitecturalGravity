"""Production report dimensions retain case grain and observation evidence."""

import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from AgMark.gui.requests.reporting import _report_dimensions
from AgMark.shared.runtime.artifacts import ArtifactRecord, sha256_bytes
from AgMark.shared.software_testing.integration.test_registered_score_reporting import (
    _registration, _score,
)


class RegisteredReportDimensionTests(unittest.TestCase):
    def test_case_means_handle_excluded_first_repetition_and_unequal_counts(self):
        registration = _registration()
        registration["metric_version"] = "1.0.0"
        run = SimpleNamespace(
            generation_id="report-dimension-generation",
            accepted_snapshot_id="report-dimension-snapshot",
            execution_boundary_fingerprint="sha256:" + "a" * 64,
            treatment_observations=(), score_artifacts=(), revalidate=Mock(),
        )
        scores = [
            _score("a", None, 1, availability="excluded"),
            _score("a", .25, 2), _score("a", .75, 3), _score("b", 1),
        ]
        retained = {"treatment_observation": [], "score_artifact": []}

        def retain(role, artifact_id, document):
            raw = json.dumps(document).encode("utf-8")
            record = ArtifactRecord(
                artifact_id=artifact_id, role=role,
                reference=f"{run.generation_id}/{artifact_id}.json",
                sha256=sha256_bytes(raw), provenance="report-dimension fixture",
            )
            retained[role].append((record, document))

        for score in scores:
            observation_id = "observation-" + score["score_artifact_id"]
            identity = {
                "accepted_generation_id": run.generation_id,
                "execution_boundary_fingerprint": run.execution_boundary_fingerprint,
            }
            observation = {
                **identity, "observation_id": observation_id,
                "request_id": "request-" + observation_id,
                "case_id": score["case_id"], "treatment_id": score["treatment_id"],
                "repetition": score["repetition_ids"][0], "terminal_status": "completed",
            }
            score.update(
                **identity, accepted_snapshot_id=run.accepted_snapshot_id,
                metric={"id": registration["metric_id"], "version": registration["metric_version"]},
                scoring_grain="repetition", observation_ids=[observation_id],
            )
            retain("treatment_observation", observation_id, observation)
            retain("score_artifact", score["score_artifact_id"], score)

        with patch("AgMark.gui.requests.reporting._retained_json_documents",
                   side_effect=lambda *args, role: tuple(retained[role])):
            counts, observations, cases, summaries, _ = _report_dimensions(run, registration)
        run.revalidate.assert_called_once_with()
        self.assertEqual((4, 3, 1), (counts.planned, counts.scored, counts.excluded))
        self.assertEqual(4, len(observations))
        self.assertEqual([.5, 1], [case.value for case in cases])
        self.assertEqual([3, 1], [len(case.evidence_refs) for case in cases])
        self.assertTrue(all(case.availability.state == "scored" for case in cases))
        self.assertTrue(all(case.availability.exclusion_authority is None for case in cases))
        summary, = summaries
        self.assertEqual((1.5, 2, .75), (summary.numerator, summary.denominator, summary.value))
        self.assertEqual((4, 3, 1), (summary.planned, summary.scorable, summary.excluded))
        self.assertIn("denominator counts cases", summary.availability.reason)


if __name__ == "__main__":
    unittest.main()
