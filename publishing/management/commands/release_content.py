"""Portable public content only. Never exports users, enquiries or drafts."""
import base64
import hashlib
import json
from pathlib import PurePosixPath

from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from blog.models import BlogPost, Category
from news.models import NewsItem
from projects.models import Project


class Command(BaseCommand):
    help = 'Export public content to stdout, or import a reviewed release bundle into empty content tables.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['export', 'import'])
        parser.add_argument('--file')

    def handle(self, *args, **options):
        if options['action'] == 'export':
            posts = list(BlogPost.objects.public())
            items = list(NewsItem.objects.public())
            projects = list(Project.objects.filter(is_published=True))
            categories = list(Category.objects.filter(pk__in={p.category_id for p in posts}))
            objects = categories + posts + items + projects
            images = []
            for obj in posts + items + projects:
                field = obj.cover_image
                if field:
                    with field.storage.open(field.name, 'rb') as stream:
                        content = stream.read(9 * 1024 * 1024)
                    if len(content) > 8 * 1024 * 1024:
                        raise CommandError('Public image exceeds bundle limit.')
                    images.append({'model': obj._meta.label_lower, 'pk': obj.pk,
                                   'name': field.name, 'sha256': hashlib.sha256(content).hexdigest(),
                                   'data': base64.b64encode(content).decode('ascii')})
            self.stdout.write(json.dumps({'version': 1, 'objects': json.loads(serializers.serialize('json', objects)), 'images': images}))
            return
        if not options['file']:
            raise CommandError('--file is required for import.')
        if any(model.objects.exists() for model in (Category, BlogPost, NewsItem, Project)):
            raise CommandError('Content tables must be empty; import never overwrites existing content.')
        with open(options['file'], encoding='utf-8') as stream:
            bundle = json.load(stream)
        models = {'blog.category': Category, 'blog.blogpost': BlogPost, 'news.newsitem': NewsItem, 'projects.project': Project}
        if bundle.get('version') != 1 or any(obj['model'] not in models for obj in bundle['objects']):
            raise CommandError('Unsupported public content bundle.')
        written = []
        try:
            with transaction.atomic():
                for obj in serializers.deserialize('json', json.dumps(bundle['objects'])):
                    if hasattr(obj.object, 'status') and obj.object.status != 'published':
                        raise CommandError('Draft content is forbidden in release bundles.')
                    if isinstance(obj.object, Project) and not obj.object.is_published:
                        raise CommandError('Unpublished projects are forbidden in release bundles.')
                    obj.save()
                for image in bundle['images']:
                    name = image['name']
                    path = PurePosixPath(name)
                    if path.is_absolute() or '..' in path.parts or '\\' in name:
                        raise CommandError('Unsafe image path.')
                    obj = models[image['model']].objects.get(pk=image['pk'])
                    field = obj.cover_image
                    if field.name != name:
                        raise CommandError('Image reference mismatch.')
                    data = base64.b64decode(image['data'], validate=True)
                    if len(data) > 8 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != image['sha256']:
                        raise CommandError('Image integrity check failed.')
                    if field.storage.exists(name):
                        raise CommandError('Import refuses to overwrite a stored image.')
                    from django.core.files.base import ContentFile
                    stored = field.storage.save(name, ContentFile(data))
                    written.append((field.storage, stored))
                    if stored != name:
                        raise CommandError('Storage changed a release image path.')
                # Explicit fixture IDs require sequence reset before future admin edits.
                from django.core.management.color import no_style
                from django.db import connection
                with connection.cursor() as cursor:
                    for sql in connection.ops.sequence_reset_sql(no_style(), list(models.values())):
                        cursor.execute(sql)
        except Exception:
            for storage, name in written:
                storage.delete(name)
            raise
        self.stdout.write(self.style.SUCCESS('Reviewed public content and images imported.'))
