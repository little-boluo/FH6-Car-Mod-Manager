from pathlib import Path
import tempfile
import unittest

from core import Manager, ModError


class VehicleNameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.content = self.root / 'Forza Horizon 6' / 'Content'
        self.mods = self.content / 'mediapc' / 'Cars'
        self.original = self.content / 'media' / 'cars'
        self.mods.mkdir(parents=True)
        self.original.mkdir(parents=True)
        (self.original / 'POR_911_23.zip').write_bytes(b'original vehicle')
        self.m = Manager(self.mods)

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, name, folder='download'):
        p = self.root / folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'mod archive unchanged')
        return p

    def test_media_reference_is_inferred_from_mediapc(self):
        self.assertEqual(self.m.vehicles, self.original)
        self.assertNotEqual(self.m.vehicles, self.mods)

    def test_matching_name_imports_and_does_not_modify_reference(self):
        source = self.source('POR_911_23.zip')
        result = self.m.import_files([source])
        self.assertEqual(result['imported'], ['POR_911_23.zip'])
        self.assertEqual((self.original / source.name).read_bytes(), b'original vehicle')
        self.assertEqual(source.read_bytes(), b'mod archive unchanged')

    def test_names_that_do_not_start_with_a_car_are_rejected(self):
        # A different car, a longer word, a shorter name, the wrong extension or no separator.
        names = ['POR_911_24.zip', 'POR_911_234.zip', 'POR_911_2.zip', 'XPOR_911_23 (1).zip', 'POR_911_23A.zip']
        result = self.m.import_files([self.source(name) for name in names])
        self.assertEqual(result['imported'], [])
        self.assertEqual(len(result['errors']), len(names))
        self.assertEqual(self.m.scan(), [])

    def test_download_copies_and_suffixes_install_under_the_original_name(self):
        names = ['POR_911_23 (1).zip', 'POR_911_23(2).ZIP', 'POR_911_23 - 副本.zip', 'POR_911_23_v2.zip']
        sources = [self.source(name, f'download{i}') for i, name in enumerate(names)]
        result = self.m.import_files(sources)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['imported'], ['POR_911_23.zip', 'POR_911_23__fh6mm_v1.zipdisabled',
                                              'POR_911_23__fh6mm_v2.zipdisabled', 'POR_911_23__fh6mm_v3.zipdisabled'])
        self.assertEqual(result['renamed'][0], 'POR_911_23 (1).zip → POR_911_23.zip')
        self.assertEqual(len(result['renamed']), 4)
        self.assertEqual({m.group for m in self.m.scan()}, {'por_911_23'})
        for source in sources:
            self.assertEqual(source.read_bytes(), b'mod archive unchanged')  # downloads are copied, never moved

    def test_misnamed_copy_inside_mod_folder_is_renamed_in_place(self):
        (self.mods / 'POR_911_23.zip').write_bytes(b'installed version')
        copy = self.mods / 'POR_911_23 (1).zip'; copy.write_bytes(b'downloaded into the mod folder')
        result = self.m.import_files([copy])
        self.assertEqual(result['imported'], ['POR_911_23__fh6mm_v1.zipdisabled'])
        self.assertFalse(copy.exists())
        self.assertEqual((self.mods / 'POR_911_23__fh6mm_v1.zipdisabled').read_bytes(), b'downloaded into the mod folder')
        self.assertEqual((self.mods / 'POR_911_23.zip').read_bytes(), b'installed version')
        # A file that already carries the manager's name is left alone.
        again = self.m.import_files([self.mods / 'POR_911_23.zip'])
        self.assertEqual(again['imported'], []); self.assertEqual(len(again['skipped']), 1)

    def test_longest_car_name_wins(self):
        (self.original / 'POR_911_23_GT3.zip').write_bytes(b'original vehicle')
        result = self.m.import_files([self.source('POR_911_23_GT3 (1).zip'), self.source('POR_911_23 (1).zip', 'other')])
        self.assertEqual(result['imported'], ['POR_911_23_GT3.zip', 'POR_911_23.zip'])

    def test_renamed_list_only_shows_real_changes(self):
        result = self.m.import_files([self.source('por_911_23.zip')])
        self.assertEqual(result['imported'], ['POR_911_23.zip'])
        self.assertEqual(result['renamed'], ['por_911_23.zip → POR_911_23.zip'])
        result = self.m.import_files([self.source('POR_911_23.zip', 'again')])
        self.assertNotIn('POR_911_23.zip → POR_911_23.zip', result['renamed'])

    def test_full_filename_extension_must_match(self):
        (self.original / 'BMW_TEST.bin').write_bytes(b'not a matching ZIP filename')
        result = self.m.import_files([self.source('BMW_TEST.zip')])
        self.assertEqual(len(result['errors']), 1)

    def test_windows_case_insensitive_comparison_uses_game_spelling(self):
        result = self.m.import_files([self.source('por_911_23.ZIP')])
        self.assertEqual(result['imported'], ['POR_911_23.zip'])

    def test_mixed_batch_imports_only_valid_names(self):
        result = self.m.import_files([self.source('POR_911_23.zip'), self.source('WRONG.zip')])
        self.assertEqual(result['imported'], ['POR_911_23.zip'])
        self.assertEqual(len(result['errors']), 1)

    def test_repeated_valid_names_still_create_disabled_variants(self):
        result = self.m.import_files([self.source('POR_911_23.zip', 'first'), self.source('POR_911_23.zip', 'second')])
        self.assertEqual(result['imported'], ['POR_911_23.zip', 'POR_911_23__fh6mm_v1.zipdisabled'])

    def test_missing_reference_fails_without_creating_it(self):
        empty = self.root / 'missing'
        manager = Manager(self.mods, empty)
        with self.assertRaises(ModError):
            manager.import_files([self.source('POR_911_23.zip')])
        self.assertFalse(empty.exists())
        self.assertEqual(manager.scan(), [])

    def test_custom_mod_folder_requires_reference(self):
        folder = self.root / 'custom'
        folder.mkdir()
        manager = Manager(folder)
        with self.assertRaises(ModError):
            manager.import_files([self.source('POR_911_23.zip')])
        manager = Manager(folder, self.original)
        self.assertEqual(len(manager.import_files([self.source('POR_911_23.zip')])['imported']), 1)

    def test_mod_directory_cannot_validate_itself(self):
        (self.mods / 'WRONG.zip').write_bytes(b'not a base game vehicle')
        manager = Manager(self.mods, self.mods)
        with self.assertRaises(ModError):
            manager.import_files([self.source('WRONG.zip')])

    def test_directories_do_not_count_as_vehicle_files(self):
        (self.original / 'WRONG.zip').mkdir()
        result = self.m.import_files([self.source('WRONG.zip')])
        self.assertEqual(len(result['errors']), 1)

    def test_catalog_is_reloaded_for_each_batch(self):
        source = self.source('NEW_CAR.zip')
        self.assertEqual(len(self.m.import_files([source])['errors']), 1)
        (self.original / 'NEW_CAR.zip').write_bytes(b'new base game car')
        self.assertEqual(self.m.import_files([source])['imported'], ['NEW_CAR.zip'])


if __name__ == '__main__':
    unittest.main()
