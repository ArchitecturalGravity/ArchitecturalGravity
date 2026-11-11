"""Legacy analysis imports backed by the standalone ArcGrav Language Engine.

Studio-only source-editing helpers remain in this package. Language-owned
submodules are compatibility aliases, never a second implementation.
"""
from AgStudio.arcgrav_language_engine.lint import Analysis, analyze
from AgStudio.arcgrav_language_engine.lint import parse, resolve
from AgStudio.arcgrav_language_engine.core import LanguageCore
from AgStudio.arcgrav_language_engine.diagnostics import DiagnosticResult
from AgStudio.arcgrav_language_engine.document import ParsedDocument
from AgStudio.arcgrav_language_engine.lint.syntax import SyntaxTree
from AgStudio.arcgrav_language_engine.lint.semantics import Semantics


def __getattr__(name):
    if name in ('RULES', 'evaluate_with_admission'):
        from . import rules
        return getattr(rules, name)
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
