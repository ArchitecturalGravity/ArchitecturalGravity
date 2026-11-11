"""Executable local rule definitions and independently verified diagnostics."""
from dataclasses import dataclass, replace
from hashlib import sha256
import re

from ..diagnostics import Finding, RuleEvidence, SEVERITY_ORDER
from ..version import LANGUAGE_CONTRACT_VERSION
from ..document import ParsedDocument
from ..recognition import SourceSpan
from .syntax import SyntaxTree, _LINE_ENDINGS
from .quoted_elements import (RULE_ID as QUOTED_RULE_ID, MESSAGE as QUOTED_MESSAGE, unmatched_quoted_elements,
                              COLLISION_RULE_ID, COLLISION_MESSAGE, quoted_element_collisions)
from .semantics import Semantics
from .document_end import (RULE_ID as END_SECTION_RULE, MESSAGE as END_SECTION_MESSAGE, document_end_span,
                           START_RULE_ID, START_MESSAGE, document_start_span)
from .spelling import SPELLING_MESSAGES, spelling_spans
from .members import MEMBER_FINDING_MESSAGES, MEMBER_INFO_MESSAGES, resolve_members, member_finding_spans
from .editor_checks import MESSAGES as EDITOR_MESSAGES, spans as editor_spans, content_owners
from .rule_units import RuleContext, build_units
from .rule_units.backtick_whitespace import spans as _backtick_whitespace_spans
from .rule_units.literal_fence_width import spans as _literal_width_spans
from .rule_units.block_separator import spans as _block_separator_spans
from .rule_units.structural_checks import (
    index as _structural_index, parent_expression as _parent_expression,
    span as _extra_span,
)


@dataclass(frozen=True, slots=True)
class Rule:
    id: str
    claim: str
    severity: str
    syntax_id: str
    limits: str
    required_evidence: tuple[str, ...] = ()
    required_relationships: tuple[str, ...] = ()



