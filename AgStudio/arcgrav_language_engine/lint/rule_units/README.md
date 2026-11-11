# ArcGrav lint rule units

Every active diagnostic check runs through the same immutable `RuleUnit`
contract. Its behavior is implemented in Python; this page is explanatory and
is neither a runtime input nor an authority or admission prerequisite.

## Executable contract

A rule definition contains its identifier, severity, syntax identity, local
claim, implemented limits, required evidence and required relationships. Each
registered definition has exactly one rule unit. The unit declares read-only
analysis dependencies, node or document scope, and literal handling.

`detect(context, node)` proposes exact source spans with owning nodes and
candidate evidence. `verify(context, candidate)` independently reconstructs the
source premises and returns concrete blockers. A detector's proposed evidence
cannot validate itself. Common checks enforce version, range, shielding,
severity and evidence requirements; rule-specific verification handles the
actual condition. Neither a positive finding nor an empty result asserts
complete document conformance.

## One execution path

Preparation recognizes, parses and resolves source once. All checks consume
that canonical document, syntax tree and semantics. Diagnostics restore lookup
indexes without reparsing. Deterministic registration order and source ranges
control the ordering of findings and suppressed conclusions.

`AG-OPERATION-LIST` owns all supported operation/list-prefix conflicts. An exact
leading `=> - ` with content highlights its five-character witness; other
supported mixed chains highlight the adjacent prefix sequence. No second
operation rule, previous findings, documentation catalogue or compatibility
execution path participates.

Derived evidence is cached per invocation using `context.evidence`. Verification
uses `verification=True` and a separate cache, so detection cannot seed its own
proof. No cache crosses a source revision or analysis context.

## Changes and verification

Implement a rule's precise source predicate and exclusions, register its unique
ID and scheduling position, then add independent positive, negative, boundary,
range, literal/recovery and forged-evidence cases. A metadata record or a
registered callable alone is not coverage. Unsupported behavior must have an
explicit local outcome rather than selecting another implementation.

From the repository root:

```text
python -m unittest AgStudio.shared.software_testing.test_lint_rule_units
python -m unittest AgStudio.shared.software_testing.test_diagnostic_evidence_indexes
python -m unittest AgStudio.shared.software_testing.test_normative_operation_dash
python -m unittest AgStudio.shared.software_testing.test_self_contained_contracts
python -m unittest AgStudio.shared.software_testing.test_analysis_stages
python -m unittest AgStudio.shared.software_testing.test_language_engine_package
python AgStudio/shared/software_testing/ci.py --all
```

The packaging and isolation tests run without documentation. API, analysis
record and snapshot schema version 2 intentionally reject retired contracts;
old snapshot layouts are not upgraded implicitly.
