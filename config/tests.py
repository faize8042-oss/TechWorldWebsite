from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

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

        self.assertEqual(
            request.META["REMOTE_ADDR"],
            "172.20.0.10",
        )

    def test_missing_forwarded_ip_is_handled(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="172.20.0.10",
        )

        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            request.META["REMOTE_ADDR"],
            "172.20.0.10",
        )

    def test_untrusted_proxy_with_multiple_headers(self):
        request = self.factory.get(
            "/",
            REMOTE_ADDR="198.51.100.10",
            HTTP_X_REAL_IP="203.0.113.25",
            HTTP_X_FORWARDED_FOR="192.0.2.1",
        )

        self.middleware(request)

        self.assertEqual(
            request.META["REMOTE_ADDR"],
            "198.51.100.10",
        )