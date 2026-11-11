"""Consumption conformance: scope, source meaning, retries, tools and pricing."""
import copy
import json
import unittest
from AgMark.shared.evaluation.telemetry.consumption import (
    ATTEMPT_MEASUREMENTS, attempt_measurements, aggregate_treatment_measurements,
    estimate_component_cost, observed_measurement, registered_resource_efficiency,
    registered_baseline_savings, validate_attempt_measurements)
from AgMark.shared.evaluation.telemetry.model import TelemetryError, RegisteredEfficiencyFormula


def envelope(tokens=None, events=(), complete=False):
    return attempt_measurements(runtime_version="1.2.3", source_identity="sha256:"+"a"*64,
        tokens=tokens or {}, tool_events=events, trace_complete=complete)


def observation(identity="one", measured=None, start="2026-09-30T00:00:00Z", end="2026-09-30T00:00:01Z", status="completed"):
    return {"accepted_generation_id":"g", "execution_boundary_fingerprint":"b", "observation_id":identity, "treatment_id":"control",
        "attempts":[{"attempt":1,"status":status,"started_at":start,"completed_at":end}],
        "extensions":{ATTEMPT_MEASUREMENTS:measured or envelope()}}


def aggregate(*docs, planned=None):
    return aggregate_treatment_measurements([(d, "sha256:"+str(i)*64) for i,d in enumerate(docs, 1)], generation_id="g", planned_observations={"control":planned if planned is not None else len(docs)}, boundary_fingerprint="b")["control"]


def event(identity, status, tool="shell"):
    return {"invocation_id":identity, "tool_id":tool,"status":status,"evidence_references":["retained-event"]}


