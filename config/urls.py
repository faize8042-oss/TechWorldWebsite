
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core import views
from core import seo


urlpatterns = [
    path("admin/", admin.site.urls),
    path("sitemap.xml", seo.sitemap, name="sitemap"),
    path("robots.txt", seo.robots, name="robots"),

    path("", views.home, name="home"),
    path("services/", views.services, name="services"),
    path("about/", views.about, name="about"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),

    path("projects/", include("projects.urls")),
    path("contact/", include("contact.urls")),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
