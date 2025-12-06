# main/urls.py
from django.urls import path
from . import views
from .pwa_views import (
    manifest_view, 
    service_worker_view, 
    offline_view, 
    push_subscribe_view
)

app_name = 'main'

urlpatterns = [
    # Main homepage
    path('', views.UnifiedHomeView.as_view(), name='home'),
    
    # PWA URLs
    path('manifest.json', manifest_view, name='pwa_manifest'),
    path('sw.js', service_worker_view, name='service_worker'),
    path('offline.html', offline_view, name='offline'),
    path('api/push-subscribe/', push_subscribe_view, name='push_subscribe'),
]