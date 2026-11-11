"""Qt-free cross-family reproducibility evidence for implemented Stage 01 facts.

These fixtures repeat exact source-associated recognition, not general grammar,
bounded recovery for every malformed form, or normative ArcGrav conformance.
"""

import unittest
from AgStudio.shared.software_testing.contract_cases import EXPECTED_LIMITATIONS
from unittest import mock

from AgStudio.shared.core import LanguageCore, SourceSession
from AgStudio.shared.recognition import recognize_source


VERSION = "unverified-test-version"
PROFILE = "cross-family-recognition-fixture"
COMPOSITE_SOURCE = (
    "Scope:\r\n"
    "  - Parent ↳\n"
    "    1. Ordered\r"
    "    P0. Priority\n"
    "  [Field]: value\u2028"
    "  => Inspect [Field]\n"
    "Task: Review [Field] AS [Alias]\r\n"
    "- See \x60Root.Node\x60 and src/*.arc\n"
    "Ordinary prose α🪐\n"
    "Scope:NoSpace\n"
    "Scope : StillAmbiguous\n"
    "Scope:\u00a0NonAsciiBoundary\n"
    "Scope\u00a0: BeforeColonBoundary\n"
    "Task: \t PostColonTabBoundary\n"
    " \tScope: TabLedBoundary\n"
    " - odd indentation\n"
    "  \t- tab-bearing boundary\n"
    "\u00a0 \t- Unicode Zs boundary\n"
    "[Task\u00a0Name]: WrappedBoundary\n"
    '"""\n'
    "Hidden: value [Symbol] * ↳\n"
    '"""\n'
    "Visible: yes"
)


def session(source, configuration):
    return SourceSession(
        source, arcgrav_version=VERSION, profile=PROFILE,
        configuration=configuration,
    )


def signature(result):
    """Source-exact, independently comparable consumer-visible recognition."""
    return (
        tuple((r.span.start, r.span.end, r.text, r.disposition)
              for r in result.regions),
        tuple((o.span.start, o.span.end, o.kind, o.claim_class,
               o.syntax_id, o.limitations) for o in result.observations),
        tuple((o.span.start, o.span.end, o.kind, o.claim_class,
               o.syntax_id, o.limitations) for o in result.occurrences),
    )


