"""Original Tk widgets with a PCL (Plain Craft Launcher 2) inspired look.

Visual language follows PCL's controls: a 48 px blue gradient title bar with
pill-shaped icon tabs, a white sidebar of list items with a growing accent bar,
white cards with soft shadows that tint blue on hover, outlined buttons
(normal / highlight / red) and slim scroll bars on a light blue backdrop.

Motion follows PCL too: colours cross-fade from whatever is on screen
(100 ms in, 200 ms out), surfaces dip slightly while pressed and spring back,
and scroll views glide with additive Fluent easing.  Everything is drawn on
retained canvas items that are only touched when a value really changes.
"""
import math
import tkinter as tk
from tkinter import ttk
import weakref

from animation import Animator, lerp_color, out_fluent, in_fluent, out_back, WEAK, MIDDLE, STRONG, EXTRA_STRONG

# PCL palette (ColorBrush1-8) on a light blue backdrop.
TEXT = '#343d4a'        # ColorBrush1
ACCENT_DARK = '#0b5bcb' # ColorBrush2
ACCENT = '#1370f3'      # ColorBrush3
ACCENT_LIGHT = '#4890f5'  # ColorBrush4
BLUE_5 = '#96c0f9'      # ColorBrush5
BLUE_6 = '#d5e6fd'      # ColorBrush6
BLUE_7 = '#e0eafd'      # ColorBrush7
BLUE_8 = '#eaf2fe'      # ColorBrush8
BG = '#e6eefa'
PANEL = '#ffffff'
MUTED = '#7b8594'
BORDER = '#dbe5f3'
SHADOW = '#9fb2cc'
RED, RED_LIGHT, RED_BACK = '#ce2111', '#ff4c4c', '#fdecec'
GREEN, GREEN_BACK = '#1f9d6b', '#e3f6ee'
GRAY_TEXT, GRAY_FILL, GRAY_EDGE = '#a6a6a6', '#f5f5f5', '#d6d6d6'
TITLE_EDGE, TITLE_MID = '#2f7fea', '#4b93f6'

FONT = 'Microsoft YaHei UI'
COLOR_IN_MS, COLOR_OUT_MS = 100, 200  # PCL MyButton AnimationColorIn / AnimationColorOut
TRANSPARENT = 'transparent'  # header tabs: show the title bar gradient behind them


def rounded_points(x1, y1, x2, y2, radius=10):
    r = min(radius, (x2-x1)/2, (y2-y1)/2)
    return (x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
            x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
            x1, y2, x1, y2-r, x1, y1+r, x1, y1)


def rounded_rect(canvas, x1, y1, x2, y2, radius=10, **kwargs):
    return canvas.create_polygon(*rounded_points(x1, y1, x2, y2, radius), smooth=True, splinesteps=24, **kwargs)


def surface_color(widget, fallback=BG):
    """The colour actually painted behind ``widget``'s children, as '#rrggbb'."""
    try:
        if isinstance(widget, ttk.Widget):
            style = ttk.Style(widget)
            color = style.lookup(widget.cget('style') or widget.winfo_class(), 'background') or style.lookup('.', 'background')
        else:
            color = widget.cget('background')
        r, g, b = widget.winfo_rgb(color)
        return '#%02x%02x%02x' % (r >> 8, g >> 8, b >> 8)
    except (tk.TclError, ValueError, AttributeError):
        return fallback


class Retained:
    """Canvas items that are created once and only reconfigured when changed."""
    def __init__(self, canvas):
        self.canvas, self.items, self.last = canvas, {}, {}

    def __call__(self, name, kind, coords, **options):
        coords = tuple(coords)
        item = self.items.get(name)
        if item is None:
            item = self.items[name] = getattr(self.canvas, 'create_' + kind)(*coords, **options)
            self.last[name] = (coords, dict(options))
            return item
        old_coords, old_options = self.last[name]
        if coords != old_coords:
            self.canvas.coords(item, *coords)
        changed = {k: v for k, v in options.items() if old_options.get(k, self) != v}
        if changed:
            self.canvas.itemconfigure(item, **changed)
            old_options.update(changed)
        self.last[name] = (coords, old_options)
        return item


# ---- vector icons (16 px design grid, drawn with retained items) -------------

def _gear_points(cx, cy, s, teeth=8, outer=7.6, inner=5.7):
    points = []
    for i in range(teeth * 4):
        angle = math.pi * 2 * i / (teeth * 4) - math.pi / 2
        radius = outer if i % 4 in (1, 2) else inner
        points += [cx + math.cos(angle) * radius * s, cy + math.sin(angle) * radius * s]
    return points


