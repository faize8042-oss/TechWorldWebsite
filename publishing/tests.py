from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
from PIL import Image
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from blog.models import BlogPost, Category
from news.models import NewsItem
from config.preview_settings import MIDDLEWARE as PREVIEW_MIDDLEWARE

class PublishingTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(PUBLISHING_IMAGE_ROOT=self.directory.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.category = Category.objects.create(name='Engineering', slug='engineering')

    def article(self, model=BlogPost, **kwargs):
        values = dict(title='Test article', slug='test-article', summary='Test summary',
            body='Test body', status='published', published_at=timezone.now()-timedelta(days=1))
        values.update({'category': self.category} if model == BlogPost else {'kind': 'industry'})
        values.update(kwargs)
        return model.objects.create(**values)

    def upload(self):
        stream = BytesIO()
        Image.new('RGB', (24, 24), 'red').save(stream, format='PNG', pnginfo=None)
        return SimpleUploadedFile('private-name.png', stream.getvalue(), content_type='image/png')

    def test_publication_boundary_both_apps(self):
        for model, section in ((BlogPost, 'blog'), (NewsItem, 'news')):
            public = self.article(model)
            draft = self.article(model, slug='draft', title='Private draft', status='draft')
            future = self.article(model, slug='future', title='Future secret', published_at=timezone.now()+timedelta(days=1))
            response = self.client.get(f'/{section}/')
            self.assertContains(response, public.title)
            self.assertNotContains(response, draft.title)
            self.assertNotContains(response, future.title)
            for item in (draft, future):
                self.assertEqual(self.client.get(item.get_absolute_url()).status_code, 404)
                self.assertEqual(self.client.get(item.get_image_url()).status_code, 404)
            self.assertEqual(self.client.get(public.get_absolute_url()).status_code, 200)
            self.assertEqual(self.client.post(public.get_absolute_url()).status_code, 405)

    def test_images_reencoded_private_and_revoked(self):
        for model in (BlogPost, NewsItem):
            item = self.article(model, cover_image=self.upload(), image_alt='Red square')
            self.assertTrue(item.cover_image.name.endswith('.jpg'))
            self.assertNotIn('private-name', item.cover_image.name)
            with self.assertRaises(ValueError):
                _ = item.cover_image.url
            response = self.client.get(item.get_image_url())
            self.assertEqual(response.status_code, 200)
            self.assertIn('no-store', response['Cache-Control'])
            # The test client's iterator closes the response with database
            # cleanup disconnected. Closing it again fires request_finished
            # outside that protection and closes PostgreSQL's test transaction.
            with patch.object(connection, 'close', wraps=connection.close) as close_connection:
                data = b''.join(response.streaming_content)
                close_connection.assert_not_called()
            self.assertTrue(response.closed)
            self.assertFalse(connection.closed_in_transaction)
            self.assertTrue(model.objects.filter(pk=item.pk).exists())
            with Image.open(BytesIO(data)) as image:
                self.assertEqual(image.format, 'JPEG')
                self.assertFalse(image.getexif())
            item.status = 'draft'
            item.save()
            self.assertEqual(self.client.get(item.get_image_url()).status_code, 404)

    def test_invalid_images_and_validation(self):
        for upload in (SimpleUploadedFile('bad.png', b'not an image'),
                       SimpleUploadedFile('bad.svg', b'<svg onload="alert(1)"></svg>')):
            with self.assertRaises(ValidationError):
                self.article(cover_image=upload, image_alt='Image')
        for values in ({'published_at': None}, {'author_name': 'private@example.com'},
                       {'status': 'invalid'}, {'body': '  '}, {'cover_image': self.upload()}):
            with self.assertRaises(ValidationError):
                self.article(**values)

    def test_database_constraints(self):
        item = self.article()
        for values in ({'status': 'invalid'}, {'published_at': None}, {'slug': ''}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                BlogPost.objects.filter(pk=item.pk).update(**values)
        with self.assertRaises(ValidationError):
            self.article()

    def test_escaped_content_and_schema(self):
        item = self.article(title='Title </script><script>alert(1)</script>',
                            body='<script>alert(2)</script>')
        with override_settings(SEO_INDEXING_ENABLED=True, SEO_SITE_URL='https://example.com'):
            response = self.client.get(item.get_absolute_url())
        self.assertContains(response, '&lt;script&gt;alert(2)&lt;/script&gt;')
        self.assertNotContains(response, '<script>alert(')
        html = response.content.decode()
        schemas = html.split('<script type="application/ld+json">')[1:]
        payload = json.loads(schemas[-1].split('</script>')[0])
        self.assertEqual(payload['headline'], item.title)
        self.assertNotIn('author', payload)

    def test_search_filters_pagination_and_empty_states(self):
        self.assertContains(self.client.get('/blog/'), 'Insights are on the way')
        for index in range(11):
            self.article(slug=f'post-{index}', title=f'Article {index}')
        response = self.client.get('/blog/?q=Article&category=engineering')
        self.assertEqual(len(response.context['page_obj']), 9)
        self.assertContains(response, 'q=Article')
        self.assertContains(self.client.get('/blog/?page=2'), 'Page 2 of 2')
        self.assertEqual(self.client.get('/blog/?page=bad').status_code, 200)
        self.assertContains(self.client.get('/blog/?category=missing'), 'No matching articles')
        self.assertContains(self.client.get('/blog/?q=missing'), 'No matching articles')
        self.article(NewsItem)
        self.assertContains(self.client.get('/news/?kind=company'), 'No matching articles')
        self.assertContains(self.client.get('/news/?kind=industry'), 'Test article')

    def test_sitemap_public_only_and_disabled(self):
        public = self.article()
        draft = self.article(slug='secret-draft', status='draft')
        future = self.article(NewsItem, slug='secret-future', published_at=timezone.now()+timedelta(days=1))
        with override_settings(SEO_INDEXING_ENABLED=True, SEO_SITE_URL='https://example.com'):
            response = self.client.get('/sitemap.xml')
        self.assertContains(response, public.get_absolute_url())
        self.assertNotContains(response, draft.get_absolute_url())
        self.assertNotContains(response, future.get_absolute_url())
        with override_settings(SEO_INDEXING_ENABLED=False):
            self.assertNotContains(self.client.get('/sitemap.xml'), public.get_absolute_url())

    def test_admin_editorial_management(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_superuser('editor', 'private@example.invalid', 'test-only-password')
        self.client.force_login(user)
        item = self.article(cover_image=self.upload(), image_alt='Red square')
        response = self.client.get(f'/admin/blog/blogpost/{item.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, item.cover_image.name)
        self.assertContains(response, 'Public')
        self.assertEqual(self.client.get('/admin/news/newsitem/').status_code, 200)

    def test_exact_publication_time_and_missing_stored_file(self):
        now = timezone.now()
        item = self.article(published_at=now)
        with patch('publishing.models.timezone.now', return_value=now):
            self.assertTrue(BlogPost.objects.public().filter(pk=item.pk).exists())
        item.cover_image = 'blog/missing.jpg'
        item.image_alt = 'Unavailable'
        item.save()
        self.assertEqual(self.client.get(item.get_image_url()).status_code, 404)

    def test_image_size_and_pixel_limits(self):
        upload = SimpleUploadedFile('large.png', b'x' * (8 * 1024 * 1024 + 1))
        with self.assertRaises(ValidationError):
            self.article(cover_image=upload, image_alt='Large')
        stream = BytesIO()
        Image.new('1', (4001, 4000)).save(stream, format='PNG')
        with self.assertRaises(ValidationError):
            self.article(cover_image=SimpleUploadedFile('pixels.png', stream.getvalue()), image_alt='Large')

    def test_missing_images_and_path_traversal(self):
        item = self.article()
        self.assertEqual(self.client.get(item.get_image_url()).status_code, 404)
        self.assertEqual(self.client.get('/blog/test-article/image/../../private/').status_code, 404)

@override_settings(ROOT_URLCONF='config.preview_urls', SEO_INDEXING_ENABLED=False,
                   MIDDLEWARE=PREVIEW_MIDDLEWARE, ALLOWED_HOSTS=['localhost'],
                   ANALYTICS_HMAC_SECRET='preview-must-not-record-visits')
class PreviewNavigationTests(SimpleTestCase):
    @patch('analytics.middleware.logger.exception')
    @patch('analytics.models.AnalyticsVisit.objects.create')
    def test_preview_no_database(self, create_visit, log_exception):
        from config.preview import allowed_path
        for path in ('/', '/blog/', '/news/'):
            response = self.client.get(path, HTTP_HOST='localhost')
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, '/blog/')
            self.assertContains(response, '/news/')
            self.assertTrue(allowed_path(path))
        self.assertFalse(allowed_path('/blog/private-draft/'))
        self.assertFalse(allowed_path('/news/private/image/'))
        create_visit.assert_not_called()
        log_exception.assert_not_called()
