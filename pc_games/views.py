# views.py
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, Count
from .models import Game, Category, Tag, DownloadMirror
from django.views.decorators.cache import cache_page


@cache_page(60 * 60 * 2)  # 2 hours
def game_list(request):
    """List all games with filtering and pagination"""
    games = Game.objects.filter(is_active=True).prefetch_related(
        'categories', 'tags', 'screenshots'
    )
    
    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        games = games.filter(
            Q(title__icontains=search_query) |
            Q(full_description__icontains=search_query)
        )
    
    # Category filter
    category_slug = request.GET.get('category')
    if category_slug:
        games = games.filter(categories__slug=category_slug)
    
    # Tag filter
    tag_slug = request.GET.get('tag')
    if tag_slug:
        games = games.filter(tags__slug=tag_slug)
    
    # Status filter
    status = request.GET.get('status')
    if status in ['new', 'updated']:
        games = games.filter(status=status)
    
    # Sorting
    sort_by = request.GET.get('sort', '-post_date')
    games = games.order_by(sort_by)
    
    # Pagination
    paginator = Paginator(games, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get all categories and tags for filters
    categories = Category.objects.annotate(game_count=Count('games')).filter(game_count__gt=0)
    tags = Tag.objects.annotate(game_count=Count('games')).filter(game_count__gt=0)
    
    context = {
        'page_obj': page_obj,
        'categories': categories,
        'tags': tags,
        'search_query': search_query,
        'current_category': category_slug,
        'current_tag': tag_slug,
        'current_status': status,
    }
    
    return render(request, 'pc_games/game_list.html', context)


def game_detail(request, slug):
    """Display detailed game information"""
    game = get_object_or_404(
        Game.objects.prefetch_related(
            'categories', 'tags', 'screenshots', 
            'download_mirrors', 'updates'
        ),
        slug=slug,
        is_active=True
    )
    
    # Group download mirrors by type
    direct_mirrors = game.download_mirrors.filter(
        mirror_type='direct', is_active=True
    ).order_by('order')
    
    torrent_mirrors = game.download_mirrors.filter(
        mirror_type='torrent', is_active=True
    ).order_by('order')
    
    context = {
        'game': game,
        'direct_mirrors': direct_mirrors,
        'torrent_mirrors': torrent_mirrors,
        'related_games': Game.objects.filter(
            categories__in=game.categories.all()
        ).exclude(id=game.id)[:6]
    }
    
    return render(request, 'pc_games/game_detail.html', context)



@cache_page(60 * 60 * 2)  # 2 hours
def category_list(request):
    """List all categories"""
    categories = Category.objects.annotate(
        game_count=Count('games', filter=Q(games__is_active=True))
    ).filter(game_count__gt=0).order_by('-game_count')
    
    context = {'categories': categories}
    return render(request, 'pc_games/category_list.html', context)


def latest_games(request):
    """Show latest game repacks"""
    latest = Game.objects.filter(
        is_active=True
    ).order_by('-post_date')[:20]
    
    context = {'games': latest}
    return render(request, 'pc_games/latest.html', context)



@cache_page(60 * 15)  # 15 mins
def search_games(request):
    """Advanced search functionality"""
    query = request.GET.get('q', '')
    games = Game.objects.filter(is_active=True)
    
    if query:
        games = games.filter(
            Q(title__icontains=query) |
            Q(full_description__icontains=query) |
            Q(companies__icontains=query)
        )
    
    paginator = Paginator(games, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    context = {
        'page_obj': page_obj,
        'query': query,
    }
    
    return render(request, 'pc_games/search.html', context)