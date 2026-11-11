"""Lossless, non-executing source recognition.

Standalone equal-width quote fences shield their contents, including unfinished
blocks through EOF. Section/list/operation prefixes and symbol/alias/binder
occurrences retain exact offsets. Noncanonical separators are explicit boundary
observations. Source recognition does not resolve identities or execute text;
parsing, semantic resolution and rule verification are separate derived stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata
from typing import Literal

from ..core import SourceSession
from ..syntax_contract import INDENT_WIDTH, syntax_id as _syntax_id, limitations as _limitations

ObservationKind = Literal[
    "unclassified",
    "markdown_fence_open",
    "markdown_fence_content",
    "markdown_fence_close",
    "section_header_candidate",
    "section_scalar_candidate",
    "section_boundary_candidate",
    "unordered_list_candidate",
    "ordered_list_candidate",
    "priority_list_candidate",
    "unordered_list_tab_boundary_candidate",
    "ordered_list_tab_boundary_candidate",
    "priority_list_tab_boundary_candidate",
    "unordered_list_unicode_boundary_candidate",
    "ordered_list_unicode_boundary_candidate",
    "priority_list_unicode_boundary_candidate",
    "operation_candidate",
    "operation_boundary_candidate",
    "literal_open",
    "literal_content",
    "literal_close",
    "unterminated_literal_open",
    "unterminated_literal_content",
]
OccurrenceKind = Literal[
    "block_binding_candidate", "block_binding_tab_boundary_candidate",
    "block_binding_unicode_boundary_candidate",
    "wildcard_candidate", "indentation_candidate",
    "indentation_boundary_candidate", "indentation_tab_boundary_candidate", "indentation_unicode_boundary_candidate",
    "symbol_candidate", "symbol_boundary_candidate", "alias_marker_candidate",
    "backticked_reference_candidate",
]
_LITERAL_KINDS = frozenset((
    "literal_open", "literal_content", "literal_close",
    "unterminated_literal_open", "unterminated_literal_content",
))
_MARKDOWN_KINDS = frozenset(("markdown_fence_open", "markdown_fence_content", "markdown_fence_close"))
_MARKDOWN_FENCE = re.compile(r"^(?:`{3,}|~{3,})")
_SECTION_KINDS = frozenset(("section_header_candidate", "section_scalar_candidate",
                            "section_boundary_candidate"))
_LIST_KINDS = frozenset(
    family + suffix for family in ('unordered_list', 'ordered_list', 'priority_list')
    for suffix in ('_candidate', '_tab_boundary_candidate', '_unicode_boundary_candidate')
)
_OPERATION_KINDS = frozenset(("operation_candidate", "operation_boundary_candidate"))
# Only whitespace immediately outside the standalone quote delimiters is
# tolerated. A run of at least three quotes opens; only the same run closes.
# Different-width runs are opaque content, not recursively active delimiters.
_LINE_BOUNDARY = " \t\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029"
# Backtick observations are isolated single-line pairs. Escapes, adjacent
# delimiters, whitespace and overlapping markers do not enter this overlay;
# the parser handles supported member names independently.
_REFERENCE_TOKEN = re.compile(r"(?<![\x60\\])\x60([^\x60\\\[\]*\r\n]+)\x60(?!\x60)")
# A terminal, unescaped `[Name` shape remains an unresolved source fragment,
# not a malformedness judgment or an admitted symbol-name grammar.
_UNFINISHED_SYMBOL_TOKEN = re.compile(r"(?<![\[\\])\[([^\[\]\s]+)$")


# Match the three canonical marker families only when an immediate ASCII
# horizontal separator follows. Tab-first cases are boundary candidates, not
# admitted list syntax; unsupported punctuation and indentation stay deferred.
_LIST_MARKER = re.compile(r"(-|[0-9]+\.|P[0-9]+\.)([ \t]+)")
_LIST_MARKER_PREFIX = re.compile(r"(-|[0-9]+\.|P[0-9]+\.)")


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Half-open Python-string offsets into original source text.

    This local lossless-partition offset is not a competing Stage 02 shared
    source-coordinate contract; that contract remains to be established.
    """

    start: int
    end: int

    def __post_init__(self) -> None:
        if (type(self.start) is not int or type(self.end) is not int):
            raise TypeError("source offsets must be integer character positions")
        if self.start < 0 or self.end < self.start:
            raise ValueError("source span must be nonnegative and ordered")

    def extract(self, source: str) -> str:
        """Return original text, without normalization or reconstruction."""
        return source[self.start:self.end]


@dataclass(frozen=True, slots=True)
class SourceRegion:
    """One contiguous, exactly retained source slice; no validity claim."""

    span: SourceSpan
    text: str
    disposition: Literal["unclassified"] = field(default="unclassified", init=False)


