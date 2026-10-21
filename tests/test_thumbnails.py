import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib

from thumbnails import ThumbnailService, Request, Paused, stamp, digest_copy, cache_key, valid_png


def png_bytes():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 36, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + b'\x30\x60\x90'*64)*36)) + chunk(b'IEND', b''))


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'CAR.zipdisabled'
        self.source.write_bytes(b'first-mod')
        self.original = self.root / 'original.zip'
        self.original.write_bytes(b'original-car')
        self.renderer = self.root / 'renderer.exe'
        self.renderer.write_bytes(b'renderer-test-double')
        self.service = ThumbnailService(self.root, self.renderer, running=lambda: False, timeout=.01)
        self.addCleanup(self.service.close)
        self.service.set_allowed(True)

    def req(self):
        sig = (stamp(self.source), stamp(self.original), str(self.root), stamp(self.renderer))
        return Request(self.source, self.original, self.root, sig, self.service.generation)

    def fake_renderer(self, command, **kwargs):
        test = self
        class Process:
            returncode = 0
            def __init__(self):
                job = json.loads(Path(command[-1]).read_text(encoding='utf-8'))
                test.assertEqual(Path(job['Input']).suffix, '.zip')
                test.assertEqual(Path(job['Input']).read_bytes(), test.source.read_bytes())
                test.assertEqual(Path(job['BaseArchive']).read_bytes(), b'original-car')
                test.assertNotEqual(Path(job['Input']), test.source)
                Path(job['Output']).write_bytes(png_bytes())
            def poll(self): return self.returncode
            def wait(self, **kwargs): return self.returncode
            def kill(self): self.returncode = -9
        return Process()

    def test_digest_preserves_source_and_detects_content(self):
        target = self.root / 'copy.zip'
        digest = digest_copy(self.source, target)
        self.assertEqual(target.read_bytes(), self.source.read_bytes())
        self.assertEqual(digest, hashlib.sha256(b'first-mod').hexdigest())

    def test_cancel_copy_does_not_change_source(self):
        def paused(): raise Paused()
        with self.assertRaises(Paused):
            digest_copy(self.source, self.root / 'copy.zip', paused)
        self.assertEqual(self.source.read_bytes(), b'first-mod')

    def test_original_and_renderer_changes_invalidate_key(self):
        a = cache_key('mod', 'original', 'game', ('renderer', 1))
        self.assertNotEqual(a, cache_key('mod2', 'original', 'game', ('renderer', 1)))
        self.assertNotEqual(a, cache_key('mod', 'original2', 'game', ('renderer', 1)))
        self.assertNotEqual(a, cache_key('mod', 'original', 'game', ('renderer', 2)))

    def test_png_rejects_truncated_and_non_image_outputs(self):
        p = self.root / 'test.png'
        p.write_bytes(png_bytes())
        self.assertTrue(valid_png(p))
        p.write_bytes(png_bytes()[:-6])
        self.assertFalse(valid_png(p))
        p.write_bytes(b'<html>error</html>')
        self.assertFalse(valid_png(p))

    def test_content_cache_survives_enable_rename(self):
        with patch('thumbnails.subprocess.Popen', side_effect=self.fake_renderer) as popen:
            first, _ = self.service._generate(self.req())
            moved = self.root / 'CAR.zip'
            self.source.rename(moved)
            self.source = moved
            second, _ = self.service._generate(self.req())
            self.assertEqual(first, second)
            self.assertEqual(popen.call_count, 1)
            self.assertEqual(self.original.read_bytes(), b'original-car')
            self.assertFalse(list(self.service.cache.glob('render-*')))

    def test_same_filename_new_content_gets_different_picture(self):
        with patch('thumbnails.subprocess.Popen', side_effect=self.fake_renderer):
            first, _ = self.service._generate(self.req())
            self.source.write_bytes(b'other-mod')
            second, _ = self.service._generate(self.req())
            self.assertNotEqual(first, second)

    def test_game_running_never_starts_renderer(self):
        self.service.running = lambda: True
        with patch('thumbnails.subprocess.Popen') as popen, self.assertRaises(Paused):
            self.service._generate(self.req())
        popen.assert_not_called()

    def test_unknown_game_status_never_starts_renderer(self):
        def error(): raise OSError('process list denied')
        self.service.running = error
        with patch('thumbnails.subprocess.Popen') as popen, self.assertRaises(OSError):
            self.service._generate(self.req())
        popen.assert_not_called()

    def test_stale_generation_is_discarded(self):
        req = self.req()
        self.service.reset()
        self.service.results.put((req, (self.root / 'old.png', '已生成')))
        self.service.drain()
        self.assertFalse(self.service.completed)
        with self.assertRaises(Paused):
            self.service._generate(req)

    def test_manual_refresh_renders_once_per_content_again(self):
        with patch('thumbnails.subprocess.Popen', side_effect=self.fake_renderer) as popen:
            self.service._generate(self.req())
            self.service.reset()
            self.service._generate(self.req())
            self.service._generate(self.req())
            self.assertEqual(popen.call_count, 2)

    def test_missing_renderer_has_explicit_status_and_no_queue(self):
        self.renderer.unlink()
        path, text = self.service.request(self.source)
        self.assertIsNone(path)
        self.assertIn('未安装', text)
        self.assertTrue(self.service.tasks.empty())

    def test_changed_source_since_queue_is_not_rendered(self):
        req = self.req()
        self.source.write_bytes(b'changed')
        with patch('thumbnails.subprocess.Popen') as popen, self.assertRaises(OSError):
            self.service._generate(req)
        popen.assert_not_called()

    def test_pause_terminates_running_renderer_and_cleans_temp(self):
        service = self.service
        class Process:
            returncode = None
            killed = False
            def poll(self): return self.returncode
            def wait(self, **kwargs): return self.returncode
            def kill(self):
                self.killed, self.returncode = True, -9
        proc = Process()
        def start(*args, **kwargs):
            service.allowed.clear()
            return proc
        with patch('thumbnails.subprocess.Popen', side_effect=start), self.assertRaises(Paused):
            service._generate(self.req())
        self.assertTrue(proc.killed)
        self.assertIsNone(service.process)
        self.assertFalse(list(service.cache.glob('render-*')))

    def test_native_crash_preserves_diagnostics_before_temp_cleanup(self):
        def crash(command, **kwargs):
            Path(kwargs['env']['FH6MM_RENDER_LOG']).write_text('App XAML failed: detail', encoding='utf-8')
            class Process:
                returncode = 3221226107
                def poll(self): return self.returncode
                def wait(self, **kwargs): return self.returncode
            return Process()
        with patch('thumbnails.subprocess.Popen', side_effect=crash):
            with self.assertRaisesRegex(RuntimeError, '0xC000027B') as error:
                self.service._generate(self.req())
        self.assertIn('App XAML failed: detail', str(error.exception))
        self.assertFalse(list(self.service.cache.glob('render-*')))


if __name__ == '__main__':
    unittest.main()
