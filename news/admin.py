from django.contrib import admin
from publishing.admin import EditorialAdmin
from .models import NewsItem

@admin.register(NewsItem)
class NewsItemAdmin(EditorialAdmin):
    list_filter = EditorialAdmin.list_filter + ('kind',)
