"""Focused scored-session responsibility conformance."""
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import *
from AgMark.shared.software_testing.adapters.codex_cli.session_test_support import _boundary, _request


class CachePolicyTests(unittest.TestCase):
    def test_cache_policy_is_inferred_from_audited_root_identity_and_reconstructs(self):
        value, record = extract()
        policy = record["cache_policy"]
        self.assertEqual("call_1", policy["cache_key_value"])
        self.assertEqual("codex_root_session_id", policy["cache_key_policy"])
        self.assertEqual("inferred_codex_0_159_0_root_default", policy["cache_key_provenance"])
        self.assertFalse(policy["cache_key_observed"])
        self.assertFalse(policy["derived_contexts_observed"])
        self.assertEqual(("implicit", "codex_request_schema"), (policy["cache_mode"], policy["cache_mode_provenance"]))
        self.assertEqual(record, extract_session_measurements(record, stdout(), runtime_version="0.159.0", process_complete=True)[1])
        retained = value["extensions"][SESSION_METRICS]["extensions"]["openai.codex_cli:session-capture"]
        self.assertEqual(policy, retained["cache_policy"])
        self.assertEqual(record["sha256"], policy["evidence_references"][0])

    def test_unknown_versions_missing_or_nonroot_identity_cannot_claim_key_policy(self):
        rows = [json.loads(line) for line in rollout().splitlines()]
        for changes in ({"source": "cli"}, {"source": {"sub_agent": "review"}}, {"session_id": "other"},
                        {"parent_thread_id": "parent"}, {"cli_version": "0.160.0"}, {"session_id": None}):
            changed = copy.deepcopy(rows)
            changed[0]["payload"].update(changes)
            raw = b"".join((json.dumps(row)+"\n").encode() for row in changed)
            _, record = extract(raw)
            self.assertIsNone(record["cache_policy"]["cache_key_value"])
            self.assertIsNone(record["cache_policy"]["cache_mode"])
        for version in ("0.160.0", "1.2.3"):
            _, record = extract_session_measurements({"availability": "retained", "thread_id": "trial",
                "content_base64": base64.b64encode(rollout()).decode()}, stdout(), runtime_version=version, process_complete=True)
            self.assertEqual("unaudited_codex_runtime_version", record["cache_policy"]["reason"])
        _, record = extract_session_measurements({"availability": "unavailable"}, stdout(), runtime_version="0.159.0", process_complete=True)
        self.assertIsNone(record["cache_policy"]["cache_key_value"])
