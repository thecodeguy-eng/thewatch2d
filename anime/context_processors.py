from .models import AnimeCategory, AnimeGenre

def anime_context(request):
    """Add anime-related context to all templates"""
    return {
        'anime_categories': AnimeCategory.objects.filter(is_active=True)[:10],
        'anime_genres': AnimeGenre.objects.all()[:15],
    }