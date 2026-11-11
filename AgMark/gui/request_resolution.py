"""Compatibility façade for repository-backed GUI request construction."""

from .requests import RepositoryApplicationRequestResolver, ResolvedRunnerTestRequest

__all__ = ["RepositoryApplicationRequestResolver", "ResolvedRunnerTestRequest"]