@dataclass(frozen=True, slots=True)
class SourceObservation:
    """One region-aligned fact, distinct from the authoritative text slice.

    Literal kinds mark matched delimiter candidates or shielded content.
    Section, list, and operation observations do not by themselves establish a
    complete grammar, binding interpretation, or validity decision. An unclosed
    literal candidate shields the remaining source instead of parsing structure.
    """

    span: SourceSpan
    kind: ObservationKind
    claim_class: Literal["recognition"] = field(default="recognition", init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.span, SourceSpan):
            raise TypeError("observation requires an original source span")
        if self.kind not in _LITERAL_KINDS | _SECTION_KINDS | _LIST_KINDS | _OPERATION_KINDS | _MARKDOWN_KINDS | {"unclassified"}:
            raise ValueError("unsupported observation kind")

    @property
    def syntax_id(self) -> str | None:
        return _syntax_id(self.kind)

    @property
    def limitations(self) -> tuple[str, ...]:
        return _limitations(self.kind)


@dataclass(frozen=True, slots=True)
class SourceOccurrence:
    """Exact source subspan, not nesting, binding, expansion, or conformance.

    Trailing binders, wildcard glyphs, bracketed symbol tokens, unfinished
    terminal bracket fragments, narrow inline alias markers, isolated backticked references and complete leading
    ASCII-space or Unicode-space prefix candidates occupy this overlay, leaving line observations
    intact. An alias marker stops before
    its independently observed bracket token, so source spans do not overlap.
    No symbol definition, invocation, alias binding, target resolution, malformedness,
    grouping, parenthood, tab/Unicode spacing width, reference-target resolution, or wildcard grammar
    is established. Backticked references do not identify a target during this
    stage. Each occurrence reports its syntax family and concrete limitations.
    """

    span: SourceSpan
    kind: OccurrenceKind
    claim_class: Literal["recognition"] = field(default="recognition", init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.span, SourceSpan):
            raise TypeError("occurrence requires an original source span")
        if self.kind not in (
            "block_binding_candidate", "block_binding_tab_boundary_candidate",
            "block_binding_unicode_boundary_candidate",
            "wildcard_candidate", "indentation_candidate",
            "indentation_boundary_candidate", "indentation_tab_boundary_candidate", "indentation_unicode_boundary_candidate",
            "symbol_candidate", "symbol_boundary_candidate", "alias_marker_candidate",
            "backticked_reference_candidate",
        ):
            raise ValueError("unsupported occurrence kind")

    @property
    def syntax_id(self) -> str | None:
        return _syntax_id(self.kind)

    @property
    def limitations(self) -> tuple[str, ...]:
        return _limitations(self.kind)


@dataclass(frozen=True, slots=True)
class SourceRecovery:
    """A bounded, untrusted candidate; never an ArcGrav invalidity verdict.

    ``resume_at`` is the first position at which independent recognition may
    continue. Unfinished symbol fragments and bare operation arrows are local
    to their physical lines; an unmatched literal shields to EOF. The
    exact source remains in regions regardless of this additional metadata.
    """

    span: SourceSpan
    resume_at: int
    kind: Literal["unfinished_symbol", "unfinished_operation", "unterminated_literal"]
    trust: Literal["untrusted"] = field(default="untrusted", init=False)
    claim_class: Literal["recognition"] = field(default="recognition", init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.span, SourceSpan):
            raise TypeError("recovery requires an original source span")
        if type(self.resume_at) is not int or self.resume_at < self.span.end:
            raise ValueError("recovery must resume after its source candidate")
        if self.kind not in ("unfinished_symbol", "unfinished_operation", "unterminated_literal"):
            raise ValueError("unsupported recovery kind")

    @property
    def limitations(self) -> tuple[str, ...]:
        return (self.kind,)


