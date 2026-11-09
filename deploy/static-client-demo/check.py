"""Dependency-free offline checks; exits nonzero on any failed check."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit

from build import HERE, OUT, ASSETS, PAGES

class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.refs, self.tags = set(), [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        if 'id' in a:
            if a['id'] in self.ids:
                raise ValueError('Duplicate ID: ' + a['id'])
            self.ids.add(a['id'])
        for attr in ('href', 'src', 'action', 'poster'):
            if attr in a:
                self.refs.append(a[attr])
        if 'srcset' in a:
            self.refs.extend(s.strip().split()[0] for s in a['srcset'].split(','))

class DemoChecks(unittest.TestCase):
    def test_exact_public_allowlist_and_hashes(self):
        expected = {v[1] for v in PAGES.values()} | {'assets/' + a for a in ASSETS} | {'assets/demo.css', 'robots.txt'}
        actual = {p.relative_to(OUT).as_posix() for p in OUT.rglob('*') if p.is_file()}
        self.assertEqual(expected, actual)
        manifest = json.loads((HERE / 'public-manifest.json').read_text())
        self.assertEqual(expected, set(manifest))
        for p in OUT.rglob('*'):
            self.assertFalse(p.is_symlink(), str(p))
            if p.is_file():
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), manifest[p.relative_to(OUT).as_posix()])

    def test_links_assets_and_fragments(self):
        docs = {p: Document(p.read_text(encoding='utf-8')) for p in OUT.glob('*.html')}
        refs = [(p, ref) for p, doc in docs.items() for ref in doc.refs]
        for p in OUT.rglob('*.css'):
            css = p.read_text(encoding='utf-8')
            refs.extend((p, ref.strip(' \"\'')) for ref in re.findall(r'url\((.*?)\)', css))
            self.assertNotIn('@import', css)
        for source, ref in refs:
            parsed = urlsplit(ref)
            self.assertFalse(parsed.scheme or parsed.netloc, f'External dependency: {ref}')
            self.assertFalse(parsed.query, ref)
            target = (OUT / unquote(parsed.path).lstrip('/') if parsed.path.startswith('/') else source.parent / unquote(parsed.path)).resolve() if parsed.path else source
            self.assertTrue(target.is_relative_to(OUT.resolve()), ref)
            self.assertTrue(target.is_file(), f'{source.name}: missing {ref}')
            if parsed.fragment:
                self.assertIn(unquote(parsed.fragment), docs[target].ids, f'{source.name}: broken fragment {ref}')

    def test_sensitive_content_and_no_backend(self):
        patterns = [r'-----BEGIN .*PRIVATE KEY', r'(?i)(?:secret_key|database_url|smtp_password|aws_secret_access_key)\s*[=:]', r'AKIA[0-9A-Z]{16}', r'(?i)(?:postgres|redis)://', r'{[%{]', r'(?i)(?:href|src|action)=[\"\'][^\"\']*(?:/admin|/api|/health|/debug|/media|private_uploads)']
        for p in OUT.rglob('*'):
            if not p.is_file():
                continue
            self.assertIn(p.suffix, ('.html', '.css', '.js', '.txt'))
            self.assertFalse(any(part.startswith('.') for part in p.relative_to(OUT).parts))
            text = p.read_text(encoding='utf-8')
            for pattern in patterns:
                self.assertIsNone(re.search(pattern, text), f'{p.name}: forbidden pattern {pattern}')
        for p in OUT.rglob('*.js'):
            self.assertIsNone(re.search(r'\b(fetch|XMLHttpRequest|WebSocket|sendBeacon)\b', p.read_text(encoding='utf-8')))

    def test_pages_navigation_contact(self):
        for _, filename in PAGES.values():
            text = (OUT / filename).read_text(encoding='utf-8')
            doc = Document(text)
            self.assertEqual(sum(tag == 'h1' for tag, _ in doc.tags), 1)
            self.assertIn(('meta', {'name': 'robots', 'content': 'noindex, nofollow'}), doc.tags)
            self.assertIn('width=device-width', text)
            self.assertIn('Contact submissions disabled', text)
            self.assertEqual(sum(a.get('aria-current') == 'page' for _, a in doc.tags), 0 if filename in ('privacy.html','terms.html') else 1)
            for dest in ('index.html','about.html','services.html','projects.html','contact.html'):
                self.assertIn(dest, doc.refs)
            self.assertFalse(any(tag == 'form' for tag, _ in doc.tags))
            for tag, attrs in doc.tags:
                if tag in ('input', 'textarea', 'button') and attrs.get('id', '').startswith('demo-'):
                    self.assertIn('disabled', attrs)
        contact = (OUT / 'contact.html').read_text(encoding='utf-8')
        self.assertIn('No enquiry is saved or emailed', contact)
        self.assertNotIn('type="submit"', contact)
        self.assertNotIn('type="file"', contact)
        self.assertIn('Portfolio content unavailable in this demo', (OUT / 'projects.html').read_text(encoding='utf-8'))

    def test_isolated_server_configuration(self):
        compose = (HERE / 'compose.yaml').read_text()
        self.assertEqual(re.findall(r'127\.0\.0\.1:\d+:\d+', compose), ['127.0.0.1:8765:8080'])
        self.assertIn('image: nginx:stable-alpine', compose)
        mounts = re.findall(r'- (\./[^\n]+)', compose)
        self.assertEqual(mounts, ['./site:/usr/share/nginx/html:ro', './nginx.conf:/etc/nginx/nginx.conf:ro'])
        self.assertNotIn('build:', compose)
        self.assertNotIn('env_file:', compose)
        nginx = (HERE / 'nginx.conf').read_text()
        for rule in ('location / { return 404; }', "form-action 'none'", "connect-src 'none'", 'return 405', 'autoindex off', 'access_log off'):
            self.assertIn(rule, nginx)
        for forbidden in ('proxy_pass', 'fastcgi_pass', 'uwsgi_pass'):
            self.assertNotIn(forbidden, nginx)

if __name__ == '__main__':
    unittest.main(verbosity=2)
