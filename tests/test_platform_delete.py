import ctypes as c
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from core import Manager, ModError, layout_from_exe, cars_from_exe
from discovery import discover
from windows_recycle import FileOperation, recycle_file
from app import Application


class PlatformDeleteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.mods = self.root / 'mods'
        self.mods.mkdir()
        self.manager = Manager(self.mods)

    def tearDown(self):
        self.tmp.cleanup()

    def make_exe(self, folder):
        folder.mkdir(parents=True)
        exe = folder / 'forzahorizon6.exe'
        exe.write_bytes(b'test fixture only')
        return exe

    def test_steam_root_layout_has_no_content_layer(self):
        root = self.root / 'Steam/steamapps/common/Forza Horizon 6'
        exe = self.make_exe(root)
        layout = layout_from_exe(exe)
        self.assertEqual(layout.platform, 'steam')
        self.assertEqual(layout.mods, root / 'mediapc/cars')
        self.assertEqual(layout.vehicles, root / 'media/cars')
        self.assertEqual(cars_from_exe(exe), root / 'mediapc/cars')
        self.assertTrue(layout.mods.is_dir())
        self.assertFalse((root / 'Content').exists())

    def test_xbox_content_layout(self):
        root = self.root / 'XboxGames/Forza Horizon 6'
        exe = self.make_exe(root / 'Content')
        layout = layout_from_exe(exe)
        self.assertEqual(layout.platform, 'xbox')
        self.assertEqual(cars_from_exe(exe), root / 'Content/mediapc/Cars')
        self.assertEqual(layout.vehicles, root / 'Content/media/cars')
        self.assertFalse((root / 'mediapc').exists())

    def test_secondary_steam_library_and_xbox_are_both_discovered(self):
        primary = self.root / 'Steam'
        (primary / 'steamapps').mkdir(parents=True)
        library = self.root / 'SecondSteamLibrary'
        steam = self.make_exe(library / 'steamapps/common/Forza Horizon 6')
        xbox = self.make_exe(self.root / 'XboxGames/Forza Horizon 6/Content')
        escaped = str(library).replace('\\', '\\\\')
        (primary / 'steamapps/libraryfolders.vdf').write_text('"1" { "path" "' + escaped + '" }')
        with patch('discovery.default_paths', return_value=([], [])), patch('discovery.running_exes', return_value=[]), patch('discovery.registry_paths', return_value=([xbox.parent.parent], [primary])):
            found = discover()
        self.assertCountEqual(found, [steam, xbox])
        self.assertEqual(layout_from_exe(steam).label, 'Steam 版')
        self.assertEqual(layout_from_exe(xbox).label, 'Xbox 版')

    def test_steam_manual_mod_directory_infers_vehicle_catalog(self):
        exe = self.make_exe(self.root / 'Steam/steamapps/common/Forza Horizon 6')
        manager = Manager(cars_from_exe(exe))
        self.assertEqual(manager.vehicles, exe.parent / 'media/cars')

    def test_default_locations_include_another_installed_game_and_deduplicate(self):
        # Reproduce a PC with a saved game plus another install on a local drive.
        saved = self.make_exe(self.root / 'Saved/Content')
        installed = self.make_exe(self.root / 'OtherDrive/XboxGames/Forza Horizon 6/Content')
        steam_root = self.root / 'ProgramFiles/Steam'
        steam = self.make_exe(steam_root / 'steamapps/common/Forza Horizon 6')
        with patch('discovery.running_exes', return_value=[]), \
                patch('discovery.registry_paths', return_value=([], [])), \
                patch('discovery.default_paths', return_value=(
                    [installed.parent.parent, saved.parent.parent], [steam_root])):
            found = discover(str(saved))
        self.assertCountEqual(found, [saved, installed, steam])
        self.assertFalse((installed.parent / 'mediapc').exists())

    def fake_recycle(self, path):
        trash = self.root / 'test_recycle_bin'
        trash.mkdir(exist_ok=True)
        path.rename(trash / path.name)

    def test_delete_active_leaves_disabled_versions_and_originals(self):
        active = self.mods / 'CAR.zip'
        active.write_bytes(b'active')
        disabled = self.mods / 'CAR__fh6mm_v1.zipdisabled'
        disabled.write_bytes(b'disabled')
        original = self.root / 'original.zip'
        original.write_bytes(b'original')
        self.manager.delete(active.name, recycler=self.fake_recycle)
        self.assertFalse(active.exists())
        self.assertEqual(disabled.read_bytes(), b'disabled')
        self.assertFalse(any(m.enabled for m in self.manager.scan()))
        self.assertEqual(original.read_bytes(), b'original')
        self.assertEqual((self.root / 'test_recycle_bin/CAR.zip').read_bytes(), b'active')

    def test_delete_disabled_leaves_active_unchanged(self):
        (self.mods / 'CAR.zip').write_bytes(b'active')
        (self.mods / 'CAR__fh6mm_v1.zipdisabled').write_bytes(b'disabled')
        self.manager.delete('CAR__fh6mm_v1.zipdisabled', recycler=self.fake_recycle)
        self.assertEqual((self.mods / 'CAR.zip').read_bytes(), b'active')

    def test_recycle_failure_does_not_fall_back_to_unlink(self):
        p = self.mods / 'CAR.zip'
        p.write_bytes(b'keep')
        with self.assertRaises(OSError):
            self.manager.delete(p.name, recycler=Mock(side_effect=OSError('cancelled')))
        self.assertEqual(p.read_bytes(), b'keep')

    def test_changed_selection_is_not_deleted(self):
        p = self.mods / 'CAR.zip'
        p.write_bytes(b'old')
        record = self.manager.get(p.name)
        p.write_bytes(b'new and longer')
        recycler = Mock()
        with self.assertRaises(ModError):
            self.manager.delete(p.name, recycler=recycler, expected=(record.size, record.modified))
        recycler.assert_not_called()

    def test_delete_requires_listed_file_and_no_pending_transaction(self):
        recycler = Mock()
        for name in ('../outside.zip', 'readme.txt', 'missing.zip'):
            with self.assertRaises(ModError):
                self.manager.delete(name, recycler=recycler)
        (self.mods / 'CAR.zip').write_bytes(b'keep')
        self.manager.journal.write_text('{}')
        with self.assertRaises(ModError):
            self.manager.delete('CAR.zip', recycler=recycler)
        recycler.assert_not_called()

    def test_windows_shell_receives_one_absolute_double_null_path(self):
        p = self.mods / '中文 CAR.zip'
        p.write_bytes(b'keep')
        shell = Mock()
        def call(pointer):
            operation = c.cast(pointer, c.POINTER(FileOperation)).contents
            expected = str(p.absolute()) + '\0\0'
            self.assertEqual(c.wstring_at(operation.pFrom, len(expected)), expected)
            self.assertEqual(operation.wFunc, 3)
            self.assertTrue(operation.fFlags & 0x0040)
            self.assertTrue(operation.fFlags & 0x4000)
            self.assertTrue(operation.fFlags & 0x1000)
            return 0
        shell.SHFileOperationW.side_effect = call
        recycle_file(p, shell=shell)

    def test_shell_aborted_flag_is_not_success(self):
        p = self.mods / 'CAR.zip'
        p.write_bytes(b'keep')
        shell = Mock()
        def abort(pointer):
            c.cast(pointer, c.POINTER(FileOperation)).contents.fAnyOperationsAborted = 1
            return 0
        shell.SHFileOperationW.side_effect = abort
        with self.assertRaises(OSError):
            recycle_file(p, shell=shell)
        self.assertEqual(p.read_bytes(), b'keep')

    def test_delete_button_cannot_bypass_game_lock(self):
        app = Application.__new__(Application)
        app.can_edit = Mock(return_value=False)
        app.manager = Mock()
        app.delete_selected()
        app.manager.delete.assert_not_called()


if __name__ == '__main__':
    unittest.main()
