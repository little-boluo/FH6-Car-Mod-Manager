from __future__ import annotations
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import traceback

from core import Manager, ModError, FileLock, atomic_json, cars_from_exe, layout_from_exe
from discovery import discover
from process_watch import game_is_running
from windows_drop import WindowsDrop
from mod_grid import ModGrid
from thumbnails import ThumbnailService
import animation
from animation import Animator
from motion_widgets import MotionProgress, DropHighlight
import i18n
from i18n import t

from ui_theme import BG, PANEL, TEXT, MUTED, ACCENT, BORDER, Card, ScrollPage, RoundedNavButton, setup_style


def size_text(n):
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if n < 1024 or unit == 'GiB':
            return f'{n:.1f} {unit}'
        n /= 1024


class Application:
    def __init__(self, root, home, *, start_services=True):
        self.root, self.home = root, home
        self.manager = None
        self.busy = False
        self.game_running = None
        self.game_error = ''
        self.startup_detection_pending = True
        self.drop = None
        self.jobs = queue.Queue()
        self.progress_events = queue.Queue()
        self.removing = None
        self.rows = {}
        self.config = {}
        self.buttons = []
        self.auto_signature = None
        self.pending_drops = []
        self.thumbnails = ThumbnailService(home)
        self.thumb_catalog = {}
        self.config_path = home / 'settings.json'
        if self.config_path.exists():
            try:
                self.config = json.loads(self.config_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                pass
        i18n.set_language(self.config.get('language', 'zh'))
        animation.set_enabled(self.config.get('animations', True))  # set "animations": false in settings.json to disable
        root.title(t('FH6 Car Mod Manager · 车辆模组管理器 0.8.3'))
        root.geometry(f'1440x{min(960, max(700, root.winfo_screenheight()-80))}')
        root.minsize(1050, 670)
        root.configure(bg=BG)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.setup_style()
        self.build()
        self.apply_controls()
        previous = self.config.get('folder', '')
        if previous and Path(previous).is_dir():
            self.manager = Manager(previous, self.config.get('vehicles'))
            self.folder.set(str(self.manager.folder))
            self.show_vehicle_directory()
            self.location_info.set(t('上次使用的模组目录 · 运行状态检测中'))
            self.refresh()
        if start_services:
            root.after(100, self.poll)
            root.after(250, self.init_drop)
            root.after(0, self.check_game)
            root.after(2000, self.watch)

    def setup_style(self):
        setup_style(self.root)

    def button(self, parent, text, command, accent=False):
        b = ttk.Button(parent, text=text, command=command, style='Accent.TButton' if accent else 'TButton', cursor='hand2')
        self.buttons.append(b)
        return b

    def build(self):
        self.page = 'mods'
        self.page_anim = Animator(self.root, self._slide_frame)
        self.slide_page = None
        self.view_filter = 'all'
        self.folder = tk.StringVar(value=t('尚未定位 mediapc\\Cars'))
        self.location_info = tk.StringVar(value=t('正在检测游戏目录'))
        self.vehicle_text = tk.StringVar(value=t('车辆文件名校验：尚未定位游戏 media\\cars'))
        self.stats = tk.StringVar(value=t('正在读取模组…'))
        self.game_status = tk.StringVar(value=t('正在检查游戏运行状态…'))
        self.selection_text = tk.StringVar(value=t('选择一张车辆卡片开始管理'))
        self.status = tk.StringVar(value=t('请在游戏关闭时安装或切换模组'))

        header = tk.Frame(self.root, bg=ACCENT, height=72)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header, text='FH6', font=('Segoe UI', 22, 'bold'), bg=ACCENT, fg='white').pack(side='left', padx=(24, 12))
        tk.Label(header, text=t('车辆模组管理器'), font=('Microsoft YaHei UI', 11), bg=ACCENT, fg='#e1efff').pack(side='left')
        tk.Label(header, text='v0.8.3', bg=ACCENT, fg='#d6e9ff', font=('Segoe UI', 10)).pack(side='right', padx=24)
        navigation = tk.Frame(header, bg=ACCENT)
        navigation.pack(side='right', padx=24)
        self.page_buttons = {}
        for key, label in [('mods', t('模组管理')), ('settings', t('设置')), ('help', t('帮助'))]:
            b = RoundedNavButton(navigation, label, lambda k=key: self.show_page(k))
            self.buttons.append(b)
            self.style_navigation(b, key == 'mods')
            b.pack(side='left', padx=5, pady=6)
            self.page_buttons[key] = b
            header.configure(height=max(72, b.winfo_reqheight()+14))

        footer = ttk.Frame(self.root, padding=(20, 7))
        footer.pack(side='bottom', fill='x')
        self.footer_status = ttk.Label(footer, textvariable=self.status, style='Muted.TLabel')
        self.footer_status.pack(side='left')
        footer.bind('<Configure>', lambda e: self.footer_status.configure(wraplength=max(180, e.width//2-200)))
        self.signature_label = ttk.Label(footer, text='BY：bilibili _-菠小萝-_',
                                         style='Muted.TLabel', font=('Microsoft YaHei UI', 10, 'bold'))
        self.signature_label.place(relx=.5, rely=.5, anchor='center')
        ttk.Label(footer, text='STEAM  /  XBOX', style='Muted.TLabel', font=('Segoe UI', 9)).pack(side='right')
        progress_host = ttk.Frame(self.root, height=4)
        progress_host.pack(side='bottom', fill='x')
        progress_host.pack_propagate(False)
        self.progress = MotionProgress(progress_host)
        self.progress.pack(fill='both', expand=True)

        body = ttk.Frame(self.root)
        body.pack(fill='both', expand=True)
        sidebar = tk.Frame(body, bg=PANEL, width=216)
        sidebar.pack(side='left', fill='y')
        sidebar.pack_propagate(False)
        tk.Frame(body, bg=BORDER, width=1).pack(side='left', fill='y')
        ttk.Label(sidebar, text='FORZA HORIZON 6', style='CardTitle.TLabel', font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=20, pady=(22, 5))
        ttk.Label(sidebar, textvariable=self.location_info, style='CardMuted.TLabel', wraplength=176).pack(anchor='w', padx=20, pady=(0, 16))
        ttk.Label(sidebar, text=t('模组库'), style='CardMuted.TLabel').pack(anchor='w', padx=20, pady=(0, 9))
        self.filter_buttons = {}
        for key, label in [('all', t('全部模组')), ('enabled', t('已启用')), ('disabled', t('已禁用')), ('variants', t('同名版本'))]:
            b = self.button(sidebar, label, lambda k=key: self.set_filter(k))
            b.configure(style='NavSelected.TButton' if key == 'all' else 'Nav.TButton')
            b.pack(fill='x', padx=12, pady=2)
            self.filter_buttons[key] = b
        bottom = ttk.Frame(sidebar, style='Side.TFrame', padding=(16, 16))
        bottom.pack(side='bottom', fill='x')
        self.button(bottom, t('＋  导入车辆 ZIP'), self.choose_import, True).pack(fill='x', pady=(0, 9))
        self.button(bottom, t('打开模组文件夹'), self.open_folder).pack(fill='x', pady=(0, 9))
        self.game_label = ttk.Label(bottom, textvariable=self.game_status, style='CardMuted.TLabel', wraplength=176)
        self.game_label.pack(anchor='w', pady=(6, 0))

        self.page_host = ttk.Frame(body)
        self.page_host.pack(fill='both', expand=True)
        self.pages = {'mods': ttk.Frame(self.page_host),
                      'settings': ScrollPage(self.page_host), 'help': ScrollPage(self.page_host)}
        mods = self.pages['mods']
        mods.place(x=22, y=20, relwidth=1, width=-44, relheight=1, height=-40)
        heading = ttk.Frame(mods)
        heading.pack(fill='x', pady=(0, 14))
        self.page_title = tk.StringVar(value=t('全部模组'))
        ttk.Label(heading, textvariable=self.page_title, style='Title.TLabel').pack(side='left')
        self.button(heading, t('刷新'), self.refresh).pack(side='right')
        summary = Card(mods, padding=16)
        summary.pack(fill='x', pady=(0, 14))
        ttk.Label(summary.body, textvariable=self.stats, style='CardMuted.TLabel', wraplength=1000).pack(anchor='w', pady=(0, 12))
        summary_row = ttk.Frame(summary.body, style='Card.TFrame')
        summary_row.pack(fill='x')
        summary_row.configure(height=62)
        summary_row.pack_propagate(False)
        self.search = tk.StringVar()
        self.search_entry = ttk.Entry(summary_row, textvariable=self.search, width=24)
        self.search_entry.pack(side='right')
        ttk.Label(summary_row, text=t('搜索文件  '), style='CardMuted.TLabel').pack(side='right')
        self.search.trace_add('write', lambda *_: self.render())
        self.drop_title = tk.Label(summary_row, text=t('将车辆 ZIP 拖入此窗口，即可安装'), bg=PANEL, fg=TEXT,
                                   font=('Microsoft YaHei UI', 10), anchor='w', wraplength=400, justify='left')
        self.drop_title.pack(side='left', fill='x', expand=True)
        self.drop_highlight = DropHighlight(summary_row)

        actions = Card(mods, padding=14)
        actions.pack(side='bottom', fill='x', pady=(14, 0))
        ttk.Label(actions.body, textvariable=self.selection_text, style='CardMuted.TLabel', wraplength=960).pack(anchor='w', pady=(0, 10))
        action_row = ttk.Frame(actions.body, style='Card.TFrame')
        action_row.pack(fill='x')
        self.toggle_btn = self.button(action_row, t('启用所选版本'), self.toggle, True)
        self.toggle_btn.pack(side='left', padx=(0, 10))
        self.button(action_row, t('仅启用此版本'), self.enable_selected).pack(side='left', padx=(0, 10))
        self.button(action_row, t('删除所选模组'), self.delete_selected).pack(side='left')
        self.button(action_row, t('重建所选缩略图'), self.retry_thumbnails).pack(side='right')
        self.tree = ModGrid(mods, self.thumbnail_for, self.selected, self.toggle)
        self.tree.pack(fill='both', expand=True)

        settings = self.pages['settings'].body
        ttk.Label(settings, text=t('设置'), style='Title.TLabel').pack(anchor='w', pady=(0, 6))
        ttk.Label(settings, text=t('连接游戏目录，管理车辆校验与预览'), style='Muted.TLabel').pack(anchor='w', pady=(0, 12))
        language_card = Card(settings, padding=12)
        language_card.pack(fill='x', pady=(0, 10))
        ttk.Label(language_card.body, text=t('界面语言 / Language'), style='CardTitle.TLabel').pack(side='left')
        self.language_value = tk.StringVar(value='English' if i18n.language == 'en' else t('简体中文'))
        self.language_box = ttk.Combobox(language_card.body, textvariable=self.language_value,
                                         values=(t('简体中文'), 'English'), state='readonly', width=16)
        self.language_box.pack(side='right')
        self.language_box.bind('<<ComboboxSelected>>', self.change_language)
        install = Card(settings, padding=12)
        install.pack(fill='x', pady=(0, 10))
        ttk.Label(install.body, text=t('游戏与模组目录'), style='CardTitle.TLabel').pack(anchor='w', pady=(0, 10))
        ttk.Entry(install.body, textvariable=self.folder, state='readonly').pack(fill='x', pady=(0, 12))
        install_actions = ttk.Frame(install.body, style='Card.TFrame')
        install_actions.pack(fill='x')
        self.button(install_actions, t('自动检测游戏'), self.auto_detect, True).pack(side='left', padx=(0, 10))
        self.button(install_actions, t('选择游戏 EXE'), self.choose_exe).pack(side='left', padx=(0, 10))
        self.button(install_actions, t('手动选择模组目录'), self.choose_folder).pack(side='left')
        ttk.Label(install.body, text=t('支持 Steam 与 Xbox 安装位置，首次定位时自动创建模组文件夹。'), style='CardMuted.TLabel').pack(anchor='w', pady=(12, 0))
        reference = Card(settings, padding=12)
        reference.pack(fill='x', pady=(0, 10))
        ttk.Label(reference.body, text=t('车辆文件名校验'), style='CardTitle.TLabel').pack(anchor='w', pady=(0, 10))
        ttk.Label(reference.body, textvariable=self.vehicle_text, style='CardMuted.TLabel', wraplength=900).pack(anchor='w', pady=(0, 12))
        self.button(reference.body, t('选择车辆校验目录'), self.choose_vehicle_directory).pack(anchor='w')
        maintenance = Card(settings, padding=12)
        maintenance.pack(fill='x')
        ttk.Label(maintenance.body, text=t('预览与恢复'), style='CardTitle.TLabel').pack(anchor='w', pady=(0, 10))
        ttk.Label(maintenance.body, text=t('仅重新生成宫格中选中车辆的预览；其他车辆缓存保留。'), style='CardMuted.TLabel').pack(anchor='w', pady=(0, 12))
        maintenance_row = ttk.Frame(maintenance.body, style='Card.TFrame')
        maintenance_row.pack(fill='x')
        self.button(maintenance_row, t('重建所选缩略图'), self.retry_thumbnails).pack(side='left', padx=(0, 10))
        self.button(maintenance_row, t('恢复中断切换'), self.recover).pack(side='left')

        help_page = self.pages['help'].body
        ttk.Label(help_page, text=t('使用帮助'), style='Title.TLabel').pack(anchor='w', pady=(0, 20))
        for title, content in [
            (t('导入车辆模组'), t('把一个或多个 ZIP 拖到窗口中，或点击左下角的导入按钮。\n文件名必须与原版 media\\cars 中的车辆文件名一致。')),
            (t('管理同名版本'), t('单击卡片选择模组，双击或按空格切换启用状态。\n同一车型只能启用一个版本，其余版本会自动保留并禁用。')),
            (t('游戏运行时锁定'), t('游戏运行期间，全部按钮、筛选、搜索和拖放都会锁定。\n退出游戏后自动恢复；删除模组会移入 Windows 回收站。')),
            (t('关于界面'), t('蓝色导航与浅色卡片布局参考 Plain Craft Launcher。\n本程序独立实现，不属于 PCL 或 Forza 官方项目。'))]:
            card = Card(help_page)
            card.pack(fill='x', pady=(0, 12))
            ttk.Label(card.body, text=title, style='CardTitle.TLabel').pack(anchor='w', pady=(0, 8))
            ttk.Label(card.body, text=content, style='CardMuted.TLabel', wraplength=950, justify='left').pack(anchor='w')

        # Wrap settings/help copy to the actual card width in either language.
        def fit_copy(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Label) and child.pack_info().get('side') == 'top':
                    child.pack_configure(fill='x')
                    child.bind('<Configure>', lambda e: e.widget.configure(wraplength=max(120, e.width)))
                fit_copy(child)
        fit_copy(settings)
        fit_copy(help_page)

    def style_navigation(self, button, selected):
        button.configure(bg='#edf1f5' if self.locked() else PANEL if selected else ACCENT,
                         fg=ACCENT if selected else PANEL,
                         activebackground='#e6f2ff', activeforeground='#125ba3', disabledforeground='#8794a5')

    def change_language(self, *_):
        language = 'en' if self.language_value.get() == 'English' else 'zh'
        if not self.can_edit():
            self.language_value.set('English' if i18n.language == 'en' else t('简体中文'))
            return
        if language == i18n.language:
            return
        settings = dict(self.config, language=language)
        try:
            atomic_json(self.config_path, settings)
        except Exception as exc:
            self.language_value.set('English' if i18n.language == 'en' else t('简体中文'))
            self.error(exc)
            return
        page, view_filter, term = self.page, self.view_filter, self.search.get()
        selection = self.tree.selection()
        self.config = settings
        i18n.set_language(language)
        self.page_anim.stop()
        for child in list(self.root.winfo_children()):
            child.destroy()
        self.buttons = []
        self.build()
        self.root.title(t('FH6 Car Mod Manager · 车辆模组管理器 0.8.3'))
        if self.manager:
            self.folder.set(str(self.manager.folder))
            self.show_vehicle_directory()
            self.location_info.set(t('模组目录已就绪'))
        self.set_filter(view_filter)
        self.search.set(term)
        if selection:
            self.focus_file(selection[0])
        self.show_page(page)
        self.apply_game_state(self.game_running, self.game_error)

    PAGE_ORDER = ('mods', 'settings', 'help')
    PAGE_PAD = (22, 20)
    SLIDE_PX = 22

    def show_page(self, key):
        if self.locked() or key not in self.pages:
            return
        previous = self.page
        if previous == key:
            # Clicking the selected tab must not unmap/remap its native children.
            return
        self.page_anim.cancel('slide')
        old, page = self.pages[previous], self.pages[key]
        px, py = self.PAGE_PAD
        old.place_configure(x=px, y=py)
        for name, other in self.pages.items():
            if name not in (previous, key):
                other.place_forget()
        self.page = key
        for name, button in self.page_buttons.items():
            self.style_navigation(button, name == key)
        direction = 1 if self.PAGE_ORDER.index(key) > self.PAGE_ORDER.index(previous) else -1
        offset = direction * self.SLIDE_PX if animation.ENABLED else 0
        self.slide_page = page
        # Retain the outgoing page underneath until the incoming page is painted.
        # Geometry and size stay identical throughout and after the transition.
        page.place(x=px + offset, y=py, relwidth=1, width=-2*px, relheight=1, height=-2*py)
        page.tkraise()
        self.page_anim.to('slide', 0.0, 240, start=offset, done=lambda: self._slide_done(page))
        if key == 'mods':
            self.tree.redraw()

    def _slide_frame(self):
        page = self.slide_page
        if page is not None and page.winfo_exists():
            page.place_configure(x=self.PAGE_PAD[0] + round(self.page_anim.get('slide')))

    def _slide_done(self, page):
        if page.winfo_exists() and page is self.pages.get(self.page):
            page.place_configure(x=self.PAGE_PAD[0])
            for other in self.pages.values():
                if other is not page:
                    other.place_forget()
            self.slide_page = None

    def set_filter(self, key):
        if self.locked():
            return
        self.view_filter = key
        titles = {'all': t('全部模组'), 'enabled': t('已启用'), 'disabled': t('已禁用'), 'variants': t('同名版本')}
        self.page_title.set(titles[key])
        for name, button in self.filter_buttons.items():
            button.configure(style='NavSelected.TButton' if name == key else 'Nav.TButton')
        self.show_page('mods')
        self.render()

    def init_drop(self):
        try:
            self.drop = WindowsDrop(self.root, self.on_drop, self.on_drag)
        except Exception as exc:
            self.drop_title.configure(text=t('点击「导入 ZIP」安装车辆模组'))
            self.log(exc)
        self.apply_controls()

    def on_drag(self, active, accepted=False, count=0):
        if not hasattr(self, 'drop_highlight'):
            return
        if active and not self.locked():
            self.show_page('mods')
            self.drop_highlight.show(accepted, count)
        else:
            self.drop_highlight.hide(immediate=self.locked())

    def locked(self):
        return self.busy or self.game_running is not False

    def apply_controls(self):
        locked = self.locked()
        if locked and hasattr(self, 'drop_highlight'):
            self.drop_highlight.hide(immediate=True)
        self.buttons = [b for b in self.buttons if b.winfo_exists()]
        for b in self.buttons:
            b.configure(state='disabled' if locked else 'normal')
        for name, button in getattr(self, 'page_buttons', {}).items():
            self.style_navigation(button, name == self.page)
        if hasattr(self, 'thumbnails'):
            self.thumbnails.set_allowed(not locked)
            if not locked:
                self.tree.redraw()
        if hasattr(self, 'language_box'):
            self.language_box.configure(state='disabled' if locked else 'readonly')
        self.search_entry.configure(state='disabled' if locked else 'normal')
        self.tree.state(['disabled'] if locked else ['!disabled'])
        self.tree.tag_configure('enabled', foreground='#6e7b8e' if locked else '#82dfb1')
        self.tree.tag_configure('disabled', foreground='#6e7b8e' if locked else '#9eacc1')
        if self.drop:
            self.drop.set_enabled(not locked)
        title = (t('FH6 正在运行 · 已锁定全部操作') if self.game_running is True else
                 t('正在检测游戏状态 · 操作暂时锁定') if self.game_running is None else
                 t('正在处理文件，请稍候') if self.busy else
                 t('将车辆 ZIP 拖入此窗口，即可安装') if self.drop else
                 t('点击「导入 ZIP」安装车辆模组'))
        self.drop_title.configure(text=title, fg=MUTED if locked else TEXT)

    def apply_game_state(self, running, error=''):
        self.game_running, self.game_error = running, error
        if running is True:
            self.game_status.set(t('● FH6 正在运行 · 全部按钮、设置及拖放已锁定；退出游戏后自动恢复'))
            self.game_label.configure(foreground='#c76b35')
        elif running is False:
            self.game_status.set(t('● FH6 未运行 · 可以管理模组'))
            self.game_label.configure(foreground='#278c74')
        else:
            self.game_status.set(t('● 无法确认游戏状态，操作已锁定，正在自动重试') if error else t('正在检查游戏运行状态…'))
            self.game_label.configure(foreground='#a67d29')
        if running is not False:
            self.pending_drops.clear()
        self.apply_controls()

    def probe_game(self):
        try:
            self.apply_game_state(game_is_running())
        except Exception as exc:
            if str(exc) != self.game_error:
                self.log(exc)
            self.apply_game_state(None, str(exc))

    def check_game(self):
        self.probe_game()
        if self.game_running is False and not self.busy and self.startup_detection_pending:
            self.root.after_idle(self.auto_detect)
        self.root.after(1000, self.check_game)

    def can_edit(self):
        if self.busy:
            return False
        # Re-check at action boundaries, including after native file dialogs close.
        self.probe_game()
        return self.game_running is False

    def block_locked_input(self, *_):
        if self.locked():
            return 'break'

    def log(self, exc):
        try:
            with (self.home / 'errors.log').open('a', encoding='utf-8') as f:
                f.write(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)) + '\n')
        except OSError:
            pass

    def error(self, exc):
        self.log(exc)
        messagebox.showerror(t('操作未完成'), str(exc), parent=self.root)

    def run(self, label, fn, callback=None, *, remove=None):
        if not self.can_edit():
            return
        self.busy = True
        self.removing = remove
        self.status.set(label + '…')
        self.progress.start(12)
        self.apply_controls()
        def work():
            try:
                self.jobs.put((None, fn(), callback))
            except Exception as exc:
                self.jobs.put((exc, None, callback))
        threading.Thread(target=work, daemon=False).start()

    def report_import_progress(self, done, total, name, index, count, phase):
        # Worker thread only enqueues plain data; all Tk work stays in poll().
        self.progress_events.put((done / max(1, total), name, index, count, phase))

    def poll(self):
        if hasattr(self, 'thumbnails') and self.thumbnails.drain():
            self.tree.redraw()
        latest = None
        if hasattr(self, 'progress_events'):
            while True:
                try:
                    latest = self.progress_events.get_nowait()
                except queue.Empty:
                    break
        if latest and self.busy:
            fraction, name, index, count, phase = latest
            self.progress.report(fraction)
            phase_text = {'hash': t('校验源文件'), 'copy': t('复制文件'),
                          'verify': t('验证完整性'), 'done': t('已处理')}.get(phase, phase)
            self.status.set(t('导入 {0}/{1} · {2} · {3}% · {4}').format(
                index, count, phase_text, round(fraction*100), name))
        try:
            exc, result, callback = self.jobs.get_nowait()
        except queue.Empty:
            pass
        else:
            removing = getattr(self, 'removing', None)
            self.removing = None
            if not exc and removing:
                # Show disappearance only after the real recycle/delete succeeds.
                self.tree.animate_remove(removing, lambda: self._finish_job(exc, result, callback))
            else:
                self._finish_job(exc, result, callback)
        self.root.after(50, self.poll)

    def _finish_job(self, exc, result, callback):
        self.busy = False
        self.progress.finish(not exc and not (isinstance(result, dict) and result.get('errors')))
        self.probe_game()
        self.status.set(t('操作未完成，请查看提示') if exc else t('就绪 · 请在游戏关闭时管理模组'))
        self.refresh()
        if exc:
            self.error(exc)
        elif callback:
            try:
                callback(result)
            except Exception as callback_error:
                self.error(callback_error)
        self.apply_controls()
        if self.pending_drops and not self.locked():
            paths, self.pending_drops = self.pending_drops, []
            self.root.after(100, lambda: self.on_drop(paths))

    def set_folder(self, folder, exe='', manual=False):
        if not self.can_edit():
            return
        layout = layout_from_exe(exe) if exe else None
        vehicles = layout.vehicles if layout else None
        if not exe and self.config.get('folder') and Path(folder).resolve() == Path(self.config['folder']).resolve():
            vehicles = self.config.get('vehicles')
        manager = Manager(folder, vehicles)
        settings = dict(self.config, **{'exe': str(exe), 'folder': str(manager.folder), 'manual': manual,
                    'vehicles': str(manager.vehicles) if manager.vehicles else '',
                    'platform': layout.platform if layout else 'manual'})
        atomic_json(self.config_path, settings)
        self.config = settings
        self.manager = manager
        self.folder.set(str(manager.folder))
        self.show_vehicle_directory()
        self.location_info.set(t('手动指定的模组目录') if manual else t('已识别 {0} · 模组目录已就绪').format(layout.label))
        self.auto_signature = None
        self.refresh()
        if manager.journal.exists():
            messagebox.showwarning(t('发现中断切换'), t('目录中有尚未完成的文件改名。请先点击「恢复中断切换」。'), parent=self.root)

    def show_vehicle_directory(self):
        p = self.manager.vehicles if self.manager else None
        self.vehicle_text.set(t('车辆文件名校验：') + str(p) + ('' if p.is_dir() else t('（目录不存在，不能导入）'))
                              if p else t('车辆文件名校验：未指定，导入前必须选择 EXE 同级的 media\\cars'))

    def choose_vehicle_directory(self):
        if not self.can_edit() or not self.manager:
            return False
        p = filedialog.askdirectory(title=t('选择 EXE 同级的 media\\cars（Xbox 在 Content 内；不是 mediapc\\cars）'),
                                    initialdir=str(self.manager.vehicles) if self.manager.vehicles and self.manager.vehicles.is_dir() else None)
        if not p or not self.can_edit():
            return False
        try:
            candidate = Manager(self.manager.folder, p)
            candidate.vehicle_catalog()
            settings = dict(self.config, vehicles=str(candidate.vehicles))
            atomic_json(self.config_path, settings)
            self.config = settings
            self.manager = candidate
            self.show_vehicle_directory()
            self.refresh()
            return True
        except Exception as exc:
            self.error(exc)
            return False

    def ensure_vehicle_directory(self):
        try:
            self.manager.vehicle_catalog()
            return True
        except ModError:
            if not self.can_edit():
                return False
            if not messagebox.askyesno(t('无法校验车辆文件名'), t('找不到或无法读取车辆校验目录。请指定游戏 EXE 同级的 media\\cars：\nSteam 在游戏根目录内，Xbox 在 Content 内。\n\n现在选择吗？'), parent=self.root):
                return False
            return self.choose_vehicle_directory()

    def attach_exe(self, exe):
        if not self.can_edit():
            return
        try:
            folder = cars_from_exe(exe)
            self.set_folder(folder, exe)
        except Exception as exc:
            self.error(exc)

    def auto_detect(self):
        if not self.can_edit():
            return
        self.startup_detection_pending = False
        self.run(t('正在检测游戏进程、Steam 库及常见安装目录'),
                 lambda: discover(self.config.get('exe', '')), self.detected)

    def detected(self, found):
        if not self.can_edit():
            self.startup_detection_pending = True
            return
        if len(found) == 1:
            self.attach_exe(found[0])
        elif len(found) > 1:
            w = tk.Toplevel(self.root)
            w.title(t('检测到多个游戏安装位置'))
            w.geometry('820x320')
            w.transient(self.root)
            w.grab_set()
            box = tk.Listbox(w, font=('Microsoft YaHei UI', 11))
            box.pack(fill='both', expand=True, padx=16, pady=16)
            for p in found:
                box.insert('end', f'[{layout_from_exe(p).label}] {p}')
            box.selection_set(0)
            def choose():
                if not self.can_edit():
                    return
                i = box.curselection()
                if i:
                    w.destroy()
                    self.attach_exe(found[i[0]])
            self.button(w, t('使用所选安装位置'), choose).pack(pady=(0, 16))
        else:
            self.location_info.set(t('自动检测未找到 forzahorizon6.exe'))
            previous = self.config.get('folder', '')
            if previous and Path(previous).is_dir():
                if messagebox.askyesno(t('未找到游戏 EXE'), t('是否使用上次手动指定的模组目录？\n\n') + previous, parent=self.root):
                    self.set_folder(previous, manual=True)
                    return
            if messagebox.askyesno(t('未找到游戏 EXE'), t('是否手动选择车辆模组文件夹？\nSteam：游戏目录\\mediapc\\cars\nXbox：游戏目录\\Content\\mediapc\\Cars'), parent=self.root):
                self.choose_folder()

    def choose_exe(self):
        if not self.can_edit():
            return
        p = filedialog.askopenfilename(title=t('选择 forzahorizon6.exe'), filetypes=[('FH6 executable', 'forzahorizon6.exe'), ('EXE', '*.exe')])
        if p:
            self.attach_exe(p)

    def choose_folder(self):
        if not self.can_edit():
            return
        p = filedialog.askdirectory(title=t('选择车辆 ZIP 模组文件夹（通常是 mediapc\\Cars）'),
                                    initialdir=self.config.get('folder') or None, mustexist=False)
        if p and self.can_edit():
            try:
                Path(p).mkdir(parents=True, exist_ok=True)
                self.set_folder(p, manual=True)
            except Exception as exc:
                self.error(exc)

    def refresh(self):
        if self.busy or not self.manager:
            return
        try:
            try:
                self.thumb_catalog = self.manager.vehicle_catalog()
            except ModError:
                self.thumb_catalog = {}
            rows = self.manager.scan()
            self.rows = {r.filename: r for r in rows}
            self.auto_signature = [(r.filename, r.size, r.modified) for r in rows]
            self.render()
            if not self.locked():
                self.tree.redraw()
        except Exception as exc:
            self.error(exc)

    def render(self):
        if self.busy:
            return
        old = self.tree.selection()
        entries = []
        term = self.search.get().strip().casefold()
        counts = Counter(r.group for r in self.rows.values())
        active_counts = Counter(r.group for r in self.rows.values() if r.enabled)
        view_filter = getattr(self, 'view_filter', 'all')
        for r in self.rows.values():
            if view_filter == 'enabled' and not r.enabled:
                continue
            if view_filter == 'disabled' and r.enabled:
                continue
            if view_filter == 'variants' and counts[r.group] < 2:
                continue
            if term and term not in r.filename.casefold():
                continue
            entries.append((r.filename, (t('● 已启用') if r.enabled else t('○ 已禁用'), r.base,
                        (t('备用位 ') + str(r.variant)) if r.variant else t('原始名称'),
                        r.filename, size_text(r.size), datetime.fromtimestamp(r.modified).strftime('%Y-%m-%d %H:%M')),
                ('enabled' if r.enabled else 'disabled',)))
        self.tree.replace(entries)
        if old and self.tree.exists(old[0]):
            self.tree.selection_set(old[0])
        elif self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])
        enabled = sum(r.enabled for r in self.rows.values())
        conflicts = sum(c > 1 for c in active_counts.values())
        text = t('{0} 个文件  /  {1} 个已启用  /  {2} 个已禁用  /  {3} 组多版本').format(len(self.rows), enabled, len(self.rows)-enabled, sum(c > 1 for c in counts.values()))
        if conflicts:
            text += t('  ·  {0} 组有多个启用文件，请选择要保留启用的版本').format(conflicts)
        self.stats.set(text)
        self.selected()

    def selected(self, *_):
        ids = self.tree.selection()
        r = self.rows.get(ids[0]) if ids else None
        self.toggle_btn.configure(text=t('停用所选版本') if r and r.enabled else t('启用所选版本'))
        self.selection_text.set(r.filename if r else t('单击卡片选择，双击切换启用；同名版本只启用一个'))

    def watch(self):
        if not self.busy and self.manager:
            try:
                current = [(r.filename, r.size, r.modified) for r in self.manager.scan()]
                if current != self.auto_signature:
                    self.refresh()
            except OSError:
                self.status.set(t('目录暂时不可访问，请检查磁盘连接'))
        self.root.after(2000, self.watch)

    def thumbnail_for(self, filename):
        r = self.rows.get(filename)
        if not r or not self.manager:
            return None, t('暂无预览')
        original_name = self.thumb_catalog.get((r.base + '.zip').casefold())
        original = self.manager.vehicles / original_name if original_name else None
        game_root = self.manager.vehicles.parent.parent if self.manager.vehicles else None
        return self.thumbnails.request(self.manager.folder / filename, original, game_root)

    def retry_thumbnails(self):
        if not self.can_edit() or not self.manager:
            return
        ids = self.tree.selection()
        if not ids or ids[0] not in self.rows:
            self.status.set(t('请先在模组宫格中选择一辆车'))
            return
        filename = ids[0]
        r = self.rows[filename]
        original_name = self.thumb_catalog.get((r.base + '.zip').casefold())
        original = self.manager.vehicles / original_name if original_name else None
        game_root = self.manager.vehicles.parent.parent if self.manager.vehicles else None
        try:
            old_image = self.thumbnails.invalidate(self.manager.folder / filename, original, game_root)
            if old_image:
                self.tree.images.pop(str(old_image), None)
            self.thumbnail_for(filename)
            self.tree.redraw()
            self.status.set(t('正在重建所选车辆预览：') + filename)
        except Exception as exc:
            self.error(exc)

    def guard_game(self, fn):
        if game_is_running():
            raise ModError(t('检测到 FH6 正在运行，请先退出游戏，再安装或切换模组。'))
        return fn()

    def toggle(self):
        if not self.can_edit() or not self.manager:
            return
        ids = self.tree.selection()
        if not ids:
            return
        filename = ids[0]
        try:
            m = self.manager.get(filename)
        except Exception as exc:
            self.error(exc)
            return
        operation = self.manager.disable if m.enabled else self.manager.enable
        self.run(t('正在停用') if m.enabled else t('正在切换启用版本'),
                 lambda: self.guard_game(lambda: operation(filename)), self.focus_file)

    def focus_file(self, filename):
        if self.tree.exists(filename):
            self.tree.selection_set(filename)
            self.tree.see(filename)

    def enable_selected(self):
        if not self.can_edit() or not self.manager or not self.tree.selection():
            return
        filename = self.tree.selection()[0]
        self.run(t('正在启用所选版本并禁用同名版本'),
                 lambda: self.guard_game(lambda: self.manager.enable(filename)), self.focus_file)

    def delete_selected(self):
        if not self.can_edit() or not self.manager or not self.tree.selection():
            return
        filename = self.tree.selection()[0]
        try:
            m = self.manager.get(filename)
        except Exception as exc:
            self.error(exc)
            return
        state = t('已启用') if m.enabled else t('已禁用')
        if not messagebox.askyesno(t('删除所选模组'),
                t('删除以下模组文件？\n\n{0}\n状态：{1}\n\n默认交给 Windows 回收站处理；只删除所选文件，同名其他版本保留。\n删除启用版本后，不会自动启用其他版本。').format(m.filename, state), parent=self.root):
            return
        if not self.can_edit():
            return
        self.run(t('正在删除所选模组'),
                 lambda: self.guard_game(lambda: self.manager.delete(filename, expected=(m.size, m.modified))),
                 lambda name: self.status.set(t('已删除：') + name), remove=filename)

    def choose_import(self):
        if not self.can_edit():
            return
        paths = filedialog.askopenfilenames(title=t('选择车辆 ZIP（可多选）'), filetypes=[(t('车辆 ZIP'), '*.zip')])
        if paths:
            self.on_drop(list(paths))

    def on_drop(self, paths):
        self.on_drag(False)
        if not paths:
            return
        self.probe_game()
        if self.game_running is not False:
            return  # Discard drops while locked; never auto-install them after exit.
        if self.busy:
            self.pending_drops.extend(paths)
            self.status.set(t('正在完成当前操作；拖入的文件已排队'))
            return
        if not self.manager:
            messagebox.showinfo(t('先选择模组目录'), t('请先定位游戏或手动选择模组目录，然后导入。'), parent=self.root)
            return
        if not self.ensure_vehicle_directory():
            return
        self.run(t('正在导入 {0} 个 ZIP').format(len(paths)), lambda: self.guard_game(lambda: self.manager.import_files(paths, progress=self.report_import_progress)), self.imported)

    def imported(self, result):
        n = len(result['imported'])
        text = t('导入 {0} 个，跳过 {1} 个，失败 {2} 个。').format(n, len(result['skipped']), len(result['errors']))
        if result['imported']:
            text += t('\n\n实际文件名：\n') + '\n'.join(result['imported'][:12])
        if result['errors']:
            text += t('\n\n失败原因：\n') + '\n'.join(result['errors'][:8])
        if result['skipped']:
            text += '\n\n' + '\n'.join(result['skipped'][:6])
        self.status.set(t('已导入 {0} 个 ZIP；同名新增版本已自动禁用').format(n))
        messagebox.showinfo(t('导入结果'), text, parent=self.root)

    def recover(self):
        if self.can_edit() and self.manager:
            self.run(t('正在恢复中断切换'), lambda: self.guard_game(self.manager.recover),
                     lambda text: messagebox.showinfo(t('恢复结果'), text, parent=self.root))

    def open_folder(self):
        if self.can_edit() and self.manager:
            if os.name == 'nt':
                os.startfile(self.manager.folder)
            else:
                messagebox.showinfo(t('模组目录'), str(self.manager.folder))

    def close(self):
        if self.busy:
            messagebox.showinfo(t('操作进行中'), t('请等待当前文件操作完成再关闭。'), parent=self.root)
            return
        if self.drop:
            self.drop.close()
        self.thumbnails.close()
        self.page_anim.stop()
        self.root.destroy()


