"""Scrollable, virtualised thumbnail cards; keeps selection API used by app actions.

Smoothness rules (PCL-style motion on a Tk canvas):
* Animation frames never touch the file system.  Thumbnail lookups and file
  stamps are refreshed only when ``redraw()`` signals new content; PNG decoding
  and downscaling run on a worker thread.
* Every card owns a fixed set of retained canvas items that are only
  reconfigured when a value changes, and card origins are whole pixels, so
  unchanged cards are never repainted and rounded corners never shimmer.
* Cards drop in from above with a slight overshoot (PCL page enter), removed
  cards shrink and fade, survivors glide to their new slots, and the wheel
  scrolls with additive Fluent tweens.
"""
from i18n import t
from collections import OrderedDict
from pathlib import Path
import importlib.util
import io
import math
import queue
import threading
import tkinter as tk
from tkinter import ttk, font
from ui_theme import (BG, PANEL, TEXT, MUTED, ACCENT, ACCENT_LIGHT, BLUE_5, SHADOW, GREEN, GREEN_BACK,
                      rounded_points, auto_hide)
import animation
from animation import (Animator, lerp_color, clamp01, linear, out_fluent, in_fluent, out_back,
                       WEAK, MIDDLE, STRONG)

PREVIEW_BG = '#131925'
LOCKED_TEXT = '#a0acba'


class RetainedCanvas:
    """Named canvas items that are created once and only touched when they change."""
    def __init__(self, canvas):
        self.canvas, self.objects, self.last, self.seen = canvas, {}, {}, set()
        self.group = ''

    def __getattr__(self, name):
        return getattr(self.canvas, name)

    def begin(self, group):
        self.group = group

    def item(self, name, kind, coords, **options):
        key = (self.group, name, kind)
        self.seen.add(key)
        coords = tuple(coords)
        item = self.objects.get(key)
        if item is None:
            item = self.objects[key] = getattr(self.canvas, 'create_' + kind)(*coords, **options)
            self.last[key] = (coords, dict(options))
            return item
        old_coords, old_options = self.last[key]
        if coords != old_coords:
            self.canvas.coords(item, *coords)
        changed = {k: v for k, v in options.items() if old_options.get(k, self) != v}
        if changed:
            self.canvas.itemconfigure(item, **changed)
            old_options.update(changed)
        self.last[key] = (coords, old_options)
        return item

    def finish(self):
        for key in self.objects.keys() - self.seen:
            self.canvas.delete(self.objects.pop(key))
            self.last.pop(key, None)
        self.seen.clear()


class PreviewLoader:
    """Decode and downscale thumbnails on a worker thread; Tk only parses raw PPM."""
    def __init__(self, size):
        self.size, self.pending = size, set()
        self.requests, self.results = queue.Queue(), queue.Queue()
        self.thread = None
        self.available = importlib.util.find_spec('PIL') is not None

    def request(self, key, path):
        if key in self.pending:
            return
        self.pending.add(key)
        self.requests.put((key, str(path)))
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name='preview-loader', daemon=True)
            self.thread.start()

    def _run(self):
        while True:
            item = self.requests.get()
            if item is None:
                return
            key, path = item
            try:
                data = self.decode(path, self.size)
            except Exception:  # unreadable or not an image: reported as a failed preview
                data = None
            self.results.put((key, data))

    @staticmethod
    def decode(path, size):
        from PIL import Image, ImageOps
        with Image.open(path) as image:
            image.draft('RGB', (size[0] * 2, size[1] * 2))
            image.load()
            if image.mode in ('RGBA', 'LA', 'P', 'PA'):
                image = image.convert('RGBA')
                backdrop = Image.new('RGB', image.size, PREVIEW_BG)
                backdrop.paste(image, mask=image.getchannel('A'))
                image = backdrop
            else:
                image = image.convert('RGB')
            resample = getattr(Image, 'Resampling', Image).LANCZOS
            image = ImageOps.contain(image, size, resample)
            buffer = io.BytesIO()
            image.save(buffer, 'PPM')
            return buffer.getvalue()

    def drain(self):
        while True:
            try:
                key, data = self.results.get_nowait()
            except queue.Empty:
                return
            self.pending.discard(key)
            yield key, data

    def close(self):
        self.requests.put(None)


