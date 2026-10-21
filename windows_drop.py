"""Native WM_DROPFILES integration. Uses only ctypes, no tkdnd dependency."""
from i18n import t
import os
import queue


class WindowsDrop:
    def __init__(self, root, callback):
        if os.name != 'nt':
            raise OSError(t('窗口拖放仅支持 Windows。'))
        import ctypes as c
        from ctypes import wintypes as w
        self.root, self.callback, self.events = root, callback, queue.Queue()
        self.closed = False
        self.c = c
        self.user = c.WinDLL('user32', use_last_error=True)
        self.shell = c.WinDLL('shell32', use_last_error=True)
        self.common = c.WinDLL('comctl32', use_last_error=True)
        self.proc_type = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, c.c_size_t, c.c_ssize_t, c.c_size_t, c.c_size_t)
        self.common.SetWindowSubclass.argtypes = [w.HWND, self.proc_type, c.c_size_t, c.c_size_t]
        self.common.SetWindowSubclass.restype = w.BOOL
        self.common.RemoveWindowSubclass.argtypes = [w.HWND, self.proc_type, c.c_size_t]
        self.common.RemoveWindowSubclass.restype = w.BOOL
        self.common.DefSubclassProc.argtypes = [w.HWND, w.UINT, c.c_size_t, c.c_ssize_t]
        self.common.DefSubclassProc.restype = c.c_ssize_t
        self.user.GetAncestor.argtypes = [w.HWND, w.UINT]
        self.user.GetAncestor.restype = w.HWND
        self.shell.DragAcceptFiles.argtypes = [w.HWND, w.BOOL]
        self.shell.DragAcceptFiles.restype = None
        self.shell.DragQueryFileW.argtypes = [w.HANDLE, w.UINT, w.LPWSTR, w.UINT]
        self.shell.DragQueryFileW.restype = w.UINT
        self.shell.DragFinish.argtypes = [w.HANDLE]
        self.shell.DragFinish.restype = None
        root.update_idletasks()
        self.hwnd = self.user.GetAncestor(root.winfo_id(), 2) or root.winfo_id()
        self.proc = self.proc_type(self.handle)  # Keep the callback alive.
        self.ident = 0xF606
        if not self.common.SetWindowSubclass(self.hwnd, self.proc, self.ident, 0):
            raise OSError(t('无法注册 Windows 拖放回调。'))
        self.shell.DragAcceptFiles(self.hwnd, True)
        root.after(100, self.poll)

    def handle(self, hwnd, msg, wp, lp, ident, ref):
        if msg == 0x0233:  # WM_DROPFILES
            try:
                count = self.shell.DragQueryFileW(wp, 0xFFFFFFFF, None, 0)
                paths = []
                for i in range(count):
                    size = self.shell.DragQueryFileW(wp, i, None, 0)
                    buf = self.c.create_unicode_buffer(size + 1)
                    self.shell.DragQueryFileW(wp, i, buf, size + 1)
                    paths.append(buf.value)
                self.events.put(paths)
            except Exception:
                self.events.put([])
            finally:
                self.shell.DragFinish(wp)
            return 0
        if msg == 0x0082:  # WM_NCDESTROY
            self.common.RemoveWindowSubclass(hwnd, self.proc, self.ident)
            self.closed = True
        return self.common.DefSubclassProc(hwnd, msg, wp, lp)

    def poll(self):
        if self.closed:
            return
        try:
            paths = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.callback(paths)
        self.root.after(100, self.poll)

    def close(self):
        if not self.closed:
            self.shell.DragAcceptFiles(self.hwnd, False)
            self.common.RemoveWindowSubclass(self.hwnd, self.proc, self.ident)
            self.closed = True

    def set_enabled(self, enabled):
        if not self.closed:
            self.shell.DragAcceptFiles(self.hwnd, bool(enabled))
