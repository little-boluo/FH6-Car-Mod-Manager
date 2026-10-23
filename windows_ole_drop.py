"""ctypes IDropTarget for real Explorer enter/leave feedback; no tkdnd runtime."""
import ctypes as c
import os
from pathlib import Path
import queue
import uuid


class POINTL(c.Structure):
    _fields_ = [('x', c.c_int32), ('y', c.c_int32)]


class FORMATETC(c.Structure):
    _fields_ = [('cfFormat', c.c_uint16), ('ptd', c.c_void_p), ('dwAspect', c.c_uint32),
                ('lindex', c.c_int32), ('tymed', c.c_uint32)]


class STGMEDIUM(c.Structure):
    _fields_ = [('tymed', c.c_uint32), ('handle', c.c_void_p), ('pUnkForRelease', c.c_void_p)]


class OleDrop:
    def __init__(self, root, callback, on_drag=None):
        if os.name != 'nt':
            raise OSError('Native file drop requires Windows')
        from ctypes import wintypes as w
        self.root, self.callback, self.on_drag = root, callback, on_drag
        self.events, self.closed, self.enabled = queue.Queue(), False, True
        self.paths, self._feedback, self._job = [], None, None
        self.zip_count, self.accepted = 0, False
        self._refs, self._registered, self._initialized = 1, False, False
        self.user = c.WinDLL('user32', use_last_error=True)
        self.shell = c.WinDLL('shell32', use_last_error=True)
        self.ole = c.WinDLL('ole32')
        self.ole.OleInitialize.argtypes, self.ole.OleInitialize.restype = [c.c_void_p], c.c_int32
        self.ole.OleUninitialize.argtypes, self.ole.OleUninitialize.restype = [], None
        self.ole.RegisterDragDrop.argtypes, self.ole.RegisterDragDrop.restype = [w.HWND, c.c_void_p], c.c_int32
        self.ole.RevokeDragDrop.argtypes, self.ole.RevokeDragDrop.restype = [w.HWND], c.c_int32
        self.ole.ReleaseStgMedium.argtypes, self.ole.ReleaseStgMedium.restype = [c.POINTER(STGMEDIUM)], None
        self.user.GetAncestor.argtypes, self.user.GetAncestor.restype = [w.HWND, w.UINT], w.HWND
        self.shell.DragQueryFileW.argtypes = [w.HANDLE, w.UINT, w.LPWSTR, w.UINT]
        self.shell.DragQueryFileW.restype = w.UINT
        self.call = c.WINFUNCTYPE
        hr, ptr, dword = c.c_int32, c.c_void_p, c.c_uint32
        effect = c.POINTER(dword)
        prototypes = [
            self.call(hr, ptr, ptr, c.POINTER(ptr)),  # QueryInterface
            self.call(dword, ptr), self.call(dword, ptr),
            self.call(hr, ptr, ptr, dword, POINTL, effect),
            self.call(hr, ptr, dword, POINTL, effect),
            self.call(hr, ptr),
            self.call(hr, ptr, ptr, dword, POINTL, effect),
        ]
        functions = (self._query, self._add_ref, self._release, self._enter,
                     self._over, self._leave, self._drop)
        self.callbacks = [proto(fn) for proto, fn in zip(prototypes, functions)]
        self.vtable = (ptr*7)(*(c.cast(fn, ptr).value for fn in self.callbacks))
        self.instance = (ptr*1)(c.addressof(self.vtable))
        self.pointer = c.cast(self.instance, ptr)
        root.update_idletasks()
        self.hwnd = self.user.GetAncestor(root.winfo_id(), 2) or root.winfo_id()
        try:
            result = self.ole.OleInitialize(None)
            if result < 0:
                raise OSError(f'OleInitialize: 0x{result & 0xffffffff:08X}')
            self._initialized = True
            result = self.ole.RegisterDragDrop(self.hwnd, self.pointer)
            if result < 0:
                raise OSError(f'RegisterDragDrop: 0x{result & 0xffffffff:08X}')
            self._registered = True
        except Exception:
            if self._initialized:
                self.ole.OleUninitialize()
                self._initialized = False
            raise
        self._job = root.after(16, self.poll)

    def _query(self, this, iid, out):
        if not out:
            return -2147467261  # E_POINTER
        out[0] = None
        supported = (uuid.UUID('00000000-0000-0000-c000-000000000046').bytes_le,
                     uuid.UUID('00000122-0000-0000-c000-000000000046').bytes_le)
        if iid and c.string_at(iid, 16) in supported:
            out[0] = self.pointer.value
            self._add_ref(this)
            return 0
        return -2147467262  # E_NOINTERFACE

    def _add_ref(self, this):
        self._refs += 1
        return self._refs

    def _release(self, this):
        self._refs = max(0, self._refs-1)
        return self._refs

    def _read_paths(self, data):
        if not data:
            return []
        fmt = FORMATETC(15, None, 1, -1, 1)  # CF_HDROP / DVASPECT_CONTENT / TYMED_HGLOBAL
        medium = STGMEDIUM()
        table = c.cast(data, c.POINTER(c.POINTER(c.c_void_p))).contents
        query = self.call(c.c_int32, c.c_void_p, c.POINTER(FORMATETC))(table[5])
        get = self.call(c.c_int32, c.c_void_p, c.POINTER(FORMATETC), c.POINTER(STGMEDIUM))(table[3])
        if query(data, c.byref(fmt)) < 0 or get(data, c.byref(fmt), c.byref(medium)) < 0:
            return []
        try:
            if medium.tymed != 1 or not medium.handle:
                return []
            count = self.shell.DragQueryFileW(medium.handle, 0xffffffff, None, 0)
            paths = []
            for i in range(count):
                size = self.shell.DragQueryFileW(medium.handle, i, None, 0)
                buf = c.create_unicode_buffer(size+1)
                self.shell.DragQueryFileW(medium.handle, i, buf, size+1)
                paths.append(buf.value)
            return paths
        finally:
            self.ole.ReleaseStgMedium(c.byref(medium))

    def _set_paths(self, paths):
        from core import regular
        self.paths, self.zip_count = list(paths), 0
        for path in self.paths:
            try:
                if Path(path).suffix.casefold() == '.zip' and regular(path):
                    self.zip_count += 1
            except OSError:
                pass

    def _feedback_event(self, active):
        hint = (active and self.enabled, self.accepted, self.zip_count)
        if hint != self._feedback:
            self._feedback = hint
            self.events.put(('hover', hint))

    def _set_effect(self, effect):
        self.accepted = bool(effect and effect[0] & 1 and not self.closed and self.enabled and self.zip_count)
        if effect:
            effect[0] = 1 if self.accepted else 0  # COPY only; never MOVE originals.

    def _enter(self, this, data, keys, point, effect):
        try:
            self._set_paths(self._read_paths(data))
        except Exception:
            self._set_paths([])
        self._set_effect(effect)
        self._feedback_event(True)
        return 0

    def _over(self, this, keys, point, effect):
        self._set_effect(effect)
        self._feedback_event(True)
        return 0

    def _leave(self, this):
        self._set_paths([])
        self.accepted = False
        self._feedback_event(False)
        return 0

    def _drop(self, this, data, keys, point, effect):
        try:
            self._set_paths(self._read_paths(data))
            self._set_effect(effect)
            if effect and effect[0]:
                self.events.put(('drop', list(self.paths)))
        except Exception:
            if effect:
                effect[0] = 0
        self._set_paths([])
        self.accepted = False
        self._feedback_event(False)
        return 0

    def poll(self):
        self._job = None
        if self.closed:
            return
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'hover' and self.on_drag:
                self.on_drag(*value)
            elif kind == 'drop' and self.enabled:
                self.callback(value)
        self._job = self.root.after(16, self.poll)

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        if not self.enabled:
            while True:
                try:
                    self.events.get_nowait()
                except queue.Empty:
                    break
            self.accepted = False
            self._set_paths([])
            self._feedback = None  # The previous feedback may have been discarded above.
            self._feedback_event(False)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self._job is not None:
            self.root.after_cancel(self._job)
            self._job = None
        if self._registered:
            self.ole.RevokeDragDrop(self.hwnd)
            self._registered = False
        if self._initialized:
            self.ole.OleUninitialize()
            self._initialized = False
