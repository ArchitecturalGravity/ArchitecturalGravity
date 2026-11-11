"""Versioned, Qt-free color scheme persistence. Colors are RGBA bytes."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import tempfile

SCHEME_DIRECTORY = Path(__file__).resolve().parents[1] / 'color_schemes'
ROLE_LABELS = {
    'editor': 'Editor — Ordinary Text',
    'selection': 'Editor — Selected Text',
    'active_row': 'Editor — Current Row',
    'correlation_pulse': 'Editor — Correlation Pulse',
    'spelling_underline': 'Editor — Misspelled word underline',
    'gutter': 'Editor — Line Numbers',
    'map_viewport': 'Infer Map — Visible Editor Area',
    'symbol': 'Symbolic Referencing — Brackets',
    'symbol_body': 'Symbolic Referencing — Identifier',
    'operation': 'Context Operation — Arrow',
    'binder': 'Explicit Block Binding — Binder',
    'alias': 'Inline Aliasing — Keyword',
    'priority': 'Listing — Priority Marker',
    'sequence': 'Listing — Ordered Marker',
    'bullet': 'Listing — Unordered Marker',
    'section': 'Sectioning',
    'colon': 'Sectioning — Colon',
    'wildcard': 'Wildcarding — Wildcard',
    'delimiter': 'Literal Quote Block — Delimiters',
    'literal': 'Literal Quote Block — Contents / Quoted Text',
    'backtick': 'Inline Representation — Backtick Delimiters',
    'backtick_content': 'Inline Representation — Structural Name',
    'double_quote': 'Inline Representation — Double Quote Delimiters',
    'double_quote_content': 'Inline Representation — Textual Value',
}

SYNTAX_ROLES = tuple(role for role in ROLE_LABELS if role not in {'editor', 'selection', 'active_row', 'gutter', 'correlation_pulse', 'spelling_underline', 'map_viewport'})

def default_scheme(path=None):
    """Load the authoritative shipped palette; never substitute hidden colors."""
    path = Path(path) if path is not None else SCHEME_DIRECTORY / 'Default.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or type(data.get('version')) is not int
                or data['version'] != 1 or data.get('name') != 'Default'):
            raise ValueError('Expected version 1 and name Default.')
        return validate_scheme(data.get('colors'), migrate=False)
    except (OSError, ValueError, TypeError) as error:
        raise ValueError(f'Cannot load default color scheme {path}: {error}. Restore a valid Default.json.') from error

def validate_scheme(value, *, migrate=True):
    if not isinstance(value, dict):
        raise ValueError('The scheme must be an object.')
    value = deepcopy(value)
    # Inline textual values previously shared the literal style. Preserve it
    # independently for both new roles, including older user Default palettes.
    if 'literal' in value:
        for role in ('double_quote', 'double_quote_content'):
            value.setdefault(role, deepcopy(value['literal']))
    # Additive migration also supports existing user-edited Default files.
    # New defaults come exclusively from the shipped file, never hidden colors.
    for key in ('correlation_pulse', 'pulse_cycles_per_minute', 'spelling_underline', 'map_viewport'):
        if key not in value:
            defaults = json.loads((SCHEME_DIRECTORY / 'Default.json').read_text(encoding='utf-8'))['colors']
            if key not in defaults:
                raise ValueError(f'Default.json is missing {key}.')
            value[key] = deepcopy(defaults[key])
    if migrate:
        # Split old shared roles without replacing any existing custom colors.
        if 'marker' in value:
            shared = value.pop('marker')
            for role in ('colon', 'wildcard'):
                value.setdefault(role, deepcopy(shared))
        if 'binder' not in value and 'operation' in value:
            value['binder'] = deepcopy(value['operation'])
        missing = {'backtick', 'backtick_content'} - set(value)
        if 'deepest_child_opacity' not in value or missing:
            defaults = default_scheme()
            value.setdefault('deepest_child_opacity', defaults['deepest_child_opacity'])
            for role in missing:
                value[role] = defaults[role]
    if 'section' not in value and 'editor' in value:
        if not isinstance(value['editor'], dict) or 'foreground' not in value['editor']:
            raise ValueError('Editor style needs foreground and background colors.')
        value['section'] = {'foreground': deepcopy(value['editor']['foreground']),
                            'background': [0, 0, 0, 0]}
    floor = value.pop('deepest_child_opacity', None)
    speed = value.pop('pulse_cycles_per_minute', None)
    if type(speed) is not int or not 0 <= speed <= 100:
        raise ValueError('Pulse speed must be an integer from 0 (Off) to 100 cycles/minute.')
    if type(floor) is not int or not 0 <= floor <= 100:
        raise ValueError('Deepest child opacity must be an integer from 0 to 100.')
    if not isinstance(value, dict) or set(value) != set(ROLE_LABELS):
        raise ValueError('The scheme must contain exactly the supported display roles.')
    for style in value.values():
        if not isinstance(style, dict) or set(style) != {'foreground', 'background'}:
            raise ValueError('Each role needs character and background colors.')
        for color in style.values():
            if not isinstance(color, (list, tuple)) or len(color) != 4 or any(type(c) is not int or not 0 <= c <= 255 for c in color):
                raise ValueError('RGBA channels must be integers from 0 to 255.')
    return {**deepcopy(value), 'deepest_child_opacity': floor, 'pulse_cycles_per_minute': speed}

def _atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.scheme-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

class SchemeStore:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else SCHEME_DIRECTORY

    def path(self, name):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,63}', name) or name != name.strip() or name.lower() in {'selected', 'con', 'prn', 'aux', 'nul'} or (name.lower() == 'default' and name != 'Default') or re.fullmatch(r'(com|lpt)[0-9]', name.lower()):
            raise ValueError('Use 1–64 letters, numbers, spaces, hyphens or underscores; Use the exact name Default for the default scheme.')
        return self.directory / (name + '.json')

    def names(self):
        if not self.directory.exists():
            return ['Default']
        return ['Default'] + sorted((p.stem for p in self.directory.glob('*.json')
                                    if p.stem.casefold() not in {'selected', 'default'}), key=str.casefold)

    def save(self, name, scheme):
        path = self.path(name)
        _atomic_json(path, {'version': 1, 'name': name, 'colors': validate_scheme(scheme)})
        return path

    def load(self, name):
        if name == 'Default':
            path = self.path(name)
            return default_scheme(path if path.exists() else None)
        with self.path(name).open(encoding='utf-8') as stream:
            data = json.load(stream)
        if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1 or data.get('name') != name:
            raise ValueError('Unsupported or invalid color scheme file.')
        return validate_scheme(data.get('colors'))

    def select(self, name, scheme):
        _atomic_json(self.directory / 'selected.json', {'version': 1, 'name': name, 'colors': validate_scheme(scheme)})

    def selected(self):
        try:
            with (self.directory / 'selected.json').open(encoding='utf-8') as stream:
                data = json.load(stream)
            if not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1 or not isinstance(data.get('name'), str):
                raise ValueError('Invalid selected scheme.')
            if data['name'] == 'Default':
                return 'Default', self.load('Default'), None
            return data['name'], validate_scheme(data.get('colors')), None
        except FileNotFoundError:
            return 'Default', self.load('Default'), None
        except (OSError, ValueError, TypeError) as error:
            return 'Default', self.load('Default'), str(error)
