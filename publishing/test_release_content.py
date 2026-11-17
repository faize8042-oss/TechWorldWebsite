import base64
from datetime import timedelta
import hashlib
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from blog.models import BlogPost, Category
from news.models import NewsItem


class ReleaseContentTests(TestCase):
    def article(self, slug, **extra):
        category, _ = Category.objects.get_or_create(name='Engineering', slug='engineering')
        return BlogPost.objects.create(category=category, title=slug, slug=slug,
            summary='Public summary', body='Public body',
            **{'status': 'published', 'published_at': timezone.now() - timedelta(days=1), **extra})

    def export(self):
        output = StringIO()
        call_command('release_content', 'export', stdout=output)
        return json.loads(output.getvalue())

    def test_export_excludes_drafts_scheduled_posts_and_unused_categories(self):
        self.article('visible')
        self.article('private-draft-marker', status='draft')
        self.article('private-future-marker', published_at=timezone.now() + timedelta(days=1))
        Category.objects.create(name='Private unused category', slug='unused')
        data = self.export()
        serialized = json.dumps(data)
        self.assertIn('visible', serialized)
        for marker in ('private-draft-marker', 'private-future-marker', 'Private unused category', 'auth.user', 'contact.'):
            self.assertNotIn(marker, serialized)
        self.assertEqual(len(data['objects']), 2)

    def test_import_roundtrip_and_refuse_existing_content(self):
        self.article('visible')
        bundle = self.export()
        with TemporaryDirectory() as temporary:
            fixture = Path(temporary) / 'public.json'
            fixture.write_text(json.dumps(bundle))
            with self.assertRaisesRegex(CommandError, 'must be empty'):
                call_command('release_content', 'import', file=str(fixture))
            BlogPost.objects.all().delete()
            Category.objects.all().delete()
            call_command('release_content', 'import', file=str(fixture), stdout=StringIO())
            self.assertEqual(BlogPost.objects.get().slug, 'visible')

    def test_invalid_model_cannot_import_accounts(self):
        with TemporaryDirectory() as temporary:
            fixture = Path(temporary) / 'public.json'
            fixture.write_text(json.dumps({'version': 1, 'objects': [{'model': 'auth.user'}], 'images': []}))
            with self.assertRaisesRegex(CommandError, 'Unsupported'):
                call_command('release_content', 'import', file=str(fixture))

    def test_image_integrity_failure_rolls_back_database(self):
        self.article('visible', cover_image='blog/test.jpg', image_alt='Test image')
        # Assemble from serializers rather than opening a nonexistent source image.
        from django.core import serializers
        objects = list(Category.objects.all()) + list(BlogPost.objects.all())
        bundle = {'version': 1, 'objects': json.loads(serializers.serialize('json', objects)), 'images': [
            {'model': 'blog.blogpost', 'pk': BlogPost.objects.get().pk, 'name': 'blog/test.jpg', 'data': base64.b64encode(b'bad').decode(), 'sha256': hashlib.sha256(b'other').hexdigest()}]}
        BlogPost.objects.all().delete()
        Category.objects.all().delete()
        with TemporaryDirectory() as temporary, override_settings(PUBLISHING_IMAGE_ROOT=temporary):
            fixture = Path(temporary) / 'public.json'
            fixture.write_text(json.dumps(bundle))
            with self.assertRaisesRegex(CommandError, 'integrity'):
                call_command('release_content', 'import', file=str(fixture))
        self.assertFalse(BlogPost.objects.exists())
        self.assertFalse(Category.objects.exists())
