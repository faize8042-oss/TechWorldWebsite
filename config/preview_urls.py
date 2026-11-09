from django.http import HttpResponse
from django.shortcuts import render
from django.urls import include, path
from core import views

def projects(request):
    return render(request, 'preview/projects.html')
def contact(request):
    return render(request, 'preview/contact.html')
def publishing_preview(request, section):
    return render(request, 'publishing/list.html', {'section': section, 'preview': True})

def robots(request):
    return HttpResponse('User-agent: *\nDisallow: /\n', content_type='text/plain')
urlpatterns = [path('', views.home, name='home'),
 path('services/', views.services, name='services'), path('about/', views.about, name='about'),
 path('privacy/', views.privacy, name='privacy'), path('terms/', views.terms, name='terms'),
 path('projects/', include(([path('', projects, name='list')], 'projects'))),
 path('contact/', include(([path('', contact, name='contact')], 'contact'))),
 path('blog/', include(([path('', lambda request: publishing_preview(request, 'blog'), name='list')], 'blog'))),
 path('news/', include(([path('', lambda request: publishing_preview(request, 'news'), name='list')], 'news'))),
 path('robots.txt', robots)]
