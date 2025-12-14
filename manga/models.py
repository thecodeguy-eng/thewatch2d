from django.db import models
from django.db.models import F
from django.urls import reverse
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
import uuid

class MangaCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    image = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Manga Categories"
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('manga:category_detail', kwargs={'slug': self.slug})

    @property
    def manga_count(self):
        return self.manga_set.filter(is_active=True).count()


class MangaGenre(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    color = models.CharField(max_length=7, default='#6366f1')
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('manga:genre_detail', kwargs={'slug': self.slug})

    @property
    def manga_count(self):
        return self.manga_set.filter(is_active=True).count()


def generate_manga_session():
    """Generate unique session ID for manga"""
    return f"manga_{uuid.uuid4().hex[:12]}"


class Manga(models.Model):
    STATUS_CHOICES = [
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('hiatus', 'Hiatus'),
        ('dropped', 'Dropped'),
    ]
    
    TYPE_CHOICES = [
        ('manga', 'Manga'),
        ('manhwa', 'Manhwa'),
        ('manhua', 'Manhua'),
        ('webtoon', 'Webtoon'),
    ]

    # WordPress Post ID (from JSON)
    wp_post_id = models.IntegerField(unique=True, null=True, blank=True)
    
    # Basic Info
    manga_id = models.IntegerField(default=0)
    manga_session = models.CharField(max_length=255, unique=True, default=generate_manga_session)
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    alternative_titles = models.TextField(blank=True, help_text="Separate with commas")
    
    # Metadata
    category = models.ForeignKey(MangaCategory, on_delete=models.SET_NULL, null=True, blank=True)
    genres = models.ManyToManyField(MangaGenre, blank=True)
    description = models.TextField(blank=True)
    cover_url = models.URLField(max_length=500, blank=True)
    banner_url = models.URLField(max_length=500, blank=True)
    
    # Type & Status
    manga_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='manga')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ongoing')
    total_chapters = models.PositiveIntegerField(default=0)
    current_chapter = models.PositiveIntegerField(default=0)
    
    # Ratings & Stats
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True,
                                validators=[MinValueValidator(0), MaxValueValidator(10)])
    views = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    bookmarks = models.PositiveIntegerField(default=0)
    
    # Additional Info
    author = models.CharField(max_length=200, blank=True)
    artist = models.CharField(max_length=200, blank=True)
    year = models.PositiveIntegerField(null=True, blank=True)
    serialization = models.CharField(max_length=100, blank=True)
    
    # SEO & Meta (from WordPress JSON)
    meta_title = models.CharField(max_length=255, blank=True)
    meta_description = models.TextField(max_length=500, blank=True)
    keywords = models.CharField(max_length=255, blank=True)
    
    # WordPress specific fields
    wp_author_id = models.IntegerField(null=True, blank=True)
    wp_featured_media = models.IntegerField(null=True, blank=True)
    wp_link = models.URLField(max_length=500, blank=True)
    
    # Flags
    is_featured = models.BooleanField(default=False)
    is_trending = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_adult = models.BooleanField(default=False)
    is_colored = models.BooleanField(default=False)
    
    # Timestamps
    released_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # WordPress dates
    wp_date = models.DateTimeField(null=True, blank=True)
    wp_modified = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['manga_id']),
            models.Index(fields=['wp_post_id']),
            models.Index(fields=['status']),
            models.Index(fields=['is_featured']),
            models.Index(fields=['is_trending']),
            models.Index(fields=['year']),
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('manga:detail', kwargs={'slug': self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Manga.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        
        if not self.meta_title:
            self.meta_title = f"Read {self.title} - Free Manga Online | Watch2D"
        
        if not self.meta_description:
            self.meta_description = f"Read {self.title} manga online for free. High-quality chapters updated regularly on Watch2D."
            
        super().save(*args, **kwargs)

    @property
    def progress_percentage(self):
        if self.total_chapters > 0:
            return (self.current_chapter / self.total_chapters) * 100
        return 0

    @property
    def is_completed_manga(self):
        return self.status == 'completed'

    def increment_views(self):
        self.views = F('views') + 1
        self.save(update_fields=['views'])
        self.refresh_from_db(fields=['views'])

    def get_latest_chapters(self, count=12):
        return self.chapters.filter(is_active=True).order_by('-chapter_number')[:count]

    def get_related_manga(self, count=6):
        related = Manga.objects.filter(
            is_active=True
        ).exclude(id=self.id)
        
        if self.category:
            related = related.filter(category=self.category)
        
        if self.genres.exists():
            related = related.filter(genres__in=self.genres.all()).distinct()
            
        return related.order_by('-views')[:count]


def generate_chapter_session():
    """Generate unique session ID for chapter"""
    return f"chapter_{uuid.uuid4().hex[:12]}"


class Chapter(models.Model):
    manga = models.ForeignKey(Manga, on_delete=models.CASCADE, related_name='chapters')
    
    # Chapter Info
    chapter_id = models.IntegerField()
    session = models.CharField(max_length=255, unique=True, default=generate_chapter_session)
    chapter_number = models.FloatField()
    volume = models.PositiveIntegerField(null=True, blank=True)
    title = models.CharField(max_length=255, blank=True)
    
    # Technical Details
    translator = models.CharField(max_length=100, blank=True, default='Unknown')
    pages_count = models.PositiveIntegerField(default=0)
    thumbnail_url = models.URLField(max_length=500, blank=True)
    
    # Source Info
    source_url = models.URLField(max_length=500, blank=True)
    publish_date = models.DateTimeField(null=True, blank=True)
    
    # Flags
    is_active = models.BooleanField(default=True)
    
    # Stats
    views = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['manga', 'chapter_number']
        unique_together = ['manga', 'chapter_number']
        indexes = [
            models.Index(fields=['chapter_id']),
            models.Index(fields=['manga', 'chapter_number']),
            models.Index(fields=['publish_date']),
        ]

    def __str__(self):
        return f"{self.manga.title} - Chapter {self.chapter_number}"

    def get_absolute_url(self):
        return reverse('manga:chapter_detail', kwargs={
            'manga_slug': self.manga.slug,
            'chapter_number': str(self.chapter_number).replace('.', '-')
        })

    @property
    def display_title(self):
        if self.title and self.title != f"Chapter {self.chapter_number}":
            return f"Chapter {self.chapter_number}: {self.title}"
        return f"Chapter {self.chapter_number}"

    def increment_views(self):
        self.views = F('views') + 1
        self.save(update_fields=['views'])
        self.refresh_from_db(fields=['views'])

    def get_previous_chapter(self):
        return Chapter.objects.filter(
            manga=self.manga,
            chapter_number__lt=self.chapter_number,
            is_active=True
        ).order_by('-chapter_number').first()

    def get_next_chapter(self):
        return Chapter.objects.filter(
            manga=self.manga,
            chapter_number__gt=self.chapter_number,
            is_active=True
        ).order_by('chapter_number').first()


class MangaPage(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='pages')
    page_number = models.PositiveIntegerField()
    image_url = models.URLField(max_length=1000)
    
    local_image = models.ImageField(upload_to='manga_pages/', blank=True, null=True)
    
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['chapter', 'page_number']
        unique_together = ['chapter', 'page_number']
        indexes = [
            models.Index(fields=['chapter', 'page_number']),
        ]

    def __str__(self):
        return f"{self.chapter} - Page {self.page_number}"


class DownloadLink(models.Model):
    QUALITY_CHOICES = [
        ('low', 'Low Quality'),
        ('medium', 'Medium Quality'),
        ('high', 'High Quality'),
        ('original', 'Original Quality'),
    ]
    
    FORMAT_CHOICES = [
        ('pdf', 'PDF'),
        ('cbz', 'CBZ'),
        ('zip', 'ZIP'),
        ('epub', 'EPUB'),
    ]

    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='download_links')
    quality = models.CharField(max_length=10, choices=QUALITY_CHOICES)
    format = models.CharField(max_length=10, choices=FORMAT_CHOICES)
    url = models.URLField(max_length=1000)
    file_size = models.CharField(max_length=20, blank=True)
    host_name = models.CharField(max_length=50, default='unknown')
    label = models.CharField(max_length=100, blank=True)
    
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    download_count = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['quality', 'format']
        indexes = [
            models.Index(fields=['chapter', 'quality']),
            models.Index(fields=['format']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.chapter} - {self.quality} ({self.format})"

    @property
    def is_expired(self):
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False

    def increment_download_count(self):
        self.download_count = F('download_count') + 1
        self.save(update_fields=['download_count'])
        self.refresh_from_db(fields=['download_count'])


class ReadingHistory(models.Model):
    # user = models.ForeignKey(User, on_delete=models.CASCADE)
    manga = models.ForeignKey(Manga, on_delete=models.CASCADE)
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, null=True, blank=True)
    page_number = models.PositiveIntegerField(default=1)
    last_read_at = models.DateTimeField(auto_now=True)
    completed = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-last_read_at']

    def __str__(self):
        return f"Reading history for {self.manga.title}"


class MangaRating(models.Model):
    # user = models.ForeignKey(User, on_delete=models.CASCADE)
    manga = models.ForeignKey(Manga, on_delete=models.CASCADE, related_name='user_ratings')
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    review = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Rating {self.rating}/10 for {self.manga.title}"


class Bookmark(models.Model):
    # user = models.ForeignKey(User, on_delete=models.CASCADE)
    manga = models.ForeignKey(Manga, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[
        ('plan_to_read', 'Plan to Read'),
        ('reading', 'Currently Reading'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
        ('dropped', 'Dropped'),
    ], default='plan_to_read')

    class Meta:
        ordering = ['-added_at']

    def __str__(self):
        return f"Bookmark for {self.manga.title}"
    


class Comment(models.Model):
    manga = models.ForeignKey(Manga, on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    
    # Comment details
    name = models.CharField(max_length=100, help_text="Commenter's name")
    email = models.EmailField(blank=True, help_text="Optional email (not displayed)")
    comment = models.TextField()
    
    # For nested comments (replies)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    
    # Moderation
    is_approved = models.BooleanField(default=True, help_text="Set to False if you want to moderate comments")
    is_active = models.BooleanField(default=True)
    
    # Metadata
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['manga', 'is_approved', 'is_active']),
            models.Index(fields=['chapter', 'is_approved', 'is_active']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        target = self.manga or self.chapter
        return f"Comment by {self.name} on {target}"
    
    @property
    def is_reply(self):
        return self.parent is not None
    
    def get_replies(self):
        return self.replies.filter(is_approved=True, is_active=True).order_by('created_at')