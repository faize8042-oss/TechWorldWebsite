
from django.shortcuts import get_object_or_404, render

from .models import Project


def project_list(request):
    """Show only published portfolio projects."""
    projects = Project.objects.filter(is_published=True)

    return render(
        request,
        "projects/project_list.html",
        {"projects": projects},
    )


def project_detail(request, slug):
    """Show one published portfolio project."""
    project = get_object_or_404(
        Project,
        slug=slug,
        is_published=True,
    )

    return render(
        request,
        "projects/project_detail.html",
        {"project": project},
    )
