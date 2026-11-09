"""Read-only checks against published content; never prints private records."""
from collections import defaultdict
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Report duplicate metadata and missing authors/cover descriptions on published Blog and News content.'

    def handle(self, *args, **options):
        from blog.models import BlogPost
        from news.models import NewsItem
        titles, descriptions = defaultdict(list), defaultdict(list)
        count, issues = 0, 0
        for model in (BlogPost, NewsItem):
            for article in model.objects.public():
                count += 1
                path = article.get_absolute_url()
                titles[(article.seo_title or article.title).strip().casefold()].append(path)
                descriptions[(article.seo_description or article.summary).strip().casefold()].append(path)
                if not article.author_name.strip():
                    issues += 1
                    self.stdout.write('REVIEW missing author: ' + path)
                if article.cover_image and not article.image_alt.strip():
                    issues += 1
                    self.stdout.write('REVIEW missing image description: ' + path)
        for label, groups in (('title', titles), ('description', descriptions)):
            for paths in groups.values():
                if len(paths) > 1:
                    issues += 1
                    self.stdout.write('REVIEW duplicate ' + label + ': ' + ', '.join(paths))
        self.stdout.write(f'Published articles checked: {count}. Editorial issues: {issues}. No records changed.')
