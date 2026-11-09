# Development Admin CSRF origin fix

The browser uses `http://127.0.0.1:8080`, but development Nginx previously
forwarded `Host $host`, dropping `:8080`. Django compared the browser Origin
against `http://127.0.0.1` and rejected the POST. The same issue affects localhost.

Development `nginx/default.conf` now uses:

```nginx
proxy_set_header Host $http_host;
```

This preserves the port and allows Django's normal same-origin check. No
`CSRF_TRUSTED_ORIGINS` addition is needed. `ALLOWED_HOSTS` already includes
`localhost` and `127.0.0.1`; host entries correctly omit ports. Nginx overwrites
`X-Forwarded-Proto` with `$scheme`; development uses HTTP and does not trust
forwarded scheme headers. `USE_X_FORWARDED_HOST` remains Django's default False.
CSRF middleware, token checks, and production configuration are unchanged.

## Apply to the existing development stack

From PowerShell, using the same Compose project selection as the running stack:

```powershell
Set-Location D:\TechWorldWebsite
docker compose -f compose.yaml exec -T nginx nginx -t
# Only after the configuration test succeeds:
docker compose -f compose.yaml exec -T nginx nginx -s reload
```

The configuration is bind-mounted, so no image rebuild or container restart is
required. No web recreation, migrations, or database operations are needed.
These commands target development only. They were not executed in the repair
session because Docker engine access was denied.

## Verify without logging in or changing data

This script GETs the Admin login form and POSTs an empty login form with its
CSRF token. HTTP 200 means CSRF passed and required-field errors were rendered;
it does not mean authentication succeeded. No credentials are supplied.

```powershell
@'
import http.cookiejar
import urllib.parse
import urllib.request

for host in ('127.0.0.1', 'localhost'):
    origin = f'http://{host}:8080'
    url = origin + '/admin/login/'
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    with opener.open(url, timeout=15) as response:
        assert response.status == 200
    token = next(c.value for c in cookies if c.name == 'csrftoken')
    data = urllib.parse.urlencode({'csrfmiddlewaretoken': token}).encode()
    request = urllib.request.Request(url, data=data, headers={'Origin': origin})
    with opener.open(request, timeout=15) as response:
        assert response.status == 200
        print(f'{origin}: Admin POST passed CSRF (HTTP 200)')
'@ | python -
```

Offline regression checks (no .env reads, database access, or migrations):

```powershell
python manage.py check --settings=config.publishing_test_settings
python manage.py test config.test_development_csrf config.tests contact.tests.PrivateAttachmentStorageTests publishing.tests.PreviewNavigationTests --settings=config.publishing_test_settings --verbosity=1
```

Validation during repair: normal Django settings passed `manage.py check` with
synthetic environment values, `.env` loading disabled, and an in-memory database
URL; all 44 selected database-free tests passed using isolated test settings. Docker/Nginx
syntax and live proxy checks remain to be run on the development host. Tests
requiring a database were excluded to honor the no-database/no-migrations scope.
