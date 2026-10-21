"""Recycle one explicit file, retaining Windows permanent-deletion warnings."""
from i18n import t
import ctypes as c
import os
from pathlib import Path


class FileOperation(c.Structure):
    # shellapi.h uses 1-byte packing for SHFILEOPSTRUCT on 32-bit Windows.
    if c.sizeof(c.c_void_p) == 4:
        _pack_ = 1
    _fields_ = [('hwnd', c.c_void_p), ('wFunc', c.c_uint32),
                ('pFrom', c.c_void_p), ('pTo', c.c_void_p),
                ('fFlags', c.c_uint16), ('fAnyOperationsAborted', c.c_int32),
                ('hNameMappings', c.c_void_p), ('lpszProgressTitle', c.c_void_p)]


def recycle_file(path, shell=None):
    if os.name != 'nt' and shell is None:
        raise OSError(t('删除按钮使用 Windows 回收站；当前系统不支持，不会改为永久删除。'))
    path = Path(path).absolute()
    if any(char in str(path) for char in ('\0', '*', '?')):
        raise ValueError(t('删除路径不允许包含通配符或空字符。'))
    if not path.is_file() or path.is_symlink():
        raise OSError(t('只能删除指定的实际文件。'))
    if shell is None:
        shell = c.WinDLL('shell32', use_last_error=True)
    shell.SHFileOperationW.argtypes = [c.POINTER(FileOperation)]
    shell.SHFileOperationW.restype = c.c_int
    # The buffer must remain alive and include two terminating NUL characters.
    names = c.create_unicode_buffer(str(path) + '\0', len(str(path)) + 2)
    op = FileOperation()
    op.wFunc = 3  # FO_DELETE
    op.pFrom = c.cast(names, c.c_void_p).value
    # ALLOWUNDO, NOCONFIRMATION, WANTNUKEWARNING, NORECURSION, NO_CONNECTED_ELEMENTS.
    # WANTNUKEWARNING retains OS confirmation if the file cannot be recycled.
    op.fFlags = 0x0040 | 0x0010 | 0x4000 | 0x1000 | 0x2000
    result = shell.SHFileOperationW(c.byref(op))
    if op.fAnyOperationsAborted:
        raise OSError(t('删除已取消，未完成删除操作。'))
    if result != 0:
        raise OSError(t('Windows 删除失败（代码 {0}），不会尝试直接永久删除。').format(result))