@dataclass(frozen=True, slots=True)
class RecognitionResult:
    """Immutable exact partition with observations, occurrences and recovery."""

    session: SourceSession
    regions: tuple[SourceRegion, ...]
    observations: tuple[SourceObservation, ...] = ()
    occurrences: tuple[SourceOccurrence, ...] = ()
    recoveries: tuple[SourceRecovery, ...] = ()
    claim_class: Literal["recognition"] = field(default="recognition", init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.session, SourceSession):
            raise TypeError("recognition requires a SourceSession")
        cursor = 0
        for region in self.regions:
            if not isinstance(region, SourceRegion):
                raise TypeError("regions must be source regions")
            if (region.span.start != cursor
                    or region.span.end != cursor + len(region.text)
                    or region.span.extract(self.session.source) != region.text):
                raise ValueError("regions must cover the exact source contiguously")
            cursor = region.span.end
        if cursor != len(self.session.source):
            raise ValueError("regions must retain the complete original source")
        if len(self.observations) != len(self.regions):
            raise ValueError("every region requires an observation")
        for region, observation in zip(self.regions, self.observations):
            if not isinstance(observation, SourceObservation):
                raise TypeError("observations must be source observations")
            if observation.span != region.span:
                raise ValueError("observations must align with original source regions")
        literal_state: Literal["paired", "unclosed"] | None = None
        literal_marker: str | None = None
        for region, observation in zip(self.regions, self.observations):
            kind = observation.kind
            marker = _standalone_literal_delimiter(region.text)
            if kind in ("literal_open", "unterminated_literal_open"):
                if literal_state is not None or marker is None:
                    raise ValueError("literal opener must be a standalone source delimiter")
                literal_state = "paired" if kind == "literal_open" else "unclosed"
                literal_marker = marker
            elif kind in ("literal_content", "unterminated_literal_content"):
                expected = ("literal_content" if literal_state == "paired"
                            else "unterminated_literal_content")
                if literal_state is None or kind != expected or marker == literal_marker:
                    raise ValueError("literal content must stay within its matching shield")
            elif kind == "literal_close":
                if literal_state != "paired" or marker != literal_marker:
                    raise ValueError("literal closer must match its opener")
                literal_state = None
                literal_marker = None
            elif literal_state is not None:
                raise ValueError("active literal cannot contain nonliteral observations")
        if literal_state == "paired":
            raise ValueError("paired literal must have a closing delimiter")
        last_end = 0
        region_index = 0
        symbol_spans_by_region: dict[int, frozenset[SourceSpan]] = {}
        reference_spans_by_region: dict[int, frozenset[SourceSpan]] = {}
        for occurrence in self.occurrences:
            if not isinstance(occurrence, SourceOccurrence):
                raise TypeError("occurrences must be source occurrences")
            if occurrence.span.start < last_end:
                raise ValueError("occurrences must be ordered without overlap")
            while (region_index < len(self.regions)
                   and self.regions[region_index].span.end <= occurrence.span.start):
                region_index += 1
            if region_index >= len(self.regions):
                raise ValueError("occurrence must be contained in a source region")
            region = self.regions[region_index]
            if self.observations[region_index].kind in _LITERAL_KINDS | _MARKDOWN_KINDS:
                raise ValueError("occurrence cannot escape literal shielding")
            if occurrence.span.end > region.span.end:
                raise ValueError("occurrence must stay within one source region")
            if occurrence.kind in ("block_binding_candidate", "block_binding_tab_boundary_candidate",
                                   "block_binding_unicode_boundary_candidate"):
                if (occurrence.span, occurrence.kind) != _block_binding_marker_fact(region):
                    raise ValueError("occurrence must match an exact trailing marker")
            elif occurrence.kind in (
                "indentation_candidate", "indentation_boundary_candidate",
                "indentation_tab_boundary_candidate", "indentation_unicode_boundary_candidate",
            ):
                if (occurrence.span, occurrence.kind) != _indentation_prefix_fact(region):
                    raise ValueError("indentation must match the exact original prefix and boundary kind")
            elif occurrence.kind == "symbol_candidate":
                if region_index not in symbol_spans_by_region:
                    symbol_spans_by_region[region_index] = frozenset(
                        _symbol_token_spans(region)
                    )
                if occurrence.span not in symbol_spans_by_region[region_index]:
                    raise ValueError("symbol must match an exact original bracket token")
            elif occurrence.kind == "symbol_boundary_candidate":
                if occurrence.span != _unfinished_symbol_span(region):
                    raise ValueError("unfinished symbol must match exact terminal source fragment")
            elif occurrence.kind == "alias_marker_candidate":
                if occurrence.span != _alias_marker_span(region):
                    raise ValueError("alias marker must match exact original AS prefix")
            elif occurrence.kind == "backticked_reference_candidate":
                if region_index not in reference_spans_by_region:
                    reference_spans_by_region[region_index] = frozenset(
                        _backticked_reference_spans(region)
                    )
                if occurrence.span not in reference_spans_by_region[region_index]:
                    raise ValueError("reference must match an exact isolated backtick pair")
            elif (occurrence.span.end != occurrence.span.start + 1
                  or occurrence.span.extract(self.session.source) != "*"):
                raise ValueError("wildcard occurrence must match one original * glyph")
            last_end = occurrence.span.end

        unfinished = {occurrence.span for occurrence in self.occurrences
                      if occurrence.kind == "symbol_boundary_candidate"}
        unclosed = next((index for index, observation in enumerate(self.observations)
                         if observation.kind == "unterminated_literal_open"), None)
        expected_literal_span = (SourceSpan(self.regions[unclosed].span.start,
                                            len(self.source))
                                 if unclosed is not None else None)
        last_start = -1
        recovery_region_index = 0
        for recovery in self.recoveries:
            if not isinstance(recovery, SourceRecovery):
                raise TypeError("recoveries must be source recoveries")
            if recovery.span.start <= last_start or recovery.resume_at > len(self.source):
                raise ValueError("recoveries must be ordered, bounded and unique")
            last_start = recovery.span.start
            if recovery.kind == "unterminated_literal":
                if (recovery.span != expected_literal_span
                        or recovery.resume_at != len(self.source)):
                    raise ValueError("literal recovery must shield to end of source")
            else:
                while (recovery_region_index < len(self.regions)
                       and self.regions[recovery_region_index].span.end
                       <= recovery.span.start):
                    recovery_region_index += 1
                region = (self.regions[recovery_region_index]
                          if recovery_region_index < len(self.regions) else None)
                if region is None or recovery.resume_at != region.span.end:
                    raise ValueError("candidate recovery must resume after its line")
                if recovery.kind == "unfinished_symbol":
                    if (recovery.span not in unfinished
                            or recovery.span.start < region.span.start
                            or recovery.span.end > region.span.end):
                        raise ValueError("symbol recovery must match its source fragment")
                elif (recovery.span != _unfinished_operation_span(region)
                      or self.observations[recovery_region_index].kind
                      != "operation_boundary_candidate"):
                    raise ValueError("operation recovery must match a bare arrow")
        expected_recoveries: list[SourceRecovery] = []
        recovery_region_cursor = 0
        for occurrence in self.occurrences:
            if occurrence.kind != "symbol_boundary_candidate":
                continue
            while (recovery_region_cursor < len(self.regions)
                   and self.regions[recovery_region_cursor].span.end
                   <= occurrence.span.start):
                recovery_region_cursor += 1
            region = self.regions[recovery_region_cursor]
            expected_recoveries.append(SourceRecovery(
                occurrence.span, region.span.end, "unfinished_symbol"
            ))
        if expected_literal_span is not None:
            expected_recoveries.append(SourceRecovery(
                expected_literal_span, len(self.source), "unterminated_literal"
            ))
        for region, observation in zip(self.regions, self.observations):
            if observation.kind in _LITERAL_KINDS:
                continue
            operation_span = _unfinished_operation_span(region)
            if operation_span is not None:
                expected_recoveries.append(SourceRecovery(
                    operation_span, region.span.end, "unfinished_operation"
                ))
        expected_recoveries.sort(key=lambda recovery: recovery.span.start)
        if self.recoveries != tuple(expected_recoveries):
            raise ValueError("recoveries must exactly match untrusted source candidates")

    @property
    def source(self) -> str:
        """Original authoritative text, including its exact line terminators."""
        return self.session.source

    def round_trip(self) -> str:
        """Reassemble regions solely to verify the lossless partition."""
        return "".join(region.text for region in self.regions)


