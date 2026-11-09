from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.utils.xmlutils import SimplerXMLGenerator


STATIC_SITEMAP_NAMES = (
    "home",
    "about",
    "services",
    "projects:list",
    "blog:list",
    "news:list",
    "contact:contact",
    "privacy",
    "terms",
)


def sitemap(request):
    """Return a public URL set only after explicit indexing configuration."""
    response = HttpResponse(content_type="application/xml; charset=utf-8")
    xml = SimplerXMLGenerator(response, "utf-8")
    xml.startDocument()
    xml.startElement(
        "urlset",
        {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"},
    )

    if settings.SEO_INDEXING_ENABLED and settings.SEO_SITE_URL:
        paths = [reverse(name) for name in STATIC_SITEMAP_NAMES]
        modified = {}
        from projects.demos import DEMOS
        paths.extend(reverse('projects:demo', kwargs={'slug': slug}) for slug in DEMOS)
        from projects.models import Project

        project_paths = Project.objects.filter(is_published=True).values_list(
            "slug", "updated_at"
        )
        for slug, updated in project_paths:
            path = reverse("projects:detail", kwargs={"slug": slug})
            paths.append(path)
            modified[path] = updated

        from blog.models import BlogPost
        from news.models import NewsItem
        for model in (BlogPost, NewsItem):
            for item in model.objects.public().only('slug', 'updated_at'):
                path = item.get_absolute_url()
                paths.append(path)
                modified[path] = item.updated_at

        for path in paths:
            xml.startElement("url", {})
            xml.startElement("loc", {})
            xml.characters(f"{settings.SEO_SITE_URL}{path}")
            xml.endElement("loc")
            if path in modified:
                xml.startElement('lastmod', {})
                xml.characters(modified[path].isoformat())
                xml.endElement('lastmod')
            xml.endElement("url")

    xml.endElement("urlset")
    xml.endDocument()
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response


def robots(request):
    """Serve crawl guidance; access control remains enforced by the app."""
    lines = ["User-agent: *", "Allow: /", "Disallow: /admin/"]
    if settings.SEO_INDEXING_ENABLED and settings.SEO_SITE_URL:
        lines.append(f"Sitemap: {settings.SEO_SITE_URL}/sitemap.xml")
    return HttpResponse(
        "\n".join(lines) + "\n",
        content_type="text/plain; charset=utf-8",
    )
