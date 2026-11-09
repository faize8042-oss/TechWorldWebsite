from django.contrib import admin
from django import forms
from django.utils import timezone

class EditorialForm(forms.ModelForm):
    class Meta:
        widgets = {'cover_image': forms.FileInput()}

class EditorialAdmin(admin.ModelAdmin):
    form = EditorialForm
    list_display = ('title', 'status', 'published_at', 'publication_state', 'updated_at')
    list_filter = ('status',)
    search_fields = ('title', 'summary', 'body')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at', 'publication_state')
    date_hierarchy = 'published_at'
    @admin.display(description='Public visibility')
    def publication_state(self, obj):
        if obj.status != 'published':
            return 'Draft'
        if obj.published_at and obj.published_at > timezone.now():
            return 'Scheduled'
        return 'Public' if obj.published_at else 'Publication date required'