def draw_icon(paint, prefix, name, cx, cy, size, color, backdrop):
    """Draw icon ``name`` centred on (cx, cy).  Each icon always uses the same
    items, so retained painting can update colour and position in place."""
    s = size / 16

    def p(*xy):
        return tuple(v for i in range(0, len(xy), 2) for v in (cx + (xy[i] - 8) * s, cy + (xy[i + 1] - 8) * s))

    stroke = max(1.2, 1.7 * s)
    if name == 'grid':
        for i, (x, y) in enumerate(((1, 1), (9, 1), (1, 9), (9, 9))):
            paint(f'{prefix}{i}', 'polygon', rounded_points(*p(x, y, x + 6, y + 6), 1.6 * s),
                  smooth=True, fill=color, outline='')
    elif name == 'gear':
        paint(f'{prefix}0', 'polygon', _gear_points(cx, cy, s), fill=color, outline='')
        paint(f'{prefix}1', 'oval', p(5.4, 5.4, 10.6, 10.6), fill=backdrop, outline='')
    elif name == 'help':
        paint(f'{prefix}0', 'oval', p(1, 1, 15, 15), fill='', outline=color, width=stroke)
        paint(f'{prefix}1', 'text', p(8, 8.4), text='?', fill=color, font=(FONT, -round(10.5 * s), 'bold'))
    elif name == 'check':
        paint(f'{prefix}0', 'oval', p(1, 1, 15, 15), fill='', outline=color, width=stroke)
        paint(f'{prefix}1', 'line', p(4.6, 8.2, 7.1, 10.7, 11.6, 5.7), fill=color, width=stroke,
              capstyle='round', joinstyle='round')
    elif name == 'block':
        paint(f'{prefix}0', 'oval', p(1, 1, 15, 15), fill='', outline=color, width=stroke)
        paint(f'{prefix}1', 'line', p(3.9, 12.1, 12.1, 3.9), fill=color, width=stroke, capstyle='round')
    elif name == 'layers':
        paint(f'{prefix}0', 'polygon', rounded_points(*p(5, 1, 15, 11), 2 * s), smooth=True,
              fill='', outline=color, width=stroke)
        paint(f'{prefix}1', 'polygon', rounded_points(*p(1, 5, 11, 15), 2 * s), smooth=True,
              fill=color, outline=color, width=stroke)
    elif name == 'plus':
        paint(f'{prefix}0', 'line', p(8, 2, 8, 14), fill=color, width=stroke * 1.15, capstyle='round')
        paint(f'{prefix}1', 'line', p(2, 8, 14, 8), fill=color, width=stroke * 1.15, capstyle='round')
    elif name == 'folder':
        paint(f'{prefix}0', 'polygon', p(1.5, 3, 6, 3, 7.6, 4.8, 14.5, 4.8, 14.5, 13.5, 1.5, 13.5),
              fill='', outline=color, width=stroke, joinstyle='round')
        paint(f'{prefix}1', 'line', p(1.5, 7, 14.5, 7), fill=color, width=stroke)
    elif name == 'refresh':
        paint(f'{prefix}0', 'arc', p(2, 2, 14, 14), start=60, extent=285, style='arc', outline=color, width=stroke)
        paint(f'{prefix}1', 'polygon', p(10.2, 1.2, 14.6, 3.4, 10.6, 6.4), fill=color, outline=color)
    elif name == 'search':
        paint(f'{prefix}0', 'oval', p(1.5, 1.5, 11, 11), fill='', outline=color, width=stroke)
        paint(f'{prefix}1', 'line', p(10, 10, 14.5, 14.5), fill=color, width=stroke * 1.2, capstyle='round')
    elif name == 'image':
        paint(f'{prefix}0', 'polygon', rounded_points(*p(1, 2.5, 15, 13.5), 2 * s), smooth=True,
              fill='', outline=color, width=stroke)
        paint(f'{prefix}1', 'polygon', p(3, 12, 7, 7.5, 10, 10.5, 11.5, 9, 13.5, 12), fill=color, outline='')
    elif name == 'trash':
        paint(f'{prefix}0', 'polygon', p(3.5, 4.5, 12.5, 4.5, 11.6, 14.5, 4.4, 14.5),
              fill='', outline=color, width=stroke, joinstyle='round')
        paint(f'{prefix}1', 'line', p(1.5, 4.5, 14.5, 4.5, 14.5, 4.5, 10, 4.5, 10, 2, 6, 2, 6, 4.5),
              fill=color, width=stroke, joinstyle='round')
    elif name == 'power':
        paint(f'{prefix}0', 'arc', p(2, 2.5, 14, 14.5), start=120, extent=300, style='arc', outline=color, width=stroke)
        paint(f'{prefix}1', 'line', p(8, 1, 8, 8), fill=color, width=stroke, capstyle='round')
    elif name == 'restore':
        paint(f'{prefix}0', 'arc', p(2, 2, 14, 14), start=-60, extent=285, style='arc', outline=color, width=stroke)
        paint(f'{prefix}1', 'polygon', p(1.4, 3.4, 5.8, 1.2, 5.4, 6.4), fill=color, outline=color)


ICON_SIZE = 16


