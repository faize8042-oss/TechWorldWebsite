
from django.http import HttpResponse
from django.shortcuts import render


def home(request):
    return render(request, "core/home.html")


def services(request):
    return render(request, "core/services.html")


def about(request):
    return render(request, "core/about.html")


def privacy(request):
    return render(request, "core/privacy.html")


def terms(request):
    return render(request, "core/terms.html")


def health(request):
    """Minimal application liveness response; does not probe dependencies."""
    response = HttpResponse("ok\n", content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "no-store"
    return response
