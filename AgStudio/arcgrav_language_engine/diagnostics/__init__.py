"""Source-exact diagnostics with self-contained, code-derived evidence."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, TYPE_CHECKING
from ..document import SourceRange
if TYPE_CHECKING:
    from ..lint.rules import Rule

Severity = Literal['critical', 'error', 'warning', 'information']
SEVERITY_ORDER = {'information': 0, 'warning': 1, 'error': 2, 'critical': 3}

@dataclass(frozen=True, slots=True)
class RuleEvidence:
    contract_version: str
    syntax_id: str
    premises: tuple[str, ...]
    limits: str

@dataclass(frozen=True, slots=True)
class Finding:
    id: str
    rule_id: str
    severity: Severity
    source_range: SourceRange
    evidence: RuleEvidence
    suppression_prerequisites: tuple[str, ...]
    message: str

@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    document_id: str
    arcgrav_version: str
    findings: tuple[Finding, ...]
    status: Literal['pending', 'evaluated', 'unsupported_version']
    rules: tuple[Rule, ...] = ()
    suppressed_conclusions: tuple[tuple[str, str, tuple[str, ...]], ...] = ()

__all__ = ['DiagnosticResult', 'Finding', 'RuleEvidence', 'Severity', 'SEVERITY_ORDER']