class TreatmentMeasurementsTests(unittest.TestCase):
    def test_independent_components_and_opaque_total(self):
        value = aggregate(observation(measured=envelope({"total_tokens":100})))
        self.assertEqual(100,value["roles"]["total_tokens"]["value"])
        for role in ("input_tokens","cached_input_tokens","output_tokens","cost","tool_calls","failed_tool_calls"):
            self.assertIsNone(value["roles"][role]["value"])
        self.assertIn("billing meaning unestablished",value["roles"]["total_tokens"]["meaning"])

    def test_complete_empty_tools_observed_zero(self):
        value = aggregate(observation(measured=envelope(complete=True)))
        self.assertEqual(0,value["roles"]["tool_calls"]["value"])
        self.assertEqual(0,value["roles"]["failed_tool_calls"]["value"])
        self.assertEqual("available",value["roles"]["failed_tool_calls"]["availability"])

    def test_duplicates_proposals_retries_and_unknown_outcomes(self):
        events=(event("a","started"),event("a","failed"),event("a","failed"),event("b","completed"),event("c","proposed"),event("d","unknown"))
        value = aggregate(observation(measured=envelope(events=events,complete=True)))
        self.assertEqual(3,value["roles"]["tool_calls"]["value"])
        self.assertEqual(1,value["roles"]["failed_tool_calls"]["value"])
        self.assertEqual("partial",value["roles"]["failed_tool_calls"]["availability"])
        with self.assertRaises(TelemetryError):
            envelope(events=(event("a","failed"),event("a","completed")),complete=True)

    def test_incomplete_trace_is_partial_even_with_no_known_failures(self):
        value=aggregate(observation(measured=envelope(events=(event("a","completed"),))))
        self.assertEqual("partial",value["roles"]["tool_calls"]["availability"])
        self.assertEqual("partial",value["roles"]["failed_tool_calls"]["availability"])
        self.assertEqual(0,value["roles"]["failed_tool_calls"]["value"])

    def test_failed_retry_consumption_and_waiting_duration(self):
        one=observation(measured=envelope({"total_tokens":10}),status="failed")
        two=observation("two",envelope({"total_tokens":20}),start="2026-09-30T00:00:02Z",end="2026-09-30T00:00:04Z")
        value=aggregate(one,two)
        self.assertEqual(30,value["roles"]["total_tokens"]["value"])
        self.assertEqual(4000,value["roles"]["duration"]["value"])
        self.assertEqual(2,value["roles"]["total_tokens"]["details"]["coverage"]["measured_attempts"])

    def test_attempt_series_includes_failed_attempts_without_reusing_usage(self):
        doc=observation()
        doc["attempts"].append({"attempt":2,"status":"completed","started_at":"2026-09-30T00:00:02Z","completed_at":"2026-09-30T00:00:03Z"})
        doc["extensions"]["arcgrav.telemetry:attempt-series"]={"1":envelope({"total_tokens":10}),"2":envelope({"total_tokens":20})}
        del doc["extensions"][ATTEMPT_MEASUREMENTS]
        self.assertEqual(30,aggregate(doc)["roles"]["total_tokens"]["value"])
        del doc["extensions"]["arcgrav.telemetry:attempt-series"]
        self.assertIsNone(aggregate(doc)["roles"]["total_tokens"]["value"])

    def test_overlap_partial_coverage_and_scope(self):
        one=observation(measured=envelope({"total_tokens":7}))
        two=observation("two",envelope({"total_tokens":9}),start="2026-09-30T00:00:00.500Z",end="2026-09-30T00:00:02Z")
        self.assertEqual(2000,aggregate(one,two)["roles"]["duration"]["value"])
        self.assertEqual("partial",aggregate(one,planned=2)["roles"]["total_tokens"]["availability"])
        self.assertEqual("elapsed/incomplete",aggregate(one,planned=2)["roles"]["duration"]["details"]["state"])
        for field in ("accepted_generation_id","execution_boundary_fingerprint"):
            bad=copy.deepcopy(one); bad[field]="other"
            with self.assertRaises(TelemetryError): aggregate(bad)
        with self.assertRaises(TelemetryError): aggregate(one,one)

    def test_incompatible_usage_cannot_pool(self):
        one=observation(measured=envelope({"total_tokens":10}))
        two=observation("two",envelope({"total_tokens":20})); two["extensions"][ATTEMPT_MEASUREMENTS]["roles"]["total_tokens"]["meaning"]="different source definition"
        self.assertEqual("non_comparable",aggregate(one,two)["roles"]["total_tokens"]["availability"])

    def test_cached_subsets_prices_and_opaque_counter_cost(self):
        roles=envelope({"input_tokens":100,"cached_input_tokens":40,"output_tokens":20})["roles"]
        price={"identity":"registered-price","date":"2026-09-30","currency":"USD","model_identity":"model", "source_sha256":"sha256:"+"b"*64,"units":1000,"rates":{"input_tokens":2,"cached_input_tokens":1,"output_tokens":4}}
        from AgMark.shared.runtime.identity import sha256_bytes
        source=json.dumps({key:value for key,value in price.items() if key != "source_sha256"}).encode()
        price["source_sha256"]=sha256_bytes(source)
        self.assertIsNone(estimate_component_cost(roles,pricing=price)["value"])
        for role in ("input_tokens","cached_input_tokens","output_tokens"): roles[role]["kind"]="provider_reported_usage"
        self.assertIsNone(estimate_component_cost(roles,pricing=price)["value"])
        from AgMark.shared.evaluation.telemetry.model import TelemetryCompatibility
        context=TelemetryCompatibility("tokenizer", "request", "framing", "none", "provider", "registered-price", "USD", "runner", "model", "boundary", "attempt").to_dict()
        for role in ("input_tokens","cached_input_tokens","output_tokens"): roles[role]["details"]["compatibility"]=context
        value=estimate_component_cost(roles,pricing=price,pricing_evidence=source)
        self.assertAlmostEqual(.24,value["value"])
        self.assertEqual(60,value["details"]["billable_components"]["input_tokens"])
        self.assertEqual("estimated_cost",value["kind"])
        incompatible={**price,"model_identity":"other"}
        other_source=json.dumps({key:value for key,value in incompatible.items() if key != "source_sha256"}).encode()
        incompatible["source_sha256"]=sha256_bytes(other_source)
        self.assertEqual("non_comparable", estimate_component_cost(roles, pricing=incompatible,pricing_evidence=other_source)["availability"])
        with self.assertRaises(TelemetryError): estimate_component_cost(roles,pricing=price,pricing_evidence=source+b"changed")
        measured=envelope(); measured["roles"]=roles; measured["roles"]["cost"]=value
        validate_attempt_measurements(measured)
        measured["roles"]["cost"]["value"]+=1
        with self.assertRaises(TelemetryError): validate_attempt_measurements(measured)
        for units in (True, float("inf"), float("nan"), 0):
            with self.assertRaises(TelemetryError): estimate_component_cost(roles, pricing={**price,"units":units})

    def test_partial_components_runtime_drift_and_attempt_series_identity(self):
        one=observation(measured=envelope({"total_tokens":10}))
        one["extensions"][ATTEMPT_MEASUREMENTS]["roles"]["total_tokens"]["availability"]="partial"
        self.assertEqual("partial",aggregate(one)["roles"]["total_tokens"]["availability"])
        two=observation("two",envelope({"total_tokens":20}))
        two["extensions"][ATTEMPT_MEASUREMENTS]["runtime_version"]="2.0.0"
        two["extensions"][ATTEMPT_MEASUREMENTS]["roles"]["total_tokens"]["details"]["runtime_version"]="2.0.0"
        self.assertEqual("non_comparable",aggregate(one,two)["roles"]["total_tokens"]["availability"])
        for indexed in ({"2":envelope()}, [], {}):
            bad=copy.deepcopy(one); bad["extensions"]["arcgrav.telemetry:attempt-series"]=indexed
            with self.assertRaises(TelemetryError): aggregate(bad)

    def test_subset_overlap_rules_do_not_add_cached_or_reasoning_twice(self):
        measured=attempt_measurements(runtime_version="1.2.3", source_identity="source", tokens={"total_tokens":120,"input_tokens":100,"cached_input_tokens":40,"output_tokens":20,"reasoning_tokens":5},
            counting_rules={"cached_input_tokens_subset_of_input_tokens":"true", "reasoning_tokens_subset_of_output_tokens":"true"})
        self.assertEqual(120,aggregate(observation(measured=measured))["roles"]["total_tokens"]["value"])
        for subset, parent in (("cached_input_tokens","input_tokens"),("reasoning_tokens","output_tokens")):
            bad=copy.deepcopy(measured); bad["roles"][subset]["value"]=bad["roles"][parent]["value"]+1
            with self.assertRaises(TelemetryError): validate_attempt_measurements(bad)

    def test_registered_efficiency_and_baseline(self):
        measure=observed_measurement(20,unit="tokens",kind="runtime_counter",source="same",meaning="counter",method="observed",evidence_references=("e",))
        formula=RegisteredEfficiencyFormula("reg","tokens-per-correct","1.0.0","total_tokens","correct_results","tokens/correct")
        self.assertEqual(10,registered_resource_efficiency(measure,correct_results=2,formula=formula)["value"])
        self.assertIsNone(registered_resource_efficiency(measure,correct_results=0,formula=formula)["value"])
        baseline={**measure,"value":40}
        self.assertIsNone(registered_baseline_savings(measure,baseline,baseline_identity="control",registration_identity="reg")["value"])
        measure["details"]["execution_boundary_fingerprint"]="b"
        self.assertEqual(.5,registered_baseline_savings(measure,baseline,baseline_identity="control",registration_identity="reg")["value"])
        self.assertEqual("non_comparable",registered_baseline_savings(measure,{**baseline,"source":"different"},baseline_identity="control",registration_identity="reg")["availability"])

    def test_schema_unknown_fields_and_missing_evidence_fail(self):
        value=envelope({"total_tokens":1}); value["unknown"]="forbidden"
        with self.assertRaises(TelemetryError): validate_attempt_measurements(value)
        value=envelope({"total_tokens":1}); value["roles"]["total_tokens"]["evidence_references"]=[]
        with self.assertRaises(TelemetryError): validate_attempt_measurements(value)
