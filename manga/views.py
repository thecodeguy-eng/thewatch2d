from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, TemplateView, View
from django.contrib import messages
from django.http import JsonResponse, Http404, HttpResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg, F
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import cache_page
from django.core.management import call_command
from django.utils import timezone
import json
import logging
from io import BytesIO
import zipfile
import requests
from PIL import Image
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from .models import Manga, Chapter, MangaCategory, MangaGenre, MangaPage, DownloadLink

logger = logging.getLogger(__name__)

class DownloadChapterView(View):
    """Download chapter as PDF or ZIP"""
    
    def get(self, request, chapter_id, format='pdf'):
        try:
            chapter = get_object_or_404(Chapter, chapter_id=chapter_id, is_active=True)
            pages = MangaPage.objects.filter(chapter=chapter).order_by('page_number')
            
            if not pages:
                return JsonResponse({'error': 'No pages found'}, status=404)
            
            if format == 'pdf':
                return self.download_as_pdf(chapter, pages)
            elif format == 'zip':
                return self.download_as_zip(chapter, pages)
            else:
                return JsonResponse({'error': 'Invalid format'}, status=400)
                
        except Exception as e:
            logger.error(f"Download error: {e}")
            return JsonResponse({'error': str(e)}, status=500)
    
    def download_as_pdf(self, chapter, pages):
        """Create PDF file with all pages"""
        buffer = BytesIO()
        
        # Create PDF
        c = canvas.Canvas(buffer, pagesize=A4)
        page_width, page_height = A4
        
        for page in pages:
            try:
                # Fetch image
                response = requests.get(page.image_url, timeout=30)
                if response.status_code == 200:
                    # Open image with PIL
                    img_data = BytesIO(response.content)
                    img = Image.open(img_data)
                    
                    # Get image dimensions
                    img_width, img_height = img.size
                    
                    # Calculate aspect ratio to fit page
                    aspect = img_height / float(img_width)
                    
                    # Fit image to page while maintaining aspect ratio
                    if aspect > (page_height / page_width):
                        # Height is the limiting factor
                        display_height = page_height - 40  # Leave margin
                        display_width = display_height / aspect
                    else:
                        # Width is the limiting factor
                        display_width = page_width - 40  # Leave margin
                        display_height = display_width * aspect
                    
                    # Center image on page
                    x = (page_width - display_width) / 2
                    y = (page_height - display_height) / 2
                    
                    # Draw image on PDF
                    img_data.seek(0)  # Reset buffer position
                    c.drawImage(ImageReader(img_data), x, y, 
                              width=display_width, height=display_height)
                    
                    # Add page number at bottom
                    c.setFont("Helvetica", 10)
                    c.drawCentredString(page_width / 2, 20, 
                                      f"Page {page.page_number} of {pages.count()}")
                    
                    # Move to next page
                    c.showPage()
                    
            except Exception as e:
                logger.error(f"Error processing page {page.page_number}: {e}")
                continue
        
        # Save PDF
        c.save()
        buffer.seek(0)
        
        # Prepare response
        filename = f"{chapter.manga.slug}-chapter-{chapter.chapter_number}.pdf"
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
    
    def download_as_zip(self, chapter, pages):
        """Create ZIP file with all pages"""
        buffer = BytesIO()
        
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for page in pages:
                try:
                    # Fetch image
                    response = requests.get(page.image_url, timeout=30)
                    if response.status_code == 200:
                        filename = f"page-{str(page.page_number).zfill(3)}.jpg"
                        zip_file.writestr(filename, response.content)
                except Exception as e:
                    logger.error(f"Error downloading page {page.page_number}: {e}")
                    continue
        
        buffer.seek(0)
        filename = f"{chapter.manga.slug}-chapter-{chapter.chapter_number}.zip"
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response

# @method_decorator(cache_page(60 * 60 * 4), name='dispatch')  # cache 4h
class MangaListView(ListView):
    model = Manga
    template_name = 'manga/list.html'
    context_object_name = 'mangas'
    paginate_by = 24
    
    def get_queryset(self):
        queryset = Manga.objects.filter(is_active=True).select_related('category').prefetch_related('genres')
        
        # Filter by category
        category_slug = self.request.GET.get('category')
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)
        
        # Filter by genre
        genre_slug = self.request.GET.get('genre')
        if genre_slug:
            queryset = queryset.filter(genres__slug=genre_slug)
        
        # Filter by type
        manga_type = self.request.GET.get('type')
        if manga_type:
            queryset = queryset.filter(manga_type=manga_type)
        
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
            'categories': MangaCategory.objects.filter(is_active=True),
            'genres': MangaGenre.objects.all()[:20],
            'type_choices': Manga.TYPE_CHOICES,
            'status_choices': Manga.STATUS_CHOICES,
            'current_filters': {
                'category': self.request.GET.get('category', ''),
                'genre': self.request.GET.get('genre', ''),
                'type': self.request.GET.get('type', ''),
                'status': self.request.GET.get('status', ''),
                'year': self.request.GET.get('year', ''),
                'order_by': self.request.GET.get('order_by', '-created_at'),
            }
        })
        return context


