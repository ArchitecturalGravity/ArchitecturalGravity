"""Operation-local schema preparation preserves fresh instance validation."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from AgMark.shared.reporting import revalidation
from AgMark.shared.software_testing.integration.test_reporting_revalidation import _metric_registration
from AgMark.shared.validation import structure


class PreparedSchemaValidationTests(unittest.TestCase):
    def setUp(self):
        self.identity = revalidation._METRIC_REGISTRATION_SCHEMA
        self.entry, self.schema = revalidation._schema_authority(
            self.identity.schema_id, self.identity.schema_version)
        self.document = _metric_registration()

    def test_schema_prepared_once_but_each_document_validated_with_exact_issues(self):
        with patch.object(structure, "_schema_definition_issues",
                          wraps=structure._schema_definition_issues) as definitions:
            validate = structure.prepare_cataloged_validator(schema_document=self.schema, entry=self.entry)
            prepared_count = definitions.call_count
            self.assertGreater(prepared_count, 0)
            self.assertEqual((), validate(self.document, source_id="first"))
            invalid = deepcopy(self.document)
            invalid["registration_version"] = "bad version"
            issues = validate(invalid, source_id="second")
            self.assertTrue(issues)
            self.assertEqual(prepared_count, definitions.call_count)
        self.assertEqual(issues, structure.validate_cataloged_document(invalid,
            schema_document=self.schema, entry=self.entry, source_id="second"))

    def test_prepared_schema_is_not_changed_by_caller_mutation(self):
        validate = structure.prepare_cataloged_validator(schema_document=self.schema, entry=self.entry)
        self.schema["properties"]["registration_version"]["const"] = "not-the-version"
        self.assertEqual((), validate(self.document, source_id="snapshot"))
        changed = structure.prepare_cataloged_validator(schema_document=self.schema, entry=self.entry)
        self.assertTrue(changed(self.document, source_id="fresh"))

    def test_unknown_schema_vocabulary_still_fails_closed(self):
        self.schema["unsupported-validation-keyword"] = True
        validate = structure.prepare_cataloged_validator(schema_document=self.schema, entry=self.entry)
        expected = structure.validate_cataloged_document(self.document,
            schema_document=self.schema, entry=self.entry, source_id="unknown")
        self.assertTrue(expected)
        self.assertEqual(expected, validate(self.document, source_id="unknown"))

    def test_reporting_scope_reuses_preparation_but_next_scope_detects_schema_and_catalog_drift(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            filename = Path(self.entry.file).name
            schema_path = root / filename
            schema_path.write_text(json.dumps(self.schema))
            # Use the actual catalog entry shape rather than inventing authority.
            actual = json.loads(revalidation._CATALOG_PATH.read_text())
            catalog = {"entries": [entry for entry in actual["entries"]
                if entry["schema_id"] == self.identity.schema_id
                and entry["schema_version"] == self.identity.schema_version]}
            catalog_path = root / "catalog.json"
            catalog_path.write_text(json.dumps(catalog))
            with patch.object(revalidation, "_SCHEMA_ROOT", root), \
                    patch.object(revalidation, "_CATALOG_PATH", catalog_path), \
                    patch.object(revalidation, "prepare_cataloged_validator",
                                 wraps=structure.prepare_cataloged_validator) as prepare:
                first = revalidation._ReportingSchemaPreparation()
                validator = first.validator(self.identity)
                self.assertIs(validator, first.validator(self.identity))
                self.assertEqual(1, prepare.call_count)
                self.assertEqual((), validator(self.document, source_id="first"))
                changed = deepcopy(self.schema)
                changed["unsupported-validation-keyword"] = True
                schema_path.write_text(json.dumps(changed))
                self.assertEqual((), validator(self.document, source_id="snapshot"))
                second = revalidation._ReportingSchemaPreparation().validator(self.identity)
                self.assertTrue(second(self.document, source_id="changed"))
                catalog["entries"] = []
                catalog_path.write_text(json.dumps(catalog))
                with self.assertRaises(revalidation.ReportingInputRevalidationError):
                    revalidation._ReportingSchemaPreparation().validator(self.identity)


if __name__ == "__main__":
    unittest.main()
