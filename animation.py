"""Frame-synchronised tween engine for Tk, modelled on PCL's ModAnimation.

* One shared clock per Tk interpreter drives every Animator, so all widgets
  advance on the same frame and each repaints at most once per frame.  Frames
  are paced against absolute deadlines (no drift, no 15/31 ms alternation),
  and on Windows the system timer resolution is raised to 1 ms only while
  something is actually moving.
* Time advances in clamped steps (like PCL's accumulated ``DeltaTick``): if the
  UI thread stalls, motion resumes where it was instead of jumping ahead.
* ``to(key, target)`` animates an absolute value; starting a new tween on the
  same key replaces the old one from the value currently on screen.
* ``add(key, delta)`` is PCL's additive ``AaDouble``: several tweens on one key
  overlap and sum, so repeated wheel notches or compound curves (fluent + back)
  never restart velocity or jump.
* Easing curves follow PCL: Fluent (power), Back, Elastic and In/Out combos.

Animations can be switched off globally (``set_enabled(False)``); values then
snap to their targets, so the UI behaves exactly as it did without animation.
"""
import math
import sys
import os
from time import perf_counter
from tkinter import TclError

ENABLED = True
FPS = 60
FRAME_MS = 1000 / FPS
MAX_STEP = .05  # longest time one frame may advance a tween (seconds)


def set_enabled(value):
    global ENABLED
    ENABLED = bool(value)


# ---- easing (PCL AniEase*) --------------------------------------------------

WEAK, MIDDLE, STRONG, EXTRA_STRONG = 2, 3, 4, 5


def linear(t):
    return t


def in_fluent(power=MIDDLE):
    def ease(t):
        return t ** power
    return ease


def out_fluent(power=MIDDLE):
    def ease(t):
        return 1 - (1 - t) ** power
    return ease


def in_out(ease_in, ease_out, middle=.5):
    def ease(t):
        if t < middle:
            return middle * ease_in(t / middle)
        return (1 - middle) * ease_out((t - middle) / (1 - middle)) + middle
    return ease


def in_out_fluent(power=MIDDLE, middle=.5):
    return in_out(in_fluent(power), out_fluent(power), middle)


def in_back(power=MIDDLE):
    p = 3 - power * .5
    def ease(t):
        return t ** p * math.cos(1.5 * math.pi * (1 - t))
    return ease


def out_back(power=MIDDLE):
    """Overshoots slightly past the target, then settles (PCL AniEaseOutBack)."""
    p = 3 - power * .5
    def ease(t):
        return 1 - (1 - t) ** p * math.cos(1.5 * math.pi * t)
    return ease


def out_elastic(power=MIDDLE):
    p = power + 4
    def ease(t):
        t = 1 - t
        return 1 - t ** ((p - 1) * .25) * math.cos((p - 3.5) * math.pi * (1 - t) ** 1.5)
    return ease


# Backwards-compatible names.
ease_out_cubic = out_fluent(MIDDLE)
ease_in_out_cubic = in_out_fluent(MIDDLE)


def ease_out_back(t, overshoot=1.2):
    t -= 1
    return 1 + (overshoot + 1) * t ** 3 + overshoot * t ** 2


def clamp01(t):
    return 0.0 if t <= 0 else 1.0 if t >= 1 else t


# ---- colour -----------------------------------------------------------------

_RGB_CACHE = {}


