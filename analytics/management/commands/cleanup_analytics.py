
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from analytics.models import AnalyticsVisit


class Command(BaseCommand):
    help = "Delete analytics visits older than the configured retention period."

    def handle(self, *args, **options):
        retention_days = settings.ANALYTICS_RETENTION_DAYS

        if retention_days < 1:
            self.stderr.write(
                self.style.ERROR(
                    "ANALYTICS_RETENTION_DAYS must be at least 1."
                )
            )
            return

        cutoff = timezone.now() - timedelta(days=retention_days)

        deleted_count, _ = AnalyticsVisit.objects.filter(
            visited_at__lt=cutoff
        ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Analytics cleanup complete. Deleted {deleted_count} records."
            )
        )
