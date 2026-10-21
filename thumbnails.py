"""Content-addressed thumbnail worker. Never rename or rewrite installed mod files."""
from i18n import t
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import queue
import struct
import subprocess
import sys
import tempfile
import threading
import time

from process_watch import game_is_running
from cache_storage import prune_cache, cleanup_stale_jobs, rotate_error_log, OWNER_FILE, OWNER_VALUE
from renderer_runtime import external_dll_search, renderer_environment, renderer_failure

RECIPE = 'fh6-fts-4f373c5-mesh-only-tight-frame-v2-640x360'


class Paused(Exception):
    pass


def stamp(path):
    if path is None:
        return None
    s = Path(path).stat()
    return (str(Path(path).resolve()), s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def renderer_path():
    root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    return root / 'renderer' / 'ForzaTech Studio.exe'


def valid_png(path):
    try:
        with Path(path).open('rb') as f:
            head = f.read(24)
            if len(head) != 24 or head[:8] != b'\x89PNG\r\n\x1a\n' or head[12:16] != b'IHDR':
                return False
            w, h = struct.unpack('>II', head[16:24])
            if not (16 <= w <= 4096 and 16 <= h <= 4096):
                return False
            f.seek(-12, 2)
            return f.read(12) == b'\0\0\0\0IEND\xaeB`\x82'
    except (OSError, ValueError):
        return False


def digest_copy(source, destination=None, check=lambda: None):
    before = stamp(source)
    h = hashlib.sha256()
    output = Path(destination).open('xb') if destination else None
    try:
        with Path(source).open('rb') as f:
            for chunk in iter(lambda: f.read(1024*1024), b''):
                check()
                h.update(chunk)
                if output:
                    output.write(chunk)
        if stamp(source) != before:
            raise OSError(t('文件在读取时发生变化，请重新生成'))
    finally:
        if output:
            output.close()
    return h.hexdigest()


def cache_key(mod_hash, base_hash, game_root, engine_stamp):
    # Names and enabled/disabled extensions deliberately do not participate.
    payload = (RECIPE, mod_hash, base_hash, str(game_root), engine_stamp)
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class Request:
    source: Path
    original: Path | None
    game_root: Path | None
    signature: tuple
    generation: int
    revision: int = 0
    force: bool = False


class ThumbnailService:
    def __init__(self, home, renderer=None, running=game_is_running, timeout=180):
        self.cache = Path(home) / 'thumbnails'
        self.cache.mkdir(parents=True, exist_ok=True)
        cleanup_stale_jobs(self.cache)
        prune_cache(self.cache)
        rotate_error_log(self.cache)
        self.renderer = Path(renderer) if renderer else renderer_path()
        self.running, self.timeout = running, timeout
        self.tasks, self.results = queue.Queue(), queue.Queue()
        self.pending, self.completed = set(), {}
        self.allowed, self.closed = threading.Event(), threading.Event()
        self.generation = 0
        self.revisions, self.forced = {}, set()
        self.process = None
        self.force_generation = False
        self.regenerated = set()
        self.thread = threading.Thread(target=self._work, name='FH6 thumbnails', daemon=True)
        self.thread.start()

    def set_allowed(self, allowed):
        (self.allowed.set if allowed else self.allowed.clear)()

    def reset(self):
        self.generation += 1
        self.completed.clear()
        self.pending.clear()
        # Explicit user refresh invalidates global texture changes not covered by car ZIP hashes.
        self.force_generation = True
        self.regenerated.clear()
        self.revisions.clear()
        self.forced.clear()

    def signature(self, source, original=None, game_root=None):
        return (stamp(source), stamp(original), str(game_root), stamp(self.renderer) if self.renderer.is_file() else None)

    def invalidate(self, source, original=None, game_root=None):
        """Invalidate one source without cancelling or clearing other vehicles."""
        self.drain()
        signature = self.signature(source, original, game_root)
        self.revisions[signature] = self.revisions.get(signature, 0) + 1
        self.forced.add(signature)
        self.pending.discard(signature)
        old = self.completed.pop(signature, (None, ''))
        return old[0]

    def drain(self):
        changed = False
        while True:
            try:
                req, result = self.results.get_nowait()
            except queue.Empty:
                return changed
            if req.generation == self.generation and req.revision == self.revisions.get(req.signature, 0):
                self.pending.discard(req.signature)
                if result is not None:  # Paused tasks retry after unlock, not permanently fail.
                    self.completed[req.signature] = result
                    if result[0] is not None:
                        self.forced.discard(req.signature)
                changed = True

    def request(self, source, original=None, game_root=None):
        self.drain()
        try:
            signature = self.signature(source, original, game_root)
        except OSError:
            return None, '文件暂时不可读取'
        if signature in self.completed:
            result = self.completed[signature]
            if result[0] is None or result[0].is_file():
                return result
            self.completed.pop(signature, None)
        if not self.renderer.is_file():
            return None, '未安装 3D 渲染组件'
        if signature not in self.pending and self.allowed.is_set():
            self.pending.add(signature)
            self.tasks.put(Request(Path(source), Path(original) if original else None,
                                   Path(game_root) if game_root else None, signature, self.generation,
                                   self.revisions.get(signature, 0), signature in self.forced))
        return None, '等待生成' if self.allowed.is_set() else '生成已暂停'

    def _check(self, req):
        if (self.closed.is_set() or not self.allowed.is_set() or req.generation != self.generation
                or req.revision != self.revisions.get(req.signature, 0)):
            raise Paused()

    def _generate(self, req):
        self._check(req)
        if self.running():
            raise Paused()
        if stamp(req.source) != req.signature[0] or stamp(req.original) != req.signature[1]:
            raise OSError(t('文件已变更'))
        # Check content-addressed cache before writing full archive copies.
        mod_hash = digest_copy(req.source, check=lambda: self._check(req))
        base_hash = digest_copy(req.original, check=lambda: self._check(req)) if req.original else ''
        key = cache_key(mod_hash, base_hash, req.game_root, req.signature[3])
        target = self.cache / (key + '.png')
        if valid_png(target) and not req.force and (not self.force_generation or key in self.regenerated):
            self._check(req)
            os.utime(target, ns=(time.time_ns(), target.stat().st_mtime_ns))
            return target, '已生成'
        with tempfile.TemporaryDirectory(prefix='render-', dir=self.cache) as folder:
            folder = Path(folder)
            (folder / OWNER_FILE).write_text(OWNER_VALUE, encoding='utf-8')
            copied = folder / 'mod.zip'
            if digest_copy(req.source, copied, lambda: self._check(req)) != mod_hash:
                raise OSError(t('文件已变更'))
            original = folder / 'original.zip' if req.original else None
            if original and digest_copy(req.original, original, lambda: self._check(req)) != base_hash:
                raise OSError(t('文件已变更'))
            output = folder / 'preview.png'
            job = folder / 'request.json'
            job.write_text(json.dumps({'Input': str(copied), 'BaseArchive': str(original) if original else None,
                'GameRoot': str(req.game_root) if req.game_root else None,
                'Output': str(output), 'Width': 640, 'Height': 360}, ensure_ascii=False), encoding='utf-8')
            self._check(req)
            if self.running():
                raise Paused()
            log_path = folder / 'renderer.log'
            with log_path.open('wb') as log:
                with external_dll_search():
                    proc = subprocess.Popen([str(self.renderer), '--fh6-thumbnail-request', str(job)],
                        cwd=str(self.renderer.parent), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                        env=renderer_environment(folder / 'startup.log'),
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                self.process = proc
                started = time.monotonic()
                try:
                    while proc.poll() is None:
                        self._check(req)
                        if self.running():
                            raise Paused()
                        if time.monotonic()-started > self.timeout:
                            raise TimeoutError(t('渲染超时\n') + renderer_failure(258, folder))
                        self.closed.wait(.35)
                    if proc.returncode:
                        raise RuntimeError(renderer_failure(proc.returncode, folder))
                finally:
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait(timeout=10)
                    self.process = None
            self._check(req)
            if not valid_png(output):
                raise RuntimeError(t('渲染组件没有输出有效 PNG'))
            os.replace(output, target)
            prune_cache(self.cache, protected=(target,))
            self.regenerated.add(key)
            return target, '已生成'

    def _work(self):
        while not self.closed.is_set():
            try:
                req = self.tasks.get(timeout=.25)
            except queue.Empty:
                continue
            try:
                result = self._generate(req)
            except Paused:
                result = None
            except Exception as exc:
                result = (None, '预览失败 · 可重试')
                try:
                    rotate_error_log(self.cache)
                    with (self.cache / 'errors.log').open('a', encoding='utf-8') as f:
                        f.write(f'{req.source.name}: {type(exc).__name__}: {exc}\n')
                except OSError:
                    pass
            self.results.put((req, result))

    def close(self):
        self.closed.set()
        self.allowed.clear()
        proc = self.process
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        self.thread.join(timeout=2)
