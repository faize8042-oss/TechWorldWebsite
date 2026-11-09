from django.test import TestCase
from django.urls import reverse

from .demos import DEMOS


class DemonstrationTests(TestCase):
    def test_portfolio_links_all_demonstrations_without_database_seeds(self):
        response = self.client.get(reverse('projects:list'))
        self.assertContains(response, 'not client engagements')
        for slug in DEMOS:
            self.assertContains(response, reverse('projects:demo', kwargs={'slug': slug}))

    def test_demo_pages_explain_limits_and_escape_input_through_client_dom(self):
        for slug, demo in DEMOS.items():
            with self.subTest(slug=slug):
                response = self.client.get(reverse('projects:demo', kwargs={'slug': slug}))
                self.assertContains(response, demo['title'])
                self.assertContains(response, 'Sample data only.')
                self.assertContains(response, demo['limit'])
                self.assertContains(response, 'id="demo-form"')

    def test_unknown_demo_returns_not_found(self):
        self.assertEqual(self.client.get('/projects/demos/unknown/').status_code, 404)
