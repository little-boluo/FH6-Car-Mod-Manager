"""Bound only manager-owned thumbnail files. Never walk game/mod directories."""
from pathlib import Path
import re
import shutil
import time

MAX_CACHE_BYTES = 256 * 1024 * 1024
MAX_CACHE_AGE = 30 * 24 * 3600
STALE_JOB_AGE = 24 * 3600
PNG_NAME = re.compile(r'^[0-9a-f]{64}\.png$')
JOB_NAME = re.compile(r'^render-[a-z0-9_]{8}$')
OWNER_FILE = '.fh6mm-owner'
OWNER_VALUE = 'FH6CarModManager thumbnail job v1'


def _redirected(path):
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except OSError:
        return True


def prune_cache(cache, *, protected=(), max_bytes=MAX_CACHE_BYTES, max_age=MAX_CACHE_AGE, now=None):
    cache = Path(cache)
    if _redirected(cache): return
    now = time.time() if now is None else now
    protected = {Path(p) for p in protected}
    entries = []
    for p in cache.glob('*.png'):
        if not PNG_NAME.fullmatch(p.name) or _redirected(p) or not p.is_file(): continue
        try:
            st = p.stat()
            if p not in protected and now-st.st_atime > max_age:
                p.unlink()
            else: entries.append((st.st_atime, st.st_size, p))
        except OSError: pass
    total = sum(size for _, size, _ in entries)
    for _, size, p in sorted(entries):
        if total <= max_bytes: break
        if p in protected: continue
        try:
            p.unlink(); total -= size
        except OSError: pass


def cleanup_stale_jobs(cache, *, now=None):
    cache = Path(cache)
    if _redirected(cache): return
    now = time.time() if now is None else now
    for p in cache.iterdir():
        if not JOB_NAME.fullmatch(p.name) or _redirected(p) or not p.is_dir(): continue
        marker = p / OWNER_FILE
        try:
            if _redirected(marker) or not marker.is_file(): continue
            if now-marker.stat().st_mtime < STALE_JOB_AGE: continue
            if marker.read_text(encoding='utf-8') != OWNER_VALUE: continue
            # Do not follow directory links, junctions or files redirected outside the job.
            if any(child.is_symlink() or bool(getattr(child.lstat(), 'st_file_attributes', 0) & 0x400)
                   for child in p.rglob('*')): continue
            shutil.rmtree(p)
        except OSError: pass


def rotate_error_log(cache):
    if _redirected(Path(cache)): return
    log = Path(cache)/'errors.log'
    try:
        if not log.is_symlink() and log.is_file() and log.stat().st_size > 2*1024*1024:
            previous = log.with_name('errors.previous.log')
            if not previous.is_symlink(): log.replace(previous)
    except OSError: pass
