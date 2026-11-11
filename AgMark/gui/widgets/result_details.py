"""Readable selected-treatment details; retained projection strings stay intact."""
import re
from .structured_evidence import escape_text, field_label, structured_fields
from .structured_evidence import load_retained_json

_ROLE = re.compile(r'^([\w.-]+): (.*?) \((.*?)\)$')


def treatment_details_markdown(row):
    lines = ['## ' + escape_text(row.treatment), '',
             'Evidence: ' + escape_text(row.evidence), '']
    source = row.details.splitlines()
    if source and source[0] == 'Evidence: ' + row.evidence:
        source = source[1:]
    if not source:
        lines += ['No additional measurement details were recorded for this treatment.', '']
    for line in source:
        role = _ROLE.fullmatch(line)
        if role:
            key, availability, unit = role.groups()
            lines += ['## ' + escape_text(field_label(key)), '',
                      '- Availability: ' + escape_text(availability),
                      '- Unit: ' + escape_text(unit), '']
            continue
        label = next((prefix for prefix in ('Registered metric', 'Details', 'Efficiency', 'Session measurements') if line.startswith(prefix + ': ')), None)
        if label:
            raw = line[len(label) + 2:]
            title = {'Registered metric': 'Accuracy · registered metric', 'Details': 'Measurement details', 'Efficiency': 'Efficiency', 'Session measurements': 'Trial session telemetry' }[label]
            try:
                data = load_retained_json(raw, legacy_markup=False)
                formatted = structured_fields(data, title)
            except (ValueError, RecursionError):
                lines += ['', '**' + escape_text(title) + '**', '', escape_text(raw), '']
            else:
                if label != 'Details':
                    lines += ['## ' + escape_text(title), '']
                    # The section heading already names the group.
                    formatted = formatted[3:]
                lines += formatted
            continue
        if line.startswith('Value: ') and '; kind: ' in line and '; method: ' in line:
            value, rest = line[7:].split('; kind: ', 1)
            kind, method = rest.split('; method: ', 1)
            lines += ['- Value: ' + ('Not recorded (null)' if value == 'None' else escape_text(value)),
                      '- Measurement type: ' + escape_text(kind),
                      '- Measurement method: ' + escape_text(method), '']
        elif line.startswith('Source: ') and '; meaning: ' in line:
            source_name, meaning = line[8:].split('; meaning: ', 1)
            lines += ['- Source: ' + escape_text(source_name), '- What this measures: ' + escape_text(meaning), '']
        elif line.startswith('Evidence references: '):
            refs = line[len('Evidence references: '):]
            lines += ['**Evidence references**', '', escape_text(refs) if refs else 'None recorded.', '']
        else:
            # Unfamiliar future prose remains visible, never interpreted as markup.
            lines += [escape_text(line), '']
    return '\n'.join(lines)
