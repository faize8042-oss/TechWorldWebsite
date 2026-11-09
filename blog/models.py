from django.db import models
from publishing.models import Publication

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    class Meta:
        ordering = ['name']
        verbose_name_plural = 'categories'
    def __str__(self):
        return self.name

class BlogPost(Publication):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='posts')
