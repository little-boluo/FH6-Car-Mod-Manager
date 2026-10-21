"""Detect game presence by process name, without requesting executable paths."""
from i18n import t
import ctypes as c
import os

GAME_EXE = 'forzahorizon6.exe'


class ProcessEntry(c.Structure):
    _fields_ = [('dwSize', c.c_uint32), ('cntUsage', c.c_uint32),
                ('th32ProcessID', c.c_uint32), ('th32DefaultHeapID', c.c_size_t),
                ('th32ModuleID', c.c_uint32), ('cntThreads', c.c_uint32),
                ('th32ParentProcessID', c.c_uint32), ('pcPriClassBase', c.c_int32),
                ('dwFlags', c.c_uint32), ('szExeFile', c.c_wchar * 260)]


def snapshot_names(kernel=None, last_error=None):
    if kernel is None:
        kernel = c.WinDLL('kernel32', use_last_error=True)
    if last_error is None:
        last_error = c.get_last_error
    kernel.CreateToolhelp32Snapshot.argtypes = [c.c_uint32, c.c_uint32]
    kernel.CreateToolhelp32Snapshot.restype = c.c_void_p
    for name in ('Process32FirstW', 'Process32NextW'):
        fn = getattr(kernel, name)
        fn.argtypes = [c.c_void_p, c.POINTER(ProcessEntry)]
        fn.restype = c.c_int
    kernel.CloseHandle.argtypes = [c.c_void_p]
    kernel.CloseHandle.restype = c.c_int
    handle = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
    if handle == c.c_void_p(-1).value or handle is None:
        raise OSError(last_error(), t('无法读取 Windows 进程列表'))
    try:
        entry = ProcessEntry()
        entry.dwSize = c.sizeof(entry)
        names = []
        ok = kernel.Process32FirstW(handle, c.byref(entry))
        while ok:
            names.append(entry.szExeFile)
            ok = kernel.Process32NextW(handle, c.byref(entry))
        code = last_error()
        if code != 18:  # ERROR_NO_MORE_FILES: normal end of snapshot.
            raise OSError(code, t('Windows 进程枚举未能完成'))
        return names
    finally:
        kernel.CloseHandle(handle)


def game_is_running():
    if os.name != 'nt':
        return False
    return any(name.casefold() == GAME_EXE for name in snapshot_names())
