"""Run only after the operator starts this demo. Targets loopback port 8765 only."""
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import hashlib
import json
from pathlib import Path

BASE = 'http://127.0.0.1:8765'
manifest = json.loads((Path(__file__).parent / 'public-manifest.json').read_text())

def request(path, method='GET'):
    try:
        return urlopen(Request(BASE + path, method=method, data=b'' if method == 'POST' else None), timeout=5)
    except HTTPError as error:
        return error

def verify():
    for name, digest in manifest.items():
        with request('/' + name) as response:
            assert response.status == 200, (name, response.status)
            assert hashlib.sha256(response.read()).hexdigest() == digest, name
            assert response.headers.get('X-Content-Type-Options') == 'nosniff', name
            assert response.headers.get('X-Robots-Tag') == 'noindex, nofollow', name
            csp = response.headers.get('Content-Security-Policy', '')
            assert "form-action 'none'" in csp and "connect-src 'none'" in csp, name
    with request('/') as response:
        assert response.status == 200
        assert hashlib.sha256(response.read()).hexdigest() == manifest['index.html']
    for path in ('/.env', '/.git/config', '/db.sqlite3', '/admin/', '/api/', '/health/', '/healthz', '/debug/', '/media/example.png', '/private_uploads/example.pdf', '/assets/', '/nginx.conf', '/compose.yaml', '/build.py', '/public-manifest.json', '/not-found.html', '/assets/js/unknown.js'):
        with request(path) as response:
            assert response.status == 404, (path, response.status)
    for method in ('POST', 'PUT', 'DELETE', 'OPTIONS'):
        with request('/contact.html', method) as response:
            assert response.status == 405, (method, response.status)
    with request('/contact.html', 'HEAD') as response:
        assert response.status == 200 and not response.read()
    print('PASS: all 19 public files and hashes, headers, root, denied paths, rejected writes, HEAD.')

if __name__ == '__main__':
    verify()
