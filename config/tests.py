from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.conf import settings

from .middleware import TrustedProxyIPMiddleware


@override_settings(TRUSTED_PROXY_IPS=["172.20.0.10"])
class TrustedProxyIPMiddlewareTests(SimpleTestCase):

    def setUp(self):
        self.factory = RequestFactory()

        self.middleware = TrustedProxyIPMiddleware(
            lambda request: HttpResponse("OK")
        )

    def test_trusted_proxy_accepts_valid_ip(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="172.20.0.10",
            HTTP_X_REAL_IP="203.0.113.25",
        )

        self.middleware(request)

        self.assertEqual(
            request.META["REMOTE_ADDR"],
            "203.0.113.25",
        )

    def test_untrusted_proxy_cannot_spoof_ip(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="198.51.100.10",
            HTTP_X_REAL_IP="203.0.113.25",
        )

        self.middleware(request)

        self.assertEqual(
            request.META["REMOTE_ADDR"],
            "198.51.100.10",
        )

    def test_invalid_forwarded_ip_is_rejected(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="172.20.0.10",
            HTTP_X_REAL_IP="invalid-ip-address",
        )

        self.middleware(request)

        self.assertEqual(request.META["REMOTE_ADDR"], "172.20.0.10")

    def test_missing_forwarded_ip_is_handled(self):
        request = self.factory.get("/", REMOTE_ADDR="172.20.0.10")
        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(request.META["REMOTE_ADDR"], "172.20.0.10")

    def test_untrusted_proxy_with_multiple_headers(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="198.51.100.10",
            HTTP_X_REAL_IP="203.0.113.25",
            HTTP_X_FORWARDED_FOR="192.0.2.1",
        )

        self.middleware(request)

        self.assertEqual(request.META["REMOTE_ADDR"], "198.51.100.10")


class DeploymentConfigurationTests(SimpleTestCase):
    def test_local_http_security_defaults_remain_disabled(self):
        self.assertEqual(settings.DEPLOYMENT_MODE, "development")
        self.assertFalse(settings.SECURE_SSL_REDIRECT)
        self.assertFalse(settings.SESSION_COOKIE_SECURE)
        self.assertFalse(settings.CSRF_COOKIE_SECURE)
        self.assertEqual(settings.SECURE_HSTS_SECONDS, 0)
        self.assertFalse(settings.SECURE_HSTS_INCLUDE_SUBDOMAINS)
        self.assertFalse(settings.SECURE_HSTS_PRELOAD)
        self.assertIsNone(settings.SECURE_PROXY_SSL_HEADER)

    @override_settings(
        DEPLOYMENT_MODE="production",
        DEBUG=False,
        SECRET_KEY="short",
        ALLOWED_HOSTS=["localhost"],
        CSRF_TRUSTED_ORIGINS=["http://localhost"],
        DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}},
        EMAIL_HOST="",
        EMAIL_HOST_USER="",
        EMAIL_HOST_PASSWORD="",
        ENABLE_HTTPS=False,
    )
    def test_invalid_production_configuration_reports_actionable_errors(self):
        from .checks import check_production_configuration

        errors = check_production_configuration(None)
        self.assertGreaterEqual(len(errors), 5)
        self.assertTrue(all(error.hint for error in errors))

    @override_settings(
        DEPLOYMENT_MODE="production",
        DEBUG=False,
        SECRET_KEY="x" * 60,
        ALLOWED_HOSTS=["site.example"],
        CSRF_TRUSTED_ORIGINS=["https://site.example"],
        DATABASES={"default": {"ENGINE": "django.db.backends.postgresql"}},
        EMAIL_HOST="smtp.example",
        EMAIL_HOST_USER="mailer",
        EMAIL_HOST_PASSWORD="placeholder-secret",
        ENABLE_HTTPS=True,
    )
    def test_validated_production_configuration_passes(self):
        from .checks import check_production_configuration

        self.assertEqual(check_production_configuration(None), [])
