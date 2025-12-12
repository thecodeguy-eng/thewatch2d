from django.contrib import admin
from django.utils.html import format_html
from .models import (
    AnimeCategory, AnimeGenre, Anime, Episode, 
    DownloadLink, Comment, CommentReply
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



class CommentReplyInline(admin.TabularInline):
    model = CommentReply
    fields = ['name', 'reply', 'is_approved', 'created_at']
    readonly_fields = ['created_at']
    extra = 0
    can_delete = True


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'content_display', 'comment_preview', 
        'is_approved', 'is_flagged', 'created_at'
    ]
    list_filter = [
        'is_approved', 'is_flagged', 'content_type', 'created_at'
    ]
    search_fields = ['name', 'email', 'comment', 'anime__title', 'episode__title']
    readonly_fields = ['created_at', 'updated_at', 'ip_address', 'user_agent']
    inlines = [CommentReplyInline]
    
    fieldsets = (
        ('Comment Details', {
            'fields': ('content_type', 'anime', 'episode', 'name', 'email', 'comment')
        }),
        ('Moderation', {
            'fields': ('is_approved', 'is_flagged')
        }),
        ('Metadata', {
            'fields': ('ip_address', 'user_agent', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['approve_comments', 'flag_comments', 'unflag_comments']
    
    def content_display(self, obj):
        """Display what content is being commented on"""
        if obj.anime:
            return format_html(
                '<a href="/admin/anime/anime/{}/change/">{}</a>',
                obj.anime.id,
                obj.anime.title
            )
        elif obj.episode:
            return format_html(
                '<a href="/admin/anime/episode/{}/change/">Episode {}</a>',
                obj.episode.id,
                obj.episode.episode_number
            )
        return '-'
    content_display.short_description = 'Content'
    
    def comment_preview(self, obj):
        """Show preview of comment"""
        preview = obj.comment[:50]
        if len(obj.comment) > 50:
            preview += '...'
        return preview
    comment_preview.short_description = 'Comment Preview'
    
    def approve_comments(self, request, queryset):
        """Bulk approve comments"""
        updated = queryset.update(is_approved=True)
        self.message_user(request, f'{updated} comment(s) approved.')
    approve_comments.short_description = 'Approve selected comments'
    
    def flag_comments(self, request, queryset):
        """Bulk flag comments"""
        updated = queryset.update(is_flagged=True)
        self.message_user(request, f'{updated} comment(s) flagged.')
    flag_comments.short_description = 'Flag selected comments'
    
    def unflag_comments(self, request, queryset):
        """Bulk unflag comments"""
        updated = queryset.update(is_flagged=False)
        self.message_user(request, f'{updated} comment(s) unflagged.')
    unflag_comments.short_description = 'Unflag selected comments'


@admin.register(CommentReply)
class CommentReplyAdmin(admin.ModelAdmin):
    list_display = ['name', 'comment_display', 'reply_preview', 'is_approved', 'created_at']
    list_filter = ['is_approved', 'created_at']
    search_fields = ['name', 'reply']
    readonly_fields = ['created_at', 'ip_address']
    
    def comment_display(self, obj):
        """Display parent comment"""
        return format_html(
            '<a href="/admin/anime/comment/{}/change/">Comment by {}</a>',
            obj.comment.id,
            obj.comment.name
        )
    comment_display.short_description = 'Parent Comment'
    
    def reply_preview(self, obj):
        """Show preview of reply"""
        preview = obj.reply[:50]
        if len(obj.reply) > 50:
            preview += '...'
        return preview
    reply_preview.short_description = 'Reply Preview'