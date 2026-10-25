
from django.db import models


class AnalyticsVisit(models.Model):
    page_path = models.CharField(max_length=255)
    visitor_hash = models.CharField(max_length=64)
    visited_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-visited_at"]
        indexes = [
            models.Index(fields=["visited_at"]),
            models.Index(fields=["page_path", "visited_at"]),
        ]

    def __str__(self):
        return f"{self.page_path} — {self.visited_at}"
