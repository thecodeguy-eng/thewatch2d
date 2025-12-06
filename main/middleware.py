# main/middleware.py
# Create this new file in your main app

from django.http import HttpResponse
from django.conf import settings

class PWAMiddleware:
    """
    Middleware to add PWA-specific headers and handle offline functionality
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Add PWA-specific headers
        if request.path.endswith('.js'):
            response['Service-Worker-Allowed'] = '/'
            
        # Add cache control for static files
        if any(request.path.startswith(prefix) for prefix in ['/static/', '/media/']):
            response['Cache-Control'] = f'public, max-age={settings.CACHE_CONTROL_MAX_AGE}'
            
        # Add security headers for PWA
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'SAMEORIGIN'
        
        return response