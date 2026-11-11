"""Outline consume one canonical model without Qt or UI parsing."""

from __future__ import annotations

import unittest
from unittest import mock

from AgStudio.gui.structure import outline_entries
from AgStudio.shared import LanguageCore
from AgStudio.shared.document import ParsedDocument, RelationshipState


class StructureProjectionTests(unittest.TestCase):
    def test_projection_preserves_canonical_ranges_and_uncertainty(self) -> None:
        source = ('[Task]: item\r\n"""\n[False]: => *\n"""\n'
                  '=>\n`Unknown` [Open\n')
        document = LanguageCore.parse_document(
            LanguageCore.open_source(source, arcgrav_version="unverified")
        )
        entries = outline_entries(document)
        self.assertEqual(tuple(entry.fact_id for entry in entries),
                         tuple(fact.id for fact in document.structural_facts))
        self.assertFalse(any("[False]" in entry.source_range.span.extract(source)
                             for entry in entries))
        for entry in entries:
            fact = document.fact(entry.fact_id)
            self.assertEqual(entry.source_range, fact.source_range)
            self.assertEqual(entry.limitations, fact.limitations)
            self.assertEqual(entry.source_trust, fact.source_trust)
            self.assertEqual(entry.claim_class, "recognition")
            self.assertEqual(entry.containment.status, "untrusted")

    def test_supported_and_absent_relationships_are_projected_from_model(self) -> None:
        document = LanguageCore.parse_document(LanguageCore.open_source(
            "[Parent]: item\n[Child]: item\n", arcgrav_version="current"))
        parent, child = document.structural_facts[:2]
        original = ParsedDocument.relationship

        def relationship(model, fact_id, kind):
            if fact_id == child.id and kind == "containment":
                return RelationshipState("containment", "supported", child.id,
                                         parent.id, ())
            if fact_id == child.id and kind == "ownership":
                return RelationshipState("ownership", "absent", child.id, None, ())
            return original(model, fact_id, kind)

        with mock.patch.object(ParsedDocument, "relationship", relationship):
            entry = next(item for item in outline_entries(document)
                         if item.fact_id == child.id)
        self.assertEqual(entry.containment.target_fact_id, parent.id)
        self.assertEqual(entry.containment.status, "supported")


if __name__ == "__main__":
    unittest.main()
