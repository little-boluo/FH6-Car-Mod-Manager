"""Small time-based tween engine for Tk.

One Animator owns a dict of named float values.  Calling ``to(key, target)``
moves a value toward ``target`` with an easing curve; a single ``after`` loop
drives every active tween and then calls ``on_frame`` so the widget can repaint.

Animations can be switched off globally (``set_enabled(False)``); values then
snap to their targets, so the UI behaves exactly as it did without animation.
"""
from time import perf_counter
from tkinter import TclError

ENABLED = True
FRAME_MS = 15


def set_enabled(value):
    global ENABLED
    ENABLED = bool(value)


# ---- easing -----------------------------------------------------------------

def linear(t):
    return t


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t):
    return 4 * t * t * t if t < .5 else 1 - (-2 * t + 2) ** 3 / 2


def ease_out_back(t, overshoot=1.2):
    t -= 1
    return 1 + (overshoot + 1) * t ** 3 + overshoot * t ** 2


# ---- colour -----------------------------------------------------------------

def _rgb(color):
    color = color.lstrip('#')
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def lerp_color(a, b, t):
    """Blend two '#rrggbb' colours; t=0 gives a, t=1 gives b."""
    if t <= 0 or a == b:
        return a
    if t >= 1:
        return b
    (r1, g1, b1), (r2, g2, b2) = _rgb(a), _rgb(b)
    return '#%02x%02x%02x' % (round(r1 + (r2 - r1) * t), round(g1 + (g2 - g1) * t), round(b1 + (b2 - b1) * t))


# ---- animator ---------------------------------------------------------------

class Animator:
    def __init__(self, widget, on_frame=None):
        self.widget, self.on_frame = widget, on_frame
        self.values, self._tweens, self._job = {}, {}, None

    def get(self, key, default=0.0):
        return self.values.get(key, default)

    def active(self, key=None):
        return bool(self._tweens) if key is None else key in self._tweens

    def set(self, key, value):
        """Jump to a value, cancelling any tween on that key."""
        self._tweens.pop(key, None)
        self.values[key] = value

    def cancel(self, key):
        self._tweens.pop(key, None)

    def forget(self, key):
        self._tweens.pop(key, None)
        self.values.pop(key, None)

    def to(self, key, target, ms=200, ease=ease_out_cubic, delay=0, start=None, done=None):
        """Animate ``key`` to ``target``.

        ``start`` sets the starting value; without it the tween starts from the
        current value, and a never-seen key simply snaps to the target.
        """
        if start is not None:
            self.values[key] = start
        current = self.values.get(key, target)
        if not ENABLED or (ms <= 0 and delay <= 0) or current == target and delay <= 0:
            self.set(key, target)
            if self.on_frame:
                self._frame()
            if done:
                done()
            return
        self.values[key] = current
        self._tweens[key] = (current, target, perf_counter() + delay / 1000, max(ms, 1) / 1000, ease, done)
        self._ensure()

    def stop(self):
        self._tweens.clear()
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except TclError:
                pass
            self._job = None

    # -- internals --
    def _ensure(self):
        if self._job is None and self._tweens:
            self._job = self.widget.after(FRAME_MS, self._step)

    def _frame(self):
        try:
            self.on_frame()
        except TclError:  # the widget was destroyed mid-animation
            self.stop()

    def _step(self):
        self._job = None
        now, finished = perf_counter(), []
        for key, tween in list(self._tweens.items()):
            a, b, t0, duration, ease, done = tween
            if now < t0:
                continue
            p = min(1.0, (now - t0) / duration)
            self.values[key] = b if p >= 1 else a + (b - a) * ease(p)
            if p >= 1:
                finished.append((key, tween, done))
        if self.on_frame:
            self._frame()  # runs before finished tweens are removed so callers see the final value
        for key, tween, done in finished:
            # A frame callback may have replaced this tween (rapid navigation).
            if self._tweens.get(key) is not tween:
                continue
            self._tweens.pop(key)
            if done:
                done()
        self._ensure()