# @method_decorator(cache_page(60 * 15), name='dispatch')  # 15 minutes for search
class MangaSearchView(ListView):
    model = Manga
    template_name = 'manga/search_results.html'
    context_object_name = 'mangas'
    paginate_by = 24
    
    def get_queryset(self):
        query = self.request.GET.get('q', '').strip()
        if not query:
            return Manga.objects.none()
        
        return Manga.objects.filter(
            Q(title__icontains=query) |
            Q(alternative_titles__icontains=query) |
            Q(description__icontains=query) |
            Q(author__icontains=query) |
            Q(artist__icontains=query) |
            Q(genres__name__icontains=query)
        ).filter(is_active=True).distinct().select_related('category').prefetch_related('genres')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        return context


# @method_decorator(cache_page(60 * 60 * 4), name='dispatch')
class TrendingMangaView(ListView):
    model = Manga
    template_name = 'manga/trending.html'
    context_object_name = 'mangas'
    paginate_by = 24
    
    def get_queryset(self):
        return Manga.objects.filter(
            is_active=True, is_trending=True
        ).select_related('category').prefetch_related('genres').order_by('-views', '-likes')


# @method_decorator(cache_page(60 * 60 * 4), name='dispatch')
class FeaturedMangaView(ListView):
    model = Manga
    template_name = 'manga/featured.html'
    context_object_name = 'mangas'
    paginate_by = 24
    
    def get_queryset(self):
        return Manga.objects.filter(
            is_active=True, is_featured=True
        ).select_related('category').prefetch_related('genres').order_by('-created_at')


# @method_decorator(cache_page(60 * 60 * 2), name='dispatch')
class MangaDetailView(DetailView):
    model = Manga
    template_name = 'manga/detail.html'
    context_object_name = 'manga'
    slug_field = 'slug'
    
    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        obj.increment_views()
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get chapters with pages count
        chapters = Chapter.objects.filter(
            manga=self.object, is_active=True
        ).order_by('-chapter_number')[:20]
        
        # Related manga
        related_mangas = self.object.get_related_manga(6)
        
        context.update({
            'chapters': chapters,
            'related_mangas': related_mangas,
            'total_chapters': Chapter.objects.filter(manga=self.object, is_active=True).count(),
        })
        return context


class MangaChaptersView(DetailView):
    model = Manga
    template_name = 'manga/chapters.html'
    context_object_name = 'manga'
    slug_field = 'slug'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        chapters = Chapter.objects.filter(
            manga=self.object, is_active=True
        ).order_by('-chapter_number')
        
        paginator = Paginator(chapters, 100)
        page_number = self.request.GET.get('page')
        context['chapters'] = paginator.get_page(page_number)
        return context


class ChapterReaderView(DetailView):
    """Main reader view for reading manga chapters"""
    model = Chapter
    template_name = 'manga/reader.html'
    context_object_name = 'chapter'
    
    def get_object(self, queryset=None):
        manga = get_object_or_404(Manga, slug=self.kwargs['manga_slug'])
        chapter_number = self.kwargs['chapter_number'].replace('-', '.')
        chapter = get_object_or_404(
            Chapter, 
            manga=manga, 
            chapter_number=float(chapter_number),
            is_active=True
        )
        # Increment views
        chapter.increment_views()
        return chapter
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get all pages for this chapter
        pages = MangaPage.objects.filter(
            chapter=self.object
        ).order_by('page_number')
        
        # Navigation chapters
        prev_chapter = self.object.get_previous_chapter()
        next_chapter = self.object.get_next_chapter()
        
        # All chapters for quick navigation
        all_chapters = Chapter.objects.filter(
            manga=self.object.manga, is_active=True
        ).order_by('chapter_number')
        
        # Download links
        download_links = DownloadLink.objects.filter(
            chapter=self.object, is_active=True
        ).order_by('quality', 'format')
        
        context.update({
            'manga': self.object.manga,
            'pages': pages,
            'prev_chapter': prev_chapter,
            'next_chapter': next_chapter,
            'all_chapters': all_chapters,
            'download_links': download_links,
        })
        return context


class GetChapterPagesView(View):
    """AJAX view to fetch chapter pages (for infinite scroll)"""
    
    def get(self, request, chapter_id):
        try:
            chapter = get_object_or_404(Chapter, chapter_id=chapter_id, is_active=True)
            
            pages = MangaPage.objects.filter(
                chapter=chapter
            ).order_by('page_number')
            
            pages_data = [
                {
                    'page_number': page.page_number,
                    'image_url': page.image_url,
                    'width': page.width,
                    'height': page.height,
                }
                for page in pages
            ]
            
            return JsonResponse({
                'success': True,
                'pages': pages_data,
                'chapter_title': chapter.display_title
            })
            
        except Exception as e:
            logger.error(f"Error fetching pages for chapter {chapter_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to fetch pages. Please try again later.'
            }, status=500)


