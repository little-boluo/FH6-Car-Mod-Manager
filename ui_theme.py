"""Original Tk widgets for a light blue, card-based desktop interface."""
import tkinter as tk
from tkinter import ttk

from animation import Animator, lerp_color

BG = '#eaf1f9'
PANEL = '#ffffff'
TEXT = '#344559'
MUTED = '#7a8b9f'
ACCENT = '#1675d1'
BORDER = '#d3e0ef'


def rounded_rect(canvas, x1, y1, x2, y2, radius=10, **kwargs):
    r = min(radius, (x2-x1)/2, (y2-y1)/2)
    return canvas.create_polygon(
        x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
        x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
        x1, y2, x1, y2-r, x1, y1+r, x1, y1,
        smooth=True, splinesteps=24, **kwargs)


class Card(tk.Frame):
    def __init__(self, parent, padding=18):
        super().__init__(parent, bg=BG)
        self.surface = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.surface.place(x=0, y=0, relwidth=1, relheight=1)
        self.body = ttk.Frame(self, style='Card.TFrame')
        self.body.pack(fill='both', expand=True, padx=padding, pady=padding)
        self.surface.bind('<Configure>', self._paint)

    def _paint(self, event):
        size = (event.width, event.height)
        if size == getattr(self, '_painted_size', None):
            return  # moved but not resized, e.g. during a page slide
        self._painted_size = size
        c = self.surface
        c.delete('all')
        rounded_rect(c, 1, 3, event.width-1, event.height-1, fill='#dce6f2', outline='')
        rounded_rect(c, 1, 1, event.width-1, event.height-3, fill=PANEL, outline=BORDER)


class ScrollPage(ttk.Frame):
    """Keep every setting reachable on short windows and larger font scales."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self, command=self.canvas.yview)
        scroll.pack(side='right', fill='y')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.configure(yscrollcommand=scroll.set, yscrollincrement=24)
        self.body = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.body.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.top = self.winfo_toplevel()
        self.bindings = [(event, self.top.bind(event, callback, add='+')) for event, callback in (
            ('<MouseWheel>', self._wheel), ('<Button-4>', lambda e: self._wheel(e, -1)),
            ('<Button-5>', lambda e: self._wheel(e, 1)))]

    def destroy(self):
        for event, binding in self.bindings:
            self.top.unbind(event, binding)
        super().destroy()

    def _wheel(self, event, direction=None):
        widget = event.widget
        while widget is not None and widget != self:
            widget = getattr(widget, 'master', None)
        if widget == self and self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(direction if direction is not None else (-1 if event.delta > 0 else 1), 'units')
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


class RoundedNavButton(tk.Canvas):
    """Draw the text and rounded surface together; no ttk image padding can clip it.

    Hover, press and selected-state changes are tweened rather than switched."""
    HOVER_FILL, PRESS_FILL = '#dceeff', '#c3e0ff'

    def __init__(self, parent, text, command, **kwargs):
        from tkinter import font
        self.text, self.command = text, command
        self.text_font = font.Font(family='Microsoft YaHei UI', size=11)
        self.fill, self.foreground, self.button_state = ACCENT, PANEL, 'normal'
        self.colors_from = (self.fill, self.foreground)
        super().__init__(parent, width=max(94, self.text_font.measure(text)+36),
                         height=self.text_font.metrics('linespace')+22, bg=ACCENT,
                         highlightthickness=0, borderwidth=0, takefocus=True, cursor='hand2')
        self.anim = Animator(self, self._paint)
        for key, value in (('hover', 0.0), ('press', 0.0), ('swap', 1.0)):
            self.anim.set(key, value)
        self.bind('<Configure>', lambda e: self._paint())
        self.bind('<Enter>', lambda e: self._hover(True))
        self.bind('<Leave>', lambda e: self._hover(False))
        self.bind('<Button-1>', self._press)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Return>', lambda e: self.invoke())
        self.bind('<space>', lambda e: self.invoke())
        self.bind('<FocusIn>', lambda e: self._paint())
        self.bind('<FocusOut>', lambda e: self._paint())
        self.bind('<Destroy>', lambda e: self.anim.stop() if e.widget is self else None)
        self.pressed = False

    def _hover(self, value):
        self.anim.to('hover', 1.0 if value else 0.0, 150)
        if not value:
            self.pressed = False
            self.anim.to('press', 0.0, 120)

    def _press(self, event):
        if self.button_state != 'disabled':
            self.focus_set()
            self.pressed = True
            self.anim.to('press', 1.0, 70)

    def _release(self, event):
        pressed, self.pressed = self.pressed, False
        self.anim.to('press', 0.0, 180)
        if pressed and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def invoke(self):
        if self.button_state != 'disabled':
            self.command()
        return 'break'

    def _base_colors(self):
        swap = self.anim.get('swap', 1.0)
        return (lerp_color(self.colors_from[0], self.fill, swap),
                lerp_color(self.colors_from[1], self.foreground, swap))

    def configure(self, cnf=None, **kwargs):
        if cnf: kwargs.update(cnf)
        before = self._base_colors()
        for key, value in list(kwargs.items()):
            if key == 'text': self.text = kwargs.pop(key)
            elif key == 'bg': self.fill = kwargs.pop(key)
            elif key == 'fg': self.foreground = kwargs.pop(key)
            elif key == 'state': self.button_state = kwargs.pop(key)
            elif key in ('activebackground', 'activeforeground', 'disabledforeground'): kwargs.pop(key)
        if kwargs: super().configure(**kwargs)
        if (self.fill, self.foreground) != before:
            # Cross-fade from what is currently on screen; snap before the first paint.
            self.colors_from = before
            self.anim.set('swap', 0.0)
            self.anim.to('swap', 1.0, 200) if self.winfo_ismapped() else self.anim.set('swap', 1.0)
        self._paint()

    config = configure

    def cget(self, key):
        if key == 'text': return self.text
        if key == 'fg': return self.foreground
        if key == 'bg': return self.fill
        if key == 'state': return self.button_state
        return super().cget(key)

    def _paint(self):
        if self.button_state == 'disabled':
            fill, fg = '#edf1f5', '#8794a5'
        else:
            hover, press = self.anim.get('hover'), self.anim.get('press')
            fill, fg = self._base_colors()
            fill = lerp_color(lerp_color(fill, self.HOVER_FILL, hover), self.PRESS_FILL, press)
            fg = lerp_color(fg, ACCENT, hover)
        width, height = max(2, self.winfo_width()-1), max(2, self.winfo_height()-1)
        r = min(12, (width-1)/2, (height-1)/2)
        points = (1+r, 1, width-r, 1, width, 1, width, 1+r,
                  width, height-r, width, height, width-r, height, 1+r, height,
                  1, height, 1, height-r, 1, 1+r, 1, 1)
        if not hasattr(self, '_surface_item'):
            self._surface_item = self.create_polygon(*points, smooth=True, splinesteps=24, width=2)
            self._text_item = self.create_text(0, 0, font=self.text_font)
        self.coords(self._surface_item, *points)
        self.itemconfigure(self._surface_item, fill=fill,
                           outline='#91c5ff' if self.focus_get() == self else fill)
        self.coords(self._text_item, self.winfo_width()/2, self.winfo_height()/2 + self.anim.get('press'))
        self.itemconfigure(self._text_item, text=self.text, fill=fg)
