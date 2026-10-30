"""Regression coverage for interrupted tweens, real import progress and OLE policy."""
import ctypes as c
import queue
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import animation
from animation import Animator
from core import Manager
from windows_ole_drop import OleDrop, POINTL, FORMATETC, STGMEDIUM


class AnimatorTests(unittest.TestCase):
    def setUp(self):
        self.scheduler = Mock()
        self.scheduler.after.return_value = 'job'
        self.anim = Animator(self.scheduler)
        animation.set_enabled(True)
        self.addCleanup(animation.set_enabled, True)

    def test_replaced_tween_is_not_deleted_by_old_completion(self):
        old_done = Mock()
        with patch('animation.perf_counter', return_value=0):
            self.anim.to('page', 1, 100, start=0, done=old_done)
        def replace_during_final_frame():
            self.anim.to('page', 2, 100)
        self.anim.on_frame = replace_during_final_frame
        with patch('animation.perf_counter', return_value=.2):
            self.anim._step()
        self.assertTrue(self.anim.active('page'))
        old_done.assert_not_called()

    def test_disabled_animation_finishes_once_without_timer(self):
        animation.set_enabled(False)
        finished = Mock()
        self.anim.to('exit', 1, 210, start=0, done=finished)
        self.assertEqual(self.anim.get('exit'), 1)
        self.assertFalse(self.anim.active())
        self.scheduler.after.assert_not_called()
        finished.assert_called_once()

    def run_frames(self, until, start=0.0, step=1/60):
        now = start
        while now < until:
            now += step
            with patch('animation.perf_counter', return_value=now):
                self.anim._step()
        return now

    def test_additive_tweens_overlap_and_sum(self):
        from animation import linear
        self.anim.set('y', 0.0)
        with patch('animation.perf_counter', return_value=0):
            self.anim.add('y', 100, 300, linear)
        now = self.run_frames(.1)
        with patch('animation.perf_counter', return_value=now):
            self.anim.add('y', 100, 300, linear)  # a second wheel notch mid-flight
        self.assertTrue(self.anim.active('y'))
        self.run_frames(1.0, now)
        self.assertAlmostEqual(self.anim.get('y'), 200)
        self.assertFalse(self.anim.active())

    def test_stalled_frame_resumes_instead_of_jumping(self):
        from animation import linear
        with patch('animation.perf_counter', return_value=0):
            self.anim.to('x', 1.0, 200, linear, start=0.0)
        with patch('animation.perf_counter', return_value=.5):  # UI thread blocked for 500 ms
            self.anim._step()
        self.assertAlmostEqual(self.anim.get('x'), animation.MAX_STEP / .2)

    def test_retarget_starts_from_value_on_screen(self):
        from animation import linear
        with patch('animation.perf_counter', return_value=0):
            self.anim.to('x', 1.0, 200, linear, start=0.0)
        now = self.run_frames(.1)
        shown = self.anim.get('x')
        with patch('animation.perf_counter', return_value=now):
            self.anim.to('x', 0.0, 200, linear)
            self.anim._step()
        self.assertAlmostEqual(self.anim.get('x'), shown)

    def test_preview_loader_close_drops_backlog_and_waits_for_open_file(self):
        import threading, time as clock
        from mod_grid import PreviewLoader
        loader = PreviewLoader((32, 18))
        started, decoded = threading.Event(), []
        def slow(path, size):
            started.set(); clock.sleep(.2); decoded.append(path)
            return b''
        with patch.object(PreviewLoader, 'decode', side_effect=slow):
            for i in range(5):
                loader.request(('k', i), f'p{i}')
            self.assertTrue(started.wait(1))
            loader.close()
        self.assertFalse(loader.thread.is_alive())  # the file being read was released
        self.assertEqual(decoded, ['p0'])          # queued requests were not decoded

    def test_unchanged_widget_options_are_not_reapplied(self):
        from app import update_widget
        widget = Mock(); widget.cget.side_effect = {'state': 'disabled', 'text': 'A'}.get
        update_widget(widget, state='disabled', text='A')
        widget.configure.assert_not_called()
        update_widget(widget, state='normal', text='A')
        widget.configure.assert_called_once_with(state='normal')


class ImportProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mods, self.base, self.downloads = [self.root / n for n in ('mods', 'base', 'downloads')]
        for p in (self.mods, self.base, self.downloads): p.mkdir()
        (self.base / 'CAR.zip').write_bytes(b'base')
        self.manager = Manager(self.mods, self.base)
        self.source = self.downloads / 'CAR.zip'
        self.source.write_bytes(b'original mod bytes' * 80000)

    def test_byte_progress_preserves_content_and_all_three_stages(self):
        events = []
        result = self.manager.import_files([self.source], progress=lambda *event: events.append(event))
        self.assertEqual(result['imported'], ['CAR.zip'])
        self.assertEqual(self.source.read_bytes(), (self.mods/'CAR.zip').read_bytes())
        self.assertEqual({e[-1] for e in events}, {'hash', 'copy', 'verify', 'done'})
        self.assertEqual([e[0] for e in events], sorted(e[0] for e in events))
        self.assertEqual(events[-1][0], events[-1][1])
        self.assertEqual(events[-1][1], self.source.stat().st_size * 3)
        self.assertFalse(list(self.mods.glob('.fh6mm-import-*')))

    def test_rejected_and_skipped_files_advance_processed_batch_without_install(self):
        invalid = self.downloads/'WRONG.zip'; invalid.write_bytes(b'invalid')
        installed = self.mods/'CAR.zip'; installed.write_bytes(b'existing')
        events = []
        result = self.manager.import_files([invalid, installed], progress=lambda *event: events.append(event))
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(len(result['skipped']), 1)
        self.assertFalse(result['imported'])
        self.assertEqual(events[-1][0], events[-1][1])
        self.assertEqual(installed.read_bytes(), b'existing')

    def test_progress_copy_failure_cleans_partial_file(self):
        import os
        original = os.fdopen
        class FailingOutput:
            def __init__(self, out): self.out = out
            def __enter__(self): return self
            def __exit__(self, *args): self.out.close()
            def write(self, block):
                self.out.write(block[:100])
                raise OSError('simulated disk failure')
        with patch('core.os.fdopen', side_effect=lambda *a, **kw: FailingOutput(original(*a, **kw))):
            result = self.manager.import_files([self.source], progress=lambda *args: None)
        self.assertEqual(len(result['errors']), 1)
        self.assertFalse(result['imported'])
        self.assertFalse((self.mods/'CAR.zip').exists())
        self.assertFalse(list(self.mods.glob('.fh6mm-import-*')))
        self.assertTrue(self.source.is_file())


class NativeDropTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.a = self.root/'A.zip'; self.a.write_bytes(b'mod')
        self.drop = OleDrop.__new__(OleDrop)
        self.drop.events = queue.Queue()
        self.drop.enabled, self.drop.closed = True, False
        self.drop.paths, self.drop.zip_count, self.drop.accepted = [], 0, False
        self.drop._feedback, self.drop._job = None, None
        self.drop.root, self.drop.callback, self.drop.on_drag = Mock(), Mock(), Mock()
        self.drop._read_paths = Mock(return_value=[str(self.a)])
        self.effect = c.pointer(c.c_uint32(3))

    def enter(self):
        self.effect[0] = 3
        self.drop._enter(None, None, 0, POINTL(), self.effect)

    def test_enter_leave_feedback_and_copy_only(self):
        self.enter()
        self.assertEqual(self.effect[0], 1)
        self.drop.poll()
        self.drop.on_drag.assert_called_with(True, True, 1)
        self.drop._leave(None); self.drop.poll()
        self.drop.on_drag.assert_called_with(False, False, 0)
        self.drop.callback.assert_not_called()

    def test_directory_named_zip_is_not_accepted(self):
        folder = self.root/'folder.zip'; folder.mkdir()
        self.drop._read_paths.return_value = [str(folder)]
        self.enter(); self.drop.poll()
        self.assertEqual(self.effect[0], 0)
        self.drop.on_drag.assert_called_with(True, False, 0)

    def test_drop_reads_current_paths_and_preserves_sources(self):
        self.enter()
        b = self.root/'B.zip'; b.write_bytes(b'other')
        self.drop._read_paths.return_value = [str(b)]
        self.drop._drop(None, None, 0, POINTL(), self.effect)
        self.drop.poll()
        self.drop.callback.assert_called_once_with([str(b)])
        self.assertEqual(self.a.read_bytes(), b'mod')
        self.assertEqual(b.read_bytes(), b'other')

    def test_lock_discards_pending_drop_and_removes_feedback(self):
        self.enter()
        self.drop._drop(None, None, 0, POINTL(), self.effect)
        self.drop.set_enabled(False)
        self.drop.set_enabled(True)
        self.drop.poll()
        self.drop.callback.assert_not_called()
        self.drop.on_drag.assert_called_with(False, False, 0)

    def test_move_only_source_is_not_accepted(self):
        self.enter()
        self.effect[0] = 2
        self.drop._over(None, 0, POINTL(), self.effect)
        self.drop.poll()
        self.assertEqual(self.effect[0], 0)
        self.drop.on_drag.assert_called_with(True, False, 1)

    def test_legacy_backend_also_discards_queued_drop_on_lock(self):
        from windows_drop import LegacyWindowsDrop
        drop = LegacyWindowsDrop.__new__(LegacyWindowsDrop)
        drop.events = queue.Queue(); drop.events.put([str(self.a)])
        drop.closed, drop.enabled = False, True
        drop.shell, drop.root, drop.callback = Mock(), Mock(), Mock()
        drop.hwnd = 123
        drop.set_enabled(False); drop.set_enabled(True); drop.poll()
        drop.callback.assert_not_called()

    def test_data_object_uses_expected_abi_and_releases_medium(self):
        d = OleDrop.__new__(OleDrop)
        d.call = getattr(c, 'WINFUNCTYPE', c.CFUNCTYPE)
        d.ole, d.shell = Mock(), Mock()
        seen = []
        def query(this, fmt):
            seen.append((fmt.contents.cfFormat, fmt.contents.dwAspect, fmt.contents.lindex, fmt.contents.tymed))
            return 0
        def get(this, fmt, medium):
            medium.contents.tymed = 1
            medium.contents.handle = 123
            return 0
        query_cb = d.call(c.c_int32, c.c_void_p, c.POINTER(FORMATETC))(query)
        get_cb = d.call(c.c_int32, c.c_void_p, c.POINTER(FORMATETC), c.POINTER(STGMEDIUM))(get)
        table = (c.c_void_p*6)()
        table[3], table[5] = c.cast(get_cb,c.c_void_p), c.cast(query_cb,c.c_void_p)
        obj = (c.c_void_p*1)(c.addressof(table))
        def paths(handle, index, buffer, size):
            if index == 0xffffffff: return 1
            if buffer is not None: buffer.value = str(self.a)
            return len(str(self.a))
        d.shell.DragQueryFileW.side_effect = paths
        self.assertEqual(d._read_paths(c.addressof(obj)), [str(self.a)])
        self.assertEqual(seen, [(15,1,-1,1)])
        self.assertEqual(c.sizeof(POINTL), 8)
        d.ole.ReleaseStgMedium.assert_called_once()


if __name__ == '__main__':
    unittest.main()
