"""Manage ZIP files in place. ZIP contents are never unpacked or edited."""
from __future__ import annotations
from i18n import t
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import uuid
from time import monotonic

SUFFIX = re.compile(r'^(.*)__fh6mm_v([1-9][0-9]*)$', re.I)


class ModError(Exception):
    pass


def sha256(path, progress=None):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
            if progress:
                progress(len(block))
    return h.hexdigest()


def atomic_json(path, data):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix='.fh6mm-json-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


class FileLock:
    def __init__(self, path):
        self.file = open(path, 'a+b')
        if self.file.seek(0, 2) == 0:
            self.file.write(b'0')
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise ModError(t('另一个管理器正在操作该目录，请稍后重试。')) from exc

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def regular(path):
    info = Path(path).lstat()
    return stat.S_ISREG(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & 0x400)


def valid_name(name):
    if (not name or name in ('.', '..') or name.endswith((' ', '.'))
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)):
        raise ModError(t('文件名不适用于 Windows：') + name)
    base = name.split('.')[0].upper()
    if base in {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} or re.fullmatch(r'(COM|LPT)[1-9¹²³]', base):
        raise ModError(t('Windows 保留文件名：') + name)
    return name


@dataclass(frozen=True)
class Mod:
    filename: str
    base: str
    variant: int
    enabled: bool
    size: int
    modified: float

    @property
    def group(self):
        return self.base.casefold()


def parse_filename(filename):
    low = filename.casefold()
    if low.endswith('.zipdisabled'):
        stem, enabled = filename[:-12], False
    elif low.endswith('.zip'):
        stem, enabled = filename[:-4], True
    else:
        return None
    if not stem:
        return None
    match = SUFFIX.fullmatch(stem)
    if match and match[1]:
        return match[1], int(match[2]), enabled
    return stem, 0, enabled


def match_vehicle(filename, catalog):
    """Return the game's original car file name for an import, or None.

    An exact (case-insensitive) match wins.  Otherwise the file name must start
    with a car name followed by a separator, as in browser copies such as
    ``Example_Car (1).zip``; the longest such car name is used, so a longer
    car name is never mistaken for a shorter one, and ``Example_Car2.zip``
    never matches ``Example_Car.zip``.
    """
    key = filename.casefold()
    if key in catalog:
        return catalog[key]
    if not key.endswith('.zip'):
        return None
    stem, best = key[:-4], None
    for low, original in catalog.items():
        if not low.endswith('.zip'):
            continue
        prefix = low[:-4]
        if (prefix and len(stem) > len(prefix) and stem.startswith(prefix)
                and not stem[len(prefix)].isalnum() and (best is None or len(prefix) > len(best[0]))):
            best = (prefix, original)
    return best[1] if best else None


@dataclass(frozen=True)
class GameLayout:
    platform: str
    exe: Path
    mods: Path
    vehicles: Path

    @property
    def label(self):
        return {'steam': t('Steam 版'), 'xbox': t('Xbox 版'), 'root': t('根目录布局')}[self.platform]


def layout_from_exe(exe):
    exe = Path(exe).absolute()
    if exe.name.casefold() != 'forzahorizon6.exe' or not exe.is_file():
        raise ModError(t('没有找到有效的 forzahorizon6.exe。'))
    root = exe.parent
    if root.name.casefold() == 'content':
        platform = 'xbox'
    elif root.parent.name.casefold() == 'common' and root.parent.parent.name.casefold() == 'steamapps':
        platform = 'steam'
    else:
        platform = 'root'
    return GameLayout(platform, exe, root / 'mediapc' / ('Cars' if platform == 'xbox' else 'cars'),
                      root / 'media' / 'cars')


def cars_from_exe(exe):
    folder = layout_from_exe(exe).mods
    folder.mkdir(parents=True, exist_ok=True)
    return folder.resolve()


