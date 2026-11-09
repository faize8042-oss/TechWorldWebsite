"""Offline, explicit-allowlist export. Never imports Django or reads runtime data."""
from pathlib import Path
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'site'
PAGES = {'home': ('core/home.html', 'index.html'), 'about': ('core/about.html', 'about.html'),
         'services': ('core/services.html', 'services.html'), 'projects:list': ('projects/project_list.html', 'projects.html'),
         'contact:contact': ('contact/contact.html', 'contact.html'), 'privacy': ('core/privacy.html', 'privacy.html'),
         'terms': ('core/terms.html', 'terms.html')}
ASSETS = [f'css/{name}.css' for name in ('style', 'components', 'responsive', 'about', 'services', 'projects', 'contact')] + [f'js/{name}.js' for name in ('theme', 'navigation', 'main')]

def read(name):
    return (ROOT / 'templates' / name).read_text(encoding='utf-8')

def block(source, name):
    match = re.search(r'{% block ' + name + r' %}(.*?){% endblock %}', source, re.S)
    return match.group(1).strip() if match else ''

def links(source):
    source = re.sub(r"{% url '([^']+)' %}", lambda m: PAGES[m[1]][1], source)
    return re.sub(r"{% static '([^']+)' %}", lambda m: 'assets/' + m[1] if m[1] in ASSETS else (_ for _ in ()).throw(ValueError('Asset not allowlisted')), source)

def build():
    # Refuse stale or unexpected files rather than copying or deleting them.
    expected = {v[1] for v in PAGES.values()} | {'assets/' + a for a in ASSETS} | {'assets/demo.css', 'robots.txt'}
    OUT.mkdir(exist_ok=True)
    for p in OUT.rglob('*'):
        if p.is_symlink() or (p.is_file() and p.relative_to(OUT).as_posix() not in expected):
            raise ValueError(f'Unexpected output: {p}')
    for asset in ASSETS:
        target = OUT / 'assets' / asset
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / 'static' / asset).read_bytes())
    (OUT / 'assets/demo.css').write_text('.demo-notice{padding:12px 18px;text-align:center;background:var(--color-surface);color:var(--color-text);border-bottom:1px solid var(--color-border);font-size:.875rem}.demo-fields{border:0;padding:0;margin:20px 0;min-width:0}.demo-fields input,.demo-fields textarea{width:100%;max-width:100%}.demo-fields:disabled{opacity:.65}\n', encoding='utf-8')
    for key, (template, filename) in PAGES.items():
        source = read(template)
        content = block(source, 'content')
        if key == 'projects:list':
            start = content.index('{% if projects %}')
            end = content.rindex('{% endif %}') + len('{% endif %}')
            empty = content[content.index('<div class="empty-portfolio"'):content.rindex('{% endif %}')]
            empty = empty.replace('No projects are published yet.', 'Portfolio content unavailable in this demo.').replace('There are no published projects to show right now.', 'Published portfolio records have not been exported for this static demo.')
            content = content[:start] + empty + content[end:]
        if key == 'contact:contact':
            start = content.index('{% if messages %}')
            end = content.index('</form>', start) + len('</form>')
            fields = ''.join(f'<div class="form-field"><label for="demo-{name}">{label}</label><input id="demo-{name}" type="{kind}" disabled></div>' for name, label, kind in [('name','Full name','text'),('email','Email address','email'),('type','Project type','text'),('budget','Estimated budget','text')])
            content = content[:start] + '<p class="demo-notice" role="note">Demo only. Contact submissions and uploads are disabled. No enquiry is saved or emailed. Please contact your Codeventra Labs representative directly.</p><fieldset class="demo-fields" disabled aria-label="Disabled demo enquiry fields">' + fields + '<div class="form-field"><label for="demo-message">Project details</label><textarea id="demo-message" rows="5" disabled></textarea></div><button class="button button-primary" type="button" disabled>Submission disabled — demo only</button></fieldset>' + content[end:]
        if key in ('privacy', 'terms'):
            content = '<div class="demo-notice" role="note">Reference website policy. This static demo has no contact submission, upload, email, or application analytics service. Theme preference is stored in your browser. The policy below describes the full website.</div>' + content
        nav = read('includes/navbar.html')
        nav = re.sub(r'{% if (.*?) %}(.*?){% endif %}', lambda m: m[2] if (f"== '{key}'" in m[1] or (key in ('projects:list', 'contact:contact') and f"== '{key.split(':')[0]}'" in m[1])) else '', nav, flags=re.S)
        styles = ''.join(f'<link rel="stylesheet" href="assets/{a}">\n' for a in ASSETS if a.startswith('css/') and a.split('/')[-1] in ('style.css','components.css','responsive.css'))
        scripts = ''.join(f'<script src="assets/{a}" defer></script>\n' for a in ASSETS if a.startswith('js/'))
        html = '<!DOCTYPE html>\n<html lang="en" data-theme="dark"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#0a0d19"><meta name="robots" content="noindex, nofollow"><title>' + block(source, 'title') + '</title><meta name="description" content="' + block(source,'meta_description').replace('\n',' ') + '">' + styles + block(source,'extra_head') + '<link rel="stylesheet" href="assets/demo.css">' + scripts + '</head><body><a class="skip-link" href="#main-content">Skip to content</a>' + nav + '<div class="demo-notice" role="note">Temporary client demo · Contact submissions disabled</div><main id="main-content">' + content + '</main>' + read('includes/footer.html') + '</body></html>\n'
        html = links(html)
        if '{%' in html or '{{' in html:
            raise ValueError(f'Unresolved template syntax in {filename}')
        (OUT / filename).write_text(html, encoding='utf-8')
    (OUT / 'robots.txt').write_text('User-agent: *\nDisallow: /\n', encoding='utf-8')
    manifest = {p.relative_to(OUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.rglob('*')) if p.is_file()}
    (HERE / 'public-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Built {len(PAGES)} pages and {len(manifest)} allowlisted public files.')

if __name__ == '__main__':
    build()
