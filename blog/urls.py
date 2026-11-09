from functools import partial
from django.urls import path
from django.views.decorators.http import require_safe
from publishing import views
from .models import BlogPost
app_name = 'blog'
urlpatterns = [
 path('', require_safe(partial(views.listing, model=BlogPost, section='blog')), name='list'),
 path('<slug:slug>/', require_safe(partial(views.detail, model=BlogPost, section='blog')), name='detail'),
 path('<slug:slug>/image/', require_safe(partial(views.image, model=BlogPost)), name='image'),
]
