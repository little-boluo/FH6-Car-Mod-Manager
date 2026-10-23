"""Scrollable, virtualised thumbnail cards; keeps selection API used by app actions."""
from i18n import t
from collections import OrderedDict
from pathlib import Path
import math
import tkinter as tk
from tkinter import ttk, font
from ui_theme import BG, PANEL, TEXT, MUTED, ACCENT, BORDER, rounded_rect
import animation
from animation import Animator, lerp_color, ease_out_cubic


class RetainedCanvas:
    """Reuse canvas objects across frames instead of deleting every card."""
    def __init__(self, canvas):
        self.canvas, self.objects, self.seen = canvas, {}, set()
        self.group, self.index = '', 0

    def __getattr__(self, name):
        return getattr(self.canvas, name)

    def begin(self, group):
        self.group, self.index = group, 0

    def item(self, kind, *coords, **options):
        key = (self.group, self.index, kind)
        self.index += 1
        self.seen.add(key)
        item = self.objects.get(key)
        if item is None:
            item = getattr(self.canvas, 'create_' + kind)(*coords, **options)
            self.objects[key] = item
        else:
            self.canvas.coords(item, *coords)
            self.canvas.itemconfigure(item, **options)
        return item

    def create_polygon(self, *coords, **options): return self.item('polygon', *coords, **options)
    def create_rectangle(self, *coords, **options): return self.item('rectangle', *coords, **options)
    def create_text(self, *coords, **options): return self.item('text', *coords, **options)
    def create_image(self, *coords, **options): return self.item('image', *coords, **options)

    def finish(self):
        for key in self.objects.keys() - self.seen:
            self.canvas.delete(self.objects.pop(key))
        self.seen.clear()


