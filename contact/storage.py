from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateContactAttachmentStorage(FileSystemStorage):
    """Store contact attachments outside the public media directory."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault(
            "location",
            settings.BASE_DIR / "private_uploads",
        )
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)