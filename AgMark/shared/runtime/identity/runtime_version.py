"""Privacy-safe runtime release labels; exact binary identity uses executable digests."""
import re

_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?")


def retained_runtime_version(value):
    """Project a transient version to its numeric core, or unavailable."""
    if not isinstance(value, str) or len(value) > 128:
        return None
    value = value.removeprefix("codex-cli ")
    if not _VERSION.fullmatch(value):
        return None
    return re.split(r"[-+]", value, maxsplit=1)[0]
