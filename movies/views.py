# movies/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from .models import Movie, Category, Comment
from .forms import MovieForm, CommentForm, DownloadLinkFormSet
from django.db.models import Q, Prefetch
from django.templatetags.static import static
import random
from django.http import JsonResponse
from django.views.decorators.cache import cache_page
from django.http import HttpResponse
from django.views.generic import UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.conf import settings
from django.http import Http404
from django.forms import modelformset_factory
from .models import DownloadLink
from django.core.cache import cache
from django.db.models import F

# Add these imports at the top of views.py
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

# Cache key constants
SIDEBAR_CATEGORIES_CACHE_KEY = 'sidebar_categories_v2'
CACHE_VERSION = 1

def get_sidebar_categories():
    """
    Cached function to get sidebar categories - reduces repeated database queries
    """
    categories = cache.get(SIDEBAR_CATEGORIES_CACHE_KEY, version=CACHE_VERSION)
    if not categories:
        target_categories = [
            'Nollywood movies',
            'Korean drama', 
            'Hollywood movies',
            'Bollywood movies'
        ]
        
        categories_qs = Category.objects.filter(
            name__in=target_categories
        ).prefetch_related(
            Prefetch(
                'movies',
                queryset=Movie.objects.select_related().only(
                    'id', 'title', 'image_url', 'created_at'
                ).order_by('-created_at')[:12],
                to_attr='latest_movies'
            )
        )
        
        
        # Order categories as specified
        category_order = {name: i for i, name in enumerate(target_categories)}
        categories_list = [cat for cat in categories_qs if cat.latest_movies]
        categories_list.sort(key=lambda cat: category_order.get(cat.name, 999))
        
        # Cache for 4 hours
        cache.set(SIDEBAR_CATEGORIES_CACHE_KEY, categories_list, 60 * 60 * 4, version=CACHE_VERSION)
        categories = categories_list
    
    return categories

def invalidate_sidebar_cache():
    """
    Call this when adding/updating movies to refresh sidebar cache
    """
    cache.delete(SIDEBAR_CATEGORIES_CACHE_KEY, version=CACHE_VERSION)

def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Sitemap: https://AlphaGL.store/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")

def custom_404_view(request, exception):
    """
    Custom 404 view that shows only specific categories
    """
    context = {
        'categories': get_sidebar_categories(),
    }
    
    return render(request, 'movies/404.html', context, status=404)

def ping_view(request):
    return JsonResponse({"status": "OK"})

