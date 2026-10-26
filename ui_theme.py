"""Original Tk widgets for a light blue, card-based desktop interface.

Motion follows PCL's controls: colours cross-fade from whatever is on screen
(100 ms in, 200 ms out), surfaces dip slightly while pressed and spring back,
selected list items grow an accent bar, and scroll views glide with additive
Fluent easing.  Everything is drawn on retained canvas items that are only
touched when a value really changes, so Tk never repaints more than it must.
"""
import tkinter as tk
from tkinter import ttk
import weakref

from animation import Animator, lerp_color, out_fluent, in_fluent, out_back, WEAK, MIDDLE, STRONG, EXTRA_STRONG

BG = '#eaf1f9'
PANEL = '#ffffff'
TEXT = '#344559'
MUTED = '#7a8b9f'
ACCENT = '#1675d1'
BORDER = '#d3e0ef'

COLOR_IN_MS, COLOR_OUT_MS = 100, 200  # PCL MyButton AnimationColorIn / AnimationColorOut


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
    """Rounded panel with a soft shadow; border and shadow deepen on hover (PCL MyCard)."""
    SHADOW, SHADOW_HOVER, EDGE_HOVER = '#dce6f2', '#cad9eb', '#b7d3f2'

    def __init__(self, parent, padding=18):
        super().__init__(parent, bg=BG)
        self.surface = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.surface.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = ttk.Frame(self, style='Card.TFrame')
        self.body.pack(fill='both', expand=True, padx=padding, pady=padding)
        self.paint = Retained(self.surface)
        self.anim = Animator(self.surface, self._paint)
        self._size = None
        self.surface.bind('<Configure>', self._configure)
        HoverTracker.of(self).register(self)

    def set_hover(self, value):
        self.anim.to('hover', 1.0 if value else 0.0, COLOR_IN_MS if value else COLOR_OUT_MS)

    def _configure(self, event):
        size = (event.width, event.height)
        if size != self._size:  # moved but not resized, e.g. during a page transition
            self._size = size
            self._paint()

    def _paint(self):
        if self._size is None:
            return
        width, height = self._size
        hover = self.anim.get('hover')
        self.paint('shadow', 'polygon', rounded_points(1, 3, width-1, height-1), smooth=True, splinesteps=24,
                   fill=lerp_color(self.SHADOW, self.SHADOW_HOVER, hover), outline='')
        self.paint('panel', 'polygon', rounded_points(1, 1, width-1, height-3), smooth=True, splinesteps=24,
                   fill=PANEL, outline=lerp_color(BORDER, self.EDGE_HOVER, hover))

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
        self.canvas.configure(yscrollcommand=scroll.set, yscrollincrement=1)
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
            self.canvas.itemconfigure(self.window, width=event.width)

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


