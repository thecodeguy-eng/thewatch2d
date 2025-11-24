# Create movies/middleware.py
from master import settings
class PWAMiddleware:
    """Middleware to add PWA-specific headers and handle PWA requests"""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Add PWA headers
        if request.path.endswith('.js') and 'sw.js' in request.path:
            response['Service-Worker-Allowed'] = '/'
            response['Cache-Control'] = 'public, max-age=3600'
        
        # Add manifest headers
        if request.path.endswith('manifest.json'):
            response['Content-Type'] = 'application/manifest+json'
            response['Cache-Control'] = 'public, max-age=86400'
        
        # Add security headers for PWA
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['Referrer-Policy'] = 'same-origin'
        
        # HTTPS enforcement for PWA features
        if not request.is_secure() and not settings.DEBUG:
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        return response