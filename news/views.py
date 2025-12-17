# news/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from .models import NewsArticle, NewsCategory, Comment
from .forms import CommentForm

def news_home(request):
    """News homepage with featured and latest articles"""
    featured_articles = NewsArticle.objects.filter(
        status='published', 
        featured=True
    ).order_by('-published_at')[:3]
    
    latest_articles = NewsArticle.objects.filter(
        status='published'
    ).order_by('-published_at')[:12]
    
    categories = NewsCategory.objects.annotate(
        article_count=Count('articles', filter=Q(articles__status='published'))
    )
    
    context = {
        'featured_articles': featured_articles,
        'latest_articles': latest_articles,
        'categories': categories,
    }
    return render(request, 'news/home.html', context)


def article_detail(request, slug):
    """Individual news article with comments"""
    article = get_object_or_404(NewsArticle, slug=slug, status='published')
    
    # Increment views
    article.views += 1
    article.save(update_fields=['views'])
    
    # Get approved comments
    comments = article.comments.filter(approved=True).select_related('user')
    
    # Handle comment form
    if request.method == 'POST' and request.user.is_authenticated:
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.article = article
            comment.user = request.user
            comment.save()
            messages.success(request, 'Your comment has been posted!')
            return redirect('news:article_detail', slug=slug)
    else:
        form = CommentForm()
    
    # Related articles
    related_articles = NewsArticle.objects.filter(
        category=article.category,
        status='published'
    ).exclude(id=article.id)[:4]
    
    context = {
        'article': article,
        'comments': comments,
        'form': form,
        'related_articles': related_articles,
    }
    return render(request, 'news/article_detail.html', context)


def news_category(request, slug):
    """News articles filtered by category"""
    category = get_object_or_404(NewsCategory, slug=slug)
    articles_list = NewsArticle.objects.filter(
        category=category,
        status='published'
    ).order_by('-published_at')
    
    paginator = Paginator(articles_list, 12)
    page = request.GET.get('page')
    articles = paginator.get_page(page)
    
    context = {
        'category': category,
        'articles': articles,
    }
    return render(request, 'news/category.html', context)


def news_search(request):
    """Search news articles"""
    query = request.GET.get('q', '')
    articles_list = []
    
    if query:
        articles_list = NewsArticle.objects.filter(
            Q(title__icontains=query) | 
            Q(content__icontains=query) |
            Q(excerpt__icontains=query),
            status='published'
        ).order_by('-published_at')
    
    paginator = Paginator(articles_list, 12)
    page = request.GET.get('page')
    articles = paginator.get_page(page)
    
    context = {
        'articles': articles,
        'query': query,
    }
    return render(request, 'news/search.html', context)


@login_required
def delete_comment(request, comment_id):
    """Delete a comment (only by comment author)"""
    comment = get_object_or_404(Comment, id=comment_id)
    
    if request.user == comment.user or request.user.is_staff:
        article_slug = comment.article.slug
        comment.delete()
        messages.success(request, 'Comment deleted successfully!')
        return redirect('news:article_detail', slug=article_slug)
    else:
        messages.error(request, 'You cannot delete this comment.')
        return redirect('news:article_detail', slug=comment.article.slug)