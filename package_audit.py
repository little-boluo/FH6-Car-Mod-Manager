"""Report actual Windows publish size; never guess savings from source sizes."""
from pathlib import Path
import sys


def report(folder, destination):
    root = Path(folder).resolve()
    files = [p for p in root.rglob('*') if p.is_file()]
    size = lambda p: p.stat().st_size
    total = sum(map(size, files))
    renderer = sum(size(p) for p in files if p.relative_to(root).parts[0] == 'renderer')
    lines = ['FH6 Car Mod Manager 0.8.8 publish inventory',
             f'Total: {total/1024**2:.2f} MiB / {len(files)} files',
             f'Renderer: {renderer/1024**2:.2f} MiB',
             '.NET and Windows App SDK runtimes remain self-contained.',
             'Only renderer-view dependencies are compiled; no main FTS shell or Markdown docs.',
             '', 'Largest files:']
    lines += [f'{size(p)/1024**2:9.2f} MiB  {p.relative_to(root)}' for p in sorted(files,key=size,reverse=True)[:30]]
    Path(destination).write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines[:4]))


if __name__ == '__main__': report(sys.argv[1], sys.argv[2])
