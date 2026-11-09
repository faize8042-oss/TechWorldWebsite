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
    VALID_PRODUCTION_SETTINGS = {
        "DEPLOYMENT_MODE": "production",
        "DEBUG": False,
        "SECRET_KEY": "test-only-secret-" + ("aB3!" * 15),
        "ALLOWED_HOSTS": ["site.example"],
        "CSRF_TRUSTED_ORIGINS": ["https://site.example"],
        "DATABASES": {
            "default": {"ENGINE": "django.db.backends.postgresql",
                        "USER": "cv_runtime", "PASSWORD": "synthetic-only",
                        "HOST": "db", "NAME": "codeventra",
                        "OPTIONS": {"options": "-c search_path=public"}}
        },
        "POSTGRES_INITIALIZATION_USER": "cv_init",
        "PRODUCTION_CREDENTIAL_CONTRACT": "runtime-secret-v1",
        "EMAIL_HOST": "smtp.example",
        "EMAIL_HOST_USER": "mailer",
        "EMAIL_HOST_PASSWORD": "placeholder-only",
        "ENABLE_HTTPS": True,
        "PRODUCTION_PROXY_TRANSPORT": "unix",
        "SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https"),
    }

    def production_errors(self, **overrides):
        values = {**self.VALID_PRODUCTION_SETTINGS, **overrides}
        with self.settings(**values):
            from .checks import check_production_configuration

            return check_production_configuration(None)

    def assert_setting_error(self, errors, setting):
        self.assertTrue(
            any(setting in error.hint for error in errors),
            f"Expected a production configuration error for {setting}.",
        )

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

    def test_validated_production_configuration_passes(self):
        self.assertEqual(self.production_errors(), [])

    def test_production_check_is_inactive_outside_production_mode(self):
        errors = self.production_errors(
            DEPLOYMENT_MODE="development",
            DEBUG=True,
            SECRET_KEY="short",
            ALLOWED_HOSTS=["*"],
            ENABLE_HTTPS=False,
        )

        self.assertEqual(errors, [])

    def test_short_and_insecure_prefix_secret_keys_are_rejected(self):
        for secret_key in ("short", "django-insecure-" + ("x" * 60)):
            with self.subTest(secret_key_length=len(secret_key)):
                errors = self.production_errors(SECRET_KEY=secret_key)
                self.assert_setting_error(errors, "SECRET_KEY")

    def test_debug_true_is_rejected(self):
        errors = self.production_errors(DEBUG=True)
        self.assert_setting_error(errors, "DEBUG")

    def test_empty_wildcard_and_local_allowed_hosts_are_rejected(self):
        invalid_hosts = ([], ["*"], ["localhost"], ["127.0.0.1"], ["::1"])
        for hosts in invalid_hosts:
            with self.subTest(hosts=hosts):
                errors = self.production_errors(ALLOWED_HOSTS=hosts)
                self.assert_setting_error(errors, "ALLOWED_HOSTS")

    def test_non_https_and_malformed_csrf_origins_are_rejected(self):
        invalid_origins = (
            "http://site.example",
            "https://",
            "https://user@site.example",
            "https://user:password@site.example",
            "https://site.example/path",
            "https://site.example?query=1",
            "https://site.example#fragment",
        )
        for origin in invalid_origins:
            with self.subTest(origin=origin):
                errors = self.production_errors(
                    CSRF_TRUSTED_ORIGINS=[origin]
                )
                self.assert_setting_error(errors, "CSRF_TRUSTED_ORIGINS")

    def test_csrf_origin_host_must_be_allowed(self):
        errors = self.production_errors(
            CSRF_TRUSTED_ORIGINS=["https://other.example"]
        )
        self.assert_setting_error(errors, "CSRF_TRUSTED_ORIGINS")

    def test_non_postgresql_database_is_rejected(self):
        errors = self.production_errors(
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3"}}
        )
        self.assert_setting_error(errors, "DATABASE_URL")

    def test_each_required_smtp_credential_is_checked(self):
        for setting in ("EMAIL_HOST", "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"):
            with self.subTest(setting=setting):
                errors = self.production_errors(**{setting: ""})
                self.assert_setting_error(errors, setting)

    def test_production_errors_name_settings_without_exposing_values(self):
        secret_key_marker = "synthetic-secret-marker"
        smtp_password_marker = "synthetic-smtp-password-marker"
        errors = self.production_errors(
            SECRET_KEY=secret_key_marker,
            EMAIL_HOST="",
            EMAIL_HOST_PASSWORD=smtp_password_marker,
        )

        rendered_errors = "\n".join(str(error) for error in errors)
        self.assert_setting_error(errors, "SECRET_KEY")
        self.assert_setting_error(errors, "EMAIL_HOST")
        self.assertNotIn(secret_key_marker, rendered_errors)
        self.assertNotIn(smtp_password_marker, rendered_errors)

    def test_https_must_be_explicitly_enabled_in_production(self):
        errors = self.production_errors(ENABLE_HTTPS=False)
        self.assert_setting_error(errors, "ENABLE_HTTPS")


