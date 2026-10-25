
import hashlib
import hmac
import logging

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class PrivacyAwareAnalyticsMiddleware:
    """
    Record limited public-page visit information.

    Raw IP addresses are never written to the analytics database.
    Analytics failures must not interrupt normal website requests.
    """

    EXCLUDED_PREFIXES = (
        "/admin/",
        "/static/",
        "/media/",
        "/contact/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (
            request.method != "GET"
            or response.status_code >= 400
            or response.status_code >= 300
            or response.status_code < 200
        ):
            return response

        path = request.path

        if path == "/robots.txt" or path == "/sitemap.xml":
            return response

        if any(path.startswith(prefix) for prefix in self.EXCLUDED_PREFIXES):
            return response

        # Avoid recording visits to non-HTML responses.
        content_type = response.get("Content-Type", "")
        if "text/html" not in content_type.lower():
            return response

        secret = getattr(settings, "ANALYTICS_HMAC_SECRET", "")

        if not secret:
            return response

        # Use the direct connection address only.
        # Do not trust arbitrary X-Forwarded-For request headers.
        ip_address = request.META.get("REMOTE_ADDR", "")

        if not ip_address:
            return response

        try:
            daily_key = (
                f"{secret}:{timezone.localdate().isoformat()}"
            ).encode("utf-8")

            visitor_hash = hmac.new(
                daily_key,
                ip_address.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            # Import and write only after the page response is generated.
            from .models import AnalyticsVisit

            AnalyticsVisit.objects.create(
                page_path=path[:255],
                visitor_hash=visitor_hash,
            )

        except Exception:
            # Analytics must never take down the website.
            logger.exception("Unable to record an analytics visit.")

        return response
