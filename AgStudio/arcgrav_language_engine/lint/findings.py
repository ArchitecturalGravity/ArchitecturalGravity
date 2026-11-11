"""One Findings stage over the prepared canonical source model."""
from ..diagnostics import DiagnosticResult
from ..document import ParsedDocument
from ..version import LANGUAGE_CONTRACT_VERSION
from .rules import RULES, evaluate_with_admission
from .semantics import Semantics
from .syntax import SyntaxTree


def assemble_diagnostics(document: ParsedDocument, tree: SyntaxTree,
                         semantics: Semantics) -> DiagnosticResult:
    if document.session.arcgrav_version != LANGUAGE_CONTRACT_VERSION:
        return DiagnosticResult(document.document_id, document.session.arcgrav_version,
                                (), 'unsupported_version')
    findings, suppressed = evaluate_with_admission(document, tree, semantics)
    return DiagnosticResult(document.document_id, document.session.arcgrav_version,
                            findings, 'evaluated', RULES, suppressed)
