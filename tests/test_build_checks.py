from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from build_checks import smoke_test, validate_environment, check_renderer_resources


class BuildCheckTests(unittest.TestCase):
    def test_unicode_and_space_path_passed_as_one_argument(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / '模组 管理器.exe'
            executable.write_bytes(b'test fixture')
            with patch('build_checks.subprocess.run') as run, redirect_stdout(io.StringIO()) as output:
                smoke_test(executable)
            run.assert_called_once_with([str(executable.resolve()), '--self-test'], check=True, timeout=30)
            self.assertIn('Packaged EXE / Tk grid: OK', output.getvalue())

    def test_missing_executable_does_not_launch(self):
        with tempfile.TemporaryDirectory() as folder, patch('build_checks.subprocess.run') as run:
            with self.assertRaises(FileNotFoundError):
                smoke_test(Path(folder) / 'missing.exe')
            run.assert_not_called()

    def test_failed_executable_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / 'manager.exe'
            executable.write_bytes(b'test fixture')
            with patch('build_checks.subprocess.run', side_effect=subprocess.CalledProcessError(1, ['manager'])):
                with self.assertRaises(subprocess.CalledProcessError):
                    smoke_test(executable)

    def test_32_bit_python_is_rejected(self):
        with patch('build_checks.struct.calcsize', return_value=4):
            with self.assertRaisesRegex(RuntimeError, '64-bit'):
                validate_environment()

    def test_missing_app_pri_rejected_even_when_dependency_pri_exists(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            root=Path(folder); (root/'Microsoft.UI.Xaml.pri').write_bytes(b'dependency fixture')
            report=root/'report.txt'
            with self.assertRaisesRegex(RuntimeError,'resources.pri was not published'):
                check_renderer_resources(root, report)
            self.assertIn('MISSING OR EMPTY',report.read_text())

    def test_empty_app_pri_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            root=Path(folder); (root/'resources.pri').touch()
            with self.assertRaises(RuntimeError):
                check_renderer_resources(root, root/'report.txt')

    def test_app_pri_does_not_require_loose_xbf_or_replace_runtime_probe(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            root=Path(folder); (root/'resources.pri').write_bytes(b'presence-check fixture, not a real PRI')
            check_renderer_resources(root, root/'report.txt')
            self.assertIn('Application resources.pri: OK',(root/'report.txt').read_text())


if __name__ == '__main__':
    unittest.main()