@override_settings(DEPLOYMENT_MODE="production", PRODUCTION_PROXY_TRANSPORT="unix",
                   SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"))
class PrivateSocketProxyTests(SimpleTestCase):
    def test_unmarked_requests_fail_closed_even_with_empty_or_trusted_peer(self):
        for peer in ("", "172.20.0.10", "198.51.100.10"):
            request = RequestFactory().get("/", REMOTE_ADDR=peer,
                HTTP_X_FORWARDED_PROTO="https", HTTP_X_REAL_IP="203.0.113.1",
                HTTP_CODEVENTRA_PRIVATE_SOCKET="True")
            response = TrustedProxyIPMiddleware(lambda r: HttpResponse("unexpected"))(request)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(request.META["REMOTE_ADDR"], peer)

    def test_marked_socket_validates_ip_and_recognizes_scheme(self):
        for address, expected in (("203.0.113.25", "203.0.113.25"),
                                  ("2001:db8::1", "2001:db8::1"),
                                  ("invalid", ""), ("1.2.3.4, 5.6.7.8", "")):
            request = RequestFactory().get("/", REMOTE_ADDR="",
                HTTP_X_REAL_IP=address, HTTP_X_FORWARDED_PROTO="https")
            request.META["codeventra.private_socket"] = True
            response = TrustedProxyIPMiddleware(lambda r: HttpResponse(str(r.is_secure())))(request)
            self.assertEqual(response.content, b"True")
            self.assertEqual(request.META["REMOTE_ADDR"], expected)

    def test_http_scheme_remains_insecure(self):
        request = RequestFactory().get("/", HTTP_X_FORWARDED_PROTO="http")
        request.META["codeventra.private_socket"] = True
        TrustedProxyIPMiddleware(lambda r: HttpResponse())(request)
        self.assertFalse(request.is_secure())


class SocketConfigurationChecksTests(DeploymentConfigurationTests):
    def test_transport_and_header_are_required(self):
        for values in ({"PRODUCTION_PROXY_TRANSPORT": ""}, {"SECURE_PROXY_SSL_HEADER": None}):
            self.assert_setting_error(self.production_errors(**values), "PRODUCTION_PROXY_TRANSPORT")

    def test_hsts_and_indexing_remain_disabled(self):
        self.assert_setting_error(self.production_errors(SECURE_HSTS_SECONDS=60), "HSTS_SECONDS")
        self.assert_setting_error(self.production_errors(SEO_INDEXING_ENABLED=True), "SEO_INDEXING_ENABLED")


class GunicornHookContractTests(SimpleTestCase):
    """Exercise our hook with fakes; this is not Linux Gunicorn validation."""
    def test_hook_rejects_tcp_and_marks_only_validated_socket(self):
        import runpy
        import socket
        import stat
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch
        unix_family = getattr(socket, "AF_UNIX", 999)
        self.enterContext(patch.object(socket, "AF_UNIX", unix_family, create=True))
        config = runpy.run_path(str(Path(settings.BASE_DIR) / "deploy/gunicorn.production.py"))
        self.assertEqual(config["secure_scheme_headers"], {})
        worker = SimpleNamespace(sockets=[SimpleNamespace(family=socket.AF_INET)],
            cfg=SimpleNamespace(secure_scheme_headers={}),
            wsgi=lambda environ, start: environ.copy())
        directory = SimpleNamespace(st_uid=10001, st_gid=10002, st_mode=stat.S_IFDIR | 0o2750)
        node = SimpleNamespace(st_uid=10001, st_gid=10002, st_mode=stat.S_IFSOCK | 0o660)
        with self.settings(DEPLOYMENT_MODE="production", PRODUCTION_PROXY_TRANSPORT="unix"), \
             patch("django.core.checks.run_checks", return_value=[]), \
             patch("os.stat", return_value=directory):
            with self.assertRaisesRegex(RuntimeError, "listener"):
                config["post_worker_init"](worker)
        worker.sockets = [SimpleNamespace(family=socket.AF_UNIX,
            getsockname=lambda: "/run/codeventra/gunicorn.sock")]
        with self.settings(DEPLOYMENT_MODE="production", PRODUCTION_PROXY_TRANSPORT="unix"), \
             patch("django.core.checks.run_checks", return_value=[]), \
             patch("os.stat", side_effect=[directory, node]):
            config["post_worker_init"](worker)
        self.assertIs(worker.wsgi({}, None)["codeventra.private_socket"], True)