class ModGrid(ttk.Frame):
    CARD_W, CARD_H, GAP = 360, 286, 12
    PREVIEW_W, PREVIEW_H = 342, 192
    WHEEL_PX = 110  # smooth-scroll distance per mouse-wheel notch

    def __init__(self, parent, thumbnail, on_select, on_toggle):
        super().__init__(parent)
        self.thumbnail, self.on_select, self.on_toggle = thumbnail, on_select, on_toggle
        self.items, self.images = OrderedDict(), OrderedDict()
        self.image_stamps = {}
        self.chosen, self.disabled, self.columns = None, False, 1
        self.hovered = None
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, takefocus=True)
        self.scroll = ttk.Scrollbar(self, command=self._scroll)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side='right', fill='y')
        self.canvas.pack(fill='both', expand=True)
        self.text_font = font.Font(family='Microsoft YaHei UI', size=10)
        self.canvas.bind('<Configure>', self._configure)
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
        self._redraw_id = None
        self.anim = Animator(self.canvas, self._on_frame)
        self._removed, self._new_count, self._release_job = set(), 0, None
        self._scroll_total, self._scroll_target, self._last_size = 1, 0, None

    def _configure(self, event):
        if (event.width, event.height) != self._last_size:  # ignore pure moves (page slide)
            self._last_size = (event.width, event.height)
            self.redraw()

    def _on_frame(self):
        if self.anim.active('scroll') and self._scroll_total > 0:
            self.canvas.yview_moveto(self.anim.get('scroll') / self._scroll_total)
        self.redraw()

    def _schedule_release(self):
        if self._release_job is None:
            self._release_job = self.after(250, self._release)

    def _release(self):
        """End of a delete/insert batch: forget animation state of cards that are gone."""
        self._release_job = None
        self._removed.clear()
        self._new_count = 0
        for key in [k for k in self.anim.values if isinstance(k, tuple) and k[1] not in self.items]:
            self.anim.forget(key)

    def selection(self):
        return (self.chosen,) if self.chosen in self.items else ()

    def selection_set(self, iid):
        if iid in self.items:
            old, self.chosen = self.chosen, iid
            if old != iid:
                if old is not None:
                    self.anim.to(('sel', old), 0.0, 200, start=self.anim.get(('sel', old), 1.0))
                self.anim.to(('sel', iid), 1.0, 200, start=self.anim.get(('sel', iid), 0.0))
            self.redraw()
            self.on_select()

    def get_children(self):
        return tuple(self.items)

    def exists(self, iid):
        return iid in self.items

    def delete(self, *ids):
        for iid in ids:
            if self.items.pop(iid, None) is not None:
                self._removed.add(iid)  # a re-insert within the batch window is a refresh, not a new card
        self._schedule_release()
        self.redraw()

    def insert(self, parent, index, iid, values, tags=()):
        fresh = iid not in self.items and iid not in self._removed
        self.items[iid] = (values, tags)
        enabled = 1.0 if 'enabled' in tags else 0.0
        if fresh:  # staggered slide-up entrance
            delay = min(self._new_count, 12) * 35
            self._new_count += 1
            self.anim.set(('en', iid), enabled)
            self.anim.to(('enter', iid), 1.0, 380, ease_out_cubic, delay=delay, start=0.0)
        else:
            previous = self.anim.get(('en', iid), enabled)
            if previous != enabled:  # enabled/disabled flipped: fade the badge and pulse the border
                self.anim.to(('en', iid), enabled, 320, start=previous)
                self.anim.to(('pulse', iid), 0.0, 800, start=1.0)
        self._schedule_release()
        self.redraw()

    def replace(self, entries):
        """Apply a complete data snapshot without clearing unchanged cards."""
        previous = self.items
        self.items = OrderedDict((iid, (values, tags)) for iid, values, tags in entries)
        for i, (iid, (values, tags)) in enumerate(self.items.items()):
            enabled = 1.0 if 'enabled' in tags else 0.0
            if iid not in previous:
                self.anim.set(('en', iid), enabled)
                # Only cards near the viewport enter; offscreen cards need no timers.
                row = i // self.columns
                visible_row = max(0, int(self.canvas.canvasy(0) // (self.CARD_H+self.GAP)))
                if visible_row <= row <= visible_row + 2:
                    self.anim.to(('enter', iid), 1.0, 250, delay=min(i % 9, 5)*24, start=0.0)
                else:
                    self.anim.set(('enter', iid), 1.0)
            elif previous[iid][1] != tags:
                self.anim.to(('en', iid), enabled, 230)
                self.anim.to(('pulse', iid), 0.0, 450, start=.65)
            if iid in self.positions:
                old_x, old_y = self.positions[iid]
                row, col = divmod(i, self.columns)
                target_x, target_y = col*(self.CARD_W+self.GAP), row*(self.CARD_H+self.GAP)
                if (old_x, old_y) != (target_x, target_y):
                    self.anim.to(('x', iid), target_x, 220, start=old_x)
                    self.anim.to(('y', iid), target_y, 220, start=old_y)
        for key in list(self.anim.values):
            if isinstance(key, tuple) and key[1] not in self.items:
                self.anim.forget(key)
        self.redraw()

    def animate_remove(self, iid, done):
        if iid not in self.items or not self.winfo_ismapped():
            done()
            return
        def finish():
            self.items.pop(iid, None)
            self.anim.forget(('exit', iid))
            self.redraw()
            done()
        self.anim.to(('exit', iid), 1.0, 210, start=0.0, done=finish)

    def state(self, states):
        self.disabled = 'disabled' in states
        self.redraw()

    def tag_configure(self, *args, **kwargs):
        pass  # Colours are painted centrally, including the locked state.

    def see(self, iid):
        if iid not in self.items:
            return
        index = list(self.items).index(iid)
        pitch = self.CARD_H + self.GAP
        total = max(self.canvas.winfo_height(), math.ceil(len(self.items) / self.columns) * pitch)
        self._scroll_total = total
        target = min((index // self.columns) * pitch, max(0, total - self.canvas.winfo_height()))
        self._scroll_target = target
        self.anim.to('scroll', target, 320, start=self.canvas.canvasy(0))
        if not self.anim.active('scroll'):  # animations off, or already there: jump
            self.canvas.yview_moveto(target / total)
        self.redraw()

    def _scroll(self, *args):
        self.anim.cancel('scroll')  # the scrollbar thumb or keyboard takes over from smooth scrolling
        self.canvas.yview(*args)
        self.redraw()

    def _wheel(self, event, direction=None):
        if self.disabled:
            return 'break'
        sign = direction if direction is not None else (-1 if event.delta > 0 else 1)
        if not animation.ENABLED:
            self._scroll('scroll', sign, 'units')
            return 'break'
        notches = 1 if direction is not None else max(.25, abs(event.delta) / 120)  # touchpads send small deltas
        current = self.canvas.canvasy(0)
        base = self._scroll_target if self.anim.active('scroll') else current
        self._scroll_target = min(max(0, self._scroll_total - self.canvas.winfo_height()),
                                  max(0, base + sign * notches * self.WHEEL_PX))
        self.anim.to('scroll', self._scroll_target, 260, start=current)
        return 'break'

    def _hit(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        col, row = int(x // (self.CARD_W + self.GAP)), int(y // (self.CARD_H + self.GAP))
        if col >= self.columns or x % (self.CARD_W + self.GAP) >= self.CARD_W or y % (self.CARD_H + self.GAP) >= self.CARD_H:
            return None
        index = row * self.columns + col
        ids = list(self.items)
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
                self.anim.to(('hover', old), 0.0, 180, start=self.anim.get(('hover', old), 1.0))
            if hovered is not None:
                self.anim.to(('hover', hovered), 1.0, 160, start=self.anim.get(('hover', hovered), 0.0))
            self.canvas.configure(cursor='hand2' if hovered else '')
            self.redraw()

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
            ids = list(self.items)
            i = ids.index(self.chosen) if self.chosen in ids else 0
            delta = {'Left': -1, 'Right': 1, 'Up': -self.columns, 'Down': self.columns}[event.keysym]
            self.selection_set(ids[max(0, min(len(ids)-1, i+delta))])
            self.see(self.chosen)
        return 'break'

    def redraw(self):
        if self._redraw_id is None:
            self._redraw_id = self.after_idle(self._draw)

    def destroy(self):
        self.anim.stop()
        if self._release_job is not None:
            self.after_cancel(self._release_job)
            self._release_job = None
        if self._redraw_id is not None:
            self.after_cancel(self._redraw_id)
            self._redraw_id = None
        super().destroy()

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
        return '\n'.join(lines)

    def _draw(self):
        self._redraw_id = None
        c = self.painter
        frame_images = []
        positions = {}
        c.begin('_empty')
        self.columns = max(1, (c.winfo_width() + self.GAP) // (self.CARD_W + self.GAP))
        pitch = self.CARD_H + self.GAP
        height = max(c.winfo_height(), math.ceil(len(self.items) / self.columns) * pitch)
        c.configure(scrollregion=(0, 0, c.winfo_width(), height))
        self._scroll_total = height
        first = max(0, int(c.canvasy(0) // pitch))
        last = int(c.canvasy(c.winfo_height()) // pitch) + 2
        if not self.items:
            c.create_text(c.winfo_width()/2, 90, text=t('这里还没有模组'), fill=TEXT, font=('Microsoft YaHei UI', 16, 'bold'))
            c.create_text(c.winfo_width()/2, 125, text=t('拖入车辆 ZIP，或调整搜索与筛选条件'), fill=MUTED, font=self.text_font)
        for i, (iid, (values, tags)) in enumerate(self.items.items()):
            row, col = divmod(i, self.columns)
            if not first <= row <= last:
                continue
            c.begin(iid)
            enabled = 'enabled' in tags
            enter = self.anim.get(('enter', iid), 1.0)
            if enter <= 0.001:  # waiting for its stagger delay
                continue
            hover = 0.0 if self.disabled else self.anim.get(('hover', iid), 0.0)
            sel = self.anim.get(('sel', iid), 1.0 if iid == self.chosen else 0.0)
            en = self.anim.get(('en', iid), 1.0 if enabled else 0.0)
            pulse = self.anim.get(('pulse', iid), 0.0)
            # Cards rise into place on entry and lift 3px under the cursor.
            base_x, base_y = col * (self.CARD_W + self.GAP), row * pitch
            x = self.anim.get(('x', iid), base_x) if self.anim.active(('x', iid)) else base_x
            base_y = self.anim.get(('y', iid), base_y) if self.anim.active(('y', iid)) else base_y
            positions[iid] = (x, base_y)
            exit_progress = self.anim.get(('exit', iid))
            card_height = max(8, self.CARD_H*(1-exit_progress))
            y = base_y + (1-enter)*14 - hover*3

            edge = lerp_color(lerp_color(BORDER, '#88b9ec', hover), ACCENT, sel)
            if pulse > .01:
                edge = lerp_color(edge, '#2fb58a' if enabled else '#9aa9bb', pulse)
            rounded_rect(c, x+2, y+4, x+self.CARD_W-1, y+card_height+hover*3,
                         fill=lerp_color('#dce6f2', '#c3d5e8', hover), outline='')
            rounded_rect(c, x+1, y+1, x+self.CARD_W-2, y+max(2,card_height-3),
                         fill=lerp_color(PANEL, BG, exit_progress), outline=lerp_color(edge, BG, exit_progress), width=2 if sel > .5 or pulse > .15 else 1)
            preview_h = min(self.PREVIEW_H, max(0, card_height-18))
            c.create_rectangle(x+9, y+9, x+9+self.PREVIEW_W, y+9+preview_h, fill='#131925', outline='')
            path, status = self.thumbnail(iid)
            img = None
            if path:
                key = str(path)
                try:
                    file_stat = Path(path).stat()
                    current_stamp = (file_stat.st_mtime_ns, file_stat.st_size)
                    if self.image_stamps.get(key) != current_stamp:
                        self.images.pop(key, None)
                    self.image_stamps[key] = current_stamp
                except OSError:
                    self.images.pop(key, None)
                if key in self.images:
                    self.images.move_to_end(key)
                    img = self.images[key]
                else:
                    try:
                        full = tk.PhotoImage(file=key)
                        factor = max(1, math.ceil(full.width()/self.PREVIEW_W), math.ceil(full.height()/self.PREVIEW_H))
                        img = full.subsample(factor, factor)
                        self.images[key] = img
                    except (tk.TclError, OSError):
                        status = t('缩略图读取失败')
            if img:
                if preview_h < img.height():
                    cropped = tk.PhotoImage(master=self, width=img.width(), height=max(1, round(preview_h)))
                    cropped.tk.call(str(cropped), 'copy', str(img), '-from', 0, 0, img.width(), max(1, round(preview_h)))
                    img = cropped
                frame_images.append(img)
                c.create_image(x+self.CARD_W/2, y+9, anchor='n', image=img,
                               state='normal' if preview_h > 1 else 'hidden')
            else:
                c.create_text(x+self.CARD_W/2, y+85, text='VEHICLE PREVIEW', fill='#8ea5be', font=('Segoe UI', 14), state='normal' if preview_h > 96 else 'hidden')
                c.create_text(x+self.CARD_W/2, y+125, text=t(status), width=self.PREVIEW_W-16, fill='#b6c7d9', font=self.text_font, state='normal' if preview_h > 145 else 'hidden')
            color = '#a0acba' if self.disabled else TEXT
            c.create_text(x+12, y+210, anchor='nw', text=self._line_cache.setdefault(iid, self._lines(iid, self.CARD_W-24)), fill=color, font=self.text_font,
                          state='normal' if card_height > 250 else 'hidden')
            state_text = t('已启用') if enabled else t('已禁用')
            badge_width = max(76, self.text_font.measure(state_text) + 20)
            badge_fill = '#eef1f5' if self.disabled else lerp_color('#edf1f6', '#e6f5ee', en)
            badge_text = '#a0acba' if self.disabled else lerp_color(MUTED, '#278c74', en)
            rounded_rect(c, x+12, y+254, x+12+badge_width, y+277, radius=8, fill=badge_fill, outline='', state='normal' if card_height > 280 else 'hidden')
            c.create_text(x+12+badge_width/2, y+265, text=state_text, fill=badge_text, font=self.text_font, state='normal' if card_height > 280 else 'hidden')
            c.create_text(x+self.CARD_W-14, y+265, anchor='e', text=values[4], fill=MUTED, font=self.text_font, state='normal' if card_height > 280 else 'hidden')
        c.finish()
        self.positions, self._frame_images = positions, frame_images
        while len(self.images) > 96:
            key, _ = self.images.popitem(last=False)
            self.image_stamps.pop(key, None)
