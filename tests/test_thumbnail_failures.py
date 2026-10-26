from dataclasses import replace
import shutil
import unittest
from unittest.mock import patch

import test_thumbnails as fixtures
from thumbnail_failures import FailureCache, FAILURE_STATUS
from thumbnails import ThumbnailService, Paused, digest_copy


class PersistentFailureTests(unittest.TestCase):
    setUp = fixtures.ThumbnailTests.setUp
    req = fixtures.ThumbnailTests.req
    fake_renderer = fixtures.ThumbnailTests.fake_renderer

    def fail_preview(self):
        with patch.object(self.service, '_render', side_effect=RuntimeError('bad model')):
            with self.assertRaisesRegex(RuntimeError, 'bad model'):
                self.service._generate(self.req())

    def restart(self):
        self.service.close()
        self.service = ThumbnailService(self.root, self.renderer, running=lambda: False)
        self.addCleanup(self.service.close)
        self.service.set_allowed(True)

    def test_restart_skips_failed_mod_without_queue_hash_or_render(self):
        self.fail_preview()
        self.restart()
        with patch.object(self.service.tasks, 'put') as enqueue, patch('thumbnails.digest_copy') as digest:
            self.assertEqual(self.service.request(self.source, self.original, self.root), (None, FAILURE_STATUS))
        enqueue.assert_not_called()
        digest.assert_not_called()

    def test_enable_and_duplicate_version_renames_preserve_failure(self):
        self.fail_preview()
        for name in ('CAR.zip', 'CAR__fh6mm_v2.zipdisabled'):
            moved = self.root / name
            self.source.rename(moved)
            self.source = moved
            self.restart()
            with patch.object(self.service.tasks, 'put') as enqueue:
                self.assertEqual(self.service.request(self.source, self.original, self.root), (None, FAILURE_STATUS))
            enqueue.assert_not_called()

    def test_copied_failed_content_never_renders_and_remembers_new_file(self):
        self.fail_preview()
        copied = self.root / 'copy.zipdisabled'
        shutil.copyfile(self.source, copied)
        self.source = copied
        self.restart()
        with patch.object(self.service, '_render') as render:
            self.assertEqual(self.service._generate(self.req()), (None, FAILURE_STATUS))
        render.assert_not_called()
        self.assertTrue(FailureCache(self.service.cache).contains_file(self.req().signature[0]))

    def test_replacing_failed_mod_content_allows_new_preview(self):
        self.fail_preview()
        self.source.write_bytes(b'fixed model content')
        self.restart()
        with patch('thumbnails.subprocess.Popen', side_effect=self.fake_renderer) as render:
            path, status = self.service._generate(self.req())
        self.assertTrue(path.is_file())
        self.assertEqual(status, '已生成')
        render.assert_called_once()

    def test_manual_retry_queues_force_and_success_clears_persistent_failure(self):
        self.fail_preview()
        self.restart()
        self.service.invalidate(self.source, self.original, self.root)
        with patch.object(self.service.tasks, 'put') as enqueue:
            self.service.request(self.source, self.original, self.root)
        req = enqueue.call_args.args[0]
        self.assertTrue(req.force)
        with patch('thumbnails.subprocess.Popen', side_effect=self.fake_renderer):
            path, _ = self.service._generate(req)
        self.assertTrue(path.is_file())
        self.assertFalse(FailureCache(self.service.cache).contains_hash(digest_copy(self.source)))

    def test_failed_manual_retry_remains_blocked_after_restart(self):
        self.fail_preview()
        with patch.object(self.service, '_render', side_effect=RuntimeError('still broken')):
            with self.assertRaises(RuntimeError):
                self.service._generate(replace(self.req(), force=True))
        self.restart()
        self.assertEqual(self.service.request(self.source, self.original, self.root), (None, FAILURE_STATUS))

    def test_pause_close_and_stale_request_are_not_persistent_failures(self):
        for action in ('pause', 'close', 'supersede', 'game'):
            with self.subTest(action=action):
                self.restart()
                def interrupt(req, mod_hash):
                    if action == 'pause':
                        self.service.set_allowed(False)
                    elif action == 'close':
                        self.service.closed.set()
                    elif action == 'supersede':
                        self.service.invalidate(self.source, self.original, self.root)
                    else:
                        self.service.running = lambda: True
                    raise RuntimeError('interrupted renderer')
                with patch.object(self.service, '_render', side_effect=interrupt):
                    with self.assertRaises((Paused, RuntimeError)):
                        self.service._generate(self.req())
                self.assertFalse(FailureCache(self.service.cache).contains_hash(digest_copy(self.source)))

    def test_failure_does_not_block_other_mods(self):
        self.fail_preview()
        self.source = self.root / 'other.zip'
        self.source.write_bytes(b'another model')
        with patch('thumbnails.subprocess.Popen', side_effect=self.fake_renderer) as render:
            path, _ = self.service._generate(self.req())
        self.assertTrue(path.is_file())
        render.assert_called_once()

    def test_corrupt_failure_cache_does_not_prevent_startup(self):
        (self.service.cache / 'failed-previews.json').write_text('{truncated', encoding='utf-8')
        self.restart()
        with patch('thumbnails.subprocess.Popen', side_effect=self.fake_renderer):
            path, _ = self.service._generate(self.req())
        self.assertTrue(path.is_file())


if __name__ == '__main__':
    unittest.main()
