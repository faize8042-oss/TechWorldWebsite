from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from .storage import storage, image_path

class PublicationQuerySet(models.QuerySet):
    def public(self):
        return self.filter(status='published', published_at__lte=timezone.now())

class Publication(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published (scheduled when future-dated)'
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    summary = models.CharField(max_length=300)
    body = models.TextField(help_text='Plain text only. HTML is displayed as text.')
    author_name = models.CharField(max_length=100, blank=True, help_text='Approved public display name only; never an email address.')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    cover_image = models.ImageField(storage=storage, upload_to=image_path, blank=True)
    image_alt = models.CharField(max_length=200, blank=True)
    seo_title = models.CharField(max_length=70, blank=True)
    seo_description = models.CharField(max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = PublicationQuerySet.as_manager()
    class Meta:
        abstract = True
        ordering = ['-published_at', '-pk']
        indexes = [models.Index(fields=['status', '-published_at'], name='%(app_label)s_public_idx')]
        constraints = [
            models.CheckConstraint(condition=Q(status__in=['draft','published']), name='%(app_label)s_status_valid'),
            models.CheckConstraint(condition=~Q(status='published') | Q(published_at__isnull=False), name='%(app_label)s_publish_date'),
            models.CheckConstraint(condition=~Q(title='') & ~Q(slug='') & ~Q(summary='') & ~Q(body=''), name='%(app_label)s_content_required'),
        ]
    def clean(self):
        super().clean()
        if self.status == 'published' and self.published_at is None:
            raise ValidationError({'published_at': 'A publication date is required.'})
        if '@' in self.author_name:
            raise ValidationError({'author_name': 'Use a public display name, not an email address.'})
        for field in ('title', 'summary', 'body'):
            if not getattr(self, field).strip():
                raise ValidationError({field: 'This field cannot be blank.'})
        if self.cover_image and not self.image_alt.strip():
            raise ValidationError({'image_alt': 'Describe the cover image for accessibility.'})
        if self.cover_image and not self.cover_image._committed:
            self._normalize_image()
    def _normalize_image(self):
        source = self.cover_image
        try:
            if source.size > 8 * 1024 * 1024:
                raise ValidationError('Images must be at most 8 MB.')
            source.seek(0)
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(source) as im:
                    if im.format not in ('JPEG', 'PNG', 'WEBP') or im.width * im.height > 16000000:
                        raise ValidationError('Use JPEG, PNG or WebP images up to 16 megapixels.')
                    im.load()
                    normalized = ImageOps.exif_transpose(im).convert('RGB')
                    normalized.thumbnail((2400, 2400))
                    output = BytesIO()
                    normalized.save(output, format='JPEG', quality=85)
            self.cover_image = ContentFile(output.getvalue(), name='cover.jpg')
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise ValidationError({'cover_image': 'Upload a valid JPEG, PNG or WebP image.'}) from None
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    def get_absolute_url(self):
        return reverse(f'{self._meta.app_label}:detail', kwargs={'slug': self.slug})
    def get_image_url(self):
        return reverse(f'{self._meta.app_label}:image', kwargs={'slug': self.slug})
    def __str__(self):
        return self.title
