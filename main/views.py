from django.shortcuts import render
from django.views.generic import TemplateView
from django.db.models import Q, Prefetch, Count
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.utils import timezone

# Import models from all apps
from movies.models import Movie, Category as MovieCategory
from anime.models import Anime, Episode
from manga.models import Manga, Chapter
from apk_store.models import APK, Category as APKCategory
from pc_games.models import Game as PCGame
from news.models import NewsArticle, NewsCategory


# ============================================
# Custom Error Handlers
# ============================================

def custom_404_view(request, exception):
    """
    Custom 404 Not Found error page
    """
    context = {
        'exception': str(exception) if exception else None,
    }
    return render(request, '404.html', context, status=404)


def custom_500_view(request):
    """
    Custom 500 Internal Server Error page
    """
    context = {}
    return render(request, '500.html', context, status=500)


def custom_403_view(request, exception):
    """
    Custom 403 Forbidden error page
    """
    context = {
        'exception': str(exception) if exception else None,
    }
    return render(request, '403.html', context, status=403)


def custom_400_view(request, exception):
    """
    Custom 400 Bad Request error page
    """
    context = {
        'exception': str(exception) if exception else None,
    }
    return render(request, '400.html', context, status=400)


def custom_503_view(request):
    """
    Custom 503 Service Unavailable page (for maintenance)
    Call this manually when needed
    """
    return render(request, '503.html', status=503)



