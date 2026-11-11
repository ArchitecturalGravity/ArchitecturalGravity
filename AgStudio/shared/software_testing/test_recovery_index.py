"""Recovery indexing preserves the original point-containment scan contract."""

from bisect import bisect_right
from hashlib import sha256
import json
import random
import unittest
from unittest import mock

from AgStudio.arcgrav_language_engine.core import SourceSession
from AgStudio.arcgrav_language_engine.document import (
    DocumentFact, ParsedDocument, SourcePoint, SourceRange,
)
from AgStudio.arcgrav_language_engine.document import model
from AgStudio.arcgrav_language_engine.recognition import (
    RecognitionResult, SourceObservation, SourceOccurrence, SourceRecovery,
    SourceSpan, recognize_source,
)


class CustomRecognitionResult(RecognitionResult):
    """Exercise the document boundary without changing recognition validation.

    These deliberately arbitrary overlays test first-match behavior, not
    recognizer output or language validity.
    """

    def __post_init__(self):
        pass


def custom_recognition(source, observations=(), occurrences=(), recoveries=()):
    base = recognize_source(SourceSession(
        source, arcgrav_version="current", profile="recovery-index-fixture",
        configuration={"spellcheck": False},
    ))
    return CustomRecognitionResult(
        base.session, base.regions, tuple(observations), tuple(occurrences),
        recoveries,
    )


def naive_facts(recognition):
    """Independent linear reference, including stable family IDs and ranges."""
    starts = tuple(region.span.start for region in recognition.regions) or (0,)
    if recognition.source.endswith(tuple("\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029")):
        starts += (len(recognition.source),)

    def point(offset):
        line = max(index for index, start in enumerate(starts) if start <= offset)
        return SourcePoint(offset, line + 1, offset - starts[line] + 1)

    facts = []
    for family, prefix, inputs in (
        ("structure", "s", recognition.observations),
        ("occurrence", "o", recognition.occurrences),
    ):
        for index, item in enumerate(inputs):
            if family == "structure" and item.kind in (
                "unclassified", "literal_content", "unterminated_literal_content",
            ):
                continue
            recovery = next((
                candidate for candidate in recognition.recoveries
                if candidate.span.start <= item.span.start < candidate.span.end
            ), None)
            facts.append(DocumentFact(
                f"{prefix}:{index}", item.kind, family,
                SourceRange(item.span, point(item.span.start), point(item.span.end)),
                item.syntax_id, item.limitations,
                "recovered_untrusted" if recovery else "observed", recovery,
            ))
    return tuple(facts)


