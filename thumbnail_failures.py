"""Persistent negative preview cache, owned by the thumbnail service."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time

FAILURE_STATUS = '预览失败 · 手动重试'


def file_key(source_stamp):
    # Enabling/disabling changes name and ctime, not the file's identity/content.
    path, device, inode, size, modified, _created = source_stamp
    identity = (device, inode) if inode else os.path.normcase(path)
    return hashlib.sha256(json.dumps((identity, size, modified)).encode()).hexdigest()


def is_digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


class FailureCache:
    def __init__(self, folder):
        self.path = Path(folder) / 'failed-previews.json'
        self.lock = threading.RLock()
        self.files, self.hashes = {}, {}
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('version') == 1:
                self.hashes = {k: v for k, v in data['hashes'].items() if is_digest(k) and isinstance(v, (int, float))}
                self.files = {k: v for k, v in data['files'].items() if is_digest(k) and v in self.hashes}
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            self.files, self.hashes = {}, {}

    def contains_file(self, source_stamp):
        with self.lock:
            return self.files.get(file_key(source_stamp)) in self.hashes

    def contains_hash(self, digest):
        with self.lock:
            return digest in self.hashes

    def remember(self, source_stamp, digest):
        with self.lock:
            key = file_key(source_stamp)
            if self.files.get(key) == digest and digest in self.hashes:
                return
            self.files[key] = digest
            self.hashes.setdefault(digest, time.time())
            self._save()

    def forget(self, digest):
        with self.lock:
            if digest not in self.hashes:
                return
            self.hashes.pop(digest)
            self.files = {k: v for k, v in self.files.items() if v != digest}
            self._save()

    def _save(self):
        # Atomic replacement prevents a partial JSON file on interrupted writes.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='failed-previews-',
                                             suffix='.tmp', dir=self.path.parent, delete=False) as f:
                temporary = Path(f.name)
                json.dump({'version': 1, 'files': self.files, 'hashes': self.hashes}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
