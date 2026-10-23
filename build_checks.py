"""Build checks kept outside PowerShell to avoid native argument quoting issues."""
import argparse
from pathlib import Path
import struct
import subprocess
import sys
import unittest


def validate_sources(root=None):
    """Detect incomplete extraction before dependencies, tests or compilation."""
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    manifest = root / 'SOURCE_FILES.txt'
    if not manifest.is_file():
        raise RuntimeError('Source package incomplete: SOURCE_FILES.txt is missing. Download and extract the complete ZIP into a new folder.')
    names = [line.strip() for line in manifest.read_text(encoding='utf-8').splitlines() if line.strip()]
    if not names:
        raise RuntimeError('Source package incomplete: SOURCE_FILES.txt is empty.')
    missing = [name for name in names if not (root / name).is_file()]
    if missing:
        raise RuntimeError('Source package incomplete. Missing files:\n  ' + '\n  '.join(missing)
                           + '\nDownload and extract the complete ZIP into a new folder; do not skip tests.')
    print(f'Source file inventory: OK ({len(names)} files)')


def validate_environment():
    if sys.version_info < (3, 10) or struct.calcsize('P') != 8:
        raise RuntimeError('64-bit Python 3.10 or newer is required.')
    import tkinter
    print(f'Python {sys.version.split()[0]} x64 / Tcl-Tk {tkinter.TkVersion}: OK')


def smoke_test(executable):
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise FileNotFoundError(f'Packaged executable not found: {executable}')
    subprocess.run([str(executable), '--self-test'], check=True, timeout=30)
    print('Packaged EXE / Tk grid: OK')


def run_tests():
    root = Path(__file__).resolve().parent
    validate_sources(root)
    log_path = root / 'test-results.log'
    suite = unittest.defaultTestLoader.discover(str(root / 'tests'))
    # Persist every failure before printing: PowerShell 5 transcripts can omit
    # portions of native stderr, which unittest uses by default.
    with log_path.open('w', encoding='utf-8') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    print(log_path.read_text(encoding='utf-8'))
    print(f'Full test log: {log_path}')
    return result.wasSuccessful()


def check_renderer_resources(folder, report=None):
    folder = Path(folder).resolve()
    report = Path(report) if report is not None else Path(__file__).resolve().parent / 'renderer-resources.log'
    resources = sorted(p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() in ('.pri', '.xbf'))
    lines = ['Renderer resource publish inventory', f'Folder: {folder}']
    lines += [f'{p.relative_to(folder)} : {p.stat().st_size} bytes' for p in resources]
    # XBF may be embedded inside PRI; do not require a separate XBF file.
    pri = folder / 'resources.pri'
    valid = pri.is_file() and pri.stat().st_size > 0
    lines.append('Application resources.pri: OK' if valid else 'Application resources.pri: MISSING OR EMPTY')
    report.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('\n'.join(lines))
    if not valid:
        raise RuntimeError('Application resources.pri was not published. See renderer-resources.log; do not copy a PRI from another version.')


def renderer_test(executable):
    report = Path(__file__).resolve().parent / 'renderer-check.log'
    report.unlink(missing_ok=True)
    try:
        result = subprocess.run([str(Path(executable).resolve()), '--renderer-self-test', str(report)], timeout=60)
    except subprocess.TimeoutExpired:
        raise RuntimeError('Packaged renderer check timed out; see renderer-check.log')
    if report.exists():
        print(report.read_text(encoding='utf-8', errors='replace'))
    if result.returncode or not report.exists():
        raise RuntimeError('Renderer startup / PNG check failed; see renderer-check.log')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('sources', 'validate', 'smoke', 'tests', 'renderer', 'resources'))
    parser.add_argument('executable', nargs='?')
    args = parser.parse_args()
    if args.mode in ('smoke', 'renderer', 'resources') and not args.executable:
        parser.error('This check requires an executable path')
    try:
        if args.mode == 'sources':
            validate_sources()
        elif args.mode == 'validate':
            validate_environment()
        elif args.mode == 'tests':
            return 0 if run_tests() else 1
        elif args.mode == 'resources':
            check_renderer_resources(args.executable)
        elif args.mode == 'renderer':
            renderer_test(args.executable)
        else:
            smoke_test(args.executable)
    except Exception as exc:
        print(f'Build check failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