def _standalone_literal_delimiter(text: str) -> str | None:
    """Identify standalone runs of at least three double quotes."""
    marker = text.strip(_LINE_BOUNDARY)
    return marker if len(marker) >= 3 and set(marker) == {'"'} else None


def _section_candidate_kind(text: str) -> ObservationKind | None:
    """Observe compact section labels and explicit noncanonical colon boundaries.

    All such lines are source-shape candidates tied to the section gap, not
    ArcGrav header/scalar grammar, binding, or version-specific conformance.
    Adjacent value/doubled-colon, whitespace-before-colon, tab-bearing
    post-colon, exactly two identifier-like label parts separated by one
    internal ASCII tab, two, three or four adjacent ASCII tabs, one non-ASCII Unicode Zs
    separator or two repeated identical non-ASCII Unicode Zs separators (bare
    or single-bracket-wrapped for those separator cases), Unicode post-colon
    space-separator and tab-/Unicode-Zs-bearing leading horizontal-prefix
    shapes stay distinct from illustrated
    headers/scalars. URI/path-led punctuation, ASCII-space multiword labels,
    and other unsupported labels remain deferred.
    """
    content = text.rstrip("\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029")
    # Leading tabs or non-ASCII category Zs separators (including mixtures
    # with ASCII horizontal spacing) are not canonical section indentation.
    # Observe a compact label/suffix only as a bounded ambiguity, alongside
    # the independent exact grouping-prefix fact. Other Unicode whitespace
    # stays deferred; no tab/Unicode width or grouping is inferred.
    prefix_end = 0
    unicode_leading = False
    for char in content:
        if char in " \t":
            prefix_end += 1
        elif unicodedata.category(char) == "Zs":
            unicode_leading = True
            prefix_end += 1
        else:
            break
    leading_prefix = content[:prefix_end]
    tabbed_leading = "\t" in leading_prefix
    label, colon, suffix = content[prefix_end:].partition(":")
    if not colon:
        return None
    # A supported section label touches its colon: Key:, not Key : or [Key]\t:.
    # Retain the latter only as boundary ambiguity, never as a header or
    # scalar. ASCII-space multiword labels remain deferred.
    # Unicode category Zs immediately before ':' is a bounded ambiguity, not
    # evidence of accepted spacing. Other internal label separators (apart
    # from the narrow two-part single-tab/single-Zs boundaries below) and
    # leading non-Zs Unicode whitespace stay deferred.
    candidate_end = len(label)
    while candidate_end and (
        label[candidate_end - 1] in " \t"
        or unicodedata.category(label[candidate_end - 1]) == "Zs"
    ):
        candidate_end -= 1
    spaced_colon = candidate_end < len(label)
    candidate_label = label[:candidate_end]
    bare = candidate_label.isidentifier()
    bracketed = (
        len(candidate_label) > 2 and candidate_label.startswith("[")
        and candidate_label.endswith("]")
        and candidate_label[1:-1].isidentifier()
    )
    # A single internal tab between exactly two compact label words, bare
    # or enclosed by one bracket pair, remains a section-bounded lexical
    # ambiguity. No bracketed multiword grammar or symbol role is admitted.
    # ASCII-space prose, multi-part/mixed separators and pre-colon spacing
    # stay deferred.
    internal_tab_label = candidate_label
    if (len(candidate_label) > 2 and candidate_label.startswith("[")
            and candidate_label.endswith("]")):
        internal_tab_label = candidate_label[1:-1]
    internal_tab_boundary = (
        not spaced_colon and internal_tab_label.count("\t") == 1
        and " " not in internal_tab_label
        and all(part.isidentifier() for part in internal_tab_label.split("\t"))
    )
    # A second deliberately bounded internal-tab ambiguity: exactly two or
    # three or four adjacent ASCII tabs between two compact identifier-like parts, bare
    # or enclosed by one bracket pair. The observed run must contain every tab
    # in the label. This is section-bounded, not repeated-tab grammar; longer
    # runs of five or more tabs, mixed separators and multi-part labels remain deferred.
    internal_tab_run_length = internal_tab_label.count("\t")
    repeated_internal_tab_boundary = (
        not spaced_colon and internal_tab_run_length in (2, 3, 4)
        and "\t" * internal_tab_run_length in internal_tab_label
        and " " not in internal_tab_label
        and all(part.isidentifier() for part in internal_tab_label.split(
            "\t" * internal_tab_run_length))
    )
    # A bounded non-ASCII Unicode Zs separator ambiguity: either one separator
    # or exactly two adjacent repeated identical separators between two compact
    # identifier-like parts, bare or enclosed by one bracket pair. ASCII-space
    # prose, mixed ASCII/Unicode separators, mixed Unicode-Zs runs, longer
    # repeated runs, multi-part labels and pre-colon spacing stay deferred.
    # This is not a bracketed multi-part label grammar or symbol interpretation.
    internal_zs_label = candidate_label
    if (len(candidate_label) > 2 and candidate_label.startswith("[")
            and candidate_label.endswith("]")):
        internal_zs_label = candidate_label[1:-1]
    internal_zs_runs: list[tuple[int, int, str]] = []
    internal_zs_index = 0
    while internal_zs_index < len(internal_zs_label):
        char = internal_zs_label[internal_zs_index]
        if char != " " and unicodedata.category(char) == "Zs":
            run_start = internal_zs_index
            while (internal_zs_index < len(internal_zs_label)
                   and internal_zs_label[internal_zs_index] == char):
                internal_zs_index += 1
            internal_zs_runs.append((run_start, internal_zs_index, char))
            continue
        internal_zs_index += 1
    if internal_zs_runs:
        zs_start, zs_end, _ = internal_zs_runs[0]
    else:
        zs_start = zs_end = -1
    internal_unicode_zs_boundary = (
        not spaced_colon and "\t" not in internal_zs_label
        and " " not in internal_zs_label and len(internal_zs_runs) == 1
        and zs_end - zs_start in (1, 2)
        and internal_zs_label[:zs_start].isidentifier()
        and internal_zs_label[zs_end:].isidentifier()
    )
    if not (bare or bracketed or internal_tab_boundary
            or repeated_internal_tab_boundary or internal_unicode_zs_boundary):
        return None
    unicode_suffix = bool(suffix) and unicodedata.category(suffix[0]) == "Zs"
    plausible_suffix = (
        not suffix.strip(" \t")
        or suffix.startswith((" ", "\t"))
        or unicode_suffix
        or bool(suffix and (suffix[0].isidentifier()
                            or suffix[0].isdigit() or suffix[0] == ":"))
    )
    if (tabbed_leading or unicode_leading or spaced_colon
            or internal_tab_boundary or repeated_internal_tab_boundary
            or internal_unicode_zs_boundary):
        return "section_boundary_candidate" if plausible_suffix else None
    # Supported section scalars use ASCII-space separators, not tab-separated
    # forms. Preserve a tab anywhere in the immediate post-colon horizontal
    # run as a section boundary, including otherwise blank suffixes. A
    # later tab inside the value does not change a canonical scalar.
    post_colon_horizontal = suffix[:len(suffix) - len(suffix.lstrip(" \t"))]
    if "\t" in post_colon_horizontal:
        return "section_boundary_candidate"
    if not suffix.strip(" \t"):
        return "section_header_candidate"
    if suffix.startswith(" "):
        return "section_scalar_candidate"
    # A non-ASCII Unicode space separator directly after the colon is not
    # the canonical ASCII-space scalar. Preserve this ambiguous source
    # shape as a section boundary rather than normalizing the whitespace; it is never a header/scalar or a validity judgment.
    if unicode_suffix:
        return "section_boundary_candidate"
    # Key:Value and Key:: are noncanonical adjacent-colon forms.
    # Keep them as boundary observations rather than header/scalar nodes; punctuation-led
    # URI/path suffixes remain unclassified source.
    return "section_boundary_candidate" if plausible_suffix else None


