import io
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .models import ContactSubmission


class RetentionTests(TestCase):
    def create_record(self, age=91, status='new', updated_age=None):
        record = ContactSubmission.objects.create(name='Synthetic', email='test@example.invalid',
            project_type='website', message='Synthetic test only', status=status)
        ContactSubmission.objects.filter(pk=record.pk).update(
            created_at=timezone.now()-timedelta(days=age),
            updated_at=timezone.now()-timedelta(days=age if updated_age is None else updated_age))
        return record

    def test_default_is_read_only(self):
        record = self.create_record()
        output = io.StringIO()
        call_command('cleanup_unanswered_enquiries', stdout=output)
        self.assertIn('1 unanswered enquiries eligible', output.getvalue())
        self.assertTrue(ContactSubmission.objects.filter(pk=record.pk).exists())

    def test_apply_keeps_recent_active_completed_and_recently_updated(self):
        expired = self.create_record()
        kept = [self.create_record(age=89), self.create_record(status='in_progress'),
                self.create_record(status='completed'), self.create_record(updated_age=1)]
        call_command('cleanup_unanswered_enquiries', apply=True, stdout=io.StringIO())
        self.assertFalse(ContactSubmission.objects.filter(pk=expired.pk).exists())
        self.assertEqual(ContactSubmission.objects.filter(pk__in=[r.pk for r in kept]).count(), 4)

    def test_attachment_removed_only_after_committed_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = FileSystemStorage(location=directory)
            name = storage.save('synthetic.txt', ContentFile(b'synthetic'))
            record = self.create_record()
            ContactSubmission.objects.filter(pk=record.pk).update(attachment=name)
            field = ContactSubmission._meta.get_field('attachment')
            with patch.object(field, 'storage', storage):
                with self.captureOnCommitCallbacks(execute=True):
                    call_command('cleanup_unanswered_enquiries', apply=True, stdout=io.StringIO())
            self.assertFalse(storage.exists(name))
