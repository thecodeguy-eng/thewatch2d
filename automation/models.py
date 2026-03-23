"""
automation/models.py
Tracks every item posted to Telegram so we never double-post.
Two tables:
  - TelegramPost     → new content (first time posted)
  - TelegramUpdate   → episode/chapter updates on existing content
"""

from django.db import models


class TelegramPost(models.Model):
    """Tracks first-time posts of new Movies / Anime / Manga."""

    CONTENT_TYPE_CHOICES = [
        ('movie', 'Movie'),
        ('anime', 'Anime'),
        ('manga', 'Manga'),
    ]

    content_type        = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    content_id          = models.IntegerField(help_text="PK of the Movie / Anime / Manga")
    content_title       = models.CharField(max_length=500)
    telegram_message_id = models.CharField(max_length=100, blank=True)
    posted_at           = models.DateTimeField(auto_now_add=True)
    success             = models.BooleanField(default=True)
    error_message       = models.TextField(blank=True)

    class Meta:
        unique_together = ['content_type', 'content_id']
        ordering = ['-posted_at']

    def __str__(self):
        return f"[NEW {self.content_type}] {self.content_title} — {self.posted_at:%Y-%m-%d %H:%M}"


class TelegramUpdate(models.Model):
    """
    Tracks episode/chapter UPDATE posts for existing series.
    One row per update notification sent.
    We store the update_key (e.g. episode label or updated_at timestamp)
    so we don't re-post the same update twice.
    """

    CONTENT_TYPE_CHOICES = [
        ('movie', 'Movie'),
        ('anime', 'Anime'),
        ('manga', 'Manga'),
    ]

    content_type        = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES)
    content_id          = models.IntegerField()
    content_title       = models.CharField(max_length=500)
    # update_key uniquely identifies this specific update
    # For movies: title_b value (episode label)
    # For anime:  episode number as string
    # For manga:  chapter number as string
    update_key          = models.CharField(max_length=500, help_text="Episode/chapter identifier")
    telegram_message_id = models.CharField(max_length=100, blank=True)
    posted_at           = models.DateTimeField(auto_now_add=True)
    success             = models.BooleanField(default=True)
    error_message       = models.TextField(blank=True)

    class Meta:
        # Each unique update per content item is only posted once
        unique_together = ['content_type', 'content_id', 'update_key']
        ordering = ['-posted_at']

    def __str__(self):
        return f"[UPDATE {self.content_type}] {self.content_title} — {self.update_key}"