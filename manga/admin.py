from django.contrib import admin
from django.utils.html import format_html
from .models import (
    MangaCategory, MangaGenre, Manga, Chapter, 
    MangaPage, DownloadLink, Comment
)

@admin.register(MangaCategory)
class MangaCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at']

@admin.register(MangaGenre)
class MangaGenreAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'color_display']
    prepopulated_fields = {'slug': ('name',)}
    
    def color_display(self, obj):
        return format_html(
            '<span style="color: {}; font-weight: bold;">●</span> {}',
            obj.color, obj.color
        )
    color_display.short_description = 'Color'

class ChapterInline(admin.TabularInline):
    model = Chapter
    fields = ['chapter_number', 'title', 'volume', 'pages_count', 'is_active', 'views']
    readonly_fields = ['views']
    extra = 0

@admin.register(Manga)
class MangaAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'manga_type', 'category', 'status', 'total_chapters', 
        'rating', 'views', 'is_featured', 'is_trending', 'created_at'
    ]
    list_filter = [
        'category', 'manga_type', 'status', 'is_featured', 'is_trending', 
        'is_active', 'year', 'is_colored'
    ]
    search_fields = ['title', 'alternative_titles', 'description', 'author', 'artist']
    filter_horizontal = ['genres']
    readonly_fields = ['manga_id', 'manga_session', 'views', 'likes', 'bookmarks', 'created_at', 'updated_at']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ChapterInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'manga_id', 'manga_session', 'alternative_titles', 'category', 'genres')
        }),
        ('Content', {
            'fields': ('description', 'cover_url', 'banner_url')
        }),
        ('Type & Status', {
            'fields': ('manga_type', 'status', 'total_chapters', 'current_chapter')
        }),
        ('Author Info', {
            'fields': ('author', 'artist', 'year', 'serialization')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description', 'keywords')
        }),
        ('Flags', {
            'fields': ('is_featured', 'is_trending', 'is_active', 'is_adult', 'is_colored')
        }),
        ('Stats', {
            'fields': ('rating', 'views', 'likes', 'bookmarks'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('released_at', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

class MangaPageInline(admin.TabularInline):
    model = MangaPage
    fields = ['page_number', 'image_url', 'width', 'height']
    extra = 0

class DownloadLinkInline(admin.TabularInline):
    model = DownloadLink
    fields = ['quality', 'format', 'url', 'file_size', 'is_active']
    extra = 0

@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = [
        'manga', 'chapter_number', 'title', 'volume', 'translator', 
        'pages_count', 'is_active', 'views', 'created_at'
    ]
    list_filter = ['is_active', 'translator', 'volume']
    search_fields = ['manga__title', 'title']
    readonly_fields = ['chapter_id', 'session', 'views', 'created_at', 'updated_at']
    inlines = [MangaPageInline, DownloadLinkInline]

@admin.register(MangaPage)
class MangaPageAdmin(admin.ModelAdmin):
    list_display = ['chapter', 'page_number', 'image_url', 'width', 'height', 'created_at']
    list_filter = ['chapter__manga']
    search_fields = ['chapter__manga__title', 'chapter__chapter_number']
    readonly_fields = ['created_at']

@admin.register(DownloadLink)
class DownloadLinkAdmin(admin.ModelAdmin):
    list_display = ['chapter', 'quality', 'format', 'host_name', 'is_active', 'expires_at', 'download_count']
    list_filter = ['quality', 'format', 'host_name', 'is_active']
    readonly_fields = ['download_count', 'created_at', 'updated_at']

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['name', 'get_target', 'comment_preview', 'is_approved', 'is_reply', 'created_at']
    list_filter = ['is_approved', 'is_active', 'created_at', 'parent']
    search_fields = ['name', 'email', 'comment']
    readonly_fields = ['ip_address', 'user_agent', 'created_at', 'updated_at']
    list_editable = ['is_approved']
    
    fieldsets = (
        ('Comment Info', {
            'fields': ('name', 'email', 'comment')
        }),
        ('Target', {
            'fields': ('manga', 'chapter', 'parent')
        }),
        ('Moderation', {
            'fields': ('is_approved', 'is_active')
        }),
        ('Metadata', {
            'fields': ('ip_address', 'user_agent', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def comment_preview(self, obj):
        return obj.comment[:50] + '...' if len(obj.comment) > 50 else obj.comment
    comment_preview.short_description = 'Comment'
    
    def get_target(self, obj):
        if obj.manga:
            return f"Manga: {obj.manga.title}"
        elif obj.chapter:
            return f"Chapter: {obj.chapter}"
        return "Unknown"
    get_target.short_description = 'Target'
    
    def is_reply(self, obj):
        return obj.is_reply
    is_reply.boolean = True
    is_reply.short_description = 'Reply'