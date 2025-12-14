from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, Count
from .models import APK, Category, Screenshot, Comment
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
import json


@method_decorator(cache_page(60 * 60 * 4), name='dispatch')  # 4 hours instead of 24
def home(request):
    """Homepage with featured and latest APKs"""
    featured_apks = APK.objects.filter(is_active=True, featured=True)[:6]
    latest_games = APK.objects.filter(is_active=True, apk_type='game').order_by('-created_at')[:12]
    latest_apps = APK.objects.filter(is_active=True, apk_type='app').order_by('-created_at')[:12]
    popular_categories = Category.objects.annotate(
        apk_count=Count('apks')
    ).filter(apk_count__gt=0).order_by('-apk_count')[:8]
    
    context = {
        'featured_apks': featured_apks,
        'latest_games': latest_games,
        'latest_apps': latest_apps,
        'categories': popular_categories,
    }
    return render(request, 'apk_store/home.html', context)


@method_decorator(cache_page(60 * 60 * 4), name='dispatch')  # 4 hours instead of 24
def apk_list(request):
    """List all APKs with filters"""
    apks = APK.objects.filter(is_active=True).select_related().prefetch_related('categories', 'screenshots')
    
    # Filter by type
    apk_type = request.GET.get('type', 'all')
    if apk_type in ['game', 'app']:
        apks = apks.filter(apk_type=apk_type)
    
    # Filter by status
    status = request.GET.get('status')
    if status:
        apks = apks.filter(status=status)
    
    # Filter by category
    category_slug = request.GET.get('category')
    if category_slug:
        apks = apks.filter(categories__slug=category_slug)
    
    # Search
    query = request.GET.get('q')
    if query:
        apks = apks.filter(
            Q(title__icontains=query) | 
            Q(description__icontains=query)
        )
    
    # Ordering
    order = request.GET.get('order', '-created_at')
    if order in ['-created_at', 'title', '-rating']:
        apks = apks.order_by(order)
    
    # Pagination
    paginator = Paginator(apks, 24)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    categories = Category.objects.all()
    
    context = {
        'page_obj': page_obj,
        'apks': page_obj,
        'categories': categories,
        'current_type': apk_type,
        'current_status': status,
        'current_category': category_slug,
        'query': query,
    }
    return render(request, 'apk_store/apk_list.html', context)


def apk_detail(request, slug):
    """Single APK detail page"""
    apk = get_object_or_404(APK.objects.prefetch_related('screenshots', 'categories', 'versions'), slug=slug)
    
    # Get approved comments (only parent comments, not replies)
    comments = apk.comments.filter(is_approved=True, parent=None).prefetch_related('replies').order_by('-created_at')
    
    # Related APKs (same category or type)
    related_apks = APK.objects.filter(
        is_active=True,
        apk_type=apk.apk_type
    ).exclude(id=apk.id).order_by('-created_at')[:6]
    
    context = {
        'apk': apk,
        'related_apks': related_apks,
        'comments': comments,
        'comments_count': comments.count(),
    }
    return render(request, 'apk_store/apk_detail.html', context)


@method_decorator(cache_page(60 * 60 * 4), name='dispatch')  # 4 hours instead of 24
def games_list(request):
    """List only games"""
    games = APK.objects.filter(is_active=True, apk_type='game').select_related().prefetch_related('categories', 'screenshots')
    
    # Filter by status
    status = request.GET.get('status')
    if status:
        games = games.filter(status=status)
    
    # Filter by category
    category_slug = request.GET.get('category')
    if category_slug:
        games = games.filter(categories__slug=category_slug)
    
    # Search
    query = request.GET.get('q')
    if query:
        games = games.filter(Q(title__icontains=query) | Q(description__icontains=query))
    
    # Ordering
    order = request.GET.get('order', '-created_at')
    games = games.order_by(order)
    
    # Pagination
    paginator = Paginator(games, 24)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    categories = Category.objects.filter(apks__apk_type='game').distinct()
    
    context = {
        'page_obj': page_obj,
        'games': page_obj,
        'categories': categories,
        'current_status': status,
        'current_category': category_slug,
        'query': query,
    }
    return render(request, 'apk_store/games_list.html', context)


