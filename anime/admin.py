from django.contrib import admin
from django.utils.html import format_html
from .models import (
    AnimeCategory, AnimeGenre, Anime, Episode, 
    DownloadLink
)

@admin.register(AnimeCategory)
class AnimeCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at']

@admin.register(AnimeGenre)
class AnimeGenreAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'color_display']
    prepopulated_fields = {'slug': ('name',)}
    
    def color_display(self, obj):
        return format_html(
            '<span style="color: {}; font-weight: bold;">●</span> {}',
            obj.color, obj.color
        )
    color_display.short_description = 'Color'

class EpisodeInline(admin.TabularInline):
    model = Episode
    fields = ['episode_number', 'title', 'is_filler', 'is_completed', 'views']
    readonly_fields = ['views']
    extra = 0

@admin.register(Anime)
class AnimeAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'category', 'status', 'total_episodes', 
        'rating', 'views', 'is_featured', 'is_trending', 'created_at'
    ]
    list_filter = [
        'category', 'status', 'is_featured', 'is_trending', 
        'is_active', 'year', 'season'
    ]
    search_fields = ['title', 'description', 'studio']
    filter_horizontal = ['genres']
    readonly_fields = ['anime_id', 'anime_session', 'views', 'likes', 'created_at', 'updated_at']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [EpisodeInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'anime_id', 'anime_session', 'category', 'genres')
        }),
        ('Content', {
            'fields': ('description', 'poster_url', 'cover_image_url')
        }),
        ('Status & Progress', {
            'fields': ('status', 'total_episodes', 'current_episode')
        }),
        ('Metadata', {
            'fields': ('year', 'season', 'studio', 'source', 'duration_minutes')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description', 'keywords')
        }),
        ('Flags', {
            'fields': ('is_featured', 'is_trending', 'is_active', 'is_adult')
        }),
        ('Stats', {
            'fields': ('rating', 'views', 'likes'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('aired_from', 'aired_to', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

class DownloadLinkInline(admin.TabularInline):
    model = DownloadLink
    fields = ['quality', 'url', 'file_size', 'is_active']
    extra = 0

@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = [
        'anime', 'episode_number', 'title', 'fansub', 
        'is_completed', 'views', 'created_at'
    ]
    list_filter = ['is_completed', 'is_filler', 'is_active', 'fansub']
    search_fields = ['anime__title', 'title']
    readonly_fields = ['episode_id', 'session', 'views', 'created_at', 'updated_at']
    inlines = [DownloadLinkInline]

@admin.register(DownloadLink)
class DownloadLinkAdmin(admin.ModelAdmin):
    list_display = ['episode', 'quality', 'host_name', 'is_active', 'expires_at', 'fetch_count']
    list_filter = ['quality', 'host_name', 'is_active']
    readonly_fields = ['fetch_count', 'created_at', 'updated_at']