# @method_decorator(cache_page(60 * 60 * 2), name='dispatch')  # 2 hours instead of 24
class UnifiedHomeView(TemplateView):
    """
    Unified homepage combining content from all apps:
    - Movies (featured, trending, latest)
    - Anime (latest anime with their episodes)
    - Manga (latest manga with their chapters)
    - News (featured and latest articles)
    - APKs (featured games & apps)
    - PC Games (latest game repacks)
    """
    template_name = 'main/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # ========== MOVIES SECTION ==========
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
        
        
        # ========== NEWS SECTION (NEW!) ==========
        # Featured news articles (for breaking news ticker and hero)
        context['featured_news'] = NewsArticle.objects.filter(
            status='published',
            featured=True
        ).select_related('category', 'author').order_by('-published_at')[:5]
        
        # If no featured articles, use latest
        if not context['featured_news'].exists():
            context['featured_news'] = NewsArticle.objects.filter(
                status='published'
            ).select_related('category', 'author').order_by('-published_at')[:5]
        
        # Latest news articles
        context['latest_news'] = NewsArticle.objects.filter(
            status='published'
        ).select_related('category', 'author').order_by('-published_at')[:8]
        
        # Trending news (by views)
        context['trending_news'] = NewsArticle.objects.filter(
            status='published'
        ).select_related('category', 'author').order_by('-views', '-published_at')[:5]
        
        # News categories with article count
        context['news_categories'] = NewsCategory.objects.annotate(
            article_count=Count('articles', filter=Q(articles__status='published'))
        ).order_by('-article_count')[:6]
        
        # Today's date for news section
        context['today_date'] = timezone.now()
        
        
        # ========== ANIME SECTION (Latest Anime with Episodes) ==========
        # Try featured first, fallback to latest if no featured
        featured_anime = Anime.objects.filter(
            is_active=True,
            is_featured=True
        ).prefetch_related(
            Prefetch(
                'episodes',
                queryset=Episode.objects.filter(is_active=True).order_by('-episode_number')[:5],
                to_attr='latest_episodes_list'
            )
        ).select_related('category').prefetch_related('genres').order_by('-created_at')[:3]
        
        # If no featured anime, get latest ones
        if not featured_anime.exists():
            featured_anime = Anime.objects.filter(
                is_active=True
            ).prefetch_related(
                Prefetch(
                    'episodes',
                    queryset=Episode.objects.filter(is_active=True).order_by('-episode_number')[:5],
                    to_attr='latest_episodes_list'
                )
            ).select_related('category').prefetch_related('genres').order_by('-created_at')[:3]
        
        context['featured_anime'] = featured_anime
        
        context['trending_anime'] = Anime.objects.filter(
            is_active=True,
            is_trending=True
        ).order_by('-views')[:12]
        
        # Fallback to latest if no trending
        if not context['trending_anime'].exists():
            context['trending_anime'] = Anime.objects.filter(
                is_active=True
            ).order_by('-created_at')[:12]
        
        context['latest_episodes'] = Episode.objects.filter(
            is_active=True,
            anime__is_active=True
        ).select_related('anime', 'anime__category').order_by('-created_at')[:12]
        
        
        # ========== MANGA SECTION (Latest Manga with Chapters) ==========
        # Try featured first, fallback to latest if no featured
        featured_manga = Manga.objects.filter(
            is_active=True,
            is_featured=True
        ).prefetch_related(
            Prefetch(
                'chapters',
                queryset=Chapter.objects.filter(is_active=True).order_by('-chapter_number')[:5],
                to_attr='latest_chapters_list'
            )
        ).select_related('category').prefetch_related('genres').order_by('-created_at')[:3]
        
        # If no featured manga, get latest ones
        if not featured_manga.exists():
            featured_manga = Manga.objects.filter(
                is_active=True
            ).prefetch_related(
                Prefetch(
                    'chapters',
                    queryset=Chapter.objects.filter(is_active=True).order_by('-chapter_number')[:5],
                    to_attr='latest_chapters_list'
                )
            ).select_related('category').prefetch_related('genres').order_by('-created_at')[:3]
        
        context['featured_manga'] = featured_manga
        
        context['trending_manga'] = Manga.objects.filter(
            is_active=True,
            is_trending=True
        ).order_by('-views')[:12]
        
        # Fallback to latest if no trending
        if not context['trending_manga'].exists():
            context['trending_manga'] = Manga.objects.filter(
                is_active=True
            ).order_by('-created_at')[:12]
        
        context['latest_chapters'] = Chapter.objects.filter(
            is_active=True,
            manga__is_active=True
        ).select_related('manga', 'manga__category').order_by('-created_at')[:12]
        
        
        # ========== APK SECTION ==========
        context['featured_apks'] = APK.objects.filter(
            is_active=True,
            featured=True
        ).prefetch_related('categories', 'screenshots').order_by('-created_at')[:12]
        
        # Fallback if no featured APKs
        if not context['featured_apks'].exists():
            context['featured_apks'] = APK.objects.filter(
                is_active=True
            ).prefetch_related('categories', 'screenshots').order_by('-created_at')[:24]
        
        context['latest_games'] = APK.objects.filter(
            is_active=True,
            apk_type='game'
        ).order_by('-created_at')[:24]
        
        context['latest_apps'] = APK.objects.filter(
            is_active=True,
            apk_type='app'
        ).order_by('-created_at')[:12]
        
        context['apk_categories'] = APKCategory.objects.all()[:12]
        
        
        # ========== PC GAMES SECTION ==========
        # Get latest PC games with proper prefetch
        context['latest_pc_games'] = PCGame.objects.filter(
            is_active=True
        ).prefetch_related('categories', 'tags', 'screenshots').order_by('-post_date')[:12]
        
        # Get featured PC games (new or updated status)
        context['featured_pc_games'] = PCGame.objects.filter(
            is_active=True,
            status__in=['new', 'updated']
        ).prefetch_related('categories', 'tags', 'screenshots').order_by('-post_date')[:6]
        
        # Fallback if no featured PC games
        if not context['featured_pc_games'].exists():
            context['featured_pc_games'] = context['latest_pc_games'][:6]
        
        
        # ========== STATS FOR HERO SECTION ==========
        context['total_movies'] = Movie.objects.count()
        context['total_anime'] = Anime.objects.filter(is_active=True).count()
        context['total_manga'] = Manga.objects.filter(is_active=True).count()
        context['total_news'] = NewsArticle.objects.filter(status='published').count()
        context['total_apks'] = APK.objects.filter(is_active=True).count()
        context['total_pc_games'] = PCGame.objects.filter(is_active=True).count()
        
        return context