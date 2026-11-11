"""Exact observed Codex identities, independent of any release allowlist."""
import re


_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?")


def runtime_version(value):
    """Validate a bounded version without dropping prerelease/build identity."""
    if not isinstance(value, str) or len(value) > 128 or _VERSION.fullmatch(value) is None:
        raise ValueError("invalid observed Codex runtime version")
    return value


def cli_runtime_version(value):
    """Parse only the CLI's content-limited version response, not arbitrary text."""
    if not isinstance(value, str) or not value.startswith("codex-cli "):
        raise ValueError("invalid Codex CLI version response")
    return runtime_version(value.removeprefix("codex-cli "))
