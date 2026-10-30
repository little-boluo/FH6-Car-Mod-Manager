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
from content_index import ContentIndex
from thumbnail_failures import FailureCache, FAILURE_STATUS, file_key
from cache_storage import prune_cache, cleanup_stale_jobs, rotate_error_log, OWNER_FILE, OWNER_VALUE
from renderer_runtime import external_dll_search, renderer_environment, renderer_failure

RECIPE = 'fh6-fts-4f373c5-mesh-only-tight-frame-v2-640x360'


class Paused(Exception):
    pass


class StaleHash(Exception):
    """The content index disagreed with the bytes actually copied; not a mod failure."""


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


PREVIEW_WIDTH = 512  # cards show previews 342 px wide; 512 still covers 150 % display scaling


def compact_preview(path):
    """Store a rendered preview at the size the grid can use, as an optimised PNG.

    The renderer captures 640x360 with an all-opaque alpha channel; keeping that
    roughly doubled the cache on disk for no visible gain.  Returns True when the
    file was rewritten; on any problem the original file is left untouched."""
    try:
        from PIL import Image
    except ImportError:
        return False
    path = Path(path)
    temporary = None
    try:
        with Image.open(path) as image:
            if image.format != 'PNG' or image.width <= PREVIEW_WIDTH:
                return False
            image.load()
            if 'A' in image.getbands() and image.getchannel('A').getextrema() == (255, 255):
                image = image.convert('RGB')
            elif image.mode not in ('RGB', 'RGBA'):
                image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
            size = (PREVIEW_WIDTH, max(16, round(image.height * PREVIEW_WIDTH / image.width)))
            small = image.resize(size, getattr(Image, 'Resampling', Image).LANCZOS)
        fd, temporary = tempfile.mkstemp(prefix='compact-', suffix='.tmp', dir=path.parent)
        os.close(fd)
        small.save(temporary, 'PNG', optimize=True)
        # Flat synthetic pictures can grow after resampling; only ever trade down.
        if not valid_png(temporary) or os.path.getsize(temporary) >= path.stat().st_size:
            return False
        os.replace(temporary, path)
        return True
    except (OSError, ValueError):
        return False
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


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


class RecentFirstQueue:
    """Pending previews; the most recently requested go first.

    Cards on screen are requested again on every grid refresh, so they overtake
    cards that were scrolled away.  Requests made within the same second keep
    their order, so a freshly shown page still fills from the top."""
    BUCKET = 1.0

    def __init__(self):
        self.ready = threading.Condition()
        self.items, self.sequence = {}, 0

    def _rank(self):
        self.sequence += 1
        return int(time.monotonic() / self.BUCKET), -self.sequence

    def put(self, req):
        with self.ready:
            self.items[req.signature] = (self._rank(), req)
            self.ready.notify()

    def touch(self, signature):
        with self.ready:
            item = self.items.get(signature)
            if item is not None:
                bucket, _ = self._rank()
                if bucket != item[0][0]:
                    self.items[signature] = ((bucket, item[0][1]), item[1])

    def get(self, timeout=None):
        with self.ready:
            if not self.items and not self.ready.wait_for(lambda: self.items, timeout):
                raise queue.Empty
            signature = max(self.items, key=lambda key: self.items[key][0])
            return self.items.pop(signature)[1]

    def empty(self):
        with self.ready:
            return not self.items


def background_thread():
    """Give the calling thread low I/O and memory priority on Windows (hashing and copying)."""
    if os.name != 'nt':
        return
    try:
        import ctypes
        kernel = ctypes.WinDLL('kernel32')
        kernel.GetCurrentThread.restype = ctypes.c_void_p
        kernel.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
        kernel.SetThreadPriority(kernel.GetCurrentThread(), 0x00010000)  # THREAD_MODE_BACKGROUND_BEGIN
    except (OSError, AttributeError):
        pass


