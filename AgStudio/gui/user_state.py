"""Application preferences only; saved-file sessions live in session_state.py.

Version 1 uses one JSON settings value so interrupted writes cannot leave a
partially updated set of panel preferences. Missing/invalid fields default open.
A missing settings adapter gives an isolated, nonpersistent state for tests.
"""
import json
from copy import deepcopy

from .inference_heat import MODE_LABELS, normalize_graph_mode


# Initial desktop configuration. No file, cursor, scroll or screen position.
DEFAULT_LAYOUT = {
    'window_size': [1180, 780],
    'maximized': False,
    'editor_map_sizes': [763, 130],
    'editor_outline_sizes': [899, 275],
    'finding_sizes': [560, 180],  # Existing expanded fallback; startup is collapsed.
    'finding_collapsed': True,
    'map_fit': True,
    'map_scale': 1.0,
}


def validated_layout(value):
    result = deepcopy(DEFAULT_LAYOUT)
    if not isinstance(value, dict):
        return result
    for name, default in result.items():
        item = value.get(name)
        if isinstance(default, list):
            if (isinstance(item, list) and len(item) == 2
                    and all(type(n) is int and 0 < n <= 20000 for n in item)):
                result[name] = item.copy()
        elif type(default) is bool:
            if type(item) is bool:
                result[name] = item
        elif type(item) in (int, float) and 0 < item <= 1:
            result[name] = float(item)
    return result


class UserState:
    KEY = 'userState/panels'
    LAYOUT_KEY = 'userState/layout'
    INFERENCE_MODE_KEY = 'userState/inferenceMode'
    FILE_DIRECTORY_KEY = 'userState/fileDirectory'

    def __init__(self, settings=None):
        self.settings = settings
        self.panels = {'side_panel': True, 'error_list': True, 'document_map': True}
        self.layout = deepcopy(DEFAULT_LAYOUT)
        self.inference_mode = 'heuristic'
        self.file_directory = ''
        if settings is None:
            return
        directory = settings.value(self.FILE_DIRECTORY_KEY, '')
        if isinstance(directory, str):
            self.file_directory = directory
        try:
            saved = json.loads(settings.value(self.INFERENCE_MODE_KEY, '{}'))
            if (isinstance(saved, dict) and type(saved.get('version')) is int
                    and saved['version'] == 1):
                mode = saved.get('mode')
                if isinstance(mode, str):
                    # Retired semantic views migrate to source-aligned ST2.
                    # Existing ST2 already uses the canonical persisted name.
                    if mode in ('semantic_triad', 'semantic_triad_3', 'semantic_basic', 'semantic_full'):
                        self.set_inference_mode('semantic_triad_2')
                    elif mode in MODE_LABELS:
                        self.inference_mode = mode
        except (TypeError, ValueError):
            pass
        try:
            saved = json.loads(settings.value(self.LAYOUT_KEY, '{}'))
            if isinstance(saved, dict) and type(saved.get('version')) is int and saved['version'] == 1:
                self.layout = validated_layout(saved)
        except (TypeError, ValueError):
            pass
        try:
            saved = json.loads(settings.value(self.KEY, '{}'))
            if not isinstance(saved, dict) or type(saved.get('version')) is not int or saved['version'] != 1:
                return
            for name in self.panels:
                if type(saved.get(name)) is bool:
                    self.panels[name] = saved[name]
        except (TypeError, ValueError):
            pass

    def set_panel(self, name, visible):
        if name not in self.panels or type(visible) is not bool:
            raise ValueError('Expected a supported panel and boolean visibility.')
        self.panels[name] = visible
        if self.settings is not None:
            self.settings.setValue(self.KEY, json.dumps({'version': 1, **self.panels}))
            self.settings.sync()

    def save_layout(self, layout):
        self.layout = validated_layout(layout)
        if self.settings is not None:
            self.settings.setValue(self.LAYOUT_KEY, json.dumps({'version': 1, **self.layout}))
            self.settings.sync()

    def set_inference_mode(self, mode):
        """Persist only the application mode, never document-specific evidence."""
        mode = normalize_graph_mode(mode)
        if not isinstance(mode, str) or mode not in MODE_LABELS:
            raise ValueError('Expected a supported inference mode.')
        self.inference_mode = mode
        if self.settings is not None:
            self.settings.setValue(self.INFERENCE_MODE_KEY,
                                   json.dumps({'version': 1, 'mode': mode}))
            self.settings.sync()

    def remember_file_directory(self, directory):
        self.file_directory = str(directory)
        if self.settings is not None:
            self.settings.setValue(self.FILE_DIRECTORY_KEY, self.file_directory)
            self.settings.sync()
