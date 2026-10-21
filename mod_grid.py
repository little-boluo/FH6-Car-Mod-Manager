"""Scrollable, virtualised thumbnail cards; keeps selection API used by app actions."""
from i18n import t
from collections import OrderedDict
from pathlib import Path
import math
import tkinter as tk
from tkinter import ttk, font
from ui_theme import BG, PANEL, TEXT, MUTED, ACCENT, BORDER, rounded_rect


class ModGrid(ttk.Frame):
    CARD_W, CARD_H, GAP = 360, 286, 12
    PREVIEW_W, PREVIEW_H = 342, 192

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
        self.canvas.bind('<Configure>', lambda e: self.redraw())
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.canvas.bind('<Button-4>', lambda e: self._wheel(e, -1))
        self.canvas.bind('<Button-5>', lambda e: self._wheel(e, 1))
        self.canvas.bind('<Button-1>', self._click)
        self.canvas.bind('<Double-1>', self._double)
        self.canvas.bind('<Key>', self._key)
        self.canvas.bind('<Motion>', self._hover)
        self.canvas.bind('<Leave>', lambda _: self._hover(None))
        self._redraw_id = None

    def selection(self):
        return (self.chosen,) if self.chosen in self.items else ()

    def selection_set(self, iid):
        if iid in self.items:
            self.chosen = iid
            self.redraw()
            self.on_select()

    def get_children(self):
        return tuple(self.items)

    def exists(self, iid):
        return iid in self.items

    def delete(self, *ids):
        for iid in ids:
            self.items.pop(iid, None)
        self.redraw()

    def insert(self, parent, index, iid, values, tags=()):
        self.items[iid] = (values, tags)
        self.redraw()

    def state(self, states):
        self.disabled = 'disabled' in states
        self.redraw()

    def tag_configure(self, *args, **kwargs):
        pass  # Colours are painted centrally, including the locked state.

    def see(self, iid):
        if iid not in self.items:
            return
        index = list(self.items).index(iid)
        total = max(1, math.ceil(len(self.items) / self.columns) * (self.CARD_H + self.GAP))
        self.canvas.yview_moveto((index // self.columns) * (self.CARD_H + self.GAP) / total)
        self.redraw()

    def _scroll(self, *args):
        self.canvas.yview(*args)
        self.redraw()

    def _wheel(self, event, direction=None):
        self._scroll('scroll', direction if direction is not None else (-1 if event.delta > 0 else 1), 'units')
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
            self.hovered = hovered
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
        if self._redraw_id is not None:
            self.after_cancel(self._redraw_id)
            self._redraw_id = None
        super().destroy()

    def _lines(self, text, width):
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
        c = self.canvas
        c.delete('all')
        self.columns = max(1, (c.winfo_width() + self.GAP) // (self.CARD_W + self.GAP))
        pitch = self.CARD_H + self.GAP
        height = max(c.winfo_height(), math.ceil(len(self.items) / self.columns) * pitch)
        c.configure(scrollregion=(0, 0, c.winfo_width(), height))
        first = max(0, int(c.canvasy(0) // pitch))
        last = int(c.canvasy(c.winfo_height()) // pitch) + 2
        if not self.items:
            c.create_text(c.winfo_width()/2, 90, text=t('这里还没有模组'), fill=TEXT, font=('Microsoft YaHei UI', 16, 'bold'))
            c.create_text(c.winfo_width()/2, 125, text=t('拖入车辆 ZIP，或调整搜索与筛选条件'), fill=MUTED, font=self.text_font)
        for i, (iid, (values, tags)) in enumerate(self.items.items()):
            row, col = divmod(i, self.columns)
            if not first <= row <= last:
                continue
            x, y = col * (self.CARD_W + self.GAP), row * pitch
            rounded_rect(c, x+2, y+4, x+self.CARD_W-1, y+self.CARD_H, fill='#dce6f2', outline='')
            rounded_rect(c, x+1, y+1, x+self.CARD_W-2, y+self.CARD_H-3,
                         fill=PANEL, outline=ACCENT if iid == self.chosen else '#88b9ec' if iid == self.hovered else BORDER,
                         width=2 if iid == self.chosen else 1)
            c.create_rectangle(x+9, y+9, x+9+self.PREVIEW_W, y+9+self.PREVIEW_H, fill='#131925', outline='')
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
                c.create_image(x+self.CARD_W/2, y+9+self.PREVIEW_H/2, image=img)
            else:
                c.create_text(x+self.CARD_W/2, y+85, text='VEHICLE PREVIEW', fill='#8ea5be', font=('Segoe UI', 14))
                c.create_text(x+self.CARD_W/2, y+125, text=t(status), width=self.PREVIEW_W-16, fill='#b6c7d9', font=self.text_font)
            color = '#a0acba' if self.disabled else TEXT
            c.create_text(x+12, y+210, anchor='nw', text=self._lines(iid, self.CARD_W-24), fill=color, font=self.text_font)
            enabled = 'enabled' in tags
            state_text = t('已启用') if enabled else t('已禁用')
            badge_width = max(76, self.text_font.measure(state_text) + 20)
            rounded_rect(c, x+12, y+254, x+12+badge_width, y+277, radius=8,
                         fill='#eef1f5' if self.disabled else '#e6f5ee' if enabled else '#edf1f6', outline='')
            c.create_text(x+12+badge_width/2, y+265, text=state_text,
                          fill='#a0acba' if self.disabled else '#278c74' if enabled else MUTED, font=self.text_font)
            c.create_text(x+self.CARD_W-14, y+265, anchor='e', text=values[4], fill=MUTED, font=self.text_font)
        while len(self.images) > 96:
            key, _ = self.images.popitem(last=False)
            self.image_stamps.pop(key, None)