class ThumbnailService:
    def __init__(self, home, renderer=None, running=game_is_running, timeout=180):
        self.cache = Path(home) / 'thumbnails'
        self.cache.mkdir(parents=True, exist_ok=True)
        self.manual = self.cache / 'manual'
        self.manual.mkdir(exist_ok=True)
        cleanup_stale_jobs(self.cache)
        prune_cache(self.cache)
        rotate_error_log(self.cache)
        self.state_lock = threading.RLock()
        self.failures = FailureCache(self.cache)
        self.hashes = ContentIndex(self.cache)
        self.renderer = Path(renderer) if renderer else renderer_path()
        self.running, self.timeout = running, timeout
        self.tasks, self.results = RecentFirstQueue(), queue.Queue()
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
        with self.state_lock:
            (self.allowed.set if allowed else self.allowed.clear)()

    def reset(self):
        with self.state_lock:
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
        with self.state_lock:
            self.drain()
            signature = self.signature(source, original, game_root)
            manual = self.manual / (file_key(signature[0]) + '.png')
            manual.unlink(missing_ok=True)
            self.hashes.forget(signature[0])  # rebuild re-reads the file instead of trusting its identity
            self.revisions[signature] = self.revisions.get(signature, 0) + 1
            self.forced.add(signature)
            self.pending.discard(signature)
            old = self.completed.pop(signature, (None, ''))
            return old[0]

    def import_manual(self, source, image, expected_stamp=None):
        """Persist for this file identity, including its enable/variant renames."""
        from manual_previews import prepare_preview
        source = Path(source)
        before = stamp(source)
        if expected_stamp is not None and before != expected_stamp:
            raise OSError(t('文件已变更'))
        def check():
            if self.closed.is_set() or self.running():
                raise OSError(t('请在游戏关闭时导入缩略图'))
            if stamp(source) != before:
                raise OSError(t('文件已变更'))
        check()
        target = self.manual / (file_key(before) + '.png')
        fd, temporary = tempfile.mkstemp(prefix='import-', suffix='.tmp', dir=self.manual)
        os.close(fd)
        try:
            prepare_preview(image, temporary)
            with self.state_lock:
                check()
                os.replace(temporary, target)
                for signature in set(self.completed) | self.pending | set(self.revisions):
                    if file_key(signature[0]) == file_key(before):
                        self.revisions[signature] = self.revisions.get(signature, 0) + 1
                        self.pending.discard(signature)
                        self.completed.pop(signature, None)
                        self.forced.discard(signature)
            return target
        finally:
            Path(temporary).unlink(missing_ok=True)


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
            manual = self.manual / (file_key(stamp(source)) + '.png')
            if manual.is_file():
                return manual, '手动缩略图'
            signature = self.signature(source, original, game_root)
        except OSError:
            return None, '文件暂时不可读取'
        if signature in self.completed:
            result = self.completed[signature]
            if result[0] is None or result[0].is_file():
                return result
            self.completed.pop(signature, None)
        if signature not in self.forced and self.failures.contains_file(signature[0]):
            return None, FAILURE_STATUS
        if not self.renderer.is_file():
            return None, '未安装 3D 渲染组件'
        if signature in self.pending:
            self.tasks.touch(signature)  # still wanted: keep it ahead of cards scrolled away
        elif self.allowed.is_set():
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
        if not req.force and self.failures.contains_file(req.signature[0]):
            return None, FAILURE_STATUS
        # Hash only when this file has no known failure (e.g. a copied/new version),
        # and only once per file identity: later launches find the preview directly.
        mod_hash = self._digest(req.source, req.signature[0], req)
        if not req.force and self.failures.contains_hash(mod_hash):
            with self.state_lock:
                self._check(req)
                self._remember_failure(req, mod_hash)
            return None, FAILURE_STATUS
        try:
            result = self._render(req, mod_hash)
        except StaleHash:
            return self._generate(req)  # the entry is gone, so this pass hashes the file itself
        except Paused:
            raise
        except Exception:
            with self.state_lock:
                # Closing, pausing, or superseding this request is not a mod failure.
                self._check(req)
                try:
                    unchanged = self.signature(req.source, req.original, req.game_root) == req.signature
                    stopped = not self.running()
                except OSError:
                    unchanged, stopped = False, False
                if unchanged and stopped:
                    self._remember_failure(req, mod_hash)
            raise
        with self.state_lock:
            self._check(req)
            try:
                self.failures.forget(mod_hash)
            except OSError as exc:
                self._log_error(req, exc, 'Could not clear failed-preview record')
        return result

    def _remember_failure(self, req, mod_hash):
        try:
            self.failures.remember(req.signature[0], mod_hash)
        except OSError as exc:
            self._log_error(req, exc, 'Could not save failed-preview record')

    def _digest(self, path, path_stamp, req):
        digest = self.hashes.get(path_stamp)
        if digest is None:
            digest = digest_copy(path, check=lambda: self._check(req))
            self.hashes.remember(path_stamp, digest)
        return digest

    def _render(self, req, mod_hash):
        base_hash = self._digest(req.original, req.signature[1], req) if req.original else ''
        key = cache_key(mod_hash, base_hash, req.game_root, req.signature[3])
        target = self.cache / (key + '.png')
        if valid_png(target) and not req.force and (not self.force_generation or key in self.regenerated):
            self._check(req)
            compact_preview(target)  # previews cached by older versions shrink once
            os.utime(target, ns=(time.time_ns(), target.stat().st_mtime_ns))
            return target, '已生成'
        with tempfile.TemporaryDirectory(prefix='render-', dir=self.cache) as folder:
            folder = Path(folder)
            (folder / OWNER_FILE).write_text(OWNER_VALUE, encoding='utf-8')
            # The mod is copied so enable/disable/delete never collide with the renderer's
            # open handle.  The original car is a game file the manager never renames; the
            # renderer opens it read-only (sharing reads) and its identity is checked after.
            copied = folder / 'mod.zip'
            if digest_copy(req.source, copied, lambda: self._check(req)) != mod_hash:
                # digest_copy already rejects files that change while being read, so a
                # mismatch here means the index was stale, not that the mod is broken.
                self.hashes.forget(req.signature[0])
                raise StaleHash()
            original = req.original
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
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                                      | getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0))
                self.process = proc
                started = time.monotonic()
                checks = 0
                try:
                    while proc.poll() is None:
                        self._check(req)
                        # Enumerating processes costs more than the cheap pause checks; about once a second.
                        if checks % 3 == 0 and self.running():
                            raise Paused()
                        checks += 1
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
            if original and stamp(original) != req.signature[1]:
                raise OSError(t('文件已变更'))
            if not valid_png(output):
                raise RuntimeError(t('渲染组件没有输出有效 PNG'))
            compact_preview(output)
            os.replace(output, target)
            prune_cache(self.cache, protected=(target,))
            self.regenerated.add(key)
            return target, '已生成'

    def _work(self):
        background_thread()
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
                result = (None, FAILURE_STATUS)
                self._log_error(req, exc)
            self.results.put((req, result))

    def _log_error(self, req, exc, context='Preview failed'):
        try:
            rotate_error_log(self.cache)
            with (self.cache / 'errors.log').open('a', encoding='utf-8') as f:
                f.write(f'{req.source.name}: {context}: {type(exc).__name__}: {exc}\n')
        except OSError:
            pass

    def close(self):
        with self.state_lock:
            self.closed.set()
            self.allowed.clear()
        proc = self.process
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        self.thread.join(timeout=2)
