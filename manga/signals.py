from django.db import models
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.text import slugify
from .models import Manga, Chapter, MangaPage

@receiver(pre_save, sender=Manga)
def generate_manga_slug(sender, instance, **kwargs):
    """Auto-generate slug for manga if not provided"""
    if not instance.slug:
        base_slug = slugify(instance.title)
        slug = base_slug
        counter = 1
        
        while Manga.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        instance.slug = slug

@receiver(post_save, sender=Chapter)
def update_manga_chapter_count(sender, instance, created, **kwargs):
    """Update manga's total chapter count when new chapter is added"""
    if created:
        manga = instance.manga
        max_chapter = Chapter.objects.filter(manga=manga).aggregate(
            max_ch=models.Max('chapter_number')
        )['max_ch'] or 0
        
        if max_chapter > manga.total_chapters:
            manga.total_chapters = int(max_chapter)
            manga.save(update_fields=['total_chapters'])

@receiver(post_save, sender=MangaPage)
def update_chapter_page_count(sender, instance, created, **kwargs):
    """Update chapter's page count when pages are added"""
    if created:
        chapter = instance.chapter
        page_count = MangaPage.objects.filter(chapter=chapter).count()
        
        if page_count != chapter.pages_count:
            chapter.pages_count = page_count
            chapter.save(update_fields=['pages_count'])