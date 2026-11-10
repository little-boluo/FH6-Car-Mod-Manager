"""Report actual Windows publish size; never guess savings from source sizes."""
from pathlib import Path
import sys

from version import APP_VERSION


def report(folder, destination):
    root = Path(folder).resolve()
    files = [p for p in root.rglob('*') if p.is_file()]
    size = lambda p: p.stat().st_size
    total = sum(map(size, files))
    renderer = sum(size(p) for p in files if p.relative_to(root).parts[0] == 'renderer')
    lines = [f'FH6 Car Mod Manager {APP_VERSION} publish inventory',
             f'Total: {total/1024**2:.2f} MiB / {len(files)} files',
             f'Renderer: {renderer/1024**2:.2f} MiB',
             '.NET and Windows App SDK runtimes remain self-contained.',
             'Windows App SDK: WinUI/Foundation/DWrite components only (no AI, ML or Widgets);'
             ' WinUI languages en-us, zh-CN, zh-TW.',
             'Optional: SaveDiskSpace.bat applies NTFS LZX compression to the installed folder.',
             'Only renderer-view dependencies are compiled; no main FTS shell or Markdown docs.',
             '', 'Largest files:']
    lines += [f'{size(p)/1024**2:9.2f} MiB  {p.relative_to(root)}' for p in sorted(files,key=size,reverse=True)[:30]]
    Path(destination).write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines[:4]))


if __name__ == '__main__': report(sys.argv[1], sys.argv[2])
