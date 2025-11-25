from django.db import models
from django.utils.text import slugify
from django.urls import reverse

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Font Awesome icon class")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('category_detail', kwargs={'slug': self.slug})


class APK(models.Model):
    TYPE_CHOICES = [
        ('game', 'Game'),
        ('app', 'App'),
    ]
    
    STATUS_CHOICES = [
        ('modded', 'Modded'),
        ('premium', 'Premium'),
        ('pro', 'Pro'),
        ('unlocked', 'Unlocked'),
        ('paid', 'Paid'),
        ('original', 'Original'),
    ]

    # Basic Info
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=300, unique=True, blank=True)
    apk_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='game')
    description = models.TextField(blank=True)
    
    # Images
    icon_url = models.URLField(max_length=500, blank=True)
    cover_image_url = models.URLField(max_length=500, blank=True)
    
    # APK Details
    version = models.CharField(max_length=50, blank=True)
    size = models.CharField(max_length=50, blank=True)
    android_version = models.CharField(max_length=50, blank=True, help_text="Minimum Android version")
    architecture = models.CharField(max_length=50, blank=True, help_text="arm7, arm8, x86, etc.")
    package_name = models.CharField(max_length=255, blank=True)
    
    # Status & Mod Info
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='modded')
    mod_features = models.TextField(blank=True, help_text="Mod features like Unlimited Money, etc.")
    
    # Downloads & Links
    download_url = models.URLField(max_length=1000, blank=True)
    source_url = models.URLField(max_length=500, unique=True)
    
    # Relationships
    categories = models.ManyToManyField(Category, related_name='apks', blank=True)
    
    # Stats
    downloads_count = models.CharField(max_length=50, blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=1, null=True, blank=True)
    
    # Meta
    is_active = models.BooleanField(default=True)
    featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "APK"
        verbose_name_plural = "APKs"
        indexes = [
            models.Index(fields=['apk_type', '-created_at']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_apk_type_display()})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            self.slug = base_slug
            counter = 1
            while APK.objects.filter(slug=self.slug).exists():
                self.slug = f"{base_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('apk_detail', kwargs={'slug': self.slug})


class Screenshot(models.Model):
    apk = models.ForeignKey(APK, on_delete=models.CASCADE, related_name='screenshots')
    image_url = models.URLField(max_length=500)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f"Screenshot for {self.apk.title}"


class APKVersion(models.Model):
    apk = models.ForeignKey(APK, on_delete=models.CASCADE, related_name='versions')
    version = models.CharField(max_length=50)
    download_url = models.URLField(max_length=1000)
    size = models.CharField(max_length=50, blank=True)
    release_date = models.DateField(null=True, blank=True)
    changelog = models.TextField(blank=True)
    is_latest = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['apk', 'version']

    def __str__(self):
        return f"{self.apk.title} v{self.version}"

    def save(self, *args, **kwargs):
        if self.is_latest:
            APKVersion.objects.filter(apk=self.apk, is_latest=True).update(is_latest=False)
        super().save(*args, **kwargs)