from functools import partial
from django.urls import path
from django.views.decorators.http import require_safe
from publishing import views
from .models import NewsItem
app_name = 'news'
urlpatterns = [
 path('', require_safe(partial(views.listing, model=NewsItem, section='news')), name='list'),
 path('<slug:slug>/', require_safe(partial(views.detail, model=NewsItem, section='news')), name='detail'),
 path('<slug:slug>/image/', require_safe(partial(views.image, model=NewsItem)), name='image'),
]
