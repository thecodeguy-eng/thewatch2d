from django.shortcuts import render
from django.views.generic import TemplateView
from django.db.models import Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

# Import models from all apps
from movies.models import Movie, Category as MovieCategory
from anime.models import Anime, Episode
from manga.models import Manga, Chapter
from apk_store.models import APK, Category as APKCategory


@method_decorator(cache_page(60 * 30), name='dispatch')  # Cache for 30 minutes
class UnifiedHomeView(TemplateView):
    """
    Unified homepage combining content from all apps:
    - Movies (featured, trending, latest)
    - Anime (popular, recent episodes)
    - Manga (trending, new chapters)
    - APK Store (featured games & apps)
    """
    template_name = 'main/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # ========== MOVIES SECTION ==========
        # Remove is_active=True since Movie model doesn't have this field
        context['featured_movies'] = Movie.objects.filter(
            is_blockbuster=True
        ).select_related().prefetch_related('categories').order_by('-created_at')[:8]
        
        context['trending_movies'] = Movie.objects.filter(
            views__gt=0
        ).order_by('-views', '-created_at')[:12]
        
        context['latest_movies'] = Movie.objects.filter(
            Q(title_b__isnull=True) | Q(title_b='')
        ).order_by('-created_at')[:12]
        
        context['movie_categories'] = MovieCategory.objects.all()[:6]
        
        
        # ========== ANIME SECTION ==========
        context['featured_anime'] = Anime.objects.filter(
            is_active=True,
            is_featured=True
        ).select_related('category').prefetch_related('genres').order_by('-views')[:8]
        
        context['trending_anime'] = Anime.objects.filter(
            is_active=True,
            is_trending=True
        ).order_by('-views')[:12]
        
        context['latest_episodes'] = Episode.objects.filter(
            is_active=True,
            anime__is_active=True
        ).select_related('anime', 'anime__category').order_by('-created_at')[:12]
        
        
        # ========== MANGA SECTION ==========
        context['featured_manga'] = Manga.objects.filter(
            is_active=True,
            is_featured=True
        ).select_related('category').prefetch_related('genres').order_by('-views')[:8]
        
        context['trending_manga'] = Manga.objects.filter(
            is_active=True,
            is_trending=True
        ).order_by('-views')[:12]
        
        context['latest_chapters'] = Chapter.objects.filter(
            is_active=True,
            manga__is_active=True
        ).select_related('manga', 'manga__category').order_by('-created_at')[:12]
        
        
        # ========== APK STORE SECTION ==========
        context['featured_apks'] = APK.objects.filter(
            is_active=True,
            featured=True
        ).prefetch_related('categories', 'screenshots').order_by('-created_at')[:8]
        
        context['latest_games'] = APK.objects.filter(
            is_active=True,
            apk_type='game'
        ).order_by('-created_at')[:12]
        
        context['latest_apps'] = APK.objects.filter(
            is_active=True,
            apk_type='app'
        ).order_by('-created_at')[:12]
        
        context['apk_categories'] = APKCategory.objects.all()[:6]
        
        
        # ========== STATS FOR HERO SECTION ==========
        context['total_movies'] = Movie.objects.count()
        context['total_anime'] = Anime.objects.filter(is_active=True).count()
        context['total_manga'] = Manga.objects.filter(is_active=True).count()
        context['total_apks'] = APK.objects.filter(is_active=True).count()
        
        return context