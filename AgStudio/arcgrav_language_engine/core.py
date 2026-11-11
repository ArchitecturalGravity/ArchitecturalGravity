"""Qt-free source sessions and local analysis entry points."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass



def _require_string_configuration_keys(value: object) -> None:
    """Reject JSON's implicit conversion of nested mapping keys to strings.

    An integer key and its textual equivalent must not produce the same
    analysis-context identity. Track visited containers so cyclic input is
    left for the JSON serializer's existing rejection path.
    """
    pending = [value]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if not isinstance(current, (dict, list, tuple)):
            continue
        if id(current) in visited:
            continue
        visited.add(id(current))
        if isinstance(current, dict):
            for key, nested in current.items():
                if not isinstance(key, str):
                    raise TypeError("configuration keys must be strings at every depth")
                pending.append(nested)
        else:
            pending.extend(current)


@dataclass(frozen=True, slots=True, init=False)
class SourceSession:
    """Immutable source and explicit analysis context, not a ParsedDocument.

    source is the original text, including whitespace and line endings.
    Configuration is snapshotted as canonical JSON so caller mutation cannot
    silently change the input of a later language service. All nested mapping
    keys must be strings, preventing JSON key coercion from conflating distinct
    contexts. No derived state is persisted with the source.
    """

    source: str
    arcgrav_version: str
    profile: str | None
    _configuration_json: str

    def __init__(
        self,
        source: str,
        *,
        arcgrav_version: str,
        profile: str | None = None,
        configuration: Mapping[str, object] | None = None,
    ) -> None:
        if not isinstance(source, str):
            raise TypeError("source must be ordinary .arc text (str)")
        if not isinstance(arcgrav_version, str) or not arcgrav_version.strip():
            raise ValueError("an explicit ArcGrav version identifier is required")
        if profile is not None and (not isinstance(profile, str) or not profile.strip()):
            raise ValueError("profile must be a non-empty identifier or None")
        if configuration is not None and not isinstance(configuration, Mapping):
            raise TypeError("configuration must be a mapping or None")

        supplied = dict(configuration) if configuration is not None else {}
        _require_string_configuration_keys(supplied)
        try:
            configuration_json = json.dumps(
                supplied, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("configuration must contain only JSON-compatible values") from exc

        object.__setattr__(self, "source", source)
        object.__setattr__(self, "arcgrav_version", arcgrav_version)
        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "_configuration_json", configuration_json)

    @property
    def configuration(self) -> dict[str, object]:
        """Return an independent copy; callers cannot mutate this session."""
        return json.loads(self._configuration_json)

    @property
    def configuration_key(self) -> str:
        """Stable context representation, not a persisted language artifact."""
        return self._configuration_json

    def with_source(self, new_source: str) -> SourceSession:
        """Represent an edit as a new source session without reconstructing text."""
        return SourceSession(
            new_source,
            arcgrav_version=self.arcgrav_version,
            profile=self.profile,
            configuration=self.configuration,
        )


class LanguageCore:
    """Own source sessions and executable language analysis, never UI policy."""

    @staticmethod
    def open_source(
        source: str,
        *,
        arcgrav_version: str,
        profile: str | None = None,
        configuration: Mapping[str, object] | None = None,
    ) -> SourceSession:
        return SourceSession(
            source,
            arcgrav_version=arcgrav_version,
            profile=profile,
            configuration=configuration,
        )

    @staticmethod
    def parse_document(session: SourceSession):
        """Build the disposable Stage 02 structural model from this source."""
        from .document import parse_document

        return parse_document(session)




    @staticmethod
    def analyze(source: str, *, arcgrav_version: str = "current", profile=None, configuration=None):
        """Run the same executable pipeline used by every host."""
        from .lint import analyze
        return analyze(source, arcgrav_version=arcgrav_version, profile=profile,
                       configuration=configuration)
