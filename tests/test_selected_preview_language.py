"""Regressions for per-vehicle refresh isolation and saved language settings."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from app import Application
from core import Manager, ModError
from thumbnails import ThumbnailService, Request, Paused
from test_thumbnails import png_bytes
import i18n


class SelectedPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.a, self.b = self.root/'A.zip', self.root/'B.zip'
        self.a.write_bytes(b'A'); self.b.write_bytes(b'B')
        self.renderer = self.root/'renderer.exe'; self.renderer.write_bytes(b'fake')
        self.service = ThumbnailService(self.root, self.renderer, running=lambda: False)
        self.addCleanup(self.service.close)
        self.service.set_allowed(True)

    def req(self, source, force=False):
        sig = self.service.signature(source)
        return Request(source, None, None, sig, self.service.generation,
                       self.service.revisions.get(sig, 0), force)

    def renderer_process(self, command, **kwargs):
        job = json.loads(Path(command[-1]).read_text())
        Path(job['Output']).write_bytes(png_bytes())
        return SimpleNamespace(returncode=0, poll=lambda: 0, wait=lambda **kw: 0)

    def test_rebuild_one_vehicle_keeps_other_cache_and_mod_bytes(self):
        with patch('thumbnails.subprocess.Popen', side_effect=self.renderer_process) as process:
            a, b = self.req(self.a), self.req(self.b)
            result_a = self.service._generate(a)
            result_b = self.service._generate(b)
            self.service.completed.update({a.signature: result_a, b.signature: result_b})
            b_time = result_b[0].stat().st_mtime_ns
            self.assertEqual(self.service.invalidate(self.a), result_a[0])
            self.assertEqual(self.service.completed[b.signature], result_b)
            self.service._generate(self.req(self.a, force=True))
            self.service._generate(self.req(self.b))
            self.assertEqual(process.call_count, 3)  # A, B, then A only.
            self.assertEqual(result_b[0].stat().st_mtime_ns, b_time)
            self.assertEqual(self.a.read_bytes(), b'A')
            self.assertEqual(self.b.read_bytes(), b'B')

    def test_stale_selected_result_cannot_replace_new_request(self):
        a, b = self.req(self.a), self.req(self.b)
        self.service.invalidate(self.a)
        self.service.pending.update((a.signature, b.signature))
        self.service.results.put((a, (self.root/'stale.png', '已生成')))
        self.service.results.put((b, (self.root/'other.png', '已生成')))
        self.service.drain()
        self.assertNotIn(a.signature, self.service.completed)
        self.assertIn(a.signature, self.service.pending)
        self.assertIn(b.signature, self.service.completed)
        with self.assertRaises(Paused): self.service._check(a)
        self.service._check(b)

    def test_forced_refresh_survives_pause(self):
        self.service.invalidate(self.a)
        req = self.req(self.a, force=True)
        self.service.results.put((req, None))
        self.service.drain()
        self.assertIn(req.signature, self.service.forced)
        self.assertNotIn(req.signature, self.service.completed)

    def app(self):
        a = Application.__new__(Application)
        a.can_edit = Mock(return_value=True)
        a.manager = SimpleNamespace(folder=self.root, vehicles=None)
        a.rows = {'A.zip': SimpleNamespace(base='A')}; a.thumb_catalog = {}
        a.tree = Mock(); a.tree.selection.return_value = ('A.zip',)
        a.tree.images = {'a.png': 'A image', 'b.png': 'B image'}
        a.thumbnails = Mock(); a.thumbnails.invalidate.return_value = Path('a.png')
        a.thumbnail_for, a.status, a.error = Mock(), Mock(), Mock()
        return a

    def test_button_invalidates_only_the_selected_image(self):
        a = self.app(); a.retry_thumbnails()
        a.thumbnails.invalidate.assert_called_once_with(self.a, None, None)
        a.thumbnails.reset.assert_not_called()
        a.thumbnail_for.assert_called_once_with('A.zip')
        self.assertEqual(a.tree.images, {'b.png': 'B image'})

    def test_no_selection_or_game_lock_cannot_refresh_all(self):
        a = self.app(); a.tree.selection.return_value = (); a.retry_thumbnails()
        a.thumbnails.invalidate.assert_not_called(); a.thumbnails.reset.assert_not_called()
        a.tree.selection.return_value = ('A.zip',); a.can_edit.return_value = False
        a.retry_thumbnails(); a.thumbnails.invalidate.assert_not_called()


class LanguageTests(unittest.TestCase):
    def tearDown(self): i18n.set_language('zh')

    def test_english_validation_error_and_formatted_summary(self):
        i18n.set_language('en')
        with tempfile.TemporaryDirectory() as folder:
            manager = Manager(folder)
            with self.assertRaisesRegex(ModError, 'Import refused'):
                manager.vehicle_catalog()
        self.assertEqual(i18n.t('导入 {0} 个，跳过 {1} 个，失败 {2} 个。').format(2, 0, 1),
                         'Imported 2, skipped 0, failed 1.')
        i18n.set_language('zh')
        self.assertEqual(i18n.t('设置'), '设置')

    def test_changing_game_folder_preserves_language_and_other_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve(); mods = root/'mods'; mods.mkdir()
            a = Application.__new__(Application)
            a.can_edit = Mock(return_value=True)
            a.config = {'language': 'en', 'future_preference': 7}
            a.config_path = root/'settings.json'
            a.folder, a.location_info = Mock(), Mock()
            a.show_vehicle_directory, a.refresh = Mock(), Mock()
            a.set_folder(mods, manual=True)
            config = json.loads(a.config_path.read_text())
            self.assertEqual(config['language'], 'en')
            self.assertEqual(config['future_preference'], 7)
            self.assertEqual(config['folder'], str(mods))

    def test_unknown_language_uses_chinese(self):
        i18n.set_language('unsupported')
        self.assertEqual(i18n.t('模组管理'), '模组管理')


if __name__ == '__main__': unittest.main()
