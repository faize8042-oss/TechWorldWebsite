import json
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import urlparse

from django.test import TestCase, override_settings
from django.urls import reverse

from projects.models import Project


class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.canonical = None
        self.title = False
        self.in_title = False
        self.title_text = ""
        self.json_ld = []
        self.in_json_ld = False
        self.script_text = ""

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta":
            key = values.get("name") or values.get("property")
            if key:
                self.meta[key] = values.get("content", "")
        elif tag == "link" and values.get("rel") == "canonical":
            self.canonical = values.get("href")
        elif tag == "title":
            self.in_title = True
        elif tag == "script" and values.get("type") == "application/ld+json":
            self.in_json_ld = True
            self.script_text = ""

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "script" and self.in_json_ld:
            self.json_ld.append(self.script_text)
            self.in_json_ld = False

    def handle_data(self, data):
        if self.in_title:
            self.title_text += data
        if self.in_json_ld:
            self.script_text += data


class SEOFoundationTests(TestCase):
    def parse_response(self, response):
        parser = MetaParser()
        parser.feed(response.content.decode(response.charset))
        return parser

    def create_project(self, title, published, **extra):
        return Project.objects.create(
            title=title,
            summary=extra.pop("summary", f"Summary for {title}"),
            description=f"Description for {title}",
            category="Web Development",
            is_published=published,
            **extra,
        )

    def test_public_page_titles_are_distinct_and_descriptions_present(self):
        names = [
            "home",
            "about",
            "services",
            "projects:list",
            "contact:contact",
            "privacy",
            "terms",
        ]
        titles = []
        for name in names:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                parsed = self.parse_response(response)
                self.assertTrue(parsed.title_text.strip())
                self.assertTrue(parsed.meta.get("description", "").strip())
                titles.append(parsed.title_text.strip())
        self.assertEqual(len(titles), len(set(titles)))

    def test_indexing_is_disabled_by_default_without_canonical_or_schema(self):
        response = self.client.get(reverse("home"))
        parsed = self.parse_response(response)
        self.assertEqual(parsed.meta["robots"], "noindex, nofollow")
        self.assertIsNone(parsed.canonical)
        self.assertFalse(parsed.json_ld)

    @override_settings(
        SEO_INDEXING_ENABLED=True,
        SEO_SITE_URL="https://example.org",
        ALLOWED_HOSTS=["testserver", "attacker.example"],
    )
    def test_configured_canonical_and_social_urls_are_consistent(self):
        response = self.client.get(reverse("about"), HTTP_HOST="attacker.example")
        parsed = self.parse_response(response)
        expected = "https://example.org/about/"
        self.assertEqual(parsed.canonical, expected)
        self.assertEqual(parsed.meta["og:url"], expected)
        self.assertEqual(parsed.meta["twitter:title"], parsed.meta["og:title"])
        self.assertEqual(
            parsed.meta["twitter:description"], parsed.meta["og:description"]
        )
        self.assertEqual(urlparse(parsed.canonical).scheme, "https")
        self.assertEqual(parsed.meta["robots"], "index, follow")

    def test_project_metadata_is_escaped_and_limited(self):
        project = self.create_project(
            "Markup Project",
            True,
            summary="<script>alert('x')</script> " + ("useful " * 32),
        )
        response = self.client.get(reverse("projects:detail", kwargs={"slug": project.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert('x')</script>")
        parsed = self.parse_response(response)
        self.assertLessEqual(len(parsed.meta["description"]), 160)
        self.assertEqual(parsed.meta["og:title"], parsed.title_text)

    @override_settings(SEO_INDEXING_ENABLED=True, SEO_SITE_URL="https://example.org")
    def test_sitemap_contains_public_pages_and_only_published_projects(self):
        published = self.create_project("Public Project", True)
        draft = self.create_project("Private Draft", False)
        response = self.client.get(reverse("sitemap"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/xml"))
        root = ET.fromstring(response.content)
        locs = [
            node.text
            for node in root.findall(
                "{http://www.sitemaps.org/schemas/sitemap/0.9}url/"
                "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
            )
        ]
        self.assertIn("https://example.org/", locs)
        self.assertIn(f"https://example.org{reverse('privacy')}", locs)
        self.assertIn(f"https://example.org{published.get_absolute_url()}", locs)
        self.assertNotIn(f"https://example.org{draft.get_absolute_url()}", locs)
        self.assertFalse(any("/admin/" in loc for loc in locs))
        self.assertFalse(any("/health/" in loc for loc in locs))
        expected_paths = [reverse(name) for name in (
            "home",
            "about",
            "services",
            "projects:list",
            "contact:contact",
            "privacy",
            "terms",
        )]
        expected_paths.append(published.get_absolute_url())
        self.assertCountEqual(
            locs,
            [f"https://example.org{path}" for path in expected_paths],
        )

    def test_sitemap_is_well_formed_and_empty_until_indexing_is_enabled(self):
        response = self.client.get(reverse("sitemap"))
        root = ET.fromstring(response.content)
        self.assertEqual(len(root), 0)

    @override_settings(SEO_INDEXING_ENABLED=True, SEO_SITE_URL="https://example.org")
    def test_empty_portfolio_sitemap_contains_static_public_pages(self):
        response = self.client.get(reverse("sitemap"))
        root = ET.fromstring(response.content)
        locs = [
            node.text
            for node in root.findall(
                "{http://www.sitemaps.org/schemas/sitemap/0.9}url/"
                "{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
            )
        ]
        self.assertEqual(len(locs), 7)
        self.assertIn("https://example.org/projects/", locs)

    def test_robots_txt_is_plain_text_and_only_advertises_configured_sitemap(self):
        response = self.client.get(reverse("robots"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        self.assertIn("Allow: /", response.content.decode())
        self.assertNotIn("Sitemap:", response.content.decode())

    @override_settings(SEO_INDEXING_ENABLED=True, SEO_SITE_URL="https://example.org")
    def test_robots_txt_includes_public_sitemap_when_enabled(self):
        response = self.client.get(reverse("robots"))
        self.assertIn("Sitemap: https://example.org/sitemap.xml", response.content.decode())

    @override_settings(SEO_INDEXING_ENABLED=True, SEO_SITE_URL="https://example.org")
    def test_structured_data_is_valid_json_and_uses_configured_origin(self):
        response = self.client.get(reverse("home"))
        parsed = self.parse_response(response)
        payload = json.loads(parsed.json_ld[0])
        self.assertEqual([item["@type"] for item in payload], ["Organization", "WebSite"])
        self.assertTrue(all(item["url"] == "https://example.org" for item in payload))
        self.assertEqual(payload[0]["slogan"], "Engineering Ideas Into Reality.")
