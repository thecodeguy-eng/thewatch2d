from django.contrib import admin
from django.urls import path, include
from django.contrib.sitemaps.views import sitemap
from movies.sitemaps import (
    HomeSitemap, SearchSitemap,
    CategorySitemap, mastermap
)
from movies.views import HomeView, robots_txt
from django.contrib.auth.views import LogoutView

sitemaps = {
    'home': HomeSitemap(),
    'search': SearchSitemap(),
    'categories': CategorySitemap(),
    'movies': mastermap(),
}

urlpatterns = [
    path('watch2d/watch2d_admin/admin', admin.site.urls),
    path('', HomeView.as_view(), name='home'),
    path('anime/', include('anime.urls')), # anime app
    path('manga/', include('manga.urls')), # manga app
    path('', include(('movies.urls', 'movies'), namespace='movies')),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path("robots.txt", robots_txt),
    path('accounts/', include('allauth.urls')),
]

handler404 = 'movies.views.custom_404_view'




# Add these to your main urls.py file
from django.views.generic import TemplateView
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.conf.urls.static import static
import json

# PWA Views
def manifest_view(request):
    """Serve the PWA manifest.json"""
    manifest_data = {
        "name": "Watch2D - Movies & Series",
        "short_name": "Watch2D",
        "description": "Stream and download movies, series, anime, K-Dramas and more.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "theme_color": "#0ea5e9",
        "background_color": "#ffffff",
        "categories": ["entertainment", "multimedia", "movies"],
        "lang": "en",
        "dir": "ltr",
        "icons": [
            {
                "src": "/static/img/icons/icon-72x72.png",
                "sizes": "72x72",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": "/static/img/icons/icon-96x96.png",
                "sizes": "96x96",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": "/static/img/icons/icon-128x128.png",
                "sizes": "128x128",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": "/static/img/icons/icon-144x144.png",
                "sizes": "144x144",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": "/static/img/icons/icon-152x152.png",
                "sizes": "152x152",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": "/static/img/icons/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": "/static/img/icons/icon-384x384.png",
                "sizes": "384x384",
                "type": "image/png",
                "purpose": "maskable any"
            },
            {
                "src": "/static/img/icons/icon-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable any"
            }
        ],
        "shortcuts": [
            {
                "name": "Search Movies",
                "short_name": "Search",
                "description": "Search for movies and series",
                "url": "/movies/search/",
                "icons": [
                    {
                        "src": "/static/img/icons/search-icon-96.png",
                        "sizes": "96x96"
                    }
                ]
            },
            {
                "name": "Hollywood Movies",
                "short_name": "Hollywood",
                "description": "Browse Hollywood movies",
                "url": "/movies/hollywood/",
                "icons": [
                    {
                        "src": "/static/img/icons/hollywood-icon-96.png",
                        "sizes": "96x96"
                    }
                ]
            }
        ]
    }
    
    response = JsonResponse(manifest_data)
    response['Content-Type'] = 'application/manifest+json'
    response['Cache-Control'] = 'public, max-age=86400'  # Cache for 1 day
    return response

def service_worker_view(request):
    """Serve the service worker"""
    with open(settings.BASE_DIR / 'movies' / 'static' / 'js' / 'sw.js', 'r') as f:
        content = f.read()
    
    response = HttpResponse(content, content_type='application/javascript')
    response['Cache-Control'] = 'public, max-age=3600'  # Cache for 1 hour
    response['Service-Worker-Allowed'] = '/'
    return response

def offline_view(request):
    """Serve the offline page"""
    return TemplateView.as_view(template_name='movies/offline.html')(request)

# Optional: Push notification subscription view
def push_subscribe_view(request):
    """Handle push notification subscriptions"""
    if request.method == 'POST':
        try:
            import json
            subscription_data = json.loads(request.body)
            
            # Save subscription to database or send to push service
            # This is where you'd implement your push notification logic
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid method'})

# Add these URL patterns to your main urlpatterns
urlpatterns += [
    # PWA URLs
    path('manifest.json', manifest_view, name='pwa_manifest'),
    path('sw.js', service_worker_view, name='service_worker'),
    path('offline.html', offline_view, name='offline'),
    
    # API endpoints for PWA features
    path('api/push-subscribe/', push_subscribe_view, name='push_subscribe'),
]

