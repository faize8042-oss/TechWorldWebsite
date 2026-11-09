"""Gaps beyond publishing.tests; fixtures exist only in Django's test database."""
from datetime import timedelta
from io import BytesIO, StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.utils import timezone

from blog.models import BlogPost, Category
from news.models import NewsItem
from core.test_seo import MetaParser


class PublishingSecurityTests(TestCase):
    def test_editorial_audit_reads_only_public_articles_and_does_not_change_them(self):
        first = self.article(BlogPost, 'audit-first', seo_title='Shared title', author_name='Faizan Yousuf')
        self.article(NewsItem, 'audit-second', seo_title='Shared title', author_name='Faizan Yousuf')
        private = self.article(BlogPost, 'audit-private', status='draft', seo_title='Shared title')
        self.article(NewsItem, 'audit-future', published_at=timezone.now() + timedelta(days=1))
        output = StringIO()
        call_command('audit_public_seo', stdout=output)
        self.assertIn('duplicate title', output.getvalue())
        self.assertIn('Published articles checked: 2', output.getvalue())
        self.assertNotIn('audit-private', output.getvalue())
        self.assertNotIn('audit-future', output.getvalue())
        first.refresh_from_db()
        private.refresh_from_db()
        self.assertEqual(first.seo_title, 'Shared title')
        self.assertEqual(private.status, 'draft')

    @override_settings(SEO_INDEXING_ENABLED=True, SEO_SITE_URL='https://techbullionhub.net')
    def test_paginated_lists_have_own_canonicals_and_filters_stay_noindex(self):
        for model, section in ((BlogPost, 'blog'), (NewsItem, 'news')):
            for index in range(10):
                self.article(model, f'canonical-{index}')
            response = self.client.get(f'/{section}/?page=2&utm_source=test')
            parsed = MetaParser()
            parsed.feed(response.content.decode())
            self.assertEqual(parsed.canonical, f'https://techbullionhub.net/{section}/?page=2')
            self.assertEqual(parsed.meta['robots'], 'index, follow')
            self.assertContains(response, 'Page 2')
            parsed = MetaParser()
            parsed.feed(self.client.get(f'/{section}/?q=canonical&page=2').content.decode())
            self.assertEqual(parsed.meta['robots'], 'noindex, follow')
            self.assertEqual(parsed.canonical, f'https://techbullionhub.net/{section}/')

    @override_settings(SEO_INDEXING_ENABLED=True, SEO_SITE_URL='https://techbullionhub.net')
    def test_article_publisher_author_and_breadcrumbs_match_visible_content(self):
        article = self.article(BlogPost, 'seo-identity', author_name='Faizan Yousuf')
        parsed = MetaParser()
        parsed.feed(self.client.get(article.get_absolute_url()).content.decode())
        schema = json.loads(parsed.json_ld[-1])
        self.assertEqual(schema['publisher']['name'], 'TechBullion Hub')
        self.assertEqual(schema['author']['url'], 'https://techbullionhub.net/about/#faizan-yousuf')
        breadcrumb = json.loads(parsed.json_ld[-2])
        self.assertEqual(breadcrumb['@type'], 'BreadcrumbList')
        self.assertEqual(breadcrumb['itemListElement'][-1]['item'], parsed.canonical)
        self.assertContains(self.client.get('/sitemap.xml'), article.updated_at.isoformat())

    def test_public_article_image_indexing_obeys_launch_gate(self):
        stream = BytesIO()
        Image.new('RGB', (8, 8)).save(stream, 'PNG')
        article = self.article(BlogPost, 'share-image', cover_image=SimpleUploadedFile('cover.png', stream.getvalue()), image_alt='Synthetic cover')
        response = self.client.get(article.get_image_url())
        self.assertEqual(response['X-Robots-Tag'], 'noindex')
        b''.join(response.streaming_content)
        with override_settings(SEO_INDEXING_ENABLED=True, SEO_SITE_URL='https://techbullionhub.net'):
            response = self.client.get(article.get_image_url())
            self.assertNotIn('X-Robots-Tag', response)
            b''.join(response.streaming_content)
            parsed = MetaParser()
            parsed.feed(self.client.get(article.get_absolute_url()).content.decode())
            self.assertEqual(parsed.meta['og:image'], 'https://techbullionhub.net' + article.get_image_url())
            self.assertEqual(parsed.meta['twitter:card'], 'summary_large_image')

    def test_article_sidebar_excludes_private_and_scheduled_items(self):
        for model in (BlogPost, NewsItem):
            with self.subTest(model=model):
                main = self.article(model, 'main-article', body='word ' * 441)
                self.article(model, 'another-public-article')
                self.article(model, 'private-sidebar-draft', status='draft')
                self.article(model, 'private-sidebar-future', published_at=timezone.now() + timedelta(days=1))
                response = self.client.get(main.get_absolute_url())
                self.assertContains(response, 'another-public-article')
                self.assertNotContains(response, 'private-sidebar-draft')
                self.assertNotContains(response, 'private-sidebar-future')
                self.assertEqual(response.context['reading_minutes'], 3)

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.override = override_settings(PUBLISHING_IMAGE_ROOT=self.directory.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.category = Category.objects.create(name='Security', slug='security')

    def article(self, model, slug, **kwargs):
        values = dict(title=slug, slug=slug, summary='Security summary', body='Security body',
                      status='published', published_at=timezone.now() - timedelta(days=1))
        values.update(category=self.category) if model is BlogPost else values.update(kind='industry')
        values.update(kwargs)
        return model.objects.create(**values)

    def test_private_content_excluded_from_search_filters_and_all_pages(self):
        for model, section, query in ((BlogPost, 'blog', 'category=security'),
                                       (NewsItem, 'news', 'kind=industry')):
            with self.subTest(section=section):
                for index in range(11):
                    self.article(model, f'visible-{index}')
                self.article(model, 'secret-draft', status='draft')
                self.article(model, 'secret-future', published_at=timezone.now() + timedelta(days=1))
                for params in ('q=secret', query, query + '&page=2', 'page=999', 'q=%27%3Cscript%3E'):
                    response = self.client.get(f'/{section}/?{params}')
                    self.assertEqual(response.status_code, 200)
                    for item in response.context['page_obj']:
                        self.assertTrue(item.slug.startswith('visible-'))
                    self.assertNotContains(response, 'secret-draft')
                    self.assertNotContains(response, 'secret-future')

    def test_admin_permissions_and_mutations(self):
        users = [None,
                 get_user_model().objects.create_user('ordinary', password='synthetic-only'),
                 get_user_model().objects.create_user('staff', password='synthetic-only', is_staff=True)]
        for model in (BlogPost, NewsItem):
            item = self.article(model, 'permission-check')
            base = f'/admin/{model._meta.app_label}/{model._meta.model_name}/'
            for user in users:
                client = Client()
                if user:
                    client.force_login(user)
                expected = 403 if user and user.is_staff else 302
                for path in (base, base + 'add/', base + f'{item.pk}/change/', base + f'{item.pk}/delete/'):
                    self.assertEqual(client.get(path).status_code, expected)
                    self.assertEqual(client.post(path, {'title': 'tampered', 'post': 'yes'}).status_code, expected)
                item.refresh_from_db()
                self.assertEqual(item.title, 'permission-check')
                self.assertEqual(model.objects.count(), 1)
                for method in ('post', 'put', 'patch', 'delete'):
                    self.assertEqual(getattr(client, method)(item.get_absolute_url()).status_code, 405)

    def test_admin_logout_invalidates_session_and_requires_csrf(self):
        user = get_user_model().objects.create_superuser('qa-admin', password='synthetic-only')
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        self.assertEqual(client.get('/admin/logout/').status_code, 405)
        self.assertEqual(client.post('/admin/logout/').status_code, 403)
        client.get('/admin/')
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.post('/admin/logout/', {'csrfmiddlewaretoken': token}).status_code, 200)
        self.assertNotIn('_auth_user_id', client.session)
        self.assertEqual(client.get('/admin/').status_code, 302)

    def test_failed_login_does_not_log_credentials(self):
        client = Client(enforce_csrf_checks=True)
        client.get('/admin/login/')
        password = 'synthetic-password-must-never-be-logged'
        with patch('logging.Logger.handle') as handle:
            response = client.post('/admin/login/', {
                'username': 'synthetic-unknown-editor', 'password': password,
                'csrfmiddlewaretoken': client.cookies['csrftoken'].value})
        self.assertEqual(response.status_code, 200)
        for call in handle.call_args_list:
            self.assertNotIn(password, call.args[0].getMessage())
            self.assertNotIn('synthetic-unknown-editor', call.args[0].getMessage())

    def test_contact_post_requires_csrf_without_sending_email(self):
        from contact.models import ContactSubmission
        client = Client(enforce_csrf_checks=True)
        before = ContactSubmission.objects.count()
        with patch('contact.views.send_mail') as send_mail:
            self.assertEqual(client.post('/contact/', {'message': 'not authorized'}).status_code, 403)
        send_mail.assert_not_called()
        self.assertEqual(ContactSubmission.objects.count(), before)

    def test_private_categories_and_seo_do_not_leak(self):
        private_category = Category.objects.create(name='Private category marker', slug='private-category')
        for model in (BlogPost, NewsItem):
            draft = self.article(model, 'private-draft', status='draft')
            future = self.article(model, 'private-future', published_at=timezone.now() + timedelta(days=1))
            if model is BlogPost:
                draft.category = private_category
                draft.save()
                self.assertNotContains(self.client.get('/blog/'), private_category.name)
            with override_settings(SEO_INDEXING_ENABLED=True, SEO_SITE_URL='https://site.example'):
                response = self.client.get('/sitemap.xml')
                for item in (draft, future):
                    self.assertNotContains(response, item.get_absolute_url())
                    self.assertEqual(self.client.get(item.get_absolute_url()).status_code, 404)

    def test_news_xss_and_seo_for_both_sections(self):
        for model in (BlogPost, NewsItem):
            item = self.article(model, 'seo-safe', title='<script>alert(1)</script>',
                                body='<img src=x onerror=alert(2)>', seo_title='QA SEO title',
                                seo_description='QA meta description')
            with override_settings(SEO_INDEXING_ENABLED=True, SEO_SITE_URL='https://site.example'):
                response = self.client.get(item.get_absolute_url())
                self.assertContains(response, '&lt;img')
                self.assertNotContains(response, '<script>alert(')
                self.assertContains(response, 'QA SEO title')
                self.assertContains(response, 'QA meta description')
                parsed = MetaParser()
                parsed.feed(response.content.decode())
                self.assertEqual(parsed.canonical, 'https://site.example' + item.get_absolute_url())
                self.assertEqual(parsed.meta['description'], 'QA meta description')
                schema = json.loads(parsed.json_ld[-1])
                self.assertEqual(schema['@type'], 'BlogPosting' if model is BlogPost else 'NewsArticle')
                self.assertEqual(schema['headline'], item.title)
                self.assertContains(self.client.get('/sitemap.xml'), item.get_absolute_url())

    def test_image_formats_spoofing_and_safe_response(self):
        for model in (BlogPost, NewsItem):
            for image_format, extension in (('PNG', 'png'), ('JPEG', 'jpg'), ('WEBP', 'webp')):
                stream = BytesIO()
                Image.new('RGB', (8, 8)).save(stream, image_format)
                item = self.article(model, 'image-' + extension,
                    cover_image=SimpleUploadedFile('cover.' + extension, stream.getvalue()), image_alt='QA image')
                response = self.client.get(item.get_image_url())
                self.assertEqual(response['Content-Type'], 'image/jpeg')
                self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
                b''.join(response.streaming_content)  # Django closes the iterator exactly once.
            for name, data in (('spoof.jpg', b'<script>alert(1)</script>'), ('corrupt.png', b'\x89PNG\r\n')):
                with self.assertRaises(ValidationError):
                    self.article(model, 'invalid-image', cover_image=SimpleUploadedFile(name, data), image_alt='Invalid')
            with self.assertRaises(ValidationError):
                self.article(model, '../unsafe')