RULES = (
    Rule(
        'AG-OPERATION-LIST',
        'Do not combine operation and list prefixes on the same line',
        'error',
        'syntax.operation',
        'Adjacent ASCII-space-separated canonical prefixes only; prose punctuation excluded',
    ),
    Rule(
        'AG-LIST-MIXED',
        'Avoid combining unordered, ordered and priority prefixes',
        'warning',
        'syntax.unordered',
        'Adjacent distinct canonical list families only',
    ),
    Rule(
        'AG-INDENT-WIDTH',
        'Use two spaces per nesting level',
        'error',
        'syntax.grouping',
        'Odd ASCII-space prefix on recognized active syntax; no inference about prose',
    ),
    Rule(
        'AG-INDENT-MIXED',
        'Do not mix tabs and spaces',
        'error',
        'syntax.grouping',
        'Both characters in one active syntax indentation prefix',
    ),
    Rule(
        'AG-LITERAL-FENCE-WIDTH',
        'Each literal parent fence must be strictly longer than every fence within its content',
        'error',
        'syntax.literal',
        'Recursive checks within canonical literal contexts; nearest matching fences identify children; equal-width boundary intent remains unresolved',
    ),
    Rule(
        'AG-LITERAL-UNCLOSED',
        'Open and close literal blocks with paired delimiters',
        'warning',
        'syntax.literal',
        'Recovery of standalone matching-width quote fences (three or more); escapes unresolved',
    ),
    Rule(
        'AG-SYNTAX-INCOMPLETE',
        'Bracket-wrapped symbolic anchors and references',
        'error',
        'syntax.symbol',
        'Active bracket groups must be matched, non-nested PascalCase identifiers without spaces',
    ),
    Rule(
        'AG-OPERATION-INCOMPLETE',
        'An arrow is followed by an operation',
        'warning',
        'syntax.operation',
        'Bare recognized arrow only; recovery does not define broader grammar',
    ),
    Rule(
        'AG-SYMBOL-BEFORE-DEFINITION',
        'Define a symbolic anchor before its first reference',
        'error',
        'syntax.symbol',
        'A supported explicit definition occurs later in this document',
    ),
    Rule(
        'AG-SYMBOL-NO-LOCAL-ANCHOR',
        'Explicit references require symbolic anchors',
        'error',
        'syntax.symbol',
        'No supported explicit definition in the document; uncertain identities excluded',
    ),
    Rule(
        'AG-SYMBOL-DUPLICATE-INSTANTIATION',
        'Do not instantiate an existing identity again using [Name]:',
        'error',
        'syntax.symbol',
        'A second active [Name]: after a prior local instantiation; mutation intent is not inferred',
    ),
    Rule(
        'AG-ALIAS-DUPLICATE-INSTANTIATION',
        'Do not instantiate an existing identity again using AS [Name]',
        'error',
        'syntax.alias',
        'A second active AS [Name] after a prior local instantiation; mutation intent is not inferred',
    ),
    Rule(
        'AG-BINDING-REFERENCE-COLON',
        'Use ↳ instead of : to bind children to an expression ending in a symbolic reference',
        'warning',
        'syntax.block_binding',
        'Complete prefixed expression with a trailing symbol-colon and a clear indented child; sole-symbol bodies excluded',
    ),
    Rule(
        'AG-PARENT-BLOCK-OPENER',
        'Add a trailing : or explicit ↳ binding before child context',
        'error',
        'syntax.grouping',
        'Recognized prefixed parents with clear children, or isolated symbols followed by list members; prose and recovery excluded',
    ),
    Rule(
        'AG-ORDERED-PARENT-COLON',
        'Add a trailing : to an ordered-list item containing children',
        'error',
        'syntax.grouping',
        'Canonical ordered item with a clear indented child; explicit binding and uncertain syntax excluded',
    ),
    Rule(
        'AG-BINDING-CHILD',
        'Whole-expression binding is followed by indented children',
        'warning',
        'syntax.block_binding',
        'No physically attached child; incomplete fragment and ambiguous indentation remain possible',
    ),
    Rule(
        'AG-SECTION-EMPTY',
        'Empty sections should be omitted',
        'warning',
        'syntax.section',
        'Recognized header without nonblank physically owned context; fragments may be intentional',
    ),
    Rule(
        'AG-INDENT-JUMP',
        'Use two spaces per nesting level',
        'warning',
        'syntax.grouping',
        'Adjacent recognized active lines increase indentation by more than two spaces; partial contexts remain possible',
    ),
    Rule(
        'AG-ALIAS-SOURCE',
        'An alias names identifiable preceding context',
        'warning',
        'syntax.alias',
        'Terminal AS [Name] with no source value; binder ambiguity excluded',
    ),
    Rule(
        'AG-LIST-EMPTY',
        'Each list marker introduces an item',
        'error',
        'syntax.unordered',
        'Bare canonical marker only; provide item content',
    ),
    Rule(
        'AG-OPERATION-MULTIPLE',
        'Keep one operation per line',
        'error',
        'syntax.operation',
        'Two or more adjacent ASCII-space-separated arrow prefixes; prose arrows excluded',
    ),
    Rule(
        'AG-WILDCARD-BARE',
        'Avoid an unqualified wildcard when scope could be excessively broad',
        'warning',
        'syntax.wildcard',
        'Standalone selector without a physical section or parent; external or procedural scope remains unknown',
    ),

    Rule(
        'AG-SYMBOL-NESTED-DECLARATION',
        'Only AS may introduce a new symbol inside a symbol body',
        'error',
        'syntax.symbol',
        'No prior eligible local identity; external-symbol/property identity remains unresolved',
    ),

    Rule(
        'AG-SYMBOL-UNUSED',
        'Instantiated symbols and aliases require a subsequent reference',
        'error',
        'syntax.symbol',
        'Supported [Name]: and AS [Name] declarations; same-name uncertainty can suppress an absent local use',
    ),

    Rule(
        'AG-BACKTICK-WHITESPACE',
        'A backticked structural name MUST NOT contain whitespace',
        'error',
        'syntax.symbol',
        'Complete backtick tokens only; textual values should use double quotes',
    ),

)
RULES += (Rule('AG-BLOCK-SEPARATOR', 'Separate distinct section and symbol declaration blocks with a blank line', 'critical', 'syntax.section', 'Parsed sibling block boundaries only; initial blocks, references and recovery excluded'),)
RULES += tuple(Rule(id, message, 'error', 'syntax.grouping', 'Editor formatting contract; literal bodies and opaque values excluded')
               for id, message in EDITOR_MESSAGES.items())
