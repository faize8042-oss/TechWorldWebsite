from pathlib import Path
from uuid import uuid4
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible

@deconstructible
class PublishingStorage(FileSystemStorage):
    def __init__(self):
        super().__init__()
    @property
    def base_location(self):
        return str(getattr(settings, 'PUBLISHING_IMAGE_ROOT', Path(settings.BASE_DIR) / 'private_publishing'))
    @property
    def location(self):
        return self.base_location
    def url(self, name):
        raise ValueError('Publishing images require publication-checked delivery.')

def image_path(instance, filename):
    return f'{instance._meta.app_label}/{uuid4().hex}.jpg'

storage = PublishingStorage()
