"""Batch enable / disable / delete and the GitHub release check."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from core import Manager
import update_check
from update_check import parse_version, is_newer, fetch_latest


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.cars = base / 'Cars'; self.cars.mkdir()
        vehicles = base / 'media' / 'cars'; vehicles.mkdir(parents=True)
        self.m = Manager(self.cars, vehicles)

    def put(self, name, value=b'x'):
        (self.cars / name).write_bytes(value)
        return name

    def state(self):
        return {m.filename: m.enabled for m in self.m.scan()}

    def test_enable_picks_one_version_per_car(self):
        a = self.put('A__fh6mm_v1.zipdisabled', b'a1')
        b = self.put('A__fh6mm_v2.zipdisabled', b'a2')
        c = self.put('B.zipdisabled', b'b')
        result = self.m.batch('enable', [b, a, c])
        self.assertEqual(result['done'], ['A.zip', 'B.zip'])
        self.assertEqual(len(result['skipped']), 1)
        self.assertEqual((self.cars / 'A.zip').read_bytes(), b'a2')  # the first selected version of A
        self.assertEqual(sum(self.state().values()), 2)

    def test_selected_enabled_version_is_kept(self):
        on = self.put('A.zip', b'on')
        off = self.put('A__fh6mm_v1.zipdisabled', b'off')
        result = self.m.batch('enable', [off, on])
        self.assertEqual(result['done'], ['A.zip'])
        self.assertEqual((self.cars / 'A.zip').read_bytes(), b'on')

    def test_disable_many(self):
        names = [self.put('A.zip'), self.put('B.zip'), self.put('C.zipdisabled')]
        result = self.m.batch('disable', names)
        self.assertEqual(result['errors'], [])
        self.assertFalse(any(self.state().values()))

    def test_delete_many_keeps_going_and_respects_confirmed_stamps(self):
        a, b, c = self.put('A.zip'), self.put('B.zip'), self.put('C.zip')
        stamps = {m.filename: (m.size, m.modified) for m in self.m.scan()}
        (self.cars / b).write_bytes(b'changed after confirmation')
        recycled = []
        result = self.m.batch('delete', [a, b, c, 'GONE.zip'], expected=stamps,
                              recycler=lambda path: (recycled.append(path.name), path.unlink()))
        self.assertEqual(result['done'], ['A.zip', 'C.zip'])
        self.assertEqual(recycled, ['A.zip', 'C.zip'])
        self.assertEqual(len(result['errors']), 2)  # B changed, GONE.zip does not exist
        self.assertTrue((self.cars / b).exists())


class UpdateCheckTests(unittest.TestCase):
    def reply(self, payload, raw=None):
        body = raw if raw is not None else json.dumps(payload).encode()
        response = Mock()
        response.__enter__ = Mock(return_value=io.BytesIO(body))
        response.__exit__ = Mock(return_value=False)
        return Mock(return_value=response)

    def test_versions(self):
        self.assertEqual(parse_version('v0.8.10'), (0, 8, 10))
        self.assertEqual(parse_version('0.9'), (0, 9, 0))
        self.assertIsNone(parse_version('beta'))
        self.assertTrue(is_newer('v0.8.10', '0.8.9'))
        self.assertFalse(is_newer('v0.8.8', '0.8.8'))
        self.assertFalse(is_newer('v0.8.7', '0.8.8'))
        self.assertFalse(is_newer('nightly', '0.8.8'))

    def test_latest_release_and_safe_page(self):
        good = self.reply({'tag_name': 'v0.9.0', 'html_url': 'https://github.com/little-boluo/FH6-Car-Mod-Manager/releases/tag/v0.9.0'})
        self.assertEqual(fetch_latest(opener=good), ('v0.9.0', 'https://github.com/little-boluo/FH6-Car-Mod-Manager/releases/tag/v0.9.0'))
        request = good.call_args.args[0]
        self.assertEqual(request.full_url, update_check.LATEST_API)
        self.assertIn('FH6CarModManager/', request.headers['User-agent'])
        odd = self.reply({'tag_name': 'v0.9.0', 'html_url': 'https://example.com/phish'})
        self.assertEqual(fetch_latest(opener=odd)[1], update_check.RELEASES_PAGE)

    def test_bad_replies_raise(self):
        for opener in (self.reply({'message': 'Not Found'}), self.reply(None, raw=b'<html>'),
                       Mock(side_effect=OSError('offline'))):
            with self.assertRaises((OSError, ValueError)):
                fetch_latest(opener=opener)


if __name__ == '__main__':
    unittest.main()