def _list_candidate_kind(text: str) -> ObservationKind | None:
    """Observe canonical list prefixes and first-separator ambiguities.

    ASCII-space-separated dash, numeric-dot and priority-dot prefixes keep
    their existing candidate kinds. A separator beginning with a tab after
    any of those shapes is separately bounded, including repeated tabs and
    mixed horizontal runs. A non-ASCII Unicode Zs immediately after a marker
    is a separate bounded boundary. Tab indentation and unsupported markers stay deferred.
    These observations establish neither list membership, numeric grammar,
    item validity nor ArcGrav conformance.
    """
    line = text.lstrip(" ")
    match = _LIST_MARKER.match(line)
    if match is None:
        prefix = _LIST_MARKER_PREFIX.match(line)
        if prefix is None or len(line) == prefix.end():
            return None
        if unicodedata.category(line[prefix.end()]) != "Zs":
            return None
        marker = prefix.group(1)
        if marker == "-":
            return "unordered_list_unicode_boundary_candidate"
        if marker.startswith("P"):
            return "priority_list_unicode_boundary_candidate"
        return "ordered_list_unicode_boundary_candidate"
    marker, separator = match.groups()
    tab_boundary = separator.startswith("\t")
    if marker == "-":
        return ("unordered_list_tab_boundary_candidate" if tab_boundary
                else "unordered_list_candidate")
    if marker.startswith("P"):
        return ("priority_list_tab_boundary_candidate" if tab_boundary
                else "priority_list_candidate")
    return ("ordered_list_tab_boundary_candidate" if tab_boundary
            else "ordered_list_candidate")


