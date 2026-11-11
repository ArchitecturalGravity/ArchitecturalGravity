"""Safe desktop dispatch uses temporary evidence only."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QProcess
from AgMark.gui import artifact_actions as a

class ArtifactActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.gid = 'generation-test'
        self.ref = self.gid + '/data ; $(echo bad).json'
        self.path = self.root / self.ref
        self.path.parent.mkdir()
        self.path.write_bytes(b'{}')
        self.digest = 'sha256:' + hashlib.sha256(b'{}').hexdigest()

    def test_repeated_actions_validate_and_dispatch_exact_local_path(self):
        actions = a.artifact_actions(self.root, self.gid, self.ref, self.digest)
        with patch.object(a, 'dispatch') as dispatch:
            for _ in range(2):
                for action in actions:
                    self.assertTrue(action.available)
                    action.operation()
            self.assertEqual(dispatch.call_count, 4)
            self.assertEqual(dispatch.call_args.args, (self.path, 'reveal'))

    def test_changed_or_missing_after_projection_fails_without_dispatch(self):
        for missing in (False, True):
            self.path.write_bytes(b'{}')
            actions = a.artifact_actions(self.root, self.gid, self.ref, self.digest)
            self.path.unlink() if missing else self.path.write_bytes(b'changed')
            with patch.object(a, 'dispatch') as dispatch, patch.object(a, '_error') as error:
                for action in actions:
                    action.operation()
                dispatch.assert_not_called()
                self.assertEqual(error.call_count, 2)

    def test_traversal_absolute_other_generation_invalid_hash(self):
        for ref, digest in [('../outside', self.digest), (str(self.path), self.digest),
                            ('generation-other/file', self.digest), (self.gid + '/../file', self.digest),
                            (self.ref, 'bad'), (self.ref, 'sha256:' + '0'*64)]:
            self.assertFalse(a.artifact_actions(self.root, self.gid, ref, digest)[0].available)

    def test_symlink_file_and_parent_escape(self):
        external = self.root / 'outside.json'
        external.write_bytes(b'{}')
        self.path.unlink()
        self.path.symlink_to(external)
        self.assertFalse(a.artifact_actions(self.root, self.gid, self.ref, self.digest)[0].available)
        self.path.unlink()
        self.path.parent.rmdir()
        self.path.parent.symlink_to(self.root, target_is_directory=True)
        self.assertFalse(a.artifact_actions(self.root, self.gid, self.gid + '/outside.json', self.digest)[0].available)

    def test_dispatch_failure_is_visible(self):
        actions = a.artifact_actions(self.root, self.gid, self.ref, self.digest)
        with patch.object(a, 'dispatch', side_effect=RuntimeError('no handler')), patch.object(a, '_error') as error:
            actions[0].operation()
            self.assertIn('no handler', str(error.call_args.args[0]))

    def test_platform_commands_no_shell_and_reveal_fallback(self):
        with patch.object(a.sys, 'platform', 'linux'), patch.object(a, '_launch') as launch:
            a.dispatch(self.path, 'open')
            self.assertEqual(launch.call_args.args, ('xdg-open', [str(self.path)]))
            a.dispatch(self.path, 'reveal')
            self.assertEqual(launch.call_args.args[0], 'dbus-send')
            launch.call_args.kwargs['fallback']()
            self.assertEqual(launch.call_args.args, ('xdg-open', [str(self.path.parent)]))
        for platform, executable in [('darwin','/usr/bin/open'),('win32','explorer.exe')]:
            with patch.object(a.sys, 'platform', platform), patch.object(a, '_launch') as launch:
                a.dispatch(self.path, 'reveal')
                self.assertEqual(launch.call_args.args[0], executable)
                self.assertEqual(launch.call_args.args[1][-1], str(self.path))

    def test_missing_launcher_and_pending_repeat(self):
        with patch.object(a, '_error') as error:
            a._launch('/nonexistent-agmark-launcher', [], key=('test', 'open'))
            process = a._launches[('test', 'open')]
            a._launch('/nonexistent-agmark-launcher', [], key=('test', 'open'))
            self.assertIs(process, a._launches[('test', 'open')])
            process.waitForFinished(2000)
            self.app.processEvents()
            self.assertNotIn(('test', 'open'), a._launches)
            error.assert_called_once()

    def test_missing_snapshot_reference_is_not_inferred_from_hash(self):
        from AgMark.gui.views.artifacts import ArtifactRowProjection, ArtifactsProjection
        off = a.ArtifactActionProjection(lambda: None, False, 'not restored')
        row = ArtifactRowProjection('identity', 'Evidence', '•', 'application/json', 'retained', '•',
                                    self.digest, '2', off, off)
        projection = ArtifactsProjection(self.gid, [row])
        restored = a.restore_artifact_actions(projection, self.root, {self.ref: self.digest})
        self.assertFalse(restored.rows[0].open_action.available)
        self.assertIsNone(restored.rows[0].reference)
        ambiguous = a.restore_artifact_actions(projection, self.root,
                         {self.ref: self.digest, self.gid + '/duplicate.json': self.digest})
        self.assertFalse(ambiguous.rows[0].open_action.available)

    def test_async_nonzero_exit_is_visible(self):
        import sys
        with patch.object(a, '_error') as error:
            a._launch(sys.executable, ['-c', 'import sys; sys.exit(3)'], key=('failure', 'open'))
            a._launches[('failure', 'open')].waitForFinished(3000)
            self.app.processEvents()
            error.assert_called_once()

    def test_read_access_time_change_is_not_content_corruption(self):
        os.utime(self.path, ns=(0, self.path.stat().st_mtime_ns))
        self.assertEqual(self.path, a.verified_path(self.root, self.gid, self.ref, self.digest))
        self.assertTrue(a.artifact_actions(self.root, self.gid, self.ref, self.digest)[0].available)

    def test_same_bytes_replacement_between_stat_and_open_is_rejected(self):
        original = Path.open
        def swapped(path, *args, **kwargs):
            if path == self.path and args == ('rb',):
                replacement = self.path.with_suffix('.replacement')
                replacement.write_bytes(b'{}')
                os.replace(replacement, self.path)
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', swapped):
            with self.assertRaisesRegex(ValueError, 'changed'):
                a.verified_path(self.root, self.gid, self.ref, self.digest)

    def test_generated_report_references_are_not_claimed_as_retained_files(self):
        from AgMark.shared.software_testing.frontends.gui import test_application_lifecycle_qt as fixture
        from AgMark.gui.projection.workspace.artifacts import _artifacts_projection
        projection = _artifacts_projection(fixture._accepted_run(self.gid), fixture._report_bundle('report-test'), None)
        generated = [r for r in projection.rows if r.reference.startswith('generated/')]
        self.assertEqual(4, len(generated))
        for row in generated:
            self.assertEqual('generated', row.status)
            self.assertFalse(row.open_action.available)
            self.assertIn('no retained local file', row.open_action.unavailable_reason)
            self.assertNotIn('outside', row.open_action.unavailable_reason)
        reopened = a.restore_artifact_actions(projection, self.root, {})
        for row in reopened.rows:
            self.assertFalse(row.open_action.available)
            self.assertNotIn('SHA256 integrity check failed', row.open_action.unavailable_reason)
