"""Explicit, immutable inputs to source analysis."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json

from .core import SourceSession


@dataclass(frozen=True, slots=True, init=False)
class AnalysisContext:
    """A language version, optional profile, and canonical JSON configuration.

    The language version is required. Unknown nonempty versions remain valid
    contexts, with the same conservative admission behavior as SourceSession.
    Validation and JSON conversion intentionally use that existing contract.
    """

    arcgrav_version: str
    profile: str | None
    _configuration_json: str

    def __init__(
        self,
        *,
        arcgrav_version: str,
        profile: str | None = None,
        configuration: Mapping[str, object] | None = None,
    ) -> None:
        session = SourceSession('', arcgrav_version=arcgrav_version,
                                profile=profile, configuration=configuration)
        object.__setattr__(self, 'arcgrav_version', session.arcgrav_version)
        object.__setattr__(self, 'profile', session.profile)
        object.__setattr__(self, '_configuration_json', session.configuration_key)

    @property
    def version(self) -> str:
        return self.arcgrav_version

    @property
    def configuration(self) -> dict[str, object]:
        """Return a defensive copy of the JSON-compatible configuration."""
        return json.loads(self._configuration_json)

    @property
    def configuration_json(self) -> str:
        return self._configuration_json

    @property
    def configuration_key(self) -> str:
        return self._configuration_json
