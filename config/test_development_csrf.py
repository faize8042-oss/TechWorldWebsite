"""Development proxy contract and Admin CSRF checks; no database access."""
from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, override_settings


@override_settings(
    ALLOWED_HOSTS=["127.0.0.1", "localhost"],
    CSRF_TRUSTED_ORIGINS=[],
    SECURE_SSL_REDIRECT=False,
    SECURE_PROXY_SSL_HEADER=None,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    MIDDLEWARE=[
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ],
)
class DevelopmentAdminCsrfTests(SimpleTestCase):
    def admin_post(self, host, origin, include_token=True):
        client = Client(enforce_csrf_checks=True)
        response = client.get("/admin/login/", HTTP_HOST=host)
        self.assertEqual(response.status_code, 200)
        data = {}
        if include_token:
            data["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
        # Empty credentials render form errors without authenticating or writing data.
        return client.post("/admin/login/", data, HTTP_HOST=host, HTTP_ORIGIN=origin)

    def test_local_origins_pass_admin_csrf_with_forwarded_port(self):
        for host in ("127.0.0.1:8080", "localhost:8080"):
            with self.subTest(host=host):
                self.assertEqual(self.admin_post(host, "http://" + host).status_code, 200)

    def test_dropped_port_reproduces_origin_failure(self):
        self.assertEqual(self.admin_post("127.0.0.1", "http://127.0.0.1:8080").status_code, 403)

    def test_untrusted_origin_is_rejected(self):
        self.assertEqual(self.admin_post("127.0.0.1:8080", "http://untrusted.example").status_code, 403)

    def test_missing_token_is_rejected(self):
        self.assertEqual(self.admin_post("localhost:8080", "http://localhost:8080", False).status_code, 403)

    def test_development_nginx_preserves_host_and_overwrites_scheme(self):
        config = (Path(settings.BASE_DIR) / "nginx/default.conf").read_text()
        self.assertIn("proxy_set_header Host $http_host;", config)
        self.assertNotIn("proxy_set_header Host $host;", config)
        self.assertIn("proxy_set_header X-Forwarded-Proto $scheme;", config)
