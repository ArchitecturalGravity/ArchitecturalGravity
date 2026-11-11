"""English spelling rules use shared lazy proposals and independent checks."""
from ..spelling import SPELLING_MESSAGES
from .contracts import RuleProposal, RuleUnit

RULE_IDS = tuple(SPELLING_MESSAGES)


def _spans(context, *, verification=False):
    # Resolve via the old façade to preserve caller monkeypatch/instrumentation
    # and to use the same disabled-spellcheck semantics as the existing engine.
    from .. import rules
    return context.evidence(
        "spelling",
        lambda: rules.spelling_spans(
            context.tree, context.source,
            enabled=context.document.session.configuration.get("spellcheck", True) is not False,
            vocabulary=context.document.session.configuration.get("spelling_words", ())),
        verification=verification)


def build_rule(metadata):
    rule_id = metadata.id
    if rule_id not in SPELLING_MESSAGES:
        raise ValueError(rule_id)

    def detect(context, node):
        if node is not None:
            return
        for (name, node_id, span), message in _spans(context).items():
            if name == rule_id:
                yield RuleProposal(span, node_id, message, ("ordinary_english_word",))

    def verify(context, candidate):
        expected = (rule_id, candidate.node_id, candidate.span)
        return (() if expected in _spans(context, verification=True)
                else ("unsupported_spelling_evidence",))

    return RuleUnit(metadata, ("syntax", "prose", "spellcheck"),
                    detect, verify, scope="document")