RULES += tuple(Rule(id, message, 'information' if id in MEMBER_INFO_MESSAGES else 'warning', 'syntax.symbol', 'Source-ordered local member paths; uncertain ownership and unsupported names excluded')
               for id, message in MEMBER_FINDING_MESSAGES.items())
RULES += tuple(Rule(id, message, 'warning' if id == 'AG-SPELLING' else 'information', 'syntax.section', 'Offline American English dictionary; conservative ordinary text only; suggestions never modify source')
               for id, message in SPELLING_MESSAGES.items())
RULES += (Rule(END_SECTION_RULE, END_SECTION_MESSAGE, 'critical', 'syntax.section', 'Final plain canonical root parent, not final line; symbolic decoration excluded; empty documents exempt; protected text cannot establish a section'),)
RULES += (Rule(START_RULE_ID, START_MESSAGE, 'information', 'syntax.section', 'First meaningful root element must be a plain section; empty documents exempt; no retrieval semantics inferred'),)
RULES += (Rule(QUOTED_RULE_ID, QUOTED_MESSAGE, 'warning', 'syntax.literal', 'Whole complete active double-quoted tokens; exact case and whitespace; exclude self and opaque fences'),)
RULES += (Rule(COLLISION_RULE_ID, COLLISION_MESSAGE, 'error', 'syntax.literal', 'Complete quoted tokens touching both ends of intervening bare text; separated elements, escapes and opaque fences excluded'),)
_EVIDENCE = {
    COLLISION_RULE_ID: 'embedded_double_quote_collision',
    QUOTED_RULE_ID: 'unmatched_exact_quoted_element',
    START_RULE_ID: 'initial_root_element',
    END_SECTION_RULE: 'final_root_parent',
    'AG-LITERAL-FENCE-WIDTH': 'outer_inner_width',
    'AG-BLOCK-SEPARATOR': 'adjacent_distinct_blocks',
    'AG-SYMBOL-UNUSED': 'unused_explicit_declaration',
    'AG-BACKTICK-WHITESPACE': 'backtick_whitespace',
    'AG-OPERATION-LIST': 'canonical_prefix_chain', 'AG-LIST-MIXED': 'prefix_chain',
    'AG-INDENT-WIDTH': 'active_indentation', 'AG-INDENT-MIXED': 'active_indentation',
    'AG-LITERAL-UNCLOSED': 'unclosed_literal', 'AG-SYNTAX-INCOMPLETE': 'malformed_symbol',
    'AG-OPERATION-INCOMPLETE': 'bare_operation', 'AG-SYMBOL-BEFORE-DEFINITION': 'forward_candidate',
    'AG-SYMBOL-NO-LOCAL-ANCHOR': 'missing_local_anchor',
    'AG-SYMBOL-DUPLICATE-INSTANTIATION': 'duplicate_symbol_instantiation',
    'AG-ALIAS-DUPLICATE-INSTANTIATION': 'duplicate_alias_instantiation',
    'AG-SYMBOL-NESTED-DECLARATION': 'forbidden_nested_declaration',
    'AG-BINDING-CHILD': 'physical_whole_line',
    'AG-BINDING-REFERENCE-COLON': 'reference_colon_child',
    'AG-ORDERED-PARENT-COLON': 'ordered_parent_without_colon',
    'AG-PARENT-BLOCK-OPENER': 'parent_without_opener',
    'AG-SECTION-EMPTY': 'empty_physical_section', 'AG-INDENT-JUMP': 'skipped_indent_level',
    'AG-ALIAS-SOURCE': 'missing_alias_source', 'AG-LIST-EMPTY': 'bare_list_marker',
    'AG-OPERATION-MULTIPLE': 'multiple_arrow_prefixes', 'AG-WILDCARD-BARE': 'bare_unowned_selector',
}
_EVIDENCE.update({id: 'ordinary_english_word' for id in SPELLING_MESSAGES})
_EVIDENCE.update({id: 'local_member_order' for id in MEMBER_FINDING_MESSAGES})
_EVIDENCE.update({id: 'editor_formatting' for id in EDITOR_MESSAGES})
RULES = tuple(replace(r, required_evidence=(_EVIDENCE[r.id],),
                     required_relationships=('physical_whole_line',) if r.id == 'AG-BINDING-CHILD' else ())
              for r in RULES)