def _operation_candidate_kind(text: str) -> ObservationKind | None:
    """Observe line-initial arrows with distinct space and bounded separators.

    The whole line remains a candidate. This neither parses a transformation
    nor establishes arrow placement, argument syntax, child binding or
    applicability for an ArcGrav version. A tab or non-ASCII Unicode Zs
    immediately after the arrow remains an operation-gap boundary, not an accepted form.
    A bare arrow is retained as a separate line-local recovery candidate.
    Other arrow forms are deferred.
    """
    line = text.lstrip(" ")
    if line.startswith("=> "):
        return "operation_candidate"
    if line.startswith("=>\t"):
        return "operation_boundary_candidate"
    if len(line) > 2 and line.startswith("=>") and unicodedata.category(line[2]) == "Zs":
        return "operation_boundary_candidate"
    if line.rstrip("\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029") == "=>":
        return "operation_boundary_candidate"
    return None


def _unfinished_operation_span(region: SourceRegion) -> SourceSpan | None:
    """Locate only a bare line-initial arrow, without a validity judgment."""
    content = region.text.rstrip("\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029")
    prefix_length = len(content) - len(content.lstrip(" "))
    if content[prefix_length:] != "=>":
        return None
    start = region.span.start + prefix_length
    return SourceSpan(start, start + 2)


def _symbol_token_spans(region: SourceRegion):
    """Observe matched PascalCase groups without leaking nested or quoted tokens."""
    from ..symbol_syntax import bracket_groups, scalar_shields
    opaque = tuple((s.start, s.end) for s in scalar_shields(region.text, 0))
    for start, end, kind in bracket_groups(region.text, opaque):
        if kind == 'symbol':
            yield SourceSpan(region.span.start + start, region.span.start + end)



def _unfinished_symbol_span(region: SourceRegion) -> SourceSpan | None:
    """Observe only an unescaped terminal `[Identifier` as a bounded fragment.

    Ignore nested/unclosed earlier openers, whitespace-bearing names, escapes,
    and arbitrary bracket damage. This is not a diagnosis, accepted name rule,
    recovery threshold, or resolved reference. The original line is unchanged.
    """
    content = region.text.rstrip("\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029").rstrip(" \t")
    match = _UNFINISHED_SYMBOL_TOKEN.search(content)
    if match is None or not match.group(1).isidentifier():
        return None
    prefix = content[:match.start()]
    if prefix.count("[") != prefix.count("]"):
        return None
    return SourceSpan(region.span.start + match.start(),
                      region.span.start + match.end())


