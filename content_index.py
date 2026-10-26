"""Persistent content hashes of mod and original car ZIPs, keyed by file identity.

Hashing a car ZIP reads hundreds of megabytes.  Without this index every launch
re-read every mod and its original car just to find the preview that was already
rendered.  Keys use the same identity as the failure cache (volume + file ID,
size, modification time), so enable/disable renames keep their entry while any
content change gets a new one.  A copy whose digest disagrees with the index
drops the entry, and "Rebuild preview" forgets it explicitly.
"""
import json
import os
from pathlib import Path
import tempfile
import threading
import time

from thumbnail_failures import file_key, is_digest

MAX_ENTRIES = 4000


class ContentIndex:
    def __init__(self, folder):
        self.path = Path(folder) / 'content-hashes.json'
        self.lock = threading.RLock()
        self.entries = {}
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('version') == 1:
                self.entries = {k: [v[0], float(v[1])] for k, v in data['entries'].items()
                                if is_digest(k) and isinstance(v, list) and len(v) == 2 and is_digest(v[0])}
        except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError):
            self.entries = {}

    def get(self, source_stamp):
        if source_stamp is None:
            return None
        with self.lock:
            entry = self.entries.get(file_key(source_stamp))
            if entry is None:
                return None
            entry[1] = time.time()  # persisted with the next change
            return entry[0]

    def remember(self, source_stamp, digest):
        with self.lock:
            key = file_key(source_stamp)
            if self.entries.get(key, [None])[0] == digest:
                return
            self.entries[key] = [digest, time.time()]
            if len(self.entries) > MAX_ENTRIES:
                for stale, _ in sorted(self.entries.items(), key=lambda item: item[1][1])[:len(self.entries) - MAX_ENTRIES]:
                    self.entries.pop(stale)
            self._save()

    def forget(self, source_stamp):
        with self.lock:
            if self.entries.pop(file_key(source_stamp), None) is not None:
                self._save()

    def _save(self):
        # Atomic replacement prevents a partial JSON file on interrupted writes.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='content-hashes-',
                                             suffix='.tmp', dir=self.path.parent, delete=False) as f:
                temporary = Path(f.name)
                json.dump({'version': 1, 'entries': self.entries}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, self.path)
        except OSError:
            pass  # the index is only an accelerator; a failed save just means hashing again later
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
