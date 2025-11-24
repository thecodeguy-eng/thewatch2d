from django.contrib import admin
from .models import Movie, Category, Comment, DownloadLink
from .views import invalidate_sidebar_cache

class DownloadLinkInline(admin.TabularInline):
    model = DownloadLink
    extra = 1  # How many empty forms to display
    fields = ('label', 'url')
    readonly_fields = ()
    show_change_link = True

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ('title', 'added_by', 'scraped', 'created_at', 'is_blockbuster',)
    list_editable = ('is_blockbuster',) 
    list_filter = ('scraped', 'categories','is_blockbuster',)
    search_fields = ('title', 'description')
    inlines = [DownloadLinkInline]  # Add download links inline
    
    def save_model(self, request, obj, form, change):
        """
        Override save_model to invalidate cache when movies are added/updated
        """
        super().save_model(request, obj, form, change)
        # Clear the sidebar cache whenever a movie is added or updated
        invalidate_sidebar_cache()
        
    def delete_model(self, request, obj):
        """
        Override delete_model to invalidate cache when movies are deleted
        """
        super().delete_model(request, obj)
        # Clear the sidebar cache whenever a movie is deleted
        invalidate_sidebar_cache()

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('movie', 'user', 'created_at')
    search_fields = ('user__username', 'movie__title', 'content')

@admin.register(DownloadLink)
class DownloadLinkAdmin(admin.ModelAdmin):
    list_display = ('movie', 'label', 'url')
    search_fields = ('movie__title', 'label', 'url')



from .models import PWAInstallation, PushSubscription, OfflineAction

@admin.register(PWAInstallation)
class PWAInstallationAdmin(admin.ModelAdmin):
    list_display = ('user', 'platform', 'installed_at')
    list_filter = ('platform', 'installed_at')
    readonly_fields = ('installed_at',)

@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    readonly_fields = ('created_at',)

@admin.register(OfflineAction)
class OfflineActionAdmin(admin.ModelAdmin):
    list_display = ('user', 'action_type', 'synced', 'created_at')
    list_filter = ('action_type', 'synced', 'created_at')
    readonly_fields = ('created_at',)