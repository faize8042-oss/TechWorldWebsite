
from django.urls import path

from . import views


app_name = "core"

urlpatterns = [
    path("", views.services, name="services"),
    path("about/", views.about, name="about"),
]
