from .storage import PrivateContactAttachmentStorage
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from PIL import Image, UnidentifiedImageError


ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG"}
MAX_ATTACHMENT_SIZE = 5 * 1024 * 1024


def validate_attachment_size(file):
    """Limit uploaded attachments to 5 MB."""
    if file.size > MAX_ATTACHMENT_SIZE:
        raise ValidationError("The attachment must be 5 MB or smaller.")


def validate_attachment_content(file):
    """
    Check that uploaded files contain valid PDF, PNG, or JPEG content.
    The file extension alone is not trusted.
    """
    filename = Path(file.name).name.lower()
    extension = Path(filename).suffix

    try:
        file.seek(0)

        if extension == ".pdf":
            # Check the PDF file signature.
            header = file.read(5)
            if header != b"%PDF-":
                raise ValidationError(
                    "The uploaded file does not contain a valid PDF signature."
                )

        elif extension in {".png", ".jpg", ".jpeg"}:
            # Verify that the image is a real PNG or JPEG.
            try:
                with Image.open(file) as image:
                    if image.format not in ALLOWED_IMAGE_FORMATS:
                        raise ValidationError(
                            "Only valid PNG and JPEG images are allowed."
                        )
                    image.verify()
            except (UnidentifiedImageError, OSError, SyntaxError) as exc:
                raise ValidationError(
                    "The uploaded image is invalid or corrupted."
                ) from exc

        else:
            raise ValidationError(
                "Only PDF, PNG, JPG, and JPEG files are allowed."
            )

    finally:
        # Leave the uploaded file ready for Django to save.
        file.seek(0)


class ContactSubmission(models.Model):
    class ProjectType(models.TextChoices):
        WEBSITE = "website", "Website Development"
        WEB_APP = "web_app", "Web Application"
        ECOMMERCE = "ecommerce", "E-commerce"
        AI = "ai", "AI Application"
        AUTOMATION = "automation", "Automation / Integration"
        OTHER = "other", "Other"

    class BudgetRange(models.TextChoices):
        UNDECIDED = "undecided", "Not decided yet"
        UNDER_500 = "under_500", "Under $500"
        FROM_500_TO_1500 = "500_1500", "$500–$1,500"
        FROM_1500_TO_5000 = "1500_5000", "$1,500–$5,000"
        OVER_5000 = "over_5000", "Over $5,000"

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    name = models.CharField(max_length=100)
    email = models.EmailField(max_length=254)

    project_type = models.CharField(
        max_length=20,
        choices=ProjectType.choices,
    )

    budget_range = models.CharField(
        max_length=20,
        choices=BudgetRange.choices,
        default=BudgetRange.UNDECIDED,
    )

    message = models.TextField(max_length=5000)

    attachment = models.FileField(
        storage=PrivateContactAttachmentStorage(),
        upload_to="contact_attachments/",
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=["pdf", "png", "jpg", "jpeg"]
            ),
            validate_attachment_size,
            validate_attachment_content,
        ],
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Contact Submission"
        verbose_name_plural = "Contact Submissions"

    def __str__(self):
        return f"{self.name} — {self.get_project_type_display()}"
