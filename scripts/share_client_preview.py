"""Export public HTTP pages only, then serve an isolated read-only client snapshot.

No Django settings, dotenv, credentials, database or private filesystem imports.
Only paths in the exported manifest are ever served. Source files are not hosted.
"""
import argparse
import hashlib
import html
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, ProxyHandler

ORIGIN = 'http://127.0.0.1:8080'
PAGES = {'/', '/services/', '/about/', '/projects/', '/contact/', '/privacy/', '/terms/', '/blog/', '/news/'}
DETAIL = re.compile(r'/(?:projects/demos/[a-z0-9-]+|projects/[a-z0-9-]+|(?:blog|news)/[a-z0-9-]+(?:/image)?)/')
STATIC = re.compile(r'/static/[A-Za-z0-9_./-]+\.(?:css|js|svg|png|jpg|jpeg|webp|ico)')
MEDIA = re.compile(r'/media/projects/[A-Za-z0-9_/-]+\.(?:png|jpg|jpeg|webp)')


def allowed(path):
    return '..' not in path and (path in PAGES or bool(DETAIL.fullmatch(path) or STATIC.fullmatch(path) or MEDIA.fullmatch(path)))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('a', 'link', 'img', 'script'):
            value = attrs.get('src') or attrs.get('href')
            if value:
                self.urls.add(value)


def export(directory):
    directory.mkdir(parents=True, exist_ok=False)
    opener = build_opener(ProxyHandler({}), NoRedirect())
    queue = sorted(PAGES)
    manifest = {}
    while queue:
        path = queue.pop(0)
        if path in manifest:
            continue
        if not allowed(path) or len(manifest) > 500:
            raise RuntimeError('Preview export path or size boundary failed')
        with opener.open(ORIGIN + path, timeout=20) as response:
            content_type = response.headers.get('Content-Type', 'application/octet-stream')
            data = response.read(10 * 1024 * 1024 + 1)
        if len(data) > 10 * 1024 * 1024:
            raise RuntimeError('Preview response exceeds size limit')
        if content_type.startswith('text/html'):
            text = data.decode('utf-8')
            # Replace server-backed forms only; browser-only demonstration forms stay functional.
            if path in ('/contact/', '/blog/', '/news/'):
                note = ('Client preview: enquiry submissions are disabled. Email faize8042@gmail.com to get in touch.'
                        if path == '/contact/' else 'Client preview: showing the currently published articles. Search and filters are available on the full site.')
                text = re.sub(r'<form\b.*?</form>', '<p role="note">' + note + '</p>', text, flags=re.S | re.I)
            text = re.sub(r'<meta\s+name="robots"[^>]*>', '<meta name="robots" content="noindex, nofollow, noarchive">', text, flags=re.I)
            notice = '<div role="note" style="padding:.6rem 1rem;text-align:center;background:#102b49;color:#fff;font:14px/1.5 sans-serif">Temporary client preview · Enquiry submissions disabled · Interactive tools use sample data</div>'
            text = text.replace('<main id="main-content">', notice + '<main id="main-content">')
            parser = Links()
            parser.feed(text)
            for value in sorted(parser.urls):
                target = urlsplit(urljoin(ORIGIN + path, html.unescape(value)))
                if target.scheme == 'http' and target.netloc == '127.0.0.1:8080' and allowed(target.path):
                    if target.path not in manifest:
                        queue.append(target.path)
            data = text.encode('utf-8')
        filename = hashlib.sha256(path.encode()).hexdigest()
        (directory / filename).write_bytes(data)
        manifest[path] = {'file': filename, 'type': content_type}
    (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest


def serve(directory, manifest, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not write visitor identifiers to local logs.

        def respond(self, status, content=b'', content_type='text/plain; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Robots-Tag', 'noindex, nofollow, noarchive')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; form-action 'none'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'")
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(content)

        def do_GET(self):
            host = self.headers.get('Host', '')
            if not re.fullmatch(r'(?:127\.0\.0\.1|localhost)(?::' + str(port) + r')?|[a-z0-9-]+\.trycloudflare\.com', host):
                return self.respond(400, b'Invalid host')
            path = urlsplit(self.path).path
            if path == '/robots.txt':
                return self.respond(200, b'User-agent: *\nDisallow: /\n')
            record = manifest.get(path)
            if record is None:
                return self.respond(404, b'Not found')
            self.respond(200, (directory / record['file']).read_bytes(), record['type'])

        do_HEAD = do_GET

        def deny(self):
            self.respond(405, b'Client preview is read-only')

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = deny

    print(f'PREVIEW_READY http://127.0.0.1:{port}/ routes={len(manifest)}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    manifest = export(args.output)
    serve(args.output, manifest, args.port)
