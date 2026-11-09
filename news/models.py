from django.db import models
from publishing.models import Publication

class NewsItem(Publication):
    class Kind(models.TextChoices):
        COMPANY = 'company', 'Company announcements'
        INDUSTRY = 'industry', 'Industry news'
    kind = models.CharField(max_length=12, choices=Kind.choices, db_index=True)
    class Meta(Publication.Meta):
        abstract = False
        constraints = Publication.Meta.constraints + [models.CheckConstraint(condition=models.Q(kind__in=['company','industry']), name='news_kind_valid')]
