"""Small retained-canvas effects. No screenshots, global transparency or UI threads."""
import tkinter as tk

import animation
from animation import Animator, lerp_color, linear, in_out_fluent, in_fluent, out_fluent, WEAK
from ui_theme import BG, ACCENT, BORDER, PANEL, MUTED, Retained, rounded_points


class MotionProgress(tk.Canvas):
    """Real work progresses smoothly; unknown work uses a stretching segment."""
    LOOP_MS = 1400
    HEAD, TAIL = staticmethod(in_out_fluent(WEAK)), staticmethod(in_fluent(WEAK))

    def __init__(self, parent):
        super().__init__(parent, height=4, bg=BG, highlightthickness=0, bd=0)
        self.anim = Animator(self, self._paint)
        self.paint = Retained(self)
        self.running, self.determinate = False, False
        self.success, self._hide_job, self._tick_job = True, None, None
        self._target = 0.0
        self.anim.set('opacity', 0.0)
        self.anim.set('progress', 0.0)
        self.bind('<Configure>', lambda e: self._paint())

    def start(self, interval=12):
        self._cancel_hide()
        self.anim.stop()
        self.running, self.determinate, self.success = True, False, True
        self._target = 0.0
        self.anim.set('opacity', 1.0)
        self.anim.set('progress', 0.0)
        self._loop()

    def _loop(self):
        # The indeterminate sweep is an ordinary tween on the shared frame clock.
        if self.running and not self.determinate and animation.ENABLED:
            self.anim.to('phase', 1.0, self.LOOP_MS, linear, start=0.0, done=self._loop)
        self._paint()

    def report(self, fraction):
        self.determinate = True
        self.anim.cancel('phase')
        # Never move backwards when a batch report arrives late.
        target = max(self._target, min(1.0, max(0.0, fraction)))
        self._target = target
        self.anim.to('progress', target, 160)

    def finish(self, success=True):
        self.running, self.success = False, success
        self.anim.cancel('phase')
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

    def _paint(self):
        width = max(1, self.winfo_width())
        opacity = self.anim.get('opacity')
        color = ACCENT if self.running else '#2aa37a' if self.success else '#d27751'
        self.paint('track', 'rectangle', (0, 0, width, 4), fill=lerp_color(BG, BORDER, opacity), outline='')
        if self.determinate:
            x1, x2 = 0, round(width * self.anim.get('progress'))
        elif animation.ENABLED:
            # Head leads with an in-out curve, tail follows with an ease-in: the
            # segment stretches, then contracts as it leaves the track.
            phase = self.anim.get('phase')
            head, tail = self.HEAD(phase), self.TAIL(phase)
            x1, x2 = round((tail * 1.4 - .2) * width), round((head * 1.4 - .2) * width)
        else:
            x1, x2 = round(width * .35), round(width * .65)
        self.paint('bar', 'rectangle', (max(0, x1), 0, min(width, x2), 4), fill=lerp_color(BG, color, opacity), outline='')

    def destroy(self):
        self.anim.stop()
        self._cancel_hide()
        super().destroy()


class DropHighlight(tk.Canvas):
    """A slim highlight over the existing import hint; never steals the drop target."""
    def __init__(self, parent):
        super().__init__(parent, height=62, bg=PANEL, highlightthickness=0, bd=0)
        self.anim = Animator(self, self._paint)
        self.paint = Retained(self)
        self.accepted, self.count = True, 0
        self.bind('<Configure>', lambda e: self._paint())

    def show(self, accepted, count=0):
        self.accepted, self.count = accepted, count
        if not self.winfo_ismapped():
            self.anim.set('lift', 0.0)
        self.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.tkraise(self)
        self.anim.to('highlight', 1.0, 140, out_fluent(WEAK), start=self.anim.get('highlight'))
        self.anim.to('lift', 1.0, 260, out_fluent())

    def hide(self, immediate=False):
        if immediate:
            self.anim.set('highlight', 0.0)
            self.anim.cancel('lift')
            self.place_forget()
        else:
            self.anim.to('highlight', 0.0, 140, in_fluent(WEAK), done=self.place_forget)

    def _paint(self):
        from i18n import t
        width, height = max(2, self.winfo_width()), max(2, self.winfo_height())
        a = self.anim.get('highlight')
        # Text drops into place as the highlight appears (PCL page-enter motion).
        lift = round((1 - self.anim.get('lift', 1.0)) * -6)
        color = ACCENT if self.accepted else '#be7652'
        self.paint('shape', 'polygon', rounded_points(1, 1, width - 1, height - 1, 9), smooth=True, splinesteps=24, width=2,
                   fill=lerp_color(PANEL, '#edf6ff' if self.accepted else '#fff4ed', a), outline=lerp_color(PANEL, color, a))
        title = t('松开以导入 {0} 个 ZIP').format(self.count) if self.accepted else t('请拖入实际的车辆 ZIP 文件')
        self.paint('title', 'text', (18, max(15, round(height/2 - 9)) + lift), anchor='w', text=title,
                   fill=lerp_color(PANEL, color, a), width=max(80, width - 36), font=('Microsoft YaHei UI', 11, 'bold'))
        self.paint('detail', 'text', (18, max(34, round(height/2 + 13)) + lift), anchor='w',
                   text=t('文件名将在安装前校验，原文件保持不变'), fill=lerp_color(PANEL, MUTED, a),
                   width=max(80, width - 36), font=('Microsoft YaHei UI', 9))

    def destroy(self):
        self.anim.stop()
        super().destroy()
