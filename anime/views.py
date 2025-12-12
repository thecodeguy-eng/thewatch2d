from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, TemplateView, View
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg, F
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.core.management import call_command
from django.utils import timezone
import json
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
import requests
from bs4 import BeautifulSoup
import cloudscraper
import re
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page

from .models import Anime, Episode, AnimeCategory, AnimeGenre, DownloadLink, Comment, CommentReply

logger = logging.getLogger(__name__)



# Add this helper function
def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@method_decorator(cache_page(60 * 60 * 4), name='dispatch')  # cache 4h
class AnimeListView(ListView):
    model = Anime
    template_name = 'anime/list.html'
    context_object_name = 'animes'
    paginate_by = 24
    
    def get_queryset(self):
        queryset = Anime.objects.filter(is_active=True).select_related('category').prefetch_related('genres')
        
        # Filter by category
        category_slug = self.request.GET.get('category')
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)
        
        # Filter by genre
        genre_slug = self.request.GET.get('genre')
        if genre_slug:
            queryset = queryset.filter(genres__slug=genre_slug)
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by year
        year = self.request.GET.get('year')
        if year:
            queryset = queryset.filter(year=year)
        
        # Order by
        order_by = self.request.GET.get('order_by', '-created_at')
        if order_by in ['-created_at', '-views', '-likes', '-rating', 'title']:
            queryset = queryset.order_by(order_by)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'categories': AnimeCategory.objects.filter(is_active=True),
            'genres': AnimeGenre.objects.all()[:20],  # Limit genres
            'status_choices': Anime.STATUS_CHOICES,
            'current_filters': {
                'category': self.request.GET.get('category', ''),
                'genre': self.request.GET.get('genre', ''),
                'status': self.request.GET.get('status', ''),
                'year': self.request.GET.get('year', ''),
                'order_by': self.request.GET.get('order_by', '-created_at'),
            }
        })
        return context
    
@method_decorator(cache_page(60 * 15), name='dispatch')  # 15 minutes for search
class AnimeSearchView(ListView):
    model = Anime
    template_name = 'anime/search_results.html'
    context_object_name = 'animes'
    paginate_by = 24
    
    def get_queryset(self):
        query = self.request.GET.get('q', '').strip()
        if not query:
            return Anime.objects.none()
        
        return Anime.objects.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(studio__icontains=query) |
            Q(genres__name__icontains=query)
        ).filter(is_active=True).distinct().select_related('category').prefetch_related('genres')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        return context


@method_decorator(cache_page(60 * 60 * 4), name='dispatch')  # 4 hours instead of 24
class TrendingAnimeView(ListView):
    model = Anime
    template_name = 'anime/trending.html'
    context_object_name = 'animes'
    paginate_by = 24
    
    def get_queryset(self):
        return Anime.objects.filter(
            is_active=True, is_trending=True
        ).select_related('category').prefetch_related('genres').order_by('-views', '-likes')


@method_decorator(cache_page(60 * 60 * 4), name='dispatch')  # 4 hours instead of 24
class FeaturedAnimeView(ListView):
    model = Anime
    template_name = 'anime/featured.html'
    context_object_name = 'animes'
    paginate_by = 24
    
    def get_queryset(self):
        return Anime.objects.filter(
            is_active=True, is_featured=True
        ).select_related('category').prefetch_related('genres').order_by('-created_at')

@method_decorator(cache_page(60 * 60 * 4), name='dispatch')  # 4 hours instead of 24
class RecentlyAddedAnimeView(ListView):
    model = Anime
    template_name = 'anime/recently_added.html'
    context_object_name = 'animes'
    paginate_by = 24
    
    def get_queryset(self):
        return Anime.objects.filter(
            is_active=True
        ).select_related('category').prefetch_related('genres').order_by('-created_at')

@method_decorator(cache_page(60 * 60 * 4), name='dispatch')  # 4 hours instead of 24
class CategoryListView(ListView):
    model = AnimeCategory
    template_name = 'anime/categories.html'
    context_object_name = 'categories'
    
    def get_queryset(self):
        return AnimeCategory.objects.filter(is_active=True).annotate(
            anime_count=Count('anime', filter=Q(anime__is_active=True))
        ).order_by('name')

@method_decorator(cache_page(60 * 60 * 2), name='dispatch')  # 2 hours instead of 24
class CategoryDetailView(DetailView):
    model = AnimeCategory
    template_name = 'anime/category_detail.html'
    context_object_name = 'category'
    slug_field = 'slug'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        animes = Anime.objects.filter(
            category=self.object, is_active=True
        ).select_related('category').prefetch_related('genres').order_by('-created_at')
        
        paginator = Paginator(animes, 24)
        page_number = self.request.GET.get('page')
        context['animes'] = paginator.get_page(page_number)
        return context

