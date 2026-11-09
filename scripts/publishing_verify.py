"""Secret-safe probes for verify-publishing.ps1. No service lifecycle operations."""
import contextlib
import io
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STAGE = 'startup'


def stage(name):
    global STAGE
    STAGE = name
    print('INFO: stage=' + name, flush=True)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def setup():
    stage('development-settings-and-django-setup')
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    import django
    django.setup()
    from django.conf import settings
    require(settings.DEPLOYMENT_MODE == 'development', 'Only the development deployment is authorized.')
    require(settings.DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql', 'PostgreSQL required.')
    return settings


def runtime():
    s = setup()
    for middleware in ('django.middleware.csrf.CsrfViewMiddleware',
                       'django.middleware.security.SecurityMiddleware',
                       'django.middleware.clickjacking.XFrameOptionsMiddleware',
                       'django.contrib.sessions.middleware.SessionMiddleware',
                       'django.contrib.auth.middleware.AuthenticationMiddleware'):
        require(middleware in s.MIDDLEWARE, 'Missing required middleware: ' + middleware)
    require(s.ALLOWED_HOSTS and all('*' not in h and not h.startswith('.') for h in s.ALLOWED_HOSTS),
            'Use explicit ALLOWED_HOSTS, without wildcards or suffixes.')
    from urllib.parse import urlsplit
    for origin in s.CSRF_TRUSTED_ORIGINS:
        parsed = urlsplit(origin)
        require('*' not in origin and parsed.scheme in ('http', 'https') and parsed.hostname in s.ALLOWED_HOSTS
                and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                and not parsed.path, 'Invalid or overly broad CSRF trusted origin.')
    require(s.SESSION_COOKIE_HTTPONLY and s.SESSION_COOKIE_SAMESITE in ('Lax', 'Strict'), 'Unsafe session cookie.')
    require(s.CSRF_COOKIE_SAMESITE in ('Lax', 'Strict'), 'Unsafe CSRF SameSite cookie.')
    require(s.SECURE_CONTENT_TYPE_NOSNIFF and s.X_FRAME_OPTIONS == 'DENY', 'Unsafe security headers.')
    require(not s.ENABLE_HTTPS and not s.SECURE_SSL_REDIRECT and not s.SESSION_COOKIE_SECURE
            and not s.CSRF_COOKIE_SECURE and s.SECURE_PROXY_SSL_HEADER is None,
            'Local HTTP verification requires the development HTTP security profile.')
    require(isinstance(s.DEBUG, bool), 'DEBUG must be a boolean; production guards are tested separately.')
    from django.core.checks import run_checks
    require(not [e for e in run_checks() if e.level >= 30], 'Django system checks have warnings/errors; run manage.py check.')
    print('PASS: development middleware, host/origin, cookie, header and Django system checks')
    print('INFO: DEBUG is ' + str(s.DEBUG) + ' in development; production guards tested in isolated tests')


def database():
    setup()
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database(), version()')
        _, version = cursor.fetchone()
        require(version.startswith('PostgreSQL 17.'), 'Expected PostgreSQL 17.')
    executor = MigrationExecutor(connection)
    executor.loader.check_consistent_history(connection)
    require(not executor.migration_plan(executor.loader.graph.leaf_nodes()),
            'Pending migrations: review and apply separately; this suite never migrates the application DB.')
    print('PASS: PostgreSQL 17 connectivity and applied migration history (read-only)')


def drift():
    setup()
    stage('makemigrations-check-dry-run')
    from django.core.management import call_command
    try:
        call_command('makemigrations', check=True, dry_run=True, interactive=False, verbosity=1)
    except SystemExit as error:
        if error.code == 1:
            print('FAIL: makemigrations --check --dry-run exited 1: model changes need migrations; no migrations written')
        raise
    print('PASS: no model/migration drift across installed apps')


def storage():
    s = setup()
    import stat
    configured_root = Path(getattr(s, 'PUBLISHING_IMAGE_ROOT', ROOT / 'private_publishing'))
    require(not configured_root.is_symlink(), 'Private publishing root must not be a symlink.')
    root = configured_root.resolve()
    for public in (Path(s.MEDIA_ROOT).resolve(), Path(s.STATIC_ROOT).resolve()):
        require(root != public and public not in root.parents and root not in public.parents,
                'Publishing storage overlaps public media/static storage.')
    require(root.is_dir() and not root.is_symlink(), 'Private publishing storage is missing or a symlink.')
    mode = root.stat()
    require(mode.st_uid == os.geteuid() and stat.S_IMODE(mode.st_mode) == 0o700,
            'Private storage root must belong to the web UID and have mode 0700.')
    require(os.access(root, os.R_OK | os.W_OK | os.X_OK), 'Web user cannot use private storage.')
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            info = path.lstat()
            require(not path.is_symlink() and info.st_uid == os.geteuid(), 'Unsafe owner or symlink in private storage.')
            require(not stat.S_IMODE(info.st_mode) & 0o022, 'Group/world writable private storage entry.')
    print('PASS: private publishing storage location, ownership, access and permissions (no writes)')


def run_regression_suite():
    from django.core.management import call_command
    call_command('test', 'config', 'core', 'projects', 'contact', 'analytics', 'blog', 'news', 'publishing',
                 interactive=False, verbosity=1,
                 testrunner='scripts.publishing_test_runner.VerificationRunner')


def tests():
    # Refuse production before selecting test settings. A new random name prevents
    # --noinput from deleting any pre-existing default test database.
    name = 'test_publishing_qa_' + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='publishing-qa-') as directory:
        os.environ['PUBLISHING_QA_DATABASE'] = name
        os.environ['PUBLISHING_QA_TEMP'] = directory
        os.environ['DJANGO_SETTINGS_MODULE'] = 'config.verification_test_settings'
        stage('verification-test-settings-and-django-setup')
        import django
        django.setup()
        from django.conf import settings
        require(settings.DATABASES['default']['ENGINE'] == 'django.db.backends.postgresql', 'PostgreSQL required.')
        from django.db import connection
        stage('postgres-test-database-preflight')
        with connection.cursor() as cursor:
            cursor.execute('SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = current_user')
            require(cursor.fetchone()[0], 'Database role lacks CREATEDB; isolated PostgreSQL tests cannot create a database. No privileges changed.')
            cursor.execute('SELECT 1 FROM pg_database WHERE datname = %s', [name])
            require(cursor.fetchone() is None, 'Allocated test database already exists; refusing to run.')
        # Do not carry a connection to the application DB into test setup.
        from django.db import connections
        connections.close_all()
        stage('django-test-create-migrate-run-destroy')
        run_regression_suite()
    print('PASS: all Django regression and publishing tests on isolated PostgreSQL database')


