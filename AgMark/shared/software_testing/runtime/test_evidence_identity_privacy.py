"""Closed retained identity and private invocation locator regression tests."""
import unittest
from AgMark.shared.runtime.identity import ExecutionBoundary, IdentityRef, ProviderRuntimeIdentity
from AgMark.shared.runtime.identity.boundary import IdentityError
from AgMark.shared.runtime.identity.canonical import canonical_sha256


def boundary(**kwargs):
    return ExecutionBoundary.build(boundary_id="test", framework=IdentityRef("framework", "1.0.0"),
        runner=IdentityRef("runner", "1.0.0"),
        provider_runtime=ProviderRuntimeIdentity("runtime", "local_process", "1.0.0"), **kwargs)


class EvidenceIdentityPrivacyTests(unittest.TestCase):
    def test_private_locators_and_unknown_controls_fail_before_acceptance(self):
        for controls in ({"codex_binary": "/home/alice/codex"},
                         {"codex_binary": "C:\\Users\\Alice\\codex.exe"},
                         {"wsl_distribution": "Alice-Work"}, {"username": "Alice"},
                         {"temperature": {"personal": 1}}, {"model_id": "alice@example.com"}):
            with self.subTest(controls=controls), self.assertRaises(IdentityError):
                boundary(controls=controls)
        for environment in ({"HOME": "/home/alice"}, {"golden.runtime_executable": "/bin/python"},
                            {"golden.runtime_sha256": "invalid"}):
            with self.subTest(environment=environment), self.assertRaises(IdentityError):
                boundary(environment=environment)

    def test_relative_resource_references_only(self):
        for reference in ("/home/alice/file", "C:/Users/Alice/file", "../file", "a/../file", "https://host/file", "a\\file"):
            with self.subTest(reference=reference), self.assertRaises(IdentityError):
                IdentityRef("runtime", "1.0.0", reference=reference)
        self.assertEqual("runtime/python", IdentityRef("runtime", "1.0.0", reference="runtime/python").reference)

    def test_unknown_extensions_cannot_smuggle_private_metadata(self):
        with self.assertRaises(IdentityError):
            boundary(extensions={"fixture:metadata": {"name": "Alice", "count": 1}})

    def test_current_minimized_identity_round_trips(self):
        value = boundary(controls={"codex_binary": "runtime/codex", "launch_mode": "native", "temperature": 0.2},
                         environment={"golden.runtime_sha256": "sha256:" + "a" * 64})
        self.assertEqual(value.canonical_bytes, ExecutionBoundary.from_document(value.to_dict()).canonical_bytes)

    def test_rehashed_unsafe_document_still_fails_admission(self):
        value = boundary().to_dict()
        value["environment"] = [{"name": "HOME", "value": "/home/alice"}]
        with self.assertRaises(IdentityError):
            ExecutionBoundary.from_document(value)


class PlanEvidencePrivacyTests(unittest.TestCase):
    def test_plan_extensions_are_closed_before_retention(self):
        from AgMark.shared.runtime.orchestration.planning import _extensions, PlanningError
        for value in ({"thirdparty:private": {"username": "Alice"}},
                      {"arcgrav.runtime:execution-only": "Alice"}):
            with self.subTest(value=value), self.assertRaises(PlanningError):
                _extensions(value)
        self.assertEqual({"arcgrav.runtime:execution-only": True}, _extensions({"arcgrav.runtime:execution-only": True}))

    def test_plan_rejects_native_input_paths(self):
        from AgMark.shared.runtime.orchestration.planning import PlannedCaseInput, PlanningError
        with self.assertRaises(PlanningError):
            PlannedCaseInput("case", "sha256:" + "a" * 64, reference="/home/alice/input.json")

    def test_advisory_rejects_unknown_and_personal_metadata(self):
        from AgMark.shared.telemetry.runtime_reference import validate_runtime_advisory
        value = {"schema_version": "1.0.0", "runner_id": "openai.codex-cli", "update_revision": "1",
                 "reference_runtime_version": "1.0.0", "selected_runtime_version": "1.0.0", "status": "match", "blocking": False}
        validate_runtime_advisory(value)
        for changed in ({**value, "username": "Alice"}, {**value, "update_revision": "/home/alice"},
                        {**value, "reference_kind": "legacy"}):
            with self.assertRaises(ValueError):
                validate_runtime_advisory(changed)

    def test_all_registered_prompt_formats_remain_admissible(self):
        import json
        from pathlib import Path
        from AgMark.shared.treatments import freeze, content_entries, CONTENT
        root = Path(__file__).resolve().parents[3]
        definition = json.loads((root / "Authority_Resolution_Benchmark/treatments/v2.0.0/treatment-set.json").read_text())
        for treatment in definition["treatments"]:
            with self.subTest(media_type=treatment["prompt"]["media_type"]):
                frozen = freeze(treatment["treatment_id"], treatment["prompt"], b"controlled input")
                self.assertEqual([frozen], content_entries({"extensions": {CONTENT: [frozen]}}))

class RuntimeVersionPrivacyTests(unittest.TestCase):
    def test_boundary_projects_suffixes_and_rejects_retained_suffixes(self):
        for version in ('1.2.3-privateCustomer', '1.2.3+privateHost', '1.2.3-rc.1+privateHost'):
            identity = ProviderRuntimeIdentity('runtime', 'cli', version)
            self.assertEqual('1.2.3', identity.to_dict()['runtime_version'])
            document = boundary().to_dict()
            document['provider_runtime']['runtime_version'] = version
            with self.assertRaises(IdentityError):
                ExecutionBoundary.from_document(document)

    def test_common_source_removes_suffix_and_rejects_reintroduced_suffix(self):
        from AgMark.shared.evaluation.telemetry.source import build_attempt_source, validate_attempt_source
        source, envelope = build_attempt_source(runtime_version='1.2.3-privateCustomer+privateHost', tokens={'total_tokens': 3})
        self.assertEqual('1.2.3', source['runtime_version'])
        self.assertNotIn('private', str((source, envelope)))
        with self.assertRaises(ValueError):
            validate_attempt_source({**source, 'runtime_version': '1.2.3-privateCustomer'})
