
import os

from django.contrib import admin, messages
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from .models import ContactSubmission


@admin.register(ContactSubmission)
class ContactSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "email",
        "project_type",
        "budget_range",
        "status",
        "has_attachment",
        "created_at",
    )

    list_filter = (
        "status",
        "project_type",
        "budget_range",
        "created_at",
    )

    search_fields = ("name", "email", "message")
    list_editable = ("status",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "attachment_status",
    )
    date_hierarchy = "created_at"

    fields = (
        "name",
        "email",
        "project_type",
        "budget_range",
        "message",
        "attachment_status",
        "status",
        "created_at",
        "updated_at",
    )

    def get_urls(self):
        custom_urls = [
            path(
                "<path:object_id>/download-attachment/",
                self.admin_site.admin_view(
                    self.download_attachment_view
                ),
                name="contact_contactsubmission_download_attachment",
            ),
        ]
        return custom_urls + super().get_urls()

    @admin.display(description="Attachment")
    def has_attachment(self, obj):
        return bool(obj.attachment)

    @admin.display(description="Attachment")
    def attachment_status(self, obj):
        if not obj or not obj.attachment:
            return "No attachment"

        url = reverse(
            "admin:contact_contactsubmission_download_attachment",
            args=[obj.pk],
        )

        return format_html(
            '<a href="{}">Download private attachment</a>',
            url,
        )

    def download_attachment_view(self, request, object_id):
        submission = get_object_or_404(
            ContactSubmission,
            pk=object_id,
        )

        if not self.has_view_or_change_permission(request, submission):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied

        if not submission.attachment:
            self.message_user(
                request,
                "This submission has no attachment.",
                level=messages.WARNING,
            )
            from django.shortcuts import redirect
            return redirect(
                "admin:contact_contactsubmission_change",
                object_id=submission.pk,
            )

        try:
            file_handle = submission.attachment.storage.open(
                submission.attachment.name,
                "rb",
            )
        except (OSError, ValueError):
            self.message_user(
                request,
                "The attachment could not be opened. "
                "Check that the private file exists.",
                level=messages.ERROR,
            )
            from django.shortcuts import redirect
            return redirect(
                "admin:contact_contactsubmission_change",
                object_id=submission.pk,
            )

        filename = os.path.basename(submission.attachment.name)

        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=filename,
            content_type="application/octet-stream",
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"

        return response
