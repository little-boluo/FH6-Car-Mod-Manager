import ctypes
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from renderer_runtime import external_dll_search, renderer_environment, renderer_failure
from renderer_check import check_renderer
from test_thumbnails import png_bytes


class RendererRuntimeTests(unittest.TestCase):
    def test_child_path_excludes_bundle_but_preserves_system_and_similar_names(self):
        # A plain mapping preserves each spelling on every platform. Windows'
        # real os.environ normalizes keys to uppercase, unlike a plain dict.
        for key in ('Path', 'PATH', 'path'):
            with self.subTest(key=key):
                original = {key: r'C:\App\_internal;C:\App\_internal\bin;C:\App\_internal-other;C:\Windows\System32', 'OTHER': 'keep'}
                with patch('renderer_runtime.os.environ', original.copy()), \
                        patch('renderer_runtime.sys.platform', 'win32'), \
                        patch('renderer_runtime.sys._MEIPASS', r'C:\App\_internal', create=True):
                    env = renderer_environment('startup.log')
                    self.assertEqual(env[key], r'C:\App\_internal-other;C:\Windows\System32')
                    self.assertEqual(env['OTHER'], 'keep')
                    self.assertEqual(env['FH6MM_RENDER_LOG'], 'startup.log')
                    self.assertEqual(dict(os.environ), original)

    def test_real_environment_normalization_and_parent_preservation(self):
        with patch.dict(os.environ, {'PATH': r'C:\App\_internal;C:\Windows\System32'}), \
                patch('renderer_runtime.sys.platform', 'win32'), \
                patch('renderer_runtime.sys._MEIPASS', r'C:\App\_internal', create=True):
            # Snapshot after the OS has normalized its keys, not the input dict.
            before = dict(os.environ)
            env = renderer_environment('startup.log')
            self.assertEqual(env['PATH'], r'C:\Windows\System32')
            self.assertEqual(dict(os.environ), before)

    def kernel(self):
        kernel = Mock()
        def get_directory(size, buffer):
            buffer.value = r'C:\Manager\_internal'
            return len(buffer.value)
        kernel.GetDllDirectoryW.side_effect = get_directory
        kernel.SetDllDirectoryW.return_value = 1
        return kernel

    def test_frozen_process_clears_and_restores_dll_directory(self):
        kernel = self.kernel()
        with patch('renderer_runtime.sys.platform', 'win32'), \
                patch('renderer_runtime.sys.frozen', True, create=True), \
                patch.object(ctypes, 'WinDLL', return_value=kernel, create=True):
            with external_dll_search():
                kernel.SetDllDirectoryW.assert_called_once_with(None)
            self.assertEqual([c.args[0] for c in kernel.SetDllDirectoryW.call_args_list],
                             [None, r'C:\Manager\_internal'])

    def test_launch_failure_still_restores_dll_directory(self):
        kernel = self.kernel()
        with patch('renderer_runtime.sys.platform', 'win32'), \
                patch('renderer_runtime.sys.frozen', True, create=True), \
                patch.object(ctypes, 'WinDLL', return_value=kernel, create=True):
            with self.assertRaisesRegex(OSError, 'launch failed'):
                with external_dll_search():
                    raise OSError('launch failed')
            kernel.SetDllDirectoryW.assert_called_with(r'C:\Manager\_internal')

    def test_unfrozen_process_does_not_change_dll_directory(self):
        with patch('renderer_runtime.sys.platform', 'win32'), \
                patch('renderer_runtime.sys.frozen', False, create=True), \
                patch.object(ctypes, 'WinDLL', create=True) as kernel:
            with external_dll_search():
                pass
            kernel.assert_not_called()

    def test_stowed_crash_keeps_startup_and_stderr_detail(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            (folder / 'startup.log').write_text('Loading App XAML resources\ninner cause', encoding='utf-8')
            (folder / 'renderer.log').write_text('native host error', encoding='utf-8')
            message = renderer_failure(3221226107, folder)
            self.assertIn('0xC000027B', message)
            self.assertIn('inner cause', message)
            self.assertIn('native host error', message)

    def run_probe(self, code, image):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name).resolve()
            exe = folder / 'renderer.exe'
            exe.write_bytes(b'fake')
            report = folder / 'check.log'
            def start(command, **kwargs):
                self.assertEqual(command[1], '--fh6-renderer-check')
                Path(kwargs['env']['FH6MM_RENDER_LOG']).write_text('probe stage', encoding='utf-8')
                if image:
                    Path(command[-1]).write_bytes(png_bytes())
                return Mock(returncode=code)
            with patch('renderer_check.renderer_path', return_value=exe), \
                    patch('renderer_check.subprocess.Popen', side_effect=start):
                result = check_renderer(report)
            return result, report.read_text(encoding='utf-8')

    def test_probe_requires_successful_exit_and_png(self):
        result, text = self.run_probe(0, True)
        self.assertEqual(result, 0)
        self.assertIn('PNG export: OK', text)

    def test_probe_rejects_exit_zero_without_png(self):
        result, text = self.run_probe(0, False)
        self.assertEqual(result, 1)
        self.assertNotIn('PNG export: OK', text)

    def test_probe_reports_native_crash_and_stage(self):
        result, text = self.run_probe(3221226107, False)
        self.assertEqual(result, 1)
        self.assertIn('0xC000027B', text)
        self.assertIn('probe stage', text)
