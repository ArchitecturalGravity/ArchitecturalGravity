"""Process-level checks for opt-in desktop fault reporting."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from AgStudio.gui import crash_logging


class CrashLoggingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "AgStudio"
        (self.root / "gui").mkdir(parents=True)
        (self.root / "shared").mkdir()
        (self.root / "gui" / "crash_logging.py").write_text(Path(crash_logging.__file__).read_text(encoding="utf-8"), encoding="utf-8")
        (self.root / "gui" / "__main__.py").write_text(
            "import os, sys\nfrom pathlib import Path\nfrom .crash_logging import launch\n"
            "def main():\n"
            "    if sys.argv[1] == 'help': raise SystemExit(0)\n"
            "    if sys.argv[1] == 'error': raise RuntimeError('test fault')\n"
            "    if sys.argv[1] == 'abrupt': os._exit(0)\n"
            "    if sys.argv[1] == 'kill':\n"
            "        import signal\n        os.kill(os.getpid(), signal.SIGKILL)\n"
            "    if sys.argv[1] == 'abort':\n"
            "        import resource\n        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n        os.abort()\n"
            "    return 0\n"
            "raise SystemExit(launch(Path(__file__).parent.parent, __package__, main))\n", encoding="utf-8")
        self.config = self.root / "shared" / "config.json"
        self.config.write_text('{"crash_logging_enabled": true}', encoding="utf-8")

    def run_child(self, mode):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.base)
        env.pop("AG_DESKTOP_CRASH_CHILD", None)
        env.pop("AG_DESKTOP_CRASH_CLEAN", None)
        return subprocess.run([sys.executable, "-m", "AgStudio.gui", mode], cwd=self.base,
                              env=env, capture_output=True, timeout=20)

    def test_disabled_and_normal_exit_do_not_create_report(self):
        self.config.write_text('{"crash_logging_enabled": false}', encoding="utf-8")
        self.assertEqual(self.run_child('ok').returncode, 0)
        self.assertFalse((self.root / 'Runtime').exists())
        self.config.write_text('{"crash_logging_enabled": true}', encoding="utf-8")
        self.assertEqual(self.run_child('ok').returncode, 0)
        self.assertEqual(self.run_child('help').returncode, 0)
        self.assertFalse((self.root / 'error.log').exists())
        self.assertFalse(list((self.root / 'Runtime/crash_logs').iterdir()))

    def test_exception_and_abrupt_exit_preserve_reports(self):
        self.assertNotEqual(self.run_child('error').returncode, 0)
        self.assertIn('test fault', (self.root / 'error.log').read_text())
        self.assertEqual(self.run_child('abrupt').returncode, 0)
        self.assertIn('without normal shutdown', (self.root / 'error.log').read_text())
        self.assertEqual(len(list(self.root.glob('error.*.log'))), 2)

    @unittest.skipIf(os.name == 'nt', 'POSIX signal exit status')
    def test_hard_kill_is_reported_by_supervisor(self):
        self.assertNotEqual(self.run_child('kill').returncode, 0)
        self.assertIn('"exit_code": -9', (self.root / 'error.log').read_text())
        self.assertNotEqual(self.run_child('abort').returncode, 0)
        self.assertIn('Fatal Python error: Aborted', (self.root / 'error.log').read_text())

    def test_recovery_ignores_live_instances(self):
        capture, reports = crash_logging._storage(self.root)
        for name, pid in [('stale', 0), ('live', os.getpid())]:
            (capture / (name + '.run.json')).write_text(json.dumps({'run_id': name, 'supervisor_pid': pid}))
            (capture / (name + '.stderr')).write_text('previous output')
        crash_logging._recover(capture, reports)
        self.assertIn('cause unavailable', (reports / 'error.log').read_text())
        self.assertTrue((capture / 'live.run.json').exists())
        self.assertFalse((capture / 'stale.run.json').exists())

    def test_marker_write_failure_does_not_abandon_child(self):
        real_write = crash_logging._write_json
        def write(path, metadata):
            if 'child_pid' in metadata:
                raise OSError('disk full')
            real_write(path, metadata)
        process = mock.Mock(pid=12345, stderr=io.BufferedReader(io.BytesIO()))
        process.wait.return_value = 7
        with mock.patch('platform.platform', return_value='test OS'), mock.patch.object(crash_logging, '_write_json', side_effect=write), mock.patch.object(crash_logging.subprocess, 'Popen', return_value=process):
            self.assertEqual(crash_logging.supervise(self.root, 'example', []), 7)
        process.wait.assert_called_once()
        self.assertIn('"exit_code": 7', (self.root / 'error.log').read_text())

    def test_bounded_capture_and_unwritable_root_fallback(self):
        output = self.base / 'capture'
        crash_logging._capture_stderr(io.BufferedReader(io.BytesIO(b'x' * (2 * 1024 * 1024) + b'last fault')), output)
        self.assertLessEqual(output.stat().st_size, 1024 * 1024)
        self.assertTrue(output.read_bytes().endswith(b'last fault'))
        with mock.patch.object(crash_logging.tempfile, 'TemporaryFile', side_effect=PermissionError), mock.patch.dict(os.environ, {'LOCALAPPDATA': str(self.base / 'fallback')}), mock.patch('sys.stderr', new_callable=io.StringIO) as stderr:
            capture, reports = crash_logging._storage(self.root)
        self.assertEqual(capture, reports)
        self.assertIn(str(reports), stderr.getvalue())
        self.assertTrue(reports.is_dir())

    def test_capture_failure_still_drains_pipe(self):
        pipe = io.BytesIO(b'x' * 200000)
        pipe.read1 = mock.Mock(wraps=pipe.read1)
        stream = mock.Mock()
        stream.write.side_effect = OSError('disk full')
        output = mock.Mock()
        output.open.return_value = stream
        crash_logging._capture_stderr(pipe, output)
        self.assertGreaterEqual(pipe.read1.call_count, 5)
        stream.write.assert_called_once()
        self.assertTrue(pipe.closed)

    def test_live_collector_preserves_recovery_marker(self):
        process = mock.Mock(pid=12345, stderr=io.BytesIO())
        process.wait.return_value = 7
        collector = mock.Mock()
        collector.is_alive.return_value = True
        with mock.patch('platform.platform', return_value='test OS'), mock.patch.object(crash_logging.threading, 'Thread', return_value=collector), mock.patch.object(crash_logging.subprocess, 'Popen', return_value=process):
            self.assertEqual(crash_logging.supervise(self.root, 'example', []), 7)
        self.assertEqual(len(list((self.root / 'Runtime/crash_logs').glob('*.run.json'))), 1)
        self.assertEqual(len(list((self.root / 'Runtime/crash_logs').glob('*.stderr'))), 1)

    def test_config_requires_explicit_boolean(self):
        for value in ['{}', '{"crash_logging_enabled": "true"}', 'bad json']:
            self.config.write_text(value)
            self.assertFalse(crash_logging.enabled(self.root))
        self.config.unlink()
        self.assertFalse(crash_logging.enabled(self.root))


if __name__ == '__main__':
    unittest.main()
