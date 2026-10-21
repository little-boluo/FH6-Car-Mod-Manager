"""Launch the independent WinUI renderer without PyInstaller's DLL overrides."""
from i18n import t
from contextlib import contextmanager
import ctypes
import ntpath
import os
from pathlib import Path
import sys
import threading

_launch_lock = threading.Lock()


def renderer_environment(log_path):
    env = os.environ.copy()
    env['FH6MM_RENDER_LOG'] = str(log_path)
    bundle = getattr(sys, '_MEIPASS', None)
    if sys.platform == 'win32' and bundle:
        base = ntpath.normcase(ntpath.normpath(str(bundle)))
        def bundled(value):
            value = ntpath.normcase(ntpath.normpath(value.strip('"')))
            return value == base or value.startswith(base.rstrip('\\') + '\\')
        for key in list(env):
            if key.casefold() == 'path':
                env[key] = ';'.join(p for p in env[key].split(';') if p and not bundled(p))
    return env


@contextmanager
def external_dll_search():
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        yield
        return
    # Only hold this override while creating the process. Restore the manager's
    # exact directory even if Popen fails; do not hold it during rendering.
    with _launch_lock:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        get_dir, set_dir = kernel.GetDllDirectoryW, kernel.SetDllDirectoryW
        get_dir.argtypes = [ctypes.c_uint32, ctypes.c_wchar_p]
        get_dir.restype = ctypes.c_uint32
        set_dir.argtypes = [ctypes.c_wchar_p]
        set_dir.restype = ctypes.c_int
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_dir(len(buffer), buffer)
        if length >= len(buffer):
            raise OSError('DLL directory exceeds buffer size')
        previous = buffer.value if length else None
        if not set_dir(None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            yield
        finally:
            if not set_dir(previous):
                raise ctypes.WinError(ctypes.get_last_error())


def read_tail(path, limit=12000):
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - limit))
            return stream.read().decode('utf-8-sig', errors='replace')
    except OSError:
        return ''


def renderer_failure(code, folder):
    folder = Path(folder)
    message = t('渲染组件退出码 {0} (0x{1:08X})').format(code, code & 0xffffffff)
    for name in ('preview.error.txt', 'startup.log', 'renderer.log'):
        detail = read_tail(folder / name)
        if detail:
            message += f'\n[{name}]\n{detail}'
    return message
