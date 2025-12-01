from django.db import models
from django.db.models import F, Max
from django.urls import reverse
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
import uuid

class AnimeCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    image = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Anime Categories"
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('anime:category_detail', kwargs={'slug': self.slug})

    @property
    def anime_count(self):
        return self.anime_set.filter(is_active=True).count()

class AnimeGenre(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    color = models.CharField(max_length=7, default='#6366f1')  # Hex color
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('anime:genre_detail', kwargs={'slug': self.slug})

    @property
    def anime_count(self):
        return self.anime_set.filter(is_active=True).count()

class Anime(models.Model):
    STATUS_CHOICES = [
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('upcoming', 'Upcoming'),
        ('dropped', 'Dropped'),
    ]
    
    SEASON_CHOICES = [
        ('spring', 'Spring'),
        ('summer', 'Summer'),
        ('fall', 'Fall'),
        ('winter', 'Winter'),
    ]

    # Basic Info - Updated for chia-anime compatibility
    anime_id = models.IntegerField(default=0)  # WordPress post ID or generated ID
    anime_session = models.CharField(max_length=255, unique=True)  # Unique identifier
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    
    # Metadata
    category = models.ForeignKey(AnimeCategory, on_delete=models.SET_NULL, null=True, blank=True)
    genres = models.ManyToManyField(AnimeGenre, blank=True)
    description = models.TextField(blank=True)
    poster_url = models.URLField(max_length=500, blank=True)
    cover_image_url = models.URLField(max_length=500, blank=True)
    
    # Status & Progress
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ongoing')
    total_episodes = models.PositiveIntegerField(default=0)
    current_episode = models.PositiveIntegerField(default=0)
    
    # Ratings & Stats
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True,
                                validators=[MinValueValidator(0), MaxValueValidator(10)])
    views = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    
    # Additional Info
    year = models.PositiveIntegerField(null=True, blank=True)
    season = models.CharField(max_length=10, choices=SEASON_CHOICES, blank=True)
    studio = models.CharField(max_length=100, blank=True)
    source = models.CharField(max_length=50, blank=True)  # Manga, Novel, etc.
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    
    # SEO & Meta
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(max_length=160, blank=True)
    keywords = models.CharField(max_length=255, blank=True)
    
    # Flags
    is_featured = models.BooleanField(default=False)
    is_trending = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_adult = models.BooleanField(default=False)
    
    # Timestamps
    aired_from = models.DateField(null=True, blank=True)
    aired_to = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['anime_id']),
            models.Index(fields=['status']),
            models.Index(fields=['is_featured']),
            models.Index(fields=['is_trending']),
            models.Index(fields=['year']),
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('anime:detail', kwargs={'slug': self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Anime.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        
        if not self.meta_title:
            self.meta_title = f"Watch {self.title} - Free Anime Streaming | Ibez"
        
        if not self.meta_description:
            self.meta_description = f"Stream {self.title} anime episodes for free. Watch high-quality anime with English subtitles on Ibez."
            
        super().save(*args, **kwargs)

    @property
    def progress_percentage(self):
        if self.total_episodes > 0:
            return (self.current_episode / self.total_episodes) * 100
        return 0

    @property
    def is_completed_anime(self):
        return self.status == 'completed'

    def increment_views(self):
        self.views = F('views') + 1
        self.save(update_fields=['views'])
        self.refresh_from_db(fields=['views'])

    def get_latest_episodes(self, count=12):
        """Get the latest episodes for this anime"""
        return self.episodes.filter(is_active=True).order_by('-episode_number')[:count]

    def get_related_anime(self, count=6):
        """Get related anime based on category and genres"""
        related = Anime.objects.filter(
            is_active=True
        ).exclude(id=self.id)
        
        if self.category:
            related = related.filter(category=self.category)
        
        if self.genres.exists():
            related = related.filter(genres__in=self.genres.all()).distinct()
            
        return related.order_by('-views')[:count]

class Episode(models.Model):
    # Relations
    anime = models.ForeignKey(Anime, on_delete=models.CASCADE, related_name='episodes')
    
    # Episode Info - Updated for chia-anime compatibility
    episode_id = models.IntegerField()  # Generated or from source
    session = models.CharField(max_length=255, unique=True)
    episode_number = models.PositiveIntegerField()
    episode2 = models.PositiveIntegerField(default=0)  # For special episodes
    title = models.CharField(max_length=255, blank=True)
    
    # Technical Details
    fansub = models.CharField(max_length=100, blank=True, default='Unknown')
    edition = models.CharField(max_length=50, blank=True)
    snapshot_url = models.URLField(max_length=500, blank=True)
    disc = models.CharField(max_length=20, blank=True)
    
    # Additional fields for chia-anime
    post_url = models.URLField(max_length=500, blank=True)  # Original post URL
    publish_date = models.DateTimeField(null=True, blank=True)  # When episode was published
    
    # Flags
    is_filler = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=True)  # Chia-anime episodes are complete when posted
    is_active = models.BooleanField(default=True)
    
    # Stats
    views = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['anime', 'episode_number']
        unique_together = ['anime', 'episode_number']
        indexes = [
            models.Index(fields=['episode_id']),
            models.Index(fields=['anime', 'episode_number']),
            models.Index(fields=['is_completed']),
            models.Index(fields=['publish_date']),
        ]

    def __str__(self):
        return f"{self.anime.title} - Episode {self.episode_number}"

    def get_absolute_url(self):
        return reverse('anime:episode_detail', kwargs={
            'anime_slug': self.anime.slug,
            'episode_number': self.episode_number
        })

    @property
    def display_title(self):
        if self.title and self.title != f"Episode {self.episode_number}":
            return f"Episode {self.episode_number}: {self.title}"
        return f"Episode {self.episode_number}"

    def increment_views(self):
        self.views = F('views') + 1
        self.save(update_fields=['views'])
        self.refresh_from_db(fields=['views'])

    def get_previous_episode(self):
        """Get the previous episode"""
        return Episode.objects.filter(
            anime=self.anime,
            episode_number__lt=self.episode_number,
            is_active=True
        ).order_by('-episode_number').first()

    def get_next_episode(self):
        """Get the next episode"""
        return Episode.objects.filter(
            anime=self.anime,
            episode_number__gt=self.episode_number,
            is_active=True
        ).order_by('episode_number').first()

class DownloadLink(models.Model):
    QUALITY_CHOICES = [
        ('360p', '360p'),
        ('480p', '480p'),
        ('720p', '720p'),
        ('1080p', '1080p'),
    ]

    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, related_name='download_links')
    quality = models.CharField(max_length=10, choices=QUALITY_CHOICES)
    url = models.URLField(max_length=1000)
    file_size = models.CharField(max_length=20, blank=True)
    host_name = models.CharField(max_length=50, default='unknown')
    label = models.CharField(max_length=100, blank=True)  # Display label for the link
    
    # Link Management
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    fetch_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['quality', 'host_name']
        indexes = [
            models.Index(fields=['episode', 'quality']),
            models.Index(fields=['host_name']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.episode} - {self.quality} ({self.host_name})"

    @property
    def is_expired(self):
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False

    def increment_fetch_count(self):
        self.fetch_count = F('fetch_count') + 1
        self.save(update_fields=['fetch_count'])
        self.refresh_from_db(fields=['fetch_count'])

# Additional models for user features (if you add authentication later)

class WatchHistory(models.Model):
    """Track user's watch history (if you add user authentication later)"""
    # user = models.ForeignKey(User, on_delete=models.CASCADE)  # Uncomment when adding auth
    anime = models.ForeignKey(Anime, on_delete=models.CASCADE)
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE, null=True, blank=True)
    last_watched_at = models.DateTimeField(auto_now=True)
    progress_seconds = models.PositiveIntegerField(default=0)  # Progress in seconds
    completed = models.BooleanField(default=False)
    
    class Meta:
        # unique_together = ['user', 'anime']  # Uncomment when adding auth
        ordering = ['-last_watched_at']

    def __str__(self):
        return f"Watch history for {self.anime.title}"

class AnimeRating(models.Model):
    """Store anime ratings (if you add user authentication later)"""
    # user = models.ForeignKey(User, on_delete=models.CASCADE)  # Uncomment when adding auth
    anime = models.ForeignKey(Anime, on_delete=models.CASCADE, related_name='user_ratings')
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    review = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # unique_together = ['user', 'anime']  # Uncomment when adding auth
        pass

    def __str__(self):
        return f"Rating {self.rating}/10 for {self.anime.title}"

class Watchlist(models.Model):
    """User's watchlist (if you add user authentication later)"""
    # user = models.ForeignKey(User, on_delete=models.CASCADE)  # Uncomment when adding auth
    anime = models.ForeignKey(Anime, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[
        ('want_to_watch', 'Want to Watch'),
        ('watching', 'Currently Watching'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
        ('dropped', 'Dropped'),
    ], default='want_to_watch')

    class Meta:
        # unique_together = ['user', 'anime']  # Uncomment when adding auth
        ordering = ['-added_at']

    def __str__(self):
        return f"Watchlist entry for {self.anime.title}"