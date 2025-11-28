from django.contrib import admin
from django.urls import path, include
from django.contrib.sitemaps.views import sitemap
from movies.sitemaps import (
    HomeSitemap, SearchSitemap,
    CategorySitemap, mastermap
)
from movies.views import robots_txt
from django.contrib.auth.views import LogoutView
from django.views.generic import TemplateView
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.conf.urls.static import static
import json

# Sitemaps
sitemaps = {
    'home': HomeSitemap(),
    'search': SearchSitemap(),
    'categories': CategorySitemap(),
    'movies': mastermap(),
}

# PWA Views
def manifest_view(request):
    """Serve the PWA manifest.json"""
    manifest_data = {
        "name": "Watch2D - Movies, Anime, Manga & Apps",
        "short_name": "Watch2D",
        "description": "Stream movies, watch anime, read manga, and download premium APKs - all in one place!",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "theme_color": "#3b82f6",
        "background_color": "#ffffff",
        "categories": ["entertainment", "multimedia", "movies", "anime", "manga"],
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
                "name": "Movies",
                "short_name": "Movies",
                "description": "Browse latest movies",
                "url": "/movies/",
                "icons": [{"src": "/static/img/icons/icon-96x96.png", "sizes": "96x96"}]
            },
            {
                "name": "Anime",
                "short_name": "Anime",
                "description": "Watch anime series",
                "url": "/anime/",
                "icons": [{"src": "/static/img/icons/icon-96x96.png", "sizes": "96x96"}]
            },
            {
                "name": "Manga",
                "short_name": "Manga",
                "description": "Read manga online",
                "url": "/manga/",
                "icons": [{"src": "/static/img/icons/icon-96x96.png", "sizes": "96x96"}]
            },
            {
                "name": "APK Store",
                "short_name": "Apps",
                "description": "Download premium APKs",
                "url": "/apk_store/",
                "icons": [{"src": "/static/img/icons/icon-96x96.png", "sizes": "96x96"}]
            }
        ]
    }
    
    response = JsonResponse(manifest_data)
    response['Content-Type'] = 'application/manifest+json'
    response['Cache-Control'] = 'public, max-age=86400'
    return response

def service_worker_view(request):
    """Serve the service worker"""
    try:
        with open(settings.BASE_DIR / 'movies' / 'static' / 'js' / 'sw.js', 'r') as f:
            content = f.read()
        response = HttpResponse(content, content_type='application/javascript')
        response['Cache-Control'] = 'public, max-age=3600'
        response['Service-Worker-Allowed'] = '/'
        return response
    except FileNotFoundError:
        return HttpResponse("Service worker not found", status=404)

def offline_view(request):
    """Serve the offline page"""
    return TemplateView.as_view(template_name='movies/offline.html')(request)

def push_subscribe_view(request):
    """Handle push notification subscriptions"""
    if request.method == 'POST':
        try:
            subscription_data = json.loads(request.body)
            # Save subscription logic here
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid method'})


# =============================================================================
# MAIN URL PATTERNS
# =============================================================================

urlpatterns = [
    # Admin
    path('watch2d/watch2d_admin/admin', admin.site.urls),
    
    # ⭐ UNIFIED HOMEPAGE (Main app)
    path('', include('main.urls')),
    
    # 🎬 Movies App (has its own home page at /movies/)
    path('movies/', include(('movies.urls', 'movies'), namespace='movies')),
    
    # 🎭 Anime App
    path('anime/', include('anime.urls')),
    
    # 📚 Manga App  
    path('manga/', include('manga.urls')),
    
    # 📱 APK Store App
    path('apk_store/', include('apk_store.urls')),
    
    # Authentication
    path('logout/', LogoutView.as_view(), name='logout'),
    path('accounts/', include('allauth.urls')),
    
    # SEO
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='sitemap'),
    path("robots.txt", robots_txt),
    
    # PWA URLs
    path('manifest.json', manifest_view, name='pwa_manifest'),
    path('sw.js', service_worker_view, name='service_worker'),
    path('offline.html', offline_view, name='offline'),
    path('api/push-subscribe/', push_subscribe_view, name='push_subscribe'),
]

# Custom 404 handler
handler404 = 'movies.views.custom_404_view'

# Static/Media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)