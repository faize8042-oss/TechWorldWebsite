"""Create a new curated build context; never scans private trees or dotenv."""
from pathlib import Path
import shutil
ROOT = Path(__file__).resolve().parents[2]
def prepare(destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    files = ['config/__init__.py', 'core/__init__.py', 'core/views.py', 'core/context_processors.py']
    files += ['config/' + n for n in ('preview.py','preview_settings.py','preview_urls.py','preview_wsgi.py')]
    files += [str(p.relative_to(ROOT)) for p in (ROOT/'templates').rglob('*.html')]
    for folder, ext in [('css','css'), ('js','js')]:
        files += [str(p.relative_to(ROOT)) for p in (ROOT/'static'/folder).glob('*.'+ext)]
    for file in files:
        source = ROOT / file
        if source.is_symlink() or any(p.is_symlink() for p in source.parents if p != ROOT.parent):
            raise ValueError('Symlink rejected')
        target = destination / file
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    for name in ('Dockerfile','.dockerignore','gunicorn.py'):
        source = ROOT/'deploy/client-preview'/name
        if source.is_symlink() or any(p.is_symlink() for p in source.parents if p != ROOT.parent):
            raise ValueError('Symlink rejected')
        shutil.copyfile(source, destination/name)
if __name__ == '__main__':
    import sys
    prepare(sys.argv[1])
