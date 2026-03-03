from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.contrib.sites.models import Site
from .models import Movie, Category


class CustomSitemapMixin:
    def get_urls(self, site=None, **kwargs):
        # Force correct domain to prevent Google "URL not allowed" errors
        site = site or Site(domain='watch2d.net', name='Watch2D')
        return super().get_urls(site=site, **kwargs)


class HomeSitemap(CustomSitemapMixin, Sitemap):
    changefreq = 'daily'
    priority = 1.0

    def items(self):
        # Return the main homepage URL name
        return ['main:home']

    def location(self, item):
        return reverse(item)


class SearchSitemap(CustomSitemapMixin, Sitemap):
    changefreq = 'weekly'
    priority = 0.5

    def items(self):
        # Namespaced URL name for search results
        return ['movies:search_results']

    def location(self, item):
        return reverse(item)


class CategorySitemap(CustomSitemapMixin, Sitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        # Explicit ordering to avoid pagination warnings
        return Category.objects.all().order_by('name')

    def location(self, obj):
        return reverse('movies:category_movies', args=[obj.id])


class mastermap(CustomSitemapMixin, Sitemap):
    changefreq = 'daily'
    priority = 0.9

    def items(self):
        # Exclude movies without a valid video URL and order by primary key
        return (
            Movie.objects
            .exclude(video_url__isnull=True)
            .exclude(video_url__exact='')
            .order_by('pk')
        )

    def location(self, obj):
        return reverse('movies:movie_detail', args=[obj.pk])


# Optional: Add sitemaps for other apps
class AnimeSitemap(CustomSitemapMixin, Sitemap):
    changefreq = 'daily'
    priority = 0.9

    def items(self):
        from anime.models import Anime
        return Anime.objects.filter(is_active=True).order_by('pk')

    def location(self, obj):
        return reverse('anime:detail', kwargs={'slug': obj.slug})


class MangaSitemap(CustomSitemapMixin, Sitemap):
    changefreq = 'daily'
    priority = 0.9

    def items(self):
        from manga.models import Manga
        return Manga.objects.filter(is_active=True).order_by('pk')

    def location(self, obj):
        return reverse('manga:detail', kwargs={'slug': obj.slug})


class APKSitemap(CustomSitemapMixin, Sitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        from apk_store.models import APK
        return APK.objects.filter(is_active=True).order_by('pk')

    def location(self, obj):
        return reverse('apk_store:apk_detail', kwargs={'slug': obj.slug})


class PCGamesSitemap(CustomSitemapMixin, Sitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        from pc_games.models import Game
        return Game.objects.filter(is_active=True).order_by('pk')

    def location(self, obj):
        return reverse('pc_games:game_detail', kwargs={'slug': obj.slug})