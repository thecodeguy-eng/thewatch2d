# admin.py
from django.contrib import admin
from .models import (
    Game, Category, Tag, Screenshot, DownloadMirror,
    GameUpdate, SystemRequirements, ScrapingLog
)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}


class ScreenshotInline(admin.TabularInline):
    model = Screenshot
    extra = 1


class DownloadMirrorInline(admin.TabularInline):
    model = DownloadMirror
    extra = 1


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ['title', 'version', 'repack_number', 'status', 'post_date', 'is_active']
    list_filter = ['status', 'is_active', 'post_date', 'categories']
    search_fields = ['title', 'companies', 'description']
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ['categories', 'tags']
    inlines = [ScreenshotInline, DownloadMirrorInline]
    date_hierarchy = 'post_date'


@admin.register(ScrapingLog)
class ScrapingLogAdmin(admin.ModelAdmin):
    list_display = ['status', 'game', 'scraped_at', 'message']
    list_filter = ['status', 'scraped_at']
    search_fields = ['message', 'error_details']
    readonly_fields = ['scraped_at']