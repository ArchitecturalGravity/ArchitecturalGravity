"""One independent rule per backticked-member finding family."""
from ..members import MEMBER_FINDING_MESSAGES, member_finding_spans
from .contracts import RuleProposal, RuleUnit

RULE_IDS = tuple(MEMBER_FINDING_MESSAGES)


def _proposals(context):
    if context.semantics is None:
        return ()
    return tuple(sorted(member_finding_spans(context.semantics.members),
                        key=lambda row: (row[1], row[2].start, row[0])))


def _independent(context):
    from .. import rules
    if context.semantics is None:
        return frozenset()
    return rules.member_finding_spans(
        rules.resolve_members(context.tree, context.semantics, context.source))


def build_rule(metadata):
    rule_id = metadata.id
    if rule_id not in MEMBER_FINDING_MESSAGES:
        raise ValueError(rule_id)

    def detect(context, node):
        if node is not None:
            return
        proposals = context.evidence("member_proposals", lambda: _proposals(context))
        for sequence, (name, node_id, span) in enumerate(proposals):
            if name == rule_id:
                yield RuleProposal(span, node_id, MEMBER_FINDING_MESSAGES[rule_id],
                                   ("local_member_order",), sequence)

    def verify(context, candidate):
        independent = context.evidence(
            "member_findings", lambda: _independent(context), verification=True)
        return (() if (rule_id, candidate.node_id, candidate.span) in independent
                else ("unsupported_member_evidence",))

    return RuleUnit(metadata, ("syntax", "semantics", "member_paths"),
                    detect, verify, scope="document", batch_group="member_findings")