@method_decorator(cache_page(60 * 60 * 2), name='dispatch')  # 2 hours instead of 24
# Add to your existing EnhancedAnimeDetailView
class EnhancedAnimeDetailView(DetailView):
    model = Anime
    template_name = 'anime/detail.html'
    context_object_name = 'anime'
    slug_field = 'slug'
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        obj.increment_views()
        
        if not obj.poster_url:
            self.try_fetch_missing_image(obj)
        
        return obj
    
    def try_fetch_missing_image(self, anime):
        """Try to fetch missing anime image in background"""
        try:
            image_fetcher = AnimeImageFetcher()
            images = image_fetcher.search_anime_images(anime.title)
            
            if images:
                anime.poster_url = images[0]['url']
                anime.save(update_fields=['poster_url'])
                print(f"Auto-updated image for {anime.title}")
                
        except Exception as e:
            print(f"Error auto-fetching image for {anime.title}: {e}")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get episodes with download links
        episodes = Episode.objects.filter(
            anime=self.object, is_active=True
        ).prefetch_related('download_links').order_by('-episode_number')[:12]
        
        # Related anime
        related_animes = self.object.get_related_anime(6)
        
        # Get approved comments
        comments = Comment.objects.filter(
            anime=self.object,
            is_approved=True
        ).prefetch_related('replies').order_by('-created_at')[:20]
        
        context.update({
            'episodes': episodes,
            'related_animes': related_animes,
            'total_episodes': Episode.objects.filter(anime=self.object, is_active=True).count(),
            'comments': comments,
            'comment_count': comments.count(),
        })
        return context
  

class AnimeEpisodesView(DetailView):
    model = Anime
    template_name = 'anime/episodes.html'
    context_object_name = 'anime'
    slug_field = 'slug'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        episodes = Episode.objects.filter(
            anime=self.object, is_active=True
        ).order_by('episode_number')
        
        paginator = Paginator(episodes, 50)
        page_number = self.request.GET.get('page')
        context['episodes'] = paginator.get_page(page_number)
        return context

# Update your existing EpisodeDetailView
class EpisodeDetailView(DetailView):
    model = Episode
    template_name = 'anime/episode_detail.html'
    context_object_name = 'episode'
    
    def get_object(self, queryset=None):
        anime = get_object_or_404(Anime, slug=self.kwargs['anime_slug'])
        episode = get_object_or_404(
            Episode, 
            anime=anime, 
            episode_number=self.kwargs['episode_number'],
            is_active=True
        )
        episode.increment_views()
        return episode
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Navigation episodes
        prev_episode = Episode.objects.filter(
            anime=self.object.anime,
            episode_number__lt=self.object.episode_number,
            is_active=True
        ).order_by('-episode_number').first()
        
        next_episode = Episode.objects.filter(
            anime=self.object.anime,
            episode_number__gt=self.object.episode_number,
            is_active=True
        ).order_by('episode_number').first()
        
        # All episodes for playlist
        episodes = Episode.objects.filter(
            anime=self.object.anime, is_active=True
        ).order_by('episode_number')
        
        # Get download links
        download_links = DownloadLink.objects.filter(
            episode=self.object, is_active=True
        ).order_by('quality')
        
        # Get approved comments
        comments = Comment.objects.filter(
            episode=self.object,
            is_approved=True
        ).prefetch_related('replies').order_by('-created_at')[:20]
        
        context.update({
            'anime': self.object.anime,
            'prev_episode': prev_episode,
            'next_episode': next_episode,
            'episodes': episodes,
            'download_links': download_links,
            'comments': comments,
            'comment_count': comments.count(),
        })
        return context

