
from django.test import TestCase
from django.urls import reverse


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
