from django.contrib import admin
from publishing.admin import EditorialAdmin
from .models import BlogPost, Category

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)

@admin.register(BlogPost)
class BlogPostAdmin(EditorialAdmin):
    list_filter = EditorialAdmin.list_filter + ('category',)
    list_select_related = ('category',)