# @method_decorator(cache_page(60 * 60 * 4), name='dispatch')  # cache 4h
class HomeView(ListView):
    model = Movie
    template_name = 'movies/home.html'
    context_object_name = 'movies'
    paginate_by = 12

    def get_queryset(self):
        # only standalone movies (no title_b)
        return (
            Movie.objects
                 .only('id', 'title', 'image_url', 'created_at', 'title_b')
                 .filter(Q(title_b__isnull=True) | Q(title_b=''))
                 .order_by('-created_at')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 0. Blockbusters (flagged in admin)
        block_qs = (
            Movie.objects
                 .only('id', 'title', 'image_url', 'created_at')
                 .filter(is_blockbuster=True)
                 .order_by('-created_at')
        )
        context['blockbusters'] = block_qs[:12]  # first 12

        # 1. Trending Now (all‑time most viewed)
        context['trending'] = (
            Movie.objects
                 .only('id', 'title', 'image_url', 'views', 'created_at')
                 .filter(views__gt=0)
                 .order_by('-views', '-created_at')[:12]  # top 6
        )

        # 2. Sidebar categories
        context['categories'] = get_sidebar_categories()

        # 3. New episodes (non-completed series)
        new_eps = (
            Movie.objects
                 .only('id', 'title', 'title_b', 'image_url', 'title_b_updated_at')
                 .filter(
                     Q(title_b__isnull=False), ~Q(title_b=''), Q(completed=False)
                 )
                 .order_by('-title_b_updated_at')
        )
        context['new_episodes'] = Paginator(new_eps, 12).get_page(
            self.request.GET.get('new_page', 1)
        )

        # 4. Completed series
        comp_ser = (
            Movie.objects
                 .only('id', 'title', 'title_b', 'image_url', 'title_b_updated_at')
                 .filter(
                     Q(title_b__isnull=False), ~Q(title_b=''), Q(completed=True)
                 )
                 .order_by('-title_b_updated_at')
        )
        context['completed_series'] = Paginator(comp_ser, 12).get_page(
            self.request.GET.get('completed_page', 1)
        )

        return context


@method_decorator(cache_page(60 * 60 * 4), name='dispatch')  # 4 hours instead of 24
class CategoryMoviesView(ListView):
    model = Movie
    template_name = 'movies/movie_list.html'
    context_object_name = 'movies'
    paginate_by = 12

    def get_queryset(self):
        self.category = get_object_or_404(Category, id=self.kwargs['cat_id'])
        # Show all movies in this category, newest first - optimized query
        return Movie.objects.select_related().only(
            'id', 'title', 'image_url', 'created_at', 'description'
        ).filter(categories=self.category).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = self.category
        
        # Use cached sidebar categories
        context['categories'] = get_sidebar_categories()
        return context


class MovieDetailView(DetailView):
    model = Movie
    template_name = 'movies/movie_detail.html'

    def get_queryset(self):
        # Optimize the detail query with prefetch_related for likes/watchlists
        return Movie.objects.prefetch_related(
            'liked_by', 'watchlisted_by', 'categories', 'comments__user'
        )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset=queryset)

        # ✅ Increment views count
        Movie.objects.filter(pk=obj.pk).update(views=F('views') + 1)
        obj.refresh_from_db(fields=['views'])  # Refresh the object so views count updates

        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        movie = self.get_object()
        request = self.request
        user = request.user

        # Like/watchlist status
        liked_users = set(movie.liked_by.all())
        watchlisted_users = set(movie.watchlisted_by.all())
        
        context['is_liked'] = user.is_authenticated and user in liked_users
        context['is_watchlisted'] = user.is_authenticated and user in watchlisted_users
        
        # Updated comments query - only top-level comments with replies prefetched
        context['comments'] = movie.comments.filter(
            parent__isnull=True
        ).select_related('user').prefetch_related(
            'replies__user'
        ).order_by('-created_at')
        
        context['comment_form'] = CommentForm()

        # Related movies
        related_movies = Movie.objects.select_related().only(
            'id', 'title', 'image_url', 'created_at'
        ).filter(
            categories__in=movie.categories.all()
        ).exclude(id=movie.id).distinct().order_by('?')[:12]
        
        context['related_movies'] = related_movies

        # Cached sidebar
        context['categories'] = get_sidebar_categories()

        # Structured data
        context['full_image_url'] = request.build_absolute_uri(movie.image_url)
        context['full_video_url'] = request.build_absolute_uri(movie.video_url)
        context['logo_url'] = request.build_absolute_uri(static('img/logo.png'))

        return context

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        movie = self.get_object()
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.movie = movie
            comment.user = request.user
            comment.save()
            messages.success(request, "Comment added.")

        return redirect(movie.get_absolute_url())