class RecoveryIndexTests(unittest.TestCase):
    def assert_matches_reference(self, recognition):
        document = ParsedDocument(recognition)
        expected = naive_facts(recognition)
        self.assertEqual(document.facts(), expected)
        for actual, reference in zip(document.facts(), expected):
            # Equal duplicate recovery records must still select the first object.
            self.assertIs(actual.recovery, reference.recovery)
            self.assertIs(document.fact(actual.id), actual)
        self.assertIs(document.recognition, recognition)
        self.assertIs(document.session, recognition.session)
        self.assertIs(document.recoveries, recognition.recoveries)
        self.assertEqual(document.source, recognition.source)
        session = recognition.session
        identity = json.dumps(
            [session.source, session.arcgrav_version, session.profile,
             session.configuration_key],
            ensure_ascii=True, separators=(",", ":"),
        ).encode("ascii")
        self.assertEqual(document.document_id, sha256(identity).hexdigest())
        return document

    def test_recognized_sources_match_naive_scan(self):
        sources = (
            "", "ordinary prose", "Task: value\n- [Name] *\n",
            "=>\r\nTask: [Open\u2028- [Child\n",
            'α🙂\r\n=>\n"""\r\n- Hidden [Open *\u2028',
            '[Open\n"""\nHidden: *\n"""\nVisible: [Last',
        )
        for source in sources:
            with self.subTest(source=source):
                self.assert_matches_reference(recognize_source(SourceSession(
                    source, arcgrav_version="current",
                    configuration={"spellcheck": False},
                )))

    def test_unordered_overlaps_duplicates_and_half_open_boundaries(self):
        source = "x" * 40
        recoveries = tuple(SourceRecovery(SourceSpan(start, end), 40, kind)
                           for start, end, kind in (
                               (8, 12, "unfinished_symbol"),
                               (2, 20, "unfinished_operation"),
                               (4, 10, "unfinished_symbol"),
                               (8, 12, "unfinished_symbol"),
                               (20, 20, "unfinished_symbol"),
                               (20, 40, "unterminated_literal"),
                               (40, 40, "unfinished_symbol"),
                           ))
        offsets = (40, 0, 1, 2, 7, 8, 9, 10, 11, 12, 19, 20, 39)
        observations = tuple(SourceObservation(
            SourceSpan(offset, 40), "section_header_candidate",
        ) for offset in offsets)
        occurrences = tuple(SourceOccurrence(
            SourceSpan(offset, offset), "wildcard_candidate",
        ) for offset in reversed(offsets))
        document = self.assert_matches_reference(custom_recognition(
            source, observations, occurrences, recoveries,
        ))
        by_start = {fact.span.start: fact for fact in document.structural_facts}
        for offset in (8, 9, 10, 11):
            self.assertIs(by_start[offset].recovery, recoveries[0])
        for offset in (2, 7, 12, 19):
            self.assertIs(by_start[offset].recovery, recoveries[1])
        for offset in (20, 39):
            self.assertIs(by_start[offset].recovery, recoveries[5])
        for offset in (0, 1, 40):
            self.assertIsNone(by_start[offset].recovery)
        self.assertEqual(document.at(40), ())

    def test_empty_recoveries_and_uncovered_gaps(self):
        source = "0123456789\n"
        observations = tuple(SourceObservation(SourceSpan(offset, offset), kind)
                             for offset, kind in (
                                 (0, "unclassified"),
                                 (2, "section_header_candidate"),
                                 (3, "literal_content"),
                                 (4, "section_scalar_candidate"),
                                 (5, "unterminated_literal_content"),
                                 (6, "ordered_list_candidate"),
                                 (7, "operation_candidate"),
                                 (len(source), "section_header_candidate"),
                             ))
        for intervals in ((), ((0, 0), (4, 4)), ((2, 4), (6, 7))):
            with self.subTest(intervals=intervals):
                recoveries = tuple(SourceRecovery(SourceSpan(start, end), end,
                                                   "unfinished_symbol")
                                   for start, end in intervals)
                document = self.assert_matches_reference(custom_recognition(
                    source, observations, recoveries=recoveries,
                ))
                self.assertEqual(tuple(fact.id for fact in document.facts()),
                                 ("s:1", "s:3", "s:5", "s:6", "s:7"))
                self.assertEqual(document.facts()[-1].source_range.start,
                                 SourcePoint(len(source), 2, 1))

    def test_seeded_arbitrary_overlays_match_naive_reference(self):
        source = "α🙂x\r\nβy\u2028zz\n" * 8
        randomizer = random.Random(19483)
        kinds = ("unclassified", "section_header_candidate", "operation_candidate",
                 "literal_content", "unterminated_literal_content")
        for case in range(80):
            def span():
                start = randomizer.randrange(len(source) + 1)
                return SourceSpan(start, randomizer.randrange(start, len(source) + 1))

            recoveries = tuple(SourceRecovery(span(), len(source), "unfinished_symbol")
                               for _ in range(randomizer.randrange(65)))
            observations = tuple(SourceObservation(span(), randomizer.choice(kinds))
                                 for _ in range(50))
            occurrences = tuple(SourceOccurrence(span(), "symbol_candidate")
                                for _ in range(50))
            with self.subTest(case=case):
                self.assert_matches_reference(custom_recognition(
                    source, observations, occurrences, recoveries,
                ))

    def test_recovery_work_scales_by_intervals_and_binary_point_queries(self):
        class CountedRecoveries(tuple):
            def __iter__(self):
                for item in super().__iter__():
                    self.visits += 1
                    yield item

        previous_probes = None
        for count in (128, 512, 2048):
            recoveries = CountedRecoveries(SourceRecovery(
                SourceSpan(2 * index, 2 * index + 1), 2 * count,
                "unfinished_symbol",
            ) for index in reversed(range(count)))
            recoveries.visits = 0
            observations = tuple(SourceObservation(
                SourceSpan(2 * index, 2 * index + 1), "section_header_candidate",
            ) for index in range(count))
            occurrences = tuple(SourceOccurrence(
                SourceSpan(2 * index + 1, 2 * index + 2), "wildcard_candidate",
            ) for index in reversed(range(count)))
            recognition = custom_recognition(
                "x" * (2 * count), observations, occurrences, recoveries,
            )
            probes = 0

            class CountedSequence:
                def __init__(self, values):
                    self.values = values

                def __len__(self):
                    return len(self.values)

                def __getitem__(self, index):
                    nonlocal probes
                    probes += 1
                    return self.values[index]

            def counted_bisect(values, offset):
                return bisect_right(CountedSequence(values), offset)

            with (
                self.subTest(count=count),
                mock.patch.object(model, "bisect_right", side_effect=counted_bisect) as search,
                mock.patch.object(model, "heappush", wraps=model.heappush) as push,
                mock.patch.object(model, "heappop", wraps=model.heappop) as pop,
            ):
                document = ParsedDocument(recognition)
                facts = 2 * count
                self.assertEqual(len(document.facts()), facts)
                self.assertEqual(recoveries.visits, count)
                self.assertEqual(push.call_count, count)
                self.assertEqual(pop.call_count, count)
                # One binary recovery lookup and two source-point lookups per fact.
                self.assertEqual(search.call_count, 3 * facts)
                self.assertLessEqual(probes, facts * (2 + (2 * count).bit_length()))
                if previous_probes is not None:
                    self.assertLess(probes, 6 * previous_probes)
                previous_probes = probes
                self.assertTrue(all(fact.recovery is not None
                                    for fact in document.structural_facts))
                self.assertTrue(all(fact.recovery is None
                                    for fact in document.occurrence_facts))


if __name__ == "__main__":
    unittest.main()