def _rgb(color):
    rgb = _RGB_CACHE.get(color)
    if rgb is None:
        value = color.lstrip('#')
        rgb = _RGB_CACHE[color] = (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    return rgb


def lerp_color(a, b, t):
    """Blend two '#rrggbb' colours; t=0 gives a, t=1 gives b."""
    if t <= 0 or a == b:
        return a
    if t >= 1:
        return b
    (r1, g1, b1), (r2, g2, b2) = _rgb(a), _rgb(b)
    return '#%02x%02x%02x' % (round(r1 + (r2 - r1) * t), round(g1 + (g2 - g1) * t), round(b1 + (b2 - b1) * t))


# ---- shared frame clock -----------------------------------------------------

class _TimerResolution:
    """Windows waits in 15.6 ms ticks by default, which makes ``after`` frames
    alternate between ~16 and ~31 ms.  Ask for 1 ms only while animating."""
    def __init__(self):
        self.active = False
        self.winmm = None
        if os.name == 'nt':
            try:
                import ctypes
                self.winmm = ctypes.WinDLL('winmm')
            except (OSError, AttributeError):
                self.winmm = None

    def set(self, active):
        if active != self.active and self.winmm is not None:
            try:
                (self.winmm.timeBeginPeriod if active else self.winmm.timeEndPeriod)(1)
            except OSError:
                return
        self.active = active


_resolution = _TimerResolution()


class Ticker:
    """One ``after`` loop per Tk interpreter that steps every active Animator."""
    def __init__(self, root):
        self.root, self.animators, self.job = root, [], None
        self.deadline = 0.0

    @staticmethod
    def of(widget):
        try:
            root = widget._root()
        except (AttributeError, TclError):
            root = widget
        ticker = getattr(root, '__dict__', {}).get('_motion_ticker')
        if ticker is None:
            ticker = Ticker(root)
            try:
                root._motion_ticker = ticker
            except AttributeError:
                pass
        return ticker

    def register(self, animator):
        if animator not in self.animators:
            self.animators.append(animator)
        if self.job is None:
            self.deadline = perf_counter() + FRAME_MS / 1000
            self._schedule(FRAME_MS)
            _resolution.set(True)

    def unregister(self, animator):
        if animator in self.animators:
            self.animators.remove(animator)
        if not self.animators:
            self.cancel()

    def cancel(self):
        if self.job is not None:
            try:
                self.root.after_cancel(self.job)
            except (TclError, RuntimeError):
                pass
            self.job = None
        _resolution.set(False)

    def _schedule(self, ms):
        try:
            self.job = self.root.after(max(1, int(ms)), self._tick)
        except (TclError, RuntimeError):  # interpreter is gone
            self.job = None
            self.animators.clear()
            _resolution.set(False)

    def _tick(self):
        self.job = None
        now = perf_counter()
        for animator in list(self.animators):
            try:
                alive = animator._advance(now)
            except Exception:
                # One broken callback must not freeze every other animation.
                alive = False
                try:
                    self.root.report_callback_exception(*sys.exc_info())
                except Exception:
                    pass
            if alive is False:
                self.unregister(animator)
        if not self.animators:
            self.cancel()
            return
        # Pace against absolute deadlines; if we fell behind, resynchronise.
        self.deadline += FRAME_MS / 1000
        now = perf_counter()
        if self.deadline < now:
            self.deadline = now + FRAME_MS / 1000
        self._schedule((self.deadline - now) * 1000)


# ---- animator ---------------------------------------------------------------

class _Tween:
    __slots__ = ('key', 'a', 'b', 'elapsed', 'duration', 'ease', 'done', 'last', 'progress')

    def __init__(self, key, a, b, duration, ease, done, delay, now):
        self.key, self.a, self.b = key, a, b
        self.duration, self.ease, self.done = duration, ease, done
        self.elapsed, self.last, self.progress = -delay, now, 0.0

    def step(self, now):
        """Advance the clock; returns True once the tween has reached its end."""
        self.elapsed += min(max(0.0, now - self.last), MAX_STEP)
        self.last = now
        if self.elapsed < 0:
            return False
        self.progress = min(1.0, self.elapsed / self.duration)
        return self.progress >= 1


class Animator:
    def __init__(self, widget, on_frame=None):
        self.widget, self.on_frame = widget, on_frame
        self.values, self._tweens, self._adds = {}, {}, []
        self._job = None  # kept for callers that check it; the shared Ticker owns the timer

    def get(self, key, default=0.0):
        return self.values.get(key, default)

    def active(self, key=None):
        if key is None:
            return bool(self._tweens or self._adds)
        return key in self._tweens or any(add.key == key for add in self._adds)

    def set(self, key, value):
        """Jump to a value, cancelling any tween on that key."""
        self.cancel(key)
        self.values[key] = value

    def cancel(self, key):
        self._tweens.pop(key, None)
        if self._adds:
            self._adds = [add for add in self._adds if add.key != key]

    def forget(self, key):
        self.cancel(key)
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
        if self._adds:
            self._adds = [add for add in self._adds if add.key != key]
        self.values[key] = current
        self._tweens[key] = _Tween(key, current, target, max(ms, 1) / 1000, ease, done, delay / 1000, perf_counter())
        self._ensure()

    def add(self, key, delta, ms=300, ease=ease_out_cubic, delay=0, done=None):
        """Additively move ``key`` by ``delta`` (PCL AaDouble).

        Overlapping ``add`` calls on one key sum smoothly.  Callers may clamp
        ``values[key]`` in ``on_frame``; the remaining deltas still apply.
        """
        self._tweens.pop(key, None)
        if not ENABLED or ms <= 0:
            self.values[key] = self.values.get(key, 0.0) + delta
            if self.on_frame:
                self._frame()
            if done:
                done()
            return
        self.values.setdefault(key, 0.0)
        self._adds.append(_Tween(key, 0.0, delta, max(ms, 1) / 1000, ease, done, delay / 1000, perf_counter()))
        self._ensure()

    def stop(self):
        self._tweens.clear()
        self._adds = []
        Ticker.of(self.widget).unregister(self)
        self._job = None

    # -- internals --
    def _ensure(self):
        if self._tweens or self._adds:
            self._job = 'ticker'
            Ticker.of(self.widget).register(self)

    def _frame(self):
        try:
            self.on_frame()
        except TclError:  # the widget was destroyed mid-animation
            self.stop()

    def _step(self):
        """Advance one frame now (used by tests and as the Ticker callback)."""
        if self._advance(perf_counter()) is False:
            Ticker.of(self.widget).unregister(self)
            self._job = None
        else:
            self._ensure()

    def _advance(self, now):
        finished = []
        for key, tween in list(self._tweens.items()):
            if tween.step(now):
                self.values[key] = tween.b
                finished.append(tween)
            elif tween.elapsed >= 0:
                self.values[key] = tween.a + (tween.b - tween.a) * tween.ease(tween.progress)
        if self._adds:
            for add in list(self._adds):
                before = add.progress
                ended = add.step(now)
                if add.elapsed >= 0 and add.progress != before:
                    eased = 1.0 if ended else add.ease(add.progress)
                    previous = add.a  # last eased fraction applied
                    self.values[add.key] = self.values.get(add.key, 0.0) + add.b * (eased - previous)
                    add.a = eased
                if ended:
                    finished.append(add)
        if self.on_frame:
            self._frame()  # runs before finished tweens are removed so callers see the final value
        for tween in finished:
            if tween in self._adds:
                self._adds.remove(tween)
            elif self._tweens.get(tween.key) is tween:
                # A frame callback may have replaced this tween (rapid navigation).
                self._tweens.pop(tween.key)
            else:
                continue
            if tween.done:
                tween.done()
        if not (self._tweens or self._adds):
            self._job = None
            return False
        return True
