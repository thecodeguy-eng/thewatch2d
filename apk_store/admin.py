# admin.py
from django.contrib import admin
from .models import APK, Category, Screenshot, APKVersion, DownloadFile, Comment

class ScreenshotInline(admin.TabularInline):
    model = Screenshot
    extra = 1
    fields = ('image_url', 'order')

class APKVersionInline(admin.TabularInline):
    model = APKVersion
    extra = 0
    fields = ('version', 'download_url', 'size', 'is_latest', 'created_at')
    readonly_fields = ('created_at',)

class DownloadFileInline(admin.TabularInline):
    model = DownloadFile
    extra = 1
    fields = ('file_type', 'file_name', 'download_url', 'size', 'version', 'order', 'is_required')
    ordering = ['order']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'get_apk_count', 'created_at')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('created_at', 'updated_at')
    
    def get_apk_count(self, obj):
        return obj.apks.count()
    get_apk_count.short_description = 'APK Count'

@admin.register(APK)
class APKAdmin(admin.ModelAdmin):
    list_display = ('title', 'apk_type', 'status', 'version', 'rating', 'is_active', 'featured', 'created_at')
    list_filter = ('apk_type', 'status', 'is_active', 'featured', 'created_at', 'categories')
    search_fields = ('title', 'description', 'package_name')
    prepopulated_fields = {'slug': ('title',)}
    filter_horizontal = ('categories',)
    readonly_fields = ('created_at', 'updated_at')  # Removed 'slug' from here
    inlines = [DownloadFileInline, ScreenshotInline, APKVersionInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'slug', 'apk_type', 'description')
        }),
        ('Images', {
            'fields': ('icon_url', 'cover_image_url')
        }),
        ('APK Details', {
            'fields': ('version', 'size', 'android_version', 'architecture', 'package_name')
        }),
        ('Status & Mod', {
            'fields': ('status', 'mod_features')
        }),
        ('Primary Download', {
            'fields': ('download_url', 'source_url'),
            'description': 'Primary download link (additional files can be added below)'
        }),
        ('Categories', {
            'fields': ('categories',)
        }),
        ('Stats', {
            'fields': ('downloads_count', 'rating')
        }),
        ('Meta', {
            'fields': ('is_active', 'featured', 'created_at', 'updated_at')
        }),
    )
    
    actions = ['mark_as_active', 'mark_as_inactive', 'mark_as_featured']
    
    def mark_as_active(self, request, queryset):
        queryset.update(is_active=True)
    mark_as_active.short_description = "Mark selected as active"
    
    def mark_as_inactive(self, request, queryset):
        queryset.update(is_active=False)
    mark_as_inactive.short_description = "Mark selected as inactive"
    
    def mark_as_featured(self, request, queryset):
        queryset.update(featured=True)
    mark_as_featured.short_description = "Mark selected as featured"

@admin.register(DownloadFile)
class DownloadFileAdmin(admin.ModelAdmin):
    list_display = ('apk', 'file_type', 'file_name', 'size', 'version', 'order', 'is_required', 'created_at')
    list_filter = ('file_type', 'is_required', 'created_at')
    search_fields = ('apk__title', 'file_name', 'description')
    readonly_fields = ('created_at',)
    ordering = ['apk', 'order']

@admin.register(Screenshot)
class ScreenshotAdmin(admin.ModelAdmin):
    list_display = ('apk', 'order', 'created_at')
    list_filter = ('apk__apk_type', 'created_at')
    search_fields = ('apk__title',)
    readonly_fields = ('created_at',)

@admin.register(APKVersion)
class APKVersionAdmin(admin.ModelAdmin):
    list_display = ('apk', 'version', 'size', 'is_latest', 'created_at')
    list_filter = ('is_latest', 'created_at')
    search_fields = ('apk__title', 'version')
    readonly_fields = ('created_at',)



@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('name', 'apk', 'comment_text_preview', 'is_approved', 'created_at', 'parent')
    list_filter = ('is_approved', 'created_at')
    search_fields = ('name', 'email', 'comment_text', 'apk__title')
    readonly_fields = ('created_at', 'updated_at')
    actions = ['approve_comments', 'disapprove_comments']
    
    def comment_text_preview(self, obj):
        return obj.comment_text[:50] + '...' if len(obj.comment_text) > 50 else obj.comment_text
    comment_text_preview.short_description = 'Comment'
    
    def approve_comments(self, request, queryset):
        queryset.update(is_approved=True)
    approve_comments.short_description = "Approve selected comments"
    
    def disapprove_comments(self, request, queryset):
        queryset.update(is_approved=False)
    disapprove_comments.short_description = "Disapprove selected comments"