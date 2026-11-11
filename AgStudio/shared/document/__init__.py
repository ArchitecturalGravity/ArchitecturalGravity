"""Compatibility namespace for AgStudio.arcgrav_language_engine.document."""
from importlib import import_module as _import_module
import sys as _sys

_engine = _import_module('AgStudio.arcgrav_language_engine.document')
_sys.modules[__name__ + '.model'] = _import_module('AgStudio.arcgrav_language_engine.document.model')
_sys.modules[__name__] = _engine