def _backticked_reference_spans(region: SourceRegion):
    """Observe only isolated canonical exact-name wrappers as source facts.

    This overlay does not parse member access or resolve the wrapped name; escapes, runs of backticks,
    whitespace-containing and marker-overlapping pairs are deferred rather
    than classified as invalid. No target or missing-backtick claim is made.
    """
    for match in _REFERENCE_TOKEN.finditer(region.text):
        content = match.group(1)
        if not content or any(char.isspace() for char in content):
            continue
        yield SourceSpan(
            region.span.start + match.start(),
            region.span.start + match.end(),
        )


def _alias_marker_span(region: SourceRegion) -> SourceSpan | None:
    """Observe only the canonical terminal ' AS [Alias]' source suffix.

    The exact 'AS ' subspan precedes an independently observed compact bracket
    token, avoiding overlapping occurrences. This does not establish the
    unresolved alias lexical grammar, which context is bound, or validity.
    A separately observed trailing space- or tab-delimited binder may follow
    the alias. The independent source facts imply no binding relationship.
    Broader spacing and name boundaries stay deferred.
    """
    content = region.text.rstrip("\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029").rstrip(" \t")
    if _block_binding_marker_fact(region) is not None:
        content = content[:-2].rstrip(" \t")
    prefix, separator, tail = content.rpartition(" AS ")
    if not separator or not prefix or prefix[-1] in " \t":
        return None
    if not (len(tail) > 2 and tail.startswith("[") and tail.endswith("]")
            and tail[1:-1].isidentifier()):
        return None
    marker_start = region.span.start + len(prefix) + 1
    return SourceSpan(marker_start, marker_start + 3)


def _block_binding_marker_fact(
    region: SourceRegion,
) -> tuple[SourceSpan, Literal[
    "block_binding_candidate", "block_binding_tab_boundary_candidate",
    "block_binding_unicode_boundary_candidate",
]] | None:
    """Locate a trailing visible binder and retain its immediate separator.

    Horizontal whitespace after the marker is retained by the region. A
    candidate alone implies neither valid placement nor actual block binding.
    A tab or non-ASCII Unicode Zs immediately before the arrow remains a
    separate boundary observation. Other shapes are not recognized as binders.
    """
    content = region.text.rstrip("\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029").rstrip(" \t")
    if (len(content) < 3 or content[-1] != "↳"
            or not (content[-2] in " \t" or unicodedata.category(content[-2]) == "Zs")
            or not any(char not in " \t" and unicodedata.category(char) != "Zs"
                       for char in content[:-2])):
        return None
    start = region.span.start + len(content) - 2
    if content[-2] == "\t":
        kind = "block_binding_tab_boundary_candidate"
    elif content[-2] == " ":
        kind = "block_binding_candidate"
    else:
        kind = "block_binding_unicode_boundary_candidate"
    return SourceSpan(start, start + 2), kind


def _indentation_prefix_fact(
    region: SourceRegion,
) -> tuple[
    SourceSpan,
    Literal[
        "indentation_candidate", "indentation_boundary_candidate",
        "indentation_tab_boundary_candidate", "indentation_unicode_boundary_candidate",
    ],
] | None:
    """Retain bounded leading horizontal spacing as bounded source shape.

    Even-width ASCII-space runs and odd/tab-bearing boundary shapes
    remain distinct. A complete prefix containing non-ASCII Unicode category
    Zs separators is a separate uncertain boundary fact, even when mixed with
    ASCII spaces or tabs. Whitespace-only lines and other Unicode whitespace
    remain deferred. No width, hierarchy, malformedness or conformance follows.
    """
    content = region.text.rstrip("\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029")
    count = 0
    has_unicode_separator = False
    for char in content:
        if char in " \t":
            count += 1
        elif unicodedata.category(char) == "Zs":
            has_unicode_separator = True
            count += 1
        else:
            break
    if not count or count == len(content):
        return None
    prefix = content[:count]
    span = SourceSpan(region.span.start, region.span.start + count)
    if has_unicode_separator:
        return span, "indentation_unicode_boundary_candidate"
    if "\t" in prefix:
        return span, "indentation_tab_boundary_candidate"
    kind = "indentation_candidate" if count % INDENT_WIDTH == 0 else "indentation_boundary_candidate"
    return span, kind