@method_decorator(cache_page(60 * 60 * 4), name='dispatch')  # 4 hours instead of 24
def apps_list(request):
    """List only apps"""
    apps = APK.objects.filter(is_active=True, apk_type='app').select_related().prefetch_related('categories', 'screenshots')
    
    # Filter by status
    status = request.GET.get('status')
    if status:
        apps = apps.filter(status=status)
    
    # Filter by category
    category_slug = request.GET.get('category')
    if category_slug:
        apps = apps.filter(categories__slug=category_slug)
    
    # Search
    query = request.GET.get('q')
    if query:
        apps = apps.filter(Q(title__icontains=query) | Q(description__icontains=query))
    
    # Ordering
    order = request.GET.get('order', '-created_at')
    apps = apps.order_by(order)
    
    # Pagination
    paginator = Paginator(apps, 24)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    categories = Category.objects.filter(apks__apk_type='app').distinct()
    
    context = {
        'page_obj': page_obj,
        'apps': page_obj,
        'categories': categories,
        'current_status': status,
        'current_category': category_slug,
        'query': query,
    }
    return render(request, 'apk_store/apps_list.html', context)


@method_decorator(cache_page(60 * 60 * 2), name='dispatch')  # 4 hours instead of 24
def category_detail(request, slug):
    """View APKs in a specific category"""
    category = get_object_or_404(Category, slug=slug)
    apks = APK.objects.filter(is_active=True, categories=category).select_related().prefetch_related('screenshots')
    
    # Filter by type
    apk_type = request.GET.get('type', 'all')
    if apk_type in ['game', 'app']:
        apks = apks.filter(apk_type=apk_type)
    
    # Ordering
    order = request.GET.get('order', '-created_at')
    apks = apks.order_by(order)
    
    # Pagination
    paginator = Paginator(apks, 24)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'category': category,
        'page_obj': page_obj,
        'apks': page_obj,
        'current_type': apk_type,
    }
    return render(request, 'apk_store/category_detail.html', context)


@method_decorator(cache_page(60 * 15), name='dispatch')  # 15 minutes for search
def search(request):
    """Search APKs"""
    query = request.GET.get('q', '')
    apks = APK.objects.none()
    
    if query:
        apks = APK.objects.filter(
            Q(title__icontains=query) | 
            Q(description__icontains=query) |
            Q(categories__name__icontains=query)
        ).filter(is_active=True).distinct()
    
    # Filter by type
    apk_type = request.GET.get('type', 'all')
    if apk_type in ['game', 'app']:
        apks = apks.filter(apk_type=apk_type)
    
    # Pagination
    paginator = Paginator(apks, 24)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'query': query,
        'page_obj': page_obj,
        'apks': page_obj,
        'current_type': apk_type,
    }
    return render(request, 'apk_store/search.html', context)





@require_POST
def post_comment(request, slug):
    """Handle comment posting via AJAX"""
    try:
        data = json.loads(request.body)
        apk = get_object_or_404(APK, slug=slug)
        
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        comment_text = data.get('comment', '').strip()
        
        # Validation
        if not name or not comment_text:
            return JsonResponse({
                'success': False,
                'error': 'Name and comment are required.'
            }, status=400)
        
        if len(name) > 100:
            return JsonResponse({
                'success': False,
                'error': 'Name is too long (max 100 characters).'
            }, status=400)
        
        if len(comment_text) > 1000:
            return JsonResponse({
                'success': False,
                'error': 'Comment is too long (max 1000 characters).'
            }, status=400)
        
        # Create comment
        comment = Comment.objects.create(
            apk=apk,
            name=name,
            email=email,
            comment_text=comment_text
        )
        
        return JsonResponse({
            'success': True,
            'comment': {
                'id': comment.id,
                'name': comment.name,
                'comment_text': comment.comment_text,
                'created_at': comment.created_at.strftime('%B %d, %Y at %I:%M %p'),
                'replies_count': 0
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid request data.'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'An error occurred. Please try again.'
        }, status=500)


@require_POST
def post_reply(request, comment_id):
    """Handle reply posting via AJAX"""
    try:
        data = json.loads(request.body)
        parent_comment = get_object_or_404(Comment, id=comment_id)
        
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        comment_text = data.get('comment', '').strip()
        
        # Validation
        if not name or not comment_text:
            return JsonResponse({
                'success': False,
                'error': 'Name and reply are required.'
            }, status=400)
        
        if len(name) > 100:
            return JsonResponse({
                'success': False,
                'error': 'Name is too long (max 100 characters).'
            }, status=400)
        
        if len(comment_text) > 1000:
            return JsonResponse({
                'success': False,
                'error': 'Reply is too long (max 1000 characters).'
            }, status=400)
        
        # Create reply
        reply = Comment.objects.create(
            apk=parent_comment.apk,
            parent=parent_comment,
            name=name,
            email=email,
            comment_text=comment_text
        )
        
        return JsonResponse({
            'success': True,
            'reply': {
                'id': reply.id,
                'name': reply.name,
                'comment_text': reply.comment_text,
                'created_at': reply.created_at.strftime('%B %d, %Y at %I:%M %p')
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid request data.'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'An error occurred. Please try again.'
        }, status=500)