REGISTRY = {r.id: r for r in RULES}
if len(REGISTRY) != len(RULES):
    raise RuntimeError("rule identifiers must be unique")
_RULE_UNITS = build_units(REGISTRY)
if set(_RULE_UNITS) != {rule.id for rule in RULES}:
    raise RuntimeError("each active lint rule requires one rule unit")
_NODE_RULE_UNITS = tuple(sorted(
    (unit for unit in _RULE_UNITS.values() if unit.scope == 'node'),
    key=lambda unit: unit.order,
))
_DOCUMENT_RULE_UNITS = tuple(sorted(
    (unit for unit in _RULE_UNITS.values() if unit.scope == 'document'),
    key=lambda unit: unit.order,
))


@dataclass(frozen=True, slots=True)
class Candidate:
    rule_id: str
    span: SourceSpan
    node_id: int
    message: str
    evidence: tuple[str, ...]


def _unused_declarations(tree, semantics):
    """Find missing later references independently for each supported identity.

    Uncertain occurrences of the same name may conceal a reference; unrelated
    malformed syntax and missing identities must not suppress an unused symbol.
    Repeated instantiations are never references.
    """
    if semantics is None:
        return ()
    uncertain_names = {s.name for s in semantics.symbols if s.kind == 'uncertain'}
    uncertain_names.update(r.reference.name for r in semantics.resolutions
                           if r.status == 'uncertain_identity')
    used = {r.candidates[0] for r in semantics.resolutions
            if r.reference.kind == 'reference'
            and r.status in ('unique_prior_anchor', 'unique_prior_alias')
            and len(r.candidates) == 1}
    return tuple(s for s in semantics.symbols
                 if s.kind in ('anchor', 'alias') and s.name not in uncertain_names
                 and s.span not in used
                 and (tree.nodes[s.node].symbol_body_span == s.span
                      or tree.nodes[s.node].alias_target_span == s.span))


def _semantic_evidence(semantics):
    if semantics is None:
        return {}, set()
    resolutions = {(r.reference.span, r.reference.node): r.status for r in semantics.resolutions}
    bindings = {b.marker for b in semantics.bindings if b.status == 'physical_whole_line' and not b.children}
    return resolutions, bindings



_EXTRA_RULES = frozenset(('AG-SECTION-EMPTY', 'AG-INDENT-JUMP', 'AG-ALIAS-SOURCE',
                          'AG-LIST-EMPTY', 'AG-OPERATION-MULTIPLE', 'AG-WILDCARD-BARE',
                          'AG-BINDING-REFERENCE-COLON', 'AG-ORDERED-PARENT-COLON', 'AG-PARENT-BLOCK-OPENER'))


