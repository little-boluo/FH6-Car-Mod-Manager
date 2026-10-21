"""Run inside the packaged manager so the test covers its DLL environment."""
from pathlib import Path
import subprocess
import tempfile

from renderer_runtime import external_dll_search, renderer_environment, renderer_failure
from thumbnails import renderer_path, valid_png


def check_renderer(report):
    report = Path(report).resolve()
    renderer = renderer_path().resolve()
    try:
        if not renderer.is_file():
            raise FileNotFoundError(f'Renderer missing: {renderer}')
        with tempfile.TemporaryDirectory(prefix='fh6-renderer-check-') as name:
            folder = Path(name).resolve()
            output = folder / 'preview.png'
            with (folder / 'renderer.log').open('wb') as log:
                with external_dll_search():
                    proc = subprocess.Popen([str(renderer), '--fh6-renderer-check', str(output)],
                        cwd=str(renderer.parent), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                        env=renderer_environment(folder / 'startup.log'),
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                try:
                    proc.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
                    raise RuntimeError('Renderer check timed out\n' + renderer_failure(proc.returncode, folder))
                if proc.returncode or not valid_png(output):
                    raise RuntimeError('Renderer did not produce a valid test PNG\n' + renderer_failure(proc.returncode, folder))
            report.write_text('WinUI / Direct3D / PNG export: OK\n' + renderer_failure(0, folder), encoding='utf-8')
        return 0
    except Exception as exc:
        report.write_text(f'Renderer: {renderer}\n{type(exc).__name__}: {exc}\n', encoding='utf-8')
        return 1
