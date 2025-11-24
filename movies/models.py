# movies/models.py
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Movie(models.Model):
    title = models.CharField(max_length=200, unique=True)
    title_b = models.CharField(max_length=200, blank=True, null=True, help_text="Stores new episode info")
    title_b_updated_at = models.DateTimeField(null=True, blank=True)
    is_series = models.BooleanField(default=False)
    completed = models.BooleanField(default=False, help_text="Mark if series is complete")  # ← ADD THIS
    description = models.TextField(blank=True)
    video_url = models.URLField("Video/Embed URL")
    download_url = models.URLField("Download URL", blank=True, null=True)
    image_url = models.URLField("Cover Image URL", blank=True, null=True)
    categories = models.ManyToManyField(Category, blank=True, related_name='movies')
    added_by = models.ForeignKey(User, null=True, blank=True,
                                 on_delete=models.SET_NULL,
                                 help_text="If user-submitted, the submitting user")
    created_at = models.DateTimeField(default=timezone.now)
    scraped = models.BooleanField(default=False,
                                  help_text="True if movie was scraped from external API")

    # Social relations: likes and watchlist (M2M with User)
    liked_by = models.ManyToManyField(User, related_name='liked_movies', blank=True)
    is_blockbuster = models.BooleanField(default=False,
                                  help_text="Mark as featured/trending for the homepage")
    watchlisted_by = models.ManyToManyField(User, related_name='watchlist_movies', blank=True)
    views = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.title
    

    def get_absolute_url(self):
        return reverse('movies:movie_detail', args=[str(self.pk)])

class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Comment by {self.user.username} on {self.movie.title}"


class DownloadLink(models.Model):
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE, related_name='download_links')
    label = models.CharField(max_length=255, blank=True)  # e.g., "Episode 1 (720p)"
    url = models.URLField()

    def __str__(self):
        return f"{self.label or 'Link'} – {self.url}"

# Add these models to movies/models.py for PWA features
from django.db import models
from django.contrib.auth.models import User

class PWAInstallation(models.Model):
    """Track PWA installations"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    user_agent = models.TextField()
    installed_at = models.DateTimeField(auto_now_add=True)
    platform = models.CharField(max_length=50)
    
    class Meta:
        db_table = 'pwa_installations'

class PushSubscription(models.Model):
    """Store push notification subscriptions"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    endpoint = models.URLField()
    p256dh_key = models.TextField()
    auth_key = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'push_subscriptions'
        unique_together = ('user', 'endpoint')

class OfflineAction(models.Model):
    """Store offline actions for sync when online"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    action_type = models.CharField(max_length=50)  # 'like', 'watchlist', 'search'
    action_data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    synced = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'offline_actions'