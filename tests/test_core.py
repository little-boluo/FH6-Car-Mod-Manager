import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import core
from core import Manager, ModError, cars_from_exe, parse_filename, sha256
from discovery import discover, find_in_install, steam_libraries, vdf_value


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.cars = self.base / 'Cars'
        self.cars.mkdir()
        self.vehicles = self.base / 'Content' / 'media' / 'cars'
        self.vehicles.mkdir(parents=True)
        (self.vehicles / 'CAR.zip').write_bytes(b'base game vehicle')
        self.m = Manager(self.cars, self.vehicles)

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, parent, name='CAR.zip', value=b'variant'):
        p = self.base / parent / name
        p.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('car/data.bin', value)
        return p

    def existing(self, name, value=b'zip bytes'):
        p = self.cars / name
        p.write_bytes(value)
        return p

    def contents(self):
        return sorted(p.read_bytes() for p in self.cars.iterdir() if parse_filename(p.name))

    def test_parse_names(self):
        self.assertEqual(parse_filename('CAR.zip'), ('CAR', 0, True))
        self.assertEqual(parse_filename('CAR.zipdisabled'), ('CAR', 0, False))
        self.assertEqual(parse_filename('CAR__fh6mm_v12.zipdisabled'), ('CAR', 12, False))
        self.assertEqual(parse_filename('车名.ZIPDISABLED'), ('车名', 0, False))
        self.assertEqual(parse_filename('CAR_v2.zip'), ('CAR_v2', 0, True))
        self.assertIsNone(parse_filename('CAR.zip.bak'))

    def test_scan_existing_files_directly(self):
        self.existing('A.zip')
        self.existing('B.zipdisabled')
        self.existing('notes.txt')
        (self.cars / 'subfolder.zip').mkdir()
        self.assertEqual([r.filename for r in self.m.scan()], ['A.zip', 'B.zipdisabled'])

    def test_zip_import_is_byte_identical_and_not_extracted(self):
        source = self.source('downloads')
        before = source.read_bytes()
        result = self.m.import_files([source])
        self.assertEqual(result['imported'], ['CAR.zip'])
        self.assertEqual((self.cars / 'CAR.zip').read_bytes(), before)
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse((self.cars / 'car').exists())

    def test_same_name_batch_only_first_is_active(self):
        paths = [self.source(f'd{i}', value=bytes([i])) for i in range(3)]
        result = self.m.import_files(paths)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['imported'], ['CAR.zip', 'CAR__fh6mm_v1.zipdisabled', 'CAR__fh6mm_v2.zipdisabled'])
        self.assertEqual(sum(m.enabled for m in self.m.scan()), 1)
        self.assertEqual(self.contents(), sorted(p.read_bytes() for p in paths))

    def test_suffix_is_transferred_when_switching(self):
        a = self.source('a', value=b'A')
        b = self.source('b', value=b'B')
        self.m.import_files([a, b])
        self.m.enable('CAR__fh6mm_v1.zipdisabled')
        self.assertEqual((self.cars / 'CAR.zip').read_bytes(), b.read_bytes())
        self.assertEqual((self.cars / 'CAR__fh6mm_v1.zipdisabled').read_bytes(), a.read_bytes())
        self.m.enable('CAR__fh6mm_v1.zipdisabled')
        self.assertEqual((self.cars / 'CAR.zip').read_bytes(), a.read_bytes())
        self.assertEqual((self.cars / 'CAR__fh6mm_v1.zipdisabled').read_bytes(), b.read_bytes())

    def test_third_variant_switch_preserves_other_disabled_copy(self):
        paths = [self.source(f'd{i}', value=bytes([i])) for i in range(3)]
        self.m.import_files(paths)
        other = (self.cars / 'CAR__fh6mm_v1.zipdisabled').read_bytes()
        self.m.enable('CAR__fh6mm_v2.zipdisabled')
        self.assertEqual((self.cars / 'CAR.zip').read_bytes(), paths[2].read_bytes())
        self.assertEqual((self.cars / 'CAR__fh6mm_v2.zipdisabled').read_bytes(), paths[0].read_bytes())
        self.assertEqual((self.cars / 'CAR__fh6mm_v1.zipdisabled').read_bytes(), other)

    def test_enable_disable_changes_extension_only(self):
        original = self.existing('CAR.zip', b'exact bytes')
        stamp = original.stat().st_mtime_ns
        target = self.m.disable('CAR.zip')
        self.assertEqual(target, 'CAR.zipdisabled')
        self.assertEqual((self.cars / target).stat().st_mtime_ns, stamp)
        self.m.enable(target)
        self.assertEqual(original.read_bytes(), b'exact bytes')

    def test_disable_collision_gets_unique_suffix(self):
        self.existing('CAR.zip', b'active')
        self.existing('CAR.zipdisabled', b'disabled')
        self.assertEqual(self.m.disable('CAR.zip'), 'CAR__fh6mm_v1.zipdisabled')
        self.assertEqual(self.contents(), [b'active', b'disabled'])

    def test_all_disabled_group_stays_disabled_on_new_import(self):
        self.existing('CAR.zipdisabled', b'old')
        result = self.m.import_files([self.source('d')])
        self.assertEqual(result['imported'], ['CAR__fh6mm_v1.zipdisabled'])
        self.assertEqual(sum(m.enabled for m in self.m.scan()), 0)

    def test_case_insensitive_same_name_import(self):
        self.existing('Car.zip', b'old')
        self.m.import_files([self.source('d', name='CAR.ZIP')])
        self.assertEqual([m.filename for m in self.m.scan()], ['Car.zip', 'Car__fh6mm_v1.zipdisabled'])

    def test_preexisting_multiple_active_versions_can_be_normalized(self):
        self.existing('CAR.zip', b'A')
        self.existing('CAR__fh6mm_v1.zip', b'B')
        self.existing('CAR__fh6mm_v2.zipdisabled', b'C')
        self.m.enable('CAR__fh6mm_v1.zip')
        self.assertEqual((self.cars / 'CAR.zip').read_bytes(), b'B')
        self.assertEqual(sum(m.enabled for m in self.m.scan()), 1)
        self.assertEqual(self.contents(), [b'A', b'B', b'C'])

    def test_import_from_target_folder_is_skipped(self):
        p = self.existing('CAR.zip')
        result = self.m.import_files([p])
        self.assertEqual(len(result['skipped']), 1)
        self.assertEqual(len(self.m.scan()), 1)

    def test_invalid_input_does_not_block_other_valid_files(self):
        source = self.source('d')
        invalid = self.base / 'readme.txt'
        invalid.write_text('not zip')
        result = self.m.import_files([invalid, source])
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(result['imported'], ['CAR.zip'])

    def test_copy_failure_does_not_leave_partial_zip(self):
        source = self.source('d')
        with patch('core.shutil.copyfileobj', side_effect=OSError('disk full')):
            result = self.m.import_files([source])
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(self.m.scan(), [])
        self.assertEqual(list(self.cars.glob('*.tmp')), [])
        self.assertTrue(source.exists())

    def test_collect_and_distribute_crash_recovery_every_move(self):
        # Two-file swap: interrupt after each of the four successful renames.
        for failure in range(1, 5):
            with self.subTest(failure=failure):
                folder = self.base / f'crash{failure}'
                folder.mkdir()
                (folder / 'CAR.zip').write_bytes(b'A')
                (folder / 'CAR__fh6mm_v1.zipdisabled').write_bytes(b'B')
                manager = Manager(folder)
                original = manager.move
                count = [0]
                def crash(source, target):
                    original(source, target)
                    count[0] += 1
                    if count[0] == failure:
                        raise KeyboardInterrupt('simulated crash')
                with patch.object(manager, 'move', side_effect=crash):
                    with self.assertRaises(KeyboardInterrupt):
                        manager.enable('CAR__fh6mm_v1.zipdisabled')
                restarted = Manager(folder, self.vehicles)
                self.assertTrue(restarted.journal.exists())
                with self.assertRaises(ModError):
                    restarted.import_files([self.source(f'source{failure}')])
                restarted.recover()
                self.assertEqual((folder / 'CAR.zip').read_bytes(), b'B')
                self.assertEqual((folder / 'CAR__fh6mm_v1.zipdisabled').read_bytes(), b'A')
                self.assertFalse(restarted.journal.exists())

    def test_recovery_blocks_external_conflict(self):
        self.existing('CAR.zip', b'A')
        self.existing('CAR__fh6mm_v1.zipdisabled', b'B')
        original = self.m.move
        def crash(source, target):
            original(source, target)
            raise KeyboardInterrupt()
        with patch.object(self.m, 'move', side_effect=crash):
            with self.assertRaises(KeyboardInterrupt):
                self.m.enable('CAR__fh6mm_v1.zipdisabled')
        tx = json.loads(self.m.journal.read_text())
        source = tx['files'][0]['source']
        self.existing(source, b'external file')
        with self.assertRaises(ModError):
            self.m.recover()
        self.assertEqual((self.cars / source).read_bytes(), b'external file')
        self.assertTrue(self.m.journal.exists())

    def test_game_directory_created_relative_to_executable(self):
        content = self.base / 'Forza Horizon 6' / 'Content'
        content.mkdir(parents=True)
        exe = content / 'forzahorizon6.exe'
        exe.write_bytes(b'test only')
        folder = cars_from_exe(exe)
        self.assertEqual(folder, content / 'mediapc' / 'Cars')
        self.assertTrue(folder.is_dir())
        self.assertFalse((content / 'Content').exists())

    def test_missing_exe_does_not_create_directory(self):
        exe = self.base / 'missing' / 'forzahorizon6.exe'
        with self.assertRaises(ModError):
            cars_from_exe(exe)
        self.assertFalse(exe.parent.exists())

    def test_discover_content_and_saved_paths(self):
        content = self.base / 'Forza Horizon 6' / 'Content'
        content.mkdir(parents=True)
        exe = content / 'forzahorizon6.exe'
        exe.write_bytes(b'test only')
        with patch('discovery.default_paths', return_value=([], [])), patch('discovery.running_exes', return_value=[]), patch('discovery.registry_paths', return_value=([], [])):
            result = discover(str(exe), [content.parent])
        self.assertEqual(result, [exe])
        self.assertFalse((content / 'mediapc').exists())

    def test_steam_vdf_paths_keep_unicode(self):
        root = self.base / 'Steam'
        (root / 'steamapps').mkdir(parents=True)
        (root / 'steamapps/libraryfolders.vdf').write_text('"libraryfolders" { "1" { "path" "D:\\\\游戏\\\\SteamLibrary" } }', encoding='utf-8')
        libs = steam_libraries(root)
        self.assertEqual(str(libs[1]), 'D:\\游戏\\SteamLibrary')
        self.assertEqual(vdf_value('"installdir" "Forza Horizon 6"', 'installdir'), 'Forza Horizon 6')

    def test_occupied_non_zip_target_never_overwritten(self):
        # A directory occupying the canonical ZIP name is not a mod, but still blocks it.
        (self.cars / 'CAR.zip').mkdir()
        result = self.m.import_files([self.source('d')])
        self.assertEqual(result['imported'], ['CAR__fh6mm_v1.zipdisabled'])
        with self.assertRaises(ModError):
            self.m.enable(result['imported'][0])
        self.assertTrue((self.cars / 'CAR.zip').is_dir())


if __name__ == '__main__':
    unittest.main()