def recognize_source(session: SourceSession) -> RecognitionResult:
    """Partition exact source; shield standalone literals before other candidates.

    Physical slices and positions never change. Paired matching-width quote
    candidates shield their contents, including markers of a different width;
    unmatched openers shield to EOF. Narrow, non-normative section candidate
    and canonical-marker list candidate observations are then attached only to
    still-unclassified regions. No general grammar, target resolution, external action, or conformance claim
    is attempted.
    """
    if not isinstance(session, SourceSession):
        raise TypeError("recognition requires a SourceSession")
    cursor = 0
    regions: list[SourceRegion] = []
    for text in session.source.splitlines(keepends=True):
        end = cursor + len(text)
        regions.append(SourceRegion(SourceSpan(cursor, end), text))
        cursor = end

    observations = [
        SourceObservation(region.span, "unclassified") for region in regions
    ]
    recoveries: list[SourceRecovery] = []
    index = 0
    while index < len(regions):
        # Markdown examples are source values too. Detect them in source order
        # so quotes inside Markdown cannot start an ArcGrav literal (and vice
        # versa). Keep their established same-character, at-least-width close
        # convention separate from exact-width double-quote delimiters.
        markdown = _MARKDOWN_FENCE.match(regions[index].text.lstrip(' \t'))
        if markdown is not None:
            marker = markdown.group()
            observations[index] = SourceObservation(regions[index].span, "markdown_fence_open")
            index += 1
            while index < len(regions):
                closing = _MARKDOWN_FENCE.match(regions[index].text.lstrip(' \t'))
                paired = (closing is not None and closing.group()[0] == marker[0]
                          and len(closing.group()) >= len(marker))
                observations[index] = SourceObservation(
                    regions[index].span, "markdown_fence_close" if paired else "markdown_fence_content")
                index += 1
                if paired:
                    break
            continue
        delimiter = _standalone_literal_delimiter(regions[index].text)
        if delimiter is None:
            index += 1
            continue

        closing = index + 1
        while closing < len(regions):
            if _standalone_literal_delimiter(regions[closing].text) == delimiter:
                break
            closing += 1
        paired = closing < len(regions)
        if not paired:
            recoveries.append(SourceRecovery(
                SourceSpan(regions[index].span.start, len(session.source)),
                len(session.source), "unterminated_literal",
            ))
        observations[index] = SourceObservation(
            regions[index].span,
            "literal_open" if paired else "unterminated_literal_open",
        )
        for body_index in range(index + 1, closing):
            observations[body_index] = SourceObservation(
                regions[body_index].span,
                "literal_content" if paired else "unterminated_literal_content",
            )
        if paired:
            observations[closing] = SourceObservation(
                regions[closing].span, "literal_close"
            )
        index = closing + 1

    # Section/list/operation observations cannot leak through paired or unmatched
    # literals. Each candidate retains its whole line and concrete boundary
    # conditions, without claiming transformation, binding, or validity.
    for region_index, observation in enumerate(observations):
        if observation.kind != "unclassified":
            continue
        kind = _section_candidate_kind(regions[region_index].text)
        if kind is None:
            kind = _list_candidate_kind(regions[region_index].text)
        if kind is None:
            kind = _operation_candidate_kind(regions[region_index].text)
        if kind is not None:
            observations[region_index] = SourceObservation(
                regions[region_index].span, kind
            )

    for region, observation in zip(regions, observations):
        if observation.kind != "operation_boundary_candidate":
            continue
        operation_span = _unfinished_operation_span(region)
        if operation_span is not None:
            recoveries.append(SourceRecovery(
                operation_span, region.span.end, "unfinished_operation"
            ))

    # Independent exact occurrences retain original order across marker families.
    # Neither paired nor unclosed standalone literals leak occurrences.
    occurrences: list[SourceOccurrence] = []
    for region, observation in zip(regions, observations):
        if observation.kind in _LITERAL_KINDS | _MARKDOWN_KINDS:
            continue
        region_occurrences: list[SourceOccurrence] = []
        indentation = _indentation_prefix_fact(region)
        if indentation is not None:
            span, kind = indentation
            region_occurrences.append(SourceOccurrence(span, kind))
        for offset, char in enumerate(region.text):
            if char == "*":
                start = region.span.start + offset
                region_occurrences.append(SourceOccurrence(
                    SourceSpan(start, start + 1), "wildcard_candidate"
                ))
        region_occurrences.extend(
            SourceOccurrence(span, "symbol_candidate")
            for span in _symbol_token_spans(region)
        )
        unfinished_symbol = _unfinished_symbol_span(region)
        if unfinished_symbol is not None:
            region_occurrences.append(SourceOccurrence(
                unfinished_symbol, "symbol_boundary_candidate"
            ))
            recoveries.append(SourceRecovery(
                unfinished_symbol, region.span.end, "unfinished_symbol"
            ))
        region_occurrences.extend(
            SourceOccurrence(span, "backticked_reference_candidate")
            for span in _backticked_reference_spans(region)
        )
        alias = _alias_marker_span(region)
        if alias is not None:
            region_occurrences.append(SourceOccurrence(alias, "alias_marker_candidate"))
        binding = _block_binding_marker_fact(region)
        if binding is not None:
            span, kind = binding
            region_occurrences.append(SourceOccurrence(span, kind))
        occurrences.extend(sorted(region_occurrences, key=lambda item: item.span.start))

    return RecognitionResult(
        session, tuple(regions), tuple(observations), tuple(occurrences),
        tuple(sorted(recoveries, key=lambda item: item.span.start)),
    )