def setup_style(root):
    s = ttk.Style(root)
    s.theme_use('clam')
    s.configure('.', background=BG, foreground=TEXT, font=('Microsoft YaHei UI', 10))
    for name, color in [('TFrame', BG), ('Card.TFrame', PANEL), ('Side.TFrame', PANEL)]:
        s.configure(name, background=color)
    s.configure('TLabel', background=BG, foreground=TEXT)
    s.configure('Muted.TLabel', foreground=MUTED)
    s.configure('Card.TLabel', background=PANEL, foreground=TEXT)
    s.configure('CardMuted.TLabel', background=PANEL, foreground=MUTED)
    s.configure('CardTitle.TLabel', background=PANEL, foreground=TEXT, font=('Microsoft YaHei UI', 12, 'bold'))
    s.configure('Title.TLabel', background=BG, foreground=TEXT, font=('Microsoft YaHei UI', 20, 'bold'))
    s.configure('TEntry', fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT,
                padding=8, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
    s.map('TEntry', bordercolor=[('focus', ACCENT)], fieldbackground=[('readonly', '#f4f8fc'), ('disabled', '#edf1f5')],
          foreground=[('disabled', '#a8b2bf')])
    s.configure('Vertical.TScrollbar', background='#c4d8ef', troughcolor=BG, borderwidth=0,
                arrowcolor=MUTED, arrowsize=12)
    s.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor=BG, borderwidth=0, thickness=3)
    # Small nine-slice images give real rounded corners while retaining native
    # ttk keyboard focus, disabled state and invocation behaviour.
    root._theme_images = []
    def sprite(fill, outline):
        image = tk.PhotoImage(master=root, width=24, height=24)
        for y in range(24):
            for x in range(24):
                dx, dy = max(6-x, 0, x-17), max(6-y, 0, y-17)
                if dx*dx + dy*dy <= 36:
                    edge = x in (0, 23) or y in (0, 23) or dx*dx + dy*dy > 24
                    image.put(outline if edge else fill, (x, y))
        root._theme_images.append(image)
        return image
    definitions = {
        'TButton': (PANEL, BORDER, '#edf6ff', ACCENT, TEXT),
        'Accent.TButton': (ACCENT, ACCENT, '#0865bd', '#0865bd', PANEL),
        'Nav.TButton': (PANEL, PANEL, '#f0f6fd', '#f0f6fd', TEXT),
        'NavSelected.TButton': ('#e6f2ff', '#e6f2ff', '#d9ebff', '#d9ebff', ACCENT),
        'Top.TButton': (ACCENT, ACCENT, '#368bdd', '#368bdd', PANEL),
        'TopSelected.TButton': (PANEL, PANEL, '#edf6ff', '#edf6ff', ACCENT),
    }
    for index, (name, (fill, edge, hover, hover_edge, fg)) in enumerate(definitions.items()):
        element = f'FH6Rounded{index}'
        normal, active, disabled = sprite(fill, edge), sprite(hover, hover_edge), sprite('#edf1f5', '#e2e8ef')
        focus = sprite(fill, ACCENT if name != 'Accent.TButton' else '#064b91')
        s.element_create(element, 'image', normal, ('disabled', disabled), ('pressed', active),
                         ('active', active), ('focus', focus), border=8, sticky='nsew')
        s.layout(name, [(element, {'sticky': 'nsew', 'children': [
            ('Button.padding', {'sticky': 'nsew', 'children': [('Button.label', {'sticky': 'nsew'})]})]})])
        s.configure(name, background=ACCENT if name.startswith('Top') else PANEL,
                    foreground=fg, padding=(14, 10), anchor='center')
        s.map(name, foreground=[('disabled', '#9ca9b8')])
    s.configure('Nav.TButton', anchor='w', padding=(16, 9))
    s.configure('NavSelected.TButton', anchor='w', padding=(16, 9))


