"""Shared IDE/CLI analysis; no Qt or document-directed I/O/execution effects."""
from dataclasses import dataclass

from ..core import LanguageCore
from ..version import ANALYSIS_SCHEMA_VERSION
from ..diagnostics import DiagnosticResult
from ..document import ParsedDocument
from .syntax import SyntaxTree, parse
from .semantics import Semantics, resolve


def __getattr__(name):
    # Preserve named imports of the former rule exports without loading their
    # implementation for consumers that need only parser/model types.
    if name in ('RULES', 'evaluate_with_admission'):
        from . import rules
        return getattr(rules, name)
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


@dataclass(frozen=True, slots=True)
class Analysis:
    document: ParsedDocument
    tree: SyntaxTree
    semantics: Semantics
    diagnostics: DiagnosticResult
    unresolved: tuple[str, ...]
    conformance: str = 'unknown'

    def as_record(self) -> dict:
        from dataclasses import asdict
        return {
            'schema_version': ANALYSIS_SCHEMA_VERSION, 'document_id': self.document.document_id,
            'arcgrav_version': self.document.session.arcgrav_version,
            'conformance': self.conformance,
            'findings': [asdict(f) for f in self.diagnostics.findings],
            'suppressed_conclusions': self.diagnostics.suppressed_conclusions,
            'unresolved': self.unresolved,
            'rules': [asdict(r) for r in self.diagnostics.rules],
            'tree': [asdict(n) for n in self.tree.nodes],
            'semantics': asdict(self.semantics),
        }


def analyze(source: str, *, arcgrav_version: str = 'current', profile=None, configuration=None) -> Analysis:
    """Compatibility entry point; all hosts use the public engine pipeline."""
    from ..api import analyze as analyze_source
    from ..context import AnalysisContext

    return analyze_source(source, AnalysisContext(
        arcgrav_version=arcgrav_version, profile=profile,
        configuration=configuration,
    ))
