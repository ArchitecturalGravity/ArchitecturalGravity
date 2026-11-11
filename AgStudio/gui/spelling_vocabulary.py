"""Explicit user vocabulary, independent of documents and preference schemas."""
import json
import os
from pathlib import Path
import stat

from PySide6.QtCore import QIODevice, QLockFile, QSaveFile, QSettings, QStandardPaths

from ..shared.lint.spelling import normalize_vocabulary_word

MAX_BYTES = 1024 * 1024
MAX_WORDS = 10000


def _words(value):
    if not isinstance(value, list) or len(value) > MAX_WORDS:
        raise ValueError('Expected a list of at most 10,000 words.')
    result = set()
    for word in value:
        normalized = normalize_vocabulary_word(word)
        if normalized is None:
            raise ValueError('Each entry must be one word of at most 128 characters.')
        result.add(normalized)
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON keys in vocabulary; repair the file before saving.')
        result[key] = value
    return result


class SpellingVocabularyStore:
    def __init__(self, settings=None, *, path=None):
        self.path = Path(path) if path is not None else None
        if self.path is None and isinstance(settings, QSettings):
            if os.name != 'nt' or settings.format() == QSettings.Format.IniFormat:
                self.path = Path(settings.fileName() + '.spelling.json')
            else:
                self.path = Path(QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.GenericConfigLocation)) / 'ArchitecturalGravity/AgStudio.spelling.json'
        self.accepted = set()
        self.ignored = set()
        self.error = None
        self.reload()

    @property
    def words(self):
        return sorted(self.accepted | self.ignored)

    def _read(self):
        if self.path is None:
            return {'version': 1, 'accepted': sorted(self.accepted), 'ignored': sorted(self.ignored)}
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return {'version': 1, 'accepted': [], 'ignored': []}
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError('Vocabulary must be a regular file no larger than 1 MiB; symbolic links are not supported.')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        with os.fdopen(os.open(self.path, flags), 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('Vocabulary must be a regular file.')
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Vocabulary must be no larger than 1 MiB.')
        payload = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_object)
        if (not isinstance(payload, dict) or type(payload.get('version')) is not int
                or payload['version'] != 1):
            raise ValueError('Unsupported vocabulary format; expected version 1.')
        _words(payload.get('accepted'))
        _words(payload.get('ignored'))
        return payload

    def reload(self):
        try:
            payload = self._read()
            self.accepted = _words(payload['accepted'])
            self.ignored = _words(payload['ignored'])
        except (OSError, ValueError, RecursionError) as exc:
            # Preserve the last good in-memory vocabulary on failed reads.
            self.error = str(exc)
            return False
        self.error = None
        return True

    def update(self, *, add=None, scope='accepted', accepted=None, ignored=None, expected=None):
        """Merge single additions; guard whole-list edits against concurrent changes.

        Unknown JSON fields survive writes. Invalid existing data is never replaced.
        """
        lock = None
        try:
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                lock = QLockFile(str(self.path) + '.lock')
                if not lock.tryLock(0):
                    raise OSError('Vocabulary is in use by another window. Try again.')
            payload = self._read()
            if self.path is not None and self.path.exists() and not self.path.stat().st_mode & 0o222:
                raise PermissionError('Vocabulary file is read-only.')
            current = (_words(payload['accepted']), _words(payload['ignored']))
            if expected is not None and current != expected:
                raise ValueError('Vocabulary changed since this dialog opened. Reopen it before saving.')
            if add is not None:
                if scope not in ('accepted', 'ignored'):
                    raise ValueError('Unknown vocabulary list.')
                words = _words(payload[scope]) | _words([add])
                payload[scope] = sorted(words)
            else:
                payload['accepted'] = sorted(_words(accepted))
                payload['ignored'] = sorted(_words(ignored))
            # Recheck limits after merging, before replacing any bytes.
            _words(payload['accepted'])
            _words(payload['ignored'])
            data = (json.dumps(payload, ensure_ascii=True, indent=2) + '\n').encode('utf-8')
            if len(data) > MAX_BYTES:
                raise ValueError('Vocabulary exceeds 1 MiB.')
            if self.path is not None:
                target = QSaveFile(str(self.path))
                target.setDirectWriteFallback(False)
                if not target.open(QIODevice.OpenModeFlag.WriteOnly):
                    raise OSError(target.errorString())
                if target.write(data) != len(data):
                    target.cancelWriting()
                    raise OSError(target.errorString())
                if not target.commit():
                    raise OSError(target.errorString())
            self.accepted = _words(payload['accepted'])
            self.ignored = _words(payload['ignored'])
            self.error = None
            return True
        except (OSError, ValueError, RecursionError) as exc:
            self.error = str(exc)
            return False
        finally:
            if lock is not None:
                lock.unlock()
