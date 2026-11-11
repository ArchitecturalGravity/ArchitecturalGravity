"""Compatibility namespace for AgStudio.arcgrav_language_engine.recognition."""
from importlib import import_module as _import_module
import sys as _sys

_engine = _import_module('AgStudio.arcgrav_language_engine.recognition')
_sys.modules[__name__ + '.source'] = _import_module('AgStudio.arcgrav_language_engine.recognition.source')
_sys.modules[__name__ + '.section_boundaries'] = _import_module('AgStudio.arcgrav_language_engine.recognition.section_boundaries')
_sys.modules[__name__] = _engine
