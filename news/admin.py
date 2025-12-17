# news/admin.py
from django.contrib import admin
from django.utils import timezone
from .models import NewsCategory, NewsArticle, Comment

@admin.register(NewsCategory)
class NewsCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ['name']


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'author', 'status', 'featured', 'views', 'published_at']
    list_filter = ['status', 'featured', 'category', 'published_at']
    search_fields = ['title', 'content']
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'published_at'
    
    fieldsets = (
        ('Article Info', {
            'fields': ('title', 'slug', 'category', 'excerpt')
        }),
        ('Content', {
            'fields': ('content', 'image_url')
        }),
        ('Settings', {
            'fields': ('status', 'featured')
        }),
        ('Timestamps', {
            'fields': ('published_at',),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.author = request.user
        if obj.status == 'published' and not obj.published_at:
            obj.published_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['user', 'article', 'content_preview', 'approved', 'created_at']
    list_filter = ['approved', 'created_at']
    search_fields = ['content', 'user__username', 'article__title']
    actions = ['approve_comments', 'disapprove_comments']
    
    def content_preview(self, obj):
        return obj.content[:50] + '...' if len(obj.content) > 50 else obj.content
    content_preview.short_description = 'Content'
    
    def approve_comments(self, request, queryset):
        queryset.update(approved=True)
    approve_comments.short_description = 'Approve selected comments'
    
    def disapprove_comments(self, request, queryset):
        queryset.update(approved=False)
    disapprove_comments.short_description = 'Disapprove selected comments'