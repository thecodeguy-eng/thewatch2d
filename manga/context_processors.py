from .models import MangaCategory, MangaGenre

def manga_context(request):
    """Add manga-related context to all templates"""
    return {
        'manga_categories': MangaCategory.objects.filter(is_active=True)[:10],
        'manga_genres': MangaGenre.objects.all()[:15],
        'manga_types': [
            {'value': 'manga', 'label': 'Manga'},
            {'value': 'manhwa', 'label': 'Manhwa'},
            {'value': 'manhua', 'label': 'Manhua'},
            {'value': 'webtoon', 'label': 'Webtoon'},
        ]
    }