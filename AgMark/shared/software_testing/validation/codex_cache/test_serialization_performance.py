"""Only class metadata is reused; each replay document is still admitted."""

import copy
import unittest
from unittest.mock import patch

from AgMark.shared.software_testing.validation.codex_cache.fixtures import replay
from AgMark.shared.validation.codex_cache import serialization
from AgMark.shared.validation.codex_cache.metrics import treatment_summary


class ReplayMetadataCacheTests(unittest.TestCase):
    def setUp(self):
        serialization._dataclass_metadata.cache_clear()
        self.addCleanup(serialization._dataclass_metadata.cache_clear)

    def test_type_hints_resolve_once_per_class_but_every_document_is_validated(self):
        document = replay().to_dict()
        with patch.object(serialization, "get_type_hints", wraps=serialization.get_type_hints) as hints, \
                patch.object(serialization, "validate_cataloged_document",
                             wraps=serialization.validate_cataloged_document) as validate:
            first = serialization.admit_validation(document)
            first_count = hints.call_count
            second = serialization.admit_validation(copy.deepcopy(document))
        self.assertGreater(first_count, 0)
        self.assertEqual(first_count, hints.call_count)
        classes = [call.args[0] for call in hints.call_args_list]
        self.assertEqual(len(classes), len(set(classes)))
        self.assertEqual(2, validate.call_count)
        self.assertIsNot(first, second)
        self.assertEqual(document, first.to_dict())
        self.assertEqual(document, second.to_dict())

    def test_warm_metadata_does_not_accept_changed_structure_or_statistics(self):
        document = replay().to_dict()
        serialization.admit_validation(document)
        changed = copy.deepcopy(document)
        changed["requests"][0]["fields"]["uncached_input_tokens"]["value"] += 1
        with self.assertRaisesRegex(ValueError, "request arithmetic or availability changed"):
            serialization.admit_validation(changed)
        changed = copy.deepcopy(document)
        changed["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "validation schema rejected"):
            serialization.admit_validation(changed)

    def test_membership_index_preserves_order_coverage_and_rejects_bad_linkage(self):
        replays = (replay(2), replay(1))
        ids = ("observation-1", "observation-2")
        arguments = dict(generation_id="generation", treatment_id="treatment", replays=replays)
        value = treatment_summary(**arguments, scored_observation_ids=ids)
        self.assertEqual(ids, value.scored_observation_ids)
        self.assertEqual(("observation-2", "observation-1"), value.sampled_observation_ids)
        self.assertEqual(2, value.coverage.validation_replays_planned)
        self.assertEqual(value.to_dict(), serialization.admit_validation(
            serialization.validation_bytes(value)).to_dict())
        with self.assertRaisesRegex(ValueError, "identity must be unique"):
            treatment_summary(**arguments, scored_observation_ids=(ids[0], ids[0]))
        with self.assertRaisesRegex(ValueError, "not linked"):
            treatment_summary(**arguments, scored_observation_ids=(ids[0],))
        with self.assertRaisesRegex(ValueError, "one replay per scored observation"):
            treatment_summary(generation_id="generation", treatment_id="treatment",
                replays=(replays[0], replays[0]),
                scored_observation_ids=ids)


if __name__ == "__main__":
    unittest.main()
