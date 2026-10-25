
from io import BytesIO
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from .forms import ContactSubmissionForm
from .models import ContactSubmission

from django.test import override_settings

class ContactFormTests(TestCase):
    def setUp(self):
        self.url = reverse("contact:contact")

        self.valid_data = {
            "name": "Test Visitor",
            "email": "visitor@example.com",
            "project_type": "website",
            "budget_range": "undecided",
            "message": "I would like information about a website project.",
        }

    def test_contact_page_loads(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Project enquiry")
        self.assertContains(response, 'name="name"')
        self.assertContains(response, 'name="email"')
        self.assertContains(response, 'name="message"')

    @patch("contact.views.send_mail", return_value=1)
    def test_valid_submission_is_saved_and_email_sent(self, mock_send_mail):
        response = self.client.post(self.url, self.valid_data)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactSubmission.objects.count(), 1)

        submission = ContactSubmission.objects.get()
        self.assertEqual(submission.name, "Test Visitor")
        self.assertEqual(submission.email, "visitor@example.com")

        mock_send_mail.assert_called_once()

    @patch(
        "contact.views.send_mail",
        side_effect=Exception("SMTP unavailable"),
    )
    def test_submission_is_saved_if_email_fails(self, mock_send_mail):
        response = self.client.post(
            self.url,
            self.valid_data,
            follow=True,
        )

        self.assertEqual(ContactSubmission.objects.count(), 1)
        self.assertEqual(response.status_code, 200)

        mock_send_mail.assert_called_once()

        messages = list(response.context["messages"])
        self.assertTrue(
            any("saved" in message.message.lower() for message in messages)
        )

    def test_invalid_submission_is_not_saved(self):
        invalid_data = self.valid_data.copy()
        invalid_data["email"] = "not-an-email"

        response = self.client.post(self.url, invalid_data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactSubmission.objects.count(), 0)
        self.assertContains(response, "not-an-email", html=False)

    def test_valid_pdf_attachment_is_accepted(self):
        pdf_file = SimpleUploadedFile(
            "project-brief.pdf",
            b"%PDF-1.7\nExample PDF content",
            content_type="application/pdf",
        )

        form = ContactSubmissionForm(
            data=self.valid_data,
            files={"attachment": pdf_file},
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_content_disguised_as_pdf_is_rejected(self):
        fake_pdf = SimpleUploadedFile(
            "project-brief.pdf",
            b"This is not a PDF file",
            content_type="application/pdf",
        )

        form = ContactSubmissionForm(
            data=self.valid_data,
            files={"attachment": fake_pdf},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("attachment", form.errors)

    def test_valid_png_attachment_is_accepted(self):
        image_bytes = BytesIO()

        image = Image.new("RGB", (10, 10), color="white")
        image.save(image_bytes, format="PNG")
        image_bytes.seek(0)

        png_file = SimpleUploadedFile(
            "project-image.png",
            image_bytes.getvalue(),
            content_type="image/png",
        )

        form = ContactSubmissionForm(
            data=self.valid_data,
            files={"attachment": png_file},
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_corrupted_png_attachment_is_rejected(self):
        corrupted_image = SimpleUploadedFile(
            "project-image.png",
            b"This is not a real PNG image",
            content_type="image/png",
        )

        form = ContactSubmissionForm(
            data=self.valid_data,
            files={"attachment": corrupted_image},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("attachment", form.errors)

    def test_attachment_over_5_mb_is_rejected(self):
        oversized_file = SimpleUploadedFile(
            "large-brief.pdf",
            b"%PDF-" + (b"A" * (5 * 1024 * 1024)),
            content_type="application/pdf",
        )

        form = ContactSubmissionForm(
            data=self.valid_data,
            files={"attachment": oversized_file},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("attachment", form.errors)

from django.core.cache import cache


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "contact-rate-limit-tests",
        }
    }
)
class ContactRateLimitTests(TestCase):

    def setUp(self):
        cache.clear()

        self.url = reverse("contact:contact")

        self.valid_data = {
            "name": "Rate Limit Tester",
            "email": "ratelimit@example.com",
            "project_type": "website",
            "budget_range": "undecided",
            "message": "Testing contact form rate limiting.",
        }

    @patch("contact.views.send_mail", return_value=1)
    def test_sixth_submission_is_blocked(self, mock_send_mail):

        for _ in range(5):
            response = self.client.post(
                self.url,
                self.valid_data,
                REMOTE_ADDR="192.0.2.10",
            )
            self.assertEqual(response.status_code, 302)

        self.assertEqual(ContactSubmission.objects.count(), 5)

        response = self.client.post(
            self.url,
            self.valid_data,
            REMOTE_ADDR="192.0.2.10",
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "too many enquiries",
        )

        self.assertEqual(
            ContactSubmission.objects.count(),
            5,
        )

        self.assertEqual(mock_send_mail.call_count, 5)

    @patch("contact.views.send_mail", return_value=1)
    def test_different_ip_has_independent_limit(self, mock_send_mail):

        for _ in range(5):
            self.client.post(
                self.url,
                self.valid_data,
                REMOTE_ADDR="192.0.2.20",
            )

        response = self.client.post(
            self.url,
            self.valid_data,
            REMOTE_ADDR="192.0.2.21",
        )

        self.assertEqual(response.status_code, 302)

        self.assertEqual(
            ContactSubmission.objects.count(),
            6,
        )

        self.assertEqual(mock_send_mail.call_count, 6)