def main():
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (OSError, AttributeError):
            pass
    home = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local' / 'share')) / 'FH6CarModManager'
    home.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    lock = None
    try:
        lock = FileLock(home / 'app.lock')
        Application(root, home)
        root.mainloop()
    except Exception as exc:
        messagebox.showerror(t('无法启动'), str(exc), parent=root)
    finally:
        if lock:
            lock.close()


def self_test():
    """Check the actual packaged UI without game discovery or user settings."""
    import tempfile
    root = tk.Tk()
    app = None
    try:
        with tempfile.TemporaryDirectory(prefix='fh6-ui-check-') as home:
            app = Application(root, Path(home), start_services=False)
            root.geometry('1440x900')
            app.apply_game_state(False)
            root.update()
            for button in app.page_buttons.values():
                assert button.cget('text'), 'Navigation text is empty'
                assert button.cget('fg') != button.cget('bg'), 'Navigation text has no contrast'
                assert button.winfo_height() >= button.winfo_reqheight(), 'Navigation text is clipped'
            app.show_page('settings')
            root.update()
            assert app.language_box.winfo_ismapped()
            app.show_page('mods')
            grid = app.tree
            for i in range(24):
                name = f'TEST_CAR_{i}.zip'
                grid.insert('', 'end', iid=name, values=(t('已启用'), 'TEST', '', name, '1 MiB', ''), tags=('enabled',))
            root.update()
            assert grid.columns >= 3
            grid.selection_set('TEST_CAR_20.zip')
            grid.see('TEST_CAR_20.zip')
            app.apply_game_state(True)
            root.update()
            assert grid.selection() == ('TEST_CAR_20.zip',)
            assert grid.disabled
            assert all(str(b.cget('state')) == 'disabled' for b in app.buttons)
            assert str(app.language_box.cget('state')) == 'disabled'
            app.thumbnails.close()
    finally:
        if app:
            app.thumbnails.close()
        root.destroy()


if __name__ == '__main__':
    if '--renderer-self-test' in sys.argv:
        from renderer_check import check_renderer
        index = sys.argv.index('--renderer-self-test')
        raise SystemExit(check_renderer(sys.argv[index + 1]))
    elif '--self-test' in sys.argv:
        self_test()
    else:
        main()
