"""Validation fast paths preserve JSON equality and duplicate diagnostics."""

import unittest
from unittest.mock import patch

from AgMark.shared.validation import structure


class StringUniquenessTests(unittest.TestCase):
    def issues(self, values):
        schema = {"type": "array", "uniqueItems": True}
        return structure._array_issues(values, schema, root=schema, identity=None,
            source_id="uniqueness-regression", pointer="/values", ref_stack=())

    def test_large_string_arrays_do_not_use_pairwise_comparison(self):
        values = ["reference-" + str(index) for index in range(2000)]
        with patch.object(structure, "_json_equal", side_effect=AssertionError("pairwise comparison")):
            self.assertEqual([], self.issues(values))
            issues = self.issues(values + [values[0], values[-1], values[0]])
        self.assertEqual(["/values/2000", "/values/2001", "/values/2002"],
            [issue.json_pointer for issue in issues])
        self.assertTrue(all(issue.message ==
            "array item duplicates an earlier item while uniqueItems is true" for issue in issues))

    def test_mixed_json_values_keep_existing_equality_semantics(self):
        values = [True, 1, 1.0, False, 0, 0.0, {}, {}, [1], [1.0], "1", "1"]
        with patch.object(structure, "_json_equal", wraps=structure._json_equal) as compare:
            issues = self.issues(values)
        self.assertGreater(compare.call_count, 0)
        self.assertEqual(["/values/2", "/values/5", "/values/7", "/values/9", "/values/11"],
            [issue.json_pointer for issue in issues])

    def test_empty_and_unicode_string_arrays_keep_exact_equality(self):
        self.assertEqual([], self.issues([]))
        issues = self.issues(["", "é", "e\u0301", "", "é"])
        self.assertEqual(["/values/3", "/values/4"], [issue.json_pointer for issue in issues])


if __name__ == "__main__":
    unittest.main()