class Manager:
    def __init__(self, folder, vehicles=None):
        self.folder = Path(folder).resolve()
        if not self.folder.is_dir():
            raise ModError(t('模组目录不存在。'))
        if vehicles:
            self.vehicles = Path(vehicles).resolve()
        elif self.folder.name.casefold() == 'cars' and self.folder.parent.name.casefold() == 'mediapc':
            self.vehicles = self.folder.parent.parent / 'media' / 'cars'
        else:
            self.vehicles = None
        self.journal = self.folder / '.fh6mm-transaction.json'

    def vehicle_catalog(self):
        if self.vehicles is None or not self.vehicles.is_dir():
            raise ModError(t('找不到原版车辆文件目录，已拒绝导入。请选择游戏 EXE 所在目录下的 media\\cars。'))
        if self.vehicles.resolve() == self.folder:
            raise ModError(t('车辆校验目录不能与模组安装目录相同，请选择 EXE 同级的 media\\cars，而不是 mediapc\\cars。'))
        try:
            return {p.name.casefold(): p.name for p in self.vehicles.iterdir() if regular(p)}
        except OSError as exc:
            raise ModError(t('无法读取原版车辆目录，已拒绝导入：') + str(self.vehicles)) from exc

    def scan(self):
        rows = []
        for p in self.folder.iterdir():
            parsed = parse_filename(p.name)
            if parsed is None:
                continue
            try:
                if not regular(p):
                    continue
                info = p.stat()
            except FileNotFoundError:
                continue
            rows.append(Mod(p.name, *parsed[:2], parsed[2], info.st_size, info.st_mtime))
        return sorted(rows, key=lambda m: (m.group, not m.enabled, m.variant, m.filename.casefold()))

    def get(self, filename):
        for m in self.scan():
            if m.filename == filename:
                return m
        raise ModError(t('该文件已被移动或重命名，请刷新列表。'))

    def path(self, name):
        return self.folder / valid_name(name)

    def names(self):
        return {p.name.casefold(): p.name for p in self.folder.iterdir()}

    def next_disabled(self, base, occupied, preferred=None):
        if preferred and preferred.casefold() not in occupied:
            return preferred
        index = 1
        while True:
            name = f'{base}__fh6mm_v{index}.zipdisabled'
            if name.casefold() not in occupied:
                return name
            index += 1

    @contextmanager
    def mutation(self, recovery=False):
        with FileLock(self.folder / '.fh6mm.lock'):
            if self.journal.exists() and not recovery:
                raise ModError(t('上次切换未完成，请先点击「恢复中断切换」。'))
            yield

    def move(self, source, target):
        # Windows rename refuses to overwrite an existing destination.
        if target.name.casefold() in self.names():
            raise ModError(t('目标名称已被占用，未覆盖：') + target.name)
        os.rename(source, target)

    def transaction(self, moves):
        moves = [(a, b) for a, b in moves if a != b]
        if not moves:
            return
        sources = {a.casefold() for a, _ in moves}
        targets = [b.casefold() for _, b in moves]
        if len(sources) != len(moves) or len(set(targets)) != len(targets):
            raise ModError(t('检测到重复的文件操作。'))
        occupied = self.names()
        for source, target in moves:
            valid_name(source)
            valid_name(target)
            if target.casefold() in occupied and target.casefold() not in sources:
                raise ModError(t('目标名称已存在：') + target)
        records = []
        for source, target in moves:
            p = self.path(source)
            if not regular(p):
                raise ModError(t('不能操作链接或非常规文件：') + source)
            records.append({'source': source, 'target': target,
                            'temp': '.fh6mm-switch-' + uuid.uuid4().hex + '.tmp',
                            'sha256': sha256(p)})
        tx = {'schema': 1, 'phase': 'collect', 'files': records}
        atomic_json(self.journal, tx)
        # On failure, preserve the journal and all bytes. Recovery rolls forward.
        self._finish(tx)

    def _finish(self, tx):
        if tx.get('schema') != 1 or tx.get('phase') not in ('collect', 'distribute'):
            raise ModError(t('无法识别中断记录，请保留目录中的文件。'))
        records = tx['files']
        for rec in records:
            for key in ('source', 'target', 'temp'):
                valid_name(rec[key])
        if tx['phase'] == 'collect':
            # Preflight the entire collection phase before moving anything.
            for rec in records:
                source, temp = self.path(rec['source']), self.path(rec['temp'])
                if temp.exists() and source.exists():
                    raise ModError(t('切换路径被外部占用，请保留文件并检查：') + rec['source'])
                p = temp if temp.exists() else source
                if not p.exists() or not regular(p) or sha256(p) != rec['sha256']:
                    raise ModError(t('切换文件缺失或被修改：') + rec['source'])
            for rec in records:
                temp = self.path(rec['temp'])
                if not temp.exists():
                    self.move(self.path(rec['source']), temp)
            tx['phase'] = 'distribute'
            atomic_json(self.journal, tx)
        for rec in records:
            temp, target = self.path(rec['temp']), self.path(rec['target'])
            if temp.exists():
                if target.name.casefold() in self.names():
                    raise ModError(t('切换目标被外部文件占用：') + rec['target'])
                p = temp
            else:
                p = target
            if not p.exists() or not regular(p) or sha256(p) != rec['sha256']:
                raise ModError(t('切换文件缺失或被修改：') + rec['target'])
        for rec in records:
            temp, target = self.path(rec['temp']), self.path(rec['target'])
            if temp.exists():
                self.move(temp, target)
        self.journal.unlink()

    def recover(self):
        with self.mutation(recovery=True):
            if not self.journal.exists():
                return t('没有待恢复的切换。')
            tx = json.loads(self.journal.read_text(encoding='utf-8'))
            self._finish(tx)
            return t('中断的切换已完成，全部文件已恢复为目标名称。')

    def enable(self, filename):
        with self.mutation():
            chosen = self.get(filename)
            group = [m for m in self.scan() if m.group == chosen.group]
            active = [m for m in group if m.enabled and m.filename != filename]
            canonical = chosen.base + '.zip'
            if chosen.enabled and chosen.filename == canonical and not active:
                return canonical
            occupied = set(self.names())
            occupied.discard(chosen.filename.casefold())
            for m in active:
                occupied.discard(m.filename.casefold())
            occupied.add(canonical.casefold())
            moves = []
            # Transfer the selected disabled suffix/name to the old active ZIP.
            preferred = chosen.filename if not chosen.enabled else None
            for m in active:
                target = self.next_disabled(chosen.base, occupied, preferred)
                occupied.add(target.casefold())
                preferred = None
                moves.append((m.filename, target))
            moves.append((chosen.filename, canonical))
            self.transaction(moves)
            return canonical

    def disable(self, filename):
        with self.mutation():
            m = self.get(filename)
            if not m.enabled:
                return m.filename
            occupied = set(self.names())
            name = m.filename[:-4] + '.zipdisabled'
            if name.casefold() in occupied:
                name = self.next_disabled(m.base, occupied)
            self.transaction([(m.filename, name)])
            return name

    def delete(self, filename, recycler=None, expected=None):
        """Delete exactly one listed file via the Windows Recycle Bin API."""
        if recycler is None:
            from windows_recycle import recycle_file
            recycler = recycle_file
        with self.mutation():
            m = self.get(filename)
            source = self.path(m.filename)
            if not regular(source):
                raise ModError(t('仅允许删除模组列表中的实际文件。'))
            if expected is not None and (m.size, m.modified) != expected:
                raise ModError(t('确认期间所选文件发生变化，未删除；请刷新后重新选择。'))
            recycler(source)
            if source.exists():
                raise ModError(t('删除未完成，文件仍在原目录。'))
            return m.filename

    def import_files(self, paths, progress=None):
        paths = list(paths)
        result = {'imported': [], 'skipped': [], 'errors': [], 'renamed': []}
        # Reload every batch; the base game's car list can change after updates.
        catalog = self.vehicle_catalog()
        weights = []
        for raw in paths:
            try:
                weights.append(max(1, Path(raw).stat().st_size) * 3)
            except OSError:
                weights.append(3)
        total, completed = sum(weights), 0
        last_report = 0.0
        def notify(value, name, index, phase, force=False):
            nonlocal last_report
            now = monotonic()
            if progress and (force or now-last_report >= .04):
                progress(value, total, name, index, len(paths), phase)
                last_report = now
        with self.mutation():
            for index, raw in enumerate(paths, 1):
                source = Path(raw).absolute()
                file_weight = weights[index-1]
                phase_bytes = 0
                def advance(amount):
                    nonlocal phase_bytes
                    phase_bytes += amount
                    notify(completed + min(file_weight-1, phase_bytes), source.name, index, phase)
                phase = 'hash'
                notify(completed, source.name, index, phase, True)
                try:
                    valid_name(source.name)
                    if source.suffix.casefold() != '.zip' or not regular(source):
                        raise ModError(t('请选择实际 ZIP 文件；不要拖入文件夹或压缩包内的虚拟文件。'))
                    original_name = match_vehicle(source.name, catalog)
                    if original_name is None:
                        raise ModError(t('文件名开头未匹配游戏 media\\cars 中的任何车辆文件，拒绝导入。文件名须以原始车辆文件名开头（如 Example_Car.zip 或 Example_Car (1).zip）。'))
                    parsed = parse_filename(source.name)
                    if parsed is None:
                        raise ModError(t('ZIP 文件名缺少名称。'))
                    in_place = source.parent.resolve() == self.folder
                    if in_place and parsed[0].casefold() == original_name[:-4].casefold():
                        result['skipped'].append(source.name + t('：已经在模组目录中'))
                        continue
                    base = original_name[:-4]
                    group = [m for m in self.scan() if m.group == base.casefold()]
                    if group:
                        base = group[0].base
                    occupied = set(self.names())
                    if not group and (base + '.zip').casefold() not in occupied:
                        dest_name = base + '.zip'
                    else:
                        dest_name = self.next_disabled(base, occupied)
                    valid_name(dest_name)
                    if in_place:
                        # A download copy such as "Example_Car (1).zip" already sits in the mod
                        # folder, where the game ignores it: give it the manager's name instead.
                        self.move(source, self.path(dest_name))
                        result['imported'].append(dest_name)
                        result['renamed'].append(f'{source.name} → {dest_name}')
                        continue
                    if shutil.disk_usage(self.folder).free < source.stat().st_size:
                        raise ModError(t('目标磁盘空间不足。'))
                    before = source.stat()
                    source_hash = sha256(source, advance) if progress else sha256(source)
                    fd, temp_name = tempfile.mkstemp(prefix='.fh6mm-import-', suffix='.tmp', dir=self.folder)
                    temp = Path(temp_name)
                    try:
                        with os.fdopen(fd, 'wb') as out, source.open('rb') as inp:
                            phase = 'copy'
                            notify(completed + phase_bytes, source.name, index, phase, True)
                            if progress:
                                for block in iter(lambda: inp.read(1024 * 1024), b''):
                                    out.write(block)
                                    advance(len(block))
                            else:
                                shutil.copyfileobj(inp, out, 1024 * 1024)
                            out.flush()
                            os.fsync(out.fileno())
                        after = source.stat()
                        phase = 'verify'
                        notify(completed + phase_bytes, source.name, index, phase, True)
                        copied_hash = sha256(temp, advance) if progress else sha256(temp)
                        if copied_hash != source_hash or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                            raise ModError(t('复制时源文件发生变化，已取消本文件导入。'))
                        shutil.copystat(source, temp)
                        self.move(temp, self.path(dest_name))
                    finally:
                        temp.unlink(missing_ok=True)
                    result['imported'].append(dest_name)
                    if dest_name != source.name:
                        result['renamed'].append(f'{source.name} → {dest_name}')
                except (OSError, ModError) as exc:
                    result['errors'].append(source.name + '：' + str(exc))
                finally:
                    completed += file_weight
                    notify(completed, source.name, index, 'done', True)
        return result
