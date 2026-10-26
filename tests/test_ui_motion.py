"""Real Tk regression checks; run with a display (or Xvfb on Linux)."""
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import tkinter as tk
import animation
from app import Application


@unittest.skipUnless(os.name == 'nt' or os.environ.get('DISPLAY'), 'Tk display required')
class UiMotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.app = Application(self.root, Path(self.temp.name), start_services=False)
        self.app.apply_game_state(False)
        self.app.probe_game = lambda: self.app.apply_game_state(False)
        self.app.tree.thumbnail = lambda name: (None, 'missing')
        self.root.geometry('1440x900+0+0')
        self.names = [f'CAR_{i}.zip' for i in range(8)]
        self.app.rows = {n: SimpleNamespace(filename=n, enabled=True, group=n, base=n[:-4],
            variant=0, size=1024, modified=0) for n in self.names}
        self.app.render()
        self.pump(.4)

    def pump(self, seconds=.3):
        until = time.monotonic() + seconds
        while time.monotonic() < until:
            self.root.update()
            time.sleep(.008)

    def tearDown(self):
        self.app.thumbnails.close()
        self.app.page_anim.stop()
        for job in self.root.tk.call('after', 'info'):
            self.root.tk.call('after', 'cancel', job)
        self.root.destroy()
        self.temp.cleanup()
        animation.set_enabled(True)
        self.assertEqual(self.errors, [])

    def test_page_finish_keeps_geometry_and_does_not_unmap_target(self):
        page = self.app.pages['settings']; events = []
        page.bind('<Unmap>', lambda e: events.append(e.widget))
        self.app.show_page('settings'); self.root.update()
        size = (page.winfo_width(), page.winfo_height())
        self.pump()
        self.assertEqual(page.winfo_manager(), 'place')
        self.assertEqual((page.winfo_width(), page.winfo_height()), size)
        self.assertEqual(page.winfo_x(), 22)
        self.assertNotIn(page, events)
        self.app.show_page('settings'); self.pump(.05)
        self.assertNotIn(page, events)

    def test_rapid_page_changes_leave_only_final_page(self):
        for page in ('settings', 'help', 'mods', 'help', 'settings'):
            self.app.show_page(page); self.pump(.025)
        self.pump(.5)  # the PCL drop-in settles after 350 ms
        self.assertEqual(self.app.page, 'settings')
        self.assertEqual([n for n,p in self.app.pages.items() if p.winfo_ismapped()], ['settings'])
        self.assertIsNone(self.app.slide_page)

    def test_unchanged_cards_and_navigation_reuse_canvas_items(self):
        grid = self.app.tree
        before = grid.canvas.find_all()
        nav = self.app.page_buttons['mods']; nav_items = nav.find_all()
        grid.anim.to(('hover', self.names[0]), 1, 160, start=0)
        self.app.render(); self.pump()
        self.assertEqual(grid.canvas.find_all(), before)
        self.assertEqual(nav.find_all(), nav_items)

    def test_delete_stays_busy_until_exit_then_reflows(self):
        name = self.names[0]; app = self.app
        def refresh():
            app.rows.pop(name, None); app.render()
        app.refresh = refresh
        app.busy = True; app.removing = name
        done = Mock(); app.jobs.put((None, None, done)); app.poll()
        self.pump(.05)
        self.assertTrue(app.busy); self.assertTrue(app.tree.exists(name))
        done.assert_not_called()
        self.pump(.5)
        self.assertFalse(app.busy); self.assertFalse(app.tree.exists(name))
        done.assert_called_once_with(None)
        self.assertEqual(app.tree.positions[self.names[1]], (0, 0))

    def test_failed_delete_keeps_card_and_reports_error(self):
        app = self.app; app.busy = True; app.removing = self.names[0]
        error = OSError('recycle failed'); app.error = Mock()
        app.jobs.put((error, None, None)); app.poll(); self.pump()
        self.assertTrue(app.tree.exists(self.names[0]))
        app.error.assert_called_once_with(error)
        self.assertFalse(app.busy)

    def test_manual_import_action_updates_card_and_small_window_button(self):
        from PIL import Image
        app = self.app
        folder = Path(self.temp.name)
        mod = folder/self.names[0]; mod.write_bytes(b'test mod')
        picture = folder/'picture.jpg'; Image.new('RGB', (900,500), 'blue').save(picture)
        app.manager = SimpleNamespace(folder=folder, vehicles=None)
        app.refresh = Mock()
        app.can_edit = lambda: not app.locked()
        app.thumbnails.running = lambda:False
        app.tree.thumbnail = app.thumbnail_for
        app.tree.selection_set(self.names[0])
        with patch('app.filedialog.askopenfilename',return_value=str(picture)):
            app.import_thumbnail()
        app.poll()
        until = time.monotonic()+3
        while app.busy and time.monotonic()<until:self.pump(.05)
        self.assertFalse(app.busy)
        target, status = app.thumbnail_for(self.names[0])
        self.assertTrue(target.is_file());self.assertEqual(status,'手动缩略图')
        self.root.geometry('1050x720');self.pump(.2)
        button=app.import_preview_btn
        self.assertTrue(button.winfo_ismapped())
        self.assertGreater(button.winfo_width(),0)
        self.assertGreaterEqual(button.winfo_x(),0)
        self.assertLessEqual(button.winfo_x()+button.winfo_width(),button.master.winfo_width())

    def test_png_thumbnail_remains_valid_through_collapse(self):
        path = Path(self.temp.name) / 'preview.png'
        img = tk.PhotoImage(master=self.root, width=320, height=180)
        img.put('#3979b3', to=(0, 0, 320, 180)); img.write(str(path), format='png')
        grid = self.app.tree
        grid.thumbnail = lambda name: (path, 'ready')
        grid.redraw(); self.pump(.05)
        self.assertTrue(any(grid.canvas.type(i) == 'image' for i in grid.canvas.find_all()))
        done = Mock(); grid.animate_remove(self.names[0], done)
        self.pump(.09)
        self.assertTrue(grid.exists(self.names[0]))
        self.assertTrue(grid._frame_images)
        self.pump(.25)
        done.assert_called_once()
        self.assertFalse(grid.exists(self.names[0]))

    def test_drop_reentry_cancels_old_hide_and_lock_hides_immediately(self):
        app = self.app
        app.on_drag(True, True, 2); self.pump(.08)
        app.on_drag(False, False, 0); self.pump(.04)
        app.on_drag(True, True, 1); self.pump(.25)
        self.assertTrue(app.drop_highlight.winfo_ismapped())
        self.assertEqual(app.drop_highlight.count, 1)
        app.apply_game_state(True); self.root.update()
        self.assertFalse(app.drop_highlight.winfo_ismapped())
        self.assertTrue(all(str(b.cget('state')) == 'disabled' for b in app.buttons))

    def test_progress_monotonic_reset_and_completion_fade(self):
        p = self.app.progress
        p.start(); p.report(.7); self.pump(.2)
        p.report(.3); self.pump(.2)
        self.assertAlmostEqual(p.anim.get('progress'), .7)
        p.finish(); self.pump(1)
        self.assertEqual(p.anim.get('progress'), 1)
        self.assertEqual(p.anim.get('opacity'), 0)
        p.start(); p.report(.1); self.pump(.2)
        self.assertAlmostEqual(p.anim.get('progress'), .1)

    def test_language_rebuild_cancels_old_animation_preserves_context(self):
        app = self.app
        app.search.set('CAR_1'); app.tree.selection_set(self.names[1])
        app.show_page('settings'); self.pump(.04)
        with patch.object(app, 'can_edit', return_value=True):
            app.language_value.set('English'); app.change_language()
        self.pump()
        self.assertEqual(app.page, 'settings')
        self.assertEqual(app.search.get(), 'CAR_1')
        self.assertEqual(app.tree.selection(), (self.names[1],))
        self.assertEqual(app.page_buttons['mods'].cget('text'), 'Mods')

    def test_animation_frames_do_not_touch_thumbnail_files(self):
        grid = self.app.tree
        grid.thumbnail = Mock(return_value=(None, 'missing'))
        grid.redraw(); self.pump(.05)
        calls = grid.thumbnail.call_count
        self.assertGreater(calls, 0)
        grid._hover(SimpleNamespace(x=20, y=20)); self.pump(.3)
        grid._wheel(SimpleNamespace(delta=-120)); self.pump(.4)
        visible_before = set(c.args[0] for c in grid.thumbnail.call_args_list[:calls])
        new_cards = set(c.args[0] for c in grid.thumbnail.call_args_list[calls:])
        self.assertFalse(new_cards & visible_before)  # only cards scrolled into view are looked up
        grid.redraw(); self.pump(.05)
        self.assertGreater(grid.thumbnail.call_count, calls)

    def test_unchanged_lock_state_does_not_reconfigure_widgets(self):
        app = self.app
        app.apply_game_state(False); self.root.update()
        with patch.object(app.search_entry, 'configure') as entry, patch.object(app.drop_title, 'configure') as title:
            app.apply_game_state(False)
        entry.assert_not_called(); title.assert_not_called()

    def test_motion_button_clicks_only_when_enabled(self):
        from ui_theme import MotionButton
        command = Mock()
        button = MotionButton(self.root, text='Go', command=command)
        button.place(x=10, y=10); self.root.update()
        def click():
            button.event_generate('<Button-1>', x=5, y=5); button.event_generate('<ButtonRelease-1>', x=5, y=5)
            self.pump(.05)
        click(); command.assert_called_once()
        button.configure(state='disabled'); self.assertEqual(button.cget('state'), 'disabled')
        click(); command.assert_called_once()
        button.configure(style='NavSelected.TButton'); self.pump(.4)
        self.assertEqual(button.anim.get('sel'), 1.0)
        button.destroy()

    def test_disabled_animations_finish_navigation_and_delete_immediately(self):
        animation.set_enabled(False)
        self.app.show_page('settings'); self.root.update()
        self.assertFalse(self.app.page_anim.active())
        self.assertEqual(self.app.pages['settings'].winfo_x(), 22)
        self.app.show_page('mods'); self.root.update()
        done = Mock(); self.app.tree.animate_remove(self.names[0], done)
        done.assert_called_once()
        self.assertFalse(self.app.tree.exists(self.names[0]))