# PCL page-enter curve: drop 16 px from above, 5 px with Fluent and 11 px with a
# Back overshoot, while the card fades in quickly.
ENTER_MS, ENTER_DROP = 350, 16
_drop_fluent, _drop_back, _fade_in = out_fluent(MIDDLE), out_back(MIDDLE), out_fluent(WEAK)
_exit_scale, _exit_fade = in_fluent(MIDDLE), out_fluent(WEAK)
_reflow = out_fluent(STRONG)


def enter_offset(progress):
    p = clamp01(progress)
    return -ENTER_DROP + 5 * _drop_fluent(min(1.0, p * ENTER_MS / 250)) + 11 * _drop_back(p)


def enter_alpha(progress):
    return _fade_in(min(1.0, clamp01(progress) * ENTER_MS / 160))


class ModGrid(ttk.Frame):
    CARD_W, CARD_H, GAP = 360, 286, 12
    PREVIEW_W, PREVIEW_H = 342, 192
    WHEEL_PX = 120  # smooth-scroll distance per mouse-wheel notch
    EXIT_MS, GHOST_MS, REFLOW_MS = 200, 160, 250

    def __init__(self, parent, thumbnail, on_select, on_toggle):
        super().__init__(parent)
        self.thumbnail, self.on_select, self.on_toggle = thumbnail, on_select, on_toggle
        self.items, self.images = OrderedDict(), OrderedDict()
        self.image_stamps = {}
        self.chosen, self.disabled, self.columns = None, False, 1
        self.hovered = None
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, takefocus=True)
        self.scroll = ttk.Scrollbar(self, command=self._scroll)
        self.canvas.configure(yscrollcommand=auto_hide(self.scroll))
        self.scroll.pack(side='right', fill='y')
        self.canvas.pack(fill='both', expand=True)
        self.text_font = font.Font(family='Microsoft YaHei UI', size=10)
        self.name_font = font.Font(family='Microsoft YaHei UI', size=10, weight='bold')
        self.canvas.bind('<Configure>', self._resized)
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.canvas.bind('<Button-4>', lambda e: self._wheel(e, -1))
        self.canvas.bind('<Button-5>', lambda e: self._wheel(e, 1))
        self.canvas.bind('<Button-1>', self._click)
        self.canvas.bind('<Double-1>', self._double)
        self.canvas.bind('<Key>', self._key)
        self.canvas.bind('<Motion>', self._hover)
        self.canvas.bind('<Leave>', lambda _: self._hover(None))
        self.painter = RetainedCanvas(self.canvas)
        self.positions, self._frame_images, self._line_cache = {}, [], {}
        self._ids, self._ghosts, self._exiting = None, OrderedDict(), None
        self._laid_out = False
        self._x_offset = 0  # the grid is centred when columns do not fill the width
        self._redraw_id = None
        self.anim = Animator(self.canvas, self._on_frame)
        self.anim.set('lock', 0.0)
        self._removed, self._new_count, self._release_job = set(), 0, None
        self._scroll_total, self._last_size, self._region = 1, None, None
        self._generation, self._thumbs, self._failed = 0, {}, {}
        self.loader, self._loader_job = PreviewLoader((self.PREVIEW_W, self.PREVIEW_H)), None

    # -- scheduling --
    def _resized(self, event):
        if (event.width, event.height) != self._last_size:  # ignore pure moves (page transitions)
            self._last_size = (event.width, event.height)
            self._request_draw()

    def _max_scroll(self):
        return max(0, self._scroll_total - self.canvas.winfo_height())

    def _on_frame(self):
        if 'scroll' in self.anim.values and self.anim.active('scroll'):
            y = self.anim.values['scroll'] = min(max(0.0, self.anim.values['scroll']), self._max_scroll())
            self.canvas.yview_moveto(round(y) / max(1, self._scroll_total))
        self._request_draw()

    def redraw(self):
        """Content may have changed (thumbnails, files, lock state): re-read it on the next draw."""
        self._generation += 1
        self._request_draw()

    def _request_draw(self):
        if self._redraw_id is None:
            self._redraw_id = self.after_idle(self._draw)

    def _schedule_release(self):
        if self._release_job is None:
            self._release_job = self.after(250, self._release)

    def _release(self):
        """End of a delete/insert batch: forget animation state of cards that are gone."""
        self._release_job = None
        self._removed.clear()
        self._new_count = 0
        self._forget_stale()

    def _forget_stale(self):
        for key in [k for k in self.anim.values if isinstance(k, tuple)
                    and k[1] not in self.items and k[1] not in self._ghosts]:
            self.anim.forget(key)
        for iid in [i for i in self._thumbs if i not in self.items and i not in self._ghosts]:
            self._thumbs.pop(iid, None)

    def _changed(self):
        self._ids = None

    def _id_list(self):
        if self._ids is None:
            self._ids = list(self.items)
        return self._ids

    # -- Treeview-like API used by the application --
    def selection(self):
        return (self.chosen,) if self.chosen in self.items else ()

    def selection_set(self, iid):
        if iid in self.items:
            old, self.chosen = self.chosen, iid
            if old != iid:
                if old is not None:
                    self.anim.to(('sel', old), 0.0, 200, start=self.anim.get(('sel', old), 1.0))
                self.anim.to(('sel', iid), 1.0, 200, start=self.anim.get(('sel', iid), 0.0))
            self._request_draw()
            self.on_select()

    def get_children(self):
        return tuple(self.items)

    def exists(self, iid):
        return iid in self.items

    def delete(self, *ids):
        for iid in ids:
            if self.items.pop(iid, None) is not None:
                self._removed.add(iid)  # a re-insert within the batch window is a refresh, not a new card
        self._changed()
        self._schedule_release()
        self._request_draw()

    def insert(self, parent, index, iid, values, tags=()):
        fresh = iid not in self.items and iid not in self._removed
        self.items[iid] = (values, tags)
        self._changed()
        enabled = 1.0 if 'enabled' in tags else 0.0
        if fresh:  # staggered drop-in entrance
            delay = min(self._new_count, 12) * 25
            self._new_count += 1
            self.anim.set(('en', iid), enabled)
            self.anim.to(('enter', iid), 1.0, ENTER_MS, linear, delay=delay, start=0.0)
        else:
            previous = self.anim.get(('en', iid), enabled)
            if previous != enabled:  # enabled/disabled flipped: fade the badge and pulse the border
                self.anim.to(('en', iid), enabled, 320, start=previous)
                self.anim.to(('pulse', iid), 0.0, 800, start=1.0)
        self._schedule_release()
        self._request_draw()

    def _slot(self, index, columns=None):
        row, col = divmod(index, columns or self.columns)
        return col * (self.CARD_W + self.GAP), row * (self.CARD_H + self.GAP)

    def replace(self, entries):
        """Apply a complete data snapshot without clearing unchanged cards."""
        previous = self.items
        self.items = OrderedDict((iid, (values, tags)) for iid, values, tags in entries)
        self._changed()
        visible_row = max(0, int(self.canvas.canvasy(0) // (self.CARD_H + self.GAP)))
        stagger = 0
        for i, (iid, (values, tags)) in enumerate(self.items.items()):
            enabled = 1.0 if 'enabled' in tags else 0.0
            ghost = self._ghosts.pop(iid, None)
            if ghost is not None:  # came back while fading out: continue from where it is
                self.anim.cancel(('gone', iid))
                self.anim.forget(('gone', iid))
                self.positions.setdefault(iid, ghost[2])
            elif iid not in previous:
                self.anim.set(('en', iid), enabled)
                # Only cards near the viewport enter; offscreen cards need no timers.
                row = i // self.columns
                if visible_row <= row <= visible_row + 3:
                    self.anim.to(('enter', iid), 1.0, ENTER_MS, linear, delay=min(stagger, 8) * 25, start=0.0)
                    stagger += 1
                else:
                    self.anim.set(('enter', iid), 1.0)
            elif previous[iid][1] != tags:
                self.anim.to(('en', iid), enabled, 230)
                self.anim.to(('pulse', iid), 0.0, 450, start=.65)
            if iid in self.positions:
                old_x, old_y = self.positions[iid]
                target_x, target_y = self._slot(i)
                if (round(old_x), round(old_y)) != (target_x, target_y):
                    self.anim.to(('x', iid), target_x, self.REFLOW_MS, _reflow, start=old_x)
                    self.anim.to(('y', iid), target_y, self.REFLOW_MS, _reflow, start=old_y)
        # Cards that left a visible slot fade out where they stood.
        for iid in previous:
            if iid not in self.items and iid in self.positions and iid not in self._ghosts:
                if not animation.ENABLED or iid == self._exiting:
                    continue
                self._ghosts[iid] = (previous[iid][0], previous[iid][1], self.positions[iid])
                self.anim.to(('gone', iid), 1.0, self.GHOST_MS, linear, start=self.anim.get(('exit', iid), 0.0),
                             done=lambda iid=iid: self._bury(iid))
        self._forget_stale()
        self._request_draw()

    def _bury(self, iid):
        self._ghosts.pop(iid, None)
        if iid not in self.items:
            for key in ('gone', 'exit', 'enter', 'hover', 'sel', 'en', 'pulse', 'x', 'y'):
                self.anim.forget((key, iid))
        self._request_draw()

    def animate_remove(self, iid, done):
        if iid not in self.items or not self.winfo_ismapped():
            done()
            return
        def finish():
            self.items.pop(iid, None)
            self._changed()
            self._exiting = None
            self.anim.forget(('exit', iid))
            self._request_draw()
            done()
        self._exiting = iid
        # PCL card removal: shrink slightly while fading out.
        self.anim.to(('exit', iid), 1.0, self.EXIT_MS, linear, start=0.0, done=finish)

    def state(self, states):
        disabled = 'disabled' in states
        if disabled != self.disabled:
            self.disabled = disabled
            self.anim.to('lock', 1.0 if disabled else 0.0, 200)
            if disabled and self.hovered is not None:
                self._hover(None)
            self._request_draw()

    def tag_configure(self, *args, **kwargs):
        pass  # Colours are painted centrally, including the locked state.

    def see(self, iid):
        if iid not in self.items:
            return
        index = self._id_list().index(iid)
        pitch = self.CARD_H + self.GAP
        view = self.canvas.winfo_height()
        total = max(view, math.ceil(len(self.items) / self.columns) * pitch)
        self._scroll_total = total
        top, row_y = self.canvas.canvasy(0), (index // self.columns) * pitch
        if top <= row_y and row_y + self.CARD_H <= top + view:
            return  # already fully visible
        # Scroll just far enough: align the row to the top when it is above, to the bottom when below.
        target = row_y if row_y < top else row_y + self.CARD_H + self.GAP - view
        target = min(max(0, target), max(0, total - view))
        self.anim.to('scroll', target, 320, out_fluent(STRONG), start=top)
        if not self.anim.active('scroll'):  # animations off, or already there: jump
            self.canvas.yview_moveto(target / total)
        self._request_draw()

    def _scroll(self, *args):
        self.anim.cancel('scroll')  # the scrollbar thumb or keyboard takes over from smooth scrolling
        self.canvas.yview(*args)
        self._request_draw()

    def _wheel(self, event, direction=None):
        if self.disabled:
            return 'break'
        sign = direction if direction is not None else (-1 if event.delta > 0 else 1)
        if not animation.ENABLED:
            self._scroll('scroll', sign, 'units')
            return 'break'
        notches = 1 if direction is not None else max(.25, abs(event.delta) / 120)  # touchpads send small deltas
        if not self.anim.active('scroll'):
            self.anim.set('scroll', self.canvas.canvasy(0))
        # PCL MyScrollViewer: each notch is its own additive Fluent tween.
        self.anim.add('scroll', sign * notches * self.WHEEL_PX, 300, out_fluent(6))
        return 'break'

    # -- input --
    def _hit(self, event):
        x, y = self.canvas.canvasx(event.x) - self._x_offset, self.canvas.canvasy(event.y)
        if x < 0:
            return None
        col, row = int(x // (self.CARD_W + self.GAP)), int(y // (self.CARD_H + self.GAP))
        if col >= self.columns or x % (self.CARD_W + self.GAP) >= self.CARD_W or y % (self.CARD_H + self.GAP) >= self.CARD_H:
            return None
        index = row * self.columns + col
        ids = self._id_list()
        return ids[index] if 0 <= index < len(ids) else None

    def _click(self, event):
        if self.disabled:
            return 'break'
        self.canvas.focus_set()
        iid = self._hit(event)
        if iid:
            self.selection_set(iid)

    def _hover(self, event):
        hovered = self._hit(event) if event is not None and not self.disabled else None
        if hovered != self.hovered:
            old, self.hovered = self.hovered, hovered
            if old is not None:
                self.anim.to(('hover', old), 0.0, 200, start=self.anim.get(('hover', old), 1.0))
            if hovered is not None:
                self.anim.to(('hover', hovered), 1.0, 120, start=self.anim.get(('hover', hovered), 0.0))
            self.canvas.configure(cursor='hand2' if hovered else '')
            self._request_draw()

    def _double(self, event):
        if not self.disabled and self._hit(event):
            self.selection_set(self._hit(event))
            self.on_toggle()
        return 'break'

    def _key(self, event):
        if self.disabled:
            return 'break'
        if event.keysym in ('space', 'Return'):
            self.on_toggle()
        elif event.keysym in ('Left', 'Right', 'Up', 'Down') and self.items:
            ids = self._id_list()
            i = ids.index(self.chosen) if self.chosen in ids else 0
            delta = {'Left': -1, 'Right': 1, 'Up': -self.columns, 'Down': self.columns}[event.keysym]
            self.selection_set(ids[max(0, min(len(ids)-1, i+delta))])
            self.see(self.chosen)
        return 'break'

    def destroy(self):
        self.anim.stop()
        self.loader.close()
        for job in ('_release_job', '_redraw_id', '_loader_job'):
            if getattr(self, job) is not None:
                self.after_cancel(getattr(self, job))
                setattr(self, job, None)
        super().destroy()

    # -- thumbnails --
    def _thumb(self, iid):
        """(path, status, stamp) for a card; file system access only once per content generation."""
        entry = self._thumbs.get(iid)
        if entry is None or entry[0] != self._generation:
            path, status = self.thumbnail(iid)
            stamp = None
            if path:
                try:
                    info = Path(path).stat()
                    stamp = (info.st_mtime_ns, info.st_size)
                except OSError:
                    stamp = None
            entry = self._thumbs[iid] = (self._generation, path, status, stamp)
        return entry[1:]

    def _image(self, path, stamp):
        """Return (image, failed).  Missing images are requested from the loader."""
        key = str(path)
        if stamp is None:
            self.images.pop(key, None)
            return None, True
        if self.image_stamps.get(key) != stamp:
            self.images.pop(key, None)
        image = self.images.get(key)
        if image is not None:
            self.images.move_to_end(key)
            return image, False
        if self._failed.get(key) == stamp:
            return None, True
        if not self.loader.available:  # no Pillow: decode in place, as before
            return self._load_inline(key, stamp)
        self.loader.request((key, stamp), path)
        if self._loader_job is None:
            self._loader_job = self.after(12, self._collect)
        return None, False

    def _load_inline(self, key, stamp):
        try:
            full = tk.PhotoImage(master=self, file=key)
            factor = max(1, math.ceil(full.width()/self.PREVIEW_W), math.ceil(full.height()/self.PREVIEW_H))
            image = full.subsample(factor, factor)
        except (tk.TclError, OSError):
            self._failed[key] = stamp
            return None, True
        self.images[key], self.image_stamps[key] = image, stamp
        return image, False

    def _collect(self):
        self._loader_job = None
        arrived = False
        for (key, stamp), data in self.loader.drain():
            arrived = True
            if data is None:
                self._failed[key] = stamp
                continue
            try:
                image = tk.PhotoImage(master=self, data=data, format='ppm')
            except tk.TclError:
                self._failed[key] = stamp
                continue
            self.images[key], self.image_stamps[key] = image, stamp
            self._failed.pop(key, None)
        if arrived:
            self._request_draw()
        if self.loader.pending:
            self._loader_job = self.after(12, self._collect)

    def _lines(self, text, width):
        if text in self._line_cache:
            return self._line_cache[text]
        lines, part = [], ''
        for char in text:
            if self.text_font.measure(part + char) > width and part:
                lines.append(part)
                part = ''
            part += char
        lines.append(part)
        if len(lines) > 2:
            lines = lines[:2]
            while self.text_font.measure(lines[-1] + '…') > width:
                lines[-1] = lines[-1][:-1]
            lines[-1] += '…'
        result = self._line_cache[text] = '\n'.join(lines)
        return result

    # -- painting --
    def _draw(self):
        self._redraw_id = None
        c = self.painter
        width, view = c.winfo_width(), c.winfo_height()
        pitch = self.CARD_H + self.GAP
        columns = max(1, (width + self.GAP) // (self.CARD_W + self.GAP))
        if columns != self.columns:
            if self.positions and animation.ENABLED and self._laid_out:
                # Window resized across a column boundary: glide cards to their new slots.
                index = {iid: i for i, iid in enumerate(self._id_list())}
                for iid, (old_x, old_y) in self.positions.items():
                    if iid in index:
                        tx, ty = self._slot(index[iid], columns)
                        self.anim.to(('x', iid), tx, self.REFLOW_MS, _reflow, start=old_x)
                        self.anim.to(('y', iid), ty, self.REFLOW_MS, _reflow, start=old_y)
            self.columns = columns
        # Before the canvas has its real size there is no layout worth animating from.
        self._laid_out = width > self.CARD_W
        self._x_offset = max(0, (width - columns * (self.CARD_W + self.GAP) + self.GAP) // 2)
        height = max(view, math.ceil(len(self.items) / columns) * pitch)
        region = (0, 0, width, height)
        if region != self._region:  # reconfiguring the canvas repaints all of it
            self._region = region
            c.configure(scrollregion=region)
        self._scroll_total = height
        top = c.canvasy(0)
        first, last = max(0, int(top // pitch)), int((top + view) // pitch) + 1
        lock = self.anim.get('lock')
        frame_images, positions = [], {}

        c.begin('_empty')
        if not self.items:
            if not self.anim.active('empty') and self.anim.get('empty', 0.0) < 1.0:
                self.anim.to('empty', 1.0, ENTER_MS, linear, start=0.0)
            e = self.anim.get('empty', 1.0)
            a, dy = enter_alpha(e), round(enter_offset(e))
            c.item('title', 'text', (width/2, 90 + dy), text=t('这里还没有模组'), fill=lerp_color(BG, TEXT, a),
                   font=('Microsoft YaHei UI', 16, 'bold'))
            c.item('hint', 'text', (width/2, 125 + dy), text=t('拖入车辆 ZIP，或调整搜索与筛选条件'),
                   fill=lerp_color(BG, MUTED, a), font=self.text_font)
        else:
            self.anim.forget('empty')

        for iid, (values, tags, (gx, gy)) in list(self._ghosts.items()):
            row = int(gy // pitch)
            if first - 1 <= row <= last + 1:
                gone = self.anim.get(('gone', iid), 1.0)
                self._card(c, iid, values, tags, gx, gy, 1.0, gone, lock, frame_images)

        for i, (iid, (values, tags)) in enumerate(self.items.items()):
            row, col = divmod(i, columns)
            moving = self.anim.active(('x', iid)) or self.anim.active(('y', iid))
            if not first <= row <= last and not moving:
                continue
            enter = self.anim.get(('enter', iid), 1.0)
            if enter <= 0.001:  # waiting for its stagger delay
                continue
            base_x, base_y = col * (self.CARD_W + self.GAP), row * pitch
            x = self.anim.get(('x', iid), base_x) if self.anim.active(('x', iid)) else base_x
            y = self.anim.get(('y', iid), base_y) if self.anim.active(('y', iid)) else base_y
            if not first - 1 <= int(y // pitch) <= last:
                continue
            positions[iid] = (x, y)
            self._card(c, iid, values, tags, x, y, enter, self.anim.get(('exit', iid)), lock, frame_images)
        c.finish()
        self.positions, self._frame_images = positions, frame_images
        while len(self.images) > 96:
            key, _ = self.images.popitem(last=False)
            self.image_stamps.pop(key, None)

    def _card(self, c, iid, values, tags, bx, by, enter, exit_progress, lock, frame_images):
        c.begin(iid)
        W, H = self.CARD_W, self.CARD_H
        enabled = 'enabled' in tags
        hover = 0.0 if self.disabled else self.anim.get(('hover', iid), 0.0)
        sel = self.anim.get(('sel', iid), 1.0 if iid == self.chosen else 0.0)
        en = self.anim.get(('en', iid), 1.0 if enabled else 0.0)
        pulse = self.anim.get(('pulse', iid), 0.0)
        alpha = enter_alpha(enter) * (1 - _exit_fade(exit_progress))
        scale = 1 - .08 * _exit_scale(exit_progress)
        # Whole-pixel origin: the card is translated rigidly, never re-rasterised.
        lift = round(hover * 2)
        ox, oy = round(bx) + self._x_offset, round(by + enter_offset(enter)) - lift
        cx, cy = ox + W / 2, oy + H / 2

        def at(px, py):
            return round(cx + (px - W / 2) * scale), round(cy + (py - H / 2) * scale)

        def fade(color):
            return lerp_color(BG, color, alpha)

        def locked(color, muted=LOCKED_TEXT):
            return lerp_color(color, muted, lock)

        # PCL MyCard: white, 6 px corners, a soft shadow that deepens and tints blue on hover.
        edge = lerp_color(lerp_color(PANEL, BLUE_5, hover), ACCENT, sel)
        if pulse > .01:
            edge = lerp_color(edge, GREEN if enabled else '#9aa9bb', pulse)
        x1, y1 = at(2, 2)
        x2, y2 = at(W - 3, H - 4)
        tint = lerp_color(SHADOW, ACCENT_LIGHT, hover)
        c.item('shadow_far', 'polygon', rounded_points(x1 - 2, y1 - 1, x2 + 2, y2 + 3 + lift, 8), smooth=True, splinesteps=24,
               fill=fade(lerp_color(BG, tint, .10 + .06 * hover)), outline='')
        c.item('shadow', 'polygon', rounded_points(x1 - 1, y1, x2 + 1, y2 + 2 + lift, 7), smooth=True, splinesteps=24,
               fill=fade(lerp_color(BG, tint, .22 + .12 * hover)), outline='')
        c.item('card', 'polygon', rounded_points(x1, y1, x2, y2, 6), smooth=True, splinesteps=24,
               fill=fade(PANEL), outline=fade(edge), width=2 if sel > .5 or pulse > .15 else 1)
        px1, py1 = at(9, 9)
        px2, py2 = at(9 + self.PREVIEW_W, 9 + self.PREVIEW_H)
        c.item('preview', 'polygon', rounded_points(px1, py1, px2, py2, 4), smooth=True, splinesteps=12,
               fill=fade(PREVIEW_BG), outline='')

        path, status, stamp = self._thumb(iid)
        image, failed = (None, False)
        if path:
            image, failed = self._image(path, stamp)
            if failed:
                status = t('缩略图读取失败')
        loading = bool(path) and image is None and not failed
        show = alpha > .9 and exit_progress < .12
        if image is not None:
            frame_images.append(image)
        c.item('image', 'image', ((px1 + px2) // 2, (py1 + py2) // 2), anchor='center',
               image=image or '', state='normal' if image is not None and show else 'hidden')
        placeholder = image is None and not loading and alpha > .5
        c.item('ph_title', 'text', at(W / 2, 85), text='VEHICLE PREVIEW', fill=fade('#8ea5be'), font=('Segoe UI', 14),
               state='normal' if placeholder else 'hidden')
        c.item('ph_status', 'text', at(W / 2, 125), text=t(status), width=self.PREVIEW_W - 16, fill=fade('#b6c7d9'),
               font=self.text_font, state='normal' if placeholder else 'hidden', justify='center')

        # Selected cards carry a blue check in the preview corner.
        mark = 'normal' if sel > .05 and show else 'hidden'
        mx, my = at(9 + self.PREVIEW_W - 16, 25)
        radius = round(10 * min(1.0, sel * 1.15))
        c.item('mark', 'oval', (mx - radius, my - radius, mx + radius, my + radius), fill=ACCENT, outline=PANEL,
               width=2, state=mark)
        c.item('mark_check', 'line', (mx - 4, my, mx - 1, my + 3, mx + 5, my - 3), fill=PANEL, width=2,
               capstyle='round', joinstyle='round', state='normal' if sel > .6 and show else 'hidden')

        texts = 'normal' if alpha > .35 else 'hidden'
        c.item('title', 'text', at(14, 212), anchor='nw', text=self._lines(iid, W - 28),
               fill=fade(locked(lerp_color(TEXT, ACCENT, sel * .85))), font=self.name_font, state=texts)
        state_text = t('已启用') if enabled else t('已禁用')
        badge_width = self.text_font.measure(state_text) + 34
        bx1, by1 = at(14, 254)
        bx2, by2 = at(14 + badge_width, 276)
        badge_fill = locked(lerp_color('#eef2f8', GREEN_BACK, en), '#f1f3f6')
        badge_ink = locked(lerp_color(MUTED, GREEN, en))
        c.item('badge', 'polygon', rounded_points(bx1, by1, bx2, by2, 11), smooth=True, splinesteps=24,
               fill=fade(badge_fill), outline='', state=texts)
        dx, dy = at(26, 265)
        c.item('badge_dot', 'oval', (dx - 3, dy - 3, dx + 3, dy + 3), fill=fade(badge_ink), outline='', state=texts)
        c.item('badge_text', 'text', at(36, 265), anchor='w', text=state_text,
               fill=fade(badge_ink), font=self.text_font, state=texts)
        c.item('size', 'text', at(W - 16, 265), anchor='e', text=values[4], fill=fade(MUTED), font=self.text_font, state=texts)
