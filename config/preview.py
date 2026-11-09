"""Fail-closed request boundary, including requests served by WhiteNoise."""
import re
from django.core.exceptions import DisallowedHost
from django.http import HttpResponse
HOST = re.compile(r'(?:localhost|127\.0\.0\.1)(?::8765)?|[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.trycloudflare\.com', re.ASCII)
PUBLIC = frozenset(['/', '/services/', '/about/', '/projects/', '/contact/', '/privacy/', '/terms/', '/robots.txt', '/blog/', '/news/'])
STATIC = re.compile(r'/static/(?:css|js)/[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*\.(?:css|js)(?:\.(?:gz|br))?', re.ASCII)
def allowed_path(path):
    return path in PUBLIC or STATIC.fullmatch(path) is not None
class PreviewBoundary:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        try:
            host = request.get_host()
        except DisallowedHost:
            return HttpResponse('Invalid host', status=400)
        if not HOST.fullmatch(host):
            return HttpResponse('Invalid host', status=400)
        if not allowed_path(request.path_info):
            return HttpResponse('Not found', status=404)
        if request.method not in ('GET', 'HEAD'):
            return HttpResponse('Preview submissions disabled', status=405)
        response = self.get_response(request)
        response['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
        response['Cache-Control'] = 'no-store'
        response['Content-Security-Policy'] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; script-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'"
        return response
