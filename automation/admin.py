from django.contrib import admin
from .models import TelegramPost, TelegramUpdate


@admin.register(TelegramPost)
class TelegramPostAdmin(admin.ModelAdmin):
    list_display    = ['content_type', 'content_title', 'posted_at', 'success']
    list_filter     = ['content_type', 'success']
    search_fields   = ['content_title']
    readonly_fields = ['posted_at']
    ordering        = ['-posted_at']


@admin.register(TelegramUpdate)
class TelegramUpdateAdmin(admin.ModelAdmin):
    list_display    = ['content_type', 'content_title', 'update_key', 'posted_at', 'success']
    list_filter     = ['content_type', 'success']
    search_fields   = ['content_title', 'update_key']
    readonly_fields = ['posted_at']
    ordering        = ['-posted_at']