"""Readable projection of retained legacy measurement prose, never report authority.

Only the generator's measurement-provenance sections are transformed. Malformed
or unfamiliar prose is kept verbatim. The saved source/export is never rewritten.
"""
from __future__ import annotations

import re

_HEADER = re.compile(r'^### .+ measurement provenance\s*$')
_ROLE = re.compile(r'^- ([\w.-]+): (.*?); source: (.*?); meaning: (.*?); method: (.*)\.$')
from .structured_evidence import (field_label as _label, escape_text as _escape,
                                  scalar_text as _scalar, structured_fields as _structured,
                                  load_retained_json as _load_legacy_json)



def readable_provenance(source):
    """Return display Markdown without mutating retained report content."""
    result = []
    in_provenance = False
    for line in source.splitlines():
        if line.startswith('#'):
            in_provenance = bool(_HEADER.fullmatch(line))
        if not in_provenance:
            result.append(line)
            continue
        if _HEADER.fullmatch(line):
            result.extend([line, '', 'Each measurement lists its availability, source and method. Retained coverage, input values, units and technical identities are grouped below when supplied.', ''])
            continue
        match = _ROLE.fullmatch(line)
        if match:
            role, availability, source_name, meaning, method = match.groups()
            # These strings already carry the generator's escaping. Reuse verbatim.
            result.extend(['', '#### ' + _escape(_label(role)), '',
                '- Availability: ' + availability,
                '- What this measures: ' + meaning,
                '- Source: ' + source_name,
                '- Aggregation method: ' + method, ''])
            continue
        stripped = line.strip()
        label = 'Measurement details' if stripped.startswith('Details: ') else 'Efficiency' if stripped.startswith('- Efficiency: ') else None
        if label:
            raw = stripped.split(': ', 1)[1]
            try:
                decoded = _load_legacy_json(raw)
                formatted = _structured(decoded, label)
            except (ValueError, RecursionError):
                result.extend(['', label + ' (unrecognized format; retained text follows):', line, ''])
            else:
                result.extend(formatted)
            continue
        result.append(line)
    return '\n'.join(result)
