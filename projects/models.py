
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Project(models.Model):
    class ProjectType(models.TextChoices):
        CLIENT = "client", "Client Project"
        INTERNAL = "internal", "Internal Project"
        PERSONAL = "personal", "Personal Project"
        CONCEPT = "concept", "Concept / Demo"

    title = models.CharField(max_length=200)

    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True,
    )

    summary = models.CharField(
        max_length=300,
        help_text="A short introduction shown on the portfolio card.",
    )

    description = models.TextField(
        help_text="Explain the project, its purpose, and what was built.",
    )

    category = models.CharField(
        max_length=100,
        help_text="For example: Web Development, AI, or E-commerce.",
    )

    technologies = models.JSONField(
        default=list,
        blank=True,
        help_text='Enter a JSON list, for example: ["Django", "PostgreSQL"].',
    )

    project_type = models.CharField(
        max_length=20,
        choices=ProjectType.choices,
        default=ProjectType.PERSONAL,
    )

    cover_image = models.ImageField(
        upload_to="projects/",
        blank=True,
        null=True,
    )

    github_url = models.URLField(
        blank=True,
        max_length=500,
    )

    live_url = models.URLField(
        blank=True,
        max_length=500,
    )

    is_published = models.BooleanField(
        default=False,
        help_text="Only published projects appear on the public website.",
    )

    featured = models.BooleanField(
        default=False,
        help_text="Mark this project as featured on the portfolio.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-featured", "-created_at"]
        verbose_name = "Portfolio Project"
        verbose_name_plural = "Portfolio Projects"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "project"
            candidate = base_slug
            counter = 2

            while (
                Project.objects.filter(slug=candidate)
                .exclude(pk=self.pk)
                .exists()
            ):
                candidate = f"{base_slug}-{counter}"
                counter += 1

            self.slug = candidate

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("projects:detail", kwargs={"slug": self.slug})

    def __str__(self):
        return self.title