class GetDownloadLinksView(View):
    """AJAX view to fetch download links for an episode"""
    
    def get(self, request, episode_id):
        try:
            episode = get_object_or_404(Episode, episode_id=episode_id, is_active=True)
            
            # Get all active download links for this episode
            links = DownloadLink.objects.filter(
                episode=episode,
                is_active=True
            ).order_by('quality')
            
            links_data = [
                {
                    'quality': link.quality,
                    'url': link.url,
                    'file_size': link.file_size,
                    'host_name': link.host_name,
                    'label': link.label or f"{link.quality} - {link.host_name.title()}",
                }
                for link in links
            ]
            
            return JsonResponse({
                'success': True,
                'links': links_data,
                'episode_title': episode.display_title
            })
            
        except Exception as e:
            logger.error(f"Error fetching download links for episode {episode_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to fetch download links. Please try again later.'
            }, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class LikeAnimeView(View):
    """AJAX view to like an anime"""
    
    def post(self, request, anime_id):
        try:
            anime = get_object_or_404(Anime, id=anime_id)
            anime.likes = F('likes') + 1
            anime.save(update_fields=['likes'])
            anime.refresh_from_db()
            
            return JsonResponse({
                'success': True,
                'likes': anime.likes
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

class IncrementViewsView(View):
    """AJAX view to increment anime views"""
    
    def post(self, request, anime_id):
        try:
            anime = get_object_or_404(Anime, id=anime_id)
            anime.increment_views()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

class ManagementDashboardView(TemplateView):
    template_name = 'anime/management.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Recent episodes for quick overview
        recent_episodes = Episode.objects.filter(
            is_active=True
        ).select_related('anime').order_by('-created_at')[:20]
        
        context.update({
            'total_animes': Anime.objects.filter(is_active=True).count(),
            'total_episodes': Episode.objects.filter(is_active=True).count(),
            'trending_animes': Anime.objects.filter(is_trending=True).count(),
            'featured_animes': Anime.objects.filter(is_featured=True).count(),
            'recent_animes': Anime.objects.filter(is_active=True).order_by('-created_at')[:10],
            'recent_episodes': recent_episodes,
        })
        return context

class TriggerScrapeView(View):
    """Trigger anime scraping via web interface"""
    
    def post(self, request):
        try:
            pages = request.POST.get('pages', 3)
            call_command('scrape_chiaanime', pages=int(pages))
            messages.success(request, f'Successfully triggered scraping for {pages} pages!')
        except Exception as e:
            messages.error(request, f'Scraping failed: {str(e)}')
        
        return redirect('anime:management')

# Homepage view to show featured content
class HomeView(TemplateView):
    template_name = 'anime/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Featured content for homepage
        featured_animes = Anime.objects.filter(
            is_active=True, is_featured=True
        ).select_related('category').prefetch_related('genres')[:8]
        
        trending_animes = Anime.objects.filter(
            is_active=True, is_trending=True
        ).select_related('category').prefetch_related('genres')[:8]
        
        recent_animes = Anime.objects.filter(
            is_active=True
        ).select_related('category').prefetch_related('genres').order_by('-created_at')[:12]
        
        # Recent episodes
        recent_episodes = Episode.objects.filter(
            is_active=True
        ).select_related('anime', 'anime__category').order_by('-created_at')[:16]
        
        context.update({
            'featured_animes': featured_animes,
            'trending_animes': trending_animes,
            'recent_animes': recent_animes,
            'recent_episodes': recent_episodes,
        })
        return context
    

class AnimeImageFetcher:
    """Helper class to fetch anime images from various sources"""
    
    def __init__(self):
        self.scraper = cloudscraper.create_scraper()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        }
    
    def search_anime_images(self, anime_title):
        """Search for anime images from multiple sources"""
        images = []
        
        # Method 1: Search on anime database sites
        images.extend(self.search_myanimelist(anime_title))
        images.extend(self.search_anilist(anime_title))
        
        # Method 2: Generic image search (as fallback)
        if not images:
            images.extend(self.search_generic_images(anime_title))
        
        return images[:5]  # Return top 5 results
    
    def search_myanimelist(self, anime_title):
        """Search MyAnimeList for anime images"""
        try:
            # Clean the title for search
            search_query = anime_title.replace(' ', '+')
            search_url = f"https://myanimelist.net/anime.php?q={search_query}"
            
            response = self.scraper.get(search_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            images = []
            
            # Look for anime images in search results
            anime_items = soup.find_all('div', class_='anime-item')
            for item in anime_items:
                img_tag = item.find('img')
                if img_tag:
                    img_src = img_tag.get('src') or img_tag.get('data-src')
                    if img_src and 'cdn.myanimelist.net' in img_src:
                        # Convert thumbnail to larger image
                        img_src = img_src.replace('t.jpg', '.jpg').replace('s.jpg', '.jpg')
                        images.append({
                            'url': img_src,
                            'source': 'MyAnimeList',
                            'title': img_tag.get('alt', anime_title)
                        })
            
            return images[:3]
            
        except Exception as e:
            print(f"Error searching MyAnimeList: {e}")
            return []
    
    def search_anilist(self, anime_title):
        """Search AniList API for anime images"""
        try:
            # AniList GraphQL API
            query = '''
            query ($search: String) {
                Page(page: 1, perPage: 5) {
                    media(search: $search, type: ANIME) {
                        id
                        title {
                            romaji
                            english
                        }
                        coverImage {
                            large
                            medium
                        }
                        bannerImage
                    }
                }
            }
            '''
            
            response = requests.post(
                'https://graphql.anilist.co',
                json={
                    'query': query,
                    'variables': {'search': anime_title}
                },
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                images = []
                
                for media in data.get('data', {}).get('Page', {}).get('media', []):
                    cover_image = media.get('coverImage', {})
                    if cover_image.get('large'):
                        images.append({
                            'url': cover_image['large'],
                            'source': 'AniList',
                            'title': media.get('title', {}).get('romaji', anime_title)
                        })
                    
                    # Also add banner image if available
                    if media.get('bannerImage'):
                        images.append({
                            'url': media['bannerImage'],
                            'source': 'AniList (Banner)',
                            'title': media.get('title', {}).get('romaji', anime_title)
                        })
                
                return images
            
        except Exception as e:
            print(f"Error searching AniList: {e}")
            return []
    
    def search_generic_images(self, anime_title):
        """Fallback generic image search"""
        # This is a placeholder - you could integrate with image APIs
        # For now, we'll return empty to avoid scraping copyrighted content
        return []

# Add this to your existing views.py

@method_decorator(csrf_exempt, name='dispatch')
class UpdateAnimeImageView(View):
    """AJAX view to update anime poster image"""
    
    def post(self, request, anime_id):
        try:
            anime = get_object_or_404(Anime, id=anime_id)
            
            # If anime already has a poster, return it
            if anime.poster_url:
                return JsonResponse({
                    'success': True,
                    'current_image': anime.poster_url
                })
            
            # Search for images
            image_fetcher = AnimeImageFetcher()
            images = image_fetcher.search_anime_images(anime.title)
            
            if images:
                # Use the first (best) result
                best_image = images[0]
                anime.poster_url = best_image['url']
                anime.save()
                
                return JsonResponse({
                    'success': True,
                    'new_image': best_image['url'],
                    'source': best_image['source'],
                    'all_options': images
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'No suitable images found'
                })
                
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
        
class FetchMissingImagesView(View):
    """Management view to fetch missing anime images"""
    
    def post(self, request):
        try:
            # Get animes without poster images
            animes_without_images = Anime.objects.filter(
                is_active=True,
                poster_url__in=['', None]
            )[:10]  # Process 10 at a time to avoid timeouts
            
            image_fetcher = AnimeImageFetcher()
            updated_count = 0
            
            for anime in animes_without_images:
                print(f"Searching images for: {anime.title}")
                images = image_fetcher.search_anime_images(anime.title)
                
                if images:
                    anime.poster_url = images[0]['url']
                    anime.save()
                    updated_count += 1
                    print(f"Updated image for {anime.title}")
                
                # Small delay to be respectful
                time.sleep(1)
            
            messages.success(
                request,
                f'Updated {updated_count} anime images. {len(animes_without_images) - updated_count} still need images.'
            )
            
        except Exception as e:
            messages.error(request, f'Error updating images: {str(e)}')
        
        return redirect('anime:management')
    
class StreamLinkResolverView(View):
    """AJAX view to resolve streaming links in real-time"""
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            url = data.get('url')
            
            if not url:
                return JsonResponse({'success': False, 'error': 'No URL provided'})
            
            # Only resolve fyptt links
            if 'fypttvideos.xyz' not in url:
                return JsonResponse({'success': True, 'resolved_url': url})
            
            # Use the same resolution logic from the scraper
            scraper = cloudscraper.create_scraper()
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://chia-anime.su/",
            }
            
            response = scraper.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for direct video sources
            video_tags = soup.find_all('video')
            for video in video_tags:
                sources = video.find_all('source')
                for source in sources:
                    src = source.get('src')
                    if src:
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            src = 'https://fypttvideos.xyz' + src
                        return JsonResponse({
                            'success': True,
                            'resolved_url': src,
                            'type': 'direct_video'
                        })
            
            # Look for iframe embeds
            iframes = soup.find_all('iframe')
            for iframe in iframes:
                src = iframe.get('src')
                if src and 'player' in src.lower():
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = 'https://fypttvideos.xyz' + src
                    return JsonResponse({
                        'success': True,
                        'resolved_url': src,
                        'type': 'iframe'
                    })
            
            # Look in JavaScript for video URLs
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    js_content = script.string
                    video_patterns = [
                        r'["\']https?://[^"\']*\.(?:mp4|m3u8|mkv)[^"\']*["\']',
                        r'source\s*:\s*["\']([^"\']+)["\']',
                        r'file\s*:\s*["\']([^"\']+)["\']'
                    ]
                    
                    for pattern in video_patterns:
                        matches = re.findall(pattern, js_content, re.IGNORECASE)
                        for match in matches:
                            clean_url = match.strip('\'"')
                            if any(ext in clean_url.lower() for ext in ['.mp4', '.m3u8', '.mkv']):
                                if clean_url.startswith('//'):
                                    clean_url = 'https:' + clean_url
                                elif clean_url.startswith('/'):
                                    clean_url = 'https://fypttvideos.xyz' + clean_url
                                return JsonResponse({
                                    'success': True,
                                    'resolved_url': clean_url,
                                    'type': 'direct_video'
                                })
            
            return JsonResponse({
                'success': False,
                'error': 'Could not resolve stream URL'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
        

    
# New view for submitting comments
@method_decorator(csrf_exempt, name='dispatch')
class SubmitCommentView(View):
    """AJAX view to submit a comment"""
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            
            # Validate required fields
            name = data.get('name', '').strip()
            comment_text = data.get('comment', '').strip()
            content_type = data.get('content_type', 'anime')
            content_id = data.get('content_id')
            
            if not name or len(name) < 2:
                return JsonResponse({
                    'success': False,
                    'error': 'Please provide your name (at least 2 characters)'
                }, status=400)
            
            if not comment_text or len(comment_text) < 3:
                return JsonResponse({
                    'success': False,
                    'error': 'Comment must be at least 3 characters long'
                }, status=400)
            
            if len(comment_text) > 1000:
                return JsonResponse({
                    'success': False,
                    'error': 'Comment is too long (max 1000 characters)'
                }, status=400)
            
            # Basic spam detection
            spam_patterns = [
                r'(https?://\S+){3,}',  # Multiple URLs
                r'(viagra|cialis|casino|porn)',  # Common spam words
            ]
            
            for pattern in spam_patterns:
                if re.search(pattern, comment_text, re.IGNORECASE):
                    return JsonResponse({
                        'success': False,
                        'error': 'Your comment appears to be spam'
                    }, status=400)
            
            # Create comment
            comment = Comment()
            comment.name = name
            comment.email = data.get('email', '').strip()
            comment.comment = comment_text
            comment.content_type = content_type
            comment.ip_address = get_client_ip(request)
            comment.user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
            
            # Link to anime or episode
            if content_type == 'anime':
                anime = get_object_or_404(Anime, id=content_id)
                comment.anime = anime
            elif content_type == 'episode':
                episode = get_object_or_404(Episode, id=content_id)
                comment.episode = episode
            
            comment.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Comment posted successfully!',
                'comment': {
                    'id': comment.id,
                    'name': comment.name,
                    'comment': comment.comment,
                    'time': comment.get_time_since(),
                    'is_recent': comment.is_recent,
                }
            })
            
        except Exception as e:
            logger.error(f"Error submitting comment: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to post comment. Please try again.'
            }, status=500)


# New view for submitting replies
@method_decorator(csrf_exempt, name='dispatch')
class SubmitReplyView(View):
    """AJAX view to submit a reply to a comment"""
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            
            # Validate required fields
            name = data.get('name', '').strip()
            reply_text = data.get('reply', '').strip()
            comment_id = data.get('comment_id')
            
            if not name or len(name) < 2:
                return JsonResponse({
                    'success': False,
                    'error': 'Please provide your name'
                }, status=400)
            
            if not reply_text or len(reply_text) < 3:
                return JsonResponse({
                    'success': False,
                    'error': 'Reply must be at least 3 characters long'
                }, status=400)
            
            if len(reply_text) > 500:
                return JsonResponse({
                    'success': False,
                    'error': 'Reply is too long (max 500 characters)'
                }, status=400)
            
            # Get parent comment
            comment = get_object_or_404(Comment, id=comment_id, is_approved=True)
            
            # Create reply
            reply = CommentReply()
            reply.comment = comment
            reply.name = name
            reply.email = data.get('email', '').strip()
            reply.reply = reply_text
            reply.ip_address = get_client_ip(request)
            reply.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Reply posted successfully!',
                'reply': {
                    'id': reply.id,
                    'name': reply.name,
                    'reply': reply.reply,
                    'time': reply.get_time_since(),
                }
            })
            
        except Exception as e:
            logger.error(f"Error submitting reply: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to post reply. Please try again.'
            }, status=500)