class HoverTracker:
    """One pointer watcher per window that tells hover-aware containers (whose
    children would otherwise steal <Enter>/<Leave>) whether the pointer is inside."""
    def __init__(self, root):
        self.root, self.targets, self.hovered, self.job = root, weakref.WeakSet(), set(), None
        root.bind_all('<Enter>', self._schedule, add='+')
        root.bind_all('<Leave>', self._schedule, add='+')

    @staticmethod
    def of(widget):
        root = widget._root()
        tracker = root.__dict__.get('_hover_tracker')
        if tracker is None:
            tracker = root._hover_tracker = HoverTracker(root)
        return tracker

    def register(self, target):
        self.targets.add(target)

    def _schedule(self, event=None):
        if self.job is None:
            try:
                self.job = self.root.after_idle(self._update)
            except tk.TclError:
                self.job = None

    def _update(self):
        self.job = None
        try:
            x, y = self.root.winfo_pointerxy()
            widget = self.root.winfo_containing(x, y)
        except (tk.TclError, KeyError):
            widget = None
        inside = set()
        while widget is not None:
            if widget in self.targets:
                inside.add(widget)
            widget = getattr(widget, 'master', None)
        for target in list(self.hovered - inside):
            if target.winfo_exists():
                target.set_hover(False)
        for target in inside - self.hovered:
            target.set_hover(True)
        self.hovered = inside


class Card(tk.Frame):
    """PCL MyCard: white, 6 px corners, soft shadow that deepens and tints blue on
    hover, optional bold title in the top-left corner."""
    RADIUS = 6
    SHADOW_LAYERS = ((3, .07), (2, .13), (1, .22))  # (spread px, strength)

    def __init__(self, parent, padding=18, title=None):
        super().__init__(parent, bg=BG)
        self.surface = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.surface.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = ttk.Frame(self, style='Card.TFrame')
        self.body.pack(fill='both', expand=True, padx=padding, pady=padding)
        self.title_label = None
        if title:
            self.title_label = ttk.Label(self.body, text=title, style='CardTitle.TLabel')
            self.title_label.pack(anchor='w', pady=(0, 10))
        self.paint = Retained(self.surface)
        self.anim = Animator(self.surface, self._paint)
        self._size = None
        self.surface.bind('<Configure>', self._resized)
        HoverTracker.of(self).register(self)

    def set_hover(self, value):
        self.anim.to('hover', 1.0 if value else 0.0, COLOR_IN_MS if value else COLOR_OUT_MS)

    def _resized(self, event):
        size = (event.width, event.height)
        if size != self._size:  # moved but not resized, e.g. during a page transition
            self._size = size
            self._paint()

    def _paint(self):
        if self._size is None:
            return
        width, height = self._size
        hover = self.anim.get('hover')
        tint = lerp_color(SHADOW, ACCENT_LIGHT, hover)
        for i, (spread, strength) in enumerate(self.SHADOW_LAYERS):
            inset = 3 - spread
            self.paint(f'shadow{i}', 'polygon', rounded_points(inset, inset + 1, width - inset, height - inset + (1 if spread < 3 else 0),
                                                                self.RADIUS + spread),
                       smooth=True, splinesteps=24, outline='',
                       fill=lerp_color(BG, tint, strength * (1 + .5 * hover)))
        self.paint('panel', 'polygon', rounded_points(3, 3, width - 3, height - 4, self.RADIUS), smooth=True, splinesteps=24,
                   fill=PANEL, outline='')
        if self.title_label is not None:
            color = lerp_color(TEXT, ACCENT_DARK, hover)
            if str(self.title_label.cget('foreground')) != color:
                self.title_label.configure(foreground=color)

    def destroy(self):
        self.anim.stop()
        super().destroy()


class ScrollPage(ttk.Frame):
    """Keep every setting reachable on short windows and larger font scales."""
    WHEEL_PX = 96

    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self, command=self._scrollbar)
        scroll.pack(side='right', fill='y')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.configure(yscrollcommand=auto_hide(scroll), yscrollincrement=0)
        self.body = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self._width = self._region = None
        self.canvas.bind('<Configure>', self._canvas_configure)
        self.body.bind('<Configure>', self._body_configure)
        self.anim = Animator(self.canvas, self._scroll_frame)
        self.top = self.winfo_toplevel()
        self.bindings = [(event, self.top.bind(event, callback, add='+')) for event, callback in (
            ('<MouseWheel>', self._wheel), ('<Button-4>', lambda e: self._wheel(e, -1)),
            ('<Button-5>', lambda e: self._wheel(e, 1)))]

    def _canvas_configure(self, event):
        if event.width != self._width:
            self._width = event.width
            self.canvas.itemconfigure(self.window, width=event.width - 12)  # room for card shadows

    def _body_configure(self, event):
        region = (0, 0, event.width, event.height)
        if region != self._region:
            self._region = region
            self.canvas.configure(scrollregion=region)

    def destroy(self):
        self.anim.stop()
        for event, binding in self.bindings:
            self.top.unbind(event, binding)
        super().destroy()

    def _limit(self):
        return max(0, (self._region or (0, 0, 0, 0))[3] - self.canvas.winfo_height())

    def _scrollbar(self, *args):
        self.anim.cancel('y')
        self.canvas.yview(*args)

    def _scroll_frame(self):
        limit = self._limit()
        y = self.anim.values['y'] = min(max(0.0, self.anim.get('y')), limit)
        total = (self._region or (0, 0, 0, 1))[3] or 1
        self.canvas.yview_moveto(round(y) / total)

    def _wheel(self, event, direction=None):
        widget = event.widget
        while widget is not None and widget != self:
            widget = getattr(widget, 'master', None)
        if widget == self and self._limit() > 0:
            sign = direction if direction is not None else (-1 if event.delta > 0 else 1)
            notches = 1 if direction is not None else max(.25, abs(event.delta) / 120)
            if not self.anim.active('y'):
                self.anim.set('y', self.canvas.canvasy(0))
            # PCL MyScrollViewer: every notch adds its own Fluent tween, so fast
            # wheel spins accelerate smoothly instead of restarting the motion.
            self.anim.add('y', sign * notches * self.WHEEL_PX, 300, out_fluent(6))
            return 'break'


