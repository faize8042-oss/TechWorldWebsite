import json

from django.conf import settings
from django.utils.safestring import mark_safe


def seo_context(request):
    """Build SEO URLs only from the explicitly configured public origin."""
    enabled = settings.SEO_INDEXING_ENABLED and bool(settings.SEO_SITE_URL)
    canonical_url = ""
    structured_data = ""

    if enabled:
        canonical_url = f"{settings.SEO_SITE_URL}{request.path}"
        payload = [
            {
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": "Codeventra Labs",
                "slogan": "Engineering Ideas Into Reality.",
                "url": settings.SEO_SITE_URL,
            },
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": "Codeventra Labs",
                "url": settings.SEO_SITE_URL,
            },
        ]
        serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        # Prevent a string value from ending the script element in HTML.
        serialized = (
            serialized.replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )
        structured_data = mark_safe(serialized)

    return {
        "seo_indexing_enabled": enabled,
        "seo_canonical_url": canonical_url,
        "seo_structured_data": structured_data,
    }
