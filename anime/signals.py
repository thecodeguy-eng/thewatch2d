from django.db import models  # Add this import
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils.text import slugify
from .models import Anime, Episode

@receiver(pre_save, sender=Anime)
def generate_anime_slug(sender, instance, **kwargs):
    """Auto-generate slug for anime if not provided"""
    if not instance.slug:
        base_slug = slugify(instance.title)
        slug = base_slug
        counter = 1
        
        while Anime.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        instance.slug = slug

@receiver(post_save, sender=Episode)
def update_anime_episode_count(sender, instance, created, **kwargs):
    """Update anime's total episode count when new episode is added"""
    if created:
        anime = instance.anime
        max_episode = Episode.objects.filter(anime=anime).aggregate(
            max_ep=models.Max('episode_number')  # Now this will work
        )['max_ep'] or 0
        
        if max_episode > anime.total_episodes:
            anime.total_episodes = max_episode
            anime.save(update_fields=['total_episodes'])