class GetDownloadLinksView(View):
    """AJAX view to fetch download links for a chapter"""
    
    def get(self, request, chapter_id):
        try:
            chapter = get_object_or_404(Chapter, chapter_id=chapter_id, is_active=True)
            
            links = DownloadLink.objects.filter(
                chapter=chapter,
                is_active=True
            ).order_by('quality', 'format')
            
            links_data = [
                {
                    'quality': link.quality,
                    'format': link.format,
                    'url': link.url,
                    'file_size': link.file_size,
                    'host_name': link.host_name,
                    'label': link.label or f"{link.get_quality_display()} - {link.format.upper()}",
                }
                for link in links
            ]
            
            return JsonResponse({
                'success': True,
                'links': links_data,
                'chapter_title': chapter.display_title
            })
            
        except Exception as e:
            logger.error(f"Error fetching download links for chapter {chapter_id}: {str(e)}")
            return JsonResponse({
                'success': False,
                'error': 'Failed to fetch download links. Please try again later.'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class TrackDownloadView(View):
    """Track download statistics"""
    
    def post(self, request, link_id):
        try:
            link = get_object_or_404(DownloadLink, id=link_id)
            link.increment_download_count()
            
            return JsonResponse({
                'success': True,
                'download_count': link.download_count
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class LikeMangaView(View):
    """AJAX view to like a manga"""
    
    def post(self, request, manga_id):
        try:
            manga = get_object_or_404(Manga, id=manga_id)
            manga.likes = F('likes') + 1
            manga.save(update_fields=['likes'])
            manga.refresh_from_db()
            
            return JsonResponse({
                'success': True,
                'likes': manga.likes
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class BookmarkMangaView(View):
    """AJAX view to bookmark a manga"""
    
    def post(self, request, manga_id):
        try:
            manga = get_object_or_404(Manga, id=manga_id)
            manga.bookmarks = F('bookmarks') + 1
            manga.save(update_fields=['bookmarks'])
            manga.refresh_from_db()
            
            return JsonResponse({
                'success': True,
                'bookmarks': manga.bookmarks
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)


class CategoryListView(ListView):
    model = MangaCategory
    template_name = 'manga/categories.html'
    context_object_name = 'categories'
    
    def get_queryset(self):
        return MangaCategory.objects.filter(is_active=True).annotate(
            manga_count=Count('manga', filter=Q(manga__is_active=True))
        ).order_by('name')


class CategoryDetailView(DetailView):
    model = MangaCategory
    template_name = 'manga/category_detail.html'
    context_object_name = 'category'
    slug_field = 'slug'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        mangas = Manga.objects.filter(
            category=self.object, is_active=True
        ).select_related('category').prefetch_related('genres').order_by('-created_at')
        
        paginator = Paginator(mangas, 24)
        page_number = self.request.GET.get('page')
        context['mangas'] = paginator.get_page(page_number)
        return context


# Homepage view
class HomeView(TemplateView):
    template_name = 'manga/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Featured content
        featured_mangas = Manga.objects.filter(
            is_active=True, is_featured=True
        ).select_related('category').prefetch_related('genres')[:8]
        
        trending_mangas = Manga.objects.filter(
            is_active=True, is_trending=True
        ).select_related('category').prefetch_related('genres')[:8]
        
        recent_mangas = Manga.objects.filter(
            is_active=True
        ).select_related('category').prefetch_related('genres').order_by('-created_at')[:12]
        
        # Recent chapters
        recent_chapters = Chapter.objects.filter(
            is_active=True
        ).select_related('manga', 'manga__category').order_by('-created_at')[:16]
        
        # Popular by type
        popular_manga = Manga.objects.filter(
            is_active=True, manga_type='manga'
        ).order_by('-views')[:6]
        
        popular_manhwa = Manga.objects.filter(
            is_active=True, manga_type='manhwa'
        ).order_by('-views')[:6]
        
        popular_manhua = Manga.objects.filter(
            is_active=True, manga_type='manhua'
        ).order_by('-views')[:6]
        
        context.update({
            'featured_mangas': featured_mangas,
            'trending_mangas': trending_mangas,
            'recent_mangas': recent_mangas,
            'recent_chapters': recent_chapters,
            'popular_manga': popular_manga,
            'popular_manhwa': popular_manhwa,
            'popular_manhua': popular_manhua,
        })
        return context


# Management Dashboard
class ManagementDashboardView(TemplateView):
    template_name = 'manga/management.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        recent_chapters = Chapter.objects.filter(
            is_active=True
        ).select_related('manga').order_by('-created_at')[:20]
        
        context.update({
            'total_mangas': Manga.objects.filter(is_active=True).count(),
            'total_chapters': Chapter.objects.filter(is_active=True).count(),
            'trending_mangas': Manga.objects.filter(is_trending=True).count(),
            'featured_mangas': Manga.objects.filter(is_featured=True).count(),
            'recent_mangas': Manga.objects.filter(is_active=True).order_by('-created_at')[:10],
            'recent_chapters': recent_chapters,
        })
        return context