class MotionButton(tk.Canvas):
    """Drop-in replacement for the app's ttk buttons with PCL-style motion.

    Supports ``text``, ``command``, ``style`` (TButton, Accent.TButton,
    Nav.TButton, NavSelected.TButton) and ``state`` through configure/cget.
    """
    # style: normal (fill, edge, text), hover (fill, edge, text), pressed fill
    STYLES = {
        'TButton': ((PANEL, BORDER, TEXT), ('#edf6ff', ACCENT, ACCENT), '#dcecfd'),
        'Accent.TButton': ((ACCENT, ACCENT, PANEL), ('#0865bd', '#0865bd', PANEL), '#06559f'),
        'Nav.TButton': ((PANEL, PANEL, TEXT), ('#f0f6fd', '#f0f6fd', ACCENT), '#e2effc'),
        'NavSelected.TButton': (('#e6f2ff', '#e6f2ff', ACCENT), ('#d9ebff', '#d9ebff', ACCENT), '#cde4fd'),
    }
    DISABLED = ('#edf1f5', '#e2e8ef', '#9ca9b8')
    FOCUS_RING = '#91c5ff'
    RADIUS, PADDING, PRESS_DEPTH = 7, (14, 10), .045
    FONT = ('Microsoft YaHei UI', 10)

    def __init__(self, parent, text='', command=None, style='TButton', state='normal', cursor='hand2', **kwargs):
        from tkinter import font
        self.text, self.command, self.style_name, self.button_state = text, command, style, str(state)
        self.text_font = font.Font(family=self.FONT[0], size=self.FONT[1], weight=self.FONT[2] if len(self.FONT) > 2 else 'normal')
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
            if key == 'text':
                value = kwargs.pop(key)
                resize, self.text = resize or value != self.text, value
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
            self._paint()

    config = configure

    def cget(self, key):
        if key == 'text': return self.text
        if key == 'state': return self.button_state
        if key == 'style': return self.style_name
        if key == 'command': return self.command
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

    def _request_size(self):
        padx, pady = self.PADDING
        width = self.text_font.measure(self.text) + 2 * padx + (8 if self._is_nav() else 0)
        super().configure(width=width, height=self.text_font.metrics('linespace') + 2 * pady)

    def _palette(self):
        if self.button_state == 'disabled':
            return self.DISABLED
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
        frame = (width, height, fill, edge, fg, x1, y1, round(sel * 1000), self.text)
        if frame == self._last_frame:
            return
        self._last_frame = frame
        self.paint('surface', 'polygon', rounded_points(x1, y1, x2, y2, self.RADIUS),
                   smooth=True, splinesteps=24, fill=fill, outline=edge, width=1)
        if self._is_nav() or sel > .001:
            # PCL MyListItem: an accent bar grows from the middle of the selected item.
            bar = max(0.0, (height - 18) * sel)
            mid = height / 2
            self.paint('indicator', 'polygon', rounded_points(x1 + 3, round(mid - bar/2), x1 + 6, round(mid + bar/2), 1.5),
                       smooth=True, fill=ACCENT if self.button_state != 'disabled' else self.DISABLED[2],
                       outline='', state='normal' if bar >= 2 else 'hidden')
        padx = self.PADDING[0] + (8 if self._is_nav() else 0)
        if self._is_nav():
            self.paint('label', 'text', (x1 - 1 + padx, height / 2), anchor='w', text=self.text, fill=fg, font=self.text_font)
        else:
            self.paint('label', 'text', (width / 2, height / 2), anchor='center', text=self.text, fill=fg, font=self.text_font)


class RoundedNavButton(MotionButton):
    """Header tab: draw the text and rounded surface together; no ttk image padding can clip it.

    Colours are set through ``bg``/``fg`` (selected tab is white on blue); hover,
    press and selected-state changes are tweened rather than switched."""
    HOVER_FILL, PRESS_FILL = '#dceeff', '#c3e0ff'
    RADIUS, PADDING, PRESS_DEPTH = 12, (18, 11), .06
    FONT = ('Microsoft YaHei UI', 11)

    def __init__(self, parent, text, command, **kwargs):
        self.fill, self.foreground = ACCENT, PANEL
        super().__init__(parent, text=text, command=command, style='Top', **kwargs)
        super().configure(bg=ACCENT)

    def _request_size(self):
        tk.Canvas.configure(self, width=max(94, self.text_font.measure(self.text) + 36),
                            height=self.text_font.metrics('linespace') + 22)

    def _is_nav(self):
        return False

    def _is_selected(self):
        return False

    def _palette(self):
        if self.button_state == 'disabled':
            return ('#edf1f5', '#edf1f5', '#8794a5')
        if self.pressed:
            return (self.PRESS_FILL, self.PRESS_FILL, ACCENT)
        if self.hovered:
            return (self.HOVER_FILL, self.HOVER_FILL, ACCENT)
        return (self.fill, self.fill, self.foreground)

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
        frame = (width, height, fill, outline, fg, x1, y1, self.text)
        if frame == self._last_frame:
            return
        self._last_frame = frame
        self.paint('surface', 'polygon', rounded_points(x1, y1, x2, y2, self.RADIUS),
                   smooth=True, splinesteps=24, width=2, fill=fill, outline=outline)
        self.paint('label', 'text', (width / 2, height / 2), text=self.text, fill=fg, font=self.text_font)
