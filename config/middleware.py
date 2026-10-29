import ipaddress

from django.conf import settings
from django.http import HttpResponseBadRequest


class TrustedProxyIPMiddleware:
    """
    Use a forwarded visitor IP only when the immediate
    connection originates from a trusted reverse proxy.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        production = settings.DEPLOYMENT_MODE == "production"
        socket_trusted = request.META.get("codeventra.private_socket") is True
        if production and not socket_trusted:
            # Fail closed before SecurityMiddleware can consume protocol headers.
            return HttpResponseBadRequest("Untrusted application transport")
        peer_ip = request.META.get("REMOTE_ADDR", "")
        forwarded_ip = request.META.get("HTTP_X_REAL_IP", "")

        trusted_proxies = getattr(
            settings,
            "TRUSTED_PROXY_IPS",
            [],
        )

        if ((production and socket_trusted) or (not production and peer_ip in trusted_proxies)) and forwarded_ip:
            try:
                # Reject forwarded IP chains.
                if "," not in forwarded_ip:
                    parsed_ip = ipaddress.ip_address(
                        forwarded_ip.strip()
                    )
                    request.META["REMOTE_ADDR"] = str(parsed_ip)

            except ValueError:
                pass

        return self.get_response(request)