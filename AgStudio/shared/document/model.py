"""Compatibility import; implementation lives in AgStudio.arcgrav_language_engine.document.model."""
from importlib import import_module as _import_module
import sys as _sys

# Alias the module itself so legacy imports, patches and trusted worker pickles
# all resolve to the same engine-owned classes and functions.
_sys.modules[__name__] = _import_module('AgStudio.arcgrav_language_engine.document.model')
