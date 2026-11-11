"""Self-contained lint rule units and shared execution contracts.

The host-independent lint runner owns candidate ordering and the common
authority gate. Each unit owns its detection and independent rule-specific
verification logic. Shared evidence is cached separately for detection and
verification so a proposal cannot become its own proof.
"""
from .contracts import RuleContext, RuleProposal, RuleUnit
from .registry import build_units

__all__ = ["RuleContext", "RuleProposal", "RuleUnit", "build_units"]
