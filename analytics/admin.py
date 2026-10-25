
from django.contrib import admin

from .models import AnalyticsVisit


@admin.register(AnalyticsVisit)
class AnalyticsVisitAdmin(admin.ModelAdmin):
    list_display = ("page_path", "visitor_hash", "visited_at")
    list_filter = ("visited_at",)
    search_fields = ("page_path", "visitor_hash")
    readonly_fields = ("page_path", "visitor_hash", "visited_at")
    date_hierarchy = "visited_at"
