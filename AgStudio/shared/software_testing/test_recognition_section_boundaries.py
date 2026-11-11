"""Table-driven section-boundary recognition fixtures.

The individual lexical examples are retained from the former per-separator files.
Source preservation, uncertainty, immutability, and no-document-action invariants
are checked once instead of repeating the same harness for every tab/Zs variant.
These are recognition observations, not ArcGrav conformance judgments.
"""

from dataclasses import FrozenInstanceError
from unittest import TestCase, mock
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS

from AgStudio.shared.core import LanguageCore, SourceSession
from AgStudio.shared.recognition import recognize_source


def session(source, configuration=None):
    return SourceSession(
        source,
        arcgrav_version="unverified-test-version",
        profile="section-boundary-matrix",
        configuration=configuration,
    )


# Each pair preserves the former positive and deferred input rows verbatim.
# Extra comparisons with already-covered scalar/list syntax live in
# test_recognition_sections.py and test_recognition_sections_internal_tabs.py.
WHITESPACE_CASES = (
    ("adjacent double tabs",
     (
            "Task\t\tName:\r\n",
            "  Task\t\tName: value\n",
            "[Task\t\tName]:Next\u2028",
            "\t[Task\t\tName]::\n",
            "[Task\t\tName]: \tMore\n",
            "Task\t\t\t\t\tName: value\n",
            "Task\t \tName: value\n",
            "Task \t\tName: value\n",
        ),
     (
            "Task\tName\tExtra: value\n",         # nonadjacent tabs / three parts
            "[Task\t\tName]:/path\n",              # unsupported direct suffix
            "[Task\t\tName]\t: value\n",           # combined pre-colon spacing
            "[[Task\t\tName]]: value\n",           # nested brackets
            "Task\t\tName!: value\n",             # unsupported label punctuation
            "Task\t\tName:\u200bNext\n",          # unsupported Unicode boundary
            "Task Name: value\n",                 # ordinary ASCII-space prose
            "Ordinary prose.\n",
        )),
    ("adjacent triple tabs",
     (
            "Task\t\t\tName:\r\n",
            "[Task\t\t\tName]:Next\u2028",
            "  Task\t\t\tName: value\n",
            "\t[Task\t\t\tName]::\n",
            "[Task\t\t\tName]: \tMore\n",
            "Task\t\t\t\t\tName: value\n",
            "[Task\t\t\t\t\tName]: value\n",
            "Task \t\t\tName: value\n",
            "Task\t\t\t Name: value\n",
        ),
     (
            "Task\t\tName\tExtra: value\n",   # tabs in two runs
            "Task\t\t\tName\tExtra: value\n", # three label parts
            "Task\t\t\tName Extra: value\n",
            "[Task\t\t\tName]\t: value\n",    # pre-colon spacing
            "Task\t\t\tName:/path\n",         # unsupported immediate suffix
            "Task\t\t\tName:\u200bNext\n",
            "Task\t\t\tName!: value\n",       # unsupported label punctuation
            "[[Task\t\t\tName]]: value\n",    # nested brackets
            "Task Name: value\n",             # ordinary ASCII-space prose
            "Ordinary prose.\n",
        )),
    ("adjacent quadruple tabs",
     (
            "Task\t\t\t\tName:\r\n",
            "[Task\t\t\t\tName]:Next\u2028",
            "  Task\t\t\t\tName: value\n",
            "\t[Task\t\t\t\tName]::\n",
            "[Task\t\t\t\tName]: \tMore\n",
            "Task\t\t\t\t\tName: value\n",
            "[Task\t\t\t\t\tName]: value\n",
            "Task \t\t\t\tName: value\n",
            "Task\t\t\t\t Name: value\n",
        ),
     (
            "Task\t\t\tName\tExtra: value\n",    # four tabs, two separate runs
            "Task\t\t\t\tName\tExtra: value\n", # extra label part
            "Task\t\t\t\tName Extra: value\n",
            "[Task\t\t\t\tName]\t: value\n",    # pre-colon spacing
            "Task\t\t\t\tName:/path\n",         # unsupported immediate suffix
            "Task\t\t\t\tName:\u200bNext\n",
            "Task\t\t\t\tName!: value\n",       # unsupported label punctuation
            "[[Task\t\t\t\tName]]: value\n",    # nested brackets
            "Task Name: value\n",               # ordinary ASCII-space prose
            "Ordinary prose.\n",
        )),
    ("Unicode separators",
     (
            "Task\u00a0Name:\r\n",
            "Task\u00a0\u00a0Name: value\n",
            "Task\u00a0\u2003Name: value\n",
            "Task\u2003\u00a0Name:Next\u2028",
            "  Task\u2003Name: value\n",
            "Task\u202fName:Next\u2028",
            "Task\u3000Name::\n",
            "\tTask\u00a0Name: value\n",
            "Task\u00a0Name: \tNext\n",
            " \u00a0\tTask\u00a0Name:\u00a0Next\n",
            "[Task\u00a0Name]: value\n",
            "[Task\u00a0\u00a0Name]: value\n",
            "[Task\u00a0\u2003Name]: value\n",
            "[Task\u202f\u3000Name]::\r\n",
            "[Task\u2003Name]:\r\n",
            "[Task\u202fName]:Next\u2028",
            "[Task\u3000Name]::\n",
            " \u00a0\t[Task\u00a0Name]: \tNext\n",
            "Task\u00a0 \u00a0Name: value\n",
            "Task\u00a0\u2003\u00a0Name: value\n",
            "Task \u00a0 Name: value\n",
            "Task\t \u00a0Name: value\n",
            "[Task\u00a0 \u00a0Name]: value\n",
            "Prose \u00a0 Name: value\n",
        ),
     (
            "Task Name: value\n",                  # ASCII-space prose
            "Task\u00a0\u2003Name\u00a0Extra: value\n", # three label parts
            "Task\u00a0Name\tExtra: value\n",
            "Task\u00a0Name\u2003Extra: value\n",  # three parts
            "Task\u00a0Name\u00a0: value\n",        # combined pre-colon case deferred
            "Task\u00a0\u2003Name\u00a0: value\n", # mixed pair plus pre-colon Zs
            "Task\u00a0\u2003Name:/path\n",       # unsupported direct suffix
            "Task\u00a0\u2003Name:\u200bValue\n", # unsupported post-colon boundary
            "Task\u200bName: value\n",              # non-Zs Unicode
            "Task\u00a0Name:/path\n",               # unsupported direct suffix
            "Task\u00a0Name!: value\n",             # unsupported label
            "Task\u00a0Name:\u200bValue\n",
            "[Task Name]: value\n",               # ASCII-space multiword
            "[Task\u00a0Name\u00a0Extra]: value\n", # three parts
            "[Task\u00a0Name]\u00a0: value\n",     # pre-colon combination deferred
            "[Task\u00a0Name]:/path\n",            # unsupported direct suffix
            "[Task\u00a0Name]:\u200bValue\n",      # unsupported post-colon boundary
            "[Task\u200bName]: value\n",           # non-Zs Unicode
            "[[Task\u00a0Name]]: value\n",         # extra brackets
            "[[Task\u00a0\u2003Name]]: value\n", # nested bracket pair not admitted
        )),
    ("ASCII and tab separators",
     (
            "Task \tName:\r\n",
            "Task\t Name: value\n",
            "[Task \tName]:Next\u2028",
            "[Task\t Name]::\n",
            "  Task \tName: \tNext\n",
            "\t[Task\t Name]:\u00a0Next\n",
            "Task \t Name: value\n",
            "Task\t  Name: value\n",
            "Task \t\tName: value\n",
            "Task\t \tName: value\n",
            "Task\u00a0 \tName: value\n",
            "Task  \tName: value\n",
        ),
     (
            "Task Name: value\n",              # pure ASCII-space prose
            "[Task Name]: value\n",
            "Task \tName\tExtra: value\n",     # additional label part
            "Task\t Name Extra: value\n",
            "[Task \tName]\t: value\n",        # combined pre-colon spacing
            "Task\t Name\u00a0: value\n",
            "Task \tName:/path\n",             # unsupported direct suffix
            "Task\t Name:\u200bValue\n",      # non-Zs post-colon separator
            "Task \u200b\tName: value\n",
            "Task \tName!: value\n",           # unsupported punctuation
            "[[Task \tName]]: value\n",       # nested brackets
        )),
    ("ASCII and Unicode separators",
     (
            "Task \u00a0Name:\r\n",
            "Task\u00a0 Name: value\n",
            "[Task \u2003Name]:Next\u2028",
            "[Task\u202f Name]::\n",
            "  Task \u00a0Name: \tNext\n",
            "\t[Task\u00a0 Name]:\u00a0Next\n",
            "Task \u3000Name: \n",
            "[Task\u3000 Name]: value\n",
            "Task \u00a0 Name: value\n",
            "Task\u00a0 \u00a0Name: value\n",
            "Task \u00a0\tName: value\n",
            "Task  \u00a0Name: value\n",
        ),
     (
            "Task Name: value\n",                   # pure ASCII-space prose
            "[Task Name]: value\n",
            "Task\u00a0 Name\tExtra: value\n",     # three label parts
            "Task \u00a0Name\u2003Extra: value\n",
            "[Task \u00a0Name]\t: value\n",       # pre-colon spacing combined
            "Task\u00a0 Name\u00a0: value\n",
            "Task \u00a0Name:/path\n",             # unsupported direct suffix
            "Task\u00a0 Name:\u200bValue\n",       # non-Zs suffix boundary
            "Task \u200bName: value\n",            # non-Zs internal glyph
            "Task \u00a0Name!: value\n",           # punctuation in label
            "[[Task \u00a0Name]]: value\n",       # extra brackets
        )),
    ("tab and Unicode separators",
     (
            "Task\t\u00a0Name:\r\n",
            "Task\u00a0\tName: value\n",
            "[Task\t\u2003Name]:Next\u2028",
            "[Task\u202f\tName]::\n",
            "  Task\t\u00a0Name: \tNext\n",
            "\t[Task\u00a0\tName]:\u00a0Next\n",
            "Task\t \u00a0Name: value\n",
            "Task\u00a0 \tName: value\n",
            "Task \t\u00a0Name: value\n",
            "Task\t\u00a0\tName: value\n",
        ),
     (
            "Task\t\u00a0Name\tExtra: value\n", # three label parts
            "Task\u00a0\tName\u2003Extra: value\n",
            "[Task\t\u00a0Name]\t: value\n",    # combined pre-colon whitespace
            "Task\t\u00a0Name\u00a0: value\n",
            "Task\t\u00a0Name:/path\n",         # unsupported direct suffix
            "Task\t\u00a0Name:\u200bNext\n",  # non-Zs immediate suffix
            "Task\t\u200bName: value\n",       # non-Zs internal glyph
            "Task\t\u00a0Name!: value\n",      # unsupported label punctuation
            "[[Task\t\u00a0Name]]: value\n",  # nested brackets
            "Task Name: prose\n",              # ordinary multiword prose
        )),
    ("extended horizontal separators",
     (
            "Task\t\t\t\t\tName: value\r\n",
            "[Task \t\t\u00a0Name]:Next\u2028",
            "Task\u00a0\u2003\u00a0Name:\n",
            "  Task\t \u00a0\tName: value\n",
        ),
     (
            "Task Name: value\n",              # ordinary ASCII-space prose
            "Task\tName\tExtra: value\n",    # two separator runs
            "Task\u00a0\u200bName: value\n",  # non-Zs Unicode whitespace
            "Task\t\tName:/path\n",          # unsupported direct suffix
            "[[Task\t\tName]]: value\n",    # nested brackets
        )),

)


