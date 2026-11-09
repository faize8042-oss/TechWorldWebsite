"""Explicit, opt-in retention cleanup; never run automatically on startup."""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from contact.models import ContactSubmission


class Command(BaseCommand):
    help = 'Preview unanswered enquiries inactive for 90 days; --apply deletes eligible records and private attachments.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Apply deletion. Default is a read-only count.')

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=90)
        eligible = ContactSubmission.objects.filter(
            status=ContactSubmission.Status.NEW, created_at__lt=cutoff, updated_at__lt=cutoff)
        if not options['apply']:
            self.stdout.write(f'DRY RUN: {eligible.count()} unanswered enquiries eligible; nothing deleted.')
            return
        deleted = 0
        # Lock and recheck each record so a concurrent admin status edit is respected.
        for pk in eligible.values_list('pk', flat=True).iterator():
            with transaction.atomic():
                record = eligible.select_for_update().filter(pk=pk).first()
                if record is None:
                    continue
                name = record.attachment.name
                storage = record.attachment.storage
                record.delete()
                if name:
                    def remove_file(name=name, storage=storage):
                        if ContactSubmission.objects.filter(attachment=name).exists():
                            return
                        try:
                            storage.delete(name)
                        except Exception:
                            raise CommandError('A private attachment could not be removed after record deletion; review private storage before retrying.') from None
                    transaction.on_commit(remove_file)
                deleted += 1
        self.stdout.write(f'Cleanup complete: {deleted} unanswered enquiries removed.')
