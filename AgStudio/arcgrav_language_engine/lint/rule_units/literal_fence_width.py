"""AG-LITERAL-FENCE-WIDTH: recursive nesting-width evidence and admission."""
import re
from ...recognition import SourceSpan
from ..syntax import _LINE_ENDINGS
from .contracts import RuleProposal, RuleUnit

RULE_ID = "AG-LITERAL-FENCE-WIDTH"


def spans(tree, source):
    """Recursively validate identified child pairs within canonical literals.

    Pair each inner opener with its next same-width fence inside its parent's
    boundary. A lone inner run contributes its width but cannot establish a
    child body. An explicit work stack avoids a Python recursion depth limit.
    Equal-width runs close the current parent; no sibling recovery is inferred.
    """
    result = {}
    opening = None
    fences = []

    def finish():
        following = {}
        next_equal = {}
        for index in range(len(fences) - 1, -1, -1):
            width = fences[index][2]
            next_equal[index] = following.get(width)
            following[width] = index
        pending = [(opening[0], opening[1].span, len(opening[1].text), 0, len(fences), None)]
        parents = []
        maxima = {}
        while pending:
            parent_id, parent_span, parent_width, index, stop, ancestor = pending.pop()
            parents.append((parent_id, parent_span, parent_width, ancestor))
            maxima[parent_id] = 0
            while index < stop:
                child_id, child_span, child_width = fences[index]
                maxima[parent_id] = max(maxima[parent_id], child_width)
                end = next_equal[index]
                if end is not None and end < stop:
                    pending.append((child_id, child_span, child_width, index + 1, end, parent_id))
                    index = end + 1
                else:
                    index += 1
        # Propagate descendant maxima upward in postorder, so every parent is
        # compared with all of its content without repeatedly rescanning it.
        for parent_id, parent_span, parent_width, ancestor in reversed(parents):
            if maxima[parent_id] >= parent_width:
                result[parent_id] = parent_span
            if ancestor is not None:
                maxima[ancestor] = max(maxima[ancestor], maxima[parent_id])

    for node in tree.nodes:
        if node.kind in ('literal_open', 'unterminated_literal_open'):
            token = next((t for t in node.tokens if t.kind == 'literal_open'), None)
            opening = (node.id, token) if token is not None else None
            fences = []
        elif node.kind == 'literal_close' and opening is not None:
            finish()
            opening = None
        elif opening is not None and node.kind in ('literal_content', 'unterminated_literal_content'):
            raw = node.span.extract(source).rstrip(_LINE_ENDINGS)
            text = raw.strip(' \t')
            if re.fullmatch(r'"{3,}', text):
                start = node.span.start + len(raw) - len(raw.lstrip(' \t'))
                fences.append((node.id, SourceSpan(start, start + len(text)), len(text)))
    if opening is not None:
        finish()
    return result



def detect(context, node):
    if node is not None:
        return
    widths = context.evidence(
        "literal_width", lambda: spans(context.tree, context.source))
    for node_id, span in widths.items():
        yield RuleProposal(span, node_id,
                           "Use matching parent fences strictly longer than every fence within their content; equal widths collide",
                           ("outer_inner_width",))


def verify(context, candidate):
    widths = context.evidence(
        "literal_width", lambda: spans(context.tree, context.source),
        verification=True)
    return (() if widths.get(candidate.node_id) == candidate.span
            else ("unsupported_literal_width",))


def build_rule(metadata):
    return RuleUnit(metadata, ("syntax", "literal_fences"), detect, verify, scope="document")
