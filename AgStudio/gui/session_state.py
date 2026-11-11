"""Versioned, atomic document snapshots, independent of preference schemas."""
import json
import os
from pathlib import Path

from PySide6.QtCore import QIODevice, QSaveFile, QSettings, QStandardPaths

from .user_state import validated_layout


def validated_session(value):
    empty = {'version': 2, 'tabs': [], 'active': None}
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or value['version'] not in (1, 2) or not isinstance(value.get('tabs'), list)):
        return empty
    legacy = value['version'] == 1
    seen = set()
    for index, item in enumerate(value['tabs']):
        if not isinstance(item, dict):
            continue
        path = item.get('path')
        if path is not None or legacy:
            if (not isinstance(path, str) or '\0' in path or not Path(path).is_absolute()
                    or Path(path).suffix.lower() not in {'.arc', '.txt'} or path in seen):
                continue
        if not legacy and not isinstance(item.get('source'), str):
            continue
        tab = {'path': path}
        if not legacy:
            tab.update(source=item['source'], dirty=item.get('dirty') is True,
                       encoding='utf-8-sig' if item.get('encoding') == 'utf-8-sig' else 'utf-8')
        if isinstance(item.get('layout'), dict):
            tab['layout'] = validated_layout(item['layout'])
        for key in ('anchor', 'position', 'vertical', 'horizontal'):
            number = item.get(key, 0)
            tab[key] = number if type(number) is int and 0 <= number <= 2147483647 else 0
        if path is not None:
            seen.add(path)
        active = value.get('active')
        if ((legacy and isinstance(active, str) and path == active)
                or (not legacy and type(active) is int and index == active)):
            empty['active'] = len(empty['tabs'])
        empty['tabs'].append(tab)
    return empty


class SessionStore:
    def __init__(self, settings=None):
        self.path = None
        # Lightweight preference adapters remain isolated, like UserState().
        if isinstance(settings, QSettings):
            if os.name != 'nt' or settings.format() == QSettings.Format.IniFormat:
                self.path = Path(settings.fileName() + '.session.json')
            else:
                self.path = Path(QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.GenericConfigLocation)) / 'ArchitecturalGravity/AgStudio.session.json'
        self.error = None

    def load(self):
        if self.path is not None:
            try:
                return validated_session(json.loads(self.path.read_text(encoding='utf-8')))
            except (OSError, ValueError, RecursionError):
                pass
        return validated_session(None)

    def save(self, value):
        if self.path is None:
            return True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            validated = validated_session(value)
            if value.get('version') == 1:
                validated['version'] = 1
                active = validated['active']
                validated['active'] = validated['tabs'][active]['path'] if active is not None else None
            data = json.dumps(validated, ensure_ascii=True).encode('utf-8')
            target = QSaveFile(str(self.path))
            # Never fall back to truncating the last good checkpoint in place.
            target.setDirectWriteFallback(False)
            if not target.open(QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(target.errorString())
            if target.write(data) != len(data):
                target.cancelWriting()
                raise OSError(target.errorString())
            if not target.commit():
                raise OSError(target.errorString())
        except OSError as exc:
            self.error = str(exc)
            return False
        self.error = None
        return True