def live():
    """Local ingress only; no credentials, publishing mutations or contact POSTs."""
    import http.cookiejar
    from html.parser import HTMLParser
    from urllib.request import build_opener, HTTPCookieProcessor, Request
    from urllib.error import HTTPError
    from urllib.parse import urljoin, urlsplit, urlencode

    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links = set()
        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            if tag == 'a' and values.get('href', '').startswith('/'):
                self.links.add(values['href'])

    base = 'http://127.0.0.1:8080'
    jar = http.cookiejar.CookieJar()

    def request(path, data=None, headers=None):
        target = urljoin(base, path)
        require(urlsplit(target).netloc == '127.0.0.1:8080', 'Refusing external HTTP request.')
        # Prevent automatic redirects to other services/origins.
        from urllib.request import HTTPRedirectHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        safe = build_opener(HTTPCookieProcessor(jar), NoRedirect())
        try:
            response = safe.open(Request(target, data=data, headers=headers or {}), timeout=15)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read(4 * 1024 * 1024).decode('utf-8', 'replace')

    routes = ('/', '/services/', '/about/', '/projects/', '/contact/', '/privacy/', '/terms/',
              '/blog/', '/news/', '/robots.txt', '/sitemap.xml', '/health/', '/admin/login/')
    links = set()
    articles = set()
    for route in routes:
        status, headers, body = request(route)
        require(status == 200, 'Live route failed: ' + route + ' (HTTP ' + str(status) + ')')
        if route not in ('/robots.txt', '/sitemap.xml', '/health/'):
            require(headers.get('X-Content-Type-Options') == 'nosniff' and headers.get('X-Frame-Options') == 'DENY',
                    'Missing live security headers: ' + route)
            require(headers.get('Referrer-Policy'), 'Missing Referrer-Policy: ' + route)
        parser = Links()
        parser.feed(body)
        links.update(parser.links)
        if route in ('/blog/', '/news/'):
            articles.update(p for p in parser.links if re.fullmatch(r'/(blog|news)/[-\w]+/', p))
        print('PASS: live ' + route)
    for route in sorted(links):
        if route.startswith('//') or route.startswith('/admin/'):
            continue
        require(request(route)[0] == 200, 'Broken local navigation link (path omitted; inspect page navigation).')
    for section in ('blog', 'news'):
        for params in ('?q=verification-no-match', '?page=2', '?page=invalid', '?category=unknown' if section == 'blog' else '?kind=company'):
            require(request('/' + section + '/' + params)[0] == 200, 'Live search/filter/pagination failed: ' + section)
    for route in articles:
        status, headers, body = request(route)
        require(status == 200 and '<title>' in body and 'name="description"' in body, 'Live published detail/metadata failed.')
    print(('PASS: live published article details' if articles else 'SKIP: live published details; no public article links available'))
    status, headers, _ = request('/admin/')
    require(status == 302 and '/admin/login/' in headers.get('Location', ''), 'Anonymous Admin access is not denied.')
    require(request('/admin/login/', headers={'Host': 'invalid.example'})[0] in (400, 444), 'Unknown Host was not rejected.')
    token = next((c.value for c in jar if c.name == 'csrftoken'), None)
    require(token, 'Admin CSRF cookie missing.')
    for data, origin, expected in (({}, base, 403), ({'csrfmiddlewaretoken': token}, 'http://invalid.example', 403),
                                   ({'csrfmiddlewaretoken': token}, base, 200)):
        require(request('/admin/login/', urlencode(data).encode(), {'Origin': origin})[0] == expected,
                'Live Admin CSRF/origin handling failed; inspect Nginx Host forwarding and CSRF configuration.')
    # Only empty credentials are submitted. There is no authentication attempt
    # with a username/password, no content creation and no outgoing email.
    for route in ('/private_publishing/verification-missing.jpg', '/media/private_publishing/verification-missing.jpg',
                  '/static/private_publishing/verification-missing.jpg'):
        require(request(route)[0] == 404, 'Unexpected private-storage public route response.')
    print('PASS: local navigation, search, filters, pagination, anonymous Admin, Host and live CSRF through Nginx')


