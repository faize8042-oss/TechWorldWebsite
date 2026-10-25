
from django.contrib import admin

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "project_type",
        "featured",
        "is_published",
        "created_at",
    )

    list_filter = (
        "category",
        "project_type",
        "featured",
        "is_published",
    )

    search_fields = (
        "title",
        "summary",
        "description",
        "category",
    )

    list_editable = ("featured", "is_published")

    readonly_fields = ("created_at", "updated_at")

    prepopulated_fields = {"slug": ("title",)}

    fieldsets = (
        (
            "Project Information",
            {
                "fields": (
                    "title",
                    "slug",
                    "summary",
                    "description",
                    "category",
                    "project_type",
                    "technologies",
                )
            },
        ),
        (
            "Project Links and Image",
            {
                "fields": (
                    "cover_image",
                    "github_url",
                    "live_url",
                )
            },
        ),
        (
            "Publishing",
            {
                "fields": (
                    "featured",
                    "is_published",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
