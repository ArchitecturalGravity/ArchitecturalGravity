"""Direct conformance tests for shared production validation authority."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from AgMark.shared.validation import (
    ArtifactSource,
    BenchmarkDiscoveryCandidate,
    ContractRequirement,
    RepositoryOwnedPath,
    RepositoryPythonSource,
    RetainedArtifactSource,
    SchemaIdentity,
    ValidationExtensionDeclaration,
    ValidationIssue,
    classify_registration_document,
    implementation_artifact_sha256,
    registration_document_inspection_issues,
    sha256_bytes,
    validate_benchmark_discovery,
    validate_evidence_set_outcome,
    validate_exact_schema_identity,
    validate_registered_logic,
    validate_registered_validation_extension_outcome,
    validate_registration_binding_outcome,
    validate_registration_document_schema,
    validate_repository_dependencies,
    validate_repository_ownership,
    validate_schema_catalog,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_SCHEMA_CATALOG = _REPOSITORY_ROOT / "AgMark/shared/schemas/catalog.json"
_CATALOG_SCHEMA = (
    _REPOSITORY_ROOT / "AgMark/shared/schemas/schema_catalog.schema.json"
)
_REGISTRATION_SCHEMA_DOCUMENT = (
    _REPOSITORY_ROOT / "AgMark/shared/schemas/registration.schema.json"
)
_METRIC_REGISTRATION_SCHEMA_DOCUMENT = (
    _REPOSITORY_ROOT / "AgMark/shared/schemas/metric_registration.schema.json"
)
_ARB_METRIC_REGISTRATION = (
    _REPOSITORY_ROOT
    / "AgMark/Authority_Resolution_Benchmark/registrations/v2.0.0"
    / "metric-field-accuracy.json"
)

_REGISTRATION_ID = "arcgrav.benchmark.validation-conformance"
_REGISTRATION_VERSION = "1.0.0"
_CONTRACT_ID = "arcgrav.shared.validation-conformance"
_ARTIFACT_ID = "validation-conformance-logic"
_ARTIFACT_REFERENCE = "AgMark/shared/validation/extensions.py"
_EXTENSION_SCOPE = "arcgrav.test:validation-document"


def _codes(issues: tuple[ValidationIssue, ...]) -> tuple[str, ...]:
    return tuple(issue.code for issue in issues)


def _assert_deterministic(
    testcase: unittest.TestCase,
    issues: tuple[ValidationIssue, ...],
) -> None:
    testcase.assertEqual(
        tuple(sorted(set(issues), key=ValidationIssue.sort_key)),
        issues,
    )


def _registration_schema_validation_inputs() -> tuple[
    dict[str, object],
    dict[str, object],
    dict[SchemaIdentity, dict[str, object]],
]:
    generic_schema = SchemaIdentity(
        "arcgrav.shared.schema.registration",
        "1.0.0",
    )
    metric_schema = SchemaIdentity(
        "arcgrav.shared.schema.metric-registration",
        "1.0.0",
    )
    return (
        json.loads(_SCHEMA_CATALOG.read_text(encoding="utf-8")),
        json.loads(_CATALOG_SCHEMA.read_text(encoding="utf-8")),
        {
            generic_schema: json.loads(
                _REGISTRATION_SCHEMA_DOCUMENT.read_text(encoding="utf-8")
            ),
            metric_schema: json.loads(
                _METRIC_REGISTRATION_SCHEMA_DOCUMENT.read_text(encoding="utf-8")
            ),
        },
    )


def _extension_declaration() -> ValidationExtensionDeclaration:
    return ValidationExtensionDeclaration(
        extension_key="arcgrav.test:validation",
        extension_id="arcgrav.test:validation.logic",
        extension_version="1.0.0",
        validation_kind="logic",
        implementation_artifact_id=_ARTIFACT_ID,
        issue_code_prefix="EXT_ARCGRAV_TEST_",
        compatibility_scope=(_EXTENSION_SCOPE,),
    )


def _registration_fixture(
    *,
    artifact_bytes: bytes = b"validation-conformance-logic",
) -> tuple[dict[str, object], ArtifactSource, ValidationExtensionDeclaration]:
    declaration = _extension_declaration()
    source = ArtifactSource(
        artifact_id=_ARTIFACT_ID,
        reference=_ARTIFACT_REFERENCE,
        data=artifact_bytes,
    )
    registration: dict[str, object] = {
        "schema_id": "arcgrav.shared.schema.registration",
        "schema_version": "1.0.0",
        "registration_id": _REGISTRATION_ID,
        "registration_version": _REGISTRATION_VERSION,
        "registration_kind": "benchmark",
        "status": "active",
        "contracts": [
            {
                "id": _CONTRACT_ID,
                "version": "1.0.0",
            }
        ],
        "implementation_artifacts": [
            {
                "artifact_id": _ARTIFACT_ID,
                "reference": _ARTIFACT_REFERENCE,
                "sha256": sha256_bytes(artifact_bytes),
            }
        ],
        "extensions": {
            declaration.extension_key: declaration.to_dict(),
        },
    }
    return registration, source, declaration


def _registration_outcome(
    registration: dict[str, object],
    source: ArtifactSource,
):
    return validate_registration_binding_outcome(
        registration,
        expected_registration_id=_REGISTRATION_ID,
        expected_registration_version=_REGISTRATION_VERSION,
        contract_requirements=(
            ContractRequirement(
                contract_id=_CONTRACT_ID,
                supported_versions=("1.0.0",),
            ),
        ),
        artifact_sources=(source,),
        allowed_artifact_roots=("AgMark/shared/validation",),
        source_id="validation-conformance-registration",
    )


class CatalogValidationConformanceTests(unittest.TestCase):
    def test_catalog_validation_is_exact_deterministic_and_non_mutating(self) -> None:
        catalog = json.loads(_SCHEMA_CATALOG.read_text(encoding="utf-8"))
        schema_document = json.loads(_CATALOG_SCHEMA.read_text(encoding="utf-8"))
        catalog_before = copy.deepcopy(catalog)
        schema_before = copy.deepcopy(schema_document)

        self.assertEqual(
            (),
            validate_schema_catalog(
                catalog,
                schema_document=schema_document,
            ),
        )
        self.assertEqual(catalog_before, catalog)
        self.assertEqual(schema_before, schema_document)

        tampered = copy.deepcopy(catalog)
        tampered["schema_version"] = "1.0.1"
        tampered_before = copy.deepcopy(tampered)
        issues = validate_schema_catalog(
            tampered,
            schema_document=schema_document,
        )

        self.assertIn("SCHEMA_VERSION_MISMATCH", _codes(issues))
        _assert_deterministic(self, issues)
        self.assertEqual(tampered_before, tampered)
        self.assertEqual(schema_before, schema_document)

    def test_exact_schema_identity_does_not_infer_or_repair(self) -> None:
        document = {
            "schema_id": "arcgrav.shared.schema.validation-result",
            "schema_version": "9.9.9",
        }
        before = copy.deepcopy(document)
        issues = validate_exact_schema_identity(
            document,
            expected=SchemaIdentity(
                "arcgrav.shared.schema.validation-result",
                "1.0.0",
            ),
            source_id="validation-result",
        )

        self.assertEqual(("SCHEMA_VERSION_MISMATCH",), _codes(issues))
        _assert_deterministic(self, issues)
        self.assertEqual(before, document)


class RegistrationDocumentClassificationConformanceTests(unittest.TestCase):
    def test_classification_precedes_family_validation_without_mutation(self) -> None:
        documents = (
            (
                {
                    "schema_id": "arcgrav.shared.schema.registration",
                    "schema_version": "1.0.0",
                    "registration_kind": "benchmark",
                },
                ("benchmark", True, True),
            ),
            (
                {
                    "schema_id": "arcgrav.shared.schema.registration",
                    "schema_version": "1.0.0",
                    "registration_kind": "scorer",
                },
                ("scorer", False, True),
            ),
            (
                {
                    "schema_id": "arcgrav.shared.schema.metric-registration",
                    "schema_version": "1.0.0",
                    "registration_id": "arcgrav.metric.example",
                },
                ("metric", False, True),
            ),
            (
                {
                    "schema_id": "arcgrav.shared.schema.unsupported",
                    "schema_version": "1.0.0",
                    "registration_kind": "runner",
                },
                ("runner", True, False),
            ),
            (
                {
                    "schema_id": "arcgrav.shared.schema.unsupported",
                    "schema_version": "1.0.0",
                    "registration_kind": "scorer",
                },
                (None, False, False),
            ),
        )

        for document, expected in documents:
            with self.subTest(document=document):
                before = copy.deepcopy(document)
                first = classify_registration_document(document)
                second = classify_registration_document(document)
                self.assertEqual(first, second)
                self.assertEqual(
                    expected,
                    (
                        first.family,
                        first.application_authority,
                        first.schema_supported,
                    ),
                )
                self.assertEqual(before, document)


    def test_unrecognized_non_application_material_has_inspection_only_issues(self) -> None:
        documents = (
            (
                {
                    "schema_id": "arcgrav.shared.schema.unsupported",
                    "schema_version": "1.0.0",
                    "registration_kind": "scorer",
                },
                "REGISTRATION_SCHEMA_UNSUPPORTED",
                "/schema_id",
            ),
            (
                {
                    "schema_id": "arcgrav.shared.schema.registration",
                    "schema_version": "1.0.0",
                    "registration_kind": "unrecognized-extension",
                },
                "REGISTRATION_FAMILY_UNSUPPORTED",
                "/registration_kind",
            ),
        )

        for document, expected_code, expected_pointer in documents:
            with self.subTest(document=document):
                before = copy.deepcopy(document)
                first = registration_document_inspection_issues(
                    document,
                    source_id="registration-inspection",
                )
                second = registration_document_inspection_issues(
                    document,
                    source_id="registration-inspection",
                )

                self.assertEqual(first, second)
                self.assertEqual((expected_code,), _codes(first))
                self.assertEqual(expected_pointer, first[0].json_pointer)
                _assert_deterministic(self, first)
                self.assertEqual(before, document)

        claimed_application = {
            "schema_id": "arcgrav.shared.schema.unsupported",
            "schema_version": "1.0.0",
            "registration_kind": "runner",
        }
        self.assertEqual(
            (),
            registration_document_inspection_issues(
                claimed_application,
                source_id="claimed-application",
            ),
        )


class RegistrationDocumentSchemaConformanceTests(unittest.TestCase):
    def test_recognized_non_application_families_use_declared_schema(self) -> None:
        catalog, catalog_schema, schema_documents = (
            _registration_schema_validation_inputs()
        )
        metric = json.loads(_ARB_METRIC_REGISTRATION.read_text(encoding="utf-8"))
        self.assertNotIn("registration_kind", metric)
        metric_before = copy.deepcopy(metric)

        first = validate_registration_document_schema(
            metric,
            catalog=catalog,
            catalog_schema_document=catalog_schema,
            schema_documents=schema_documents,
            source_id="authority-resolution-metric",
        )
        second = validate_registration_document_schema(
            metric,
            catalog=catalog,
            catalog_schema_document=catalog_schema,
            schema_documents=schema_documents,
            source_id="authority-resolution-metric",
        )

        self.assertEqual((), first)
        self.assertEqual(first, second)
        self.assertEqual(metric_before, metric)

        generic, _, _ = _registration_fixture()
        generic["registration_kind"] = "scorer"
        generic_before = copy.deepcopy(generic)
        generic_issues = validate_registration_document_schema(
            generic,
            catalog=catalog,
            catalog_schema_document=catalog_schema,
            schema_documents=schema_documents,
            source_id="generic-scorer-registration",
        )

        self.assertEqual((), generic_issues)
        self.assertEqual(generic_before, generic)

    def test_unsupported_schema_diagnostic_is_deterministic_and_non_mutating(self) -> None:
        catalog, catalog_schema, schema_documents = (
            _registration_schema_validation_inputs()
        )
        document = {
            "schema_id": "arcgrav.shared.schema.unsupported",
            "schema_version": "1.0.0",
            "registration_kind": "scorer",
        }
        before = copy.deepcopy(document)

        first = validate_registration_document_schema(
            document,
            catalog=catalog,
            catalog_schema_document=catalog_schema,
            schema_documents=schema_documents,
            source_id="unsupported-registration",
        )
        second = validate_registration_document_schema(
            document,
            catalog=catalog,
            catalog_schema_document=catalog_schema,
            schema_documents=schema_documents,
            source_id="unsupported-registration",
        )

        self.assertEqual(first, second)
        self.assertEqual(("REGISTRATION_SCHEMA_UNSUPPORTED",), _codes(first))
        self.assertEqual("/schema_id", first[0].json_pointer)
        _assert_deterministic(self, first)
        self.assertEqual(before, document)

    def test_dedicated_schema_does_not_accept_generic_only_fields(self) -> None:
        catalog, catalog_schema, schema_documents = (
            _registration_schema_validation_inputs()
        )
        metric = json.loads(_ARB_METRIC_REGISTRATION.read_text(encoding="utf-8"))
        metric["registration_kind"] = "metric"
        before = copy.deepcopy(metric)

        issues = validate_registration_document_schema(
            metric,
            catalog=catalog,
            catalog_schema_document=catalog_schema,
            schema_documents=schema_documents,
            source_id="authority-resolution-metric",
        )

        self.assertEqual(("SCHEMA_STRUCTURE_INVALID",), _codes(issues))
        self.assertEqual("/registration_kind", issues[0].json_pointer)
        self.assertEqual(
            "arcgrav.shared.schema.metric-registration",
            issues[0].schema.schema_id if issues[0].schema else None,
        )
        _assert_deterministic(self, issues)
        self.assertEqual(before, metric)

    def test_generic_schema_still_requires_its_declared_fields(self) -> None:
        catalog, catalog_schema, schema_documents = (
            _registration_schema_validation_inputs()
        )
        generic, _, _ = _registration_fixture()
        generic["registration_kind"] = "scorer"
        del generic["registration_kind"]
        before = copy.deepcopy(generic)

        issues = validate_registration_document_schema(
            generic,
            catalog=catalog,
            catalog_schema_document=catalog_schema,
            schema_documents=schema_documents,
            source_id="generic-scorer-registration",
        )

        self.assertEqual(("SCHEMA_STRUCTURE_INVALID",), _codes(issues))
        self.assertEqual("/registration_kind", issues[0].json_pointer)
        _assert_deterministic(self, issues)
        self.assertEqual(before, generic)


class RegistrationValidationConformanceTests(unittest.TestCase):
    def test_registration_authority_binds_exact_identity_and_bytes(self) -> None:
        registration, source, _ = _registration_fixture()
        before = copy.deepcopy(registration)

        outcome = _registration_outcome(registration, source)

        self.assertTrue(outcome.valid)
        self.assertTrue(
            outcome.matches(
                registration,
                source_id="validation-conformance-registration",
            )
        )
        self.assertEqual(before, registration)

        tampered = copy.deepcopy(registration)
        tampered["registration_version"] = "1.0.1"
        tampered["implementation_artifacts"][0]["sha256"] = sha256_bytes(
            b"different-logic"
        )
        tampered_before = copy.deepcopy(tampered)

        invalid = _registration_outcome(tampered, source)

        self.assertFalse(invalid.valid)
        self.assertIn("REGISTRATION_VERSION_MISMATCH", _codes(invalid.issues))
        self.assertIn("REGISTRATION_ARTIFACT_HASH_MISMATCH", _codes(invalid.issues))
        _assert_deterministic(self, invalid.issues)
        self.assertEqual(tampered_before, tampered)

    def test_python_artifact_identity_rejects_crlf_alternate_bytes(self) -> None:
        lf_bytes = b"line one\nline two\n"
        crlf_bytes = b"line one\r\nline two\r\n"
        registration, _, _ = _registration_fixture(artifact_bytes=lf_bytes)
        registration["implementation_artifacts"][0]["sha256"] = (
            implementation_artifact_sha256(_ARTIFACT_REFERENCE, lf_bytes)
        )
        crlf_source = ArtifactSource(
            artifact_id=_ARTIFACT_ID,
            reference=_ARTIFACT_REFERENCE,
            data=crlf_bytes,
        )

        invalid = _registration_outcome(registration, crlf_source)
        self.assertFalse(invalid.valid)
        self.assertIn("REGISTRATION_ARTIFACT_HASH_MISMATCH", _codes(invalid.issues))
        self.assertNotEqual(
            implementation_artifact_sha256(_ARTIFACT_REFERENCE, lf_bytes),
            implementation_artifact_sha256(_ARTIFACT_REFERENCE, crlf_bytes),
        )

    def test_validated_registration_authority_rejects_later_mutation(self) -> None:
        registration, source, _ = _registration_fixture()
        outcome = _registration_outcome(registration, source)
        mutated = copy.deepcopy(registration)
        mutated["status"] = "inactive"

        self.assertFalse(
            outcome.matches(
                mutated,
                source_id="validation-conformance-registration",
            )
        )


class RepositoryValidationConformanceTests(unittest.TestCase):
    def test_repository_ownership_and_dependencies_fail_closed(self) -> None:
        valid_ownership = (
            RepositoryOwnedPath(
                "AgMark/shared/validation/core.py",
                "production",
            ),
            RepositoryOwnedPath(
                "AgMark/shared/software_testing/conformance/test_validation.py",
                "developer_testing",
            ),
        )
        self.assertEqual((), validate_repository_ownership(valid_ownership))

        invalid_ownership = (
            RepositoryOwnedPath(
                "AgMark/shared/validation/core.py",
                "developer_testing",
            ),
            RepositoryOwnedPath(
                "AgMark/shared/software_testing/conformance/test_validation.py",
                "production",
            ),
        )
        ownership_issues = validate_repository_ownership(invalid_ownership)
        self.assertEqual(
            {
                "DEVELOPER_TESTING_OWNERSHIP_INVALID",
                "PRODUCTION_OWNERSHIP_INVALID",
            },
            set(_codes(ownership_issues)),
        )
        _assert_deterministic(self, ownership_issues)

        source = RepositoryPythonSource(
            "AgMark/shared/validation/bad_dependencies.py",
            (
                "from AgMark.gui import app\n"
                "from AgMark.Authority_Resolution_Benchmark import package\n"
                "from AgMark.shared.software_testing import ci\n"
            ),
        )
        dependency_issues = validate_repository_dependencies(
            (source,),
            benchmark_module_prefixes=(
                "AgMark.Authority_Resolution_Benchmark",
            ),
        )
        self.assertEqual(
            {
                "PRODUCTION_TESTING_IMPORT_FORBIDDEN",
                "SHARED_FRONTEND_IMPORT_FORBIDDEN",
                "SHARED_BENCHMARK_IMPORT_FORBIDDEN",
            },
            set(_codes(dependency_issues)),
        )
        _assert_deterministic(self, dependency_issues)

    def test_discovery_requires_exact_validated_registration_authority(self) -> None:
        registration, source, _ = _registration_fixture()
        outcome = _registration_outcome(registration, source)
        valid = BenchmarkDiscoveryCandidate(
            package_root="AgMark/Authority_Resolution_Benchmark",
            registration_source_id="validation-conformance-registration",
            registration=registration,
            registration_validation=outcome,
        )
        self.assertEqual((), validate_benchmark_discovery((valid,)))

        mutated = copy.deepcopy(registration)
        mutated["registration_version"] = "1.0.1"
        stale = BenchmarkDiscoveryCandidate(
            package_root="AgMark/Authority_Resolution_Benchmark",
            registration_source_id="validation-conformance-registration",
            registration=mutated,
            registration_validation=outcome,
        )
        issues = validate_benchmark_discovery((stale,))

        self.assertIn(
            "BENCHMARK_DISCOVERY_REGISTRATION_VALIDATION_MISMATCH",
            _codes(issues),
        )
        _assert_deterministic(self, issues)

        missing = BenchmarkDiscoveryCandidate(
            package_root="AgMark/Unregistered_Benchmark",
            registration_source_id="missing-registration",
            registration=None,
        )
        missing_issues = validate_benchmark_discovery((missing,))
        self.assertEqual(
            ("BENCHMARK_DISCOVERY_REGISTRATION_MISSING",),
            _codes(missing_issues),
        )


class RetainedEvidenceValidationConformanceTests(unittest.TestCase):
    def test_retained_evidence_requires_exact_bytes_and_never_repairs(self) -> None:
        source = RetainedArtifactSource(
            artifact_id="response",
            reference="evidence/response.json",
            data=b'{"response":"ok"}',
            provenance="runner",
        )
        artifact = {
            "artifact_id": "response",
            "reference": source.reference,
            "sha256": source.sha256,
            "availability": "retained",
        }
        before = copy.deepcopy(artifact)

        outcome = validate_evidence_set_outcome(
            (artifact,),
            sources=(source,),
            evidence_set_id="evidence-set-valid",
            generation_id="generation-valid",
            terminal_state="accepted",
            source_id="retained-evidence",
            required_artifact_ids=("response",),
        )

        self.assertTrue(outcome.valid)
        self.assertTrue(outcome.publication_authorized)
        self.assertTrue(outcome.authorizes("response", source.sha256))
        self.assertEqual(before, artifact)

        tampered = copy.deepcopy(artifact)
        tampered["sha256"] = sha256_bytes(b'{"response":"tampered"}')
        tampered_before = copy.deepcopy(tampered)
        invalid = validate_evidence_set_outcome(
            (tampered,),
            sources=(source,),
            evidence_set_id="evidence-set-invalid",
            generation_id="generation-invalid",
            terminal_state="accepted",
            source_id="retained-evidence",
            required_artifact_ids=("response",),
        )

        self.assertFalse(invalid.valid)
        self.assertFalse(invalid.publication_authorized)
        self.assertIn("EVIDENCE_ARTIFACT_HASH_MISMATCH", _codes(invalid.issues))
        self.assertIn(
            "EVIDENCE_REQUIRED_ARTIFACT_NOT_AUTHORITATIVE",
            _codes(invalid.issues),
        )
        _assert_deterministic(self, invalid.issues)
        self.assertEqual(tampered_before, tampered)


class RegisteredExtensionValidationConformanceTests(unittest.TestCase):
    def test_registered_logic_is_additive_and_mutation_isolated(self) -> None:
        registration, source, declaration = _registration_fixture()
        registration_outcome = _registration_outcome(registration, source)
        authority = validate_registered_validation_extension_outcome(
            registration,
            registration_outcome=registration_outcome,
            declaration=declaration,
            source_id="validation-extension-authority",
        )
        self.assertTrue(authority.valid)

        document = {"values": ["original"]}
        before = copy.deepcopy(document)

        def validator(value: object) -> tuple[ValidationIssue, ...]:
            assert isinstance(value, dict)
            value["values"].append("extension-mutation")
            return (
                ValidationIssue(
                    code="EXT_ARCGRAV_TEST_REJECTED",
                    source_id="validation-extension-input",
                    message="registered validation extension rejected the input",
                ),
            )

        issues = validate_registered_logic(
            document,
            authority=authority,
            logic_source=source,
            validator=validator,
            compatibility_scope=_EXTENSION_SCOPE,
            source_id="validation-extension-input",
            shared_issues=(),
        )

        self.assertEqual(("EXT_ARCGRAV_TEST_REJECTED",), _codes(issues))
        self.assertEqual(before, document)
        _assert_deterministic(self, issues)

    def test_invalid_or_mismatched_extension_authority_does_not_execute(self) -> None:
        registration, source, declaration = _registration_fixture()
        registration_outcome = _registration_outcome(registration, source)
        tampered = copy.deepcopy(registration)
        tampered["extensions"][declaration.extension_key][
            "extension_version"
        ] = "1.0.1"
        authority = validate_registered_validation_extension_outcome(
            tampered,
            registration_outcome=registration_outcome,
            declaration=declaration,
            source_id="validation-extension-authority",
        )
        self.assertFalse(authority.valid)
        self.assertIn(
            "VALIDATION_EXTENSION_REGISTRATION_AUTHORITY_MISMATCH",
            _codes(authority.issues),
        )
        self.assertIn(
            "VALIDATION_EXTENSION_DECLARATION_MISMATCH",
            _codes(authority.issues),
        )
        _assert_deterministic(self, authority.issues)

        called = False

        def validator(value: object) -> tuple[ValidationIssue, ...]:
            nonlocal called
            called = True
            return ()

        document = {"value": "unchanged"}
        before = copy.deepcopy(document)
        issues = validate_registered_logic(
            document,
            authority=authority,
            logic_source=source,
            validator=validator,
            compatibility_scope=_EXTENSION_SCOPE,
            source_id="validation-extension-input",
            shared_issues=(),
        )

        self.assertFalse(called)
        self.assertEqual(
            ("VALIDATION_EXTENSION_AUTHORITY_INVALID",),
            _codes(issues),
        )
        self.assertEqual(before, document)

        valid_authority = validate_registered_validation_extension_outcome(
            registration,
            registration_outcome=registration_outcome,
            declaration=declaration,
            source_id="validation-extension-authority",
        )
        mismatched_source = ArtifactSource(
            artifact_id=_ARTIFACT_ID,
            reference=_ARTIFACT_REFERENCE,
            data=b"different-extension-bytes",
        )
        mismatch_issues = validate_registered_logic(
            document,
            authority=valid_authority,
            logic_source=mismatched_source,
            validator=validator,
            compatibility_scope=_EXTENSION_SCOPE,
            source_id="validation-extension-input",
            shared_issues=(),
        )

        self.assertFalse(called)
        self.assertEqual(
            ("VALIDATION_EXTENSION_ARTIFACT_HASH_MISMATCH",),
            _codes(mismatch_issues),
        )
        self.assertEqual(before, document)


if __name__ == "__main__":
    unittest.main()