def source():
    css = (ROOT / 'static/css/publishing.css').read_text(encoding='utf-8')
    require('@media' in css and ('max-width' in css or 'min-width' in css), 'Publishing CSS has no responsive breakpoint.')
    nginx = (ROOT / 'nginx/default.conf').read_text(encoding='utf-8')
    require('proxy_set_header Host $http_host;' in nginx and 'proxy_set_header X-Forwarded-Proto $scheme;' in nginx,
            'Development Nginx must preserve Host port and overwrite forwarded scheme.')
    require('private_publishing' not in nginx, 'Review unexpected private publishing reference in development Nginx.')
    print('PASS: source proxy forwarding contract and responsive CSS breakpoints')


def browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit(2)
    with sync_playwright() as playwright:
        try:
            browser_instance = playwright.chromium.launch(headless=True)
        except Exception:
            # Package installation alone does not imply a working browser.
            raise SystemExit(2)
        try:
            for width, height in ((390, 844), (768, 1024), (1440, 900)):
                context = browser_instance.new_context(viewport={'width': width, 'height': height})
                # Only local pages/assets; never follow analytics or third-party links.
                context.route('**/*', lambda route: route.continue_() if
                    route.request.url.startswith('http://127.0.0.1:8080/') else route.abort())
                page = context.new_page()
                for path in ('/', '/blog/', '/news/'):
                    response = page.goto('http://127.0.0.1:8080' + path, wait_until='networkidle')
                    require(response and response.status == 200, 'Browser navigation failed.')
                    require(page.locator('h1').count() > 0, 'Browser page has no main heading.')
                    require(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'),
                            'Horizontal overflow at viewport ' + str(width) + ' for ' + path)
                    require(page.locator('body').is_visible(), 'Browser body is not visible.')
                context.close()
            print('PASS: Chromium mobile/tablet/desktop navigation, visible headings and horizontal overflow checks')
        finally:
            browser_instance.close()


if __name__ == '__main__':
    # Never forward raw tracebacks, test form data, settings or DB connection
    # errors to the console. Test identifiers and counts are safe diagnostics.
    output = io.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            {'runtime': runtime, 'database': database, 'drift': drift, 'storage': storage,
             'tests': tests, 'live': live, 'source': source, 'browser': browser}[sys.argv[1]]()
    except BaseException as error:
        code = 2 if isinstance(error, SystemExit) and error.code == 2 else 1
        if code == 2:
            pass
        elif isinstance(error, AssertionError):
            print('FAIL: ' + str(error))
        else:
            # Frame metadata only: never include source text, locals or messages.
            import traceback
            for frame in traceback.extract_tb(error.__traceback__):
                print('INFO: exception-frame=' + Path(frame.filename).name + ':' + str(frame.lineno) + ':' + frame.name)
            sqlstate = getattr(error.__cause__, 'sqlstate', None) or getattr(error.__cause__, 'pgcode', None)
            detail = (' SQLSTATE=' + sqlstate) if isinstance(sqlstate, str) and re.fullmatch('[A-Z0-9]{5}', sqlstate) else ''
            exit_detail = (' exit=' + str(error.code)) if isinstance(error, SystemExit) and isinstance(error.code, int) else ''
            print('FAIL: stage=' + STAGE + ' exception=' + type(error).__name__ + exit_detail + detail + '; raw exception withheld')
    for line in output.getvalue().splitlines():
        if line.startswith(('PASS:', 'SKIP:', 'INFO:', 'Ran ', 'OK', 'FAILED (')):
            print(line)
        elif line == 'FAIL: makemigrations --check --dry-run exited 1: model changes need migrations; no migrations written':
            print(line)
        elif re.fullmatch(r'(FAIL|ERROR): test_[A-Za-z0-9_]+ \([A-Za-z0-9_.]+\)', line):
            print(line)
    if code == 0:
        print('QA_COMPLETE:' + sys.argv[1])
    sys.exit(code)
