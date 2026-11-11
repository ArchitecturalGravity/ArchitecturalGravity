"""Provider-free integration tests for accepted reporting revalidation."""

from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from AgMark.shared.evaluation import (
    IdentityRef,
    SCORER_INVOCATION_CONTRACT_ID,
    SCORER_INVOCATION_CONTRACT_VERSION,
)
from AgMark.shared.evaluation.availability import AvailabilityRecord
from AgMark.shared.reporting import (
    REQUIRED_REPORT_SECTIONS,
    CaseResultEntry,
    ObservationCounts,
    ObservationMatrixEntry,
    RegisteredReportMetric,
    ReportArtifactRef,
    ReportSection,
    ReportingInputRevalidationError,
    TreatmentSummary,
    build_canonical_report_model,
    generate_report_bundle,
    revalidate_accepted_reporting_input,
)
from AgMark.shared.reporting.model import _mint_accepted_reporting_input
from AgMark.shared.runtime.artifacts import (
    ArtifactPayload,
    FilesystemArtifactStore,
    PublicationDestination,
    RETAINABLE_EVIDENCE,
    SchemaBinding,
    publish_accepted_artifact_index,
)
from AgMark.shared.runtime.identity import (
    ExecutionBoundary,
    IdentityRef as RuntimeIdentityRef,
    ProviderRuntimeIdentity,
)