def admission(candidate: Candidate, document: ParsedDocument, tree: SyntaxTree, semantics: Semantics | None = None, *, _rule_context=None) -> tuple[str, ...]:
    """Check exact source premises, then independently verify the rule predicate."""
    blockers = []
    unit_context = _rule_context if _rule_context is not None else RuleContext(document, tree, semantics)
    if document.session.arcgrav_version != 'current':
        blockers.append('version_mismatch')
    rule = REGISTRY.get(candidate.rule_id)
    if rule is None:
        return ('unknown_rule',)
    if not 0 <= candidate.node_id < len(tree.nodes):
        return ('missing_canonical_node',)
    node = tree.nodes[candidate.node_id]
    if not node.span.start <= candidate.span.start < candidate.span.end <= node.span.end:
        blockers.append('imprecise_range')
    if node.kind.startswith('markdown_fence_') and candidate.rule_id not in {END_SECTION_RULE, START_RULE_ID}:
        blockers.append('literal_source')
    # Opaque source is never silently promoted to an active language finding.
    if (node.kind in ('literal_content', 'unterminated_literal_content')
            and candidate.rule_id not in {'AG-LITERAL-FENCE-WIDTH', END_SECTION_RULE, START_RULE_ID}) or (candidate.rule_id not in {'AG-BACKTICK-WHITESPACE', QUOTED_RULE_ID, COLLISION_RULE_ID, END_SECTION_RULE, START_RULE_ID, *MEMBER_FINDING_MESSAGES} and any(
            span.start < candidate.span.end and candidate.span.start < span.end for span in node.quoted_spans)):
        blockers.append('literal_source')
    if rule.severity not in SEVERITY_ORDER:
        blockers.append('invalid_severity')
    for required in rule.required_evidence:
        if required not in candidate.evidence:
            blockers.append('missing_evidence:' + required)

    unit = _RULE_UNITS.get(candidate.rule_id)
    if unit is not None:
        blockers.extend(unit.verify(unit_context, candidate))
    else:
        raise RuntimeError('registered rule lacks its executable unit')

    for relationship in rule.required_relationships:
        if relationship not in candidate.evidence:
            blockers.append('untrusted_relationship:' + relationship)
    return tuple(blockers)


def evaluate_with_admission(document: ParsedDocument, tree: SyntaxTree, semantics: Semantics):
    """Detect through registered rules; independently verify admitted candidates."""
    if document.session.arcgrav_version != 'current':
        return (), ()
    candidates = []
    unit_context = RuleContext(document, tree, semantics)

    def propose(rule_id, proposal):
        candidates.append(Candidate(rule_id, proposal.span, proposal.node_id,
                                    proposal.message, proposal.evidence))

    for node in tree.nodes:
        if node.kind.startswith('markdown_fence_'):
            continue
        literal = 'literal' in node.kind
        for unit in _NODE_RULE_UNITS:
            if unit.literal_policy == 'only' and not literal:
                continue
            if unit.literal_policy == 'exclude' and literal:
                continue
            for proposal in unit.detect(unit_context, node):
                propose(unit.id, proposal)

    # Some document-wide families originally emitted in source/semantic order,
    # across multiple IDs. Preserve that order without coupling the runner to
    # any rule name: grouped units attach the original evidence sequence.
    pending_group = None
    pending = []
    for unit in _DOCUMENT_RULE_UNITS:
        if pending_group != unit.batch_group:
            for _, rule_id, proposal in sorted(pending, key=lambda row: row[0]):
                propose(rule_id, proposal)
            pending = []
            pending_group = unit.batch_group
        for proposal in unit.detect(unit_context, None):
            if unit.batch_group is None:
                propose(unit.id, proposal)
            else:
                if proposal.sequence is None:
                    raise ValueError(f"grouped rule proposal missing sequence: {unit.id}")
                pending.append((proposal.sequence, unit.id, proposal))
    for _, rule_id, proposal in sorted(pending, key=lambda row: row[0]):
        propose(rule_id, proposal)

    found, suppressed = [], []
    # Candidate proposals never authorize findings without independent rule checks.
    for candidate in candidates:
        blockers = admission(candidate, document, tree, semantics, _rule_context=unit_context)
        if blockers:
            suppressed.append((candidate.rule_id, str(candidate.node_id), blockers))
            continue
        r = REGISTRY[candidate.rule_id]
        span = candidate.span
        identity = sha256(f'{document.document_id}:{r.id}:{span.start}:{span.end}'.encode()).hexdigest()
        found.append(Finding(identity, r.id, r.severity, document.source_range(span),
            RuleEvidence(LANGUAGE_CONTRACT_VERSION, r.syntax_id, candidate.evidence, r.limits),
            candidate.evidence + (r.limits,), candidate.message))
    return tuple(sorted(found, key=lambda f: (f.source_range.span.start, f.source_range.span.end, f.rule_id))), tuple(suppressed)
