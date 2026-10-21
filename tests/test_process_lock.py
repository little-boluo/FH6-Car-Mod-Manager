import ctypes as c
import queue
import unittest
from unittest.mock import Mock, patch

from app import Application
from process_watch import ProcessEntry, snapshot_names, game_is_running


class ProcessDetectionTests(unittest.TestCase):
    def fake_kernel(self, names, terminal_error=18):
        kernel = Mock()
        kernel.CreateToolhelp32Snapshot.return_value = 1234
        iterator = iter(names)
        def next_entry(handle, pointer):
            try:
                name = next(iterator)
            except StopIteration:
                return 0
            entry = c.cast(pointer, c.POINTER(ProcessEntry)).contents
            self.assertEqual(entry.dwSize, c.sizeof(ProcessEntry))
            entry.szExeFile = name
            return 1
        kernel.Process32FirstW.side_effect = next_entry
        kernel.Process32NextW.side_effect = next_entry
        return kernel, lambda: terminal_error

    def test_enumeration_needs_names_not_full_paths(self):
        kernel, error = self.fake_kernel(['System', 'ForzaHorizon6.EXE', 'explorer.exe'])
        self.assertEqual(snapshot_names(kernel, error), ['System', 'ForzaHorizon6.EXE', 'explorer.exe'])
        kernel.CloseHandle.assert_called_once_with(1234)

    def test_exact_case_insensitive_game_name(self):
        with patch('process_watch.os.name', 'nt'), patch('process_watch.snapshot_names', return_value=['FORZAHORIZON6.EXE']):
            self.assertTrue(game_is_running())
        with patch('process_watch.os.name', 'nt'), patch('process_watch.snapshot_names', return_value=['ForzaHorizon5.exe', 'forzahorizon6.exe.helper']):
            self.assertFalse(game_is_running())

    def test_snapshot_error_is_not_reported_as_game_exit(self):
        kernel, error = self.fake_kernel([], 5)
        kernel.CreateToolhelp32Snapshot.return_value = c.c_void_p(-1).value
        with self.assertRaises(OSError):
            snapshot_names(kernel, error)
        kernel.CloseHandle.assert_not_called()

    def test_partial_enumeration_failure_closes_handle_and_raises(self):
        kernel, error = self.fake_kernel(['explorer.exe'], 5)
        with self.assertRaises(OSError):
            snapshot_names(kernel, error)
        kernel.CloseHandle.assert_called_once_with(1234)


class InterfaceLockTests(unittest.TestCase):
    def setUp(self):
        self.app = Application.__new__(Application)
        a = self.app
        a.busy = False
        a.game_running = None
        a.game_error = ''
        a.buttons = [Mock() for _ in range(10)]
        for button in a.buttons:
            button.winfo_exists.return_value = True
        a.search_entry, a.tree, a.drop = Mock(), Mock(), Mock()
        a.drop_title, a.game_status, a.game_label = Mock(), Mock(), Mock()
        a.pending_drops = []
        a.root, a.status, a.progress = Mock(), Mock(), Mock()
        a.jobs = queue.Queue()
        a.refresh, a.log, a.error = Mock(), Mock(), Mock()

    def assert_buttons(self, state):
        for b in self.app.buttons:
            self.assertEqual(b.configure.call_args.kwargs['state'], state)

    def test_running_locks_every_button_search_tree_and_drop(self):
        self.app.apply_game_state(True)
        self.assert_buttons('disabled')
        self.app.search_entry.configure.assert_called_with(state='disabled')
        self.app.tree.state.assert_called_with(['disabled'])
        self.app.drop.set_enabled.assert_called_with(False)
        self.assertEqual(self.app.block_locked_input(), 'break')

    def test_exit_unlocks_controls(self):
        self.app.apply_game_state(True)
        self.app.apply_game_state(False)
        self.assert_buttons('normal')
        self.app.drop.set_enabled.assert_called_with(True)
        self.assertIsNone(self.app.block_locked_input())

    def test_game_exit_during_job_does_not_unlock_busy_controls(self):
        self.app.busy = True
        self.app.apply_game_state(False)
        self.assert_buttons('disabled')

    def test_unknown_state_keeps_controls_locked(self):
        with patch('app.game_is_running', side_effect=OSError('cannot enumerate')):
            self.app.probe_game()
        self.assertIsNone(self.app.game_running)
        self.assert_buttons('disabled')

    def test_running_discards_queued_drops(self):
        self.app.pending_drops = ['A.zip']
        self.app.apply_game_state(True)
        self.assertEqual(self.app.pending_drops, [])
        with patch('app.game_is_running', return_value=True):
            self.app.on_drop(['B.zip'])
        self.assertEqual(self.app.pending_drops, [])

    def test_action_boundary_rechecks_cached_stopped_state(self):
        self.app.game_running = False
        with patch('app.game_is_running', return_value=True):
            self.assertFalse(self.app.can_edit())
        self.assert_buttons('disabled')

    def test_file_worker_guard_blocks_operation(self):
        fn = Mock()
        with patch('app.game_is_running', return_value=True):
            with self.assertRaises(Exception):
                self.app.guard_game(fn)
        fn.assert_not_called()

    def test_job_completion_cannot_unlock_running_game(self):
        self.app.busy = True
        self.app.jobs.put((None, None, None))
        with patch('app.game_is_running', return_value=True):
            self.app.poll()
        self.assertFalse(self.app.busy)
        self.assertTrue(self.app.game_running)
        self.assert_buttons('disabled')

    def test_path_selection_does_not_create_folder_while_running(self):
        with patch('app.game_is_running', return_value=True), patch('app.cars_from_exe') as create:
            self.app.attach_exe('forzahorizon6.exe')
        create.assert_not_called()


if __name__ == '__main__':
    unittest.main()
