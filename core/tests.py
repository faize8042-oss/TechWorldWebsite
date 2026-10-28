
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from projects.models import Project


class PublicPageTests(TestCase):
    def test_public_pages_load(self):
        page_names = [
            "home",
            "services",
            "about",
            "privacy",
            "terms",
        ]

        for page_name in page_names:
            with self.subTest(page=page_name):
                response = self.client.get(reverse(page_name))
                self.assertEqual(response.status_code, 200)

    def test_contact_page_loads(self):
        response = self.client.get(reverse("contact:contact"))
        self.assertEqual(response.status_code, 200)

    def test_projects_page_loads(self):
        response = self.client.get(reverse("projects:list"))
        self.assertEqual(response.status_code, 200)

    def test_missing_page_returns_404(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)

    def test_health_endpoint_is_minimal_and_available_over_local_http(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response.content, b"ok\n")
        for sensitive in ("SECRET_KEY", "DATABASE_URL", "password", "postgres"):
            self.assertNotIn(sensitive.encode().lower(), response.content.lower())

    def test_shared_accessibility_navigation_markup_is_rendered(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'class="skip-link" href="#main-content"')
        self.assertContains(response, 'aria-label="Main navigation"')
        self.assertContains(response, 'aria-controls="primary-navigation"')
        self.assertContains(response, 'aria-expanded="false"')
        self.assertContains(response, 'class="theme-toggle"')

    def test_contact_form_has_labels_and_file_upload(self):
        response = self.client.get(reverse("contact:contact"))
        self.assertContains(response, 'for="id_name"')
        self.assertContains(response, 'for="id_email"')
        self.assertContains(response, 'enctype="multipart/form-data"')

    def test_project_detail_cover_image_is_lazy_loaded(self):
        project = Project.objects.create(
            title="Image loading check",
            summary="A test project summary",
            description="A test project description",
            category="Web Development",
            is_published=True,
            cover_image="projects/test-cover.webp",
        )
        response = self.client.get(project.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'alt="Cover image for Image loading check" loading="lazy"',
        )

    @override_settings(DEBUG=False)
    def test_custom_404_is_branded_noindex_and_has_no_canonical(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)
        self.assertContains(response, 'content="noindex, nofollow"', status_code=404)
        self.assertNotContains(response, 'rel="canonical"', status_code=404)
        self.assertNotContains(response, "Traceback", status_code=404)

    def test_custom_500_template_renders_without_exception_details(self):
        from django.views.defaults import server_error

        request = RequestFactory().get("/failure/")
        response = server_error(request)
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "Something went wrong", status_code=500)
        self.assertContains(response, 'content="noindex, nofollow"', status_code=500)
        self.assertNotContains(response, 'rel="canonical"', status_code=500)
        self.assertNotContains(response, "Traceback", status_code=500)