class RecognitionDeterminismTests(unittest.TestCase):
    def assert_recognition_only(self, result):
        self.assertEqual(result.claim_class, "recognition")
        self.assertEqual(result.source, result.round_trip())
        self.assertTrue(all(region.disposition == "unclassified"
                            for region in result.regions))
        self.assertTrue(all(observation.claim_class == "recognition"
                            for observation in result.observations))
        self.assertTrue(all(occurrence.claim_class == "recognition"
                            for occurrence in result.occurrences))
        for region, observation in zip(result.regions, result.observations):
            self.assertEqual(observation.span, region.span)
            self.assertEqual(region.span.extract(result.source), region.text)
            if observation.kind != "unclassified":
                self.assertIsNotNone(observation.syntax_id)
                self.assertEqual(observation.limitations, EXPECTED_LIMITATIONS[observation.kind])
        previous_end = 0
        for occurrence in result.occurrences:
            self.assertGreaterEqual(occurrence.span.start, previous_end)
            self.assertLess(occurrence.span.start, occurrence.span.end)
            self.assertLessEqual(occurrence.span.end, len(result.source))
            self.assertEqual(occurrence.limitations, EXPECTED_LIMITATIONS[occurrence.kind])
            previous_end = occurrence.span.end
        # Stage 00's documented projection has no verified version admission.

    def test_equivalent_detached_context_repeats_all_implemented_fact_kinds(self):
        original_configuration = {"z": {"choices": [1, "α"]}, "a": [True, {"safe": True}]}
        first_session = session(COMPOSITE_SOURCE, original_configuration)
        original_configuration["z"]["choices"].append("caller mutation")
        original_configuration["a"].append("caller mutation")
        equivalent = session(COMPOSITE_SOURCE, {
            "a": [True, {"safe": True}], "z": {"choices": [1, "α"]},
        })
        self.assertEqual(first_session.configuration_key, equivalent.configuration_key)
        self.assertEqual(first_session.configuration["z"]["choices"], [1, "α"])

        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            baseline = recognize_source(first_session)
            repeated = [recognize_source(equivalent) for _ in range(5)]

        self.assertEqual(baseline.round_trip(), COMPOSITE_SOURCE)
        self.assertEqual(baseline.session.arcgrav_version, VERSION)
        self.assertEqual(baseline.session.profile, PROFILE)
        for result in (baseline, *repeated):
            self.assertEqual(result, baseline)
            self.assertEqual(signature(result), signature(baseline))
            self.assert_recognition_only(result)

        self.assertEqual(
            {o.kind for o in baseline.observations},
            {"section_header_candidate", "section_scalar_candidate",
             "section_boundary_candidate", "unordered_list_candidate", "ordered_list_candidate",
             "priority_list_candidate", "operation_candidate", "unclassified",
             "literal_open", "literal_content", "literal_close"},
        )
        self.assertEqual(
            {o.kind for o in baseline.occurrences},
            {"indentation_candidate", "indentation_boundary_candidate",
             "indentation_tab_boundary_candidate",
             "indentation_unicode_boundary_candidate", "block_binding_candidate",
             "symbol_candidate", "alias_marker_candidate",
             "backticked_reference_candidate", "wildcard_candidate"},
        )
        spaced = COMPOSITE_SOURCE.index("Scope : StillAmbiguous")
        self.assertEqual(
            next(o.kind for o in baseline.observations if o.span.start == spaced),
            "section_boundary_candidate",
        )
        unicode_boundary = COMPOSITE_SOURCE.index("Scope:\u00a0NonAsciiBoundary")
        self.assertEqual(
            next(o.kind for o in baseline.observations if o.span.start == unicode_boundary),
            "section_boundary_candidate",
        )
        precolon_unicode = COMPOSITE_SOURCE.index("Scope\u00a0: BeforeColonBoundary")
        candidate = next(o for o in baseline.observations
                         if o.span.start == precolon_unicode)
        self.assertEqual(candidate.kind, "section_boundary_candidate")
        self.assertEqual(candidate.syntax_id, "syntax.section")
        self.assertEqual(candidate.limitations, EXPECTED_LIMITATIONS[candidate.kind])
        postcolon_tab = COMPOSITE_SOURCE.index("Task: \t PostColonTabBoundary")
        candidate = next(o for o in baseline.observations
                         if o.span.start == postcolon_tab)
        self.assertEqual(candidate.kind, "section_boundary_candidate")
        self.assertEqual(candidate.span.extract(COMPOSITE_SOURCE),
                         "Task: \t PostColonTabBoundary\n")
        self.assertEqual(candidate.syntax_id, "syntax.section")
        self.assertEqual(candidate.limitations, EXPECTED_LIMITATIONS[candidate.kind])
        tab_led = COMPOSITE_SOURCE.index(" \tScope: TabLedBoundary")
        candidate = next(o for o in baseline.observations if o.span.start == tab_led)
        self.assertEqual(candidate.kind, "section_boundary_candidate")
        self.assertEqual(candidate.span.extract(COMPOSITE_SOURCE),
                         " \tScope: TabLedBoundary\n")
        self.assertEqual(candidate.syntax_id, "syntax.section")
        self.assertEqual(candidate.limitations, EXPECTED_LIMITATIONS[candidate.kind])
        tab_prefix = next(o for o in baseline.occurrences if o.span.start == tab_led)
        self.assertEqual(tab_prefix.kind, "indentation_tab_boundary_candidate")
        self.assertEqual(tab_prefix.span.extract(COMPOSITE_SOURCE), " \t")
        self.assertEqual(tab_prefix.limitations, EXPECTED_LIMITATIONS[tab_prefix.kind])

        odd = COMPOSITE_SOURCE.index(" - odd indentation")
        odd_fact = next(o for o in baseline.occurrences
                        if o.span.start == odd)
        self.assertEqual(odd_fact.kind, "indentation_boundary_candidate")
        self.assertEqual(odd_fact.span.extract(COMPOSITE_SOURCE), " ")
        self.assertEqual(odd_fact.syntax_id, "syntax.grouping")
        self.assertEqual(odd_fact.limitations, EXPECTED_LIMITATIONS[odd_fact.kind])
        tabbed = COMPOSITE_SOURCE.index("  \t- tab-bearing boundary")
        tab_fact = next(o for o in baseline.occurrences if o.span.start == tabbed)
        self.assertEqual(tab_fact.kind, "indentation_tab_boundary_candidate")
        self.assertEqual(tab_fact.span.extract(COMPOSITE_SOURCE), "  \t")
        self.assertEqual(tab_fact.syntax_id, "syntax.grouping")
        self.assertEqual(tab_fact.limitations, EXPECTED_LIMITATIONS[tab_fact.kind])
        unicode_indent = COMPOSITE_SOURCE.index("\u00a0 \t- Unicode Zs boundary")
        unicode_fact = next(o for o in baseline.occurrences
                            if o.span.start == unicode_indent)
        self.assertEqual(unicode_fact.kind, "indentation_unicode_boundary_candidate")
        self.assertEqual(unicode_fact.span.extract(COMPOSITE_SOURCE), "\u00a0 \t")
        self.assertEqual(unicode_fact.syntax_id, "syntax.grouping")
        self.assertEqual(unicode_fact.limitations, EXPECTED_LIMITATIONS[unicode_fact.kind])
        wrapped = COMPOSITE_SOURCE.index("[Task\u00a0Name]: WrappedBoundary")
        wrapped_fact = next(o for o in baseline.observations
                            if o.span.start == wrapped)
        self.assertEqual(wrapped_fact.kind, "section_boundary_candidate")
        self.assertEqual(wrapped_fact.syntax_id, "syntax.section")
        self.assertEqual(wrapped_fact.limitations, EXPECTED_LIMITATIONS[wrapped_fact.kind])
        hidden = COMPOSITE_SOURCE.index("Hidden: value")
        self.assertEqual(
            next(o.kind for o in baseline.observations if o.span.start == hidden),
            "literal_content",
        )
        self.assertTrue(all(not (hidden <= o.span.start < hidden + len("Hidden: value [Symbol] * ↳"))
                            for o in baseline.occurrences))
        copied_configuration = baseline.session.configuration
        copied_configuration["z"]["choices"].append("external change")
        self.assertEqual(baseline, recognize_source(first_session))

    def test_unresolved_and_unterminated_sources_remain_stable_between_interleaved_runs(self):
        cases = (
            "",
            "Scope:NoSpace\nScope : value\nTwo words: prose\r\n[Open:\n -odd indentation",
            'Task: Visible\n"""\n  => Hidden [Ref] * ↳\nScope: hidden',
            '""""\nScope:\n"""\n- Still hidden\n""""\nPlain prose',
        )
        configuration = {"flags": {"preserve": True}, "items": [1, None, "δ"]}
        baselines = [recognize_source(session(source, configuration)) for source in cases]
        for source, baseline in zip(cases, baselines):
            for _ in range(3):
                repeated = recognize_source(session(source, {
                    "items": [1, None, "δ"], "flags": {"preserve": True},
                }))
                self.assertEqual(signature(repeated), signature(baseline))
                self.assertEqual(repeated, baseline)
                self.assert_recognition_only(repeated)
        self.assertEqual([o.kind for o in baselines[1].observations],
                         ["section_boundary_candidate"] * 2 + ["unclassified"] * 3)
        self.assertEqual(baselines[1].observations[0].limitations, EXPECTED_LIMITATIONS[baselines[1].observations[0].kind])
        self.assertEqual(baselines[2].observations[-1].kind,
                         "unterminated_literal_content")
        self.assertEqual(baselines[2].occurrences, ())
        self.assertEqual([o.kind for o in baselines[3].observations],
                         ["literal_open", "literal_content", "literal_content",
                          "literal_content", "literal_close", "unclassified"])

    def test_new_boundary_families_compose_without_source_or_trust_leakage(self):
        source = (
            "Task:\r\n"
            "-\t \tglob.glob('*.arc') AS [Alias]\t↳\n"
            "  =>\tProcess [Alias]\u2028"
            "Escaped \\[Other] and `[Hidden]` *\n"
            "[Open\n"
            '"""\n'
            "=>\tHidden AS [Alias] ↳ *\n"
            '"""\n'
            "Final prose"
        )
        first = session(source, {"z": [1], "a": True})
        same = session(source, {"a": True, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(signature(result), signature(recognize_source(same)))
        self.assert_recognition_only(result)
        self.assertEqual([o.kind for o in result.observations], [
            "section_header_candidate", "unordered_list_tab_boundary_candidate",
            "operation_boundary_candidate", "unclassified", "unclassified",
            "literal_open", "literal_content", "literal_close", "unclassified",
        ])
        self.assertEqual([o.kind for o in result.occurrences], [
            "wildcard_candidate", "alias_marker_candidate", "symbol_candidate",
            "block_binding_tab_boundary_candidate", "indentation_candidate",
            "symbol_candidate", "wildcard_candidate", "symbol_boundary_candidate",
        ])
        self.assertEqual([r.kind for r in result.recoveries], ["unfinished_symbol"])
        self.assertEqual(result.recoveries[0].resume_at,
                         source.index("[Open\n") + len("[Open\n"))
        self.assertEqual(result.recoveries[0].trust, "untrusted")
        self.assertEqual(result.recoveries[0].limitations, EXPECTED_LIMITATIONS[result.recoveries[0].kind])

    def test_extended_horizontal_and_unicode_markers_compose(self):
        source = (
            "Task\t \u00a0\tName: value\r\n"
            "-\u00a0Use [Source] AS [Alias]\u2003↳\n"
            "  =>\u202fInspect src/*.arc\n"
            "[Open\n"
            '"""\n'
            "Task\u00a0\u2003Name: -\u00a0Hidden * ↳\n"
            '"""\n'
            "Ordinary prose\n"
        )
        first = session(source, {"z": [1], "a": True})
        same = session(source, {"a": True, "z": [1]})
        with mock.patch("builtins.open", side_effect=AssertionError("filesystem")), \
             mock.patch("glob.glob", side_effect=AssertionError("expansion")), \
             mock.patch("os.system", side_effect=AssertionError("process")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            result = recognize_source(first)
            self.assertEqual(signature(result), signature(recognize_source(same)))
        self.assert_recognition_only(result)
        self.assertEqual([fact.kind for fact in result.observations], [
            "section_boundary_candidate", "unordered_list_unicode_boundary_candidate",
            "operation_boundary_candidate", "unclassified", "literal_open",
            "literal_content", "literal_close", "unclassified",
        ])
        self.assertEqual([fact.kind for fact in result.occurrences], [
            "symbol_candidate", "alias_marker_candidate",
            "symbol_candidate", "block_binding_unicode_boundary_candidate",
            "indentation_candidate", "wildcard_candidate",
            "symbol_boundary_candidate",
        ])
        self.assertEqual([fact.kind for fact in result.recoveries],
                         ["unfinished_symbol"])
        self.assertEqual(result.recoveries[0].trust, "untrusted")
        self.assertEqual(result.round_trip(), source)


if __name__ == "__main__":
    unittest.main()
