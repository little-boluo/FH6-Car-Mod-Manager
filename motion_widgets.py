"""Small retained-canvas effects. No screenshots, global transparency or UI threads."""
import tkinter as tk
from time import perf_counter

import animation
from animation import Animator, lerp_color
from ui_theme import BG, ACCENT, BORDER, PANEL, MUTED, rounded_rect


class MotionProgress(tk.Canvas):
    """Real work progresses smoothly; unknown work uses a moving segment."""
    def __init__(self, parent):
        super().__init__(parent, height=4, bg=BG, highlightthickness=0, bd=0)
        self.anim = Animator(self, self._paint)
        self.running, self.determinate = False, False
        self.success, self._hide_job, self._tick_job = True, None, None
        self.track = self.create_rectangle(0, 0, 0, 4, fill=BORDER, outline='')
        self.bar = self.create_rectangle(0, 0, 0, 4, fill=ACCENT, outline='')
        self.bind('<Configure>', lambda e: self._paint())

    def start(self, interval=12):
        self._cancel_hide()
        self.anim.stop()
        self.running, self.determinate, self.success = True, False, True
        self._target = 0.0
        self.anim.set('opacity', 1.0)
        self.anim.set('progress', 0.0)
        self.started = perf_counter()
        self._tick()

    def report(self, fraction):
        self.determinate = True
        # Never move backwards when a batch report arrives late.
        target = max(getattr(self, '_target', 0.0), min(1.0, max(0.0, fraction)))
        self._target = target
        self.anim.to('progress', target, 160)

    def finish(self, success=True):
        self.running, self.success = False, success
        if self._tick_job is not None:
            self.after_cancel(self._tick_job)
            self._tick_job = None
        self.determinate = True
        self.anim.to('progress', 1.0, 180)
        self._cancel_hide()
        self._hide_job = self.after(650, self._fade)

    def stop(self):
        self.finish()

    def _cancel_hide(self):
        if self._hide_job is not None:
            self.after_cancel(self._hide_job)
            self._hide_job = None

    def _fade(self):
        self._hide_job = None
        self.anim.to('opacity', 0.0, 250)

    def _tick(self):
        if self._tick_job is not None:
            self.after_cancel(self._tick_job)
            self._tick_job = None
        if self.running and not self.determinate:
            self._paint()
            self._tick_job = self.after(16 if animation.ENABLED else 150, self._tick)

    def _paint(self):
        width = max(1, self.winfo_width())
        opacity = self.anim.get('opacity')
        self.coords(self.track, 0, 0, width, 4)
        self.itemconfigure(self.track, fill=lerp_color(BG, BORDER, opacity))
        color = ACCENT if self.running else '#2aa37a' if self.success else '#d27751'
        self.itemconfigure(self.bar, fill=lerp_color(BG, color, opacity))
        if self.determinate:
            self.coords(self.bar, 0, 0, width * self.anim.get('progress'), 4)
        else:
            phase = ((perf_counter() - getattr(self, 'started', 0)) / 1.2) % 1
            x = (phase * 1.3 - .3) * width if animation.ENABLED else width * .35
            self.coords(self.bar, max(0, x), 0, min(width, x + width*.3), 4)

    def destroy(self):
        self.anim.stop()
        self._cancel_hide()
        if self._tick_job is not None:
            self.after_cancel(self._tick_job)
        super().destroy()


class DropHighlight(tk.Canvas):
    """A slim highlight over the existing import hint; never steals the drop target."""
    def __init__(self, parent):
        super().__init__(parent, height=62, bg=PANEL, highlightthickness=0, bd=0)
        self.anim = Animator(self, self._paint)
        self.accepted, self.count = True, 0
        self.bind('<Configure>', lambda e: self._paint())
        self._shape = rounded_rect(self, 1, 1, 2, 2, radius=9, fill=PANEL, outline=BORDER, width=2)
        self._title = self.create_text(18, 21, anchor='w', fill=ACCENT, font=('Microsoft YaHei UI', 11, 'bold'))
        self._detail = self.create_text(18, 43, anchor='w', fill=MUTED, font=('Microsoft YaHei UI', 9))

    def show(self, accepted, count=0):
        self.accepted, self.count = accepted, count
        self.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.tkraise(self)
        self.anim.to('highlight', 1.0, 140, start=self.anim.get('highlight'))

    def hide(self, immediate=False):
        if immediate:
            self.anim.set('highlight', 0.0)
            self.place_forget()
        else:
            self.anim.to('highlight', 0.0, 140, done=self.place_forget)

    def _paint(self):
        from i18n import t
        width, height = max(2, self.winfo_width()), max(2, self.winfo_height())
        a = self.anim.get('highlight')
        color = ACCENT if self.accepted else '#be7652'
        # Keep the outline item; resizing never clears the canvas between frames.
        r = 9
        self.coords(self._shape, 1+r, 1, width-1-r, 1, width-1, 1, width-1, 1+r,
                    width-1, height-1-r, width-1, height-1, width-1-r, height-1, 1+r, height-1,
                    1, height-1, 1, height-1-r, 1, 1+r, 1, 1)
        self.itemconfigure(self._shape, fill=lerp_color(PANEL, '#edf6ff' if self.accepted else '#fff4ed', a),
                           outline=lerp_color(PANEL, color, a))
        title = t('松开以导入 {0} 个 ZIP').format(self.count) if self.accepted else t('请拖入实际的车辆 ZIP 文件')
        self.itemconfigure(self._title, text=title, fill=lerp_color(PANEL, color, a), width=max(80, width-36))
        self.itemconfigure(self._detail, text=t('文件名将在安装前校验，原文件保持不变'),
                           fill=lerp_color(PANEL, MUTED, a), width=max(80, width-36))
        self.coords(self._title, 18, max(15, height/2-9))
        self.coords(self._detail, 18, max(34, height/2+13))

    def destroy(self):
        self.anim.stop()
        super().destroy()
