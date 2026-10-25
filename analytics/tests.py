
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import AnalyticsVisit


@override_settings(ANALYTICS_HMAC_SECRET="test-only-analytics-secret")
class AnalyticsMiddlewareTests(TestCase):
    def test_public_html_page_records_visit(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AnalyticsVisit.objects.filter(page_path="/").exists()
        )

    def test_contact_page_is_excluded(self):
        self.client.get(reverse("contact:contact"))

        self.assertFalse(
            AnalyticsVisit.objects.filter(
                page_path="/contact/"
            ).exists()
        )

    def test_query_parameters_are_not_stored(self):
        self.client.get("/?campaign=test")

        visit = AnalyticsVisit.objects.get(page_path="/")
        self.assertNotIn("campaign", visit.page_path)

    def test_analytics_records_do_not_store_raw_ip_field(self):
        field_names = {
            field.name for field in AnalyticsVisit._meta.get_fields()
        }

        self.assertNotIn("ip_address", field_names)
        self.assertIn("visitor_hash", field_names)
