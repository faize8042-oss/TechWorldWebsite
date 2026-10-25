
from django.test import TestCase
from django.urls import reverse

from .models import Project


class ProjectPageTests(TestCase):
    def create_project(self, title, is_published, **extra):
        return Project.objects.create(
            title=title,
            summary=f"Summary for {title}",
            description=f"Description for {title}",
            category="Web Development",
            is_published=is_published,
            **extra,
        )

    def test_published_project_appears_in_list(self):
        project = self.create_project(
            "Published Demo",
            is_published=True,
        )

        response = self.client.get(reverse("projects:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, project.title)

    def test_unpublished_project_is_hidden(self):
        project = self.create_project(
            "Private Draft",
            is_published=False,
        )

        response = self.client.get(reverse("projects:list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, project.title)

    def test_published_project_detail_loads(self):
        project = self.create_project(
            "Portfolio Example",
            is_published=True,
        )

        response = self.client.get(
            reverse("projects:detail", kwargs={"slug": project.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, project.title)

    def test_unpublished_project_detail_returns_404(self):
        project = self.create_project(
            "Unpublished Example",
            is_published=False,
        )

        response = self.client.get(
            reverse("projects:detail", kwargs={"slug": project.slug})
        )

        self.assertEqual(response.status_code, 404)
