"""Minimized input and exact scoring response projection for saved generations."""
import json
from pathlib import Path
import tempfile
import unittest
from AgMark.gui.application.console_projection import _accepted_run_live_view, historical_console_update
from AgMark.gui.application.history import HistoricalRun


def observation():
    from AgMark.shared.software_testing.adapters.execution.test_emission import (
        CanonicalExecutionEmissionTests, _result,
    )
    value = CanonicalExecutionEmissionTests()._emit(execution=_result(response_bytes=b"real response\n"))
    value.update(accepted_generation_id="generation-test", observation_id="observation:one", treatment_id="treatment")
    return value


class LiveViewProjectionTests(unittest.TestCase):
    def test_response_remains_exact_without_raw_framed_prompt(self):
        document = observation()
        sections, diagnostics = _accepted_run_live_view([document])
        self.assertEqual(sections, (("observation:one", None, "real response\n"),))
        self.assertEqual(diagnostics, ())
        self.assertNotIn("content_base64", document["extensions"].get("arcgrav.runner:submitted_input", {}))

    def test_absent_input_is_unavailable_and_corrupt_response_rejected(self):
        document = observation()
        document["extensions"].pop("arcgrav.runner:submitted_input", None)
        self.assertIsNone(_accepted_run_live_view([document])[0][0][1])
        document["response"]["sha256"] = "sha256:wrong"
        sections, diagnostics = _accepted_run_live_view([document])
        self.assertIsNone(sections[0][2])
        self.assertTrue(diagnostics)

    def test_saved_run_uses_retained_bytes_and_rejects_changed_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); gid='generation-test'
            path=root/gid/'observation-one'/'observation.json'; path.parent.mkdir(parents=True)
            raw=json.dumps(observation()).encode();path.write_bytes(raw)
            from AgMark.shared.software_testing.validation.test_imported_run import seal_generation
            from zipfile import ZipFile
            (root/f'.{gid}.terminal').write_text('accepted')
            archive=seal_generation(root,gid)
            run=HistoricalRun(gid,root,'Completed','success','today')
            self.assertIsNone(historical_console_update(run).live_view[0][1])
            self.assertEqual(historical_console_update(run).live_view[0][2], 'real response\n')
            self.assertEqual(historical_console_update(run).live_view_treatments, (('observation:one', 'treatment'),))
            with ZipFile(archive, 'a') as package:
                package.writestr('unlisted.json', '{}')
            self.assertEqual(historical_console_update(run).live_view, ())