_SCORER_ID = "arcgrav.scorer.reporting-integration"
_SCORER_VERSION = "1.0.0"
_METRIC_ID = "arcgrav.metric.reporting-integration"
_METRIC_VERSION = "1.0.0"
_METRIC_REGISTRATION_ID = "arcgrav.metric-registration.reporting-integration"
_METRIC_REGISTRATION_VERSION = "1.0.0"
_COMPARISON_TRACK = "reporting-integration"


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _metric_registration() -> dict[str, object]:
    return {
        "schema_id": "arcgrav.shared.schema.metric-registration",
        "schema_version": "1.0.0",
        "extensions": {},
        "registration_id": _METRIC_REGISTRATION_ID,
        "registration_version": _METRIC_REGISTRATION_VERSION,
        "metric_id": _METRIC_ID,
        "metric_version": _METRIC_VERSION,
        "name": "Reporting integration score",
        "description": "Provider-free metric for reporting revalidation integration.",
        "classification": "correctness",
        "comparison_track_id": _COMPARISON_TRACK,
        "is_primary_endpoint": True,
        "formula_or_algorithm": "Retain the exact registered score.",
        "required_inputs": ["response"],
        "unit": "score",
        "valid_range": {
            "kind": "numeric",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "directionality": "higher_is_better",
        "numerator_denominator": {
            "uses_rate": False,
            "numerator_rule": "not a rate",
            "denominator_rule": "not a rate",
        },
        "repetition_aggregation": "identity",
        "case_aggregation": "identity",
        "state_treatment": [
            {
                "state": "completed",
                "disposition": "score",
            }
        ],
        "normalization_and_equivalence": "No normalization or semantic equivalence.",
        "availability_and_noncomparability": "Retain explicit shared availability states.",
        "required_companion_values": [],
        "presentation_precision": 3,
        "scorer_or_annotation": {
            "procedure_id": _SCORER_ID,
            "version": _SCORER_VERSION,
            "kind": "scorer",
        },
        "contracts": [
            {
                "id": SCORER_INVOCATION_CONTRACT_ID,
                "version": SCORER_INVOCATION_CONTRACT_VERSION,
            }
        ],
    }


class ReportingRevalidationIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._set_up_evidence(controls={"temperature": 0})

    def _set_up_evidence(self, *, controls) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        benchmark_root = root / "benchmark"
        benchmark_root.mkdir()
        destination = PublicationDestination.benchmark_owned(
            benchmark_root / "evidence",
            benchmark_root=benchmark_root,
        )
        self.store = FilesystemArtifactStore(destination)
        self.generation_id = "generation-reporting-revalidation"

        self.boundary = ExecutionBoundary.build(
            boundary_id="boundary-reporting-revalidation",
            framework=RuntimeIdentityRef(
                "arcgrav.framework.reporting-integration",
                "1.0.0",
            ),
            runner=RuntimeIdentityRef(
                "arcgrav.runner.reporting-integration",
                "1.0.0",
            ),
            provider_runtime=ProviderRuntimeIdentity(
                runtime_id="provider-free-runtime",
                runtime_version="1.0.0",
                provider="provider-free",
                access_method="local",
                model="fixture",
            ),
            controls=controls,
            environment={"runtime_family": "reporting-revalidation"},
        )
        self.metric_registration = _metric_registration()
        response = b'{"answer":"ok"}'

        records = self.store.publish_generation(
            self.generation_id,
            (
                ArtifactPayload(
                    artifact_id="execution-boundary-reporting-revalidation",
                    role="execution_boundary",
                    relative_path="execution-boundary.json",
                    data=self.boundary.canonical_bytes,
                    provenance="integration:reporting-revalidation",
                    retention_class=RETAINABLE_EVIDENCE,
                    media_type="application/json",
                    encoding="utf-8",
                    schema=SchemaBinding(
                        "arcgrav.shared.schema.execution-boundary",
                        "1.0.0",
                    ),
                ),
                ArtifactPayload(
                    artifact_id="metric-registration-reporting-revalidation",
                    role="metric_registration",
                    relative_path="metric-registration.json",
                    data=_json_bytes(self.metric_registration),
                    provenance="integration:reporting-revalidation",
                    retention_class=RETAINABLE_EVIDENCE,
                    media_type="application/json",
                    encoding="utf-8",
                    schema=SchemaBinding(
                        "arcgrav.shared.schema.metric-registration",
                        "1.0.0",
                    ),
                ),
                ArtifactPayload(
                    artifact_id="response-reporting-revalidation",
                    role="response",
                    relative_path="response.json",
                    data=response,
                    provenance="integration:reporting-revalidation",
                    retention_class=RETAINABLE_EVIDENCE,
                    media_type="application/json",
                    encoding="utf-8",
                ),
            ),
        )
        self.records = {record.artifact_id: record for record in records}
        self.index = publish_accepted_artifact_index(
            store=self.store,
            generation_id=self.generation_id,
            terminal_status="accepted",
            artifacts=records,
        )

        response_ref = ReportArtifactRef.from_record(
            self.records["response-reporting-revalidation"]
        )
        boundary_ref = ReportArtifactRef.from_record(
            self.records["execution-boundary-reporting-revalidation"]
        )
        observation_availability = AvailabilityRecord(
            affected_kind="evidence_role",
            affected="response",
            state="retained",
            reason="Exact response evidence retained.",
            source_identity=response_ref.artifact_id,
        )
        score_availability = AvailabilityRecord(
            affected_kind="measurement",
            affected=_METRIC_ID,
            state="scored",
            reason="Registered score retained.",
            source_identity=response_ref.artifact_id,
        )
        metric = RegisteredReportMetric(
            registration=copy.deepcopy(self.metric_registration),
            scorer=IdentityRef(_SCORER_ID, _SCORER_VERSION),
            scoring_contracts=(
                IdentityRef(
                    SCORER_INVOCATION_CONTRACT_ID,
                    SCORER_INVOCATION_CONTRACT_VERSION,
                ),
            ),
        )
        self.accepted = _mint_accepted_reporting_input(
            artifact_index=self.index,
            accepted_snapshot_id="snapshot-reporting-revalidation",
            execution_boundary=boundary_ref,
            execution_boundary_fingerprint=self.boundary.fingerprint,
            benchmark=IdentityRef(
                "arcgrav.benchmark.reporting-integration",
                "1.0.0",
            ),
            case_set=IdentityRef(
                "arcgrav.case-set.reporting-integration",
                "1.0.0",
            ),
            treatment_set=IdentityRef(
                "arcgrav.treatment-set.reporting-integration",
                "1.0.0",
            ),
            comparison_track_id=_COMPARISON_TRACK,
            primary_endpoint=IdentityRef(_METRIC_ID, _METRIC_VERSION),
            metrics=(metric,),
            observation_counts=ObservationCounts(
                planned=1,
                finalized=1,
                completed=1,
                scored=1,
                failed=0,
                missing=0,
                excluded=0,
                non_scorable=0,
            ),
            observation_matrix=(
                ObservationMatrixEntry(
                    observation_id="observation-reporting-revalidation",
                    request_id="request-reporting-revalidation",
                    case_id="case-reporting-revalidation",
                    treatment_id="treatment-reporting-revalidation",
                    repetition_id=1,
                    execution_boundary_fingerprint=self.boundary.fingerprint,
                    availability=observation_availability,
                    evidence_refs=(response_ref,),
                ),
            ),
            case_result_matrix=(
                CaseResultEntry(
                    case_id="case-reporting-revalidation",
                    treatment_id="treatment-reporting-revalidation",
                    execution_boundary_fingerprint=self.boundary.fingerprint,
                    metric_registration_id=_METRIC_REGISTRATION_ID,
                    metric_registration_version=_METRIC_REGISTRATION_VERSION,
                    availability=score_availability,
                    value=1.0,
                    evidence_refs=(response_ref,),
                ),
            ),
            treatment_summaries=(
                TreatmentSummary(
                    treatment_id="treatment-reporting-revalidation",
                    metric_registration_id=_METRIC_REGISTRATION_ID,
                    metric_registration_version=_METRIC_REGISTRATION_VERSION,
                    availability=score_availability,
                    planned=1,
                    finalized=1,
                    completed=1,
                    scorable=1,
                    failed=0,
                    missing=0,
                    excluded=0,
                    non_scorable=0,
                    numerator=1,
                    denominator=1,
                    value=1.0,
                ),
            ),
        )

    def _sections(self) -> dict[str, ReportSection]:
        return {
            name: ReportSection(availability="available")
            for name in REQUIRED_REPORT_SECTIONS
        }

    def _remint(self, **changes: object):
        values = {
            "artifact_index": self.accepted.artifact_index,
            "accepted_snapshot_id": self.accepted.accepted_snapshot_id,
            "execution_boundary": self.accepted.execution_boundary,
            "execution_boundary_fingerprint": (
                self.accepted.execution_boundary_fingerprint
            ),
            "benchmark": self.accepted.benchmark,
            "case_set": self.accepted.case_set,
            "treatment_set": self.accepted.treatment_set,
            "comparison_track_id": self.accepted.comparison_track_id,
            "primary_endpoint": self.accepted.primary_endpoint,
            "metrics": self.accepted.metrics,
            "observation_counts": self.accepted.observation_counts,
            "observation_matrix": self.accepted.observation_matrix,
            "case_result_matrix": self.accepted.case_result_matrix,
            "treatment_summaries": self.accepted.treatment_summaries,
        }
        values.update(changes)
        return _mint_accepted_reporting_input(**values)

    def test_revalidation_authorizes_canonical_report_assembly(self) -> None:
        authority = revalidate_accepted_reporting_input(
            self.accepted,
            store=self.store,
        )
        self.assertTrue(authority.valid)
        self.assertEqual("fixture", authority.model_id)
        self.assertIsNone(authority.reasoning_effort)
        report = build_canonical_report_model(
            authority,
            report_id="report-reporting-revalidation",
            report_version="1.0.0",
            status="complete",
            sections=self._sections(),
            report_manifest_id="manifest-reporting-revalidation",
            generated_at="2026-09-19T20:00:00Z",

        )
        self.assertEqual(self.generation_id, report.accepted_generation_id)

    def test_reasoning_effort_comes_from_the_exact_retained_boundary(self):
        for effort in ("high", "xhigh", "none", None, ""):
            with self.subTest(effort=effort):
                self._set_up_evidence(controls={"temperature": 0, "reasoning_effort": effort})
                authority = revalidate_accepted_reporting_input(self.accepted, store=self.store)
                self.assertEqual(effort or None, authority.reasoning_effort)
                self.assertEqual("fixture", authority.model_id)

    def test_resource_round_trip_preserves_partial_unknown_and_retry_evidence(self):
        from AgMark.shared.adapters._contract import ValidatedRequest
        from AgMark.shared.adapters.execution import emit_terminal_observation
        from AgMark.shared.software_testing.adapters.execution.test_emission import _target, _result
        from AgMark.shared.evaluation.telemetry.consumption import ATTEMPT_MEASUREMENTS, attempt_measurements, aggregate_treatment_measurements
        from AgMark.shared.evaluation.telemetry.source import ATTEMPT_SOURCES, build_attempt_source
        sources = {}
        source=_sha256(b"response")
        def envelope(tokens=None, events=(), complete=False):
            record, value = build_attempt_source(runtime_version="1.0.0", tokens=tokens,
                tool_events=events, trace_complete=complete)
            sources[value["source_identity"]] = record
            return value
        unknown={"invocation_id":"invocation", "tool_id":"shell", "status":"unknown", "evidence_references":[source]}
        for name, envelopes in (
            ("measured",(envelope({"total_tokens":100,"input_tokens":20,"cached_input_tokens":0,"output_tokens":80},complete=True),)),
            ("partial",(envelope({"total_tokens":10},(unknown,)),)),
            ("unavailable",(envelope(),)),
            ("retry",(envelope({"total_tokens":10},complete=True),envelope({"total_tokens":20},complete=True))),
        ):
            with self.subTest(state=name):
                request=ValidatedRequest({}, self.generation_id,"request-reporting-revalidation","observation-reporting-revalidation",
                    "arcgrav.benchmark.reporting-integration","case-reporting-revalidation","treatment-reporting-revalidation",1,
                    self.boundary.fingerprint,self.boundary.to_dict(),{},b"prompt",b"input",_sha256(b"request"),{},None)
                extension={ATTEMPT_MEASUREMENTS:envelopes[0]} if len(envelopes)==1 else {"arcgrav.telemetry:attempt-series":{str(i):value for i,value in enumerate(envelopes,1)}}
                extension[ATTEMPT_SOURCES] = {value["source_identity"]: sources[value["source_identity"]] for value in envelopes}
                document=emit_terminal_observation(request,
                    target=replace(_target(target_class="mock-model"), runtime_version="1.0.0"),
                    execution=_result(response_bytes=b'{"answer":"ok"}'),
                    runner_id="arcgrav.runner.reporting-integration",runner_version="1.0.0",
                    framed_request=b"prompt\n\ninput", request_framing_mode="test-fixture",
                    extensions=extension)
                if len(envelopes)>1:
                    document["attempts"]=[{**document["attempts"][0],"attempt":i,"status":"failed" if i==1 else "completed"} for i in range(1,len(envelopes)+1)]
                raw=_json_bytes(document)
                store=FilesystemArtifactStore(PublicationDestination.benchmark_owned(Path(self._tmp.name)/("resources-"+name),benchmark_root=Path(self._tmp.name)))
                payloads=[ArtifactPayload(artifact_id=r.artifact_id,role=r.role,relative_path=Path(r.reference).name,data=self.store.read_verified(r),provenance=r.provenance,
                    retention_class=RETAINABLE_EVIDENCE,media_type=r.media_type,encoding=r.encoding,schema=r.schema) for r in self.index.artifacts]
                payloads.append(ArtifactPayload(artifact_id="observation-resource",role="treatment_observation",relative_path="observation.json",data=raw,provenance="integration:resource-round-trip",retention_class=RETAINABLE_EVIDENCE,
                    media_type="application/json",encoding="utf-8",schema=SchemaBinding("arcgrav.shared.schema.treatment-observation","1.0.0")))
                records=store.publish_generation(self.generation_id,tuple(payloads))
                index=publish_accepted_artifact_index(store=store,generation_id=self.generation_id,terminal_status="accepted",artifacts=records)
                authority=revalidate_accepted_reporting_input(self._remint(artifact_index=index),store=store)
                expected=aggregate_treatment_measurements([(document,_sha256(raw))],generation_id=self.generation_id,boundary_fingerprint=self.boundary.fingerprint,planned_observations={request.treatment_id:1})
                self.assertEqual(expected[request.treatment_id]["computation_sha256"],authority.treatment_measurements[request.treatment_id]["computation_sha256"])
                with self.assertRaises(TypeError): authority.treatment_measurements[request.treatment_id]["roles"]["total_tokens"]["value"]=999
                model=build_canonical_report_model(authority,report_id="resources-"+name,report_version="1.0.0",status="complete",sections=self._sections(),report_manifest_id="manifest-"+name,generated_at="2026-09-30T00:00:00Z")
                bundle=generate_report_bundle(model,input_evidence_set_id="inputs-"+name,generator=IdentityRef("resource-fixture","1.0.0"),procedure_id="resources",procedure_version="1.0.0",command_or_procedure="retained shared resources",report_reference="report.json",canonical_evidence_reference="canonical.json",human_reference="report.md",manifest_reference="manifest.json")
                self.assertEqual(expected,json.loads(bundle.canonical_evidence.data)["treatment_measurements"])
                evidence = json.loads(bundle.canonical_evidence.data)
                observation = evidence["observation_results"][0]
                self.assertEqual(document["observation_id"], observation["observation_id"])
                self.assertEqual(document["attempts"][0]["started_at"], observation["attempt_started_at"])
                self.assertEqual(expected[request.treatment_id]["roles"], observation["measurements"]["roles"])
                self.assertIn("Treatment Total Averaged Results",bundle.human.data.decode())
                self.assertEqual(bundle.report.sha256, bundle.report_manifest["report"]["sha256"])
                observation_record=next(r for r in records if r.role=="treatment_observation")
                path=store.root/observation_record.reference
                path.chmod(0o600)
                path.write_bytes(raw+b"changed")
                with self.assertRaises(ReportingInputRevalidationError): revalidate_accepted_reporting_input(self._remint(artifact_index=index),store=store)

    def test_generation_projects_one_model_and_binds_exact_components(self) -> None:
        authority = revalidate_accepted_reporting_input(
            self.accepted,
            store=self.store,
        )
        sections = self._sections()
        sections["statistical_summary"] = ReportSection(
            availability="unavailable",
            reason="No registered statistical summary.",
        )
        report = build_canonical_report_model(
            authority,
            report_id="report-reporting-generation",
            report_version="1.0.0",
            status="complete_with_deviations",
            sections=sections,
            report_manifest_id="manifest-reporting-generation",
            generated_at="2026-09-19T20:00:00Z",

            extensions={"fixture:reporting-generation": {"preserved": True}},
        )

        kwargs = {
            "input_evidence_set_id": "evidence-set-reporting-generation",
            "generator": IdentityRef(
                "arcgrav.generator.reporting-integration",
                "1.0.0",
            ),
            "procedure_id": "arcgrav.procedure.reporting-integration",
            "procedure_version": "1.0.0",
            "command_or_procedure": "provider-free deterministic report generation",
            "report_reference": "generated/report.json",
            "canonical_evidence_reference": "generated/canonical-evidence.json",
            "human_reference": "generated/report.md",
            "manifest_reference": "generated/report-manifest.json",
        }
        bundle = generate_report_bundle(report, **kwargs)
        repeated = generate_report_bundle(report, **kwargs)

        self.assertEqual(bundle.report.data, repeated.report.data)
        self.assertEqual(
            bundle.canonical_evidence.data,
            repeated.canonical_evidence.data,
        )
        self.assertEqual(bundle.human.data, repeated.human.data)
        self.assertEqual(bundle.manifest.data, repeated.manifest.data)

        machine = json.loads(bundle.report.data.decode("utf-8"))
        evidence = json.loads(bundle.canonical_evidence.data.decode("utf-8"))
        manifest = json.loads(bundle.manifest.data.decode("utf-8"))
        human = bundle.human.data.decode("utf-8")

        self.assertEqual(
            "unavailable",
            machine["sections"]["statistical_summary"]["availability"],
        )
        self.assertEqual(
            "No registered statistical summary.",
            machine["sections"]["statistical_summary"]["reason"],
        )
        self.assertEqual(
            "retained",
            evidence["observation_matrix"][0]["availability"]["state"],
        )
        self.assertEqual(
            {"preserved": True},
            machine["extensions"]["fixture:reporting-generation"],
        )
        # Detailed availability stays in separate exact evidence, linked by
        # the compact human report rather than duplicated in an appendix.
        self.assertEqual(machine["sections"]["statistical_summary"],
                         evidence["sections"]["statistical_summary"])
        self.assertIn("canonical-evidence.json", human)
        self.assertNotIn("## Appendix", human)

        self.assertNotIn("verification_status", manifest)
        self.assertEqual(bundle.report.sha256, manifest["report"]["sha256"])
        component_hashes = {
            item["artifact_id"]: item["sha256"]
            for item in manifest["components"]
        }
        self.assertEqual(
            {
                component.artifact_id: component.sha256
                for component in bundle.components
            },
            component_hashes,
        )
        self.assertEqual(
            {record.artifact_id for record in self.index.artifacts},
            {item["artifact_id"] for item in manifest["inputs"]},
        )

    def test_canonical_report_rejects_unrevalidated_input(self) -> None:
        with self.assertRaises(TypeError):
            build_canonical_report_model(  # type: ignore[arg-type]
                self.accepted,
                report_id="report-reporting-revalidation",
                report_version="1.0.0",
                status="complete",
                sections=self._sections(),
                report_manifest_id="manifest-reporting-revalidation",
                generated_at="2026-09-19T20:00:00Z",

            )

    def test_retained_byte_drift_fails_closed(self) -> None:
        record = self.records["response-reporting-revalidation"]
        path = self.store.root / record.reference
        path.chmod(0o644)
        path.write_bytes(b'{"answer":"changed"}')
        with self.assertRaises(ReportingInputRevalidationError):
            revalidate_accepted_reporting_input(
                self.accepted,
                store=self.store,
            )

    def test_consumed_evidence_must_match_exact_accepted_reference(self) -> None:
        observation = self.accepted.observation_matrix[0]
        current = observation.evidence_refs[0]
        mismatched = ReportArtifactRef(
            artifact_id=current.artifact_id,
            sha256=_sha256(b"other-response"),
            reference=current.reference,
            availability=current.availability,
        )
        changed = self._remint(
            observation_matrix=(
                replace(observation, evidence_refs=(mismatched,)),
            ),
        )
        with self.assertRaisesRegex(
            ReportingInputRevalidationError,
            "differs from exact accepted authority",
        ):
            revalidate_accepted_reporting_input(
                changed,
                store=self.store,
            )

    def test_metric_scorer_and_contract_authority_are_revalidated(self) -> None:
        changed_registration = copy.deepcopy(self.metric_registration)
        changed_registration["scorer_or_annotation"] = {
            "procedure_id": "arcgrav.scorer.substituted",
            "version": _SCORER_VERSION,
            "kind": "scorer",
        }
        changed_metric = RegisteredReportMetric(
            registration=changed_registration,
            scorer=self.accepted.metrics[0].scorer,
            scoring_contracts=self.accepted.metrics[0].scoring_contracts,
        )
        changed = self._remint(metrics=(changed_metric,))
        with self.assertRaisesRegex(
            ReportingInputRevalidationError,
            "exact scorer",
        ):
            revalidate_accepted_reporting_input(
                changed,
                store=self.store,
            )

        changed_contracts = copy.deepcopy(self.metric_registration)
        changed_contracts["contracts"] = [
            {
                "id": "arcgrav.shared.other-contract",
                "version": "1.0.0",
            }
        ]
        contract_metric = RegisteredReportMetric(
            registration=changed_contracts,
            scorer=self.accepted.metrics[0].scorer,
            scoring_contracts=self.accepted.metrics[0].scoring_contracts,
        )
        contract_changed = self._remint(metrics=(contract_metric,))
        with self.assertRaisesRegex(
            ReportingInputRevalidationError,
            "scoring contracts",
        ):
            revalidate_accepted_reporting_input(
                contract_changed,
                store=self.store,
            )

    def test_retained_metric_registration_must_match_comparison_authority(self) -> None:
        changed_registration = copy.deepcopy(self.metric_registration)
        changed_registration["description"] = "Substituted inline registration."
        changed_metric = RegisteredReportMetric(
            registration=changed_registration,
            scorer=self.accepted.metrics[0].scorer,
            scoring_contracts=self.accepted.metrics[0].scoring_contracts,
        )
        changed = self._remint(metrics=(changed_metric,))
        with self.assertRaisesRegex(
            ReportingInputRevalidationError,
            "differs from accepted reporting authority",
        ):
            revalidate_accepted_reporting_input(
                changed,
                store=self.store,
            )


if __name__ == "__main__":
    unittest.main()