def auto_hide(scrollbar):
    """yscrollcommand that keeps the bar's width but hides its thumb when
    everything fits (PCL shows a scroll bar only when there is something to scroll)."""
    def update(first, last):
        scrollbar.set(first, last)
        style = 'Idle.Vertical.TScrollbar' if float(first) <= 0 and float(last) >= 1 else 'Vertical.TScrollbar'
        if str(scrollbar.cget('style')) != style:
            scrollbar.configure(style=style)
    return update


def setup_style(root):
    s = ttk.Style(root)
    s.theme_use('clam')
    s.configure('.', background=BG, foreground=TEXT, font=(FONT, 10))
    for name, color in [('TFrame', BG), ('Card.TFrame', PANEL), ('Side.TFrame', PANEL)]:
        s.configure(name, background=color)
    s.configure('TLabel', background=BG, foreground=TEXT)
    s.configure('Muted.TLabel', foreground=MUTED)
    s.configure('Card.TLabel', background=PANEL, foreground=TEXT)
    s.configure('CardMuted.TLabel', background=PANEL, foreground=MUTED)
    s.configure('CardTitle.TLabel', background=PANEL, foreground=TEXT, font=(FONT, 11, 'bold'))
    s.configure('Side.TLabel', background=PANEL, foreground=MUTED, font=(FONT, 9))
    s.configure('SideTitle.TLabel', background=PANEL, foreground=TEXT, font=('Segoe UI', 10, 'bold'))
    s.configure('Title.TLabel', background=BG, foreground=TEXT, font=(FONT, 17, 'bold'))
    s.configure('Subtitle.TLabel', background=BG, foreground=MUTED, font=(FONT, 10))
    s.configure('TEntry', fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT,
                padding=7, bordercolor=BLUE_5, lightcolor=PANEL, darkcolor=PANEL)
    s.map('TEntry', bordercolor=[('focus', ACCENT_LIGHT)], fieldbackground=[('readonly', '#f7faff'), ('disabled', GRAY_FILL)],
          foreground=[('disabled', GRAY_TEXT)])
    s.configure('TCombobox', fieldbackground=PANEL, background=PANEL, foreground=TEXT, arrowcolor=ACCENT,
                bordercolor=BLUE_5, lightcolor=PANEL, darkcolor=PANEL, padding=5, arrowsize=14)
    s.map('TCombobox', fieldbackground=[('readonly', PANEL), ('disabled', GRAY_FILL)],
          bordercolor=[('focus', ACCENT_LIGHT), ('active', ACCENT_LIGHT)], arrowcolor=[('disabled', GRAY_TEXT)],
          foreground=[('disabled', GRAY_TEXT)], background=[('active', BLUE_8)])
    root.option_add('*TCombobox*Listbox.font', (FONT, 10))
    root.option_add('*TCombobox*Listbox.selectBackground', BLUE_7)
    root.option_add('*TCombobox*Listbox.selectForeground', ACCENT_DARK)
    root.option_add('*TCombobox*Listbox.background', PANEL)
    root.option_add('*TCombobox*Listbox.foreground', TEXT)
    # PCL MyScrollBar: a slim thumb without arrows.
    s.layout('Vertical.TScrollbar', [('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children': [
        ('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})]})])
    s.configure('Vertical.TScrollbar', background=BLUE_5, troughcolor=BG, bordercolor=BG,
                lightcolor=BLUE_5, darkcolor=BLUE_5, arrowsize=9, gripcount=0, borderwidth=0, relief='flat')
    s.map('Vertical.TScrollbar', background=[('pressed', ACCENT), ('active', ACCENT_LIGHT)],
          lightcolor=[('pressed', ACCENT), ('active', ACCENT_LIGHT)], darkcolor=[('pressed', ACCENT), ('active', ACCENT_LIGHT)])
    s.configure('Idle.Vertical.TScrollbar', background=BG, lightcolor=BG, darkcolor=BG)
    s.map('Idle.Vertical.TScrollbar', background=[('active', BG)], lightcolor=[('active', BG)], darkcolor=[('active', BG)])
    s.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor=BG, borderwidth=0, thickness=3)
    for name in ('TButton', 'Accent.TButton', 'Danger.TButton', 'Nav.TButton', 'NavSelected.TButton'):
        s.configure(name, background=PANEL, foreground=TEXT, padding=(14, 8))  # ttk fallback only


class MotionButton(tk.Canvas):
    """Drop-in replacement for the app's ttk buttons with PCL-style looks and motion.

    Styles: ``TButton`` (PCL normal), ``Accent.TButton`` (PCL highlight),
    ``Danger.TButton`` (PCL red), ``Nav.TButton`` / ``NavSelected.TButton``
    (PCL list items with an accent bar).  Supports ``text``, ``command``,
    ``style``, ``state``, ``icon`` and ``badge`` through configure/cget.
    """
    # style: normal (fill, edge, text), hover (fill, edge, text), pressed fill
    STYLES = {
        'TButton': ((PANEL, '#5d6676', TEXT), (BLUE_7, ACCENT, ACCENT), BLUE_6),
        'Accent.TButton': ((PANEL, ACCENT_DARK, ACCENT_DARK), (BLUE_7, ACCENT, ACCENT), BLUE_6),
        'Danger.TButton': ((PANEL, RED, RED), (RED_BACK, RED_LIGHT, RED_LIGHT), '#fbdddd'),
        'Nav.TButton': ((PANEL, PANEL, TEXT), (BLUE_8, BLUE_8, ACCENT), BLUE_7),
        'NavSelected.TButton': ((PANEL, PANEL, ACCENT_DARK), (BLUE_8, BLUE_8, ACCENT), BLUE_7),
    }
    DISABLED = (GRAY_FILL, GRAY_EDGE, GRAY_TEXT)
    NAV_DISABLED = (PANEL, PANEL, GRAY_TEXT)
    FOCUS_RING = ACCENT_LIGHT
    RADIUS, PADDING, PRESS_DEPTH = 4, (14, 8), .045
    NAV_PADDING, NAV_HEIGHT = (14, 0), 40
    FONT = (FONT, 10)

    def __init__(self, parent, text='', command=None, style='TButton', state='normal', cursor='hand2',
                 icon=None, badge=None, **kwargs):
        from tkinter import font
        self.text, self.command, self.style_name, self.button_state = text, command, style, str(state)
        self.icon, self.badge = icon, badge
        self.text_font = font.Font(family=self.FONT[0], size=self.FONT[1], weight=self.FONT[2] if len(self.FONT) > 2 else 'normal')
        self.badge_font = font.Font(family='Segoe UI', size=9)
        self.hovered = self.pressed = self.focus_ring = self._mouse_focus = False
        self.base_cursor = cursor
        super().__init__(parent, bg=surface_color(parent), highlightthickness=0, borderwidth=0, takefocus=True,
                         cursor=cursor if self.button_state != 'disabled' else '', **kwargs)
        self._request_size()
        self.paint = Retained(self)
        self.anim = Animator(self, self._paint)
        self._to = self._from = self._palette()
        self.anim.set('mix', 1.0)
        self.anim.set('sel', 1.0 if self._is_selected() else 0.0)
        self._last_frame = None
        self.bind('<Configure>', lambda e: self._paint())
        self.bind('<Enter>', lambda e: self._hover(True))
        self.bind('<Leave>', lambda e: self._hover(False))
        self.bind('<Button-1>', self._press)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Return>', lambda e: self.invoke())
        self.bind('<space>', lambda e: self.invoke())
        self.bind('<FocusIn>', self._focus_in)
        self.bind('<FocusOut>', self._focus_out)
        self.bind('<Destroy>', lambda e: self.anim.stop() if e.widget is self else None)

    # -- ttk.Button compatible surface --
    def invoke(self):
        if self.button_state != 'disabled' and self.command:
            self.command()
        return 'break'

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        retarget = resize = False
        for key in list(kwargs):
            if key in ('text', 'icon', 'badge'):
                value = kwargs.pop(key)
                if value != getattr(self, key):
                    setattr(self, key, value)
                    resize = True
            elif key == 'command':
                self.command = kwargs.pop(key)
            elif key == 'style':
                value = kwargs.pop(key)
                if value != self.style_name:
                    self.style_name, retarget, resize = value, True, True
                    selected = 1.0 if self._is_selected() else 0.0
                    if not self.winfo_ismapped():
                        self.anim.set('sel', selected)
                    elif selected:
                        # PCL MyListItem: the bar grows with a soft overshoot, shrinks quickly.
                        self.anim.to('sel', 1.0, 300, out_back(WEAK))
                    else:
                        self.anim.to('sel', 0.0, 150, in_fluent(WEAK))
            elif key == 'state':
                value = str(kwargs.pop(key))
                if value != self.button_state:
                    self.button_state, retarget = value, True
                    if value == 'disabled':
                        self.pressed = False
                        self.anim.to('press', 0.0, 200)
                    kwargs['cursor'] = self.base_cursor if value != 'disabled' else ''
            elif key == 'cursor':
                self.base_cursor = kwargs[key]
                if self.button_state == 'disabled':
                    kwargs[key] = ''
        if kwargs:
            super().configure(**kwargs)
        if resize:
            self._request_size()
        if retarget:
            self._retarget(COLOR_OUT_MS)
        else:
            self._last_frame = None if resize else self._last_frame
            self._paint()

    config = configure

    def cget(self, key):
        if key == 'text': return self.text
        if key == 'state': return self.button_state
        if key == 'style': return self.style_name
        if key == 'command': return self.command
        if key == 'icon': return self.icon
        if key == 'badge': return self.badge
        return super().cget(key)

    def __getitem__(self, key):
        return self.cget(key)

    def __setitem__(self, key, value):
        self.configure(**{key: value})

    # -- appearance --
    def _is_selected(self):
        return self.style_name == 'NavSelected.TButton'

    def _is_nav(self):
        return self.style_name.startswith('Nav')

    def _icon_width(self):
        return ICON_SIZE + 8 if self.icon else 0

    def _badge_width(self):
        return self.badge_font.measure(str(self.badge)) + 14 if self.badge not in (None, '') else 0

    def _request_size(self):
        if self._is_nav():
            width = self.text_font.measure(self.text) + self._icon_width() + self._badge_width() + 2 * self.NAV_PADDING[0] + 12
            height = max(self.NAV_HEIGHT, self.text_font.metrics('linespace') + 16)
        else:
            padx, pady = self.PADDING
            width = self.text_font.measure(self.text) + self._icon_width() + 2 * padx
            height = self.text_font.metrics('linespace') + 2 * pady
        tk.Canvas.configure(self, width=width, height=height)

    def _palette(self):
        if self.button_state == 'disabled':
            return self.NAV_DISABLED if self._is_nav() else self.DISABLED
        normal, hover, press_fill = self.STYLES.get(self.style_name, self.STYLES['TButton'])
        if self.pressed:
            return (press_fill,) + hover[1:]
        return hover if self.hovered else normal

    def _colors(self):
        mix = self.anim.get('mix', 1.0)
        return tuple(lerp_color(a, b, mix) for a, b in zip(self._from, self._to))

    def _retarget(self, ms):
        target = self._palette()
        if target == self._to:
            self._paint()
            return
        self._from, self._to = self._colors(), target
        if self.winfo_ismapped():
            self.anim.to('mix', 1.0, ms, start=0.0)
        else:
            self.anim.set('mix', 1.0)
            self._paint()

    def _hover(self, value):
        self.hovered = value
        if not value and self.pressed:
            # Leaving while held: release slowly (PCL MyButton 800 ms Strong).
            self.pressed = False
            self.anim.to('press', 0.0, 600, out_fluent(STRONG))
        self._retarget(COLOR_IN_MS if value else COLOR_OUT_MS)

    def _press(self, event):
        if self.button_state == 'disabled':
            return
        self._mouse_focus = True
        self.focus_set()
        self._mouse_focus = False
        self.pressed = True
        self.anim.to('press', 1.0, 80, out_fluent(EXTRA_STRONG))
        self._retarget(COLOR_IN_MS)

    def _release(self, event):
        pressed, self.pressed = self.pressed, False
        self.anim.to('press', 0.0, 300, out_fluent(MIDDLE))
        self._retarget(COLOR_OUT_MS)
        if pressed and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def _focus_in(self, event):
        self.focus_ring = not self._mouse_focus  # keyboard focus only, like modern controls
        self._paint()

    def _focus_out(self, event):
        self.focus_ring = False
        self._paint()

    def _shape(self, width, height):
        press = self.anim.get('press')
        depth = self.PRESS_DEPTH * (.45 if self._is_nav() else 1)
        dx, dy = round(width * depth * press / 2), round(height * depth * press / 2)
        return 1 + dx, 1 + dy, width - 1 - dx, height - 1 - dy

    def _paint(self):
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 2 or height <= 2:
            return
        fill, edge, fg = self._colors()
        if self.focus_ring and self.button_state != 'disabled':
            edge = self.FOCUS_RING
        sel = self.anim.get('sel')
        x1, y1, x2, y2 = self._shape(width, height)
        frame = (width, height, fill, edge, fg, x1, y1, round(sel * 1000), self.text, self.icon, self.badge)
        if frame == self._last_frame:
            return
        self._last_frame = frame
        nav = self._is_nav()
        self.paint('surface', 'polygon', rounded_points(x1, y1, x2, y2, self.RADIUS),
                   smooth=True, splinesteps=24, fill=fill, outline=edge, width=1)
        mid = height / 2
        if nav or sel > .001:
            # PCL MyListItem: an accent bar grows from the middle of the selected item.
            bar = max(0.0, (height - 16) * sel)
            self.paint('indicator', 'polygon', rounded_points(x1 + 2, round(mid - bar/2), x1 + 6, round(mid + bar/2), 2),
                       smooth=True, fill=ACCENT if self.button_state != 'disabled' else GRAY_TEXT,
                       outline='', state='normal' if bar >= 2 else 'hidden')
        if nav:
            x = x1 + self.NAV_PADDING[0] + 6
        else:
            x = (width - self.text_font.measure(self.text) - self._icon_width()) / 2
        if self.icon:
            draw_icon(self.paint, 'icon', self.icon, round(x + ICON_SIZE / 2), round(mid), ICON_SIZE, fg, fill)
            x += self._icon_width()
        self.paint('label', 'text', (round(x), round(mid)), anchor='w', text=self.text, fill=fg, font=self.text_font)
        if nav:
            shown = self.badge not in (None, '')
            bw = self._badge_width()
            bx2 = x2 - 10
            selected = self.style_name == 'NavSelected.TButton' and self.button_state != 'disabled'
            self.paint('badge', 'polygon', rounded_points(bx2 - bw, round(mid - 10), bx2, round(mid + 10), 10),
                       smooth=True, outline='', fill=BLUE_7 if selected else '#eef2f8',
                       state='normal' if shown else 'hidden')
            self.paint('badge_text', 'text', (bx2 - bw / 2, round(mid)), text=str(self.badge or ''), font=self.badge_font,
                       fill=ACCENT_DARK if selected else MUTED, state='normal' if shown else 'hidden')


class RoundedNavButton(MotionButton):
    """PCL title-bar tab: a 27 px pill with an icon.  Unselected tabs are
    transparent over the gradient; the selected tab is white with blue text.

    Colours are set through ``bg``/``fg`` (``bg='transparent'`` shows the title
    bar behind it); hover, press and selection changes are tweened."""
    RADIUS, PADDING, PRESS_DEPTH = 99, (14, 6), .06
    FONT = (FONT, 10)

    def __init__(self, parent, text, command, icon=None, **kwargs):
        self.fill, self.foreground, self.backdrop = TRANSPARENT, PANEL, TITLE_MID
        super().__init__(parent, text=text, command=command, style='Top', icon=icon, **kwargs)
        tk.Canvas.configure(self, bg=self.backdrop)

    def set_backdrop(self, color):
        """Colour of the title bar behind this tab (it sits on a gradient)."""
        if color != self.backdrop:
            self.backdrop = color
            tk.Canvas.configure(self, bg=color)
            self._from = self._to = self._palette()
            self._last_frame = None
            self._paint()

    def _request_size(self):
        tk.Canvas.configure(self, width=self.text_font.measure(self.text) + self._icon_width() + 2 * self.PADDING[0],
                            height=max(27, self.text_font.metrics('linespace') + 2 * self.PADDING[1]))

    def _is_nav(self):
        return False

    def _is_selected(self):
        return False

    def _palette(self):
        base = self.backdrop if self.fill == TRANSPARENT else self.fill
        if self.button_state == 'disabled':
            if self.fill == TRANSPARENT:
                return (base, base, lerp_color(base, PANEL, .55))
            return ('#eef2f8', '#eef2f8', '#9aa7b8')
        if self.fill == TRANSPARENT:
            lift = .32 if self.pressed else .2 if self.hovered else 0.0
            color = lerp_color(base, PANEL, lift)
            return (color, color, self.foreground)
        if self.pressed:
            return (BLUE_7, BLUE_7, self.foreground)
        return (base, base, self.foreground)

    def configure(self, cnf=None, **kwargs):
        if cnf:
            kwargs.update(cnf)
        retarget = False
        for key in ('bg', 'fg'):
            if key in kwargs:
                value = kwargs.pop(key)
                if value != (self.fill if key == 'bg' else self.foreground):
                    retarget = True
                    if key == 'bg':
                        self.fill = value
                    else:
                        self.foreground = value
        for key in ('activebackground', 'activeforeground', 'disabledforeground'):
            kwargs.pop(key, None)
        super().configure(**kwargs)
        if retarget:
            # Cross-fade from what is currently on screen; snaps before the first paint.
            self._retarget(COLOR_OUT_MS)

    config = configure

    def cget(self, key):
        if key == 'fg': return self.foreground
        if key == 'bg': return self.fill
        return super().cget(key)

    def _paint(self):
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 2 or height <= 2:
            return
        fill, _, fg = self._colors()
        x1, y1, x2, y2 = self._shape(width - 1, height - 1)
        outline = self.FOCUS_RING if self.focus_ring and self.button_state != 'disabled' else fill
        frame = (width, height, fill, outline, fg, x1, y1, self.text, self.backdrop)
        if frame == self._last_frame:
            return
        self._last_frame = frame
        self.paint('surface', 'polygon', rounded_points(x1, y1, x2, y2, (y2 - y1) / 2),
                   smooth=True, splinesteps=24, width=1, fill=fill, outline=outline)
        x = (width - self.text_font.measure(self.text) - self._icon_width()) / 2
        if self.icon:
            draw_icon(self.paint, 'icon', self.icon, round(x + ICON_SIZE / 2), round(height / 2), ICON_SIZE, fg, fill)
            x += self._icon_width()
        self.paint('label', 'text', (round(x), round(height / 2)), anchor='w', text=self.text, fill=fg, font=self.text_font)


def _hex(rgb):
    return '#%02x%02x%02x' % rgb


class GradientHeader(tk.Canvas):
    """PCL title bar: a horizontal gradient (darker edges, lighter middle), the
    logo on the left, centred tabs and a caption on the right."""
    HEIGHT = 48

    def __init__(self, parent, title, subtitle, caption):
        from tkinter import font
        self.title_font = font.Font(family='Segoe UI', size=16, weight='bold')
        self.sub_font = font.Font(family=FONT, size=10)
        super().__init__(parent, height=max(self.HEIGHT, self.title_font.metrics('linespace') + 18),
                         bg=TITLE_EDGE, highlightthickness=0, borderwidth=0)
        self.paint = Retained(self)
        self.tabs, self._image, self._width = [], None, None
        self.texts = (title, subtitle, caption)
        self.bind('<Configure>', self._resized)

    @staticmethod
    def color_at(fraction):
        # Edge → middle → edge, like PCL's three gradient stops.
        return lerp_color(TITLE_EDGE, TITLE_MID, 1 - abs(fraction * 2 - 1))

    def add_tab(self, tab):
        self.tabs.append(tab)
        self._layout()

    def _resized(self, event):
        if event.width != self._width:
            self._width = event.width
            self._layout()

    def _layout(self):
        width, height = max(2, self.winfo_width()), max(2, int(self.cget('height')))
        if self._image is None or self._image.width() != width:
            # One row of colours, tiled down by Tk: cheap even on wide windows.
            row = ' '.join(self.color_at(x / max(1, width - 1)) for x in range(width))
            self._image = tk.PhotoImage(master=self, width=width, height=height)
            self._image.put('{' + row + '}', to=(0, 0, width, height))
            self.paint('gradient', 'image', (0, 0), anchor='nw', image=self._image)
        title, subtitle, caption = self.texts
        self.paint('title', 'text', (22, height / 2), anchor='w', text=title, fill=PANEL, font=self.title_font)
        self.paint('subtitle', 'text', (30 + self.title_font.measure(title), height / 2 + 1), anchor='w',
                   text=subtitle, fill=BLUE_6, font=self.sub_font)
        self.paint('caption', 'text', (width - 20, height / 2), anchor='e', text=caption, fill=BLUE_6, font=self.sub_font)
        widths = [int(tab.cget('width')) for tab in self.tabs]
        gap = 10
        x = (width - sum(widths) - gap * max(0, len(widths) - 1)) / 2
        left_limit = 40 + self.title_font.measure(title) + self.sub_font.measure(subtitle)
        x = max(x, left_limit)  # narrow windows: never cover the logo
        for i, (tab, w) in enumerate(zip(self.tabs, widths)):
            self.paint(f'tab{i}', 'window', (round(x), height // 2), anchor='w', window=tab)
            tab.set_backdrop(self.color_at((x + w / 2) / width))
            x += w + gap


class SearchBox(tk.Canvas):
    """PCL MySearchBox: rounded outline, magnifier icon and a placeholder.
    ``entry`` is a plain tk.Entry, so state and text behave as usual."""
    def __init__(self, parent, textvariable, placeholder='', width=240):
        from tkinter import font
        self.font = font.Font(family=FONT, size=10)
        height = self.font.metrics('linespace') + 16
        super().__init__(parent, width=width, height=height, bg=surface_color(parent),
                         highlightthickness=0, borderwidth=0)
        self.variable, self.placeholder = textvariable, placeholder
        self.entry = tk.Entry(self, textvariable=textvariable, relief='flat', borderwidth=0, highlightthickness=0,
                              font=self.font, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                              disabledbackground=GRAY_FILL, disabledforeground=GRAY_TEXT,
                              selectbackground=BLUE_6, selectforeground=TEXT)
        self.paint = Retained(self)
        self.anim = Animator(self, self._paint)
        self.hovered = self.focused = False
        self.bind('<Configure>', lambda e: self._paint())
        for widget in (self, self.entry):
            widget.bind('<Enter>', lambda e: self._set('hovered', True), add='+')
            widget.bind('<Leave>', lambda e: self._set('hovered', False), add='+')
        self.entry.bind('<FocusIn>', lambda e: self._set('focused', True), add='+')
        self.entry.bind('<FocusOut>', lambda e: self._set('focused', False), add='+')
        self.bind('<Button-1>', lambda e: self.entry.focus_set())
        self._trace = textvariable.trace_add('write', lambda *_: self._paint())
        self.bind('<Destroy>', self._destroyed)

    def _destroyed(self, event):
        if event.widget is self:
            self.anim.stop()
            try:
                self.variable.trace_remove('write', self._trace)
            except tk.TclError:
                pass

    def _set(self, name, value):
        setattr(self, name, value)
        target = 1.0 if self.focused else .5 if self.hovered else 0.0
        self.anim.to('glow', target, COLOR_IN_MS if target else COLOR_OUT_MS)

    def _paint(self):
        width, height = self.winfo_width(), self.winfo_height()
        if width <= 2 or height <= 2:
            return
        glow = self.anim.get('glow')
        disabled = str(self.entry.cget('state')) == 'disabled'
        fill = GRAY_FILL if disabled else PANEL
        edge = GRAY_EDGE if disabled else lerp_color(lerp_color(BLUE_5, ACCENT_LIGHT, min(1, glow * 2)), ACCENT, max(0, glow * 2 - 1))
        self.paint('surface', 'polygon', rounded_points(1, 1, width - 1, height - 1, 4), smooth=True, splinesteps=24,
                   fill=fill, outline=edge, width=1)
        draw_icon(self.paint, 'icon', 'search', 18, height // 2, 14, GRAY_TEXT if disabled else lerp_color(MUTED, ACCENT, glow), fill)
        empty = not self.variable.get() and not self.focused
        # Embedded windows always sit above canvas items, so the entry collapses
        # while the placeholder is shown; clicking the box focuses it again.
        self.paint('entry', 'window', (32, height // 2), anchor='w', window=self.entry,
                   width=1 if empty else max(10, width - 42), height=self.font.metrics('linespace') + 4)
        self.paint('placeholder', 'text', (34, height // 2), anchor='w', text=self.placeholder, fill=GRAY_TEXT,
                   font=self.font, state='normal' if empty else 'hidden')
