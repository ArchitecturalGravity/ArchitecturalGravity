"""Independent, source-first ArcGrav language analysis.

Use AnalysisContext with prepare/diagnose for staged consumers, or analyze for a
complete result. Importing the package does not load the diagnostic checks or
spelling implementation. Public model types retain stable engine module paths.
"""
from importlib import import_module
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import PathFinder
from pathlib import Path
import sys


_ENGINE_NAME = 'arcgrav_language_engine'
_ENGINE_ALIAS = 'AgStudio.' + _ENGINE_NAME
_ENGINE_PARENT = Path(__file__).resolve().parent.parent


class _EngineAliasLoader(Loader):
    """Reuse an engine module, including its original loader and pickle names."""

    def __init__(self, target):
        self.target = target
        self.original_spec = None

    def create_module(self, spec):
        module = import_module(self.target)
        expected_root = _ENGINE_PARENT / _ENGINE_NAME
        if not Path(module.__file__).resolve().is_relative_to(expected_root):
            raise ImportError(
                'AgStudio cannot alias a language engine loaded from another '
                'installation; start a fresh Python process for this checkout.'
            )
        self.original_spec = module.__spec__
        return module

    def exec_module(self, module):
        # importlib assigns the alias spec even when create_module returns an
        # existing object. Preserve the engine's reload/resource identity too.
        module.__spec__ = self.original_spec


class _EngineAliasFinder(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == _ENGINE_NAME:
            # Resolve only this package from its actual source directory. Never
            # add all Studio modules to global search paths or prefer an
            # unrelated installed engine over the checked-out implementation.
            return PathFinder.find_spec(fullname, [str(_ENGINE_PARENT)])
        if fullname == _ENGINE_ALIAS or fullname.startswith(_ENGINE_ALIAS + '.'):
            spec = PathFinder.find_spec(fullname, path)
            if spec is not None:
                engine_name = fullname[len('AgStudio.'):]
                spec.loader = _EngineAliasLoader(engine_name)
            return spec
        return None


# Reloading either package name must not accumulate global import hooks.
# Standalone installations have no host alias and need no import hook.
if (__name__ == _ENGINE_ALIAS or _ENGINE_PARENT.name == 'AgStudio') and not any(
        getattr(finder, '_agstudio_engine_alias', None) == str(_ENGINE_PARENT)
        for finder in sys.meta_path):
    _finder = _EngineAliasFinder()
    _finder._agstudio_engine_alias = str(_ENGINE_PARENT)
    sys.meta_path.insert(0, _finder)


if __name__ == _ENGINE_ALIAS:
    # The namespace host has no initializer. Bootstrap the public package on
    # first checkout import, then replace this temporary module with it before
    # any model classes can be defined under a second name.
    sys.modules[__name__] = _EngineAliasLoader(_ENGINE_NAME).create_module(None)
else:
    from .context import AnalysisContext
    from .version import API_VERSION, ANALYSIS_SCHEMA_VERSION, LANGUAGE_CONTRACT_VERSION, PACKAGE_VERSION, SNAPSHOT_SCHEMA_VERSION, __version__

    _EXPORT_MODULES = {
        **dict.fromkeys(('prepare', 'diagnose', 'analyze'), '.api'),
        **dict.fromkeys(('LanguageCore', 'SourceSession'), '.core'),
        **dict.fromkeys(('DocumentFact', 'ParsedDocument', 'RelationshipState', 'SourcePoint', 'SourceRange', 'parse_document'), '.document'),
        **dict.fromkeys(('RecognitionResult', 'SourceSpan', 'SourceRegion', 'SourceObservation', 'SourceOccurrence', 'SourceRecovery', 'recognize_source'), '.recognition'),
        **dict.fromkeys(('SyntaxTree', 'Node', 'Token'), '.lint.syntax'),
        **dict.fromkeys(('Semantics', 'Symbol', 'Resolution', 'Binding'), '.lint.semantics'),
        'MemberOccurrence': '.lint.members',
        'CanonicalDocument': '.lint.model',
        'Analysis': '.lint',
        **dict.fromkeys(('AnalysisSnapshot', 'PreparedSnapshot', 'DocumentSnapshot', 'PackedAnalysisSnapshot', 'freeze_document', 'restore_document', 'freeze_analysis', 'restore_analysis', 'pack_analysis', 'unpack_analysis'), '.snapshot'),
        **dict.fromkeys(('DiagnosticResult', 'Finding', 'Severity', 'RuleEvidence'), '.diagnostics'),
    }


    def __getattr__(name):
        module_name = _EXPORT_MODULES.get(name)
        if module_name is None:
            raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
        value = getattr(import_module(module_name, __name__), name)
        globals()[name] = value
        return value


    def __dir__():
        return sorted(set(globals()) | set(_EXPORT_MODULES))


    __all__ = ['AnalysisContext', 'PACKAGE_VERSION', 'API_VERSION', 'ANALYSIS_SCHEMA_VERSION', 'LANGUAGE_CONTRACT_VERSION', 'SNAPSHOT_SCHEMA_VERSION', '__version__', *_EXPORT_MODULES]
