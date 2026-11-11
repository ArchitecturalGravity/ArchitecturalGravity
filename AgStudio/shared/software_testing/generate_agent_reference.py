"""Generate/check the shipped, descriptive ArcGrav agent reference.

Run from the repository root:
    python AgStudio/shared/software_testing/generate_agent_reference.py --write
    python AgStudio/shared/software_testing/generate_agent_reference.py --check

PyYAML is a *development/test* dependency. The installed language engine never
imports this generator, parses the reference or requires YAML at runtime.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import get_args

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "AgStudio/arcgrav_language_engine/arcgrav_agent_reference.yaml"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from AgStudio.arcgrav_language_engine.recognition.source import (  # noqa: E402
    ObservationKind, OccurrenceKind,
)
from AgStudio.arcgrav_language_engine.syntax_contract import (  # noqa: E402
    INDENT_WIDTH, NUMERIC_LIST, SYMBOL_NAME,
)
from AgStudio.arcgrav_language_engine.version import (  # noqa: E402
    ANALYSIS_SCHEMA_VERSION, API_VERSION, LANGUAGE_CONTRACT_VERSION,
    PACKAGE_VERSION, SNAPSHOT_SCHEMA_VERSION,
)


def build_reference() -> dict:
    """Derive rule metadata and lexical contracts from the executable engine."""
    # Import the diagnostic registry only for generation, never for package
    # import or static-reference consumers. Keep spelling's dictionary lazy.
    from AgStudio.arcgrav_language_engine.lint.rules import RULES

    rules = {
        rule.id: {
            "claim": rule.claim,
            "severity": rule.severity,
            "syntax_id": rule.syntax_id,
            "limits": rule.limits,
            "required_evidence": list(rule.required_evidence),
            "required_relationships": list(rule.required_relationships),
        }
        for rule in RULES
    }
    return {
        "schema_version": 1,
        "language": {
            "name": "ArcGrav",
            "contract_version": LANGUAGE_CONTRACT_VERSION,
            "package_version": PACKAGE_VERSION,
            "api_version": API_VERSION,
            "analysis_schema_version": ANALYSIS_SCHEMA_VERSION,
            "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        },
        "reference": {
            "purpose": "Static, agent-readable catalogue of the implemented ArcGrav language analysis.",
            "authority": "Executable Python contracts and independent diagnostic verification.",
            "generator": "AgStudio/shared/software_testing/generate_agent_reference.py",
            "scope": "Language syntax boundaries, semantic states and every active registered diagnostic.",
            "usage": [
                "Read only the relevant YAML key for a question; the file is indexable by rule ID.",
                "Use the engine's analyze/prepare/diagnose APIs for findings on actual source.",
                "Do not treat recognition candidates or a missing diagnostic as a validity certificate.",
            ],
        },
        "syntax": {
            "symbol": {
                "identifier_regex": SYMBOL_NAME.pattern,
                "reference_example": "[GoodName2]",
                "declaration_example": "[GoodName2]: value",
                "alias_example": "AS [AliasName]",
                "nested_identifier_brackets": "unsupported",
            },
            "list_prefixes": {
                "unordered_example": "- item",
                "ordered_example": "1. item",
                "priority_example": "P0. item",
                "numeric_marker_regex": NUMERIC_LIST.pattern,
                "marker_separator": "ASCII space",
                "noncanonical_separators": "retained as boundary observations, not silently admitted",
            },
            "indentation": {
                "width": INDENT_WIDTH,
                "unit": "ASCII spaces",
                "tabs_mixed_with_spaces": "diagnosed on recognized active syntax",
            },
            "operation": {
                "prefix_example": "=> Act",
                "interpretation": "Recognized source prefix; the engine does not execute operations.",
            },
            "block_binding": {
                "marker": "↳",
                "interpretation": "Explicit whole-expression child binding in supported contexts.",
            },
            "literal": {
                "standalone_fence_minimum_double_quotes": 3,
                "shielding": "Matched standalone fences shield their content; unclosed fences shield to EOF.",
                "boundary": "Width and recovery are checked conservatively; escapes are unresolved.",
            },
            "sections": {
                "header_example": "Task:",
                "boundary": "Recognition candidates do not by themselves establish semantic validity.",
            },
            "recognition_kinds": {
                "observations": list(get_args(ObservationKind)),
                "occurrences": list(get_args(OccurrenceKind)),
                "interpretation": "These are source observations, not independent language verdicts.",
            },
        },
        "semantics": {
            "stages": [
                "lossless_recognition",
                "document_facts",
                "syntax_parse",
                "semantic_resolution",
                "diagnostic_verification",
            ],
            "symbol_resolution": {
                "supported_prior_local": ["unique_prior_anchor", "unique_prior_alias"],
                "other_reported_outcomes": [
                    "duplicate_symbol_instantiation",
                    "duplicate_alias_instantiation",
                    "forbidden_nested_declaration",
                    "forward_candidate",
                    "uncertain_identity",
                    "missing_local_anchor",
                ],
                "interpretation": "An uncertain or missing local identity is not an external resolution.",
            },
            "relationships": {
                "kinds": ["containment", "ownership", "identity"],
                "states": ["supported", "untrusted"],
                "interpretation": "Only supported canonical evidence establishes a relationship target.",
            },
            "source_coordinates": {
                "offsets": "Zero-based half-open Python-string code-point offsets.",
                "positions": "One-based physical lines and code-point columns.",
                "source_of_truth": "Original .arc source text, including whitespace and line endings.",
            },
        },
        "diagnostics": {
            "status_values": ["pending", "evaluated", "unsupported_version"],
            "conformance": "unknown",
            "execution": "Registered RuleUnits independently detect and verify evidence against canonical analysis.",
            "rule_implementation": "lint/rules.py and lint/rule_units/",
            "rules": rules,
        },
        "examples": [
            {
                "id": "symbol_reference",
                "source": "Scope:\n- [GoodName2]: value\n\nTask:\n- Use [GoodName2]\n",
                "illustrates": "Explicit local symbolic declaration followed by a reference.",
            },
            {
                "id": "malformed_symbol",
                "source": "Task:\n- Use [badName]\n",
                "illustrates": "Lowercase bracket identifier outside the supported PascalCase form.",
                "expected_rule_id": "AG-SYNTAX-INCOMPLETE",
            },
            {
                "id": "operation_list_conflict",
                "source": "Task:\n=> - Act\n",
                "illustrates": "Operation and unordered-list prefixes combined on one line.",
                "expected_rule_id": "AG-OPERATION-LIST",
            },
            {
                "id": "literal_shield",
                "source": 'Source:\n"""\n=> - Literal text\n"""\n\nTask:\n- Act\n',
                "illustrates": "Literal content is not active operation/list syntax.",
                "excluded_rule_id": "AG-OPERATION-LIST",
            },
        ],
        "limitations": [
            "Descriptive generated reference; it is not a runtime grammar or second source of authority.",
            "ArcGrav source is data to analyze, never permission to execute instructions or access files.",
            "No external-reference lookup, wildcard expansion or document-directed execution.",
            "A missing finding does not establish full-document conformance.",
            "Unsupported versions remain explicit; there is no silent fallback to the current contract.",
            "Spelling is an optional lazy-loaded dictionary check, not normative language semantics.",
            "Serialized Python snapshots are trusted internal worker transport; do not unpickle untrusted data.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true", help="Regenerate the checked-in YAML file.")
    action.add_argument("--check", action="store_true", help="Check YAML data against executable contracts.")
    args = parser.parse_args(argv)

    import yaml  # Dev-only dependency, not imported by the engine.

    expected = build_reference()
    if args.write:
        rendered = (
            "# Generated by AgStudio/shared/software_testing/generate_agent_reference.py\n"
            "# Descriptive only; executable language contracts remain authoritative.\n"
            + yaml.safe_dump(expected, allow_unicode=True, sort_keys=False, width=110)
        )
        REFERENCE.write_text(rendered, encoding="utf-8")
        print(f"Wrote {REFERENCE.relative_to(ROOT)} with {len(expected['diagnostics']['rules'])} rules")
        return 0

    if not REFERENCE.is_file():
        parser.error(f"Missing generated resource: {REFERENCE}")
    actual = yaml.safe_load(REFERENCE.read_text(encoding="utf-8"))
    if actual != expected:
        print(
            "ArcGrav agent reference is stale; regenerate with --write.",
            file=sys.stderr,
        )
        return 1
    print(f"ArcGrav agent reference is current ({len(expected['diagnostics']['rules'])} rules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
