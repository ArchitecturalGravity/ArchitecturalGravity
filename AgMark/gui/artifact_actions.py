"""Runtime-created read-only desktop actions; disk data never supplies callbacks.

Each click revalidates generation confinement, symlinks and expected SHA256.
External viewers necessarily reopen the path after dispatch (not an atomic read).
"""
from dataclasses import replace
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import atexit
import tempfile
import shutil
from AgMark.shared.runtime.artifacts.archive import archive_path, read_archive_member, digest
from AgMark.gui.views.artifacts import ArtifactActionProjection


_extract_root = None


def verified_path(root, generation_id, reference, digest, *, materialize=True):
    if not isinstance(reference, str) or '\\' in reference:
        raise ValueError('Artifact reference is not a safe relative path')
    parts = PurePosixPath(reference).parts
    if not parts or PurePosixPath(reference).is_absolute() or '..' in parts or parts[0] != generation_id:
        raise ValueError('Artifact path is outside the selected generation')
    if not isinstance(digest, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise ValueError('Artifact has no valid expected SHA256')
    if not isinstance(generation_id, str) or not re.fullmatch(r'generation-[a-zA-Z0-9_-]+', generation_id):
        raise ValueError('Invalid selected generation')
    root = Path(root).absolute()
    sealed = archive_path(root, generation_id)
    if sealed.exists() or sealed.is_symlink():
        if sealed.is_symlink():
            raise ValueError("Run archive symlink is forbidden")
        data = read_archive_member(sealed, reference)
        if "sha256:" + hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("Archived artifact digest differs from its retained record")
        if not materialize:
            return sealed
        global _extract_root
        if _extract_root is None:
            _extract_root = Path(tempfile.mkdtemp(prefix="agmark-artifact-"))
            atexit.register(shutil.rmtree, _extract_root, ignore_errors=True)
        suffix = PurePosixPath(reference).suffix
        with tempfile.NamedTemporaryFile(dir=_extract_root, prefix="artifact-", suffix=suffix, delete=False) as stream:
            stream.write(data)
            stream.flush()
        return Path(stream.name)
    path = root.joinpath(*parts)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Artifact path contains a symlink')
    if not path.resolve(strict=True).is_relative_to(root.resolve(strict=True) / generation_id):
        raise ValueError('Artifact path escapes its generation')
    def identity(value):
        # Reading may update atime. Only identity/content metadata detects a
        # replacement or mutation; compare the opened descriptor as well.
        return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
                value.st_mtime_ns, value.st_ctime_ns)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('Artifact is not a regular file')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        if identity(before) != identity(os.fstat(stream.fileno())):
            raise ValueError('Artifact changed while opening')
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
        if identity(before) != identity(os.fstat(stream.fileno())):
            raise ValueError('Artifact changed while reading')
    if identity(before) != identity(path.stat()) or 'sha256:' + h.hexdigest() != digest:
        raise ValueError('Artifact changed: SHA256 integrity check failed')
    return path


_launches = {}
_dialogs = []


def _error(message):
    from PySide6.QtWidgets import QApplication, QMessageBox
    box = QMessageBox(QMessageBox.Icon.Warning, 'Artifact action unavailable', str(message),
                      QMessageBox.StandardButton.Ok, QApplication.activeWindow())
    _dialogs.append(box)
    box.finished.connect(lambda _: _dialogs.remove(box) if box in _dialogs else None)
    box.open()


def _launch(program, args, *, key, fallback=None):
    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication
    if key in _launches:
        return
    process = QProcess(QApplication.instance())
    _launches[key] = process
    done = False
    def finish(ok, detail=''):
        nonlocal done
        if done:
            return
        done = True
        _launches.pop(key, None)
        process.deleteLater()
        if not ok:
            if fallback is not None:
                fallback()
            else:
                _error('The desktop could not open this artifact or folder. Check its default application.\n' + detail)
    process.errorOccurred.connect(lambda _: finish(False, process.errorString()))
    process.finished.connect(lambda code, status: finish(code == 0 and status == QProcess.ExitStatus.NormalExit,
        bytes(process.readAllStandardError()).decode('utf-8', errors='replace')[-1000:]))
    process.start(program, args)


def dispatch(path, action):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    key = (str(path), action)
    if sys.platform == 'darwin':
        _launch('/usr/bin/open', (['-R'] if action == 'reveal' else []) + [str(path)], key=key)
    elif sys.platform == 'win32':
        if action == 'reveal':
            _launch('explorer.exe', ['/select,', str(path)], key=key)
        elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            raise RuntimeError('No default application accepted the artifact')
    elif action == 'reveal':
        _launch('dbus-send', ['--session', '--print-reply', '--reply-timeout=1500',
            '--dest=org.freedesktop.FileManager1', '/org/freedesktop/FileManager1',
            'org.freedesktop.FileManager1.ShowItems', 'array:string:' + path.as_uri(), 'string:'],
            key=key, fallback=lambda: _launch('xdg-open', [str(path.parent)], key=key))
    else:
        _launch('xdg-open', [str(path)], key=key)


def artifact_actions(root, generation_id, reference, digest):
    def invoke(action):
        try:
            path = verified_path(root, generation_id, reference, digest,
                                 materialize=action != "reveal")
            dispatch(path, action)
        except (OSError, ValueError, RuntimeError) as exc:
            _error(exc)
    try:
        if root is None:
            raise ValueError('No retained artifact store is available')
        verified_path(root, generation_id, reference, digest, materialize=False)
    except (OSError, ValueError, TypeError) as exc:
        disabled = ArtifactActionProjection(lambda: None, False, str(exc))
        return disabled, disabled
    return tuple(ArtifactActionProjection(lambda action=action: invoke(action), True)
                 for action in ('open', 'reveal'))


def restore_artifact_actions(projection, root, inventory):
    """Rebind only exact archived references; never infer matches by hash."""
    rows = []
    for row in projection.rows:
        reference = row.reference
        digest = inventory.get(reference) if isinstance(reference, str) else None
        if reference is None:
            unavailable = ArtifactActionProjection(lambda: None, False,
                'Archived artifact has no exact retained reference.')
            actions = (unavailable, unavailable)
        elif reference not in inventory:
            unavailable = ArtifactActionProjection(lambda: None, False,
                'No generation-local file is retained for this artifact. Export generated reports from Reports.')
            actions = (unavailable, unavailable)
        else:
            actions = artifact_actions(root, projection.run_id, reference,
                                       digest if digest == row.integrity_hash else None)
        rows.append(replace(row, open_action=actions[0], reveal_action=actions[1], reference=reference))
    return replace(projection, rows=rows)
