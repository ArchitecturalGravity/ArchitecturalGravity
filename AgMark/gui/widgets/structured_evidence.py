"""Safe, lossless display helpers for nested retained evidence."""
import re
import json
from decimal import Decimal

_LABELS = {
    'meaning': 'What this measures', 'method': 'Measurement method',
    'kind': 'Measurement type', 'coverage': 'Measurement coverage',
    'inputs': 'Retained input measurements', 'details': 'Measurement details',
    'counting_rules': 'Counting rules', 'evidence_references': 'Evidence references',
    'execution_boundary_fingerprint': 'Execution boundary fingerprint',
    'measured_attempts': 'Measured attempts', 'observed_attempts': 'Observed attempts',
    'observed_observations': 'Observed observations', 'planned_observations': 'Planned observations',
}


def field_label(key):
    text = key.replace('_', ' ')
    return _LABELS.get(key, text[:1].upper() + text[1:])


def escape_text(value):
    # Values are text, never Markdown/HTML instructions. Preserve embedded newlines
    # visibly inside table cells, rather than silently merging distinct lines.
    text = str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = re.sub(r'([\\`*_{}\[\]()#+.!|~-])', r'\\\1', text)
    return text.replace('\r', '\\r').replace('\n', '\\n')


def scalar_text(value):
    if value is None:
        return 'Not recorded (null)'
    if value is True or value is False:
        return ('True' if value else 'False') + ' (boolean)'
    if value == '':
        return 'Empty text (empty string)'
    if value == {}:
        return 'No fields (empty object)'
    if value == []:
        return 'No items (empty list)'
    if isinstance(value, str) and value in ('true', 'false', 'null'):
        return escape_text(value) + ' (text)'
    return escape_text(value)


def structured_fields(value, path='Measurement details'):
    """Group nested records; every scalar, array position and empty value survives."""
    lines = ['', '**' + escape_text(path) + '**', '']
    if not isinstance(value, (dict, list)) or not value:
        return lines + [scalar_text(value), '']
    items = list(value.items()) if isinstance(value, dict) else [(f'Item {i}', v) for i, v in enumerate(value, 1)]
    leaves = [(k, v) for k, v in items if not isinstance(v, (dict, list)) or not v]
    if leaves:
        lines += ['| Field | Recorded value |', '| --- | --- |']
        for key, item in leaves:
            lines.append('| ' + escape_text(field_label(key)) + ' | ' + scalar_text(item) + ' |')
    # Coverage comes first so completeness is readable before technical identities.
    groups = [(k, v) for k, v in items if isinstance(v, (dict, list)) and v]
    groups.sort(key=lambda pair: pair[0] != 'coverage')
    for key, item in groups:
        lines += structured_fields(item, path + ' / ' + field_label(key))
    return lines + ['']


def load_retained_json(text, *, legacy_markup=True):
    # Reverse only escapes emitted by generation.cell, not arbitrary HTML entities.
    if legacy_markup:
        text = text.replace('\\|', '|').replace('&lt;', '<').replace('&gt;', '>')
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate field")
            result[key] = value
        return result
    return json.loads(text, parse_float=Decimal, object_pairs_hook=unique_object, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))

