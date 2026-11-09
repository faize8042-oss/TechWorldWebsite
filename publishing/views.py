import json
import math
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.cache import patch_cache_control
from django.utils.safestring import mark_safe
from django.views.decorators.http import require_safe


def no_store(response):
    patch_cache_control(response, private=True, no_store=True, max_age=0)
    return response


def listing(request, model, section):
    items = model.objects.public()
    query = request.GET.get('q', '').strip()[:200]
    selected = request.GET.get('category' if section == 'blog' else 'kind', '')[:120]
    if query:
        items = items.filter(Q(title__icontains=query) | Q(summary__icontains=query) | Q(body__icontains=query))
    if section == 'blog':
        from blog.models import Category
        filters = Category.objects.filter(posts__in=model.objects.public()).distinct()
        if selected:
            items = items.filter(category__slug=selected)
        items = items.select_related('category')
    else:
        filters = model.Kind.choices
        if selected:
            items = items.filter(kind=selected)
    page = Paginator(items, 9).get_page(request.GET.get('page'))
    page.object_list = list(page.object_list)
    for article in page.object_list:
        article.reading_minutes = max(1, math.ceil(len(article.body.split()) / 220))
    params = request.GET.copy()
    params.pop('page', None)
    canonical = ''
    if settings.SEO_INDEXING_ENABLED and settings.SEO_SITE_URL:
        canonical = settings.SEO_SITE_URL + reverse(section + ':list')
        if not query and not selected and page.number > 1:
            canonical += '?page=' + str(page.number)
    return no_store(render(request, 'publishing/list.html', {'section': section, 'page_obj': page,
        'query': query, 'selected': selected, 'filters': filters, 'page_query': params.urlencode(),
        'seo_canonical_url': canonical}))


def detail(request, model, section, slug):
    article = get_object_or_404(model.objects.public(), slug=slug)
    reading_minutes = max(1, math.ceil(len(article.body.split()) / 220))
    related_items = model.objects.public().exclude(pk=article.pk)[:3]
    schema = ''
    breadcrumbs = ''
    if settings.SEO_INDEXING_ENABLED and settings.SEO_SITE_URL:
        payload = {'@context': 'https://schema.org', '@type': 'BlogPosting' if section == 'blog' else 'NewsArticle',
            'headline': article.title, 'description': article.seo_description or article.summary,
            'datePublished': article.published_at.isoformat(), 'dateModified': article.updated_at.isoformat(),
            'mainEntityOfPage': settings.SEO_SITE_URL + article.get_absolute_url()}
        payload['publisher'] = {'@type': 'Organization', '@id': settings.SEO_SITE_URL + '/#organization',
                                'name': 'TechBullion Hub', 'url': settings.SEO_SITE_URL}
        payload['articleSection'] = str(article.category) if section == 'blog' else article.get_kind_display()
        payload['inLanguage'] = 'en'
        if article.author_name:
            payload['author'] = {'@type': 'Person', 'name': article.author_name}
            if article.author_name.casefold() == 'faizan yousuf':
                payload['author']['url'] = settings.SEO_SITE_URL + reverse('about') + '#faizan-yousuf'
        if article.cover_image:
            payload['image'] = settings.SEO_SITE_URL + article.get_image_url()
        schema = mark_safe(json.dumps(payload).replace('<', r'\u003c').replace('>', r'\u003e').replace('&', r'\u0026'))
        breadcrumb_payload = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': settings.SEO_SITE_URL + '/'},
            {'@type': 'ListItem', 'position': 2, 'name': section.title(), 'item': settings.SEO_SITE_URL + reverse(section + ':list')},
            {'@type': 'ListItem', 'position': 3, 'name': article.title, 'item': settings.SEO_SITE_URL + article.get_absolute_url()}]}
        breadcrumbs = mark_safe(json.dumps(breadcrumb_payload).replace('<', r'\u003c').replace('>', r'\u003e').replace('&', r'\u0026'))
    return no_store(render(request, 'publishing/detail.html', {'article': article, 'section': section,
        'article_schema': schema, 'breadcrumb_schema': breadcrumbs, 'reading_minutes': reading_minutes, 'related_items': related_items}))


def image(request, model, slug):
    article = get_object_or_404(model.objects.public(), slug=slug)
    if not article.cover_image:
        raise Http404
    try:
        response = FileResponse(article.cover_image.open('rb'), content_type='image/jpeg')
    except (OSError, ValueError):
        raise Http404 from None
    response['X-Content-Type-Options'] = 'nosniff'
    if not (settings.SEO_INDEXING_ENABLED and settings.SEO_SITE_URL):
        response['X-Robots-Tag'] = 'noindex'
    return no_store(response)
