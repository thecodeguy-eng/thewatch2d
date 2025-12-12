# models.py
from django.db import models
from django.utils.text import slugify
from django.core.validators import URLValidator

class Category(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Game(models.Model):
    REPACK_STATUS_CHOICES = [
        ('new', 'New'),
        ('updated', 'Updated'),
        ('active', 'Active'),
    ]

    # Basic Info
    title = models.CharField(max_length=500)
    slug = models.SlugField(max_length=500, unique=True)
    repack_number = models.CharField(max_length=20, blank=True)  # e.g., #6364
    version = models.CharField(max_length=500, blank=True)  # INCREASED from 200
    
    # Description & Details
    short_description = models.TextField(blank=True)
    full_description = models.TextField(blank=True)
    game_description = models.TextField(blank=True)  # From spoiler section
    
    # Technical Details
    original_size = models.CharField(max_length=100, blank=True)  # INCREASED from 50
    repack_size = models.CharField(max_length=100, blank=True)  # INCREASED from 50
    languages = models.TextField(blank=True)  # CHANGED to TextField for long lists
    
    # Companies
    companies = models.TextField(blank=True)  # CHANGED to TextField for multiple companies
    
    # Repack Features
    repack_features = models.TextField(blank=True)
    installation_time = models.CharField(max_length=500, blank=True)  # INCREASED from 200
    installation_size = models.CharField(max_length=200, blank=True)  # INCREASED from 100
    
    # Images
    cover_image = models.URLField(max_length=1000, blank=True)
    
    # Metadata
    categories = models.ManyToManyField(Category, related_name='games', blank=True)
    tags = models.ManyToManyField(Tag, related_name='games', blank=True)
    
    # Post Info
    post_url = models.URLField(max_length=1000, unique=True)
    post_id = models.IntegerField(unique=True)
    post_date = models.DateTimeField()
    modified_date = models.DateTimeField()
    
    # Status
    status = models.CharField(max_length=20, choices=REPACK_STATUS_CHOICES, default='active')
    is_active = models.BooleanField(default=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    scraped_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-post_date']
        indexes = [
            models.Index(fields=['-post_date']),
            models.Index(fields=['slug']),
            models.Index(fields=['post_id']),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Screenshot(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='screenshots')
    image_url = models.URLField(max_length=1000)
    thumbnail_url = models.URLField(max_length=1000, blank=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.game.title} - Screenshot {self.order}"


class DownloadMirror(models.Model):
    MIRROR_TYPE_CHOICES = [
        ('direct', 'Direct Download'),
        ('torrent', 'Torrent'),
        ('magnet', 'Magnet Link'),
    ]

    FILEHOSTER_CHOICES = [
        ('datanodes', 'DataNodes'),
        ('fuckingfast', 'FuckingFast'),
        ('multiupload', 'MultiUpload'),
        ('1337x', '1337x'),
        ('rutor', 'RuTor'),
        ('tapochek', 'Tapochek.net'),
    ]

    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='download_mirrors')
    mirror_type = models.CharField(max_length=20, choices=MIRROR_TYPE_CHOICES)
    filehoster = models.CharField(max_length=50, choices=FILEHOSTER_CHOICES)
    
    # For direct downloads
    parts = models.JSONField(default=list, blank=True)  # List of download part URLs
    
    # For torrents
    torrent_url = models.URLField(max_length=2000, blank=True)
    magnet_link = models.TextField(blank=True)
    torrent_file_url = models.URLField(max_length=2000, blank=True)
    
    # Additional info
    notes = models.CharField(max_length=500, blank=True)  # e.g., "Speed & Usability"
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'mirror_type']

    def __str__(self):
        return f"{self.game.title} - {self.filehoster} ({self.mirror_type})"


class GameUpdate(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='updates')
    update_title = models.CharField(max_length=500)
    version_from = models.CharField(max_length=200, blank=True)
    version_to = models.CharField(max_length=200, blank=True)
    download_url = models.URLField(max_length=2000)
    source = models.CharField(max_length=200, blank=True)  # e.g., "ElAmigos", "scene"
    file_name = models.CharField(max_length=500)
    release_date = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.game.title} - {self.update_title}"


class SystemRequirements(models.Model):
    game = models.OneToOneField(Game, on_delete=models.CASCADE, related_name='requirements')
    minimum_ram = models.CharField(max_length=100, blank=True)
    recommended_ram = models.CharField(max_length=100, blank=True)
    minimum_storage = models.CharField(max_length=100, blank=True)
    os_requirements = models.TextField(blank=True)
    additional_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Requirements for {self.game.title}"


class ScrapingLog(models.Model):
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('error', 'Error'),
        ('partial', 'Partial'),
    ]

    game = models.ForeignKey(Game, on_delete=models.SET_NULL, null=True, blank=True, related_name='scraping_logs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    message = models.TextField()
    page_url = models.URLField(max_length=1000, blank=True)
    error_details = models.TextField(blank=True)
    scraped_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scraped_at']

    def __str__(self):
        return f"{self.status} - {self.scraped_at.strftime('%Y-%m-%d %H:%M')}"