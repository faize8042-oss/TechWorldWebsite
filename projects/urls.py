
from django.urls import path

from . import views


app_name = "projects"

urlpatterns = [
    path("", views.project_list, name="list"),
    path("demos/<slug:slug>/", views.project_demo, name="demo"),
    path("<slug:slug>/", views.project_detail, name="detail"),
]