class SectionBoundaryMatrixTests(TestCase):
    def test_positive_and_deferred_source_shapes_keep_exact_ranges(self):
        for family, positive, deferred in WHITESPACE_CASES:
            source = "".join(positive + deferred)
            result = recognize_source(session(source))
            expected = (("section_boundary_candidate",) * len(positive)
                        + ("unclassified",) * len(deferred))
            with self.subTest(family=family):
                self.assertEqual(result.source, source)
                self.assertEqual(result.round_trip(), source)
                self.assertEqual(len(result.regions), len(expected))
                self.assertEqual(len(result.observations), len(expected))
                self.assertTrue(all(region.disposition == "unclassified"
                                    for region in result.regions))
            offset = 0
            for index, (line, region, fact, kind) in enumerate(
                    zip(positive + deferred, result.regions, result.observations,
                        expected)):
                with self.subTest(family=family, index=index, line=line):
                    self.assertEqual(fact.kind, kind)
                    self.assertEqual(region.span, fact.span)
                    self.assertEqual(region.span.start, offset)
                    self.assertEqual(region.text, line)
                    self.assertEqual(fact.span.extract(source), line)
                    self.assertEqual(fact.claim_class, "recognition")
                    if index < len(positive):
                        self.assertEqual(fact.syntax_id, "syntax.section")
                        self.assertEqual(fact.limitations, EXPECTED_LIMITATIONS[fact.kind])
                    else:
                        self.assertIsNone(fact.syntax_id)
                        self.assertEqual(fact.limitations, ())
                offset = region.span.end
            self.assertEqual(offset, len(source))

    def test_shared_literal_determinism_and_no_document_actions(self):
        # A single cross-family invariant, rather than identical fixture setup
        # repeated separately for each combination of tabs and Unicode spaces.
        prefixes = (
            "Task\t\tName: glob.glob('*.arc') ↳\r\n",
            "Task\t\t\tName: glob.glob('*.arc') ↳\r\n",
            "Task\t\t\t\tName: glob.glob('*.arc') ↳\r\n",
            "Task\u00a0Name: glob.glob('*.arc') ↳\r\n",
            "Task \tName: glob.glob('*.arc') ↳\r\n",
            "Task \u00a0Name: glob.glob('*.arc') ↳\r\n",
            "Task\t\u00a0Name: glob.glob('*.arc') ↳\r\n",
            "Task\t\t\t\t\tName: glob.glob('*.arc') ↳\r\n",
        )
        for index, prefix in enumerate(prefixes):
            source = (prefix + '"""\n'
                      "Task\t\u00a0Name: hidden [Symbol] * ↳\n"
                      '"""\n'
                      '""""\n'
                      "Task\t\u00a0Name: hidden until EOF\n")
            with self.subTest(index=index):
                original = session(source, {"z": [1], "a": {"safe": True}})
                equivalent = session(source, {"a": {"safe": True}, "z": [1]})
                with (mock.patch("builtins.open",
                                 side_effect=AssertionError("source-triggered I/O")),
                      mock.patch("subprocess.run",
                                 side_effect=AssertionError("source-triggered execution")),
                      mock.patch("glob.glob",
                                 side_effect=AssertionError("source-triggered expansion")),
                      mock.patch("socket.create_connection",
                                 side_effect=AssertionError("source-triggered network"))):
                    result = recognize_source(original)
                    self.assertEqual(result, recognize_source(equivalent))
                self.assertEqual(result.round_trip(), source)
                self.assertEqual(result.observations[0].kind,
                                 "section_boundary_candidate")
                self.assertFalse(any(
                    o.kind == "section_boundary_candidate" and o.span.start >= len(prefix)
                    for o in result.observations
                ))
                self.assertTrue(any(o.kind == "literal_content"
                                    for o in result.observations))
                with self.assertRaises(FrozenInstanceError):
                    result.observations[0].kind = "section_header_candidate"


if __name__ == "__main__":
    import unittest
    unittest.main()