@login_required
def toggle_like(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    user = request.user
    if user in movie.liked_by.all():
        movie.liked_by.remove(user)
    else:
        movie.liked_by.add(user)
    return redirect(movie.get_absolute_url())

@login_required
def toggle_watchlist(request, pk):
    movie = get_object_or_404(Movie, pk=pk)
    user = request.user
    if user in movie.watchlisted_by.all():
        movie.watchlisted_by.remove(user)
    else:
        movie.watchlisted_by.add(user)
    return redirect(movie.get_absolute_url())

@method_decorator(cache_page(60 * 15), name='dispatch')  # 15 minutes for search
class SearchResultsView(ListView):
    model = Movie
    template_name = 'movies/search_results.html'
    context_object_name = 'movies'
    paginate_by = 12

    def get_queryset(self):
        query = self.request.GET.get('q', '').strip()
        if not query:
            return Movie.objects.none()

        # Create cache key for search results
        search_cache_key = f'search_{hash(query.lower())}'
        cached_results = cache.get(search_cache_key)
        
        if cached_results is not None:
            return cached_results

        # Optimize query with only necessary fields
        base_qs = Movie.objects.select_related().only(
            'id', 'title', 'description', 'image_url', 'created_at'
        )

        # 1) Exact‐phrase match: title__icontains OR description__icontains
        exact_q = Q(title__icontains=query) | Q(description__icontains=query)
        exact_matches = list(base_qs.filter(exact_q).distinct())

        if exact_matches:
            # Cache for 30 minutes
            cache.set(search_cache_key, exact_matches, 60 * 30)
            return exact_matches

        # 2) Keyword fallback
        keywords = query.split()
        fallback_q = Q()
        for kw in keywords:
            fallback_q |= Q(title__icontains=kw) | Q(description__icontains=kw)

        keyword_results = list(base_qs.filter(fallback_q).distinct())

        # Rank by keyword matches
        def count_matches(movie):
            text = f"{movie.title} {movie.description}".lower()
            return sum(kw.lower() in text for kw in keywords)

        sorted_results = sorted(keyword_results, key=count_matches, reverse=True)
        
        # Cache for 30 minutes
        cache.set(search_cache_key, sorted_results, 60 * 30)
        return sorted_results

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        
        # Use cached sidebar categories
        context['categories'] = get_sidebar_categories()
        return context
    
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
import json

@csrf_exempt
def pwa_install_tracking(request):
    """Track PWA installations"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            PWAInstallation.objects.create(
                user=request.user if request.user.is_authenticated else None,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                platform=data.get('platform', 'unknown')
            )
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid method'})

@login_required
def sync_offline_actions(request):
    """Sync offline actions when user comes back online"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            actions = data.get('actions', [])
            
            for action_data in actions:
                OfflineAction.objects.create(
                    user=request.user,
                    action_type=action_data.get('type'),
                    action_data=action_data.get('data', {}),
                    synced=True
                )
            
            return JsonResponse({'success': True, 'synced': len(actions)})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid method'})

# Add these view functions to your views.py

@require_POST
def add_comment(request, pk):
    """
    Add a comment to a movie (AJAX endpoint)
    Supports both authenticated and anonymous users
    """
    movie = get_object_or_404(Movie, pk=pk)
    
    # Check if AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    content = request.POST.get('content', '').strip()
    
    if not content:
        if is_ajax:
            return JsonResponse({
                'success': False,
                'message': 'Comment cannot be empty'
            })
        messages.error(request, 'Comment cannot be empty')
        return redirect(movie.get_absolute_url())
    
    # Create comment
    comment = Comment()
    comment.movie = movie
    comment.content = content
    
    if request.user.is_authenticated:
        comment.user = request.user
    else:
        guest_name = request.POST.get('name', '').strip()
        if not guest_name:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please provide your name'
                })
            messages.error(request, 'Please provide your name')
            return redirect(movie.get_absolute_url())
        comment.guest_name = guest_name
    
    comment.save()
    
    if is_ajax:
        # Render the comment HTML
        html = render_to_string('movies/components/comment_item.html', {
            'comment': comment,
            'movie': movie,
            'user': request.user
        })
        
        return JsonResponse({
            'success': True,
            'message': 'Comment posted successfully!',
            'html': html,
            'comment_id': comment.id
        })
    
    messages.success(request, 'Comment posted successfully!')
    return redirect(movie.get_absolute_url() + '#comments-section')


@require_POST
def add_reply(request, movie_pk, comment_pk):
    """
    Add a reply to a comment (AJAX endpoint)
    """
    movie = get_object_or_404(Movie, pk=movie_pk)
    parent_comment = get_object_or_404(Comment, pk=comment_pk)
    
    # Check if AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    content = request.POST.get('content', '').strip()
    
    if not content:
        if is_ajax:
            return JsonResponse({
                'success': False,
                'message': 'Reply cannot be empty'
            })
        messages.error(request, 'Reply cannot be empty')
        return redirect(movie.get_absolute_url())
    
    # Create reply
    reply = Comment()
    reply.movie = movie
    reply.parent = parent_comment
    reply.content = content
    
    if request.user.is_authenticated:
        reply.user = request.user
    else:
        guest_name = request.POST.get('name', '').strip()
        if not guest_name:
            if is_ajax:
                return JsonResponse({
                    'success': False,
                    'message': 'Please provide your name'
                })
            messages.error(request, 'Please provide your name')
            return redirect(movie.get_absolute_url())
        reply.guest_name = guest_name
    
    reply.save()
    
    if is_ajax:
        # Render the reply HTML
        html = render_to_string('movies/components/comment_item.html', {
            'comment': reply,
            'movie': movie,
            'user': request.user
        })
        
        return JsonResponse({
            'success': True,
            'message': 'Reply posted successfully!',
            'html': html,
            'comment_id': reply.id
        })
    
    messages.success(request, 'Reply posted successfully!')
    return redirect(movie.get_absolute_url() + '#comments-section')


@require_POST
def delete_comment(request, pk):
    """
    Delete a comment (only owner or staff)
    """
    comment = get_object_or_404(Comment, pk=pk)
    movie = comment.movie
    
    # Check permissions
    if request.user.is_authenticated and (request.user == comment.user or request.user.is_staff):
        comment.delete()
        
        # Check if AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': 'Comment deleted successfully'
            })
        
        messages.success(request, 'Comment deleted successfully')
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': 'You do not have permission to delete this comment'
            })
        
        messages.error(request, 'You do not have permission to delete this comment')
    
    return redirect(movie.get_absolute_url() + '#comments-section')
