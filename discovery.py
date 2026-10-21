"""Bounded Windows game discovery, with no drive-wide recursive scan."""
import os
from pathlib import Path
import re
import subprocess

EXE = 'forzahorizon6.exe'


def vdf_value(text, key):
    m = re.search(r'"' + re.escape(key) + r'"\s*"((?:\\.|[^"\\])*)"', text, re.I)
    return m[1].replace('\\\\', '\\').replace('\\"', '"') if m else None


def steam_libraries(root):
    paths = [Path(root)]
    p = Path(root) / 'steamapps' / 'libraryfolders.vdf'
    try:
        content = p.read_text(encoding='utf-8', errors='replace')
        for value in re.findall(r'"path"\s*"((?:\\.|[^"\\])*)"', content, re.I):
            paths.append(Path(value.replace('\\\\', '\\')))
        for value in re.findall(r'"\d+"\s*"([A-Za-z]:[^"\n]*)"', content):
            paths.append(Path(value.replace('\\\\', '\\')))
    except OSError:
        pass
    return paths


def find_in_install(path):
    root = Path(path)
    result = []
    if root.name.casefold() == EXE and root.is_file():
        return [root.absolute()]
    for directory in (root, root / 'Content'):
        try:
            for p in directory.iterdir():
                if p.name.casefold() == EXE and p.is_file():
                    result.append(p.absolute())
        except OSError:
            pass
    return result


def running_exes():
    if os.name != 'nt':
        return []
    cmd = ("[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
           "Get-CimInstance Win32_Process -Filter \"Name='forzahorizon6.exe'\" "
           "| ForEach-Object { $_.ExecutablePath }")
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', cmd],
                                capture_output=True, timeout=5, creationflags=0x08000000)
        return [Path(s.strip()) for s in result.stdout.decode('utf-8-sig', errors='replace').splitlines() if s.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []


def registry_paths():
    installs, steam = [], []
    if os.name != 'nt':
        return installs, steam
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, r'SOFTWARE\Valve\Steam', 0, winreg.KEY_READ | view) as key:
                    for value in ('SteamPath', 'InstallPath'):
                        try:
                            steam.append(Path(winreg.QueryValueEx(key, value)[0]))
                        except OSError:
                            pass
            except OSError:
                pass
            try:
                with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall', 0, winreg.KEY_READ | view) as parent:
                    for i in range(winreg.QueryInfoKey(parent)[0]):
                        try:
                            with winreg.OpenKey(parent, winreg.EnumKey(parent, i)) as key:
                                name = winreg.QueryValueEx(key, 'DisplayName')[0]
                                if re.search(r'forza\s*horizon\s*6', name, re.I):
                                    installs.append(Path(winreg.QueryValueEx(key, 'InstallLocation')[0]))
                        except OSError:
                            pass
            except OSError:
                pass
    return installs, steam


def default_paths():
    """Collect local drive and environment roots separately for test isolation."""
    installs, steam = [], []
    if os.name == 'nt':
        import ctypes
        drives = [Path(f'{letter}:\\') for letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ'
                  if ctypes.windll.kernel32.GetDriveTypeW(f'{letter}:\\') == 3]
        for env in ('ProgramFiles', 'ProgramFiles(x86)'):
            if os.environ.get(env):
                steam.append(Path(os.environ[env]) / 'Steam')
        for drive in drives:
            for root in (drive / 'XboxGames', drive / 'Games', drive):
                for title in ('Forza Horizon 6', 'ForzaHorizon6', 'FH6'):
                    installs.append(root / title)
                if root != drive:
                    try:
                        installs.extend(p for p in root.iterdir() if p.is_dir() and re.search(r'forza.*6', p.name, re.I))
                    except OSError:
                        pass
            steam += [drive / 'Steam', drive / 'SteamLibrary', drive / 'Games' / 'Steam']
    return installs, steam


def discover(saved_exe='', extra_roots=()):
    """Return only paths backed by an actual executable; no folder is created here."""
    candidates = []
    if saved_exe:
        candidates += find_in_install(saved_exe)
    for p in running_exes():
        candidates += find_in_install(p)
    installs, steam = registry_paths()
    installs += [Path(p) for p in extra_roots]
    local_installs, local_steam = default_paths()
    installs += local_installs
    steam += local_steam
    seen_libraries = set()
    for steam_root in steam:
        for lib in steam_libraries(steam_root):
            key = str(lib).casefold()
            if key in seen_libraries:
                continue
            seen_libraries.add(key)
            common = lib / 'steamapps' / 'common'
            installs += [common / n for n in ('ForzaHorizon6', 'Forza Horizon 6', 'FH6')]
            try:
                for manifest in (lib / 'steamapps').glob('appmanifest_*.acf'):
                    content = manifest.read_text(encoding='utf-8', errors='replace')
                    if re.search(r'forza\s*horizon\s*6', vdf_value(content, 'name') or '', re.I):
                        folder = vdf_value(content, 'installdir')
                        if folder and '/' not in folder and '\\' not in folder and folder not in ('.', '..'):
                            installs.append(common / folder)
            except OSError:
                pass
    for root in installs:
        candidates += find_in_install(root)
    result, seen = [], set()
    for p in candidates:
        key = str(p.resolve()).casefold()
        if key not in seen:
            seen.add(key)
            result.append(p.resolve())
    return result
